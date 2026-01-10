"""
windows_open_new_window.py

Robust helper: open a path in a NEW Windows Explorer window.
- Folder  → explorer /n <path>
- File    → explorer /select,<path>
Safe, silent, OS-validated, Copilot/Cursor friendly.
"""

from __future__ import annotations
import os
import subprocess
import platform
from typing import Optional


def open_in_new_explorer_window(path: str) -> bool:
    """
    Open `path` in a new Windows Explorer window.

    Returns:
        True  -> command dispatched successfully
        False -> invalid input / unsupported OS / execution failure
    """

    # ✅ Hard OS guard
    if platform.system() != "Windows":
        return False

    if not isinstance(path, str) or not path.strip():
        return False

    try:
        norm_path = os.path.normpath(os.path.abspath(path))
    except Exception:
        return False

    try:
        explorer = os.path.join(os.environ.get("WINDIR", "C:\\Windows"), "explorer.exe")

        # 📂 Directory → new window
        if os.path.isdir(norm_path):
            cmd = [explorer, "/n", norm_path]

        # 📄 File → select in folder
        else:
            if os.path.exists(norm_path):
                target = norm_path
            else:
                parent = os.path.dirname(norm_path)
                if not os.path.isdir(parent):
                    return False
                target = os.path.join(parent, os.path.basename(norm_path))

            # Explorer requires /select,PATH as one token
            cmd = [explorer, f"/select,{target}"]

        subprocess.Popen(
            cmd,
            shell=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=subprocess.DETACHED_PROCESS
        )

        return True

    except Exception:
        return False
