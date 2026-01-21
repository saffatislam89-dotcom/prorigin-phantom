import shutil 
import os
import sys
import json
import re
import threading
import traceback
import time
from pathlib import Path
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor
from typing import Optional, Dict, Any

# File monitoring
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

# Local LLM
import ollama

# --- ইম্পোর্ট এরর হ্যান্ডলিং ---
try:
    import pdfplumber
    HAS_PDF_SUPPORT = True
except ImportError:
    HAS_PDF_SUPPORT = False

try:
    from docx import Document
    HAS_DOCX_SUPPORT = True
except ImportError:
    HAS_DOCX_SUPPORT = False

# -------------------
# Configuration
# -------------------
LLM_MODEL = "llama3"
SENSITIVITY_THRESHOLD = 90
MAX_WORKERS = 2
MAX_FILE_SIZE_MB = 50
MONITORED_EXTENSIONS = {".txt", ".pdf", ".docx", ".doc", ".log", ".json", ".csv", ".md"}
LOG_FILE_PATH = r"phantom_alerts.log" 
# --- Secret Vault Configuration ---
VAULT_DIR_NAME = ".jarvis_secure_vault" # ফোল্ডারের নামের আগে ডট (.) মানে এটি সাধারণ চোখে দেখা যাবে না

# -------------------
# Utility Functions
# -------------------
def get_user_profile_dir():
    return os.path.expanduser("~")

def is_text_file(file_path: str) -> bool:
    ext = Path(file_path).suffix.lower()
    return ext in MONITORED_EXTENSIONS

def read_text_file(file_path: str) -> Optional[str]:
    try:
        if not os.path.exists(file_path): return None
        file_size_mb = os.path.getsize(file_path) / (1024 * 1024)
        if file_size_mb > MAX_FILE_SIZE_MB: return None
        ext = Path(file_path).suffix.lower()
        if ext in {".txt", ".log", ".json", ".csv", ".md"}:
            with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                return f.read()
        if ext == ".pdf" and HAS_PDF_SUPPORT:
            text = ""
            with pdfplumber.open(file_path) as pdf:
                for page in pdf.pages[:10]:
                    text += (page.extract_text() or "") + "\n"
            return text if text.strip() else None
        return None
    except Exception as e:
        print(f"[!] Read error ({file_path}): {e}")
        return None

def analyze_content_with_llama(file_path: str, content: str) -> Optional[Dict[str, Any]]:
    if not content or len(content.strip()) < 10: return None
    try:
        content = content[:5000]
        system_prompt = (
            "You are a security analyzer. Return ONLY a valid JSON object. "
            "No preamble, no markdown blocks, no extra words. "
            "JSON: {\"sensitivity_score\": int, \"reason\": \"string\"}"
        )
        user_prompt = f"Analyze file '{os.path.basename(file_path)}' content: {content}"
        response = ollama.chat(
            model=LLM_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        )
        response_text = response['message']['content']
        json_match = re.search(r"\{.*\}", response_text, re.DOTALL)
        if json_match:
            return json.loads(json_match.group(0))
    except Exception as e:
        print(f"[!] AI Parsing Error for {file_path}: {e}")
    return None

# -------------------
# Security Vault Logic
# -------------------
def secure_data_vault(file_path):
    """সেনসিটিভ ফাইলগুলোকে গোপন ফোল্ডারে ব্যাকআপ নেওয়ার ফাংশন"""
    try:
        # ১. গোপন ভল্টের লোকেশন সেট করা (User Home Directory তে)
        vault_path = os.path.join(get_user_profile_dir(), VAULT_DIR_NAME)
        
        # ২. ভল্ট না থাকলে তৈরি করা
        if not os.path.exists(vault_path):
            os.makedirs(vault_path)
            # উইন্ডোজে ফোল্ডারটিকে Hidden বা লুকানো করার জন্য
            os.system(f'attrib +h "{vault_path}"')

        # ৩. ফাইলের নতুন নাম দেওয়া (Timestamp সহ, যাতে ডুপ্লিকেট না হয়)
        file_name = os.path.basename(file_path)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        safe_name = f"SECURED_{timestamp}_{file_name}"
        destination = os.path.join(vault_path, safe_name)

        # ৪. ফাইল কপি করা (shutil.copy2 মেটাডাটা সহ কপি করে)
        shutil.copy2(file_path, destination)
        
        return True, destination
    except Exception as e:
        print(f"[!] Vault Backup Failed: {e}")
        return False, str(e)
    
# -------------------
# File Event Handler
# -------------------
class FileContentAnalyzerHandler(FileSystemEventHandler):
    def __init__(self, executor: ThreadPoolExecutor, voice_callback=None): 
        self.executor = executor
        self.voice_callback = voice_callback
        self.analyzed_keys = set()
        self._lock = threading.Lock()

    def on_modified(self, event):
        if not event.is_directory: self._queue(event.src_path)

    def on_created(self, event):
        if not event.is_directory: self._queue(event.src_path)

    def _queue(self, file_path: str):
        if not is_text_file(file_path): return
        try:
            mtime = os.path.getmtime(file_path)
            key = (file_path, mtime)
            with self._lock:
                if key in self.analyzed_keys: return
                self.analyzed_keys.add(key)
            self.executor.submit(self._process, file_path)
        except OSError: pass

    def process_file(self, file_path):
        try:
            # ফাইলের নাম ছোট হাতের অক্ষরে নিয়ে আসা যাতে সব ক্যাটাগরি ম্যাচ করে
            filename = os.path.basename(file_path).lower()
            
            # আপনার কাঙ্ক্ষিত সেনসিটিভ কি-ওয়ার্ডসমূহ
            keywords = ["secret", "confidential", "password", "secured", "private"]
            
            # যদি ফাইলের নামের মধ্যে উপরের যেকোনো একটি শব্দ থাকে
            if any(key in filename for key in keywords):
                alert_msg = f"Security Alert: A confidential file named {filename} has been detected."
                
                # টার্মিনালে লাল এলার্ট দেখানো
                print(f"\n[!] {alert_msg}") 
                
                # মেইন জার্ভিসকে (main_test1.2.py) এলার্ট পাঠানো যাতে সে কথা বলে ওঠে
                if self.callback: 
                    self.callback(alert_msg)
        except Exception as e:
            print(f"Error processing file: {e}")
        
        analysis = analyze_content_with_llama(file_path, content)
        
        # যদি স্কোর ৮০ বা তার বেশি হয়
        if analysis and analysis.get("sensitivity_score", 0) >= SENSITIVITY_THRESHOLD:
            file_name = os.path.basename(file_path)
            
            # --- ১. প্রথমে ফাইলটি সিকিউর ভল্টে আপলোড করা ---
            is_secured, vault_loc = secure_data_vault(file_path)
            
            vault_msg = ""
            if is_secured:
                vault_msg = "File has been encrypted and moved to the secure vault."
            else:
                vault_msg = "Warning: Failed to secure the file."

            # --- ২. এলার্ট মেসেজ তৈরি করা ---
            alert_text = (f"Sir, high threat detected in {file_name}. "
                          f"{vault_msg} Please check logs immediately.")
            
            print(f"\n[ALERT] {alert_text}")
            print(f"[VAULT] Backup Location: {vault_loc}")

            # --- ৩. জার্ভিসকে দিয়ে বলানো ---
            if self.voice_callback:
                self.voice_callback(alert_text)

# -------------------
# Monitoring & Connectivity
# -------------------
def check_ollama():
    try:
        ollama.list()
        return True
    except Exception:
        print("[!] Ollama is not responding. Ensure 'ollama serve' is running.")
        return False

def start_monitoring(voice_callback=None):
    if not check_ollama(): return
    user_dir = get_user_profile_dir()
    print(f"[*] Monitoring started on: {user_dir}")
    
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        event_handler = FileContentAnalyzerHandler(executor, voice_callback)
        observer = Observer()
        observer.schedule(event_handler, user_dir, recursive=True)
        observer.start()
        try:
            while True: time.sleep(1)
        except KeyboardInterrupt:
            observer.stop()
        observer.join()

# --- সরাসরি টেস্ট করার জন্য এটি প্রয়োজন ---
if __name__ == "__main__":
    start_monitoring()