# dotfiles

## Cloning

```sh
git config --global user.name MaxHalford
git config --global user.email maxhalford25@gmail.com
git clone https://github.com/MaxHalford/dotfiles
cd dotfiles
```

## Secret environment variables

Optionally, create a `~/.secrets` file.

```sh
export POETRY_HTTP_BASIC_PYPI_USERNAME=<keep_it_secret>
export POETRY_HTTP_BASIC_PYPI_PASSWORD=<keep_it_safe>
```

## MacOS specific

```sh
brew install docker docker-compose zsh
brew install --cask anaconda iterm2 visual-studio-code
curl https://raw.githubusercontent.com/github/gitignore/master/Global/macOS.gitignore -o ~/.gitignore
```

For iterm2, go to `General > Preferences`, click on `Load preferences from a custom folder or URL`, and select the `iterm2` folder. Also set `Save changes` to `Automatically` so that changes are synced.

## Linux specific

```sh
```

## General

```sh
sh -c "$(curl -fsSL https://raw.githubusercontent.com/robbyrussell/oh-my-zsh/master/tools/install.sh)"
python make_symlinks.py
```

For VSCode, you have to install extensions manually, as so:

```sh
while read extension; do
  code --install-extension $extension
done < vscode/extensions.txt
```

You'll have to update the list of extensions if you install a new one, like this:

```sh
code --list-extensions > vscode/extensions.txt
```
