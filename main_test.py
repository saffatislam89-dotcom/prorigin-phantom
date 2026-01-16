"""
main.py - Jarvis with Groq (llama-3.3-70b-versatile) reasoning (refactor + safe integration)

Notes:
- This file integrates the Groq SDK chat completions API to return a structured JSON action object.
- The Groq client is instantiated with the API key you provided.
- query_llama_for_action uses messages format and requests response_format {"type":"json_object"}.
- If the Groq API fails or parsing fails, the function falls back to local_keyword_fallback.
- The safe_call architecture and all existing module integrations remain unchanged.
"""

import time
import sys
import webbrowser
import os
import re
import ctypes
import traceback
import difflib
import json
from collections import deque

# HTTP client for compatibility (left as-is)
import requests

# Groq SDK client initialization (moved to top per request)
from groq import Groq

try:
    client = Groq(api_key="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")
except Exception as e:
    print(f"[!] Groq client initialization error: {e}")
    client = None

# Local modules (must exist in your project)
import power as pc
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


# -------------------
# Configuration: LLM (kept for compatibility; Groq client used directly)
# -------------------
LLM_MODEL = "llama-3.3-70b-versatile"


# -------------------
# Helpers
# -------------------
def is_admin():
    try:
        if os.name == "nt":
            return ctypes.windll.shell32.IsUserAnAdmin() != 0
        else:
            return os.geteuid() == 0
    except Exception:
        return False


def safe_call(fn, *args, default=None, **kwargs):
    """
    Call a function and catch any exception: return default on failure and log.
    This prevents the main loop from crashing if a module fails.
    """
    try:
        return fn(*args, **kwargs)
    except Exception as e:
        print(f"[!] Safe call error in {getattr(fn, '__name__', str(fn))}: {e}")
        traceback.print_exc()
        return default


def initialize_indexing_service():
    """
    Placeholder for a local, privacy-first indexing service.
    - Should run locally, encrypted on disk (no cloud).
    - Provides fast search for 'recent', 'last edited', etc.
    Implementation intentionally left out (placeholder).
    """
    return None


def find_folder_path_by_search(target_name, max_depth=2):
    """
    Fast BFS search from the user's home directory for the first folder/file that matches target_name.
    Short-circuits immediately on first match (very fast for small depth).
    """
    if not target_name:
        return None
    target = target_name.lower().strip()
    home_root = os.environ.get("USERPROFILE") or os.path.expanduser("~")

    # Quick-check standard folders
    standard_folders = {
        "desktop": os.path.join(home_root, "Desktop"),
        "downloads": os.path.join(home_root, "Downloads"),
        "documents": os.path.join(home_root, "Documents"),
        "pictures": os.path.join(home_root, "Pictures"),
        "music": os.path.join(home_root, "Music"),
        "videos": os.path.join(home_root, "Videos"),
    }
    for key, p in standard_folders.items():
        try:
            if key == target or target in key or key in target:
                if os.path.isdir(p):
                    return p
        except Exception:
            continue

    def is_match(name):
        try:
            dn = name.lower()
            if dn == target:
                return True
            if target in dn:
                return True
            # fuzzy match
            ratio = difflib.SequenceMatcher(None, target, dn).ratio()
            return ratio >= 0.65
        except Exception:
            return False

    # BFS with short-circuit: queue of (path, depth_left)
    queue = deque()
    queue.append((home_root, max_depth))
    while queue:
        current, depth_left = queue.popleft()
        try:
            with os.scandir(current) as it:
                for entry in it:
                    try:
                        if not entry.is_dir(follow_symlinks=False):
                            # also match files' names if requested (user might say a filename)
                            if is_match(entry.name):
                                return os.path.join(current, entry.name)
                            continue
                    except Exception:
                        continue
                    # entry is a directory candidate
                    if is_match(entry.name):
                        return os.path.join(current, entry.name)
                    if depth_left > 0:
                        queue.append((os.path.join(current, entry.name), depth_left - 1))
        except (PermissionError, FileNotFoundError):
            continue
        except Exception:
            traceback.print_exc()
            continue
    return None


# -------------------
# Local keyword fallback (unchanged)
# -------------------
def local_keyword_fallback(user_text):
    """
    Local keyword-based fallback that returns an action object similar to LLM output.
    This is used when the API call fails or is unavailable.
    """
    txt = (user_text or "").lower()
    # System
    if "shutdown" in txt or "power off" in txt:
        return {"action": "shutdown", "args": {}, "reply": ""}
    if "restart" in txt:
        return {"action": "restart", "args": {}, "reply": ""}
    if "sleep" in txt or "hibernate" in txt:
        return {"action": "sleep", "args": {}, "reply": ""}
    
    # WiFi
    if "turn on wifi" in txt or "enable wifi" in txt:
        return {"action": "enable_wifi", "args": {}, "reply": ""}
    if "turn off wifi" in txt or "disable wifi" in txt:
        return {"action": "disable_wifi", "args": {}, "reply": ""}
    if "wifi status" in txt or "is wifi" in txt:
        return {"action": "wifi_status", "args": {}, "reply": ""}

    # Screenshot
    if "screenshot" in txt or "screen shot" in txt:
        if "copy" in txt:
            return {"action": "copy_screenshot", "args": {}, "reply": ""}
        return {"action": "take_screenshot", "args": {}, "reply": ""}

    # Brightness
    if "brightness" in txt:
        if "increase" in txt or "brighter" in txt:
            return {"action": "increase_brightness", "args": {}, "reply": ""}
        if "decrease" in txt or "darker" in txt:
            return {"action": "decrease_brightness", "args": {}, "reply": ""}
        m = re.search(r'(\d{1,3})', txt)
        if m:
            try:
                v = int(m.group(1))
                return {"action": "set_brightness", "args": {"value": v}, "reply": ""}
            except Exception:
                pass
        return {"action": "reply", "args": {}, "reply": "Do you want me to increase or decrease the brightness, Boss?"}

    # Bluetooth
    if "turn on bluetooth" in txt or "enable bluetooth" in txt:
        return {"action": "enable_bluetooth", "args": {}, "reply": ""}
    if "turn off bluetooth" in txt or "disable bluetooth" in txt:
        return {"action": "disable_bluetooth", "args": {}, "reply": ""}
    if "bluetooth status" in txt or "is bluetooth" in txt:
        return {"action": "bluetooth_status", "args": {}, "reply": ""}

    # Open URL / website simple cases
    if "youtube" in txt:
        return {"action": "open_url", "args": {"url": "https://www.youtube.com"}, "reply": ""}
    if "google" in txt:
        return {"action": "open_url", "args": {"url": "https://www.google.com"}, "reply": ""}
    # --- Custom Websites & Apps from List ---
    
    # Facebook
    if "facebook" in txt:
        return {"action": "open_url", "args": {"url": "https://www.facebook.com"}, "reply": ""}
        
    # YouTube Music
    if "youtube music" in txt or "yt music" in txt:
        return {"action": "open_url", "args": {"url": "https://music.youtube.com"}, "reply": ""}
        
    # ChatGPT
    if "chatgpt" in txt or "chat gpt" in txt:
        return {"action": "open_url", "args": {"url": "https://chatgpt.com"}, "reply": ""}

    # Grok (xAI)
    if "grok" in txt:
        return {"action": "open_url", "args": {"url": "https://grok.com"}, "reply": ""}

    # Notepad
    if "notepad" in txt:
        return {"action": "open_app", "args": {"app_name": "notepad"}, "reply": ""}

    # Camera
    if "camera" in txt:
        return {"action": "open_app", "args": {"app_name": "camera"}, "reply": ""}
        
    # File Explorer
    if "file explorer" in txt or "this pc" in txt:
        return {"action": "open_app", "args": {"app_name": "explorer"}, "reply": ""}

    # Recycle Bin
    if "recycle bin" in txt:
        return {"action": "open_path", "args": {"path": "shell:RecycleBinFolder"}, "reply": ""}

    # uTorrent
    if "utorrent" in txt:
        return {"action": "open_app", "args": {"app_name": "utorrent"}, "reply": ""}

    # WinDirStat
    if "windirstat" in txt:
        return {"action": "open_app", "args": {"app_name": "windirstat"}, "reply": ""}

    # backiee (Wallpaper app)
    if "backiee" in txt:
        return {"action": "open_app", "args": {"app_name": "backiee"}, "reply": ""}
    
    # NitroSense
    if "nitrosense" in txt or "nitro sense" in txt:
        return {"action": "open_app", "args": {"app_name": "nitrosense"}, "reply": ""}

    # Open path/app
    if "open" in txt:
        q = txt.replace("open", "").strip()
        # if looks like a URL
        if q.startswith("http") or "." in q and " " not in q:
            url = q if q.startswith("http") else f"http://{q}"
            return {"action": "open_url", "args": {"url": url}, "reply": ""}
        # prefer open_path for likely file/folder targets
        return {"action": "open_path", "args": {"query": q}, "reply": ""}

    # Fallback reply
    return {"action": "reply", "args": {}, "reply": "Sorry, I couldn't interpret that. Could you repeat?"}


# -------------------
# LLM Integration using Groq SDK (refactored)
# -------------------
def query_llama_for_action(user_text, context=None, timeout=8):
    """
    Query the Groq LLM (llama-3.3-70b-versatile) for a structured action.

    Implementation details:
    - Uses messages format with system + user roles.
    - Requests response_format: {"type": "json_object"} so the model returns a clean JSON object.
    - If client is not initialized or the API call/parsing fails, falls back to local_keyword_fallback.
    - Returns dict with keys: action (str), args (dict), reply (str).
    """
    # Fallback if something goes wrong
    if client is None:
        print("[!] Groq client not available; using local keyword fallback.")
        return local_keyword_fallback(user_text)

    system_message = (
        "You are Jarvis' local reasoning assistant. You MUST return a single JSON object and NOTHING ELSE.\n"
        "Allowed actions and their meanings:\n"
        "- shutdown: shut down the system\n"
        "- restart: restart the system\n"
        "- sleep: put the system to sleep mode\n"
        "- enable_wifi / disable_wifi / wifi_status: manage/check WiFi\n"
        "- take_screenshot / copy_screenshot: screenshot operations\n"
        "- open_url: open a web URL (args.url)\n"
        "- open_path: open a local path or perform a smart search (args.path or args.query)\n"
        "- open_app / close_app: launch or close an application (args.app_name)\n"
        "- set_brightness / increase_brightness / decrease_brightness / max_brightness / min_brightness\n"
        "- enable_bluetooth / disable_bluetooth / bluetooth_status\n"
        "- reply: a conversational reply (args may be empty, reply contains the text)\n\n"
        "Return JSON object with keys: action (string), args (object), reply (string).\n"
        "Example: {\"action\":\"open_path\",\"args\":{\"query\":\"my resume\"},\"reply\":\"\"}\n"
        "Do not include any commentary outside the JSON. Use response_format json_object."
    )
    user_message = f"User said: {user_text}\n\nContext: {context or ''}"

    try:
        # Call Groq chat completions with messages and request JSON object response
        resp = client.chat.completions.create(
            model=LLM_MODEL,
            messages=[
                {"role": "system", "content": system_message},
                {"role": "user", "content": user_message},
            ],
            max_tokens=512,
            temperature=0.0,
            response_format={"type": "json_object"},
        )
    except Exception as e:
        print(f"[!] Groq API call failed: {e}")
        traceback.print_exc()
        return local_keyword_fallback(user_text)

    # Defensive parsing of the Groq SDK response
    try:
        # Many SDK shapes: try extracting textual content first
        text = None
        if hasattr(resp, "choices") and resp.choices:
            choice = resp.choices[0]
            # choice.message.content is common
            if hasattr(choice, "message") and getattr(choice.message, "content", None) is not None:
                text = choice.message.content
            elif getattr(choice, "content", None) is not None:
                text = choice.content
            elif getattr(choice, "text", None) is not None:
                text = choice.text

        # If resp itself is a dict-like with JSON, accept it directly
        if isinstance(resp, dict) and "action" in resp:
            return resp

        # Fallback to resp.text if available
        if text is None and hasattr(resp, "text"):
            text = resp.text

        if not text:
            # If the SDK returned a nested dict form, try to discover it
            try:
                if isinstance(resp, dict):
                    for field in ("output", "result", "response", "text"):
                        if field in resp:
                            candidate = resp[field]
                            if isinstance(candidate, dict) and "action" in candidate:
                                return candidate
                            if isinstance(candidate, str):
                                text = candidate
                                break
            except Exception:
                pass

        if not text:
            print("[!] Groq returned no textual content; falling back to local logic.")
            return local_keyword_fallback(user_text)

        text = text.strip()

        # Try to parse JSON object directly
        try:
            parsed = json.loads(text)
            if isinstance(parsed, dict) and "action" in parsed:
                return parsed
        except Exception:
            # Try to extract first {...} substring
            try:
                first_brace = text.find("{")
                last_brace = text.rfind("}")
                if first_brace != -1 and last_brace != -1 and last_brace > first_brace:
                    chunk = text[first_brace : last_brace + 1]
                    parsed = json.loads(chunk)
                    if isinstance(parsed, dict) and "action" in parsed:
                        return parsed
            except Exception:
                pass

        # If parsing failed, fallback to local keyword logic
        print("[!] Could not parse JSON from Groq response; falling back to local keyword logic.")
        try:
            print("Raw Groq response (snippet):", text[:1000])
        except Exception:
            pass
        return local_keyword_fallback(user_text)

    except Exception as e:
        print(f"[!] Error parsing Groq response: {e}")
        traceback.print_exc()
        return local_keyword_fallback(user_text)


# -------------------
# Action Dispatcher (unchanged)
# -------------------
def dispatch_action(action_obj, voice, original_command):
    """
    Map the structured action (from LLM or fallback) to local module functions.
    Every branch provides voice feedback and returns after execution.
    This function assumes all module calls should be made safe (safe_call).
    """
    action = (action_obj.get("action") or "").strip()
    args = action_obj.get("args") or {}
    reply = action_obj.get("reply") or ""

    # Helper to speak and return True (indicating handled)
    def speak_and_return(msg):
        try:
            voice.speak(msg)
        except Exception:
            print(f"[!] voice.speak failed for message: {msg}")
        return True

    # Map of actions to handlers:
    try:
        # System
        if action in ("shutdown",):
            safe_call(pc.shutdown_system)
            return speak_and_return("Shutting down the system, Boss. Goodbye!")

        if action in ("restart",):
            safe_call(pc.restart_system)
            return speak_and_return("Restarting the system, please wait.")
        if action == "sleep":
            safe_call(pc.sleep_system)
            return speak_and_return("Putting the system to sleep, Boss.")
        
        # WiFi
        if action == "enable_wifi":
            ok = safe_call(wifi.enable_wifi, default=False)
            if ok:
                return speak_and_return("WiFi enabled successfully, Boss.")
            else:
                return speak_and_return("I need administrator privileges to enable WiFi.")

        if action == "disable_wifi":
            ok = safe_call(wifi.disable_wifi, default=False)
            if ok:
                return speak_and_return("WiFi disabled successfully, Boss.")
            else:
                return speak_and_return("I need administrator privileges to disable WiFi.")

        if action == "wifi_status":
            status = safe_call(wifi.get_wifi_status, default=None)
            if status:
                return speak_and_return(f"WiFi is {status}, Boss.")
            else:
                return speak_and_return("Unable to check WiFi status.")

        # Screenshots
        if action == "take_screenshot" or action == "take_screenshot":
            path = safe_call(screen.take_ss, default=None)
            if path:
                return speak_and_return("Screenshot captured and saved, Boss.")
            else:
                return speak_and_return("Failed to capture the screenshot.")

        if action == "copy_screenshot":
            ok = safe_call(screen.copy_ss_to_clipboard, default=False)
            if ok:
                return speak_and_return("Copied to clipboard, Boss.")
            else:
                return speak_and_return("Failed to copy screenshot to clipboard.")

        # Brightness
        if action == "set_brightness":
            val = args.get("value")
            try:
                if val is None:
                    # try to infer numeric inside original command
                    m = re.search(r'(\d{1,3})', original_command)
                    if m:
                        val = int(m.group(1))
                val = int(val)
                val = max(10, min(100, val))
                safe_call(bc.set_brightness, val)
                return speak_and_return(f"Setting brightness to {val} percent, Boss")
            except Exception:
                return speak_and_return("I couldn't set brightness. Please specify a number between 10 and 100.")

        if action == "increase_brightness":
            try:
                cur = safe_call(bc.get_brightness, default=0) or 0
                cur = int(float(cur))
                new = min(100, cur + 20)
                safe_call(bc.set_brightness, new)
                return speak_and_return(f"Increasing brightness to {new} percent, Boss")
            except Exception:
                return speak_and_return("I couldn't increase brightness.")

        if action == "decrease_brightness":
            try:
                cur = safe_call(bc.get_brightness, default=100) or 100
                cur = int(float(cur))
                new = max(10, cur - 20)
                safe_call(bc.set_brightness, new)
                return speak_and_return(f"Decreasing brightness to {new} percent, Boss")
            except Exception:
                return speak_and_return("I couldn't decrease brightness.")

        if action in ("max_brightness", "maximum_brightness"):
            safe_call(bc.set_brightness, 100)
            return speak_and_return("Setting brightness to 100 percent, Boss")

        if action in ("min_brightness", "minimum_brightness"):
            safe_call(bc.set_brightness, 10)
            return speak_and_return("Setting brightness to 10 percent, Boss")

        # Bluetooth (requires admin)
        if action == "enable_bluetooth":
            if not is_admin():
                return speak_and_return("Boss, I need Administrator privileges to change hardware settings. Please restart VS Code as an Admin.")
            ok = safe_call(getattr(bt, "enable_bluetooth", lambda: False), default=False)
            if ok:
                return speak_and_return("Bluetooth is now on, Boss")
            else:
                return speak_and_return("I encountered an error while changing bluetooth settings")

        if action == "disable_bluetooth":
            if not is_admin():
                return speak_and_return("Boss, I need Administrator privileges to change hardware settings. Please restart VS Code as an Admin.")
            ok = safe_call(getattr(bt, "disable_bluetooth", lambda: False), default=False)
            if ok:
                return speak_and_return("Bluetooth has been disabled, Sir")
            else:
                return speak_and_return("I encountered an error while changing bluetooth settings")

        if action == "bluetooth_status":
            status = safe_call(getattr(bt, "get_bluetooth_status", lambda: None), default=None)
            if status is True:
                return speak_and_return("Bluetooth is currently enabled")
            elif status is False:
                return speak_and_return("Bluetooth is turned off")
            else:
                return speak_and_return("I am unable to access bluetooth settings on this device")

        # Open URL
        if action == "open_url":
            url = args.get("url")
            if url:
                try:
                    webbrowser.open(url)
                    return speak_and_return("Opening the requested website, Boss")
                except Exception:
                    return speak_and_return("I couldn't open that URL.")
            else:
                return speak_and_return("No URL provided.")

        # Open path or smart search (DEEP search integrated)
        if action == "open_path":
            # args may contain 'path' (explicit) or 'query' (vague)
            explicit_path = args.get("path")
            query = args.get("query") or args.get("name") or args.get("query_string") or ""
            target_path = None
            if explicit_path:
                target_path = os.path.expanduser(os.path.expandvars(explicit_path))
            else:
                # Use deep recursive os.walk search focused on Desktop/Downloads/Documents up to 3-4 layers deep.
                ql = (query or "").strip()
                if ql:
                    std_dirs = []
                    home_root = os.environ.get("USERPROFILE") or os.path.expanduser("~")
                    for d in ("Desktop", "Downloads", "Documents"):
                        p = os.path.join(home_root, d)
                        if os.path.isdir(p):
                            std_dirs.append(p)

                    # quick standard-name match first
                    for sd in std_dirs:
                        base = os.path.basename(sd).lower()
                        if ql.lower() == base or ql.lower() in base or base in ql.lower():
                            target_path = sd
                            break

                    # if not found, deep walk each std_dir with limited depth
                    if not target_path:
                        max_depth = 4
                        for root_dir in std_dirs:
                            try:
                                for root, dirs, files in os.walk(root_dir):
                                    # compute depth relative to root_dir
                                    rel = os.path.relpath(root, root_dir)
                                    depth = 0 if rel == "." else rel.count(os.sep) + 1
                                    if depth > max_depth:
                                        # skip walking deeper in this branch
                                        dirs[:] = []
                                        continue
                                    # check directory names
                                    for d in dirs:
                                        try:
                                            if ql.lower() in d.lower() or difflib.SequenceMatcher(None, ql.lower(), d.lower()).ratio() >= 0.65:
                                                candidate = os.path.join(root, d)
                                                target_path = candidate
                                                break
                                        except Exception:
                                            continue
                                    if target_path:
                                        break
                                    # also check files
                                    for f in files:
                                        try:
                                            if ql.lower() in f.lower() or difflib.SequenceMatcher(None, ql.lower(), f.lower()).ratio() >= 0.65:
                                                candidate = os.path.join(root, f)
                                                target_path = candidate
                                                break
                                        except Exception:
                                            continue
                                    if target_path:
                                        break
                                if target_path:
                                    break
                            except (PermissionError, FileNotFoundError):
                                continue
                            except Exception:
                                traceback.print_exc()
                                continue

                # as a last resort, try a shallow BFS search already available
                if not target_path:
                    found = find_folder_path_by_search(ql, max_depth=2)
                    if found:
                        target_path = found

            if not target_path:
                return speak_and_return("I could not find that path or access is denied.")
            ok = safe_call(op.open_path, target_path, default=False)
            if ok:
                return speak_and_return("Opening it for you, Boss")
            else:
                return speak_and_return("I could not find that path or access is denied")

        # Application launch / close
        if action == "open_app":
            app_name = args.get("app_name") or args.get("app") or args.get("what") or ""
            if not app_name:
                return speak_and_return("Which application should I open, Boss?")
            if app_launcher is None:
                return speak_and_return("Application launcher not available on this system.")
            ok = safe_call(app_launcher.open_app, app_name, default=False)
            if ok:
                return speak_and_return(f"Opening {app_name}, Boss.")
            else:
                return speak_and_return(f"Searching... I couldn't find {app_name} locally.")

        if action == "close_app":
            app_name = args.get("app_name") or args.get("app") or ""
            if not app_name:
                return speak_and_return("Which application should I close, Boss?")
            ok = safe_call(getattr(app_launcher, "close_app", lambda _ : False), app_name, default=False)
            if ok:
                return speak_and_return(f"Closed {app_name}, Boss.")
            else:
                return speak_and_return(f"I couldn't close {app_name}.")

        # If action is 'reply' or unknown, speak reply text or fallback to a conversational LLM reply
        if action == "reply":
            if reply:
                return speak_and_return(reply)
            # If no reply text, fall back to safe conversational fallback
            return speak_and_return("I am here, Boss. Could you please clarify?")

        # Unknown action: provide a conversational fallback (try to use reply)
        if reply:
            return speak_and_return(reply)

        # If we reach here, we didn't map the action
        return speak_and_return("I couldn't map your request to a local action. Ask me something else.")

    except Exception as e:
        print(f"[!] dispatch_action error: {e}")
        traceback.print_exc()
        try:
            voice.speak("An error occurred while processing your request.")
        except Exception:
            pass
        return True


# -------------------
# Main loop (unchanged)
# -------------------
def start_jarvis():
    if JarvisVoiceEngine is None:
        print("[!] Jarvis voice engine missing.")
        return
    try:
        voice = JarvisVoiceEngine()
    except Exception as e:
        print(f"[!] Engine Error: {e}")
        traceback.print_exc()
        return

    # Initialize (privacy-first) indexing service if/when implemented
    initialize_indexing_service()

    voice.greet()

    while True:
        try:
            raw_command = voice.listen()
            if not raw_command or len(raw_command.strip()) < 2:
                continue

            command = raw_command.strip()
            normalized_command = re.sub(r"\s+", " ", command.lower().replace("-", " ")).strip()
            print(f">>> Recognized: {command}")

            # Priority quick-exit (local quick checks prior to LLM to save latency)
            if any(word in normalized_command for word in ["goodbye", "stop", "exit"]):
                voice.speak("Shutting down. Goodbye, Boss.")
                break

            # Ask LLM (primary interpreter)
            # Provide a short context: list of available modules and their capabilities
            context = (
                "Available local actions: shutdown, restart, enable_wifi, disable_wifi, wifi_status, "
                "take_screenshot, copy_screenshot, open_url, open_path, open_app, close_app, "
                "set_brightness (value), increase_brightness, decrease_brightness, max_brightness, min_brightness, "
                "enable_bluetooth, disable_bluetooth, bluetooth_status. "
                "If user intent is conversational, return action: reply with reply text."
            )

            action_obj = query_llama_for_action(command, context=context, timeout=6)

            # dispatch_action will execute the mapped function and speak the result.
            handled = dispatch_action(action_obj, voice, command)
            # Ensure the loop continues after action
            continue

        except Exception as e:
            print(f"[!] Main loop error: {e}")
            traceback.print_exc()
            # Continue listening despite the error
            continue

        finally:
            # small pause to be friendly to CPU
            time.sleep(0.05)


if __name__ == "__main__":
    start_jarvis()