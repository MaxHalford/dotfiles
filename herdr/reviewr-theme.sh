#!/bin/sh

set -eu

mode="${1:-auto}"
if [ "$mode" = auto ]; then
    if [ "$(defaults read -g AppleInterfaceStyle 2>/dev/null || true)" = Dark ]; then
        mode=dark
    else
        mode=light
    fi
fi

case "$mode" in
    light) source_config="$HOME/dotfiles/herdr/reviewr.toml" ;;
    dark) source_config="$HOME/dotfiles/herdr/reviewr-dark.toml" ;;
    *)
        printf 'Usage: %s [auto|light|dark]\n' "$0" >&2
        exit 2
        ;;
esac

[ -f "$source_config" ] || {
    printf 'Missing Reviewr configuration: %s\n' "$source_config" >&2
    exit 1
}

reviewr_config="$HOME/.config/herdr/plugins/config/persiyanov.reviewr/config.toml"
mkdir -p "$(dirname "$reviewr_config")"
ln -sfn "$source_config" "$reviewr_config"
printf 'Reviewr theme: %s\n' "$mode"
