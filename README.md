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

Codex starts with `FORCE_COLOR=1` so its prompt stays readable across appearance changes, with reduced color detail.

## Herdr shortcuts

- `Cmd+D`: Open Reviewr. Press `s` to send comments to the agent or `q` to close.
- `Cmd+G`: Open shipr. Right-click a worktree to commit and push or create a PR; press `q` to close or cancel an active command.
- `Ctrl+B`, then `m`: Open Mermaid preview.

## Editors

Refresh the tracked VS Code extension list with `code --list-extensions > vscode/extensions.txt`. Zed settings are linked by `make_symlinks.py`; install a Rosé Pine theme extension in Zed to match VS Code's Dawn and Moon themes.
