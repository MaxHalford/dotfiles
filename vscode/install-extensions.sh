#!/usr/bin/env bash
# Install all VSCode extensions listed in extensions.txt.
# Refresh the list with: code --list-extensions > vscode/extensions.txt
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
while read -r extension; do
  [ -z "$extension" ] && continue
  code --install-extension "$extension"
done < "$HERE/extensions.txt"
