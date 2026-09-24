# dotfiles

Personal macOS setup for my shell, terminal, editors, and Herdr plugins.

## Setup

```sh
git clone https://github.com/MaxHalford/dotfiles
cd dotfiles
brew bundle
curl https://raw.githubusercontent.com/github/gitignore/master/Global/macOS.gitignore -o ~/.gitignore
sh -c "$(curl -fsSL https://raw.githubusercontent.com/robbyrussell/oh-my-zsh/master/tools/install.sh)"
python make_symlinks.py
./herdr/sync-plugins.sh
./vscode/install-extensions.sh
```

`make_symlinks.py` links the tracked configs through `~/dotfiles`. Rerun it if this checkout moves. For iTerm2, load preferences from the `iterm2` folder and set saving to Automatic.

## Local configuration

Use `~/.secrets` for secrets and `~/.zshrc.local` for machine-specific shell settings; both are sourced by `.zshrc` when present.

Ghostty and VS Code use Rosé Pine Dawn in light mode and Rosé Pine Moon in dark mode. Herdr follows Ghostty's palette. Reload Ghostty after keybinding changes with `Cmd+Shift+,`.

## Herdr shortcuts

- `Cmd+D`: Open Reviewr. Press `s` to send comments to the agent or `q` to close.
- `Cmd+G`: Open shipr's PR table. It loads 25 PRs first and fetches more as you navigate toward the end. The first column shows time since the latest commit, and loaded PRs are sorted newest first. Press `Enter` to focus or open the selected PR's Herdr worktree, `p` to publish or push from the current worktree, `o` to open the PR in GitHub, `r` to refresh, and `q` to close or cancel an active command. Right-click a PR for more actions.

From a dirty default branch, `p` asks for a branch and commit message, creates the branch in the current worktree, commits and pushes the changes, and opens the PR. The current pane and Codex session stay in place. Shipr shows the PR URL after creation and selects its row on refresh. You can also use `p` from an existing feature branch. Opening an existing PR creates a separate Herdr worktree from the PR head. Pushing a PR checks its current head repository and branch again before sending commits.
- `Ctrl+B`, then `m`: Open Mermaid preview.

## Editors

Refresh the tracked VS Code extension list with `code --list-extensions > vscode/extensions.txt`. Zed settings are linked by `make_symlinks.py`; install a Rosé Pine theme extension in Zed to match VS Code's Dawn and Moon themes.
