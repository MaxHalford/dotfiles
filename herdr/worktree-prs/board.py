"""Curses worktree and pull request board for a Herdr terminal popup."""

import curses
import json
import os
import queue
import subprocess
import sys
import threading
import time
import traceback
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
    dirty: bool = False
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
        label += " / checks complete"
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
    window.timeout(-1)
    try:
        curses.curs_set(1)
        while True:
            draw_line(window, height - 1, label + "".join(value), width)
            window.move(height - 1, min(len(label) + len(value), width - 2))
            window.refresh()
            key = window.get_wch()
            if key in ("\n", "\r", curses.KEY_ENTER):
                return "".join(value).strip()
            if key == "\x1b":
                return None
            if key in ("\b", "\x7f", curses.KEY_BACKSPACE):
                if value:
                    value.pop()
            elif isinstance(key, str) and key.isprintable() and len(label) + len(value) < width - 2:
                value.append(key)
    finally:
        curses.curs_set(0)
        window.timeout(100)


def confirm(window, label):
    return prompt(window, label + " [y/N] ").lower() == "y"


def main(window):
    curses.curs_set(0)
    curses.set_escdelay(25)
    init_colors()
    window.keypad(True)
    window.timeout(100)
    repo = repository_directory()
    trees = []
    error = ""
    selected = 0
    offset = 0
    refreshed = 0.0
    message = "Loading worktrees and pull requests..."
    updates = queue.Queue(maxsize=1)
    refreshing = False

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
        try:
            result, refresh_error = updates.get_nowait()
        except queue.Empty:
            pass
        else:
            refreshing = False
            refreshed = time.monotonic()
            if refresh_error:
                message = f"Refresh failed: {refresh_error}"
            else:
                chosen = str(trees[selected].path) if trees else ""
                trees, error = result
                selected = next((i for i, tree in enumerate(trees) if str(tree.path) == chosen), 0)
                message = error or f"Updated {time.strftime('%H:%M:%S')}"
        if time.monotonic() - refreshed >= REFRESH_SECONDS:
            start_refresh()
        height, width = window.getmaxyx()
        visible = max(1, height - 5)
        selected = min(selected, max(0, len(trees) - 1))
        offset = max(0, min(offset, selected))
        if selected >= offset + visible:
            offset = selected - visible + 1
        window.erase()
        loading = "  refreshing..." if refreshing else ""
        draw_line(window, 0, f"Worktree PRs  {repo.name}  (every {REFRESH_SECONDS}s){loading}", width, curses.A_BOLD)
        branch_width = max(12, (width - 36) // 3)
        path_width = max(12, (width - 36) // 3)
        draw_line(window, 1, f"{'WORKTREE':<{path_width}} {'BRANCH':<{branch_width}} {'LOCAL':<9} PR STATUS", width, curses.A_UNDERLINE)
        for row, tree in enumerate(trees[offset:offset + visible], start=2):
            local = "unavailable" if tree.unavailable else ("dirty" if tree.dirty else "clean")
            status = "Unavailable" if tree.unavailable else ("PR unavailable" if tree.pr_unavailable else pr_status(tree.pr))
            prefix = f"{tree.path.name:<{path_width}.{path_width}} {tree.branch:<{branch_width}.{branch_width}} {local:<9.9} "
            selected_style = curses.A_REVERSE if row - 2 + offset == selected else 0
            draw_line(window, row, prefix + status, width, selected_style)
            if len(prefix) < width - 1:
                window.addnstr(row, len(prefix), clean(status), width - len(prefix) - 1,
                               selected_style | status_style(tree))
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
        elif key == ord("r"):
            start_refresh()
            message = "Refreshing..."
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
                start_refresh()
            except CommandError as exc:
                message = f"Failed: {exc}"


if __name__ == "__main__":
    try:
        curses.wrapper(main)
    except Exception as error:
        state = os.environ.get("HERDR_PLUGIN_STATE_DIR")
        if state:
            Path(state).mkdir(parents=True, exist_ok=True)
            (Path(state) / "board-error.log").write_text(traceback.format_exc())
        print(f"Worktree PRs: {error}")
        if sys.stdin.isatty():
            input("Press Enter to close...")
