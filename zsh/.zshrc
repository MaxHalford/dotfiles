# p10k instant prompt (must stay at top)
if [[ -r "${XDG_CACHE_HOME:-$HOME/.cache}/p10k-instant-prompt-${(%):-%n}.zsh" ]]; then
  source "${XDG_CACHE_HOME:-$HOME/.cache}/p10k-instant-prompt-${(%):-%n}.zsh"
fi

export GPG_TTY=$(tty)
export CUA_REPL_ENABLED_SURFACES="browser,computer"

# Restore passphrase-protected SSH keys saved in the macOS Keychain for Git signing.
if [[ "$OSTYPE" == darwin* ]]; then
  /usr/bin/ssh-add --apple-load-keychain >/dev/null 2>&1
fi

# Oh-my-zsh
export ZSH="$HOME/.oh-my-zsh"
ZSH_AUTOSUGGEST_HIGHLIGHT_STYLE='fg=5'
ZSH_THEME="powerlevel10k/powerlevel10k"
DISABLE_UNTRACKED_FILES_DIRTY="true"
plugins=(
    git
    z
    zsh-autosuggestions
    bgnotify
    zsh-syntax-highlighting
)
source $ZSH/oh-my-zsh.sh

# Keep Tab as regular shell completion.
bindkey -M emacs '^I' expand-or-complete
bindkey -M viins '^I' expand-or-complete

# Fix slow paste with zsh-syntax-highlighting
pasteinit() {
  OLD_SELF_INSERT=${${(s.:.)widgets[self-insert]}[2,3]}
  zle -N self-insert url-quote-magic
}
pastefinish() {
  zle -N self-insert $OLD_SELF_INSERT
}
zstyle :bracketed-paste-magic paste-init pasteinit
zstyle :bracketed-paste-magic paste-finish pastefinish

# Completions
zstyle ':completion:*' menu select
fpath+=~/.zfunc

# pyenv
export PYENV_ROOT="$HOME/.pyenv"
command -v pyenv >/dev/null || export PATH="$PYENV_ROOT/bin:$PATH"
eval "$(pyenv init -)"
export PYENV_VIRTUALENV_DISABLE_PROMPT=1

# nvm (lazy-loaded)
export NVM_DIR="${XDG_CONFIG_HOME:-$HOME}/.nvm"
nvm() {
  unfunction nvm
  [ -s "$NVM_DIR/nvm.sh" ] && . "$NVM_DIR/nvm.sh"
  nvm "$@"
}

# PATH
export PATH="$HOME/.local/bin:$PATH"
export PATH="$HOME/dotfiles/bin:$PATH"
export PATH="/Applications/Postgres.app/Contents/Versions/latest/bin:$PATH"
export PATH="/opt/homebrew/opt/openjdk/bin:$PATH"

# bun
export BUN_INSTALL="$HOME/.bun"
export PATH="$BUN_INSTALL/bin:$PATH"
[ -s "$HOME/.bun/_bun" ] && source "$HOME/.bun/_bun"

# opencode
export PATH="$HOME/.opencode/bin:$PATH"

# Secrets
[ -f ~/.secrets ] && source ~/.secrets

# Zinit (fzf-history-search)
if [[ ! -f $HOME/.local/share/zinit/zinit.git/zinit.zsh ]]; then
    print -P "%F{33} %F{220}Installing %F{33}ZDHARMA-CONTINUUM%F{220} Initiative Plugin Manager (%F{33}zdharma-continuum/zinit%F{220})…%f"
    command mkdir -p "$HOME/.local/share/zinit" && command chmod g-rwX "$HOME/.local/share/zinit"
    command git clone https://github.com/zdharma-continuum/zinit "$HOME/.local/share/zinit/zinit.git" && \
        print -P "%F{33} %F{34}Installation successful.%f%b" || \
        print -P "%F{160} The clone has failed.%f%b"
fi
source "$HOME/.local/share/zinit/zinit.git/zinit.zsh"

autoload -Uz _zinit
(( ${+_comps} )) && _comps[zinit]=_zinit
zinit ice lucid wait'0'
zinit light joshskidmore/zsh-fzf-history-search

if type brew &>/dev/null; then
    FPATH="$(brew --prefix)/share/zsh/site-functions:${FPATH}"
fi
autoload -Uz compinit
compinit

# p10k config
[[ ! -f ~/.p10k.zsh ]] || source ~/.p10k.zsh

# Herdr doesn't answer background-color queries, so Claude's "auto" theme
# falls back to dark. Follow the macOS appearance instead, like Ghostty does, and
# use the ANSI variants so colors come from the Ghostty (Rosé Pine) palette.
claude() {
  local theme=light-ansi
  [[ "$(defaults read -g AppleInterfaceStyle 2>/dev/null)" == Dark ]] && theme=dark-ansi
  command claude --enable-auto-mode --settings "{\"theme\":\"$theme\"}" "$@"
}

# Log in first when needed (see bin/gauth), but only from a terminal so scripts
# never block on a browser. Agents get the same check through a PreToolUse hook.
_gauth_then() { [[ -t 1 ]] && gauth; command "$@"; }
bq() { _gauth_then bq "$@"; }
gsutil() { _gauth_then gsutil "$@"; }
gcloud() {
  case "$1" in
    auth|config|components|version|help|"") command gcloud "$@" ;;
    *) _gauth_then gcloud "$@" ;;
  esac
}

# Host-specific overrides (machine-injected installers, work-only env, etc.)
[ -f ~/.zshrc.local ] && source ~/.zshrc.local
