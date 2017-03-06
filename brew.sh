#!/usr/bin/env bash

# Install command-line tools using Homebrew.

# Make sure we’re using the latest Homebrew.
brew update
brew tap caskroom/cask

# Upgrade any already-installed formulae.
brew upgrade

# Install necessary libraries
brew install git
brew install mysql
brew install npm
brew install ruby
brew install Caskroom/cask/java

# Remove outdated versions from the cellar.
brew cleanup
