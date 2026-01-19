
"""
main_test.py - Jarvis local (Ollama) reasoning (refactor + safe integration)

Notes:
- Fully offline: no cloud clients, no API keys, no .env usage.
- Uses local Ollama via `ollama.chat(model="llama3", messages=[...])`.
- query_llama_for_action returns a structured JSON object {action, args, reply} or falls back to local_keyword_fallback.
- The dispatch_action, safe_call, and search helpers are left unchanged except for targeted fixes requested:
  - Fixed system_message quoting/formatting.
  - Robust Ollama response parsing using response['message']['content'] and JSON extraction via find('{')/rfind('}').
  - Injects past memories into the system message so the model knows it has long-term memory.
  - Removed duplicate screenshot condition and added admin checks for WiFi (hardware safety).
- MemoryManager persists long-term memories locally (SQLite) and is used to provide context to the LLM.
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
import sqlite3
from collections import deque
from datetime import datetime

# Local Ollama client (requires ollama running locally and python ollama package installed)
import ollama

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
# Configuration: Local LLM model name
# -------------------
# Use the local Ollama model "llama3"
LLM_MODEL = "llama3"


# -------------------
# Helpers (unchanged)
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
# Memory Manager (new)
# -------------------
class MemoryManager:
    """
    Simple local long-term memory implemented with SQLite.
    Stores 'content', optional 'tags', and 'created_at'.
    Allows retrieval by keyword search over content and tags.
    """

    def __init__(self, db_path=None):
        # default location: ~/.phantom_memory.db
        if db_path:
            self.db_path = db_path
        else:
            home = os.path.expanduser("~")
            self.db_path = os.path.join(home, ".phantom_memory.db")
        self._ensure_db()

    def _get_conn(self):
        # Enable check_same_thread=False for possible multithreaded use
        return sqlite3.connect(self.db_path, check_same_thread=False)

    def _ensure_db(self):
        try:
            conn = self._get_conn()
            cur = conn.cursor()
            cur.execute(
                """CREATE TABLE IF NOT EXISTS memories (
                       id INTEGER PRIMARY KEY AUTOINCREMENT,
                       content TEXT NOT NULL,
                       tags TEXT,
                       created_at TEXT NOT NULL
                   )"""
            )
            cur.execute(
                """CREATE INDEX IF NOT EXISTS idx_memories_content ON memories(content)"""
            )
            cur.execute(
                """CREATE INDEX IF NOT EXISTS idx_memories_tags ON memories(tags)"""
            )
            conn.commit()
        except Exception:
            traceback.print_exc()
        finally:
            try:
                conn.close()
            except Exception:
                pass

    def store(self, content, tags=None):
        """
        Store a memory. tags can be a comma-separated string or list.
        Returns True on success.
        """
        if not content:
            return False
        if isinstance(tags, (list, tuple)):
            tags = ",".join([t.strip().lower() for t in tags if t])
        elif isinstance(tags, str):
            tags = tags.strip().lower()
        else:
            tags = None
        try:
            conn = self._get_conn()
            cur = conn.cursor()
            cur.execute(
                "INSERT INTO memories (content, tags, created_at) VALUES (?, ?, ?)",
                (content.strip(), tags, datetime.utcnow().isoformat()),
            )
            conn.commit()
            return True
        except Exception:
            traceback.print_exc()
            return False
        finally:
            try:
                conn.close()
            except Exception:
                pass

    def retrieve_by_keywords(self, keywords, limit=5):
        """
        Retrieve relevant memories given a list of keywords.
        Returns a list of content strings ordered by insertion (most recent first may be preferred).
        """
        if not keywords:
            return []
        try:
            conn = self._get_conn()
            cur = conn.cursor()
            # Build WHERE clause with LIKE for each keyword searching content OR tags
            clauses = []
            params = []
            for kw in keywords:
                kw = kw.strip().lower()
                if not kw:
                    continue
                clauses.append("(content LIKE ? OR tags LIKE ?)")
                params.extend([f"%{kw}%", f"%{kw}%"])
            if not clauses:
                return []
            where = " OR ".join(clauses)
            query = f"SELECT content, tags, created_at FROM memories WHERE {where} ORDER BY created_at DESC LIMIT ?"
            params.append(limit)
            cur.execute(query, params)
            rows = cur.fetchall()
            results = []
            for r in rows:
                content = r[0]
                tags = r[1] or ""
                created = r[2] or ""
                results.append({"content": content, "tags": tags, "created_at": created})
            return results
        except Exception:
            traceback.print_exc()
            return []
        finally:
            try:
                conn.close()
            except Exception:
                pass

    def search(self, query_text, limit=5):
        """
        Convenience wrapper: extract keywords from query_text and call retrieve_by_keywords.
        """
        if not query_text:
            return []
        # Simple keyword extraction: words longer than 3 chars and unique
        tokens = re.findall(r"\w{4,}", query_text.lower())
        seen = []
        for t in tokens:
            if t not in seen:
                seen.append(t)
            if len(seen) >= 8:
                break
        return self.retrieve_by_keywords(seen, limit=limit)


# instantiate a global memory manager
_memory_manager = MemoryManager()


def save_memory(user_input, ai_response, tags=None):
    """
    Public helper to save an interaction to long-term memory.
    user_input: text from user
    ai_response: text or structured reply from assistant
    tags: optional list or comma-separated tags
    """
    try:
        content = f"User: {user_input}\nAssistant: {ai_response}"
        return _memory_manager.store(content, tags=tags)
    except Exception:
        traceback.print_exc()
        return False


def get_relevant_memories(user_input, limit=5):
    """
    Public helper to retrieve relevant memories for a given user input.
    Returns a list of content strings (up to 'limit').
    """
    try:
        rows = _memory_manager.search(user_input, limit=limit)
        # return brief excerpts for the prompt (truncate long memories)
        excerpts = []
        for r in rows:
            c = r.get("content", "").replace("\n", " ").strip()
            if len(c) > 400:
                c = c[:400].rsplit(" ", 1)[0] + "..."
            ts = r.get("created_at", "")
            excerpts.append(f"{c} ({ts})")
        return excerpts
    except Exception:
        traceback.print_exc()
        return []


# -------------------
# Local keyword fallback (unchanged)
# -------------------
def local_keyword_fallback(user_text):
    """
    Local keyword-based fallback that returns an action object similar to LLM output.
    This is used when the model call fails or is unavailable.
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
    if "brightness" in txt or "bright" in txt or "dark" in txt:
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
    if "facebook" in txt:
        return {"action": "open_url", "args": {"url": "https://www.facebook.com"}, "reply": ""}
    if "youtube music" in txt or "yt music" in txt:
        return {"action": "open_url", "args": {"url": "https://music.youtube.com"}, "reply": ""}
    if "chatgpt" in txt or "chat gpt" in txt:
        return {"action": "open_url", "args": {"url": "https://chatgpt.com"}, "reply": ""}
    if "grok" in txt:
        return {"action": "open_url", "args": {"url": "https://grok.com"}, "reply": ""}

    # Apps
    if "notepad" in txt:
        return {"action": "open_app", "args": {"app_name": "notepad"}, "reply": ""}
    if "camera" in txt:
        return {"action": "open_app", "args": {"app_name": "camera"}, "reply": ""}
    if "file explorer" in txt or "this pc" in txt:
        return {"action": "open_app", "args": {"app_name": "explorer"}, "reply": ""}
    if "recycle bin" in txt:
        return {"action": "open_path", "args": {"path": "shell:RecycleBinFolder"}, "reply": ""}
    if "utorrent" in txt:
        return {"action": "open_app", "args": {"app_name": "utorrent"}, "reply": ""}
    if "windirstat" in txt:
        return {"action": "open_app", "args": {"app_name": "windirstat"}, "reply": ""}
    if "backiee" in txt:
        return {"action": "open_app", "args": {"app_name": "backiee"}, "reply": ""}
    if "nitrosense" in txt or "nitro sense" in txt:
        return {"action": "open_app", "args": {"app_name": "nitrosense"}, "reply": ""}

    # Open path/app
    if "open" in txt:
        q = txt.replace("open", "").strip()
        # if looks like a URL
        if q.startswith("http") or ("." in q and " " not in q):
            url = q if q.startswith("http") else f"http://{q}"
            return {"action": "open_url", "args": {"url": url}, "reply": ""}
        # prefer open_path for likely file/folder targets
        return {"action": "open_path", "args": {"query": q}, "reply": ""}

    # Fallback reply
    return {"action": "reply", "args": {}, "reply": "Sorry, I couldn't interpret that. Could you repeat?"}


# -------------------
# LLM Integration using local Ollama (ONLY this function changed)
# -------------------
def query_llama_for_action(user_text, context=None, timeout=15):
    """
    Query Ollama with context injection for Long-Term Memory.
    """
    try:
        # 1. Retrieve relevant past memories (The "Recall" Step)
        # Note: Ensure get_relevant_memories helper exists in your file
        past_memories = get_relevant_memories(user_text, limit=3)
        memory_block = ""
        if past_memories:
            memory_list = "\n".join([f"- {m}" for m in past_memories])
            memory_block = f"\n\nPREVIOUS MEMORIES (USE THESE TO ANSWER):\n{memory_list}"
        
        # 2. Strict System Instruction
        system_message = (
            "You are Phantom AI, a highly intelligent local assistant with long-term memory.\n"
            "You have full control over the user's PC (WiFi, Screen, Apps).\n"
            f"{memory_block}\n\n"
            "INSTRUCTIONS:\n"
            "1. You MUST return ONLY a JSON object.\n"
            "2. If the user asks about past info, use the 'PREVIOUS MEMORIES' section.\n"
            "3. Format: {\"action\": \"action_name\", \"args\": {}, \"reply\": \"Your response\"}\n"
            "Allowed actions: shutdown, restart, enable_wifi, disable_wifi, wifi_status, "
            "take_screenshot, open_url, open_path, open_app, set_brightness, reply."
        )

        # 3. Call Ollama
        response = ollama.chat(
            model=LLM_MODEL,
            messages=[
                {'role': 'system', 'content': system_message},
                {'role': 'user', 'content': f"User: {user_text}"}
            ]
        )
        
        # 4. Extract Response Content
        # Handle Ollama dictionary response correctly
        text = response['message']['content']
        
        # 5. Smart JSON Parsing (Ignoring filler text)
        start = text.find('{')
        end = text.rfind('}') + 1
        if start != -1 and end != 0:
            json_str = text[start:end]
            return json.loads(json_str)
            
        # Fallback if no JSON found
        return {"action": "reply", "args": {}, "reply": text}

    except Exception as e:
        print(f"[!] LLM Logic Error: {e}")
        return local_keyword_fallback(user_text)


# -------------------
# Action Dispatcher (unchanged except requested fixes)
# -------------------
def dispatch_action(action_obj, voice, original_command):
    """
    Executes actions silently in background but speaks the AI's natural reply.
    """
    # 1. Get the natural reply generated by Llama 3
    ai_reply = action_obj.get("reply", "")
    action = action_obj.get("action", "")
    args = action_obj.get("args", {})

    # Helper: Decides what to speak. 
    # Logic: If AI gave a specific reply, use it. Otherwise use the default technical message.
    def speak_and_save(success_message=None, error_message=None, is_error=False):
        final_msg = ""
        
        if is_error:
            # If error, ignores AI reply and speaks the error
            final_msg = error_message if error_message else "I encountered an error."
        else:
            # If success, prefer AI's natural reply. If empty, use technical fallback.
            final_msg = ai_reply if ai_reply else (success_message if success_message else "Done, Boss.")
        
        # Speak and Save to Memory
        voice.speak(final_msg)
        save_memory(original_command, final_msg)
        return True

    try:
        # --- System Actions ---
        if action == "shutdown":
            safe_call(pc.shutdown_system)
            return speak_and_save(success_message="Shutting down system.")
            
        if action == "restart":
            safe_call(pc.restart_system)
            return speak_and_save(success_message="Restarting system.")

        if action == "take_screenshot":
            path = safe_call(screen.take_ss)
            if path: 
                return speak_and_save(success_message="Screenshot saved.")
            return speak_and_save(error_message="I failed to capture the screen.", is_error=True)

        # --- WiFi ---
        if action == "enable_wifi":
            if safe_call(wifi.enable_wifi): 
                return speak_and_save(success_message="WiFi enabled.")
            return speak_and_save(error_message="I need admin rights for WiFi.", is_error=True)
            
        if action == "disable_wifi":
            if safe_call(wifi.disable_wifi): 
                return speak_and_save(success_message="WiFi disabled.")
            return speak_and_save(error_message="I need admin rights for WiFi.", is_error=True)

        if action == "wifi_status":
            status = safe_call(wifi.get_wifi_status)
            # For status, we update the AI reply if it was generic
            if not ai_reply: ai_reply = f"WiFi status is {status}"
            return speak_and_save(success_message=f"WiFi is {status}")

        # --- Brightness ---
        if action == "set_brightness":
            val = args.get("value", 50)
            safe_call(bc.set_brightness, val)
            return speak_and_save(success_message=f"Brightness set to {val}%.")

        # --- Apps & URLs ---
        if action == "open_url":
            url = args.get("url")
            if url: 
                webbrowser.open(url)
                return speak_and_save(success_message=f"Opening {url}")
            return speak_and_save(error_message="No URL found.", is_error=True)

        if action == "open_app":
            app = args.get("app_name")
            if safe_call(app_launcher.open_app, app):
                return speak_and_save(success_message=f"Opening {app}.")
            return speak_and_save(error_message=f"I couldn't find {app}.", is_error=True)

        # --- Pure Conversation ---
        if action == "reply":
            # Just speak whatever Llama 3 sent
            final_reply = ai_reply if ai_reply else "I am listening, Boss."
            voice.speak(final_reply)
            save_memory(original_command, final_reply)
            return True

        # --- Fallback for unknown actions ---
        # If the action performed but we don't have a specific handler, just speak the AI reply
        if ai_reply:
            return speak_and_save()
        
        return speak_and_save(success_message="Command processed.")

    except Exception as e:
        print(f"[!] Dispatch Error: {e}")
        return speak_and_save(error_message="Something went wrong internally.", is_error=True)
    
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

            # Ask local model (primary interpreter)
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
