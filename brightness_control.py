# brightness_control.py
# Fully fixed, hardened, cross-platform screen brightness control.

from __future__ import annotations
import subprocess
import shutil
from pathlib import Path
from typing import Optional
import sys

# ---------------------------
# Platform detection
# ---------------------------

def _is_windows() -> bool:
    return sys.platform == "win32"

def _is_macos() -> bool:
    return sys.platform == "darwin"

def _is_linux() -> bool:
    return sys.platform.startswith("linux")

# ---------------------------
# Linux helpers
# ---------------------------

def _linux_get_brightness_brightnessctl() -> Optional[int]:
    try:
        bc = shutil.which("brightnessctl")
        if not bc:
            return None
        proc_get = subprocess.run([bc, "get"], capture_output=True, text=True, timeout=2, check=False)
        proc_max = subprocess.run([bc, "max"], capture_output=True, text=True, timeout=2, check=False)
        if proc_get.returncode != 0 or proc_max.returncode != 0:
            return None
        cur, mx = int(proc_get.stdout.strip()), int(proc_max.stdout.strip())
        if mx <= 0:
            return None
        return max(0, min(100, round(cur * 100 / mx)))
    except Exception:
        return None

def _linux_set_brightness_brightnessctl(percent: int) -> bool:
    try:
        bc = shutil.which("brightnessctl")
        if not bc:
            return False
        arg = f"{percent}%"
        proc = subprocess.run([bc, "set", arg], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=2, check=False)
        return proc.returncode == 0
    except Exception:
        return False

def _linux_get_brightness_xbacklight() -> Optional[int]:
    try:
        xb = shutil.which("xbacklight")
        if not xb:
            return None
        proc = subprocess.run([xb, "-get"], capture_output=True, text=True, timeout=2, check=False)
        if proc.returncode != 0:
            return None
        return max(0, min(100, round(float(proc.stdout.strip()))))
    except Exception:
        return None

def _linux_set_brightness_xbacklight(percent: int) -> bool:
    try:
        xb = shutil.which("xbacklight")
        if not xb:
            return False
        proc = subprocess.run([xb, "-set", str(percent)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=2, check=False)
        return proc.returncode == 0
    except Exception:
        return False

def _linux_get_brightness_sysfs() -> Optional[int]:
    try:
        base = Path("/sys/class/backlight")
        if not base.exists() or not base.is_dir():
            return None
        for entry in base.iterdir():
            bfile, mfile = entry / "brightness", entry / "max_brightness"
            if bfile.exists() and mfile.exists():
                try:
                    cur, mx = int(bfile.read_text().strip()), int(mfile.read_text().strip())
                    if mx <= 0:
                        continue
                    return max(0, min(100, round(cur * 100 / mx)))
                except Exception:
                    continue
        return None
    except Exception:
        return None

def _linux_set_brightness_sysfs(percent: int) -> bool:
    try:
        base = Path("/sys/class/backlight")
        if not base.exists() or not base.is_dir():
            return False
        for entry in base.iterdir():
            bfile, mfile = entry / "brightness", entry / "max_brightness"
            if bfile.exists() and mfile.exists():
                try:
                    mx = int(mfile.read_text().strip())
                    target = max(0, min(mx, round(percent * mx / 100)))
                    try:
                        with open(bfile, "w") as fh:
                            fh.write(str(target))
                        return True
                    except PermissionError:
                        continue
                except Exception:
                    continue
        return False
    except Exception:
        return False

# ---------------------------
# Windows helpers
# ---------------------------

def _windows_get_brightness_powershell() -> Optional[int]:
    try:
        pwsh = shutil.which("powershell")
        if not pwsh:
            return None
        cmd = [
            pwsh, "-NoProfile", "-NonInteractive", "-Command",
            "Get-WmiObject -Namespace root\\wmi -Class WmiMonitorBrightness | "
            "Select-Object -ExpandProperty CurrentBrightness | Select-Object -First 1"
        ]
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=2, check=False)
        if proc.returncode != 0 or not proc.stdout:
            return None
        val = int(proc.stdout.strip())
        return max(0, min(100, val))
    except Exception:
        return None

def _windows_set_brightness_powershell(percent: int) -> bool:
    try:
        pwsh = shutil.which("powershell")
        if not pwsh:
            return False
        script = (
            "$m = Get-WmiObject -Namespace root\\wmi -Class WmiMonitorBrightnessMethods -ErrorAction SilentlyContinue | Select-Object -First 1; "
            f"if ($m -ne $null) {{ $m.WmiSetBrightness(1, {percent}) | Out-Null; exit 0 }} else {{ exit 1 }}"
        )
        proc = subprocess.run([pwsh, "-NoProfile", "-NonInteractive", "-Command", script], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=2, check=False)
        return proc.returncode == 0
    except Exception:
        return False

# ---------------------------
# macOS helpers
# ---------------------------

def _mac_get_brightness_unavailable() -> Optional[int]:
    return None

def _mac_set_brightness_unavailable(percent: int) -> bool:
    return False

# ---------------------------
# Public API
# ---------------------------

def get_brightness() -> Optional[int]:
    try:
        if _is_linux():
            return (_linux_get_brightness_brightnessctl() or
                    _linux_get_brightness_xbacklight() or
                    _linux_get_brightness_sysfs())
        if _is_windows():
            return _windows_get_brightness_powershell()
        if _is_macos():
            return _mac_get_brightness_unavailable()
        return None
    except Exception:
        return None

def set_brightness(percent: int) -> bool:
    if not isinstance(percent, int) or percent < 0 or percent > 100:
        return False
    try:
        if _is_linux():
            return (_linux_set_brightness_brightnessctl(percent) or
                    _linux_set_brightness_xbacklight(percent) or
                    _linux_set_brightness_sysfs(percent))
        if _is_windows():
            return _windows_set_brightness_powershell(percent)
        if _is_macos():
            return _mac_set_brightness_unavailable(percent)
        return False
    except Exception:
        return False
