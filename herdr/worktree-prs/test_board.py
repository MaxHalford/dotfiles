import importlib.util
import json
import queue
import subprocess
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest import mock


SPEC = importlib.util.spec_from_file_location("worktree_pr_board", Path(__file__).with_name("board.py"))
board = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(board)


def git(*args, cwd):
    return subprocess.run(["git", *args], cwd=cwd, text=True, capture_output=True, check=True).stdout.strip()


class BoardTests(unittest.TestCase):
    def test_parse_worktrees_and_open_pr(self):
        with tempfile.TemporaryDirectory() as directory:
            raw = f"worktree {directory}\0HEAD abc\0branch refs/heads/feature/a\0\0"
            tree = board.parse_worktrees(raw)[0]
            self.assertEqual(tree.branch, "feature/a")
            self.assertFalse(tree.unavailable)
            prs = [
                {"headRefName": "feature/a", "state": "MERGED"},
                {"headRefName": "feature/a", "state": "OPEN"},
            ]
            self.assertEqual(board.matching_pr(prs, tree.branch)["state"], "OPEN")

    def test_prunable_worktree_is_unavailable(self):
        raw = "worktree /tmp/missing-worktree\0HEAD abc\0branch refs/heads/old\0prunable gitdir missing\0\0"
        self.assertTrue(board.parse_worktrees(raw)[0].unavailable)

    def test_relevant_worktrees_and_commit_ages(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            checkout = root / "main"
            git("init", "-b", "main", str(checkout), cwd=root)
            git("config", "user.name", "Test User", cwd=checkout)
            git("config", "user.email", "test@example.com", cwd=checkout)
            (checkout / "base.txt").write_text("base\n")
            git("add", "-A", cwd=checkout)
            git("commit", "-m", "Initial", cwd=checkout)
            for branch in ("quiet", "dirty", "feature"):
                git("worktree", "add", "-b", branch, str(root / branch), "main", cwd=checkout)
            (root / "dirty" / "new.txt").write_text("not committed\n")
            (root / "feature" / "new.txt").write_text("committed\n")
            git("add", "-A", cwd=root / "feature")
            git("commit", "-m", "Feature", cwd=root / "feature")

            original_run = board.run

            def run_without_github(argv, **kwargs):
                if argv[:3] == ["gh", "pr", "list"]:
                    return "[]"
                return original_run(argv, **kwargs)

            with mock.patch.object(board, "run", side_effect=run_without_github):
                trees, error = board.load_board(checkout)
            self.assertFalse(error)
            visible = [tree.branch for tree in board.visible_worktrees(trees)]
            self.assertEqual(visible[0], "main")
            self.assertEqual(set(visible), {"main", "feature", "dirty"})
            self.assertEqual(len(board.visible_worktrees(trees, show_all=True)), 4)
            self.assertGreater(trees[0].last_commit, 0)
            self.assertTrue(trees[0].is_base)
            self.assertEqual(board.local_status(next(tree for tree in trees if tree.branch == "feature")),
                             "+1 commit")

            def run_with_open_pr(argv, **kwargs):
                if argv[:3] == ["gh", "pr", "list"]:
                    return json.dumps([{"headRefName": "quiet", "state": "OPEN"}])
                return original_run(argv, **kwargs)

            with mock.patch.object(board, "run", side_effect=run_with_open_pr):
                trees, _ = board.load_board(checkout)
            self.assertEqual(len(board.visible_worktrees(trees)), 4)

    def test_age_labels(self):
        self.assertEqual(board.age_label(0, now=100), "-")
        self.assertEqual(board.age_label(100, now=100), "just now")
        self.assertEqual(board.age_label(100, now=220), "2m ago")
        self.assertEqual(board.age_label(100, now=7300), "2h ago")

    def test_commit_all_and_push_only_selected_worktree(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            origin = root / "origin.git"
            checkout = root / "checkout"
            git("init", "--bare", str(origin), cwd=root)
            git("init", "-b", "main", str(checkout), cwd=root)
            git("config", "user.name", "Test User", cwd=checkout)
            git("config", "user.email", "test@example.com", cwd=checkout)
            (checkout / "base.txt").write_text("base\n")
            git("add", "-A", cwd=checkout)
            git("commit", "-m", "Initial", cwd=checkout)
            git("remote", "add", "origin", str(origin), cwd=checkout)
            git("switch", "-c", "feature/a", cwd=checkout)
            (checkout / "base.txt").write_text("changed\n")
            (checkout / "new.txt").write_text("new\n")
            hook = checkout / ".git" / "hooks" / "pre-commit"
            hook.write_text("#!/bin/sh\necho 'Checking files in pre-commit'\n")
            hook.chmod(0o755)
            events = queue.SimpleQueue()
            operation = board.Operation(events)
            self.assertTrue(board.commit_all(checkout, "Add feature", operation))
            board.push(checkout, "feature/a", operation)
            head = git("rev-parse", "HEAD", cwd=checkout)
            self.assertEqual(git("rev-parse", "refs/heads/feature/a", cwd=origin), head)
            self.assertEqual(git("status", "--porcelain", cwd=checkout), "")
            self.assertEqual(git("log", "-1", "--format=%s", cwd=checkout), "Add feature")
            reported = []
            while not events.empty():
                reported.append(events.get_nowait())
            self.assertIn(("stage", "Committing (hooks may run)"), reported)
            self.assertIn(("line", "Checking files in pre-commit"), reported)
            self.assertIn(("stage", "Pushing branch"), reported)

    def test_create_pr_never_publishes_when_status_is_unavailable(self):
        tree = board.Worktree(Path("/tmp/example"), "feature/a", pr_unavailable=True)
        with mock.patch.object(board, "run") as command:
            with self.assertRaisesRegex(board.CommandError, "status is unavailable"):
                board.publish(tree, "Message", True)
            command.assert_not_called()

    def test_create_pr_pushes_before_opening(self):
        tree = board.Worktree(Path("/tmp/example"), "feature/a")
        with mock.patch.object(board, "run", side_effect=["main\n", "https://github.com/example/repo/pull/1\n"]), \
             mock.patch.object(board, "has_changes", return_value=False), \
             mock.patch.object(board, "push") as push:
            result = board.publish(tree, "", True)
        self.assertEqual(result, "https://github.com/example/repo/pull/1")
        push.assert_called_once_with(tree.path, tree.branch, None)

    def test_create_pr_from_main_branches_before_committing_and_pushing(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            origin = root / "origin.git"
            checkout = root / "checkout"
            git("init", "--bare", str(origin), cwd=root)
            git("init", "-b", "main", str(checkout), cwd=root)
            git("config", "user.name", "Test User", cwd=checkout)
            git("config", "user.email", "test@example.com", cwd=checkout)
            (checkout / "base.txt").write_text("base\n")
            git("add", "-A", cwd=checkout)
            git("commit", "-m", "Initial", cwd=checkout)
            initial_head = git("rev-parse", "HEAD", cwd=checkout)
            git("remote", "add", "origin", str(origin), cwd=checkout)
            git("branch", "topic/taken", cwd=checkout)
            (checkout / "change.txt").write_text("change\n")
            tree = board.Worktree(checkout, "main", dirty=True)
            original_run = board.run
            github_calls = []

            def run_with_github(argv, **kwargs):
                if argv[:3] == ["gh", "repo", "view"]:
                    return "main\n"
                if argv[:3] == ["gh", "pr", "create"]:
                    github_calls.append(argv)
                    return "https://github.com/example/repo/pull/1\n"
                return original_run(argv, **kwargs)

            with mock.patch.object(board, "run", side_effect=run_with_github):
                result = board.publish(tree, "Fix the popup", True, branch_name="topic/popup")
            self.assertEqual(result, "https://github.com/example/repo/pull/1")
            self.assertEqual(git("branch", "--show-current", cwd=checkout), "topic/popup")
            self.assertEqual(git("rev-parse", "main", cwd=checkout), initial_head)
            self.assertEqual(git("status", "--porcelain", cwd=checkout), "")
            self.assertEqual(git("rev-parse", "topic/popup", cwd=checkout),
                             git("rev-parse", "refs/heads/topic/popup", cwd=origin))
            self.assertEqual(github_calls[0][-2:], ["--head", "topic/popup"])
            with self.assertRaisesRegex(board.CommandError, "already exists"):
                board.validate_new_branch(checkout, "topic/taken")
            with self.assertRaisesRegex(board.CommandError, "Invalid branch name"):
                board.validate_new_branch(checkout, "bad..name")

    def test_create_pr_from_main_requires_a_branch_name_before_switching(self):
        tree = board.Worktree(Path("/tmp/example"), "main")
        with mock.patch.object(board, "run", return_value="main\n") as command, \
             mock.patch.object(board, "has_changes", return_value=True):
            with self.assertRaisesRegex(board.CommandError, "branch name is required"):
                board.publish(tree, "A commit", True)
        self.assertEqual(command.call_count, 1)

    def test_create_pr_from_clean_main_does_not_create_a_branch(self):
        tree = board.Worktree(Path("/tmp/example"), "main")
        with mock.patch.object(board, "run", return_value="main\n") as command, \
             mock.patch.object(board, "has_changes", return_value=False):
            with self.assertRaisesRegex(board.CommandError, "needs uncommitted changes"):
                board.publish(tree, "", True)
        self.assertEqual(command.call_count, 1)

    def test_cancel_stops_a_running_command(self):
        events = queue.SimpleQueue()
        operation = board.Operation(events)
        errors = []

        def work():
            try:
                board.run(["python3", "-u", "-c",
                           "import time; print('Running hook'); time.sleep(10)"], operation=operation)
            except board.CommandError as error:
                errors.append(str(error))

        worker = threading.Thread(target=work, daemon=True)
        worker.start()
        self.assertEqual(events.get(timeout=2), ("line", "Running hook"))
        operation.cancel()
        worker.join(timeout=3)
        self.assertFalse(worker.is_alive())
        self.assertIn("Cancelled", errors[0])

    def test_escape_cancels_confirmation(self):
        window = mock.Mock()
        window.getmaxyx.return_value = (20, 80)
        window.get_wch.return_value = "\x1b"
        with mock.patch.object(board.curses, "curs_set"):
            self.assertFalse(board.confirm(window, "Publish?"))

    def test_enter_accepts_confirmation(self):
        window = mock.Mock()
        window.getmaxyx.return_value = (20, 80)
        window.get_wch.return_value = "\n"
        with mock.patch.object(board.curses, "curs_set"):
            self.assertTrue(board.confirm(window, "Publish?"))

    def test_option_delete_erases_a_word_in_commit_message(self):
        window = mock.Mock()
        window.getmaxyx.return_value = (20, 80)
        window.get_wch.side_effect = list("Add fix") + ["\x1b", "\x7f"] + list("popup") + ["\n"]
        with mock.patch.object(board.curses, "curs_set"):
            self.assertEqual(board.prompt(window, "Commit message: "), "Add popup")

    def test_commit_message_supports_cursor_editing(self):
        window = mock.Mock()
        window.getmaxyx.return_value = (20, 80)
        window.get_wch.side_effect = ["A", "c", board.curses.KEY_LEFT, "b", "\n"]
        with mock.patch.object(board.curses, "curs_set"):
            self.assertEqual(board.prompt(window, "Commit message: "), "Abc")

    def test_escape_does_not_close_while_refresh_is_running(self):
        window = mock.Mock()
        window.getmaxyx.return_value = (24, 100)
        window.getch.side_effect = [27, ord("q")]

        def slow_refresh(_repo):
            time.sleep(0.5)
            return [], ""

        with mock.patch.object(board, "repository_directory", return_value=Path("/tmp/example")), \
             mock.patch.object(board, "load_board", side_effect=slow_refresh), \
             mock.patch.object(board, "init_colors"), \
             mock.patch.object(board.curses, "curs_set"), \
             mock.patch.object(board.curses, "set_escdelay"), \
             mock.patch.object(board.curses, "mouseinterval"), \
             mock.patch.object(board.curses, "mousemask"):
            started = time.monotonic()
            board.main(window)
            elapsed = time.monotonic() - started
        self.assertEqual(window.getch.call_count, 2)
        self.assertLess(elapsed, 0.2)

    def test_pr_status_colors(self):
        with mock.patch.object(board.curses, "color_pair", side_effect=lambda pair: pair):
            merged = board.Worktree(Path("/tmp/example"), "feature/a", pr={"state": "MERGED"})
            failed = board.Worktree(Path("/tmp/example"), "feature/a", pr={
                "state": "OPEN", "statusCheckRollup": [{"conclusion": "FAILURE"}]
            })
            waiting = board.Worktree(Path("/tmp/example"), "feature/a", pr={
                "state": "OPEN", "reviewDecision": "REVIEW_REQUIRED"
            })
            self.assertEqual(board.status_style(merged), 4)
            self.assertEqual(board.status_style(failed), 3)
            self.assertEqual(board.status_style(waiting), 2)

    def test_context_menu_offers_actions_for_the_clicked_worktree(self):
        tree = board.Worktree(Path("/tmp/feature"), "feature/a", dirty=True)
        menu = board.context_menu(tree, 95, 22, 100, 24)
        self.assertIs(menu.tree, tree)
        self.assertLess(menu.x + menu.width, 100)
        self.assertLess(menu.y + len(menu.actions) + 1, 24)
        self.assertEqual(board.menu_choice(menu, menu.x + 2, menu.y + 1),
                         ("Commit & create PR", "create_pr"))
        self.assertEqual(board.menu_choice(menu, menu.x + 2, menu.y + 2),
                         ("Commit & push", "push"))
        self.assertIsNone(board.menu_choice(menu, menu.x - 1, menu.y + 1))

    def test_context_menu_hides_create_pr_when_one_is_open_or_status_is_unknown(self):
        open_pr = board.Worktree(Path("/tmp/feature"), "feature/a", pr={"state": "OPEN"})
        unknown = board.Worktree(Path("/tmp/feature"), "feature/a", pr_unavailable=True)
        self.assertEqual(board.context_actions(open_pr), [("Push", "push")])
        self.assertEqual(board.context_actions(unknown), [("Push", "push")])
        self.assertEqual(board.context_actions(board.Worktree(Path("/tmp/feature"), "(detached)")), [])

    def test_context_menu_labels_default_branch_creation(self):
        main = board.Worktree(Path("/tmp/main"), "main", dirty=True, is_base=True)
        self.assertEqual(board.context_actions(main)[0], ("Commit & create branch/PR", "create_pr"))

    def test_hook_output_drops_terminal_escape_codes(self):
        self.assertEqual(board.clean("\x1b[31mfailed\x1b[0m"), "failed")


if __name__ == "__main__":
    unittest.main()
