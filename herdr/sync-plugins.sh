#!/bin/sh
set -eu

herdr plugin install Volpestyle/herdr-plugin-mermaid-preview --yes
herdr plugin install persiyanov/herdr-reviewr --yes
reviewr_config="$HOME/.config/herdr/plugins/config/persiyanov.reviewr/config.toml"
mkdir -p "$(dirname "$reviewr_config")"
ln -sfn "$HOME/dotfiles/herdr/reviewr.toml" "$reviewr_config"
herdr plugin link "$HOME/dotfiles/herdr/shipr"
herdr integration install codex
