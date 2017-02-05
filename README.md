# My dotfiles

## Installation

### Using Git and the bootstrap script

```sh
cd ~/projects/
git clone https://github.com/mathiasbynens/dotfiles.git && cd dotfiles && ./bootstrap.sh
```

To update, `cd` into the `dotfiles` folder and then:

```sh
./bootstrap.sh
```

### Sublime Text 3 settings

[Install Sublime Text 3](https://www.sublimetext.com/3) and then:

```sh
cd ~/Library/Application\ Support/Sublime\ Text\ 3
ln ~/projects/dotfiles/Sublime\ Text\ 3/Installed\ Packages ./Installed\ Packages
ln ~/projects/dotfiles/Sublime\ Text\ 3/Packages ./Packages
ln ~/projects/dotfiles/Sublime\ Text\ 3/Preferences.sublime-settings ./Packages/User/
```

### Sensible macOS defaults

When setting up a new Mac, you may want to set some sensible macOS defaults:

```sh
./.macos
```

### Install Homebrew formulae

When setting up a new Mac, you may want to install some common [Homebrew](http://brew.sh/) formulae (after installing Homebrew, of course):

```sh
./brew.sh
```
