from __future__ import annotations
import subprocess
import shutil
import functools

def handle_errors(return_on_error=False):
    def dec(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except Exception as e:
                print(f"[!] Bluetooth Error: {e}")
                return return_on_error
        return wrapper
    return dec

def _powershell_cmd(script: str):
    pwsh = shutil.which("powershell") or shutil.which("pwsh")
    if not pwsh: return None
    try:
        # এটি রেডিও স্ট্যাটাস পরিবর্তন করার আধুনিক উইন্ডোজ কমান্ড
        proc = subprocess.run([pwsh, "-NoProfile", "-Command", script], capture_output=True, text=True, timeout=5)
        return proc.stdout.strip()
    except:
        return None

@handle_errors(return_on_error=None)
def get_bluetooth_status() -> bool:
    # চেক করবে ব্লুটুথ রেডিও বর্তমানে অন না অফ
    script = "Get-NetAdapter -Name *Bluetooth* | Select-Object -ExpandProperty Status"
    res = _powershell_cmd(script)
    if res and "Up" in res:
        return True
    return False

@handle_errors(return_on_error=False)
def enable_bluetooth() -> bool:
    # হার্ডওয়্যার ডিসেবল না করে শুধুমাত্র ব্লুটুথ রেডিও অন করবে
    script = "Get-NetAdapter -Name *Bluetooth* | Enable-NetAdapter -Confirm:$false"
    _powershell_cmd(script)
    # রেডিও অন করার জন্য অতিরিক্ত কমান্ড (উইন্ডোজ ১০/১১ এর জন্য)
    _powershell_cmd("Start-Service bthserv")
    return True

@handle_errors(return_on_error=False)
def disable_bluetooth() -> bool:
    # এটি ব্লুটুথ সার্ভিস বন্ধ করবে যা আইকন গায়েব না করেই কানেকশন অফ করবে
    script = "Get-NetAdapter -Name *Bluetooth* | Disable-NetAdapter -Confirm:$false"
    _powershell_cmd(script)
    _powershell_cmd("Stop-Service bthserv -Force")
    return True