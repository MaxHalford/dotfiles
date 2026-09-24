"""Open the plugin's session-modal popup from a keybound Herdr action."""

import os
import subprocess
import sys


def main():
    herdr = os.environ.get("HERDR_BIN_PATH", "herdr")
    plugin = os.environ.get("HERDR_PLUGIN_ID", "dev.max.worktree-prs")
    result = subprocess.run(
        [herdr, "plugin", "pane", "open", "--plugin", plugin, "--entrypoint", "board"],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode:
        print(result.stderr or result.stdout, file=sys.stderr)
    return result.returncode


if __name__ == "__main__":
    sys.exit(main())
