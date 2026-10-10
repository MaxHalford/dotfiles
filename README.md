# dotfiles

Personal macOS setup for my shell, terminal, editors, and Herdr plugins.

## Setup

```sh
git clone https://github.com/MaxHalford/dotfiles
cd dotfiles
brew bundle
curl https://raw.githubusercontent.com/github/gitignore/master/Global/macOS.gitignore -o ~/.gitignore
sh -c "$(curl -fsSL https://raw.githubusercontent.com/robbyrussell/oh-my-zsh/master/tools/install.sh)"
python install.py
./herdr/sync-plugins.sh
./vscode/install-extensions.sh
```

`install.py` links the tracked configs through `~/dotfiles` and sets the global Git hooks path. Rerun it after adding a config, a skill, or moving this checkout.

## Layout

Each top-level folder holds one tool's config; `install.py` lists where each file is linked. A few folders are shared:

| Folder | Contents |
| --- | --- |
| `agents/` | Shared by Claude Code and Codex. Every skill in `agents/skills` is linked into both; hook scripts in `agents/hooks` are referenced from `claude/settings.json` and `codex/hooks.json`. |
| `bin/` | Scripts on `PATH`, such as `gauth`, which refreshes gcloud and ADC credentials with one browser login when they expire. |
| `git-hooks/` | Global Git hooks. `forward-local` keeps each repository's own hooks working. |
| `games/`, `nixos/`, `shortcuts/` | Configs that are installed by hand or only kept for reference, apart from the WoW fonts and Warcraft III keys. |

## Google Cloud login

The `bq`, `gcloud`, and `gsutil` shell wrappers run `gauth` first when called from a terminal. Claude Code and Codex run it through a `PreToolUse` hook before any command that uses `dbt`, `bq`, `gcloud`, or `gsutil`. Codex asks you to review new or changed hooks once before running them.

## Local configuration

Use `~/.secrets` for secrets and `~/.zshrc.local` for machine-specific shell settings; both are sourced by `.zshrc` when present.

### Corridor MCP

The Codex config includes [Corridor's MCP server](https://docs.corridor.dev/ide-setup/custom-mcp-servers), but it is currently disabled. To re-enable it, set `enabled = true` under `[mcp_servers.corridor]`, then restart Codex. It uses `CORRIDOR_API_TOKEN`; generate a token in [Corridor settings](https://app.corridor.dev/settings) and add `export CORRIDOR_API_TOKEN='your-token'` to `~/.secrets`.

When using the desktop app, launch it from a shell with `CORRIDOR_API_TOKEN` set so it inherits the token.

## macOS shortcuts

[Diary entry](shortcuts/Diary%20entry.shortcut) opens or creates today's Obsidian daily note in the `Max` vault. It contains one **Open URLs** action with `obsidian://daily?vault=Max`, which uses the vault's Daily notes settings for the folder, date format, and template. Obsidian's Daily notes core plugin must be enabled.

On a new Mac, double-click `shortcuts/Diary entry.shortcut` and choose **Add Shortcut**. Then search for **Diary entry** in Raycast and press `Enter`. Restart Raycast if the shortcut does not appear. Shortcuts are imported into the app's library rather than symlinked by `install.py`.

To update the tracked copy, edit **Diary entry** in Shortcuts, choose **File → Export**, select **Anyone**, and save over `shortcuts/Diary entry.shortcut`. The export includes the shortcut's action, not any diary contents. See Apple's [shortcut export instructions](https://support.apple.com/guide/shortcuts-mac/share-shortcuts-apdf01f8c054/mac).

## Herdr shortcuts

| Shortcut | Action |
| --- | --- |
| `Cmd+D` | Open Reviewr. |
| `Cmd+E` | Open the focused pane's current directory in VS Code. |
| `Cmd+G` | Open [shipr](herdr/shipr/README.md). |
| `Ctrl+B`, then `m` | Open Mermaid Preview for the focused Codex pane. |

### Mermaid previews

[Mermaid Preview](https://github.com/Volpestyle/herdr-plugin-mermaid-preview) watches the focused Codex session and renders complete `mermaid` code blocks in a separate Herdr tab. Press `Ctrl+B`, then `m` while focused on Codex to open it. Use `n`/`p` to browse diagrams, `+`/`-` to zoom, arrow keys to pan, and `q` to close the preview.

The plugin requires Node.js 22.12 or newer and a Kitty graphics terminal such as Ghostty. The tracked Herdr config already enables Kitty graphics, and `sync-plugins.sh` installs both the plugin and the Codex session integration. After changing keybindings, press `Ctrl+B`, then `Shift+R` in Herdr to reload the client's config; `herdr server reload-config` alone does not reload local client keybindings. If a preview waits for session identity, start a new Codex session. If it stays blank after first enabling graphics, detach and reattach the Herdr client.

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
