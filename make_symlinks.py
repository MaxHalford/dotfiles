import argparse
import os
from pathlib import Path
import shlex
import subprocess


parser = argparse.ArgumentParser()
parser.add_argument("--dry", dest="dry", action="store_true")
parser.set_defaults(dry=False)
args = parser.parse_args()


HERE = Path(__file__).parent


def symlink(src: str, dst_dir: str):
    src = Path(src)
    os.system(f"ln -sf {HERE / src} {Path(dst_dir) / src.name}")
    print(f"{src} -> {dst_dir}")


SYMLINKS = [
    ("vscode/settings.json", "~/Library/Application\\ Support/Code/User"),
    ("vscode/keybinding.json", "~/Library/Application\\ Support/Code/User"),
    ("vscode/snippets", "~/Library/Application\\ Support/Code/User"),
    (".zshrc", "~/"),
]


if __name__ == "__main__":
    for src, dst_dir in SYMLINKS:
        symlink(src, dst_dir)
