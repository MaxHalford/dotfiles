# My dotfiles

## Installation

### Initial required software

- [Homebrew](http://brew.sh/)
- [iterm2](https://www.iterm2.com/index.html)

### Install Homebrew formulae

```sh
./brew.sh
```

### Using Git and the bootstrap script

```sh
cd ~/projects/
git clone https://github.com/MaxHalford/dotfiles && cd dotfiles && ./bootstrap.sh
```

To update, `cd` into the `dotfiles` folder and then:

```sh
./bootstrap.sh
```

### Sublime Text 3 settings

[Install Sublime Text 3](https://www.sublimetext.com/3) and then:

```sh
ln -s sublime/ ~/Library/Application\ Support/Sublime\ Text\ 3/Packages/User
```

### iterm2 settings

- Open iterm2
- Go to <kbd>Preferences</kbd> > <kbd>General</kbd>
- In the preferences part click on <kbd>Browse</kbd> and choose the `iterm2_profile/` folder

### Sensible macOS defaults

```sh
./.macos
```
