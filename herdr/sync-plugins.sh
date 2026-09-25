#!/bin/sh
set -eu

herdr plugin install persiyanov/herdr-reviewr --yes
herdr plugin install aarsh21/herdr-tab-title --yes
sh "$HOME/dotfiles/herdr/reviewr-theme.sh" auto
herdr plugin link "$HOME/dotfiles/herdr/shipr"
herdr integration install codex
if [ "${HERDR_ENV:-}" = 1 ]; then
    herdr plugin action invoke aarsh21.tab-title.start
fi
