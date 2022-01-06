# dotfiles

## Cloning

```sh
git config --global user.name MaxHalford
git config --global user.email maxhalford25@gmail.com
git clone https://github.com/MaxHalford/dotfiles
cd dotfiles
```

## MacOS specific

```sh
brew install docker docker-compose zsh
brew install --cask anaconda iterm2 visual-studio-code
```

For iterm2, go to `General > Preferences`, click on `Load preferences from a custom folder or URL`, and select the `iterm2_profile` folder. Also set `Save changes` to `Automatically` so that changes are synced.

## Linux specific

```sh
```

## General

```sh
sh -c "$(curl -fsSL https://raw.githubusercontent.com/robbyrussell/oh-my-zsh/master/tools/install.sh)"
python make_symlinks.py
```
