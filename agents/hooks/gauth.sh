#!/bin/zsh
# PreToolUse hook for Claude Code and Codex: before the agent runs a command
# that needs Google credentials, run gauth. The .zshrc wrappers only do this
# from a terminal, and dbt reads ADC without going through them.

# Codex may send the command as `cmd` and/or as an argv array.
cmd=$(jq -r '.tool_input | (.command // .cmd // empty) | if type == "array" then join(" ") else . end')
[[ "$cmd" =~ '(^|[^[:alnum:]_-])(dbt|bq|gsutil|gcloud)([^[:alnum:]_-]|$)' ]] || exit 0
# Don't block on login when the command is itself an auth command.
[[ "$cmd" =~ 'gcloud[[:space:]]+auth' ]] && exit 0

"${0:A:h}/../../bin/gauth" && exit 0
echo "gcloud login failed or timed out; ask the user to run: gcloud auth login --update-adc" >&2
exit 2
