"""Curses pull request board for a Herdr terminal popup."""

import curses
import os
import queue
import re
import sys
import threading
import time
import traceback
from dataclasses import dataclass
from pathlib import Path

from shipr_core import (
    CommandError, Operation, PullRequest, checkout_pr, clean, has_changes, load_board,
    open_herdr_worktree, open_pr, pr_status, publish, publish_from_main, repository_directory,
    run, update_pr,
)


REFRESH_SECONDS = 30


@dataclass
class ContextMenu:
    tree: PullRequest
    x: int
    y: int
    width: int
    actions: list


def context_actions(tree):
    actions = [("Open PR in GitHub", "open_pr")]
    if tree.worktree is None:
        actions.append(("Open in new Herdr worktree", "checkout_pr"))
    else:
        actions.append(("Go to Herdr worktree", "focus_worktree"))
        actions.append(("Commit & push to PR", "update_pr"))
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
    pr = tree.pr
    if pr.get("reviewDecision") == "CHANGES_REQUESTED":
        return curses.color_pair(3)
    if pr.get("isDraft"):
        return curses.color_pair(5)
    if pr.get("reviewDecision") == "REVIEW_REQUIRED":
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


class ShiprApp:
    def __init__(self, window, repo):
        self.window = window
        self.repo = repo
        self.items = []
        self.current_tree = None
        self.error = ""
        self.selected = 0
        self.offset = 0
        self.refreshed = 0.0
        self.message = "Loading pull requests..."
        self.message_persistent = False
        self.menu = None
        self.updates = queue.Queue(maxsize=1)
        self.action_events = queue.Queue(maxsize=128)
        self.refreshing = False
        self.active_action = None
        self.action_stage = ""
        self.action_line = ""
        self.action_started = 0.0
        self.closing_after_cancel = False
        self.created_pr_url = ""
        self.pending_pr_number = None

    @staticmethod
    def item_key(item):
        return item.pr.get("number")

    def selected_item(self):
        return self.items[self.selected] if self.items else None

    def select_key(self, key):
        self.selected = next((i for i, item in enumerate(self.items) if self.item_key(item) == key), 0)

    def start_refresh(self):
        if self.refreshing:
            return
        self.refreshing = True

        def worker():
            try:
                self.updates.put((load_board(self.repo), None))
            except Exception as exc:
                self.updates.put((None, str(exc)))

        threading.Thread(target=worker, daemon=True).start()

    def receive_refresh(self):
        try:
            result, failure = self.updates.get_nowait()
        except queue.Empty:
            return
        self.refreshing = False
        self.refreshed = time.monotonic()
        if failure:
            if self.active_action is None and not self.message_persistent:
                self.message = f"✗ Refresh failed: {failure}"
            return
        selected = self.selected_item()
        key = self.item_key(selected) if selected else None
        self.items, self.current_tree, self.error = result
        self.menu = None
        if self.pending_pr_number and any(item.pr.get("number") == self.pending_pr_number for item in self.items):
            self.select_key(self.pending_pr_number)
            self.pending_pr_number = None
        else:
            self.select_key(key)
        if self.active_action is None and not self.message_persistent:
            self.message = f"✗ {self.error}" if self.error else f"Updated {time.strftime('%H:%M:%S')}"

    def receive_actions(self):
        for _ in range(128):
            try:
                kind, value = self.action_events.get_nowait()
            except queue.Empty:
                return False
            if kind == "stage":
                self.action_stage = value
                self.action_line = ""
            elif kind == "line":
                self.action_line = value
            elif kind == "checked_out":
                return True
            elif kind == "created":
                self.active_action = None
                self.created_pr_url = value
                match = re.search(r"/pull/(\d+)(?:$|[/?#])", value)
                self.pending_pr_number = int(match.group(1)) if match else None
                self.message = "✓ PR created • press o to open it in GitHub"
                self.message_persistent = True
                self.action_stage = ""
                self.action_line = ""
                if self.closing_after_cancel:
                    return True
                self.start_refresh()
            elif kind == "done":
                self.active_action = None
                self.message = value
                self.message_persistent = True
                self.action_stage = ""
                self.action_line = ""
                if self.closing_after_cancel:
                    return True
                self.start_refresh()
        return False

    def draw_row(self, row, item, branch_width, path_width, width):
        selected_style = curses.A_REVERSE if row - 2 + self.offset == self.selected else 0
        local = item.worktree.name if item.worktree else "—"
        prefix = f"#{item.pr['number']:<6} {item.branch:<{branch_width}.{branch_width}} "
        prefix += f"{local:<{path_width}.{path_width}} {pr_status(item.pr):<24.24} "
        status = item.pr.get("title") or "(untitled)"
        draw_line(self.window, row, prefix + status, width, selected_style)
        if len(prefix) < width - 1:
            self.window.addnstr(row, len(prefix), clean(status), width - len(prefix) - 1,
                                selected_style | status_style(item))

    def draw(self):
        window = self.window
        height, width = window.getmaxyx()
        visible = max(1, height - 5)
        self.selected = max(0, min(self.selected, len(self.items) - 1))
        self.offset = max(0, min(self.offset, self.selected))
        if self.selected >= self.offset + visible:
            self.offset = self.selected - visible + 1
        window.erase()
        loading = "  refreshing..." if self.refreshing else ""
        draw_line(window, 0, f"shipr  •  {self.repo.name}  •  {len(self.items)} open PRs  "
                  f"({REFRESH_SECONDS}s refresh){loading}", width, curses.A_BOLD)
        branch_width = max(12, (width - 66) // 3)
        path_width = max(12, (width - 66) // 3)
        header = f"{'PR':<7} {'BRANCH':<{branch_width}} {'WORKTREE':<{path_width}} {'STATUS':<24} TITLE"
        draw_line(window, 1, header, width, curses.A_UNDERLINE)
        for row, item in enumerate(self.items[self.offset:self.offset + visible], start=2):
            self.draw_row(row, item, branch_width, path_width, width)
        if self.active_action is None:
            draw_line(window, height - 3,
                      "↑↓ select  right-click PR  p publish current  u push current  o open PR  r refresh  q close", width)
            item = self.selected_item()
            if self.created_pr_url:
                detail = f"PR URL: {self.created_pr_url}"
            elif item:
                detail = f"PR #{item.pr['number']}  {item.pr.get('title', '')}  {item.worktree or 'not checked out'}"
            else:
                detail = "No open PRs. Press p to publish changes from this worktree."
            draw_line(window, height - 2, detail, width)
            draw_line(window, height - 1, self.message or self.error, width,
                      feedback_style(self.message or self.error))
        else:
            elapsed = int(time.monotonic() - self.action_started)
            spinner = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"[int((time.monotonic() - self.action_started) * 10) % 10]
            draw_line(window, height - 3, "q cancel and close after the current command stops", width)
            draw_line(window, height - 2,
                      f"{spinner} {self.action_stage or 'Starting'}  {elapsed // 60:02d}:{elapsed % 60:02d}",
                      width, curses.A_BOLD)
            draw_line(window, height - 1, self.action_line or "Waiting for command output...", width)
        if self.menu is not None:
            draw_context_menu(window, self.menu)
        window.refresh()

    def handle_mouse(self):
        try:
            _, x, y, _, buttons = curses.getmouse()
        except curses.error:
            return None, False
        height, width = self.window.getmaxyx()
        row_index = self.offset + y - 2
        on_row = 2 <= y < 2 + max(1, height - 5) and 0 <= row_index < len(self.items)
        if buttons & (curses.BUTTON3_PRESSED | curses.BUTTON3_CLICKED):
            self.menu = context_menu(self.items[row_index], x, y, width, height) if on_row else None
            if on_row:
                self.created_pr_url = ""
                self.selected = row_index
                if self.menu is None:
                    self.message = "! This row has no available actions"
            return None, False
        if buttons & (curses.BUTTON1_PRESSED | curses.BUTTON1_CLICKED):
            action = menu_choice(self.menu, x, y) if self.menu is not None else None
            self.menu = None
            if action is not None:
                return action, False
            if on_row:
                self.created_pr_url = ""
                self.selected = row_index
        return None, False

    def start_action(self, work, success):
        self.active_action = Operation(self.action_events)
        self.created_pr_url = ""
        operation = self.active_action
        self.message_persistent = False
        self.action_started = time.monotonic()
        self.action_stage = "Starting"
        self.action_line = ""

        def worker():
            try:
                result = work(operation)
            except Exception as exc:
                summary = str(exc).splitlines()[-1] if str(exc) else type(exc).__name__
                self.action_events.put(("done", f"✗ {summary}"))
            else:
                self.action_events.put(success(result))

        threading.Thread(target=worker, daemon=True).start()

    def publish_action(self, tree, create_pr):
        if tree is None or tree.unavailable or tree.branch == "(detached)":
            self.message = "! Open shipr from an available branch worktree"
            return
        if create_pr and tree.pr and tree.pr.get("state") == "OPEN":
            self.message = "! This branch already has an open PR"
            return
        if create_pr and tree.pr_unavailable:
            self.message = "! GitHub status is unavailable; refresh before creating a PR"
            return
        from_main = create_pr and tree.is_base
        verb = "create a branch here and open a PR" if from_main else "create a PR" if create_pr else "push"
        if not confirm(self.window, f"{verb} for {tree.branch}?"):
            self.message = "○ Cancelled"
            return
        try:
            dirty_now = has_changes(tree.path)
        except CommandError as exc:
            self.message = f"✗ {exc}"
            return
        if from_main and not dirty_now:
            self.message = "! The default branch needs uncommitted changes to create a PR"
            return
        branch_name = None
        if from_main:
            branch_name = prompt(self.window, "New branch name: ")
            if not branch_name:
                self.message = "○ Cancelled: branch name required"
                return
        commit_message = prompt(self.window, "Commit message: ") if dirty_now else ""
        if dirty_now and not commit_message:
            self.message = "○ Cancelled: commit message required"
            return
        if from_main:
            self.start_action(lambda operation: publish_from_main(tree, branch_name, commit_message, operation),
                              lambda result: ("created", result))
        else:
            self.start_action(
                lambda operation: publish(tree, commit_message, create_pr, operation),
                lambda result: ("created", result) if create_pr else ("done", f"✓ {result}"),
            )

    def update_pr_action(self, item):
        if item.worktree is None:
            self.message = "! Open this PR in a Herdr worktree before pushing"
            return
        if not confirm(self.window, f"Push worktree changes to PR #{item.pr['number']}?"):
            self.message = "○ Cancelled"
            return
        try:
            dirty_now = has_changes(item.worktree)
        except CommandError as exc:
            self.message = f"✗ {exc}"
            return
        commit_message = prompt(self.window, "Commit message: ") if dirty_now else ""
        if dirty_now and not commit_message:
            self.message = "○ Cancelled: commit message required"
            return
        self.start_action(lambda operation: update_pr(item, commit_message, operation),
                          lambda result: ("done", f"✓ {result}"))

    def handle_action(self, action_id):
        item = self.selected_item()
        if item is None:
            return False
        if action_id == "open_pr":
            try:
                open_pr(item)
            except CommandError as exc:
                self.message = f"✗ {exc}"
            else:
                number = item.pr.get("number")
                self.message = f"✓ Opened PR #{number} in GitHub" if number else "✓ Opened PR in GitHub"
            return False
        if action_id == "focus_worktree":
            if self.current_tree and item.worktree == self.current_tree.path:
                return True
            try:
                open_herdr_worktree(self.repo, item.worktree, item.branch)
            except CommandError as exc:
                self.message = f"✗ {exc}"
                return False
            return True
        if action_id == "checkout_pr":
            self.start_action(lambda operation: checkout_pr(item, operation),
                              lambda _path: ("checked_out", None))
            return False
        if action_id == "update_pr":
            self.update_pr_action(item)
            return False
        self.message = "! Unknown action"
        return False

    def handle_key(self, key):
        if self.active_action is not None:
            if key == ord("q") and not self.closing_after_cancel:
                self.closing_after_cancel = True
                self.active_action.cancel()
                self.action_stage = "Cancelling"
            return False
        if key == ord("q"):
            return True
        action = None
        if key == curses.KEY_MOUSE:
            action, close = self.handle_mouse()
            if close:
                return True
            if action is None:
                return False
        if key in (curses.KEY_DOWN, ord("j")):
            self.menu = None
            self.created_pr_url = ""
            self.selected = min(self.selected + 1, max(0, len(self.items) - 1))
        elif key in (curses.KEY_UP, ord("k")):
            self.menu = None
            self.created_pr_url = ""
            self.selected = max(0, self.selected - 1)
        elif key == ord("r"):
            self.menu = None
            self.start_refresh()
            self.message_persistent = False
            self.message = "Refreshing..."
        elif key == ord("p"):
            self.menu = None
            self.publish_action(self.current_tree, True)
        elif key == ord("u"):
            self.menu = None
            self.publish_action(self.current_tree, False)
        elif key == ord("o"):
            self.menu = None
            if self.created_pr_url:
                try:
                    run(["open", self.created_pr_url], cwd=self.repo)
                except CommandError as exc:
                    self.message = f"✗ {exc}"
                else:
                    self.message = "✓ Opened PR in GitHub"
            elif self.selected_item():
                return self.handle_action("open_pr")
        elif action is not None:
            return self.handle_action(action[1])
        return False

    def run(self):
        self.start_refresh()
        while True:
            if self.receive_actions():
                return
            self.receive_refresh()
            if self.active_action is None and time.monotonic() - self.refreshed >= REFRESH_SECONDS:
                self.start_refresh()
            self.draw()
            if self.handle_key(self.window.getch()):
                return


def main(window):
    curses.curs_set(0)
    curses.set_escdelay(25)
    curses.mouseinterval(0)
    curses.mousemask(curses.BUTTON1_PRESSED | curses.BUTTON1_CLICKED |
                     curses.BUTTON3_PRESSED | curses.BUTTON3_CLICKED)
    init_colors()
    window.keypad(True)
    window.timeout(100)
    ShiprApp(window, repository_directory()).run()


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
