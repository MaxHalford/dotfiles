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
- `Cmd+G`: Open shipr's table of the 50 most recent open PRs. Right-click a PR to open it in GitHub, open or focus its Herdr worktree, or commit and push changes to its head branch (including a fork when you have write access). Press `p` to commit, push, and create a PR from the worktree that opened shipr, or `u` to commit and push that worktree. Press `r` to refresh and `q` to close or cancel an active command.

From a dirty default branch, `p` asks for a branch and commit message, creates a Herdr worktree at the current commit, moves the changes there, creates the PR, and focuses the new workspace. The original worktree stays on the default branch. You can also start in a branch worktree created by Herdr and use `p` to publish it. Opening an existing PR creates a separate Herdr worktree from the PR head. Pushing a PR checks its current head repository and branch again before sending commits.
- `Ctrl+B`, then `m`: Open Mermaid preview.

## Editors

Refresh the tracked VS Code extension list with `code --list-extensions > vscode/extensions.txt`. Zed settings are linked by `make_symlinks.py`; install a Rosé Pine theme extension in Zed to match VS Code's Dawn and Moon themes.
