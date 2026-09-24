import importlib.util
import subprocess
import tempfile
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
            self.assertTrue(board.commit_all(checkout, "Add feature"))
            board.push(checkout, "feature/a")
            head = git("rev-parse", "HEAD", cwd=checkout)
            self.assertEqual(git("rev-parse", "refs/heads/feature/a", cwd=origin), head)
            self.assertEqual(git("status", "--porcelain", cwd=checkout), "")
            self.assertEqual(git("log", "-1", "--format=%s", cwd=checkout), "Add feature")

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
        push.assert_called_once_with(tree.path, tree.branch)


if __name__ == "__main__":
    unittest.main()
