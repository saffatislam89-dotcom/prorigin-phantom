"""
os_capabilities.py

Cross-platform utilities to inspect basic OS information and supported system capabilities.

Design goals:
- Detect OS name and version.
- Detect administrative privilege (Windows admin or Unix root).
- Report whether a small set of high-level "features" are likely to be supported on the current platform.
- Be safe on import (do not execute detection at import time).
- No third-party libraries, Python 3.10+ compatible.
- Fail silently: do not raise on detection errors; return conservative values (e.g., False or "Unknown").
"""

from __future__ import annotations

import os
import platform
import sys
from typing import Dict


def _detect_os_name() -> str:
    """
    Detect the operating system family in normalized form.

    Returns:
        One of: "Windows", "Linux", "macOS", or "Unknown".
    """
    try:
        system = platform.system()
        if system == "Windows":
            return "Windows"
        if system == "Darwin":
            return "macOS"
        if system == "Linux":
            return "Linux"
        # Fallback for other/unexpected values
        return "Unknown"
    except Exception:
        # Silent failure per requirements
        return "Unknown"


def _detect_os_version() -> str:
    """
    Produce a human-readable OS version string.

    Returns:
        A best-effort version string or "Unknown".
    """
    try:
        os_name = platform.system()
        if os_name == "Windows":
            # platform.version() returns the underlying OS version string.
            # platform.release() returns the product release (e.g., "10")
            ver = platform.version()
            release = platform.release()
            return f"{release} (version={ver})"
        if os_name == "Darwin":
            # mac_ver returns (release, versioninfo, machine)
            mac_ver = platform.mac_ver()[0]
            if mac_ver:
                return f"macOS {mac_ver}"
            # fallback
            return platform.platform()
        if os_name == "Linux":
            # Try a few Linux-specific helpers but don't rely on deprecated/dist-specific APIs.
            # platform.release() is usually the kernel release; that's still useful.
            release = platform.release()
            distro = ""
            try:
                # Python 3.8+ removed platform.linux_distribution(); attempt reading /etc/os-release.
                if os.path.exists("/etc/os-release"):
                    with open("/etc/os-release", "r", encoding="utf-8") as f:
                        for line in f:
                            if line.startswith("PRETTY_NAME="):
                                # PRETTY_NAME="Ubuntu 20.04.6 LTS"
                                distro = line.split("=", 1)[1].strip().strip('"')
                                break
            except Exception:
                # Ignore any error reading the file; fall back to generic info.
                distro = ""
            if distro:
                return f"{distro} (kernel {release})"
            return f"Linux (kernel {release})"
        # Generic fallback
        return platform.platform() or "Unknown"
    except Exception:
        return "Unknown"


def _is_admin_unix() -> bool:
    """
    Detect Unix root privileges.

    Returns:
        True if running as root, False otherwise or on failure.
    """
    try:
        # os.geteuid exists on POSIX systems.
        if hasattr(os, "geteuid"):
            return os.geteuid() == 0
        # If geteuid is not available, conservatively return False.
        return False
    except Exception:
        return False


def _is_admin_windows() -> bool:
    """
    Detect Windows administrative privilege.

    Uses ctypes to call IsUserAnAdmin. This is safe to call at runtime and
    is wrapped in try/except to avoid crashes on unsupported environments.

    Returns:
        True if admin, False otherwise or on failure.
    """
    try:
        if sys.platform != "win32":
            return False
        import ctypes  # local import to avoid importing on non-windows unnecessarily

        try:
            return bool(ctypes.windll.shell32.IsUserAnAdmin())
        except Exception:
            # Older or restricted Windows builds may raise; fall back to False.
            return False
    except Exception:
        return False


def get_os_info() -> Dict[str, object]:
    """
    Return basic operating system information.

    The function performs detection at call-time (to avoid doing work on import).

    Returns:
        dict with keys:
            - os_name: "Windows" | "Linux" | "macOS" | "Unknown"
            - os_version: human-readable version string or "Unknown"
            - is_admin: True if running with elevated privileges (Windows admin / Unix root), else False

    Notes:
        - Detection is best-effort and uses safe, guarded checks.
        - On any internal error the corresponding value will be a conservative default
          (e.g., "Unknown" or False) rather than raising.
    """
    try:
        os_name = _detect_os_name()
        os_version = _detect_os_version()
        # Determine admin/root depending on platform family.
        if os_name == "Windows":
            is_admin = _is_admin_windows()
        elif os_name in ("Linux", "macOS"):
            is_admin = _is_admin_unix()
        else:
            # Unknown platforms: attempt both checks conservatively.
            is_admin = _is_admin_unix() or _is_admin_windows()
        return {"os_name": os_name, "os_version": os_version, "is_admin": bool(is_admin)}
    except Exception:
        # Silent failure: return conservative defaults.
        return {"os_name": "Unknown", "os_version": "Unknown", "is_admin": False}


def supports_feature(feature_name: str) -> bool:
    """
    Report whether a named high-level feature is likely to be supported on this system.

    Supported feature names (case-insensitive):
      - "file_open": Basic ability to open/read/write files.
      - "app_control": Ability to programmatically launch or open applications/files.
      - "keyboard_mouse": Ability to programmatically synthesize or control keyboard/mouse input.
      - "system_volume": Ability to programmatically change system audio volume.
      - "power_control": Ability to programmatically shutdown/restart the system (usually requires elevated privileges).

    Returns:
        True if the feature is likely available, False otherwise (or on error).

    Notes:
        - This is a conservative, best-effort probe and does not perform invasive operations.
        - The function never performs privileged actions; it only infers capability from the platform and common runtime conditions.
        - On error the function returns False.
    """
    if not isinstance(feature_name, str):
        return False

    key = feature_name.strip().lower()

    try:
        info = get_os_info()
        os_name = info.get("os_name", "Unknown")
        is_admin = bool(info.get("is_admin", False))
    except Exception:
        # In case get_os_info fails unexpectedly, be conservative.
        os_name = "Unknown"
        is_admin = False

    try:
        # FILE OPEN: virtually always available in standard Python runtime.
        if key == "file_open":
            # We do not actually attempt file I/O here to avoid side-effects;
            # assume file I/O support unless running in an extremely constrained environment.
            return True

        # APP CONTROL: launching/controlling external apps.
        # - On desktop-class OSes we consider it available.
        # - On Linux we check for a display environment variable as a heuristic for desktop.
        if key == "app_control":
            if os_name == "Windows":
                return True
            if os_name == "macOS":
                return True
            if os_name == "Linux":
                # If a graphical display exists, app control (opening GUI apps) is likely possible.
                if os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"):
                    return True
                # Headless servers may still have ability to run processes, but 'app control' here
                # is interpreted as user-facing app launching; be conservative.
                return False
            return False

        # KEYBOARD_MOUSE: synthesizing input events typically requires a graphical session
        # or specific device access (and sometimes elevated privileges).
        if key == "keyboard_mouse":
            if os_name == "Windows":
                # Windows desktop typically supports APIs for input simulation.
                return True
            if os_name == "macOS":
                # macOS supports accessibility APIs; assume available on desktops.
                return True
            if os_name == "Linux":
                # Require a display server (X11/Wayland) as a heuristic.
                if os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"):
                    # Note: on some Linux setups input injection requires root (uinput) or X access;
                    # we don't attempt to verify that here — return True as the baseline.
                    return True
                return False
            return False

        # SYSTEM VOLUME: changing system volume is platform-specific.
        if key == "system_volume":
            if os_name == "Windows":
                # Windows has APIs to change system volume (Core Audio).
                return True
            if os_name == "macOS":
                # macOS can be controlled via CoreAudio APIs / AppleScript; assume available.
                return True
            if os_name == "Linux":
                # Attempt to detect common Linux audio subsystems without executing external binaries.
                # Check for ALSA /proc presence or environment variables for Pulse/PipeWire.
                try:
                    if os.path.exists("/proc/asound"):
                        return True
                except Exception:
                    pass
                # Environment heuristics for pulseaudio/pipewire
                if any(
                    os.environ.get(k)
                    for k in ("PULSE_SERVER", "PIPEWIRE_SOCKET", "PULSE_CLIENTSERVER")
                ):
                    return True
                # If there is a desktop session, audio control is more likely available.
                if os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"):
                    # conservative True because desktop Linux commonly has an audio server.
                    return True
                return False
            return False

        # POWER CONTROL: shutdown/reboot. Usually requires administrative privileges.
        if key == "power_control":
            # Conservatively require elevated privileges.
            return bool(is_admin)

        # Unknown feature
        return False
    except Exception:
        # All detection is wrapped to avoid raising; on any error return False.
        return False