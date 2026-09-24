import argparse
import os
from pathlib import Path
import shlex
import tempfile


HERE = Path(__file__).parent
ANCHOR = Path.home() / "dotfiles"


def link_checkout():
    checkout = HERE.resolve()
    if ANCHOR.is_symlink():
        if ANCHOR.resolve() == checkout:
            return
        ANCHOR.unlink()
    elif ANCHOR.exists():
        raise RuntimeError(f"{ANCHOR} exists and is not a symlink")
    ANCHOR.symlink_to(checkout, target_is_directory=True)
    print(f"{ANCHOR} -> {checkout}")


def symlink(src: str, dst_dir: str, dst_name=None):
    src_path = Path(src)
    dst = Path(dst_dir).expanduser() / (dst_name or src_path.name)
    if not (HERE / src_path).exists():
        raise FileNotFoundError(HERE / src_path)
    src_abs = ANCHOR / src_path
    dst.parent.mkdir(parents=True, exist_ok=True)
    if dst.is_symlink():
        if dst.readlink() == src_abs:
            return
        dst.unlink()
    elif dst.exists() and not dst.is_dir():
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
    ("herdr/config.toml", "~/.config/herdr"),
    (".ipython/profile_default/startup", "~/.ipython/profile_default"),
    ("codex/AGENTS.md", "~/.codex"),
    ("codex/config.toml", "~/.codex"),
    (".zshrc", "~/"),
    (".p10k.zsh", "~/"),
    ("claude/settings.json", "~/.claude"),
    ("claude/statusline-command.sh", "~/.claude"),
    ("iterm2/com.max.iterm-clear-tab-color.plist", "~/Library/LaunchAgents"),
    ("warcraft3/CustomKeys.txt", "~/Library/Application Support/Blizzard/Warcraft III/CustomKeyBindings"),
]

LAUNCH_AGENTS = [
    "iterm2/com.max.iterm-clear-tab-color.plist",
]


def link_wow_fonts():
    root = Path(os.environ.get("WOW_ROOT", "/Applications/World of Warcraft")).expanduser()
    src = "wow/fonts/DorisPP.ttf"
    names = ("ARIALN.ttf", "FRIZQT__.ttf", "MORPHEUS.ttf", "skurri.ttf")
    for client in sorted(root.glob("_*_")):
        if not client.is_dir():
            continue
        fonts = client / "Fonts"
        changed = [
            fonts / name for name in names
            if not (fonts / name).is_symlink()
            or (fonts / name).readlink() != ANCHOR / src
        ]
        if not changed:
            continue
        if not (HERE / src).is_file():
            raise FileNotFoundError(HERE / src)
        if any(path.is_dir() for path in changed):
            raise RuntimeError(f"Expected font files, found a directory in {fonts}")
        fonts.mkdir(parents=True, exist_ok=True)
        # Preserve previous overrides and GPU caches; WoW rebuilds caches on launch.
        previous = [path for path in changed if path.exists() or path.is_symlink()]
        previous += [
            path for path in fonts.iterdir()
            if path.is_file() and path.suffix in (".slug", ".slugo")
        ]
        if previous:
            backup = Path(tempfile.mkdtemp(prefix=".dotfiles-backup-", dir=fonts))
            for path in previous:
                path.rename(backup / path.name)
            print(f"Backed up previous WoW fonts and caches to {backup}")
        for name in names:
            symlink(src, str(fonts), name)


def reload_launch_agent(plist_rel: str):
    plist = (HERE / plist_rel).resolve()
    os.system(f"launchctl unload {shlex.quote(str(plist))} 2>/dev/null")
    os.system(f"launchctl load {shlex.quote(str(plist))}")
    print(f"launchctl reloaded {plist.name}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--wow-only", action="store_true", help="Only install WoW fonts")
    args = parser.parse_args()
    link_checkout()
    if not args.wow_only:
        for src, dst_dir in SYMLINKS:
            symlink(src, dst_dir)
        for plist in LAUNCH_AGENTS:
            reload_launch_agent(plist)
    link_wow_fonts()
