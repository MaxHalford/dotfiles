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

## Herdr shortcuts

| Shortcut | Action |
| --- | --- |
| `Cmd+D` | Open Reviewr. |
| `Cmd+E` | Open the focused pane's current directory in VS Code. |
| `Cmd+G` | Open [shipr](herdr/shipr/README.md). |

### Tab titles

The Herdr Tab Title plugin names tabs after the focused pane's foreground program, such as `codex` or `hugo`. At an idle shell, it uses the current directory name. Manually renamed tabs keep their names.

### Reviewr

When you press `Cmd+D`, Reviewr selects Rosé Pine Dawn in macOS light mode or Rosé Pine in dark mode before opening. An already open pane keeps its theme when macOS appearance changes; close and reopen it with `Cmd+D` to pick up the new theme.

| Key | Action |
| --- | --- |
| `e` | Open the selected file or diff line in VS Code. |
| `q` | Close Reviewr. |

### Shipr

| Key | Action |
| --- | --- |
| `p` | Publish changes or push to the current PR. |
| `o` | Open the PR in the browser. |
| `r` | Refresh pull requests. |
| `q` | Close shipr or cancel the current action. |
| `Enter` | Focus or create the selected PR's worktree. |
