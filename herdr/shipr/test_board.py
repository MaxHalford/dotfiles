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
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            feature = root / "feature"
            pr_two = root / "pr-two"
            feature.mkdir()
            pr_two.mkdir()
            raw = (f"worktree {feature}\0branch refs/heads/feature\0\0"
                   f"worktree {pr_two}\0branch refs/heads/shipr/pr-2-abcdef1234\0\0")
            rows = [core.PullRequest(root, pr) for pr in prs]
            with mock.patch.object(core, "run", return_value=raw):
                self.assertIsNone(core.find_pr_worktree(rows[0], prs))
                self.assertEqual(core.find_pr_worktree(rows[1], prs), pr_two)

    def test_board_loads_prs_without_looking_up_every_worktree(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            checkout = repository(root)
            feature = root / "feature"
            git("worktree", "add", "-b", "feature", str(feature), "main", cwd=checkout)
            (feature / "change.txt").write_text("change\n")
            original_run = core.run
            commands = []

            def run_with_prs(argv, **kwargs):
                commands.append(argv)
                if argv[:3] == ["gh", "repo", "view"]:
                    return json.dumps({"nameWithOwner": "owner/project",
                                       "url": "https://github.com/owner/project"})
                if argv[:3] == ["gh", "api", "graphql"]:
                    self.assertIn("first=25", argv)
                    self.assertIn("commits(last: 1)", argv[argv.index("-f") + 1])
                    return json.dumps({"data": {"repository": {"pullRequests": {
                        "nodes": [
                            {"number": 12, "headRefName": "feature", "state": "OPEN",
                             "title": "Local", "commits": {"nodes": [{"commit": {
                                 "committedDate": "2026-09-25T12:00:00Z",
                                 "statusCheckRollup": {"state": "SUCCESS"}}}]}},
                            {"number": 13, "headRefName": "remote", "state": "OPEN",
                             "title": "Remote", "commits": {"nodes": []}},
                        ], "pageInfo": {"endCursor": None, "hasNextPage": False},
                        "totalCount": 2}}}})
                return original_run(argv, **kwargs)

            with mock.patch.object(core, "run", side_effect=run_with_prs):
                page = core.load_board(feature)
            rows, current = page.items, page.current
            self.assertEqual(page.error, "")
            self.assertEqual([row.pr["number"] for row in rows], [12, 13])
            self.assertEqual(page.total_count, 2)
            self.assertEqual(rows[0].pr["lastCommitAt"], "2026-09-25T12:00:00Z")
            self.assertEqual(rows[0].pr["statusCheckRollup"], [{"state": "SUCCESS"}])
            self.assertIsNone(rows[0].worktree)
            self.assertIsNone(rows[1].worktree)
            self.assertFalse(any(argv[:3] == ["git", "worktree", "list"] for argv in commands))
            self.assertEqual(core.find_pr_worktree(rows[0], [row.pr for row in rows]).resolve(),
                             feature.resolve())
            self.assertEqual(current.branch, "feature")
            self.assertTrue(current.dirty)
            self.assertEqual(current.pr["number"], 12)
            rows[0].worktree = feature
            self.assertEqual(board.context_actions(rows[0])[-1],
                             ("Commit & push to PR", "update_pr"))
            self.assertEqual(board.context_actions(rows[1])[-1],
                             ("Open in new Herdr worktree", "checkout_pr"))

    def test_pr_page_uses_a_cursor_and_normalizes_head_commit(self):
        response = {"data": {"repository": {"pullRequests": {
            "nodes": [{"number": 7, "state": "OPEN", "commits": {"nodes": [{"commit": {
                "committedDate": "2026-09-25T12:00:00Z",
                "statusCheckRollup": {"state": "PENDING"}}}]}}],
            "pageInfo": {"endCursor": "next-page", "hasNextPage": True},
            "totalCount": 70}}}}
        with mock.patch.object(core, "github_repository", return_value=("owner", "project", "github.com")), \
             mock.patch.object(core, "run", return_value=json.dumps(response)) as command:
            prs, cursor, total, error = core.load_open_prs(Path("/tmp/project"), "first-page")
        self.assertEqual((cursor, total, error), ("next-page", 70, ""))
        self.assertEqual(prs[0]["lastCommitAt"], "2026-09-25T12:00:00Z")
        self.assertEqual(prs[0]["statusCheckRollup"], [{"state": "PENDING"}])
        argv = command.call_args.args[0]
        self.assertIn("first=25", argv)
        self.assertIn("after=first-page", argv)
        self.assertNotIn("contexts", argv[argv.index("-f") + 1])

    def test_github_repository_uses_local_origin_without_an_api_call(self):
        repo = Path("/tmp/project")
        with mock.patch.dict(os.environ, {"GH_REPO": "", "GH_HOST": ""}), \
             mock.patch.object(core, "run", return_value="git@github.com:owner/project.git\n") as command:
            self.assertEqual(core.github_repository.__wrapped__(repo),
                             ("owner", "project", "github.com"))
        command.assert_called_once_with(["git", "remote", "get-url", "origin"], cwd=repo)

    def test_current_branch_pr_is_checked_only_when_p_is_pressed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            checkout = repository(root)
            feature = root / "feature"
            git("worktree", "add", "-b", "feature", str(feature), "main", cwd=checkout)
            prs = [{"number": number, "state": "OPEN", "headRefName": f"other-{number}"}
                   for number in range(1, 26)]
            with mock.patch.object(core, "load_open_prs", return_value=(prs, "page-two", 50, "")), \
                 mock.patch.object(core, "current_branch_pr") as lookup:
                page = core.load_board(feature)
            lookup.assert_not_called()
            self.assertIsNone(page.current.pr)
            self.assertEqual(page.next_cursor, "page-two")
            self.assertEqual(len(page.items), 25)
            app = board.ShiprApp(mock.Mock(), feature)
            with mock.patch.object(board, "current_branch_pr", return_value={
                    "number": 49, "state": "OPEN", "headRefName": "feature"}) as lookup, \
                 mock.patch.object(board, "confirm", return_value=False) as confirm:
                app.publish_action(page.current)
            lookup.assert_called_once_with(feature, "feature")
            self.assertEqual(page.current.pr["number"], 49)
            self.assertIn("push to PR #49", confirm.call_args.args[1])

    def test_refresh_fetches_only_the_pages_already_loaded(self):
        with tempfile.TemporaryDirectory() as directory:
            checkout = repository(Path(directory))
            first = [{"number": number, "state": "OPEN", "headRefName": f"branch-{number}"}
                     for number in range(1, 26)]
            second = [{"number": number, "state": "OPEN", "headRefName": f"branch-{number}"}
                      for number in range(26, 31)]
            with mock.patch.object(core, "load_open_prs", side_effect=[
                    (first, "page-two", 30, ""), (second, None, 30, "")]) as load:
                page = core.load_board(checkout, pages=2)
            self.assertEqual([call.args[1] for call in load.call_args_list], [None, "page-two"])
            self.assertEqual(len(page.items), 30)
            self.assertEqual(page.total_count, 30)
            self.assertIsNone(page.next_cursor)

    def test_scroll_fetches_next_page_and_preserves_selection(self):
        repo = Path("/tmp/project")
        window = mock.Mock()
        window.getmaxyx.return_value = (16, 110)
        app = board.ShiprApp(window, repo)
        app.items = [core.PullRequest(repo, {"number": number, "state": "OPEN",
                                                 "lastCommitAt": f"2026-09-{25 - number:02d}T12:00:00Z"})
                     for number in range(1, 26)]
        app.selected = 23
        app.next_cursor = "page-two"
        app.total_count = 50
        older = [core.PullRequest(repo, {"number": number, "state": "OPEN",
                                          "lastCommitAt": "2026-08-01T12:00:00Z"})
                 for number in range(26, 51)]
        with mock.patch.object(board, "load_board", return_value=core.BoardPage(
                older, core.Worktree(repo, "main"), None, 50)) as load:
            app.handle_key(board.curses.KEY_DOWN)
            update = app.page_updates.get(timeout=2)
            app.page_updates.put(update)
        app.receive_more()
        load.assert_called_once_with(repo, cursor="page-two")
        self.assertEqual(len(app.items), 50)
        self.assertEqual(app.selected_item().pr["number"], 25)
        self.assertIsNone(app.next_cursor)

    def test_left_and_right_arrows_move_visible_pages(self):
        repo = Path("/tmp/project")
        window = mock.Mock()
        window.getmaxyx.return_value = (10, 100)
        app = board.ShiprApp(window, repo)
        app.items = [core.PullRequest(repo, {"number": number}) for number in range(20)]
        app.handle_key(board.curses.KEY_RIGHT)
        self.assertEqual(app.selected, 5)
        app.handle_key(board.curses.KEY_LEFT)
        self.assertEqual(app.selected, 0)
        app.selected = 14
        with mock.patch.object(app, "start_load_more") as load_more:
            app.handle_key(board.curses.KEY_RIGHT)
        self.assertEqual(app.selected, 19)
        load_more.assert_called_once()

    def test_last_commit_age_and_sort_order(self):
        repo = Path("/tmp/project")
        newer = core.PullRequest(repo, {"number": 2, "lastCommitAt": "2026-09-25T12:00:00Z"})
        older = core.PullRequest(repo, {"number": 1, "lastCommitAt": "2026-09-24T12:00:00Z"})
        self.assertEqual(board.sort_prs([older, newer]), [newer, older])
        self.assertEqual(board.commit_age(newer.pr, board.commit_time(newer.pr) + 3600), "1h ago")

    def test_pr_table_shows_colored_diffs_and_alternating_rows(self):
        window = mock.Mock()
        window.getmaxyx.return_value = (10, 110)
        app = board.ShiprApp(window, Path("/tmp/project"), stripe_colors=True)
        app.items = [
            core.PullRequest(app.repo, {"number": 1, "state": "OPEN", "title": "First",
                                           "headRefName": "first", "additions": 0, "deletions": 2,
                                           "url": "https://github.com/o/r/pull/1",
                                           "statusCheckRollup": [
                                               {"status": "COMPLETED", "conclusion": "SUCCESS"}]}),
            core.PullRequest(app.repo, {"number": 2, "state": "OPEN", "title": "Second",
                                           "headRefName": "second", "additions": 1234567,
                                           "deletions": 56, "statusCheckRollup": [
                                               {"state": "FAILURE"}]}, Path("/tmp/second")),
        ]
        with mock.patch.object(board.curses, "color_pair", side_effect=lambda pair: pair << 8):
            app.draw()
        calls = [call.args for call in window.addnstr.call_args_list]
        self.assertTrue(any(row == 1 and "LAST COMMIT" in value and "CI" in value and
                            "DIFF" in value
                            for row, _, value, *_ in calls))
        selected = [call for call in calls if call[0] == 2]
        self.assertEqual(len(selected), 1)
        self.assertEqual(selected[0][4], board.curses.A_REVERSE | board.curses.A_BOLD)
        self.assertIn("+0", selected[0][2])
        self.assertIn("-2", selected[0][2])
        self.assertIn("Passing", selected[0][2])
        striped = [call for call in calls if call[0] == 3]
        self.assertEqual(striped[0][4], 6 << 8)
        self.assertFalse(striped[0][2].startswith("●"))
        self.assertIn("+1,234,567 / -56", striped[0][2])
        self.assertTrue(any("Failing" in call[2] and call[4] == 9 << 8 for call in striped))
        self.assertTrue(any("+1,234,567" in call[2] and call[4] == 7 << 8 for call in striped))
        self.assertTrue(any("-56" in call[2] and call[4] == 9 << 8 for call in striped))
        header = next(value for row, _, value, *_ in calls if row == 1)
        self.assertNotIn("WORKTREE", header)
        self.assertEqual(striped[0][2].index("Second"), header.index("TITLE"))
        self.assertTrue(any(row == 8 and "PR URL: https://github.com/o/r/pull/1" in value
                            for row, _, value, *_ in calls))

    def test_missing_diff_counts_are_not_reported_as_zero(self):
        self.assertEqual(board.diff_count(None, "+"), "—")
        self.assertEqual(board.diff_count(0, "+"), "+0")

    def test_ci_status_summarizes_actions_and_commit_statuses(self):
        checks = lambda *values: {"statusCheckRollup": list(values)}
        self.assertEqual(board.ci_status(checks()), ("No checks", 0))
        self.assertEqual(board.ci_status({}), ("—", 0))
        self.assertEqual(board.ci_status(checks(
            {"status": "IN_PROGRESS", "conclusion": None}, {"state": "SUCCESS"})),
            ("Pending", 2))
        self.assertEqual(board.ci_status(checks(
            {"conclusion": "FAILURE", "status": "COMPLETED"}, {"state": "PENDING"})),
            ("Failing", 3))
        self.assertEqual(board.ci_status(checks({"conclusion": "SKIPPED"})), ("Skipped", 2))

    def test_stripe_color_pairs_keep_the_terminal_foreground(self):
        with mock.patch.object(board.curses, "has_colors", return_value=True), \
             mock.patch.object(board.curses, "start_color"), \
             mock.patch.object(board.curses, "use_default_colors"), \
             mock.patch.object(board.curses, "init_pair") as init_pair, \
             mock.patch.object(board.curses, "COLORS", 256, create=True), \
             mock.patch.object(board.curses, "COLOR_PAIRS", 256, create=True), \
             mock.patch.object(board, "stripe_background", return_value=254):
            self.assertTrue(board.init_colors())
        init_pair.assert_any_call(6, -1, 254)
        init_pair.assert_any_call(7, board.curses.COLOR_GREEN, 254)
        init_pair.assert_any_call(9, board.curses.COLOR_RED, 254)

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

    def test_pr_push_uses_the_repository_shape_returned_by_gh(self):
        row = core.PullRequest(Path("/tmp/project"), {"number": 3}, Path("/tmp/project"))
        details = {"state": "OPEN", "headRefName": "test-again",
                   "headRepository": {"name": "dotfiles", "nameWithOwner": "MaxHalford/dotfiles"},
                   "headRepositoryOwner": {"login": "MaxHalford"},
                   "url": "https://github.com/MaxHalford/dotfiles/pull/3"}
        with mock.patch.object(core, "run", side_effect=[json.dumps(details), ""]) as command:
            core.push_to_pr(row)
        self.assertEqual(command.call_args_list[1], mock.call(
            ["git", "push", "https://github.com/MaxHalford/dotfiles.git",
             "HEAD:refs/heads/test-again"], cwd=row.worktree, timeout=120, operation=None))

    def test_fork_pr_push_uses_the_pr_host(self):
        row = core.PullRequest(Path("/tmp/project"), {"number": 42}, Path("/tmp/pr"))
        details = {"state": "OPEN", "headRefName": "fix",
                   "headRepository": {"nameWithOwner": "contributor/fork"},
                   "url": "https://git.example.com/base/project/pull/42"}
        with mock.patch.object(core, "run", side_effect=[json.dumps(details), ""]) as command:
            core.push_to_pr(row)
        self.assertEqual(command.call_args_list[1].args[0],
                         ["git", "push", "https://git.example.com/contributor/fork.git",
                          "HEAD:refs/heads/fix"])

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

    def test_dirty_main_creates_branch_and_pr_in_the_same_worktree(self):
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
            original_run = core.run
            commands = []

            def command(argv, **kwargs):
                commands.append(argv)
                if argv[:3] == ["gh", "repo", "view"]:
                    return "main\n"
                if argv[:3] == ["gh", "pr", "create"]:
                    return "https://github.com/o/r/pull/1\n"
                return original_run(argv, **kwargs)

            with mock.patch.object(core, "run", side_effect=command):
                url = core.publish_from_main(core.Worktree(checkout, "main"), "topic/fix", "Fix it")
            self.assertEqual(url, "https://github.com/o/r/pull/1")
            self.assertEqual(git("branch", "--show-current", cwd=checkout), "topic/fix")
            self.assertEqual(git("rev-parse", "main", cwd=checkout), initial_main)
            self.assertEqual(git("status", "--porcelain", cwd=checkout), "")
            self.assertEqual((checkout / "base.txt").read_text(), "staged update\n")
            self.assertEqual((checkout / "new.txt").read_text(), "untracked file\n")
            self.assertEqual(git("rev-parse", "HEAD", cwd=checkout),
                             git("rev-parse", "refs/heads/topic/fix", cwd=origin))
            self.assertEqual(git("stash", "list", cwd=checkout), "")
            self.assertIn(["git", "switch", "-c", "topic/fix"], commands)
            self.assertFalse(any(argv[0] == os.environ.get("HERDR_BIN_PATH", "herdr") for argv in commands))

    def test_push_finds_project_venv_tool_for_stale_hook_path(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            checkout = repository(root)
            origin = root / "origin.git"
            git("init", "--bare", str(origin), cwd=root)
            git("remote", "add", "origin", str(origin), cwd=checkout)
            git("switch", "-c", "topic", cwd=checkout)
            hook = checkout / ".git" / "hooks" / "pre-push"
            hook.write_text("#!/bin/sh\nexec prek\n")
            hook.chmod(0o755)
            venv_bin = checkout / ".venv" / "bin"
            venv_bin.mkdir(parents=True)
            prek = venv_bin / "prek"
            prek.write_text("#!/bin/sh\nexit 0\n")
            prek.chmod(0o755)
            core.push(checkout, "topic")
            self.assertEqual(git("rev-parse", "topic", cwd=checkout),
                             git("rev-parse", "refs/heads/topic", cwd=origin))

    def test_push_error_surfaces_hook_failure(self):
        output = ".git/hooks/pre-push: exec: prek: not found\nerror: failed to push some refs to 'origin'"
        self.assertEqual(core.command_failure(["git", "push"], output),
                         ".git/hooks/pre-push: exec: prek: not found")

    def test_failed_branch_creation_keeps_main_changes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            checkout = repository(root)
            (checkout / "new.txt").write_text("keep this\n")
            original_run = core.run

            def command(argv, **kwargs):
                if argv[:3] == ["gh", "repo", "view"]:
                    return "main\n"
                if argv[:3] == ["git", "switch", "-c"]:
                    raise core.CommandError("Git could not create a branch")
                return original_run(argv, **kwargs)

            with mock.patch.object(core, "run", side_effect=command):
                with self.assertRaisesRegex(core.CommandError, "Git could not create"):
                    core.publish_from_main(core.Worktree(checkout, "main"), "topic/fix", "Fix it")
            self.assertEqual((checkout / "new.txt").read_text(), "keep this\n")
            self.assertEqual(git("stash", "list", cwd=checkout), "")
            self.assertEqual(git("branch", "--show-current", cwd=checkout), "main")

    def test_failed_pr_creation_keeps_the_new_branch_and_changes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            checkout = repository(root)
            origin = root / "origin.git"
            git("init", "--bare", str(origin), cwd=root)
            git("remote", "add", "origin", str(origin), cwd=checkout)
            (checkout / "new.txt").write_text("keep this\n")
            original_run = core.run

            def command(argv, **kwargs):
                if argv[:3] == ["gh", "repo", "view"]:
                    return "main\n"
                if argv[:3] == ["gh", "pr", "create"]:
                    raise core.CommandError("GitHub rejected the PR")
                return original_run(argv, **kwargs)

            with mock.patch.object(core, "run", side_effect=command):
                with self.assertRaisesRegex(core.CommandError, "still on branch topic/fix"):
                    core.publish_from_main(core.Worktree(checkout, "main"), "topic/fix", "Fix it")
            self.assertEqual(git("branch", "--show-current", cwd=checkout), "topic/fix")
            self.assertEqual((checkout / "new.txt").read_text(), "keep this\n")
            self.assertEqual(git("log", "-1", "--format=%s", cwd=checkout), "Fix it")

    def test_board_preserves_pr_selection_and_has_no_worktree_toggle(self):
        repo = Path("/tmp/project")
        current = core.Worktree(repo, "feature")
        first = core.PullRequest(repo, {"number": 1, "state": "OPEN"})
        second = core.PullRequest(repo, {"number": 2, "state": "OPEN"})
        app = board.ShiprApp(mock.Mock(), repo)
        app.items = [first, second]
        app.selected = 1
        updated = core.PullRequest(repo, {"number": 2, "state": "OPEN"})
        app.updates.put((core.BoardPage([updated, first], current, None, 2), None))
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
        publish.assert_called_once_with(app.current_tree)

    def test_main_publish_uses_same_worktree_flow(self):
        repo = Path("/tmp/project")
        tree = core.Worktree(repo, "main", is_base=True, dirty=True)
        app = board.ShiprApp(mock.Mock(), repo)
        with mock.patch.object(board, "confirm", return_value=True), \
             mock.patch.object(board, "has_changes", return_value=True), \
             mock.patch.object(board, "prompt", side_effect=["topic/fix", "Fix it"]), \
             mock.patch.object(app, "start_action") as start, \
             mock.patch.object(board, "publish_from_main", return_value="https://github.com/o/r/pull/42") as publish:
            app.publish_action(tree)
            work, success = start.call_args.args
            self.assertEqual(work(None), "https://github.com/o/r/pull/42")
        publish.assert_called_once_with(tree, "topic/fix", "Fix it", None)
        self.assertEqual(success("https://github.com/o/r/pull/42"),
                         ("created", "https://github.com/o/r/pull/42"))

    def test_p_pushes_when_current_branch_already_has_an_open_pr(self):
        repo = Path("/tmp/project")
        tree = core.Worktree(repo, "feature", pr={"number": 42, "state": "OPEN"})
        app = board.ShiprApp(mock.Mock(), repo)
        with mock.patch.object(board, "confirm", return_value=True) as confirm, \
             mock.patch.object(board, "has_changes", return_value=False), \
             mock.patch.object(app, "start_action") as start, \
             mock.patch.object(board, "publish", return_value="Changes pushed") as publish:
            app.publish_action(tree)
            work, success = start.call_args.args
            self.assertEqual(work(None), "Changes pushed")
        self.assertIn("push to PR #42", confirm.call_args.args[1])
        publish.assert_called_once_with(tree, "", False, None)
        self.assertEqual(success("Changes pushed"), ("done", "✓ Changes pushed"))

    def test_p_waits_for_pr_status_before_choosing_an_action(self):
        tree = core.Worktree(Path("/tmp/project"), "feature", pr_unavailable=True)
        app = board.ShiprApp(mock.Mock(), tree.path)
        with mock.patch.object(app, "start_action") as start:
            app.publish_action(tree)
        start.assert_not_called()
        self.assertIn("GitHub status is unavailable", app.message)

    def test_created_pr_url_remains_available_and_selects_new_row(self):
        repo = Path("/tmp/project")
        app = board.ShiprApp(mock.Mock(), repo)
        app.active_action = object()
        url = "https://github.com/o/r/pull/42"
        app.action_events.put(("created", url))
        with mock.patch.object(app, "start_refresh"):
            app.receive_actions()
        self.assertEqual(app.created_pr_url, url)
        self.assertEqual(app.pending_pr_number, 42)
        with mock.patch.object(board, "run") as command:
            app.handle_key(ord("o"))
        command.assert_called_once_with(["open", url], cwd=repo)
        app.updates.put((core.BoardPage([
            core.PullRequest(repo, {"number": 1, "state": "OPEN"}),
            core.PullRequest(repo, {"number": 42, "state": "OPEN", "url": url})],
            core.Worktree(repo, "topic/fix"), None, 2), None))
        app.receive_refresh()
        self.assertEqual(app.selected_item().pr["number"], 42)

    def test_pr_row_focus_uses_herdr_worktree_open(self):
        repo = Path("/tmp/project")
        path = Path("/tmp/pr")
        row = core.PullRequest(repo, {"number": 42, "headRefName": "feature"}, path)
        app = board.ShiprApp(mock.Mock(), repo)
        app.items = [row]
        with mock.patch.object(board, "open_herdr_worktree") as opened:
            self.assertTrue(app.handle_action("focus_worktree"))
        opened.assert_called_once_with(repo, path, "feature")

    def test_enter_focuses_or_opens_the_selected_pr_worktree(self):
        repo = Path("/tmp/project")
        app = board.ShiprApp(mock.Mock(), repo)
        present = core.PullRequest(repo, {"number": 1, "headRefName": "feature"},
                                   Path("/tmp/feature"))
        absent = core.PullRequest(repo, {"number": 2, "headRefName": "other"})
        app.items = [present, absent]
        with mock.patch.object(board, "find_pr_worktree", side_effect=[present.worktree, None]), \
             mock.patch.object(board, "open_herdr_worktree") as focus, \
             mock.patch.object(app, "start_action") as start:
            self.assertTrue(app.handle_key(10))
            app.selected = 1
            self.assertFalse(app.handle_key(board.curses.KEY_ENTER))
        focus.assert_called_once_with(repo, present.worktree, "feature")
        start.assert_called_once()

    def test_right_click_resolves_worktree_only_for_the_clicked_pr(self):
        repo = Path("/tmp/project")
        window = mock.Mock()
        window.getmaxyx.return_value = (12, 110)
        app = board.ShiprApp(window, repo)
        app.items = [core.PullRequest(repo, {"number": 1, "headRefName": "feature"})]
        with mock.patch.object(board.curses, "getmouse", return_value=(0, 5, 2, 0,
                                                                        board.curses.BUTTON3_PRESSED)), \
             mock.patch.object(board, "find_pr_worktree", return_value=Path("/tmp/feature")) as find:
            app.handle_mouse()
        find.assert_called_once()
        self.assertEqual(app.menu.actions[-1], ("Commit & push to PR", "update_pr"))

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
