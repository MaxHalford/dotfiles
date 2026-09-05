import os
from pathlib import Path
import shlex


HERE = Path(__file__).parent


def symlink(src: str, dst_dir: str):
    src_path = Path(src)
    dst = Path(dst_dir).expanduser() / src_path.name
    src_abs = (HERE / src_path).resolve()
    dst.parent.mkdir(parents=True, exist_ok=True)
    if dst.is_symlink() or (dst.exists() and not dst.is_dir()):
        dst.unlink()
    elif dst.is_dir():
        print(f"SKIP {dst} (existing non-symlink directory — remove manually to relink)")
        return
    dst.symlink_to(src_abs)
    print(f"{src} -> {dst}")


SYMLINKS = [
    ("vscode/settings.json", "~/Library/Application Support/Code/User"),
    ("vscode/keybindings.json", "~/Library/Application Support/Code/User"),
    ("vscode/snippets", "~/Library/Application Support/Code/User"),
    ("zed/settings.json", "~/Library/Application Support/Zed"),
    ("zed/keymap.json", "~/Library/Application Support/Zed"),
    ("ghostty/config.ghostty", "~/.config/ghostty"),
    ("ghostty/themes/Rose Pine Moon Clear Diffs", "~/.config/ghostty/themes"),
    ("herdr/config.toml", "~/.config/herdr"),
    (".ipython/profile_default/startup", "~/.ipython/profile_default"),
    (".zshrc", "~/"),
    (".p10k.zsh", "~/"),
    ("claude/settings.json", "~/.claude"),
    ("claude/statusline-command.sh", "~/.claude"),
    ("iterm2/com.max.iterm-clear-tab-color.plist", "~/Library/LaunchAgents"),
]

LAUNCH_AGENTS = [
    "iterm2/com.max.iterm-clear-tab-color.plist",
]


def reload_launch_agent(plist_rel: str):
    plist = (HERE / plist_rel).resolve()
    os.system(f"launchctl unload {shlex.quote(str(plist))} 2>/dev/null")
    os.system(f"launchctl load {shlex.quote(str(plist))}")
    print(f"launchctl reloaded {plist.name}")


if __name__ == "__main__":
    for src, dst_dir in SYMLINKS:
        symlink(src, dst_dir)
    for plist in LAUNCH_AGENTS:
        reload_launch_agent(plist)
