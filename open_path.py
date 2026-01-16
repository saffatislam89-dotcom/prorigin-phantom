import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import List, Optional, Union

def _is_windows() -> bool:
    return sys.platform == "win32"

def _choose_linux_opener() -> Optional[str]:
    candidates = ("xdg-open", "gio", "gnome-open", "kde-open", "kde-open5")
    for cmd in candidates:
        if shutil.which(cmd):
            return cmd
    return None

def open_path(path: Union[str, os.PathLike]) -> bool:
    try:
        if not isinstance(path, (str, os.PathLike)):
            return False
        p = Path(path).expanduser().resolve(strict=True)
        if not (p.is_file() or p.is_dir()):
            return False
        
        if _is_windows():
            os.startfile(str(p))
            return True
        elif sys.platform == "darwin":
            subprocess.run(["open", str(p)], check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return True
        else:
            opener = _choose_linux_opener()
            if opener:
                subprocess.run([opener, str(p)], check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                return True
        return False
    except Exception:
        return False