"""Curses worktree and pull request board for a Herdr terminal popup."""

import curses
import json
import os
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


REFRESH_SECONDS = 30
PR_FIELDS = "number,title,url,state,isDraft,headRefName,statusCheckRollup,reviewDecision"


class CommandError(Exception):
    pass


def run(argv, cwd=None, timeout=45):
    env = os.environ.copy()
    env["GIT_TERMINAL_PROMPT"] = "0"
    env["GH_PROMPT_DISABLED"] = "1"
    try:
        result = subprocess.run(
            argv, cwd=cwd, env=env, capture_output=True, text=True, timeout=timeout, check=False
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        raise CommandError(str(error)) from error
    if result.returncode:
        raise CommandError((result.stderr or result.stdout).strip() or f"Command failed: {argv[0]}")
    return result.stdout


def repository_directory():
    context = json.loads(os.environ.get("HERDR_PLUGIN_CONTEXT_JSON", "{}"))
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
    dirty: bool = False
    ahead: int = 0
    pr: Optional[dict] = None
    pr_unavailable: bool = False


def parse_worktrees(raw):
    trees = []
    for record in raw.split("\0\0"):
        fields = record.strip("\0").split("\0")
        if not fields or not fields[0].startswith("worktree "):
            continue
        path = Path(fields[0][9:])
        branch = next((field[7:] for field in fields if field.startswith("branch ")), "(detached)")
        if branch.startswith("refs/heads/"):
            branch = branch[len("refs/heads/"):]
        unavailable = any(field.startswith("prunable ") for field in fields) or not path.is_dir()
        trees.append(Worktree(path, branch, unavailable))
    return trees


def matching_pr(prs, branch):
    matches = [pr for pr in prs if pr.get("headRefName") == branch]
    return next((pr for pr in matches if pr.get("state") == "OPEN"), matches[0] if matches else None)


def pr_status(pr):
    if not pr:
        return "No PR"
    state = pr.get("state", "UNKNOWN")
    if state != "OPEN":
        return state.title()
    label = "Draft" if pr.get("isDraft") else "Open"
    checks = pr.get("statusCheckRollup") or []
    failed = sum(check.get("conclusion") in ("FAILURE", "TIMED_OUT", "CANCELLED", "ACTION_REQUIRED") or check.get("state") in ("FAILURE", "ERROR") for check in checks)
    pending = sum(check.get("status") in ("IN_PROGRESS", "QUEUED", "PENDING") or check.get("state") in ("PENDING", "EXPECTED") for check in checks)
    if failed:
        label += f" / {failed} failing"
    elif pending:
        label += f" / {pending} pending"
    elif checks:
        label += " / checks passed"
    review = pr.get("reviewDecision")
    if review == "CHANGES_REQUESTED":
        label += " / changes requested"
    elif review == "REVIEW_REQUIRED":
        label += " / review needed"
    return label


def load_board(repo):
    raw = run(["git", "worktree", "list", "--porcelain", "-z"], cwd=repo)
    trees = parse_worktrees(raw)
    error = ""
    try:
        prs = json.loads(run(["gh", "pr", "list", "--state", "all", "--limit", "500", "--json", PR_FIELDS], cwd=repo))
    except (CommandError, ValueError) as exc:
        prs = []
        error = f"GitHub refresh failed: {exc}"
    for tree in trees:
        if tree.unavailable:
            continue
        tree.pr_unavailable = bool(error)
        try:
            tree.dirty = bool(run(["git", "status", "--porcelain"], cwd=tree.path))
        except CommandError:
            tree.unavailable = True
            continue
        try:
            tree.ahead = int(run(["git", "rev-list", "--count", "@{upstream}..HEAD"], cwd=tree.path).strip())
        except (CommandError, ValueError):
            tree.ahead = 0
        tree.pr = matching_pr(prs, tree.branch)
    return trees, error


def has_changes(path):
    return bool(run(["git", "status", "--porcelain"], cwd=path))


def commit_all(path, message):
    if not has_changes(path):
        return False
    run(["git", "add", "-A"], cwd=path)
    run(["git", "commit", "-m", message], cwd=path, timeout=120)
    return True


def push(path, branch):
    try:
        run(["git", "rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{upstream}"], cwd=path)
    except CommandError:
        run(["git", "push", "-u", "origin", branch], cwd=path, timeout=120)
    else:
        run(["git", "push"], cwd=path, timeout=120)


def publish(tree, message, create_pr):
    if tree.unavailable or tree.branch == "(detached)":
        raise CommandError("This worktree has no usable branch")
    if create_pr and tree.pr and tree.pr.get("state") == "OPEN":
        raise CommandError("This branch already has an open pull request")
    if create_pr and tree.pr_unavailable:
        raise CommandError("GitHub PR status is unavailable; refresh before creating a PR")
    if create_pr:
        default_branch = run(
            ["gh", "repo", "view", "--json", "defaultBranchRef", "--jq", ".defaultBranchRef.name"],
            cwd=tree.path,
        ).strip()
        if tree.branch == default_branch:
            raise CommandError("The repository's default branch cannot open a PR against itself")
    if message:
        commit_all(tree.path, message)
    elif has_changes(tree.path):
        raise CommandError("A commit message is required for uncommitted changes")
    push(tree.path, tree.branch)
    if create_pr:
        return run(["gh", "pr", "create", "--fill", "--head", tree.branch], cwd=tree.path, timeout=120).strip()
    return "Changes pushed"


def clean(value):
    return "".join(ch if ch.isprintable() else " " for ch in str(value))


def draw_line(window, row, text, width, style=0):
    if row < 0 or row >= window.getmaxyx()[0]:
        return
    window.addnstr(row, 0, clean(text).ljust(max(0, width - 1)), max(0, width - 1), style)


def prompt(window, label):
    height, width = window.getmaxyx()
    draw_line(window, height - 1, label, width)
    window.move(height - 1, min(len(label), width - 2))
    curses.echo()
    window.timeout(-1)
    try:
        value = window.getstr(height - 1, min(len(label), width - 2), max(1, width - len(label) - 2))
    finally:
        curses.noecho()
        window.timeout(500)
    return value.decode("utf-8", "replace").strip()


def confirm(window, label):
    return prompt(window, label + " [y/N] ").lower() == "y"


def main(window):
    curses.curs_set(0)
    window.keypad(True)
    window.timeout(500)
    repo = repository_directory()
    trees, error = load_board(repo)
    selected = 0
    offset = 0
    refreshed = time.monotonic()
    message = error
    while True:
        height, width = window.getmaxyx()
        visible = max(1, height - 5)
        selected = min(selected, max(0, len(trees) - 1))
        offset = max(0, min(offset, selected))
        if selected >= offset + visible:
            offset = selected - visible + 1
        window.erase()
        draw_line(window, 0, f"Worktree PRs  {repo.name}  (refresh every {REFRESH_SECONDS}s)", width, curses.A_BOLD)
        branch_width = max(12, (width - 36) // 3)
        path_width = max(12, (width - 36) // 3)
        draw_line(window, 1, f"{'WORKTREE':<{path_width}} {'BRANCH':<{branch_width}} {'LOCAL':<9} PR STATUS", width, curses.A_UNDERLINE)
        for row, tree in enumerate(trees[offset:offset + visible], start=2):
            local = "unavailable" if tree.unavailable else ("dirty" if tree.dirty else (f"ahead {tree.ahead}" if tree.ahead else "clean"))
            status = "Unavailable" if tree.unavailable else ("PR unavailable" if tree.pr_unavailable else pr_status(tree.pr))
            line = f"{tree.path.name:<{path_width}.{path_width}} {tree.branch:<{branch_width}.{branch_width}} {local:<9.9} {status}"
            draw_line(window, row, line, width, curses.A_REVERSE if row - 2 + offset == selected else 0)
        draw_line(window, height - 3, "Up/Down select  c commit + create PR  p commit + push  r refresh  q/Esc close", width)
        detail = str(trees[selected].path) if trees else "No worktrees found"
        draw_line(window, height - 2, detail, width)
        draw_line(window, height - 1, message or error, width)
        window.refresh()
        key = window.getch()
        if key in (ord("q"), 27):
            return
        if key in (curses.KEY_DOWN, ord("j")):
            selected = min(selected + 1, len(trees) - 1)
        elif key in (curses.KEY_UP, ord("k")):
            selected = max(0, selected - 1)
        elif key in (ord("r"),) or time.monotonic() - refreshed >= REFRESH_SECONDS:
            chosen = str(trees[selected].path) if trees else ""
            trees, error = load_board(repo)
            selected = next((i for i, tree in enumerate(trees) if str(tree.path) == chosen), 0)
            refreshed = time.monotonic()
            message = error or "Updated"
        elif key in (ord("c"), ord("p")) and trees:
            tree = trees[selected]
            create_pr = key == ord("c")
            if tree.unavailable or tree.branch == "(detached)":
                message = "Select an available worktree with a branch"
                continue
            if create_pr and tree.pr and tree.pr.get("state") == "OPEN":
                message = "This branch already has an open PR"
                continue
            if create_pr and tree.pr_unavailable:
                message = "GitHub status is unavailable; refresh before creating a PR"
                continue
            verb = "create a PR" if create_pr else "push"
            if not confirm(window, f"{verb} for {tree.branch}?"):
                message = "Cancelled"
                continue
            try:
                commit_message = prompt(window, "Commit message: ") if has_changes(tree.path) else ""
                if has_changes(tree.path) and not commit_message:
                    message = "Cancelled: commit message required"
                    continue
                message = publish(tree, commit_message, create_pr)
                trees, error = load_board(repo)
                refreshed = time.monotonic()
            except CommandError as exc:
                message = f"Failed: {exc}"


if __name__ == "__main__":
    try:
        curses.wrapper(main)
    except (CommandError, ValueError, KeyError) as error:
        print(f"Worktree PRs: {error}")
        input("Press Enter to close...")
