#!/bin/sh
set -eu

herdr plugin install Volpestyle/herdr-plugin-mermaid-preview --yes
herdr plugin link "$HOME/dotfiles/herdr/worktree-prs"
herdr integration install codex
