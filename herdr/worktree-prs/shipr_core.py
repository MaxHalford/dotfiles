"""Pull request state and Git/Herdr operations for shipr."""

import json
import os
import queue
import re
import signal
import subprocess
import threading
from collections import deque
from dataclasses import dataclass
from pathlib import Path
from typing import Optional
from urllib.parse import urlsplit


PR_FIELDS = "number,title,url,state,isDraft,headRefName,reviewDecision"
PR_LIMIT = 50
ANSI_ESCAPE = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")


class CommandError(Exception):
    pass


class Operation:
    def __init__(self, events):
        self.events = events
        self.cancelled = threading.Event()
        self.lock = threading.Lock()
        self.process = None

    def stage(self, label):
        self.events.put(("stage", label))

    def line(self, value):
        line = clean(value.strip())
        if line:
            try:
                self.events.put_nowait(("line", line))
            except queue.Full:
                pass

    def attach(self, process):
        with self.lock:
            self.process = process
            cancelled = self.cancelled.is_set()
        if cancelled:
            self._signal(process, signal.SIGTERM)

    def detach(self, process):
        with self.lock:
            if self.process is process:
                self.process = None

    @staticmethod
    def _signal(process, sig):
        if process.poll() is None:
            try:
                os.killpg(process.pid, sig)
            except ProcessLookupError:
                pass

    def cancel(self):
        self.cancelled.set()
        with self.lock:
            process = self.process
        if process:
            self._signal(process, signal.SIGTERM)

            def force_stop():
                with self.lock:
                    still_current = self.process is process
                if still_current:
                    self._signal(process, signal.SIGKILL)

            timer = threading.Timer(2, force_stop)
            timer.daemon = True
            timer.start()


def run(argv, cwd=None, timeout=45, operation=None):
    env = os.environ.copy()
    env["GIT_TERMINAL_PROMPT"] = "0"
    env["GH_PROMPT_DISABLED"] = "1"
    if operation is not None:
        if operation.cancelled.is_set():
            raise CommandError("Cancelled; check Git status and PRs before retrying")
        try:
            with subprocess.Popen(
                argv, cwd=cwd, env=env, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT, text=True, errors="replace", start_new_session=True
            ) as process:
                operation.attach(process)
                output = deque(maxlen=200)
                try:
                    for line in process.stdout:
                        output.append(line)
                        operation.line(line)
                    returncode = process.wait()
                finally:
                    operation.detach(process)
        except OSError as error:
            raise CommandError(str(error)) from error
        if operation.cancelled.is_set():
            raise CommandError("Cancelled; check Git status and PRs before retrying")
        result = "".join(output)
        if returncode:
            raise CommandError(result[-4000:].strip() or f"Command failed: {argv[0]}")
        return result
    try:
        result = subprocess.run(
            argv, cwd=cwd, env=env, capture_output=True, text=True, timeout=timeout, check=False
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        raise CommandError(str(error)) from error
    if result.returncode:
        raise CommandError((result.stderr or result.stdout).strip() or f"Command failed: {argv[0]}")
    return result.stdout


def plugin_context():
    try:
        context = json.loads(os.environ.get("HERDR_PLUGIN_CONTEXT_JSON", "{}"))
    except ValueError:
        return {}
    return context if isinstance(context, dict) else {}


def repository_directory():
    context = plugin_context()
    cwd = context.get("focused_pane_cwd") or context.get("workspace_cwd")
    if cwd:
        return Path(run(["git", "rev-parse", "--show-toplevel"], cwd=cwd).strip())
    workspace_id = os.environ.get("HERDR_WORKSPACE_ID") or context.get("workspace_id")
    pane_id = context.get("pane_id") or context.get("focused_pane_id")
    snapshot_response = json.loads(run([os.environ.get("HERDR_BIN_PATH", "herdr"), "api", "snapshot"]))
    snapshot = snapshot_response["result"]["snapshot"]
    panes = snapshot["panes"]
    candidates = [pane for pane in panes if pane.get("pane_id") == pane_id]
    candidates += [pane for pane in panes if pane.get("workspace_id") == workspace_id and pane.get("focused")]
    candidates += [pane for pane in panes if pane.get("workspace_id") == workspace_id]
    if not candidates:
        raise CommandError("No focused Herdr workspace was found")
    cwd = candidates[0].get("foreground_cwd") or candidates[0].get("cwd")
    if not cwd:
        raise CommandError("The focused Herdr pane has no working directory")
    return Path(run(["git", "rev-parse", "--show-toplevel"], cwd=cwd).strip())


@dataclass
class Worktree:
    path: Path
    branch: str
    unavailable: bool = False
    head: str = ""
    dirty: bool = False
    current: bool = False
    is_base: bool = False
    pr: Optional[dict] = None
    pr_unavailable: bool = False


@dataclass
class PullRequest:
    repo: Path
    pr: dict
    worktree: Optional[Path] = None

    @property
    def branch(self):
        return self.pr.get("headRefName") or ""


def parse_worktrees(raw):
    trees = []
    for record in raw.split("\0\0"):
        fields = record.strip("\0").split("\0")
        if not fields or not fields[0].startswith("worktree "):
            continue
        path = Path(fields[0][9:])
        branch = next((field[7:] for field in fields if field.startswith("branch ")), "(detached)")
        head = next((field[5:] for field in fields if field.startswith("HEAD ")), "")
        if branch.startswith("refs/heads/"):
            branch = branch[len("refs/heads/"):]
        unavailable = any(field.startswith("prunable ") for field in fields) or not path.is_dir()
        trees.append(Worktree(path, branch, unavailable, head=head))
    return trees


def matching_pr(prs, branch):
    alias = re.fullmatch(r"shipr/pr-(\d+)(?:-[0-9a-f]{10}(?:-\d+)?)?", branch)
    if alias:
        return next((pr for pr in prs if str(pr.get("number")) == alias.group(1)), None)
    matches = [pr for pr in prs if pr.get("headRefName") == branch and pr.get("state") == "OPEN"]
    return matches[0] if len(matches) == 1 else None


def pr_status(pr):
    if not pr:
        return "No PR"
    state = pr.get("state", "UNKNOWN")
    if state != "OPEN":
        return state.title()
    label = "Draft" if pr.get("isDraft") else "Open"
    review = pr.get("reviewDecision")
    if review == "CHANGES_REQUESTED":
        label += " / changes requested"
    elif review == "REVIEW_REQUIRED":
        label += " / review needed"
    return label


def default_base(repo, trees):
    try:
        remote = run(["git", "symbolic-ref", "--quiet", "--short", "refs/remotes/origin/HEAD"],
                     cwd=repo).strip()
    except CommandError:
        remote = ""
    if remote:
        branch = remote.split("/", 1)[-1]
        if any(tree.branch == branch for tree in trees):
            return branch
        return remote
    for branch in ("main", "master"):
        try:
            run(["git", "rev-parse", "--verify", f"refs/heads/{branch}"], cwd=repo)
            return branch
        except CommandError:
            pass
    return trees[0].branch if trees and trees[0].branch != "(detached)" else None


def load_open_prs(repo):
    try:
        prs = json.loads(run(["gh", "pr", "list", "--state", "open", "--limit", str(PR_LIMIT),
                              "--json", PR_FIELDS], cwd=repo))
    except (CommandError, ValueError) as exc:
        return [], f"GitHub refresh failed: {exc}"
    return prs, ""


def enrich_worktree(tree, repo, base, prs, pr_error):
    if tree.unavailable:
        return
    base_branch = base.removeprefix("origin/") if base else ""
    tree.is_base = bool(base_branch and tree.branch == base_branch)
    tree.pr_unavailable = bool(pr_error)
    try:
        tree.dirty = has_changes(tree.path)
    except CommandError:
        tree.unavailable = True
        return
    tree.pr = matching_pr(prs, tree.branch)
    tree.current = tree.path.resolve() == repo.resolve()


def pull_request_rows(repo, prs, trees):
    rows = []
    paths_by_branch = {tree.branch: tree.path for tree in trees if not tree.unavailable}
    for pr in prs:
        if pr.get("state") != "OPEN" or not pr.get("number"):
            continue
        worktree = next((tree.path for tree in trees if not tree.unavailable and
                         tree.branch.startswith(f"shipr/pr-{pr['number']}-")), None)
        if worktree is None:
            worktree = paths_by_branch.get(f"shipr/pr-{pr['number']}")
        if worktree is None and sum(other.get("headRefName") == pr.get("headRefName") for other in prs) == 1:
            worktree = paths_by_branch.get(pr.get("headRefName"))
        rows.append(PullRequest(repo, pr, worktree))
    return rows


def load_board(repo):
    trees = parse_worktrees(run(["git", "worktree", "list", "--porcelain", "-z"], cwd=repo))
    base = default_base(repo, trees)
    prs, error = load_open_prs(repo)
    current = next((tree for tree in trees if tree.path.resolve() == repo.resolve()), None)
    if current is None:
        raise CommandError("The current directory is not a registered worktree")
    enrich_worktree(current, repo, base, prs, error)
    return pull_request_rows(repo, prs, trees), current, error


def has_changes(path, operation=None):
    return bool(run(["git", "status", "--porcelain"], cwd=path, operation=operation))


def commit_all(path, message, operation=None):
    if operation:
        operation.stage("Checking changes")
    if not has_changes(path, operation):
        return False
    if operation:
        operation.stage("Staging all changes")
    run(["git", "add", "-A"], cwd=path, operation=operation)
    if operation:
        operation.stage("Committing (hooks may run)")
    run(["git", "commit", "-m", message], cwd=path, timeout=120, operation=operation)
    return True


def push(path, branch, operation=None):
    if operation:
        operation.stage("Pushing branch")
    try:
        run(["git", "rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{upstream}"], cwd=path,
            operation=operation)
    except CommandError:
        if operation and operation.cancelled.is_set():
            raise
        if branch.startswith("shipr/pr-"):
            raise CommandError("This PR checkout has no push upstream; configure one before pushing")
        run(["git", "push", "-u", "origin", branch], cwd=path, timeout=120, operation=operation)
    else:
        run(["git", "push"], cwd=path, timeout=120, operation=operation)


def open_pr(tree):
    if not tree.pr or tree.pr.get("state") != "OPEN" or not tree.pr.get("url"):
        raise CommandError("No open PR URL is available; refresh and retry")
    run(["open", tree.pr["url"]], cwd=tree.repo if isinstance(tree, PullRequest) else tree.path)


def herdr_source(repo):
    context = plugin_context()
    workspace_id = os.environ.get("HERDR_WORKSPACE_ID") or context.get("workspace_id")
    return ["--workspace", workspace_id] if workspace_id else ["--cwd", str(repo)]


def open_herdr_worktree(repo, path, label=None):
    argv = [os.environ.get("HERDR_BIN_PATH", "herdr"), "worktree", "open", *herdr_source(repo),
            "--path", str(path)]
    if label:
        argv.extend(["--label", label])
    argv.append("--focus")
    run(argv, cwd=repo)


def checkout_pr(row, operation=None):
    if row.pr.get("state") != "OPEN" or not row.pr.get("number"):
        raise CommandError("This PR is no longer open; refresh and retry")
    if row.worktree is not None:
        raise CommandError(f"PR #{row.pr['number']} is already checked out in {row.worktree}")
    number = int(row.pr["number"])
    if operation:
        operation.stage(f"Fetching PR #{number}")
    run(["git", "fetch", "origin", f"pull/{number}/head"], cwd=row.repo,
        timeout=120, operation=operation)
    sha = run(["git", "rev-parse", "--short=10", "FETCH_HEAD"], cwd=row.repo,
              operation=operation).strip()
    branch = f"shipr/pr-{number}-{sha}"
    suffix = 2
    while True:
        try:
            run(["git", "show-ref", "--verify", "--quiet", f"refs/heads/{branch}"],
                cwd=row.repo, operation=operation)
        except CommandError:
            if operation and operation.cancelled.is_set():
                raise
            break
        branch = f"shipr/pr-{number}-{sha}-{suffix}"
        suffix += 1
    if operation:
        operation.stage(f"Opening PR #{number} in Herdr")
    run([os.environ.get("HERDR_BIN_PATH", "herdr"), "worktree", "create",
         *herdr_source(row.repo), "--branch", branch, "--base", "FETCH_HEAD",
         "--label", f"PR #{number}", "--focus"], cwd=row.repo, timeout=120,
        operation=operation)
    return branch


def push_to_pr(row, operation=None):
    number = row.pr.get("number")
    if not number:
        raise CommandError("The PR number is unavailable")
    if operation:
        operation.stage(f"Checking PR #{number} push target")
    pr = json.loads(run(["gh", "pr", "view", str(number), "--json",
                         "state,headRefName,headRepository,headRepositoryOwner,url"],
                        cwd=row.repo, operation=operation))
    if pr.get("state") != "OPEN":
        raise CommandError(f"PR #{number} is no longer open")
    repository = pr.get("headRepository") or {}
    url = repository.get("url")
    if not url:
        slug = repository.get("nameWithOwner")
        owner = (pr.get("headRepositoryOwner") or {}).get("login")
        if not slug and owner and repository.get("name"):
            slug = f"{owner}/{repository['name']}"
        pr_url = urlsplit(pr.get("url") or "")
        if slug and len(slug.split("/")) == 2 and pr_url.scheme == "https" and pr_url.netloc:
            url = f"{pr_url.scheme}://{pr_url.netloc}/{slug}"
    branch = pr.get("headRefName")
    if not url or not branch:
        raise CommandError(f"PR #{number} has no available head repository and branch")
    if operation:
        operation.stage(f"Pushing to PR #{number}")
    remote = url.rstrip("/")
    if not remote.endswith(".git"):
        remote += ".git"
    run(["git", "push", remote, f"HEAD:refs/heads/{branch}"],
        cwd=row.worktree, timeout=120, operation=operation)


def publish(tree, message, create_pr, operation=None):
    if tree.unavailable or tree.branch == "(detached)":
        raise CommandError("This worktree has no usable branch")
    current_branch = run(["git", "branch", "--show-current"], cwd=tree.path,
                         operation=operation).strip()
    if current_branch != tree.branch:
        raise CommandError("This worktree changed branches; refresh shipr before publishing")
    if create_pr and tree.pr and tree.pr.get("state") == "OPEN":
        raise CommandError("This branch already has an open pull request")
    if create_pr and tree.pr_unavailable:
        raise CommandError("GitHub PR status is unavailable; refresh before creating a PR")
    if create_pr:
        if operation:
            operation.stage("Checking PR base branch")
        default_branch = run(
            ["gh", "repo", "view", "--json", "defaultBranchRef", "--jq", ".defaultBranchRef.name"],
            cwd=tree.path, operation=operation,
        ).strip()
        if tree.branch == default_branch:
            raise CommandError("Create a branch worktree in Herdr before publishing a PR")
    if message:
        commit_all(tree.path, message, operation)
    elif has_changes(tree.path, operation):
        raise CommandError("A commit message is required for uncommitted changes")
    if tree.pr and tree.pr.get("state") == "OPEN":
        push_to_pr(PullRequest(tree.path, tree.pr, tree.path), operation)
    else:
        push(tree.path, tree.branch, operation)
    if create_pr:
        if operation:
            operation.stage("Opening pull request")
        url = run(["gh", "pr", "create", "--fill", "--head", tree.branch], cwd=tree.path,
                  timeout=120, operation=operation).strip()
        return url
    return "Changes pushed"


def validate_new_branch(repo, branch, operation=None):
    branch = branch.strip()
    if not branch:
        raise CommandError("A branch name is required")
    try:
        run(["git", "check-ref-format", "--branch", branch], cwd=repo, operation=operation)
    except CommandError as error:
        raise CommandError(f"Invalid branch name: {branch}") from error
    refs = run(["git", "for-each-ref", "--format=%(refname:short)",
                "refs/heads", "refs/remotes/origin"], cwd=repo, operation=operation).splitlines()
    if branch in refs or f"origin/{branch}" in refs:
        raise CommandError(f"Branch already exists: {branch}")
    return branch


def publish_from_main(tree, branch_name, message, operation=None):
    repo = tree.path
    if tree.unavailable or tree.branch == "(detached)":
        raise CommandError("Open shipr from an available default-branch worktree")
    current_branch = run(["git", "branch", "--show-current"], cwd=repo,
                         operation=operation).strip()
    default_branch = run(["gh", "repo", "view", "--json", "defaultBranchRef", "--jq",
                          ".defaultBranchRef.name"], cwd=repo, operation=operation).strip()
    if current_branch != tree.branch or current_branch != default_branch:
        raise CommandError("The default branch changed; refresh shipr before publishing")
    branch = validate_new_branch(repo, branch_name, operation)
    if not message or not has_changes(repo, operation):
        raise CommandError("Uncommitted changes and a commit message are required")
    if operation:
        operation.stage(f"Creating branch {branch} in this worktree")
    run(["git", "switch", "-c", branch], cwd=repo, operation=operation)
    try:
        return publish(Worktree(repo, branch), message, True, operation)
    except Exception as error:
        raise CommandError(f"{error}; still on branch {branch} in {repo}") from error


def update_pr(row, message, operation=None):
    if row.worktree is None:
        raise CommandError("Open this PR in a Herdr worktree before pushing")
    branch = run(["git", "branch", "--show-current"], cwd=row.worktree,
                 operation=operation).strip()
    if matching_pr([row.pr], branch) is None:
        raise CommandError("This worktree changed branches; refresh shipr before pushing")
    if message:
        commit_all(row.worktree, message, operation)
    elif has_changes(row.worktree, operation):
        raise CommandError("A commit message is required for uncommitted changes")
    push_to_pr(row, operation)
    return f"PR #{row.pr['number']} pushed"


def clean(value):
    return "".join(ch if ch.isprintable() else " " for ch in ANSI_ESCAPE.sub("", str(value)))
