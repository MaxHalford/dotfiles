"""Curses worktree and pull request board for a Herdr terminal popup."""

import curses
import json
import os
import queue
import re
import signal
import subprocess
import sys
import threading
import time
import traceback
from collections import deque
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


REFRESH_SECONDS = 30
PR_FIELDS = "number,title,url,state,isDraft,headRefName,statusCheckRollup,reviewDecision"
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


def repository_directory():
    context = json.loads(os.environ.get("HERDR_PLUGIN_CONTEXT_JSON", "{}"))
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
    last_commit: int = 0
    unique_commits: int = 0
    current: bool = False
    is_base: bool = False
    relevant: bool = False
    pr: Optional[dict] = None
    pr_unavailable: bool = False


@dataclass
class ContextMenu:
    tree: Worktree
    x: int
    y: int
    width: int
    actions: list


def context_actions(tree):
    if tree.unavailable or tree.branch == "(detached)":
        return []
    actions = []
    if not tree.pr_unavailable and not (tree.pr and tree.pr.get("state") == "OPEN"):
        if tree.is_base:
            label = "Commit & create branch/PR" if tree.dirty else "Create branch/PR"
        else:
            label = "Commit & create PR" if tree.dirty else "Create PR"
        actions.append((label, "create_pr"))
    actions.append(("Commit & push" if tree.dirty else "Push", "push"))
    return actions


def context_menu(tree, x, y, width, height):
    actions = context_actions(tree)
    if not actions or width < 8 or height < len(actions) + 2:
        return None
    menu_width = min(max(len(label) for label, _ in actions) + 4, width - 1)
    return ContextMenu(tree, max(0, min(x, width - menu_width - 1)),
                       max(0, min(y, height - len(actions) - 2)), menu_width, actions)


def menu_choice(menu, x, y):
    index = y - menu.y - 1
    if menu.x <= x < menu.x + menu.width and 0 <= index < len(menu.actions):
        return menu.actions[index]
    return None


def draw_context_menu(window, menu):
    width = menu.width
    window.addnstr(menu.y, menu.x, "┌" + "─" * (width - 2) + "┐", width, curses.A_BOLD)
    for index, (label, _) in enumerate(menu.actions, start=1):
        window.addnstr(menu.y + index, menu.x, ("│ " + label).ljust(width - 1) + "│",
                       width, curses.A_REVERSE)
    window.addnstr(menu.y + len(menu.actions) + 1, menu.x,
                   "└" + "─" * (width - 2) + "┘", width, curses.A_BOLD)


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
        label += " / checks complete"
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


def age_label(timestamp, now=None):
    if not timestamp:
        return "-"
    seconds = max(0, int((time.time() if now is None else now) - timestamp))
    if seconds < 60:
        return "just now"
    if seconds < 3600:
        return f"{seconds // 60}m ago"
    if seconds < 86400:
        return f"{seconds // 3600}h ago"
    if seconds < 604800:
        return f"{seconds // 86400}d ago"
    if seconds < 2592000:
        return f"{seconds // 604800}w ago"
    if seconds < 31536000:
        return f"{seconds // 2592000}mo ago"
    return f"{seconds // 31536000}y ago"


def visible_worktrees(trees, show_all=False):
    return [tree for tree in trees if show_all or tree.relevant]


def local_status(tree):
    if tree.unavailable:
        return "unavailable"
    if tree.dirty:
        return "dirty"
    if tree.unique_commits:
        suffix = "commit" if tree.unique_commits == 1 else "commits"
        return f"+{tree.unique_commits} {suffix}"
    return "clean"


def load_board(repo):
    raw = run(["git", "worktree", "list", "--porcelain", "-z"], cwd=repo)
    trees = parse_worktrees(raw)
    base = default_base(repo, trees)
    commit_times = {}
    unique_counts = {}
    error = ""
    try:
        prs = json.loads(run(["gh", "pr", "list", "--state", "all", "--limit", "500", "--json", PR_FIELDS], cwd=repo))
    except (CommandError, ValueError) as exc:
        prs = []
        error = f"GitHub refresh failed: {exc}"
    for tree in trees:
        if tree.unavailable:
            continue
        tree.is_base = bool(base and tree.branch == (base[7:] if base.startswith("origin/") else base))
        tree.pr_unavailable = bool(error)
        try:
            tree.dirty = bool(run(["git", "status", "--porcelain"], cwd=tree.path))
        except CommandError:
            tree.unavailable = True
            continue
        if tree.head:
            if tree.head not in commit_times:
                try:
                    commit_times[tree.head] = int(run(["git", "show", "-s", "--format=%ct", tree.head],
                                                      cwd=repo).strip())
                except (CommandError, ValueError):
                    commit_times[tree.head] = 0
            tree.last_commit = commit_times[tree.head]
            if base and tree.branch != base:
                if tree.head not in unique_counts:
                    try:
                        unique_counts[tree.head] = int(run(["git", "rev-list", "--count",
                                                           f"{base}..{tree.head}"], cwd=repo).strip())
                    except (CommandError, ValueError):
                        unique_counts[tree.head] = 0
                tree.unique_commits = unique_counts[tree.head]
        tree.pr = matching_pr(prs, tree.branch)
        tree.current = tree.path.resolve() == repo.resolve()
        tree.relevant = tree.current or tree.dirty or tree.unique_commits > 0 or bool(
            tree.pr and tree.pr.get("state") == "OPEN"
        )
        if base is None and tree.branch != "(detached)":
            tree.relevant = True
    trees.sort(key=lambda tree: (not tree.current, -tree.last_commit, tree.path.name))
    return trees, error


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
        run(["git", "push", "-u", "origin", branch], cwd=path, timeout=120, operation=operation)
    else:
        run(["git", "push"], cwd=path, timeout=120, operation=operation)


def validate_new_branch(path, branch, operation=None):
    branch = branch.strip()
    if not branch:
        raise CommandError("A branch name is required")
    try:
        run(["git", "check-ref-format", "--branch", branch], cwd=path, operation=operation)
    except CommandError as error:
        raise CommandError(f"Invalid branch name: {branch}") from error
    refs = run(["git", "for-each-ref", "--format=%(refname:short)",
                "refs/heads", "refs/remotes/origin"], cwd=path, operation=operation).splitlines()
    taken = set(refs)
    if branch in taken or f"origin/{branch}" in taken:
        raise CommandError(f"Branch already exists: {branch}")
    return branch


def publish(tree, message, create_pr, operation=None, branch_name=None):
    if tree.unavailable or tree.branch == "(detached)":
        raise CommandError("This worktree has no usable branch")
    if create_pr and tree.pr and tree.pr.get("state") == "OPEN":
        raise CommandError("This branch already has an open pull request")
    if create_pr and tree.pr_unavailable:
        raise CommandError("GitHub PR status is unavailable; refresh before creating a PR")
    branch = tree.branch
    if create_pr:
        if operation:
            operation.stage("Checking PR base branch")
        default_branch = run(
            ["gh", "repo", "view", "--json", "defaultBranchRef", "--jq", ".defaultBranchRef.name"],
            cwd=tree.path, operation=operation,
        ).strip()
        if branch == default_branch:
            if not message or not has_changes(tree.path, operation):
                raise CommandError("The default branch needs uncommitted changes to create a PR")
            branch = validate_new_branch(tree.path, branch_name or "", operation)
            if operation:
                operation.stage(f"Creating branch {branch}")
            run(["git", "switch", "-c", branch], cwd=tree.path, operation=operation)
        elif branch_name:
            raise CommandError("This worktree is no longer on the default branch; refresh and retry")
    if message:
        commit_all(tree.path, message, operation)
    elif has_changes(tree.path, operation):
        raise CommandError("A commit message is required for uncommitted changes")
    push(tree.path, branch, operation)
    if create_pr:
        if operation:
            operation.stage("Opening pull request")
        return run(["gh", "pr", "create", "--fill", "--head", branch], cwd=tree.path,
                   timeout=120, operation=operation).strip()
    return "Changes pushed"


def clean(value):
    return "".join(ch if ch.isprintable() else " " for ch in ANSI_ESCAPE.sub("", str(value)))


def draw_line(window, row, text, width, style=0):
    if row < 0 or row >= window.getmaxyx()[0]:
        return
    window.addnstr(row, 0, clean(text).ljust(max(0, width - 1)), max(0, width - 1), style)


def feedback_style(message):
    if message.startswith("✓"):
        return curses.color_pair(1) | curses.A_BOLD
    if message.startswith("✗"):
        return curses.color_pair(3) | curses.A_BOLD
    if message.startswith("!"):
        return curses.color_pair(2)
    if message.startswith("○"):
        return curses.A_DIM
    return 0


def status_style(tree):
    if tree.unavailable or tree.pr_unavailable or not tree.pr:
        return curses.A_DIM
    pr = tree.pr
    if pr.get("state") == "MERGED":
        return curses.color_pair(4)
    if pr.get("state") != "OPEN":
        return curses.A_DIM
    checks = pr.get("statusCheckRollup") or []
    if pr.get("reviewDecision") == "CHANGES_REQUESTED" or any(
        check.get("conclusion") in ("FAILURE", "TIMED_OUT", "CANCELLED", "ACTION_REQUIRED")
        or check.get("state") in ("FAILURE", "ERROR") for check in checks
    ):
        return curses.color_pair(3)
    if pr.get("isDraft"):
        return curses.color_pair(5)
    if "pending" in pr_status(pr) or pr.get("reviewDecision") == "REVIEW_REQUIRED":
        return curses.color_pair(2)
    return curses.color_pair(1)


def init_colors():
    if not curses.has_colors():
        return
    curses.start_color()
    try:
        curses.use_default_colors()
    except curses.error:
        background = curses.COLOR_BLACK
    else:
        background = -1
    for pair, color in ((1, curses.COLOR_GREEN), (2, curses.COLOR_YELLOW),
                        (3, curses.COLOR_RED), (4, curses.COLOR_BLUE),
                        (5, curses.COLOR_MAGENTA)):
        curses.init_pair(pair, color, background)


def prompt(window, label):
    height, width = window.getmaxyx()
    value = []
    cursor = 0
    window.timeout(-1)
    try:
        curses.curs_set(1)
        while True:
            draw_line(window, height - 1, label + "".join(value), width)
            window.move(height - 1, min(len(label) + cursor, width - 2))
            window.refresh()
            key = window.get_wch()
            if key in ("\n", "\r", curses.KEY_ENTER):
                return "".join(value).strip()
            if key == "\x1b":
                window.timeout(40)
                try:
                    following = window.get_wch()
                except curses.error:
                    return None
                finally:
                    window.timeout(-1)
                if following in ("\b", "\x7f", curses.KEY_BACKSPACE):
                    key = "\x17"
                else:
                    return None
            if key in ("\b", "\x7f", curses.KEY_BACKSPACE):
                if cursor:
                    del value[cursor - 1]
                    cursor -= 1
            elif key == curses.KEY_DC:
                if cursor < len(value):
                    del value[cursor]
            elif key == "\x17":
                while cursor and value[cursor - 1].isspace():
                    del value[cursor - 1]
                    cursor -= 1
                while cursor and not value[cursor - 1].isspace():
                    del value[cursor - 1]
                    cursor -= 1
            elif key == "\x15":
                value.clear()
                cursor = 0
            elif key == curses.KEY_LEFT:
                cursor = max(0, cursor - 1)
            elif key == curses.KEY_RIGHT:
                cursor = min(len(value), cursor + 1)
            elif key == curses.KEY_HOME or key == "\x01":
                cursor = 0
            elif key == curses.KEY_END or key == "\x05":
                cursor = len(value)
            elif isinstance(key, str) and key.isprintable() and len(label) + len(value) < width - 2:
                value.insert(cursor, key)
                cursor += 1
    finally:
        curses.curs_set(0)
        window.timeout(100)


def confirm(window, label):
    answer = prompt(window, label + " [Y/n] ")
    return answer is not None and answer.lower() in ("", "y", "yes")


def main(window):
    curses.curs_set(0)
    curses.set_escdelay(25)
    curses.mouseinterval(0)
    curses.mousemask(curses.BUTTON1_PRESSED | curses.BUTTON1_CLICKED |
                     curses.BUTTON3_PRESSED | curses.BUTTON3_CLICKED)
    init_colors()
    window.keypad(True)
    window.timeout(100)
    repo = repository_directory()
    all_trees = []
    trees = []
    show_all = False
    error = ""
    selected = 0
    offset = 0
    refreshed = 0.0
    message = "Loading worktrees and pull requests..."
    updates = queue.Queue(maxsize=1)
    action_events = queue.Queue(maxsize=128)
    refreshing = False
    active_action = None
    action_stage = ""
    action_line = ""
    action_started = 0.0
    closing_after_cancel = False
    message_persistent = False
    menu = None

    def start_refresh():
        nonlocal refreshing
        if refreshing:
            return
        refreshing = True

        def worker():
            try:
                updates.put((load_board(repo), None))
            except Exception as exc:
                updates.put((None, str(exc)))

        threading.Thread(target=worker, daemon=True).start()

    start_refresh()
    while True:
        for _ in range(128):
            try:
                kind, value = action_events.get_nowait()
            except queue.Empty:
                break
            if kind == "stage":
                action_stage = value
                action_line = ""
            elif kind == "line":
                action_line = value
            elif kind == "done":
                active_action = None
                message = value
                message_persistent = True
                action_stage = ""
                action_line = ""
                if closing_after_cancel:
                    return
                start_refresh()
        try:
            result, refresh_error = updates.get_nowait()
        except queue.Empty:
            pass
        else:
            refreshing = False
            refreshed = time.monotonic()
            if refresh_error:
                if active_action is None and not message_persistent:
                    message = f"✗ Refresh failed: {refresh_error}"
            else:
                chosen = str(trees[selected].path) if trees else ""
                all_trees, error = result
                trees = visible_worktrees(all_trees, show_all)
                menu = None
                selected = next((i for i, tree in enumerate(trees) if str(tree.path) == chosen), 0)
                if active_action is None and not message_persistent:
                    message = f"✗ {error}" if error else f"Updated {time.strftime('%H:%M:%S')}"
        if active_action is None and time.monotonic() - refreshed >= REFRESH_SECONDS:
            start_refresh()
        height, width = window.getmaxyx()
        visible = max(1, height - 5)
        selected = max(0, min(selected, len(trees) - 1))
        offset = max(0, min(offset, selected))
        if selected >= offset + visible:
            offset = selected - visible + 1
        window.erase()
        loading = "  refreshing..." if refreshing else ""
        mode = "all" if show_all else "relevant"
        draw_line(window, 0, f"shipr  •  {repo.name}  •  {len(trees)}/{len(all_trees)} {mode}  "
                  f"({REFRESH_SECONDS}s refresh){loading}",
                  width, curses.A_BOLD)
        age_width = 11
        branch_width = max(12, (width - 51) // 3)
        path_width = max(12, (width - 51) // 3)
        draw_line(window, 1, f"{'LAST COMMIT':<{age_width}} {'WORKTREE':<{path_width}} "
                  f"{'BRANCH':<{branch_width}} {'CHANGES':<10} PR STATUS", width, curses.A_UNDERLINE)
        for row, tree in enumerate(trees[offset:offset + visible], start=2):
            local = local_status(tree)
            status = "Unavailable" if tree.unavailable else ("PR unavailable" if tree.pr_unavailable else pr_status(tree.pr))
            age = age_label(tree.last_commit)
            prefix = f"{age:<{age_width}.{age_width}} {tree.path.name:<{path_width}.{path_width}} "
            prefix += f"{tree.branch:<{branch_width}.{branch_width}} {local:<10.10} "
            selected_style = curses.A_REVERSE if row - 2 + offset == selected else 0
            draw_line(window, row, prefix + status, width, selected_style)
            if len(prefix) < width - 1:
                window.addnstr(row, len(prefix), clean(status), width - len(prefix) - 1,
                               selected_style | status_style(tree))
        if active_action is None:
            toggle = "a relevant" if show_all else "a all"
            draw_line(window, height - 3,
                      f"↑↓ select  right-click actions  r refresh  {toggle}  q close", width)
            detail = f"{selected + 1}/{len(trees)}  {trees[selected].path}" if trees else "No worktrees found"
            draw_line(window, height - 2, detail, width)
            draw_line(window, height - 1, message or error, width, feedback_style(message or error))
        else:
            elapsed = int(time.monotonic() - action_started)
            spinner = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"[int((time.monotonic() - action_started) * 10) % 10]
            draw_line(window, height - 3, "q cancel and close after the current command stops", width)
            draw_line(window, height - 2, f"{spinner} {action_stage or 'Starting'}  {elapsed // 60:02d}:{elapsed % 60:02d}",
                      width, curses.A_BOLD)
            draw_line(window, height - 1, action_line or "Waiting for command output...", width)
        if menu is not None:
            draw_context_menu(window, menu)
        window.refresh()
        key = window.getch()
        if active_action is not None:
            if key == ord("q"):
                if not closing_after_cancel:
                    closing_after_cancel = True
                    active_action.cancel()
                    action_stage = "Cancelling"
            continue
        if key == ord("q"):
            return
        action = None
        if key == curses.KEY_MOUSE:
            try:
                _, x, y, _, buttons = curses.getmouse()
            except curses.error:
                continue
            row_index = offset + y - 2
            on_row = 2 <= y < 2 + visible and 0 <= row_index < len(trees)
            if buttons & (curses.BUTTON3_PRESSED | curses.BUTTON3_CLICKED):
                if on_row:
                    selected = row_index
                    menu = context_menu(trees[selected], x, y, width, height)
                    if menu is None:
                        message = "! This worktree has no available actions"
                else:
                    menu = None
                continue
            if buttons & (curses.BUTTON1_PRESSED | curses.BUTTON1_CLICKED):
                if menu is not None:
                    action = menu_choice(menu, x, y)
                    menu = None
                if action is None:
                    if on_row:
                        selected = row_index
                    elif 2 <= y < height - 3:
                        return
                    continue
            else:
                continue
        if key in (curses.KEY_DOWN, ord("j")):
            menu = None
            selected = min(selected + 1, max(0, len(trees) - 1))
        elif key in (curses.KEY_UP, ord("k")):
            menu = None
            selected = max(0, selected - 1)
        elif key == ord("r"):
            menu = None
            start_refresh()
            message_persistent = False
            message = "Refreshing..."
        elif key == ord("a"):
            menu = None
            chosen = str(trees[selected].path) if trees else ""
            show_all = not show_all
            trees = visible_worktrees(all_trees, show_all)
            selected = next((i for i, tree in enumerate(trees) if str(tree.path) == chosen), 0)
            message = "Showing all registered worktrees" if show_all else "Showing relevant worktrees"
            message_persistent = False
        elif action is not None:
            _, action_id = action
            tree = trees[selected]
            create_pr = action_id == "create_pr"
            if tree.unavailable or tree.branch == "(detached)":
                message = "! Select an available worktree with a branch"
                continue
            if create_pr and tree.pr and tree.pr.get("state") == "OPEN":
                message = "! This branch already has an open PR"
                continue
            if create_pr and tree.pr_unavailable:
                message = "! GitHub status is unavailable; refresh before creating a PR"
                continue
            if create_pr:
                verb = "create a branch and PR" if tree.is_base else "create a PR"
            else:
                verb = "push"
            if not confirm(window, f"{verb} for {tree.branch}?"):
                message = "○ Cancelled"
                continue
            try:
                dirty_now = has_changes(tree.path)
            except CommandError as exc:
                message = f"✗ {exc}"
                continue
            if create_pr and tree.is_base and not dirty_now:
                message = "! The default branch needs changes to create a PR"
                continue
            branch_name = None
            if create_pr and tree.is_base:
                branch_name = prompt(window, "New branch name: ")
                if not branch_name:
                    message = "○ Cancelled: branch name required"
                    continue
            commit_message = prompt(window, "Commit message: ") if dirty_now else ""
            if dirty_now and not commit_message:
                message = "○ Cancelled: commit message required"
                continue
            active_action = Operation(action_events)
            message_persistent = False
            action_started = time.monotonic()
            action_stage = "Starting"
            action_line = ""

            def worker(chosen_tree=tree, chosen_message=commit_message, should_create=create_pr,
                       chosen_branch=branch_name, operation=active_action):
                try:
                    result = publish(chosen_tree, chosen_message, should_create, operation,
                                     branch_name=chosen_branch)
                except Exception as exc:
                    summary = str(exc).splitlines()[-1] if str(exc) else type(exc).__name__
                    action_events.put(("done", f"✗ {summary}"))
                else:
                    summary = f"PR created: {result}" if should_create else result
                    action_events.put(("done", f"✓ {summary}"))

            threading.Thread(target=worker, daemon=True).start()


if __name__ == "__main__":
    try:
        curses.wrapper(main)
    except Exception as error:
        state = os.environ.get("HERDR_PLUGIN_STATE_DIR")
        if state:
            Path(state).mkdir(parents=True, exist_ok=True)
            (Path(state) / "board-error.log").write_text(traceback.format_exc())
        print(f"shipr: {error}")
        if sys.stdin.isatty():
            input("Press Enter to close...")
