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

```sh
brew install docker docker-compose zsh
brew install --cask anaconda iterm2 visual-studio-code
curl https://raw.githubusercontent.com/github/gitignore/master/Global/macOS.gitignore -o ~/.gitignore
```

For iterm2, go to `General > Preferences`, click on `Load preferences from a custom folder or URL`, and select the `iterm2` folder. Also set `Save changes` to `Automatically` so that changes are synced.

## General

```sh
sh -c "$(curl -fsSL https://raw.githubusercontent.com/robbyrussell/oh-my-zsh/master/tools/install.sh)"
python make_symlinks.py
```

For VSCode extensions:

```sh
./vscode/install-extensions.sh
```

Refresh the list whenever you install a new extension:

```sh
code --list-extensions > vscode/extensions.txt
```
