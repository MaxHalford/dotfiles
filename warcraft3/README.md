# Warcraft III hotkeys

`CustomKeys.txt` starts from the installed Warcraft III profile and assigns the four ability columns to **A, Z, E, R**, from left to right. The same keys select hero abilities when leveling them. Attack moves from **A** to **Q** so the first ability can use A. Some campaign and neutral abilities use a different AZER key to avoid conflicts; fifth abilities on a few campaign heroes and worker resource commands retain their original keys.

Run `python make_symlinks.py` from the repository to install the file at `~/Library/Application Support/Blizzard/Warcraft III/CustomKeyBindings/CustomKeys.txt`. In Warcraft III, set **Options → Input → Preset Keybindings** to **Custom**.

If this change is merged from a temporary worktree, run the symlink script again from the main dotfiles checkout so the game points to the lasting copy.

Control groups use the game's number keys: **1–0** recalls a group. On macOS, turn on **Use Command as Control** in the game's input settings to assign a group with **Command+1** through **Command+0**. This setting is stored as `usecmdasctrl=1` under `[Mac]` in `War3Preferences.txt`.
