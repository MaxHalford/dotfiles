#!/bin/sh

set -eu

if [ -z "${HERDR_SOCKET_PATH:-}" ]; then
    printf 'Reviewr toggle must run from Herdr.\n' >&2
    exit 1
fi
[ -n "${HERDR_ACTIVE_WORKSPACE_ID:-}" ] || {
    printf 'Reviewr toggle needs an active Herdr workspace.\n' >&2
    exit 1
}

sh "$HOME/dotfiles/herdr/reviewr-theme.sh" auto

exec "${HERDR_BIN_PATH:-herdr}" plugin action invoke persiyanov.reviewr.toggle
