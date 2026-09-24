# dotfiles

## Cloning

```sh
git clone https://github.com/MaxHalford/dotfiles
cd dotfiles
```

## Secret environment variables

Optionally, create a `~/.secrets` file.

```sh
export POETRY_HTTP_BASIC_PYPI_USERNAME=<keep_it_secret>
export POETRY_HTTP_BASIC_PYPI_PASSWORD=<keep_it_safe>
```

## Host-specific config

`.zshrc` sources `~/.zshrc.local` at the end if it exists. Put machine-specific env vars, installer-injected blocks (Aikido, safe-chain, etc.), and work-only PATH entries there — not in the tracked `.zshrc`.

## MacOS specific

Install the packages and applications declared in `Brewfile`:

```sh
brew bundle
curl https://raw.githubusercontent.com/github/gitignore/master/Global/macOS.gitignore -o ~/.gitignore
```

When adding or removing software, update the committed `Brewfile`:

```sh
brew bundle add <formula>
brew bundle add --cask <application>
brew bundle remove <formula>
brew bundle remove --cask <application>
brew bundle check
```

For iterm2, go to `General > Preferences`, click on `Load preferences from a custom folder or URL`, and select the `iterm2` folder. Also set `Save changes` to `Automatically` so that changes are synced.

## General

```sh
sh -c "$(curl -fsSL https://raw.githubusercontent.com/robbyrussell/oh-my-zsh/master/tools/install.sh)"
python make_symlinks.py
```

The script creates `~/dotfiles` as a stable link to this checkout and points
installed config links through it. If you move the checkout, run the script
again from its new location to update the anchor and installed links.

The symlink script also installs the Ghostty configuration. It maps Option+Delete to backward word deletion and Option+R to fzf history search; Zsh maps Tab to normal completion. Ghostty follows the macOS appearance with its bundled Rosé Pine Dawn and Rosé Pine Moon themes. Powerlevel10k uses their ANSI surface/text pair for readable segments in both modes.

Herdr uses its `terminal` theme to follow Ghostty's palette. Ghostty uses Rosé Pine Dawn in light mode and Rosé Pine Moon in dark mode, matching VS Code's preferred themes.

Codex CLI 0.156.1 caches its terminal colors at startup, so its prompt and diff backgrounds can lag after macOS changes appearance. The Zsh `codex` function starts Codex with `FORCE_COLOR=1`; this makes the prompt use the terminal's default background as it changes, at the cost of less detailed Codex colors. Restart an existing Codex session to apply the workaround. Herdr 0.9.1 can also keep reporting the old terminal background to programs inside its panes. The symlink script installs `codex/AGENTS.md` as global Codex guidance at `~/.codex/AGENTS.md`; it points to the local `~/.codex/RTK.md` instructions.

Install or update the tracked Herdr plugins and agent integrations:

```sh
./herdr/sync-plugins.sh
```

The Mermaid preview opens with `Ctrl+B`, then `m`.
Press `Cmd+D` in Herdr to open Reviewr over the current tab. Click a changed file to browse its diff, then click or drag its line-number gutter to comment. Type the comment and press Enter to save it; press `s` to send the comments to the agent, or `q` to close the review. The view includes branch commits and uncommitted changes, and opens only when requested.
After changing Ghostty keybindings in this checkout, press `Cmd+Shift+,` in Ghostty to reload them; Ghostty does not reload the file automatically.
Open Shipr with `Cmd+G`. It refreshes every 30 seconds without blocking input. Right-click a worktree row to create a PR or push; if the worktree has changes, the selected action commits all changes first. Clean worktrees use their existing commits. During publishing, the popup shows the current step, elapsed time, and output from Git hooks and GitHub; `q` cancels the active command and closes when it stops. After cancelling, check Git status and PRs before retrying because earlier steps may have finished. Click empty space inside the popup, or press `q`, to close while idle. Press `r` to refresh. PR statuses use green for open, yellow for pending checks or reviews, red for failing checks or requested changes, magenta for drafts, and blue for merged PRs.
Creating a PR from the repository's default branch prompts for a new branch name, then creates that branch, commits, pushes, and opens the PR. The default branch stays at its original commit. The confirmation prompt defaults to yes; press Enter to continue or `n` to cancel. In the text prompts, Backspace, Delete, Option+Delete, and the arrow keys work for editing.
The first column shows the time since each worktree's last commit. By default, the table shows the current worktree and worktrees with changes, commits beyond the default branch, or an open PR. Press `a` to show all registered worktrees, including quiet or unavailable ones, and `a` again to restore the relevant view.
Herdr 0.9.0 does not send clicks outside a plugin popup to the plugin, so closing by clicking beyond the popup border requires a Herdr change.

For VSCode extensions:

```sh
./vscode/install-extensions.sh
```

Refresh the list whenever you install a new extension:

```sh
code --list-extensions > vscode/extensions.txt
```

## Zed

`make_symlinks.py` links `zed/settings.json` and `zed/keymap.json` into
`~/Library/Application Support/Zed`. The Zed configuration carries over the
portable VS Code preferences: a system-aware theme, Rec Mono editor font, save
behavior, editor layout, wrapping, and Python/Rust language-specific
format-on-save settings.

The bundled Zed themes are used as a valid fallback. Install a Rosé Pine Zed
theme extension and select `Rosé Pine Dawn` / `Rosé Pine Moon` in Zed to restore
the VS Code color scheme. Zed extensions provide language servers, formatters,
notebooks, themes, and AI features separately, so VS Code extension-specific
preferences are intentionally not included.
