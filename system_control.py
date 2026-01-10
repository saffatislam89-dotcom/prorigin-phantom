# system_control.py — Fully Hardened Version
# Cross-platform system controls: volume & brightness

from __future__ import annotations
import os, sys, re, shutil, subprocess
from pathlib import Path
from typing import Optional

# --------------------------- Platform helpers ---------------------------

def _is_windows() -> bool: return sys.platform == "win32"
def _is_macos() -> bool: return sys.platform == "darwin"
def _is_linux() -> bool: return sys.platform.startswith("linux")
def _valid_percent(p) -> bool:
    return isinstance(p, int) and 0 <= p <= 100

# --------------------------- Linux Volume ---------------------------

def _linux_get_volume_pactl() -> Optional[int]:
    try:
        pactl = shutil.which("pactl")
        if not pactl: return None
        res = subprocess.run([pactl, "get-sink-volume", "@DEFAULT_SINK@"], capture_output=True, text=True, check=False, timeout=2)
        m = re.search(r"(\d{1,3})%\b", res.stdout or "")
        return max(0, min(100, int(m.group(1)))) if m else None
    except Exception: return None

def _linux_set_volume_pactl(percent: int) -> bool:
    try:
        pactl = shutil.which("pactl")
        if not pactl: return False
        res = subprocess.run([pactl, "set-sink-volume", "@DEFAULT_SINK@", f"{percent}%"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False, timeout=2)
        return res.returncode == 0
    except Exception: return False

def _linux_mute_pactl(mute: bool) -> bool:
    try:
        pactl = shutil.which("pactl")
        if not pactl: return False
        arg = "1" if mute else "0"
        res = subprocess.run([pactl, "set-sink-mute", "@DEFAULT_SINK@", arg], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False, timeout=2)
        return res.returncode == 0
    except Exception: return False

def _linux_get_volume_amixer() -> Optional[int]:
    try:
        amixer = shutil.which("amixer")
        if not amixer: return None
        res = subprocess.run([amixer, "get", "Master"], capture_output=True, text=True, check=False, timeout=2)
        m = re.search(r"\[(\d{1,3})%\]", res.stdout or "")
        return max(0, min(100, int(m.group(1)))) if m else None
    except Exception: return None

def _linux_set_volume_amixer(percent: int) -> bool:
    try:
        amixer = shutil.which("amixer")
        if not amixer: return False
        res = subprocess.run([amixer, "set", "Master", f"{percent}%"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False, timeout=2)
        return res.returncode == 0
    except Exception: return False

def _linux_mute_amixer(mute: bool) -> bool:
    try:
        amixer = shutil.which("amixer")
        if not amixer: return False
        mode = "mute" if mute else "unmute"
        res = subprocess.run([amixer, "set", "Master", mode], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False, timeout=2)
        return res.returncode == 0
    except Exception: return False

# --------------------------- macOS Volume ---------------------------

def _mac_get_volume() -> Optional[int]:
    try:
        osa = shutil.which("osascript")
        if not osa: return None
        res = subprocess.run([osa, "-e", "output volume of (get volume settings)"], capture_output=True, text=True, check=False, timeout=2)
        return max(0, min(100, int(res.stdout.strip()))) if res.stdout.strip().isdigit() else None
    except Exception: return None

def _mac_set_volume(percent: int) -> bool:
    try:
        osa = shutil.which("osascript")
        if not osa: return False
        res = subprocess.run([osa, "-e", f"set volume output volume {percent}"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False, timeout=2)
        return res.returncode == 0
    except Exception: return False

def _mac_mute_set(mute: bool) -> bool:
    try:
        osa = shutil.which("osascript")
        if not osa: return False
        val = "true" if mute else "false"
        res = subprocess.run([osa, "-e", f"set volume output muted {val}"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False, timeout=2)
        return res.returncode == 0
    except Exception: return False

# --------------------------- Windows Volume ---------------------------

def _windows_get_volume_powershell() -> Optional[int]:
    try:
        pwsh = shutil.which("powershell")
        if not pwsh: return None
        script = "[void][System.Reflection.Assembly]::LoadWithPartialName('System.Runtime.InteropServices'); $d=New-Object -ComObject MMDeviceEnumerator;$v=$d.GetDefaultAudioEndpoint(0,1).AudioEndpointVolume.MasterVolumeLevelScalar;Write-Output ([math]::Round($v*100))"
        res = subprocess.run([pwsh, "-NoProfile", "-NonInteractive", "-Command", script], capture_output=True, text=True, check=False, timeout=2)
        return max(0, min(100, int(res.stdout.strip()))) if res.stdout.strip().isdigit() else None
    except Exception: return None

def _windows_set_volume_powershell(percent: int) -> bool:
    try:
        pwsh = shutil.which("powershell")
        if not pwsh: return False
        script = f"[void][System.Reflection.Assembly]::LoadWithPartialName('System.Runtime.InteropServices'); $d=New-Object -ComObject MMDeviceEnumerator;$d.GetDefaultAudioEndpoint(0,1).AudioEndpointVolume.MasterVolumeLevelScalar={percent/100.0}"
        res = subprocess.run([pwsh, "-NoProfile", "-NonInteractive", "-Command", script], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False, timeout=2)
        return res.returncode == 0
    except Exception: return False

def _windows_mute_powershell(mute: bool) -> bool:
    try:
        pwsh = shutil.which("powershell")
        if not pwsh: return False
        val = "$true" if mute else "$false"
        script = f"[void][System.Reflection.Assembly]::LoadWithPartialName('System.Runtime.InteropServices');$d=New-Object -ComObject MMDeviceEnumerator;$d.GetDefaultAudioEndpoint(0,1).AudioEndpointVolume.Mute={val}"
        res = subprocess.run([pwsh, "-NoProfile", "-NonInteractive", "-Command", script], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False, timeout=2)
        return res.returncode == 0
    except Exception: return False

# --------------------------- Public API ---------------------------

def get_volume() -> Optional[int]:
    try:
        if _is_linux(): return _linux_get_volume_pactl() or _linux_get_volume_amixer()
        if _is_macos(): return _mac_get_volume()
        if _is_windows(): return _windows_get_volume_powershell()
    except Exception: return None
    return None

def set_volume(percent: int) -> bool:
    if not _valid_percent(percent): return False
    try:
        if _is_linux(): return _linux_set_volume_pactl(percent) or _linux_set_volume_amixer(percent)
        if _is_macos(): return _mac_set_volume(percent)
        if _is_windows(): return _windows_set_volume_powershell(percent)
    except Exception: return False
    return False

def mute_volume() -> bool:
    try:
        if _is_linux(): return _linux_mute_pactl(True) or _linux_mute_amixer(True)
        if _is_macos(): return _mac_mute_set(True)
        if _is_windows(): return _windows_mute_powershell(True)
    except Exception: return False
    return False

def unmute_volume() -> bool:
    try:
        if _is_linux(): return _linux_mute_pactl(False) or _linux_mute_amixer(False)
        if _is_macos(): return _mac_mute_set(False)
        if _is_windows(): return _windows_mute_powershell(False)
    except Exception: return False
    return False
