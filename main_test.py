"""
main.py - The Brain of Jarvis
"""
import time
import sys
import webbrowser
import os
import re
import ctypes
import traceback
import difflib

import power as pc  # এই লাইনটি না থাকলে pc. কমান্ড কাজ করবে না
import wifi_controller as wifi
import ss_control as screen
import brightness_control as bc
import bluetooth_controller as bt
import open_path as op

try:
    from jarvis_voice_engine import JarvisVoiceEngine
    import app_launcher
except ImportError as e:
    print(f"[!] Critical Error: {e}")
    sys.exit(1)


def is_admin():
    """
    Return True if the current process has administrator/root privileges.
    Works on Windows and Unix-like systems.
    """
    try:
        if os.name == "nt":
            # On Windows, IsUserAnAdmin() returns non-zero for admin
            return ctypes.windll.shell32.IsUserAnAdmin() != 0
        else:
            # On Unix-like, UID 0 is root
            return os.geteuid() == 0
    except Exception:
        # If anything goes wrong, be conservative and treat as non-admin
        return False


def find_folder_path_by_search(target_name, max_depth=2):
    """
    Search user's home for a folder matching target_name with a shallow depth.
    Returns the first matching full path or None.
    Matching strategy:
      - exact name (case-insensitive)
      - name contains target_name (case-insensitive)
      - fuzzy close match on folder name (difflib, cutoff 0.6)
    """
    home_root = os.environ.get("USERPROFILE") or os.path.expanduser("~")
    target_lower = (target_name or "").lower().strip()

    def is_match(dir_name):
        dn = dir_name.lower()
        if dn == target_lower:
            return True
        if target_lower in dn:
            return True
        # fuzzy match
        ratio = difflib.SequenceMatcher(None, target_lower, dn).ratio()
        if ratio >= 0.6:
            return True
        return False

    try:
        # Check top-level directories first
        try:
            with os.scandir(home_root) as it:
                for entry in it:
                    try:
                        if entry.is_dir(follow_symlinks=False) and is_match(entry.name):
                            return os.path.join(home_root, entry.name)
                    except PermissionError:
                        continue
        except FileNotFoundError:
            return None

        # Depth-limited search
        def scan_dir(current_path, depth_left):
            if depth_left < 0:
                return None
            try:
                with os.scandir(current_path) as it:
                    for entry in it:
                        if not entry.is_dir(follow_symlinks=False):
                            continue
                        try:
                            if is_match(entry.name):
                                return os.path.join(current_path, entry.name)
                        except PermissionError:
                            continue
                    if depth_left > 0:
                        with os.scandir(current_path) as it2:
                            for entry2 in it2:
                                if entry2.is_dir(follow_symlinks=False):
                                    found = scan_dir(os.path.join(current_path, entry2.name), depth_left - 1)
                                    if found:
                                        return found
            except (PermissionError, FileNotFoundError):
                return None
            return None

        return scan_dir(home_root, max_depth)
    except Exception:
        return None


def start_jarvis():
    try:
        voice = JarvisVoiceEngine()
    except Exception as e:
        print(f"[!] Engine Error: {e}")
        return

    voice.greet()

    while True:
        try:
            raw_command = voice.listen()
            if not raw_command or len(raw_command.strip()) < 2:
                continue

            # Keep original for logging; use normalized_command for all recognition tests
            command = raw_command.strip()
            normalized_command = command.lower().replace("-", "").strip()
            print(f">>> Recognized: {command}")

            # --- EXIT EARLY ---
            if any(word in normalized_command for word in ["goodbye", "stop", "exit"]):
                voice.speak("Shutting down. Goodbye, Boss.")
                break

            # --- SYSTEM CONTROLS (high priority) ---
            if "shutdown the system" in normalized_command or "power off" in normalized_command:
                voice.speak("Shutting down the system, Boss. Goodbye!")
                pc.shutdown_system()
                continue

            if "restart the system" in normalized_command or "restart" == normalized_command:
                voice.speak("Restarting the system, please wait.")
                pc.restart_system()
                continue

            if "sleep the system" in normalized_command or "sleep" in normalized_command:
                voice.speak("Putting the system to sleep.")
                pc.sleep_system()
                continue

            # --- WIFI CONTROLS ---
            if "turn on wifi" in normalized_command or "enable wifi" in normalized_command:
                if wifi.enable_wifi():
                    voice.speak("WiFi enabled successfully, Boss.")
                else:
                    voice.speak("I need administrator privileges to enable WiFi.")
                continue

            if "turn off wifi" in normalized_command or "disable wifi" in normalized_command:
                if wifi.disable_wifi():
                    voice.speak("WiFi disabled successfully, Boss.")
                else:
                    voice.speak("I need administrator privileges to disable WiFi.")
                continue

            if "wifi status" in normalized_command or "is wifi" in normalized_command:
                status = wifi.get_wifi_status()
                if status:
                    voice.speak(f"WiFi is {status}, Boss.")
                else:
                    voice.speak("Unable to check WiFi status.")
                continue

            # --- BLUETOOTH CONTROLS (with admin check) ---
            if "turn on bluetooth" in normalized_command or "enable bluetooth" in normalized_command:
                if not is_admin():
                    voice.speak("Boss, I need Administrator privileges to change hardware settings. Please restart VS Code as an Admin.")
                    continue
                if not hasattr(bt, "enable_bluetooth"):
                    voice.speak("Bluetooth controller is not available on this device")
                    continue
                try:
                    ok = bt.enable_bluetooth()
                    if ok is True:
                        voice.speak("Bluetooth is now on, Boss")
                    elif ok is False:
                        voice.speak("I encountered an error while changing bluetooth settings")
                    else:
                        voice.speak("I encountered an error while changing bluetooth settings")
                except Exception as e:
                    print(f"[!] Bluetooth Error (enable): {e}")
                    traceback.print_exc()
                    voice.speak("Boss, I need Administrator privileges to change hardware settings. Please restart VS Code as an Admin.")
                continue

            if "turn off bluetooth" in normalized_command or "disable bluetooth" in normalized_command:
                if not is_admin():
                    voice.speak("Boss, I need Administrator privileges to change hardware settings. Please restart VS Code as an Admin.")
                    continue
                if not hasattr(bt, "disable_bluetooth"):
                    voice.speak("Bluetooth controller is not available on this device")
                    continue
                try:
                    ok = bt.disable_bluetooth()
                    if ok is True:
                        voice.speak("Bluetooth has been disabled, Sir")
                    elif ok is False:
                        voice.speak("I encountered an error while changing bluetooth settings")
                    else:
                        voice.speak("I encountered an error while changing bluetooth settings")
                except Exception as e:
                    print(f"[!] Bluetooth Error (disable): {e}")
                    traceback.print_exc()
                    voice.speak("Boss, I need Administrator privileges to change hardware settings. Please restart VS Code as an Admin.")
                continue

            if "is bluetooth on" in normalized_command or "check bluetooth status" in normalized_command:
                if not hasattr(bt, "get_bluetooth_status"):
                    voice.speak("Bluetooth controller is not available on this device")
                    continue
                try:
                    status = bt.get_bluetooth_status()
                    if status is True:
                        voice.speak("Bluetooth is currently enabled")
                    elif status is False:
                        voice.speak("Bluetooth is turned off")
                    else:
                        voice.speak("I am unable to access bluetooth settings on this device")
                except Exception as e:
                    print(f"[!] Bluetooth Error (status): {e}")
                    traceback.print_exc()
                    voice.speak("I am unable to access bluetooth settings on this device")
                continue

            # --- SCREENSHOT CONTROLS ---
            if "take a screenshot" in normalized_command or "capture the screen" in normalized_command:
                try:
                    path = screen.take_ss()
                    if path:
                        voice.speak("Screenshot captured and saved to your folder, Boss.")
                    else:
                        voice.speak("Failed to capture the screenshot.")
                except Exception as e:
                    print(f"[!] Screenshot Error: {e}")
                    traceback.print_exc()
                    voice.speak("An error occurred while taking the screenshot.")
                continue

            if "copy screenshot" in normalized_command or "copy the screenshot" in normalized_command:
                try:
                    if screen.copy_ss_to_clipboard():
                        voice.speak("Copied to clipboard, Sir.")
                    else:
                        voice.speak("Failed to copy screenshot to clipboard.")
                except Exception as e:
                    print(f"[!] Clipboard Error: {e}")
                    traceback.print_exc()
                    voice.speak("An error occurred while copying to clipboard.")
                continue

            # --- OPEN PATH / FOLDER HANDLING (intelligent) ---
            # Trigger when user explicitly says open + (folder/directory/path or known folder name)
            if re.search(r'\bopen\b', normalized_command) and any(
                k in normalized_command
                for k in ["folder", "directory", "path", "downloads", "documents", "desktop", "pictures", "music", "videos"]
            ):
                try:
                    # Robust extraction: supports:
                    # "open downloads folder", "open my downloads", "open the downloads", "open downloads"
                    # also supports quoted paths: open "C:\some path"
                    folder_name = None
                    # If user provided an explicit path (contains :\ on Windows or leading / on Unix)
                    explicit_path_match = re.search(r'open\s+(?:the |my |a |an )?[\'"]?(?P<path>([a-zA-Z]:\\|/)[^\'"]+)[\'"]?', normalized_command)
                    if explicit_path_match:
                        candidate = explicit_path_match.group("path")
                        target_path = os.path.expanduser(os.path.expandvars(candidate))
                    else:
                        # capture token after open and before optional word folder/directory/path
                        folder_match = re.search(
                            r'open\s+(?:the |my |a |an )?(?P<name>[\w\s\-\.\']+?)(?:\s+(?:folder|directory|path))?(?:\s|$)',
                            normalized_command,
                        )
                        if folder_match:
                            folder_name = folder_match.group("name").strip().strip("'").strip('"')
                        # fallback to keyword search
                        if not folder_name:
                            for k in ["downloads", "documents", "desktop", "pictures", "music", "videos"]:
                                if k in normalized_command:
                                    folder_name = k
                                    break

                        if not folder_name:
                            voice.speak("Which folder would you like me to open, Boss?")
                            continue

                        # map standard folders first
                        standard_folders = {
                            "desktop": os.path.expanduser("~/Desktop"),
                            "downloads": os.path.expanduser("~/Downloads"),
                            "documents": os.path.expanduser("~/Documents"),
                            "pictures": os.path.expanduser("~/Pictures"),
                            "music": os.path.expanduser("~/Music"),
                            "videos": os.path.expanduser("~/Videos"),
                        }

                        lname = folder_name.lower()
                        target_path = None

                        # direct and substring matches
                        for key, p in standard_folders.items():
                            if lname == key or key in lname or lname in key:
                                if os.path.isdir(p):
                                    target_path = p
                                    break

                        # fuzzy match against standard folders
                        if target_path is None:
                            keys = list(standard_folders.keys())
                            close = difflib.get_close_matches(lname, keys, n=1, cutoff=0.6)
                            if close:
                                candidate = close[0]
                                p = standard_folders.get(candidate)
                                if p and os.path.isdir(p):
                                    target_path = p

                        # if still not found, search home shallowly
                        if target_path is None:
                            found = find_folder_path_by_search(lname, max_depth=2)
                            if found:
                                target_path = found

                    if not target_path:
                        voice.speak("I couldn't find a folder with that name on your system.")
                        continue

                    # make sure open_path is available
                    if not hasattr(op, "open_path"):
                        voice.speak("Path opener module is not available on this device.")
                        continue

                    try:
                        ok = op.open_path(target_path)
                    except ImportError as ie:
                        if "os_capabilities" in str(ie):
                            print(f"[!] open_path ImportError: {ie}")
                            traceback.print_exc()
                            voice.speak("I cannot access OS capabilities. Please ensure os_capabilities.py is present.")
                            continue
                        else:
                            print(f"[!] open_path ImportError: {ie}")
                            traceback.print_exc()
                            voice.speak("I could not open that path due to an import error.")
                            continue
                    except Exception as e:
                        print(f"[!] open_path Error: {e}")
                        traceback.print_exc()
                        voice.speak("I could not find that path or access is denied.")
                        continue

                    if ok is True:
                        voice.speak("Opening it for you, Boss")
                    else:
                        voice.speak("I could not find that path or access is denied")
                except Exception as e:
                    print(f"[!] Open Path Handling Error: {e}")
                    traceback.print_exc()
                    voice.speak("An error occurred while trying to open the path.")
                continue

            # --- BRIGHTNESS CONTROLS (use normalized_command consistently) ---
            m = re.search(r'set brightness to\s+(\d{1,3})', normalized_command)
            if m:
                try:
                    value = int(m.group(1))
                    value = max(10, min(100, value))
                    bc.set_brightness(value)
                    voice.speak(f"Setting brightness to {value} percent, Boss")
                except Exception as e:
                    print(f"[!] Brightness Error (set): {e}")
                    traceback.print_exc()
                    voice.speak("Sorry, brightness control is not supported on this device.")
                continue

            if 'increase brightness' in normalized_command:
                try:
                    cur = bc.get_brightness()
                    cur = int(float(cur))
                    new = min(100, cur + 20)
                    bc.set_brightness(new)
                    voice.speak(f"Increasing brightness to {new} percent, Boss")
                except Exception as e:
                    print(f"[!] Brightness Error (increase): {e}")
                    traceback.print_exc()
                    voice.speak("Sorry, brightness control is not supported on this device.")
                continue

            if 'decrease brightness' in normalized_command:
                try:
                    cur = bc.get_brightness()
                    cur = int(float(cur))
                    new = max(10, cur - 20)
                    bc.set_brightness(new)
                    voice.speak(f"Decreasing brightness to {new} percent, Boss")
                except Exception as e:
                    print(f"[!] Brightness Error (decrease): {e}")
                    traceback.print_exc()
                    voice.speak("Sorry, brightness control is not supported on this device.")
                continue

            if 'maximum brightness' in normalized_command or 'max brightness' in normalized_command:
                try:
                    bc.set_brightness(100)
                    voice.speak("Setting brightness to 100 percent, Boss")
                except Exception as e:
                    print(f"[!] Brightness Error (max): {e}")
                    traceback.print_exc()
                    voice.speak("Sorry, brightness control is not supported on this device.")
                continue

            if 'minimum brightness' in normalized_command or 'min brightness' in normalized_command:
                try:
                    bc.set_brightness(10)
                    voice.speak("Setting brightness to 10 percent, Boss")
                except Exception as e:
                    print(f"[!] Brightness Error (min): {e}")
                    traceback.print_exc()
                    voice.speak("Sorry, brightness control is not supported on this device.")
                continue

            # --- WEBSITES (explicit phrases first) ---
            if "youtube music" in normalized_command:
                voice.speak("Opening YouTube Music, Boss.")
                webbrowser.open("https://music.youtube.com")
                continue

            if re.search(r'\bopen (?:youtube|open youtube)\b', normalized_command):
                voice.speak("Opening YouTube, Boss.")
                webbrowser.open("https://www.youtube.com")
                continue

            if re.search(r'\bopen (?:google|open google)\b', normalized_command):
                voice.speak("Opening Google, Boss.")
                webbrowser.open("https://www.google.com")
                continue

            if re.search(r'\bopen (?:facebook|open facebook)\b', normalized_command):
                voice.speak("Opening Facebook, Boss.")
                webbrowser.open("https://www.facebook.com")
                continue

            # --- APPLICATION LAUNCH (generic) ---
            # Only trigger if command starts with open and wasn't handled by open-path earlier
            m_open_app = re.match(r'^\s*open\s+(?P<what>.+)$', normalized_command)
            if m_open_app:
                what = m_open_app.group("what").strip()
                # Avoid interpreting known folder names as apps (they were handled above)
                known_folder_keywords = {"folder", "directory", "path", "downloads", "documents", "desktop", "pictures", "music", "videos"}
                if not any(k in what for k in known_folder_keywords):
                    # speak original 'what' with original capitalization where possible
                    # map 'what' to text from original command (simple heuristic)
                    orig_what = command[len(command.lower().find("open")) + 4 :].strip() if "open" in command.lower() else what
                    app_name = orig_what or what
                    voice.speak(f"Opening {app_name}, Boss.")
                    try:
                        if not app_launcher.open_app(app_name):
                            voice.speak(f"Searching... I couldn't find {app_name}.")
                    except Exception as e:
                        print(f"[!] App Launcher Error: {e}")
                        traceback.print_exc()
                        voice.speak(f"Unable to open {app_name}.")
                    continue

            # --- CLOSE / TERMINATE APPS ---
            if any(word in normalized_command for word in ["close", "terminate"]):
                # try to extract app name
                close_match = re.search(r'(?:close|terminate)\s+(?:the |my |a |an )?(?P<app>.+)$', normalized_command)
                if close_match:
                    app_name = close_match.group("app").strip()
                    voice.speak(f"Closing {app_name}, Boss.")
                    try:
                        app_launcher.close_app(app_name)
                    except Exception as e:
                        print(f"[!] Close App Error: {e}")
                        traceback.print_exc()
                        voice.speak(f"I couldn't close {app_name}.")
                else:
                    voice.speak("Which application should I close, Boss?")
                continue

            # If we reach here, no known command matched; small idle delay
        except Exception as e:
            print(f"[!] Loop Error: {e}")
            traceback.print_exc()
            continue

        time.sleep(0.1)


if __name__ == "__main__":
    start_jarvis()