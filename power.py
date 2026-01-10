# power_controller.py
from __future__ import annotations

import shutil
import subprocess
import sys
from typing import Optional

# Module-level configuration for optional confirmation behavior
_require_confirmation: bool = False
_confirmation_granted: bool = False

# Timeout for subprocess calls (seconds)
_SUBPROCESS_TIMEOUT = 2


# -------------------------
# Platform detection
# -------------------------


def _platform() -> str:
    try:
        return sys.platform or ""
    except Exception:
        return ""


def _is_windows() -> bool:
    return _platform().startswith("win")


def _is_macos() -> bool:
    return _platform().startswith("darwin")


def _is_linux() -> bool:
    return _platform().startswith("linux")


# -------------------------
# Helpers for confirmation
# -------------------------


def set_require_confirmation(require: bool) -> None:
    """
    Configure whether destructive power actions require prior explicit confirmation.

    When enabled (require=True), shutdown/restart/sleep will only proceed after
    grant_confirmation() has been called and will return False otherwise.

    This helper is safe to call at runtime. It does not perform any I/O.
    """
    global _require_confirmation
    try:
        _require_confirmation = bool(require)
    except Exception:
        # Defensive: ignore any issues
        pass


def grant_confirmation() -> None:
    """
    Grant confirmation for destructive power actions once.

    If confirmation is required (set_require_confirmation(True)), calling this
    function will allow the next power action to proceed. The confirmation is
    not persisted across processes.
    """
    global _confirmation_granted
    try:
        _confirmation_granted = True
    except Exception:
        pass


def _consume_confirmation() -> bool:
    """
    Internal helper: return True if either confirmation is not required, or if
    it is required and has been granted. If granted, consume it (one-time).
    """
    global _confirmation_granted
    try:
        if not _require_confirmation:
            return True
        if _confirmation_granted:
            _confirmation_granted = False
            return True
        return False
    except Exception:
        return False


# -------------------------
# Safe subprocess runner
# -------------------------


def _run_cmd(cmd: list[str]) -> Optional[tuple[int, str, str]]:
    """
    Run a command safely without shell, capture output, and enforce timeout.
    Returns tuple(returncode, stdout, stderr) or None on failure.
    """
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=_SUBPROCESS_TIMEOUT, check=False)
        return proc.returncode, proc.stdout or "", proc.stderr or ""
    except Exception:
        return None


def _execute_and_check(cmd: list[str]) -> bool:
    """
    Execute the given command list and return True if it executed and returned exit code 0.
    Returns False on timeout, error, or non-zero exit code.
    """
    try:
        res = _run_cmd(cmd)
        if not res:
            return False
        rc, _, _ = res
        return rc == 0
    except Exception:
        return False


# -------------------------
# Windows implementations
# -------------------------


def _windows_is_supported() -> bool:
    """
    Windows is supported if platform is Windows and required commands (shutdown) or PowerShell are present.
    Using built-in commands; most Windows systems will support these operations.
    """
    try:
        # 'shutdown' is built-in; check presence
        return shutil.which("shutdown") is not None or shutil.which("powershell") is not None
    except Exception:
        return False


def _windows_shutdown() -> bool:
    """
    Attempt to shut down Windows using 'shutdown' command. Returns True if the command succeeded (exit code 0).
    This will not wait for the system to power off; it returns based on command acceptance.
    """
    try:
        if not _consume_confirmation():
            return False
        sh = shutil.which("shutdown")
        if sh:
            return _execute_and_check([sh, "/s", "/t", "0"])
        # Fallback: attempt PowerShell Stop-Computer
        pw = shutil.which("powershell") or shutil.which("pwsh")
        if pw:
            return _execute_and_check([pw, "-NoProfile", "-NonInteractive", "-Command", "Stop-Computer -Force"])
        return False
    except Exception:
        return False


def _windows_restart() -> bool:
    """
    Attempt to restart Windows. Returns True if the command was accepted.
    """
    try:
        if not _consume_confirmation():
            return False
        sh = shutil.which("shutdown")
        if sh:
            return _execute_and_check([sh, "/r", "/t", "0"])
        pw = shutil.which("powershell") or shutil.which("pwsh")
        if pw:
            return _execute_and_check([pw, "-NoProfile", "-NonInteractive", "-Command", "Restart-Computer -Force"])
        return False
    except Exception:
        return False


def _windows_sleep() -> bool:
    """
    Attempt to put Windows to sleep using rundll32. This may require appropriate system support.
    Returns True if the command executed successfully (exit code 0).
    """
    try:
        if not _consume_confirmation():
            return False
        rundll = shutil.which("rundll32.exe")
        if rundll:
            # This attempts to call SetSuspendState; behavior depends on system configuration (hibernate vs sleep)
            return _execute_and_check([rundll, "powrprof.dll,SetSuspendState", "0,1,0"])
        # Fallback: attempt PowerShell sleep via calling SetSuspendState through P/Invoke is complex; return False
        return False
    except Exception:
        return False


# -------------------------
# macOS implementations
# -------------------------


def _macos_is_supported() -> bool:
    """
    macOS is supported if osascript is present to ask System Events to perform actions.
    """
    try:
        return shutil.which("osascript") is not None
    except Exception:
        return False


def _macos_shutdown() -> bool:
    """
    Ask macOS System Events to shut down via osascript. Returns True if the command executed successfully.
    Note: this may require appropriate privileges and will be accepted asynchronously by the OS.
    """
    try:
        if not _consume_confirmation():
            return False
        osa = shutil.which("osascript")
        if not osa:
            return False
        # Use AppleScript to tell System Events to shut down
        return _execute_and_check([osa, "-e", 'tell application "System Events" to shut down'])
    except Exception:
        return False


def _macos_restart() -> bool:
    """
    Ask macOS System Events to restart via osascript.
    """
    try:
        if not _consume_confirmation():
            return False
        osa = shutil.which("osascript")
        if not osa:
            return False
        return _execute_and_check([osa, "-e", 'tell application "System Events" to restart'])
    except Exception:
        return False


def _macos_sleep() -> bool:
    """
    Ask macOS to sleep via osascript. This is the most portable approach using standard tools.
    """
    try:
        if not _consume_confirmation():
            return False
        osa = shutil.which("osascript")
        if not osa:
            return False
        return _execute_and_check([osa, "-e", 'tell application "System Events" to sleep'])
    except Exception:
        return False


# -------------------------
# Linux implementations
# -------------------------


def _linux_is_supported() -> bool:
    """
    Linux is considered supported if at least one common power management command is available:
    - systemctl, shutdown, reboot, or pm-suspend
    """
    try:
        return any(
            shutil.which(cmd) is not None
            for cmd in ("systemctl", "shutdown", "reboot", "pm-suspend", "pm-hibernate")
        )
    except Exception:
        return False


def _linux_shutdown() -> bool:
    """
    Attempt to shut down Linux using systemctl if available, else shutdown command.
    Returns True if command executed and returned success.
    """
    try:
        if not _consume_confirmation():
            return False
        systemctl = shutil.which("systemctl")
        if systemctl:
            # 'poweroff' is preferred and will be accepted by systemd
            if _execute_and_check([systemctl, "poweroff"]):
                return True
        shutdown = shutil.which("shutdown")
        if shutdown:
            # attempt immediate halt
            if _execute_and_check([shutdown, "-h", "now"]):
                return True
        # fallback: 'halt'
        halt = shutil.which("halt")
        if halt:
            return _execute_and_check([halt])
        return False
    except Exception:
        return False


def _linux_restart() -> bool:
    """
    Attempt to reboot the Linux system using systemctl or reboot/shutdown.
    """
    try:
        if not _consume_confirmation():
            return False
        systemctl = shutil.which("systemctl")
        if systemctl:
            if _execute_and_check([systemctl, "reboot"]):
                return True
        reboot = shutil.which("reboot")
        if reboot:
            if _execute_and_check([reboot]):
                return True
        shutdown = shutil.which("shutdown")
        if shutdown:
            if _execute_and_check([shutdown, "-r", "now"]):
                return True
        return False
    except Exception:
        return False


def _linux_sleep() -> bool:
    """
    Attempt to suspend (sleep) Linux system. Prefer systemctl suspend, then pm-suspend.
    """
    try:
        if not _consume_confirmation():
            return False
        systemctl = shutil.which("systemctl")
        if systemctl:
            if _execute_and_check([systemctl, "suspend"]):
                return True
        pmsuspend = shutil.which("pm-suspend")
        if pmsuspend:
            if _execute_and_check([pmsuspend]):
                return True
        return False
    except Exception:
        return False


# -------------------------
# Public API
# -------------------------


def is_power_action_supported() -> bool:
    """
    Check whether power actions (shutdown/restart/sleep) are supported on this platform
    by verifying the availability of commonly-used system utilities.

    Returns True if supported (best-effort), False otherwise.
    """
    try:
        if _is_windows():
            return _windows_is_supported()
        if _is_macos():
            return _macos_is_supported()
        if _is_linux():
            return _linux_is_supported()
        return False
    except Exception:
        return False


def shutdown_system() -> bool:
    """
    Attempt a clean system shutdown.

    Returns True if the shutdown command was accepted by the OS (best-effort), False otherwise.

    If confirmation is required (see set_require_confirmation), this function will return False
    unless grant_confirmation() has been called prior to invoking this function.
    """
    try:
        if not _consume_confirmation():
            return False
        if _is_windows():
            return _windows_shutdown()
        if _is_macos():
            return _macos_shutdown()
        if _is_linux():
            return _linux_shutdown()
        return False
    except Exception:
        return False


def restart_system() -> bool:
    """
    Attempt to restart (reboot) the system.

    Returns True if the restart command was accepted by the OS (best-effort), False otherwise.

    Use grant_confirmation()/set_require_confirmation() to control destructive action confirmations.
    """
    try:
        if not _consume_confirmation():
            return False
        if _is_windows():
            return _windows_restart()
        if _is_macos():
            return _macos_restart()
        if _is_linux():
            return _linux_restart()
        return False
    except Exception:
        return False


def sleep_system() -> bool:
    """
    Attempt to put the system to sleep/suspend.

    Returns True if the suspend command was accepted by the OS (best-effort), False otherwise.

    Note: actual sleep behavior may depend on hardware, drivers, and permissions.
    """
    try:
        if not _consume_confirmation():
            return False
        if _is_windows():
            return _windows_sleep()
        if _is_macos():
            return _macos_sleep()
        if _is_linux():
            return _linux_sleep()
        return False
    except Exception:
        return False