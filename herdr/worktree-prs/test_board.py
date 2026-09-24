import importlib.util
import json
import os
import queue
import subprocess
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

import shipr_core as core


SPEC = importlib.util.spec_from_file_location("shipr_board", Path(__file__).with_name("board.py"))
board = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(board)


def git(*args, cwd):
    return subprocess.run(["git", *args], cwd=cwd, text=True, capture_output=True, check=True).stdout.strip()


def repository(root):
    checkout = root / "project"
    git("init", "-b", "main", str(checkout), cwd=root)
    git("config", "user.name", "Test User", cwd=checkout)
    git("config", "user.email", "test@example.com", cwd=checkout)
    (checkout / "base.txt").write_text("base\n")
    git("add", "-A", cwd=checkout)
    git("commit", "-m", "Initial", cwd=checkout)
    return checkout


class ShiprTests(unittest.TestCase):
    def test_pr_mapping_distinguishes_forks_with_the_same_branch_name(self):
        prs = [
            {"number": 1, "state": "OPEN", "headRefName": "feature"},
            {"number": 2, "state": "OPEN", "headRefName": "feature"},
        ]
        self.assertIsNone(core.matching_pr(prs, "feature"))
        self.assertEqual(core.matching_pr(prs, "shipr/pr-2-abcdef1234"), prs[1])
        self.assertEqual(core.matching_pr(prs, "shipr/pr-2-abcdef1234-2"), prs[1])
        rows = core.pull_request_rows(Path("/tmp/project"), prs, [
            core.Worktree(Path("/tmp/feature"), "feature"),
            core.Worktree(Path("/tmp/pr-two"), "shipr/pr-2-abcdef1234"),
        ])
        self.assertIsNone(rows[0].worktree)
        self.assertEqual(rows[1].worktree, Path("/tmp/pr-two"))

    def test_board_lists_only_prs_and_tracks_the_originating_worktree(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            checkout = repository(root)
            feature = root / "feature"
            git("worktree", "add", "-b", "feature", str(feature), "main", cwd=checkout)
            (feature / "change.txt").write_text("change\n")
            original_run = core.run

            def run_with_prs(argv, **kwargs):
                if argv[:3] == ["gh", "pr", "list"]:
                    self.assertEqual(argv[3:7], ["--state", "open", "--limit", "50"])
                    return json.dumps([
                        {"number": 12, "headRefName": "feature", "state": "OPEN", "title": "Local"},
                        {"number": 13, "headRefName": "remote", "state": "OPEN", "title": "Remote"},
                    ])
                return original_run(argv, **kwargs)

            with mock.patch.object(core, "run", side_effect=run_with_prs):
                rows, current, error = core.load_board(feature)
            self.assertEqual(error, "")
            self.assertEqual([row.pr["number"] for row in rows], [12, 13])
            self.assertEqual(rows[0].worktree.resolve(), feature.resolve())
            self.assertIsNone(rows[1].worktree)
            self.assertEqual(current.branch, "feature")
            self.assertTrue(current.dirty)
            self.assertEqual(current.pr["number"], 12)
            self.assertEqual(board.context_actions(rows[0])[-1],
                             ("Commit & push to PR", "update_pr"))
            self.assertEqual(board.context_actions(rows[1])[-1],
                             ("Open in new Herdr worktree", "checkout_pr"))

    def test_pr_checkout_uses_herdr_and_leaves_current_worktree_alone(self):
        repo = Path("/tmp/project")
        row = core.PullRequest(repo, {"number": 42, "state": "OPEN"})
        calls = []

        def command(argv, **kwargs):
            calls.append(argv)
            if argv[:3] == ["git", "rev-parse", "--short=10"]:
                return "abcdef1234\n"
            if argv[:3] == ["git", "show-ref", "--verify"]:
                raise core.CommandError("branch absent")
            return ""

        with mock.patch.dict(os.environ, {"HERDR_WORKSPACE_ID": "w12"}), \
             mock.patch.object(core, "run", side_effect=command):
            branch = core.checkout_pr(row)
        self.assertEqual(branch, "shipr/pr-42-abcdef1234")
        self.assertEqual(calls[0], ["git", "fetch", "origin", "pull/42/head"])
        self.assertEqual(calls[-1], [os.environ.get("HERDR_BIN_PATH", "herdr"), "worktree", "create",
                                     "--workspace", "w12", "--branch", branch, "--base", "FETCH_HEAD",
                                     "--label", "PR #42", "--focus"])
        self.assertFalse(any(argv[:2] == ["git", "switch"] for argv in calls))

    def test_pr_checkout_chooses_new_branch_when_previous_checkout_was_removed(self):
        row = core.PullRequest(Path("/tmp/project"), {"number": 42, "state": "OPEN"})
        seen = []

        def command(argv, **kwargs):
            seen.append(argv)
            if argv[:3] == ["git", "rev-parse", "--short=10"]:
                return "abcdef1234\n"
            if argv[:3] == ["git", "show-ref", "--verify"] and argv[-1].endswith("abcdef1234-2"):
                raise core.CommandError("branch absent")
            return ""

        with mock.patch.object(core, "run", side_effect=command):
            self.assertEqual(core.checkout_pr(row), "shipr/pr-42-abcdef1234-2")
        self.assertIn("--branch", seen[-1])
        self.assertEqual(seen[-1][seen[-1].index("--branch") + 1], "shipr/pr-42-abcdef1234-2")

    def test_pr_push_targets_its_current_head_repository_and_branch(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            checkout = repository(root)
            fork = root / "fork.git"
            git("init", "--bare", str(fork), cwd=root)
            git("worktree", "add", "-b", "shipr/pr-42-abcdef1234", str(root / "pr"), "main",
                cwd=checkout)
            pr_tree = root / "pr"
            (pr_tree / "fix.txt").write_text("fix\n")
            row = core.PullRequest(checkout, {"number": 42, "state": "OPEN"}, pr_tree)
            original_run = core.run

            def command(argv, **kwargs):
                if argv[:3] == ["gh", "pr", "view"]:
                    return json.dumps({"state": "OPEN", "headRefName": "contributor/fix",
                                       "headRepository": {"url": f"file://{root / 'fork'}"}})
                return original_run(argv, **kwargs)

            with mock.patch.object(core, "run", side_effect=command):
                self.assertEqual(core.update_pr(row, "Fix review feedback"), "PR #42 pushed")
            self.assertEqual(git("rev-parse", "HEAD", cwd=pr_tree),
                             git("rev-parse", "refs/heads/contributor/fix", cwd=fork))
            self.assertEqual(git("branch", "--show-current", cwd=pr_tree), "shipr/pr-42-abcdef1234")

    def test_closed_pr_is_not_pushed(self):
        row = core.PullRequest(Path("/tmp/project"), {"number": 42}, Path("/tmp/pr"))
        with mock.patch.object(core, "run", return_value='{"state":"CLOSED"}') as command:
            with self.assertRaisesRegex(core.CommandError, "no longer open"):
                core.push_to_pr(row)
        self.assertEqual(command.call_count, 1)

    def test_new_pr_publishes_the_current_branch_and_rejects_default_branch(self):
        tree = core.Worktree(Path("/tmp/project"), "feature")
        with mock.patch.object(core, "run", side_effect=["feature\n", "main\n",
                                                        "https://github.com/o/r/pull/1\n"]), \
             mock.patch.object(core, "has_changes", return_value=False), \
             mock.patch.object(core, "push") as push:
            self.assertEqual(core.publish(tree, "", True), "https://github.com/o/r/pull/1")
        push.assert_called_once_with(tree.path, "feature", None)
        base = core.Worktree(Path("/tmp/project"), "main")
        with mock.patch.object(core, "run", return_value="main\n") as command:
            with self.assertRaisesRegex(core.CommandError, "branch worktree in Herdr"):
                core.publish(base, "", True)
        self.assertEqual(command.call_count, 2)

    def test_current_open_pr_push_uses_pr_target(self):
        tree = core.Worktree(Path("/tmp/pr"), "shipr/pr-42-abcdef1234",
                             pr={"number": 42, "state": "OPEN"})
        with mock.patch.object(core, "run", return_value="shipr/pr-42-abcdef1234\n"), \
             mock.patch.object(core, "has_changes", return_value=False), \
             mock.patch.object(core, "push_to_pr") as push_pr, \
             mock.patch.object(core, "push") as push:
            self.assertEqual(core.publish(tree, "", False), "Changes pushed")
        push_pr.assert_called_once()
        push.assert_not_called()

    def test_dirty_main_creates_herdr_worktree_and_pr_with_the_current_changes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            checkout = repository(root)
            origin = root / "origin.git"
            git("init", "--bare", str(origin), cwd=root)
            git("remote", "add", "origin", str(origin), cwd=checkout)
            git("push", "-u", "origin", "main", cwd=checkout)
            (checkout / "base.txt").write_text("staged update\n")
            git("add", "base.txt", cwd=checkout)
            (checkout / "new.txt").write_text("untracked file\n")
            initial_main = git("rev-parse", "HEAD", cwd=checkout)
            created = root / "new-worktree"
            original_run = core.run
            herdr_calls = []

            def command(argv, **kwargs):
                if argv[:3] == ["gh", "repo", "view"]:
                    return "main\n"
                if argv[:3] == ["gh", "pr", "create"]:
                    return "https://github.com/o/r/pull/1\n"
                if argv[:3] == [os.environ.get("HERDR_BIN_PATH", "herdr"), "worktree", "create"]:
                    herdr_calls.append(argv)
                    git("worktree", "add", "-b", "topic/fix", str(created), argv[argv.index("--base") + 1],
                        cwd=checkout)
                    return ""
                if argv[:3] == [os.environ.get("HERDR_BIN_PATH", "herdr"), "worktree", "open"]:
                    herdr_calls.append(argv)
                    return ""
                return original_run(argv, **kwargs)

            with mock.patch.object(core, "run", side_effect=command):
                url = core.publish_from_main(core.Worktree(checkout, "main"), "topic/fix", "Fix it")
            self.assertEqual(url, "https://github.com/o/r/pull/1")
            self.assertEqual(git("branch", "--show-current", cwd=checkout), "main")
            self.assertEqual(git("rev-parse", "HEAD", cwd=checkout), initial_main)
            self.assertEqual(git("status", "--porcelain", cwd=checkout), "")
            self.assertEqual(git("branch", "--show-current", cwd=created), "topic/fix")
            self.assertEqual((created / "base.txt").read_text(), "staged update\n")
            self.assertEqual((created / "new.txt").read_text(), "untracked file\n")
            self.assertEqual(git("rev-parse", "HEAD", cwd=created),
                             git("rev-parse", "refs/heads/topic/fix", cwd=origin))
            self.assertEqual(git("stash", "list", cwd=checkout), "")
            self.assertIn("--no-focus", herdr_calls[0])
            self.assertIn("--focus", herdr_calls[1])

    def test_failed_herdr_creation_restores_main_changes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            checkout = repository(root)
            (checkout / "new.txt").write_text("keep this\n")
            original_run = core.run

            def command(argv, **kwargs):
                if argv[:3] == ["gh", "repo", "view"]:
                    return "main\n"
                if argv[:3] == [os.environ.get("HERDR_BIN_PATH", "herdr"), "worktree", "create"]:
                    raise core.CommandError("Herdr could not create a worktree")
                return original_run(argv, **kwargs)

            with mock.patch.object(core, "run", side_effect=command):
                with self.assertRaisesRegex(core.CommandError, "Herdr could not create"):
                    core.publish_from_main(core.Worktree(checkout, "main"), "topic/fix", "Fix it")
            self.assertEqual((checkout / "new.txt").read_text(), "keep this\n")
            self.assertEqual(git("stash", "list", cwd=checkout), "")
            self.assertEqual(git("branch", "--show-current", cwd=checkout), "main")

    def test_board_preserves_pr_selection_and_has_no_worktree_toggle(self):
        repo = Path("/tmp/project")
        current = core.Worktree(repo, "feature")
        first = core.PullRequest(repo, {"number": 1, "state": "OPEN"})
        second = core.PullRequest(repo, {"number": 2, "state": "OPEN"})
        app = board.ShiprApp(mock.Mock(), repo)
        app.items = [first, second]
        app.selected = 1
        updated = core.PullRequest(repo, {"number": 2, "state": "OPEN"})
        app.updates.put((([updated, first], current, ""), None))
        app.receive_refresh()
        self.assertIs(app.selected_item(), updated)
        self.assertIs(app.current_tree, current)
        app.handle_key(ord("\t"))
        self.assertEqual(app.items, [updated, first])

    def test_global_publish_uses_current_worktree_even_when_pr_table_is_empty(self):
        app = board.ShiprApp(mock.Mock(), Path("/tmp/project"))
        app.current_tree = core.Worktree(Path("/tmp/project"), "feature")
        with mock.patch.object(app, "publish_action") as publish:
            app.handle_key(ord("p"))
            app.handle_key(ord("u"))
        self.assertEqual(publish.call_args_list,
                         [mock.call(app.current_tree, True), mock.call(app.current_tree, False)])

    def test_pr_row_focus_uses_herdr_worktree_open(self):
        repo = Path("/tmp/project")
        path = Path("/tmp/pr")
        row = core.PullRequest(repo, {"number": 42, "headRefName": "feature"}, path)
        app = board.ShiprApp(mock.Mock(), repo)
        app.items = [row]
        with mock.patch.object(board, "open_herdr_worktree") as opened:
            self.assertTrue(app.handle_action("focus_worktree"))
        opened.assert_called_once_with(repo, path, "feature")

    def test_open_pr_uses_its_url(self):
        row = core.PullRequest(Path("/tmp/project"),
                               {"number": 42, "state": "OPEN", "url": "https://github.com/o/r/pull/42"})
        with mock.patch.object(core, "run") as command:
            core.open_pr(row)
        command.assert_called_once_with(["open", "https://github.com/o/r/pull/42"], cwd=row.repo)

    def test_cancel_stops_a_running_command(self):
        events = queue.SimpleQueue()
        operation = core.Operation(events)
        errors = []

        def work():
            try:
                core.run(["python3", "-u", "-c", "import time; print('Running'); time.sleep(10)"],
                         operation=operation)
            except core.CommandError as error:
                errors.append(str(error))

        worker = threading.Thread(target=work, daemon=True)
        worker.start()
        self.assertEqual(events.get(timeout=2), ("line", "Running"))
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

    def test_hook_output_drops_terminal_escape_codes(self):
        self.assertEqual(core.clean("\x1b[31mfailed\x1b[0m"), "failed")


if __name__ == "__main__":
    unittest.main()
