# My dotfiles

## Installation

### Using Git and the bootstrap script

You can clone the repository wherever you want. (I like to keep it in `~/projects/dotfiles`, with `~/dotfiles` as a symlink.) The bootstrapper script will pull in the latest version and copy the files to your home folder.

```sh
cd projects
git clone https://github.com/mathiasbynens/dotfiles.git && cd dotfiles && source bootstrap.sh
```

To update, `cd` into your local `dotfiles` repository and then:

```sh
source bootstrap.sh
```

### Sublime Text 3 settings

[Install Sublime Text 3](https://www.sublimetext.com/3) and then:

```sh
cd ~/Library/Application\ Support/Sublime\ Text\ 3
ln -s ~/projects/dotfiles/Sublime\ Text\ 3/Installed\ Packages ./Installed\ Packages
ln -s ~/projects/dotfiles/Sublime\ Text\ 3/Packages ./Packages
ln -s ~/projects/dotfiles/Sublime\ Text\ 3/Preferences.sublime-settings ./Packages/User
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
