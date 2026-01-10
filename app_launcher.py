"""
app_launcher.py - The Ultimate Version
Supports: EXE, Shortcuts, and Modern Store Apps (WhatsApp, Spotify, etc.)
"""
import os
import shutil
import subprocess
import sys
import webbrowser
from pathlib import Path

def _is_windows():
    return sys.platform == "win32"

# --- 1. SHORTCUT FINDER (For Start Menu Apps) ---
def _find_windows_shortcut(app_name):
    """
    Scans the Start Menu for shortcuts (.lnk files).
    This handles apps like YouTube PWA, Games, etc.
    """
    try:
        search_paths = [
            os.path.join(os.environ["APPDATA"], "Microsoft", "Windows", "Start Menu", "Programs"),
            os.path.join(os.environ["PROGRAMDATA"], "Microsoft", "Windows", "Start Menu", "Programs"),
            os.path.join(os.path.expanduser("~"), "AppData", "Roaming", "Microsoft", "Internet Explorer", "Quick Launch", "User Pinned", "TaskBar")
        ]
        
        target = app_name.lower().strip()
        for path in search_paths:
            if not os.path.exists(path): continue
            
            for root, _, files in os.walk(path):
                for file in files:
                    if target in file.lower() and file.endswith(".lnk"):
                        return os.path.join(root, file)
        return None
    except:
        return None

# --- 2. THE MAIN LAUNCHER ---
def open_app(app_name):
    name = app_name.lower().strip()
    
    # A. Special Protocols for Store Apps (The "Cheat Sheet")
    # এটা ব্যবহার করলে WhatsApp/Spotify ১০০% খুলবে।
    custom_protocols = {
        "whatsapp": "whatsapp://",
        "spotify": "spotify:",
        "messenger": "messenger:",
        "telegram": "tg://",
        "settings": "ms-settings:",
        "calculator": "calc",
        "notepad": "notepad",
        "camera": "microsoft.windows.camera:",
        "store": "ms-windows-store:",
        "netflix": "netflix:"
    }
    
    try:
        # Step 1: Check Custom Protocols first (Fastest)
        if name in custom_protocols:
            cmd = custom_protocols[name]
            # প্রোটোকল রান করা (যেমন whatsapp://)
            if "://" in cmd or ":" in cmd:
                webbrowser.open(cmd) 
            else:
                subprocess.Popen(cmd, shell=True)
            return True

        # Step 2: Search for Shortcuts (Start Menu)
        # আপনার পিন করা YouTube বা গেমগুলো এখান থেকে খুলবে
        shortcut = _find_windows_shortcut(name)
        if shortcut:
            os.startfile(shortcut)
            return True

        # Step 3: Check System PATH (Normal .exe files)
        path_exe = shutil.which(name)
        if path_exe:
            subprocess.Popen([path_exe], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return True

        # Step 4: Last Resort (Shell Execute)
        # তবে এরর পপ-আপ বন্ধ করার জন্য আমরা 'try' ব্যবহার করছি
        try:
            subprocess.Popen(f"start {name}", shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return True
        except:
            return False

    except Exception as e:
        print(f"[!] App Launch Error: {e}")
        return False

def close_app(app_name):
    try:
        # ভলান্টিয়ারি ক্লোজ
        os.system(f"taskkill /f /im {app_name}.exe /t")
        return True
    except:
        return False