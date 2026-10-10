#!/bin/sh
set -eu

herdr plugin install persiyanov/herdr-reviewr --yes
herdr plugin install aarsh21/herdr-tab-title --yes
herdr plugin install Volpestyle/herdr-plugin-mermaid-preview --yes
sh "$HOME/dotfiles/herdr/reviewr-theme.sh" auto
herdr plugin link "$HOME/dotfiles/herdr/shipr"
herdr integration install codex
herdr integration install claude

# Teach both agents to drive Herdr, matching the installed version.
for skills in "$HOME/.claude/skills" "$HOME/.codex/skills"; do
    mkdir -p "$skills/herdr"
    herdr --skill > "$skills/herdr/SKILL.md"
done

# .zshrc adds ~/.zfunc to fpath before compinit.
mkdir -p "$HOME/.zfunc"
herdr completion zsh > "$HOME/.zfunc/_herdr"
if [ "${HERDR_ENV:-}" = 1 ]; then
    herdr plugin action invoke aarsh21.tab-title.start
fi
