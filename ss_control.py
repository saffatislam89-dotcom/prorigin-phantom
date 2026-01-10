"""
Screenshot Control Module for Windows 10/11
Provides functionality to capture screenshots and copy them to clipboard.
"""

import os
import io
import subprocess
from pathlib import Path
from datetime import datetime
from typing import Optional

try:
    from PIL import Image, ImageGrab
except ImportError:
    raise ImportError("Pillow (PIL) is required. Install it using: pip install Pillow")

try:
    import pyautogui
except ImportError:
    raise ImportError("pyautogui is required. Install it using: pip install pyautogui")

pyautogui.FAILSAFE = False


def _ensure_screenshots_folder() -> Optional[Path]:
    screenshots_dir = Path("Screenshots")
    try:
        screenshots_dir.mkdir(exist_ok=True)
        return screenshots_dir
    except Exception as e:
        print(f"Error creating Screenshots folder: {str(e)}")
        return None


def _generate_filename() -> str:
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    return f"Jarvis_SS_{timestamp}.png"


def take_ss() -> Optional[str]:
    try:
        screenshots_dir = _ensure_screenshots_folder()
        if not screenshots_dir:
            return None

        screenshot = pyautogui.screenshot()
        filename = _generate_filename()
        filepath = screenshots_dir / filename
        screenshot.save(str(filepath), "PNG")

        return str(filepath.absolute())

    except Exception as e:
        print(f"Error taking screenshot: {str(e)}")
        return None


def copy_ss_to_clipboard() -> bool:
    try:
        screenshot = pyautogui.screenshot()

        if _copy_via_powershell(screenshot):
            return True

        return _copy_via_ctypes(screenshot)

    except Exception as e:
        print(f"Error copying screenshot to clipboard: {str(e)}")
        return False


def _copy_via_powershell(image: Image.Image) -> bool:
    try:
        import tempfile

        # Windows-friendly temporary path using Path and .absolute()
        with tempfile.NamedTemporaryFile(suffix=".bmp", delete=False) as tmp:
            tmp_path = str(Path(tmp.name).absolute()).replace("\\", "\\\\")
            image.save(tmp.name, "BMP")

        try:
            # Fixed PowerShell Command with proper Add-Type for newer Windows 10/11
            ps_command = f'''
Add-Type -AssemblyName System.Windows.Forms
$image = [System.Drawing.Image]::FromFile("{tmp_path}")
[System.Windows.Forms.Clipboard]::SetImage($image)
$image.Dispose()
'''

            result = subprocess.run(
                ["powershell", "-NoProfile", "-Command", ps_command],
                capture_output=True,
                timeout=5,
                check=False
            )

            return result.returncode == 0

        finally:
            if os.path.exists(tmp.name):
                os.remove(tmp.name)

    except Exception as e:
        print(f"PowerShell method error: {str(e)}")
        return False


def _copy_via_ctypes(image: Image.Image) -> bool:
    try:
        import ctypes

        bmp_buffer = io.BytesIO()
        image.save(bmp_buffer, format="BMP")
        bmp_data = bmp_buffer.getvalue()
        dib_data = bmp_data[14:]

        CF_DIB = 8

        if not ctypes.windll.user32.OpenClipboard(None):
            return False

        try:
            ctypes.windll.user32.EmptyClipboard()

            hglobal = ctypes.windll.kernel32.GlobalAlloc(0x0002, len(dib_data))
            if not hglobal:
                return False

            lpvoid = ctypes.windll.kernel32.GlobalLock(hglobal)
            if not lpvoid:
                ctypes.windll.kernel32.GlobalFree(hglobal)
                return False

            ctypes.memmove(lpvoid, dib_data, len(dib_data))
            ctypes.windll.kernel32.GlobalUnlock(hglobal)

            return bool(ctypes.windll.user32.SetClipboardData(CF_DIB, hglobal))

        finally:
            ctypes.windll.user32.CloseClipboard()

    except Exception as e:
        print(f"Error copying screenshot to clipboard: {str(e)}")
        return False


def main():
    print("=" * 60)
    print("Screenshot Control Module - Windows 10/11")
    print("=" * 60)

    print("\n[1] Taking screenshot and saving to file...")
    path = take_ss()
    print("SUCCESS" if path else "FAILED")

    print("\n[2] Taking screenshot and copying to clipboard...")
    print("SUCCESS" if copy_ss_to_clipboard() else "FAILED")

    print("\n" + "=" * 60)


if __name__ == "__main__":
    main()