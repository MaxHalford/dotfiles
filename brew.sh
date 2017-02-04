#!/usr/bin/env bash

# Install command-line tools using Homebrew.

# Make sure we’re using the latest Homebrew.
brew update

# Upgrade any already-installed formulae.
brew upgrade

# Install necessary libraries
brew install git
brew install mysql

# Remove outdated versions from the cellar.
brew cleanup
