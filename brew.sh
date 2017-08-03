#!/usr/bin/env bash

# Install command-line tools using Homebrew

# Make sure we’re using the latest Homebrew
brew update
brew tap caskroom/cask

# Upgrade any already-installed formulae
brew upgrade

# Install necessary libraries
brew install git
brew install mysql
brew install npm
brew install ruby
brew install Caskroom/cask/java
brew install zsh

# No formulas but needed
sh -c "$(curl -fsSL https://raw.githubusercontent.com/robbyrussell/oh-my-zsh/master/tools/install.sh)"

# Remove outdated versions from the cellar
brew cleanup
