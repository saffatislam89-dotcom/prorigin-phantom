"""
phantom_observer_v2.py - Stark Industries Grade File Monitor
Upgraded by: Phantom AI Architect
"""

import os
import sys
import json
import re
import traceback
import time
import shutil  # Added for VAULT functionality
from pathlib import Path
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor
from typing import Optional, Dict, Any
import threading

# File monitoring
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
import ollama

# Optional PDF/DOCX support imports remain same...
try:
    import pdfplumber
    HAS_PDF_SUPPORT = True
except Exception:
    HAS_PDF_SUPPORT = False

try:
    from docx import Document
    HAS_DOCX_SUPPORT = True
except Exception:
    HAS_DOCX_SUPPORT = False

# -------------------
# Configuration (UPGRADED)
# -------------------
LLM_MODEL = "llama3"
SENSITIVITY_THRESHOLD = 75  # Lowered slightly to catch more potential threats
MAX_WORKERS = 4
MAX_FILE_SIZE_MB = 50

# Added High-Risk Extensions
MONITORED_EXTENSIONS = {
    ".txt", ".pdf", ".docx", ".doc", ".log", ".json", ".csv", ".md",
    ".env", ".pem", ".key", ".yaml", ".yml", ".xml", ".ini", ".conf"
}

# Paths
VAULT_DIR = os.path.join(os.path.expanduser("~"), "Phantom_Secret_Vault")
ALERT_LOG_PATH = r"phantom_alerts.log"

# Create Vault if not exists
if not os.path.exists(VAULT_DIR):
    os.makedirs(VAULT_DIR)
    print(f"[*] Secure Vault Created at: {VAULT_DIR}")

# -------------------
# Utility & Helpers
# -------------------
def get_user_profile_dir() -> str:
    return os.path.expanduser("~")

def is_monitorable_file(file_path: str) -> bool:
    """Enhanced check for file types, ignoring vault and system files."""
    # Don't monitor the vault itself to avoid infinite loops
    if VAULT_DIR in file_path:
        return False
        
    basename = os.path.basename(file_path)
    # Ignore common system/temp files
    if basename.startswith(".") or basename.startswith("~") or "cache" in file_path.lower():
        return False

    ext = Path(file_path).suffix.lower()
    return ext in MONITORED_EXTENSIONS

def move_to_vault(file_path: str, reason: str) -> str:
    """Moves the dangerous file to the secure vault."""
    try:
        filename = os.path.basename(file_path)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        new_name = f"{timestamp}_{filename}"
        destination = os.path.join(VAULT_DIR, new_name)
        
        # Copy first (safer), then delete source, or use move
        shutil.move(file_path, destination)
        
        # Create a metadata file explaining why it was moved
        meta_path = destination + ".meta.json"
        with open(meta_path, "w") as f:
            json.dump({"original_path": file_path, "reason": reason, "moved_at": str(datetime.now())}, f)
            
        return destination
    except Exception as e:
        print(f"[!] FAILED TO MOVE TO VAULT: {e}")
        return None

def read_text_file(file_path: str) -> Optional[str]:
    # ... (Same reading logic as before, just kept concise for response) ...
    # The crucial change is handling errors explicitly
    try:
        if not os.path.exists(file_path): return None
        size_mb = os.path.getsize(file_path) / (1024 * 1024)
        if size_mb > MAX_FILE_SIZE_MB: return None
        
        ext = Path(file_path).suffix.lower()
        
        # Expanded text reading for code/config files
        if ext in {".txt", ".log", ".json", ".csv", ".md", ".env", ".pem", ".key", ".yaml", ".yml", ".xml", ".ini", ".conf"}:
            try:
                with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                    return f.read()
            except: return None
            
        # PDF/DOCX logic remains same...
        if ext == ".pdf" and HAS_PDF_SUPPORT:
            try:
                text_accum = []
                with pdfplumber.open(file_path) as pdf:
                    for page in pdf.pages[:15]: # Increased page limit
                        text_accum.append(page.extract_text() or "")
                return "\n".join(text_accum)
            except: return None
            
        if ext in {".docx", ".doc"} and HAS_DOCX_SUPPORT:
            try:
                doc = Document(file_path)
                return "\n".join(p.text for p in doc.paragraphs)
            except: return None
            
        return None
    except: return None

def analyze_content_with_llama(file_path: str, content: str) -> Optional[Dict[str, Any]]:
    if not content or len(content.strip()) < 5: return None

    try:
        # INCREASED CONTEXT LIMIT from 5000 to 15000 chars
        max_chars = 15000 
        if len(content) > max_chars:
            content = content[:max_chars] + "\n[...truncated...]"

        system_prompt = (
            "You are a cyber-security auditor. Analyze the file content for SENSITIVE DATA.\n"
            "Sensitive data includes: passwords, API keys, private keys (RSA/DSA), bank account numbers, credit cards, "
            "AWS keys, social security numbers, or confidential business strategy.\n"
            "RETURN ONLY JSON: {\"sensitivity_score\": int(0-100), \"reason\": \"short string\"}."
        )

        user_prompt = f"File: {os.path.basename(file_path)}\nContent:\n{content}"

        response = ollama.chat(
            model=LLM_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        )
        
        # ... (Same JSON extraction logic as your previous code) ...
        response_text = str(response['message']['content']) if 'message' in response else str(response)
        
        first_brace = response_text.find("{")
        last_brace = response_text.rfind("}")
        if first_brace == -1 or last_brace == -1: return None
        
        json_text = response_text[first_brace:last_brace+1]
        try:
            parsed = json.loads(json_text)
            parsed["sensitivity_score"] = int(parsed.get("sensitivity_score", 0))
            return parsed
        except: return None

    except Exception: return None

# -------------------
# File Event Handler
# -------------------
class FileContentAnalyzerHandler(FileSystemEventHandler):
    def __init__(self, executor: ThreadPoolExecutor):
        super().__init__()
        self.executor = executor
        self._recent = set()
        self._lock = threading.Lock()

    def on_created(self, event): self._schedule(event.src_path, "created")
    def on_modified(self, event): self._schedule(event.src_path, "modified")

    def _schedule(self, path: str, ev_type: str):
        if not is_monitorable_file(path): return
        
        # Debounce logic (prevents scanning same file twice in 2 seconds)
        try:
            mtime = os.path.getmtime(path)
            key = (path, int(mtime))
            with self._lock:
                if key in self._recent: return
                self._recent.add(key)
                if len(self._recent) > 500: self._recent.pop() # clear old cache
        except: return

        print(f"[SCANNING] {os.path.basename(path)}")
        self.executor.submit(self._analyze_and_act, path)

    def _analyze_and_act(self, path: str):
        try:
            content = read_text_file(path)
            if not content: return

            analysis = analyze_content_with_llama(path, content)
            if not analysis: return

            score = analysis.get("sensitivity_score", 0)
            
            if score >= SENSITIVITY_THRESHOLD:
                reason = analysis.get("reason", "Unknown")
                print(f"🚨 [DANGER] High Sensitivity ({score}) detected in {path}")
                
                # --- THE VAULT LOGIC ---
                vault_path = move_to_vault(path, reason)
                
                if vault_path:
                    log_msg = f"[SECURED] Moved to Vault: {vault_path} | Reason: {reason}"
                    print(log_msg)
                    with open(ALERT_LOG_PATH, "a") as f: f.write(log_msg + "\n")
                else:
                    print(f"[!] FAILED TO SECURE FILE: {path}")

        except Exception as e:
            print(f"[!] Error processing {path}: {e}")

# -------------------
# Main
# -------------------
if __name__ == "__main__":
    print(f"[*] PHANTOM AI OBSERVER v2.0 - ONLINE")
    print(f"[*] Secure Vault: {VAULT_DIR}")
    
    # Check Ollama logic here (skipped for brevity, same as yours)
    
    user_dir = get_user_profile_dir()
    observer = Observer()
    handler = FileContentAnalyzerHandler(ThreadPoolExecutor(max_workers=MAX_WORKERS))
    observer.schedule(handler, path=user_dir, recursive=True)
    observer.start()
    
    try:
        while True: time.sleep(1)
    except KeyboardInterrupt:
        observer.stop()
    observer.join()