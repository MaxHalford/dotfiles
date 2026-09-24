# shipr

Shipr is a Herdr popup for browsing GitHub pull requests and working with them in Herdr worktrees. It uses the current workspace repository and keeps publishing on the current worktree so the terminal and agent session stay in place.

## Requirements

- macOS and Herdr 0.9.0 or newer.
- Python 3.9 or newer, Git, and the GitHub CLI (`gh`) on `PATH`.
- GitHub CLI authentication for the repository (`gh auth login`).

## Install

From this repository, link the plugin for local development:

```sh
herdr plugin link /path/to/dotfiles/herdr/shipr
```

Once published on GitHub, install the plugin from its repository subdirectory:

```sh
herdr plugin install MaxHalford/dotfiles/herdr/shipr
```

Bind the `dev.max.worktree-prs.open` action in your Herdr configuration, or invoke it with `herdr plugin action invoke dev.max.worktree-prs.open`.

## Use

| Key | Action |
| --- | --- |
| `↑` / `↓`, `j` / `k` | Select a PR; loading another page starts near the end. |
| `←` / `→`, `Page Up` / `Page Down` | Move one visible page through the table; more PRs load at the end. |
| `Home` / `End` | Jump to the first or last loaded PR. |
| `Enter` | Focus the PR's Herdr worktree, or create a separate worktree from its head if needed. |
| `p` | Publish or push changes from the current worktree. |
| `o` | Open the selected or newly created PR in the browser. |
| `r` | Refresh the loaded pages. |
| `q` | Close the popup, or cancel the active command and close. |
| Right-click | Show PR actions, including commit and push when its worktree is open. |

### Publishing with `p`

| Current worktree when pressing `p` | Result |
| --- | --- |
| Dirty default branch | Ask for a branch name and commit message, create the branch in this worktree, commit, push, and open a PR. The pane and agent session stay in place; shipr shows the PR URL and selects its row after refresh. |
| Feature branch without an open PR | Commit any changes, push the branch, and open a PR. |
| Branch with an open PR | Commit any changes and push to the PR's current head repository and branch. |

For commits and pushes, shipr includes the current worktree's `.venv/bin` on `PATH` so Git hooks can find tools installed in that environment.

The first load requests 25 open PRs and their latest commit time, diff size, review state, and aggregate CI state. Worktree matching runs only when you press `Enter` or right-click a PR. More PRs load as you navigate toward the end. Fetched PRs are sorted by latest commit, newest first; additional pages can move rows into a new position. The source pages use GitHub's PR update order, so a PR outside the loaded pages is not part of the sort yet. The table refreshes every 60 seconds while open.

## Test

```sh
python3 -m unittest discover -s herdr/shipr -p 'test_*.py' -q
```

## Publishing

Herdr supports installing a plugin from a GitHub repository subdirectory, so this manifest can stay here. Before a public release, choose a repository license and update the manifest version. Add the `herdr-plugin` GitHub topic if you want the plugin to appear in the [Herdr marketplace](https://herdr.dev/docs/marketplace/).
