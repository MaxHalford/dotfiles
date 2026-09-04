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

The symlink script also installs the Ghostty configuration. It maps
Option+Delete to backward word deletion and Option+R to fzf history search;
Zsh maps Tab to normal completion.

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
