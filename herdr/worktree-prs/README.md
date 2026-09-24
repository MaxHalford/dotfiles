# shipr

Shipr is a Herdr popup for browsing GitHub pull requests and working with them in Herdr worktrees. It uses the current workspace repository and keeps publishing on the current worktree so the terminal and agent session stay in place.

## Requirements

- macOS and Herdr 0.9.0 or newer.
- Python 3.9 or newer, Git, and the GitHub CLI (`gh`) on `PATH`.
- GitHub CLI authentication for the repository (`gh auth login`).

## Install

From this repository, link the plugin for local development:

```sh
herdr plugin link /path/to/dotfiles/herdr/worktree-prs
```

Once published on GitHub, install the plugin from its repository subdirectory:

```sh
herdr plugin install MaxHalford/dotfiles/herdr/worktree-prs
```

Bind the `dev.max.worktree-prs.open` action in your Herdr configuration, or invoke it with `herdr plugin action invoke dev.max.worktree-prs.open`.

## Use

| Key | Action |
| --- | --- |
| `↑` / `↓`, `j` / `k` | Select a PR; loading another page starts near the end. |
| `Page Up` / `Page Down`, `Home` / `End` | Move through the table. |
| `Enter` | Focus the PR's Herdr worktree, or create one from its head if needed. |
| `p` | Publish changes from the current worktree, or commit and push to its open PR. |
| `o` | Open the selected or newly created PR in the browser. |
| `r` | Refresh the loaded pages. |
| `q` | Close the popup, or cancel the active command and close. |

Right-click a PR for its actions, including commit and push when a matching worktree exists. From a dirty default branch, `p` asks for a branch and commit message, then creates the branch in the same worktree, commits, pushes, and opens a PR.

The first load requests 25 open PRs and their latest commit time, diff size, review state, and aggregate CI state. Worktree matching runs only when you press `Enter` or right-click a PR. More PRs load as you navigate toward the end. Fetched PRs are sorted by latest commit, newest first; additional pages can move rows into a new position. The source pages use GitHub's PR update order, so a PR outside the loaded pages is not part of the sort yet. The table refreshes every 60 seconds while open.

## Test

```sh
python3 -m unittest discover -s herdr/worktree-prs -p 'test_*.py' -q
```

## Publishing

Herdr supports installing a plugin from a GitHub repository subdirectory, so this manifest can stay here. Before a public release, choose a repository license and update the manifest version. Add the `herdr-plugin` GitHub topic if you want the plugin to appear in the [Herdr marketplace](https://herdr.dev/docs/marketplace/).
