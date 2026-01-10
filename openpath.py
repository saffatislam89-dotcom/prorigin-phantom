"""
open_path.py

Cross-platform utility to open a file or directory with the system default application / file
explorer.

Public API:
    open_path(path: str) -> bool

Behavior:
- If `path` is a file: open it with the OS default application.
- If `path` is a directory: open it in the system file explorer.
- Supports Windows, macOS, and common Linux desktop environments.
- Returns True on a best-effort successful request to open; returns False on any error.
- Silent on failures (no exceptions propagated, no stdout/stderr prints).
- Uses only the Python standard library and does not use shell=True.
- Does not perform any actions at import-time.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import List, Optional, Union


def _is_windows() -> bool:
    return sys.platform == "win32"


def _is_macos() -> bool:
    return sys.platform == "darwin"


def _is_linux() -> bool:
    # 'linux' may be 'linux' or start with 'linux'
    return sys.platform.startswith("linux")


def _choose_linux_opener() -> Optional[str]:
    """
    Return the first available command for opening a path on Linux desktops,
    or None if none are found.
    Order chosen to prefer xdg-open (freedesktop standard), then gio (GLib/GIO),
    then a few older KDE/GNOME helpers.
    """
    candidates = ("xdg-open", "gio", "gnome-open", "kde-open", "kde-open5")
    for cmd in candidates:
        if shutil.which(cmd):
            return cmd
    return None


def open_path(path: Union[str, os.PathLike]) -> bool:
    """
    Open a file or directory using the operating system's default handler.

    Args:
        path: A path-like object or string pointing to an existing file or directory.

    Returns:
        True if the operation was successfully initiated (best-effort), False otherwise.

    Behavior and safety:
    - Validates and normalizes the input path. If the path does not exist, returns False.
    - Requires that os_capabilities.supports_feature("app_control") returns True; if not, returns False.
    - Uses only standard library modules.
    - Does not use shell=True or write to stdout/stderr.
    - Silent failures: any error returns False.
    """
    try:
        # Basic type validation
        if not isinstance(path, (str, os.PathLike)):
            return False

        # Normalize & verify existence. resolve(strict=True) will raise if missing.
        p = Path(path).expanduser()
        try:
            p = p.resolve(strict=True)
        except Exception:
            # Path does not exist or cannot be resolved -> requirement: return False
            return False

        # Ensure it's a file or directory
        if not (p.is_file() or p.is_dir()):
            return False

        # Lazy import of os_capabilities to check app_control support;
        # any problem importing or the feature being unsupported => return False.
        try:
            from os_capabilities import supports_feature  # type: ignore
        except Exception:
            return False

        try:
            if not supports_feature("app_control"):
                return False
        except Exception:
            # supports_feature should not raise, but be defensive.
            return False

        # Platform-specific opening
        if _is_windows():
            # Use os.startfile which delegates to the shell to open with default app.
            # This raises OSError on failure; catch and return False.
            try:
                os.startfile(str(p))
                return True
            except Exception:
                return False

        if _is_macos():
            # Use 'open' command
            cmd = ["open", str(p)]
            try:
                proc = subprocess.run(
                    cmd, check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
                )
                return proc.returncode == 0
            except Exception:
                return False

        if _is_linux():
            opener = _choose_linux_opener()
            if not opener:
                return False
            cmd: List[str] = [opener, str(p)]
            try:
                proc = subprocess.run(
                    cmd, check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
                )
                return proc.returncode == 0
            except Exception:
                return False

        # Unknown platform: conservative False
        return False

    except Exception:
        # Any unexpected error: fail silently and return False
        return False