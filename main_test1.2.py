"""
main_test1.2.py - Jarvis local (Ollama) with Phantom Security & Live Dashboard
"""

import threading
from phantom_observer import start_monitoring
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

# Local Ollama client
import ollama

# Local modules
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
# Global Configuration & Status
# -------------------
LLM_MODEL = "llama3"
current_security_status = "System Secure"
global_voice_engine = None # For background threads to access speech

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
    try:
        return fn(*args, **kwargs)
    except Exception as e:
        print(f"[!] Safe call error in {getattr(fn, '__name__', str(fn))}: {e}")
        traceback.print_exc()
        return default

def initialize_indexing_service():
    return None

def find_folder_path_by_search(target_name, max_depth=2):
    if not target_name: return None
    target = target_name.lower().strip()
    home_root = os.environ.get("USERPROFILE") or os.path.expanduser("~")
    
    standard_folders = {
        "desktop": os.path.join(home_root, "Desktop"),
        "downloads": os.path.join(home_root, "Downloads"),
        "documents": os.path.join(home_root, "Documents"),
        "pictures": os.path.join(home_root, "Pictures"),
        "music": os.path.join(home_root, "Music"),
        "videos": os.path.join(home_root, "Videos"),
    }
    for key, p in standard_folders.items():
        if key in target or target in key:
            if os.path.isdir(p): return p

    # BFS Search Logic...
    queue = deque()
    queue.append((home_root, max_depth))
    while queue:
        current, depth_left = queue.popleft()
        try:
            with os.scandir(current) as it:
                for entry in it:
                    if entry.name.lower() == target or target in entry.name.lower():
                        return os.path.join(current, entry.name)
                    if entry.is_dir() and depth_left > 0:
                        queue.append((entry.path, depth_left - 1))
        except: continue
    return None

# -------------------
# Memory Manager
# -------------------
class MemoryManager:
    def __init__(self, db_path=None):
        if db_path: self.db_path = db_path
        else:
            home = os.path.expanduser("~")
            self.db_path = os.path.join(home, ".phantom_memory.db")
        self._ensure_db()

    def _get_conn(self):
        return sqlite3.connect(self.db_path, check_same_thread=False)

    def _ensure_db(self):
        try:
            conn = self._get_conn()
            cur = conn.cursor()
            cur.execute("""CREATE TABLE IF NOT EXISTS memories (
                           id INTEGER PRIMARY KEY AUTOINCREMENT,
                           content TEXT NOT NULL, tags TEXT, created_at TEXT NOT NULL)""")
            conn.commit()
            conn.close()
        except: pass

    def store(self, content, tags=None):
        try:
            conn = self._get_conn()
            conn.execute("INSERT INTO memories (content, tags, created_at) VALUES (?, ?, ?)",
                         (content.strip(), tags, datetime.utcnow().isoformat()))
            conn.commit()
            conn.close()
            return True
        except: return False

    def search(self, query_text, limit=5):
        try:
            conn = self._get_conn()
            cur = conn.cursor()
            cur.execute("SELECT content FROM memories WHERE content LIKE ? ORDER BY created_at DESC LIMIT ?", 
                        (f"%{query_text}%", limit))
            rows = cur.fetchall()
            conn.close()
            return [{"content": r[0]} for r in rows]
        except: return []

_memory_manager = MemoryManager()

def save_memory(user_input, ai_response):
    _memory_manager.store(f"User: {user_input}\nAssistant: {ai_response}")

def get_relevant_memories(user_input, limit=3):
    rows = _memory_manager.search(user_input, limit)
    return [r['content'] for r in rows]

# -------------------
# Security Alert Callback
# -------------------
def security_alert(text):
    global current_security_status
    
    # 1. Update the live dashboard status
    file_name = text.split(":")[-1].strip() if ":" in text else "Unknown"
    current_security_status = f"THREAT DETECTED: {file_name}"
    
    # 2. Print Alert
    print(f"\n\n[!] SECURITY SHIELD: {current_security_status}")
    
    # 3. Speak Alert (using global engine reference if available)
    if global_voice_engine:
        global_voice_engine.speak(text)
    
    # 4. Reset Status after short delay logic (handled in loop usually, but we reset generic here)
    time.sleep(2) 
    current_security_status = "System Secure"

# -------------------
# Local Keyword Fallback
# -------------------
def local_keyword_fallback(user_text):
    txt = (user_text or "").lower()
    
    # --- VAULT COMMANDS (New) ---
    if "open security vault" in txt or "show my vault" in txt or "open vault" in txt:
        vault_path = os.path.join(os.path.expanduser("~"), ".jarvis_secure_vault")
        if os.path.exists(vault_path):
            return {"action": "open_path", "args": {"query": vault_path}, "reply": "Opening your secure data vault, Sir."}
        else:
            return {"action": "reply", "args": {}, "reply": "The vault hasn't been created yet, Sir."}

    # System
    if "shutdown" in txt: return {"action": "shutdown", "args": {}, "reply": ""}
    if "restart" in txt: return {"action": "restart", "args": {}, "reply": ""}
    
    # WiFi
    if "turn on wifi" in txt: return {"action": "enable_wifi", "args": {}, "reply": ""}
    if "turn off wifi" in txt: return {"action": "disable_wifi", "args": {}, "reply": ""}
    
    # Screenshot
    if "screenshot" in txt: return {"action": "take_screenshot", "args": {}, "reply": ""}
    
    # Apps
    if "notepad" in txt: return {"action": "open_app", "args": {"app_name": "notepad"}, "reply": ""}
    if "chrome" in txt: return {"action": "open_app", "args": {"app_name": "chrome"}, "reply": ""}
    
    return {"action": "reply", "args": {}, "reply": "Sorry, I couldn't interpret that."}

# -------------------
# LLM Integration
# -------------------
def query_llama_for_action(user_text, context=None, timeout=15):
    try:
        memories = get_relevant_memories(user_text)
        mem_block = "\n".join(memories) if memories else "None"
        
        system_message = (
            "You are Phantom AI, an advanced local assistant.\n"
            f"Memories: {mem_block}\n"
            "Return ONLY a JSON object: {\"action\": \"name\", \"args\": {}, \"reply\": \"text\"}"
        )

        response = ollama.chat(model=LLM_MODEL, messages=[
            {'role': 'system', 'content': system_message},
            {'role': 'user', 'content': user_text}
        ])
        
        text = response['message']['content']
        start, end = text.find('{'), text.rfind('}') + 1
        if start != -1 and end != 0:
            return json.loads(text[start:end])
        return local_keyword_fallback(user_text) # Fallback if no JSON
    except:
        return local_keyword_fallback(user_text)

# -------------------
# Action Dispatcher
# -------------------
def dispatch_action(action_obj, voice, original_command):
    ai_reply = action_obj.get("reply", "")
    action = action_obj.get("action", "")
    args = action_obj.get("args", {})

    # Speak result helper
    def finish(msg):
        voice.speak(msg)
        save_memory(original_command, msg)
        return True

    try:
        if action == "shutdown":
            pc.shutdown_system()
            return finish("Shutting down system.")
        if action == "restart":
            pc.restart_system()
            return finish("Restarting system.")
        if action == "take_screenshot":
            screen.take_ss()
            return finish("Screenshot captured.")
        if action == "open_url":
            webbrowser.open(args.get("url"))
            return finish(ai_reply or "Opening website.")
        if action == "open_app":
            app_launcher.open_app(args.get("app_name"))
            return finish(ai_reply or "Opening application.")
        if action == "open_path":
            # Direct path opening (used for Vault)
            path = args.get("query")
            if os.path.exists(path):
                os.startfile(path)
                return finish(ai_reply or "Opening folder.")
        
        # Conversational Reply
        if ai_reply:
            return finish(ai_reply)

    except Exception as e:
        print(f"[!] Dispatch Error: {e}")
        finish("I encountered an error executing that command.")

# -------------------
# Main Jarvis Loop
# -------------------
def start_jarvis():
    global global_voice_engine
    
    if JarvisVoiceEngine is None:
        print("[!] Jarvis voice engine missing.")
        return

    try:
        voice = JarvisVoiceEngine()
        global_voice_engine = voice # Allow security thread to use voice
        voice.greet()
    except Exception as e:
        print(f"[!] Voice Engine Init Error: {e}")
        return

    # --- Live Dashboard Loop ---
    while True:
        try:
            # 1. Show Status (Listening Mode)
            print(f"\r[STATUS: {current_security_status}] >>> Jarvis is Listening...", end="", flush=True)
            
            # 2. Listen for command
            command = voice.listen() 
            
            if command:
                # 3. Show Status (Processing Mode)
                print(f"\r[STATUS: {current_security_status}] >>> Jarvis is Processing...", end="", flush=True)
                
                # Check for quick exit
                if any(w in command.lower() for w in ["exit", "quit", "stop"]):
                    voice.speak("Goodbye, Sir.")
                    break
                
                # 4. LLM Processing
                action_obj = query_llama_for_action(command)
                dispatch_action(action_obj, voice, command)
            
        except Exception as e:
            print(f"\n[!] Main Loop Error: {e}")
            continue

# -------------------
# System Entry Point
# -------------------
if __name__ == "__main__":
    try:
        # 1. Start Phantom Security Guard in Background
        # daemon=True ensures it closes when main program closes
        security_thread = threading.Thread(
            target=start_monitoring, 
            args=(security_alert,), 
            daemon=True
        )
        security_thread.start()
        
        print("\n[+] Phantom Guard is active (Background).")
        print("[+] Jarvis Voice System Initializing...")
        
        # 2. Start Main Jarvis Interface
        start_jarvis()
        
    except KeyboardInterrupt:
        print("\n[!] Force Shutdown Initiated.")
        sys.exit(0)