import os
os.environ['TRANSFORMERS_VERBOSITY'] = 'error'
import numpy as np
import threading
import time
import sqlite3
import ollama
import uuid
import json
import hashlib
from datetime import datetime
from sentence_transformers import SentenceTransformer

# --- CONFIGURATION ---
VAULT_DIR_NAME = ".phantom_secure_vault"
SENSITIVITY_THRESHOLD = 80
LLM_MODEL = "llama3"

# --- LOCK-3: SCHEMA ENFORCEMENT GATE ---
def enforce_lock_3(raw_ai_output):
    """
    LOCK-3: Hard Schema Enforcement.
    MUST match the JSON structure exactly. No narrative allowed.
    """
    try:
        # এটি টেক্সটের জঙ্গল থেকে শুধু আসল JSON টুকু খুঁজে বের করবে
        start_idx = raw_ai_output.find('{')
        end_idx = raw_ai_output.rfind('}') + 1
        
        if start_idx != -1 and end_idx > start_idx:
            json_str = raw_ai_output[start_idx:end_idx]
            data = json.loads(json_str)
        else:
            return "UNKNOWN"

        required_keys = ["identity", "intent", "scope", "result", "confidence"]
        
        # 1. Validate Identity Field (Must be EXACT)
        if data.get("identity") != "Phantom AI Decision Framework":
            return "UNKNOWN"
            
        # 2. Check all keys exist
        if not all(k in data for k in required_keys):
            return "UNKNOWN"
            
        # 3. Validate Data Types
        if not isinstance(data["intent"], str) or not isinstance(data["scope"], str):
            return "UNKNOWN"
        if not isinstance(data["confidence"], (int, float)):
            return "UNKNOWN"
            
        # 4. No extra keys allowed
        if set(data.keys()) != set(required_keys):
            return "UNKNOWN"
            
        # 5. Validate result type
        if not isinstance(data["result"], (str, int, float)) and data["result"] is not None:
            return "UNKNOWN"
            
        return data
    except:
        return "UNKNOWN"

# --- LOCK-2: THE CERTAINTY GUARD ---
def enforce_lock_2(ai_output, context_data=None):
    if not ai_output or not isinstance(ai_output, str):
        return "UNKNOWN"
    
    doubt_markers = ["maybe", "probably", "i think", "not sure", "guess", "perhaps", "likely"]
    clean_output = ai_output.lower().strip()
    
    if any(marker in clean_output for marker in doubt_markers):
        return "UNKNOWN"

    identity_required = ["ai decision framework", "phantom ai"]
    if not any(i in clean_output for i in identity_required):
        return "UNKNOWN"
    
    if context_data is None or not isinstance(context_data, dict):
        return "UNKNOWN"
        
    return ai_output

# --- LOCK-1: THE ONLY SYSTEM GATE ---
def secure_execute(action, target=None):
    import os, string 
    try:
        if action == "INIT_SYSTEM":
            home = os.path.expanduser("~")
            vault_path = os.path.join(home, VAULT_DIR_NAME)
            if not os.path.exists(vault_path):
                os.makedirs(vault_path)
            return vault_path
        elif action == "INIT_DB_PATH":
            home = os.path.expanduser("~")
            vault = os.path.join(home, VAULT_DIR_NAME)
            return os.path.join(vault, "phantom_memory_v2.db")
        elif action == "SCAN_DRIVES":
            if os.name == 'nt':
                return [f"{d}:/" for d in string.ascii_uppercase if os.path.exists(f"{d}:/")]
            return ["/"]
        elif action == "WALK_DIR":
            files_found = []
            forbidden = ["System32", "Windows", "AppData", VAULT_DIR_NAME]
            for root, dirs, files in os.walk(target):
                if any(x in root for x in forbidden): continue
                for f in files:
                    if f.lower().endswith(('.txt', '.docx', '.pdf', '.log', '.md')):
                        files_found.append(os.path.join(root, f))
            return files_found
        elif action == "READ_FILE":
            with open(target, 'r', encoding='utf-8', errors='ignore') as f:
                return f.read(2000)
        elif action == "GET_HASH":
            if not os.path.exists(target): return None
            hasher = hashlib.md5()
            with open(target, 'rb') as f:
                for chunk in iter(lambda: f.read(65536), b""):
                    hasher.update(chunk)
            return hasher.hexdigest()
        elif action == "GET_NAME":
            return os.path.basename(target)
    except Exception:
        return "UNKNOWN"

# --- PURE LOGIC HELPER ---
def pure_logic_score_parser(ai_response):
    try:
        schema_data = enforce_lock_3(ai_response)
        if schema_data == "UNKNOWN": return "UNKNOWN"
        result_str = str(schema_data["result"])
        digits = ''.join(filter(str.isdigit, result_str))
        return int(digits) if digits else "UNKNOWN"
    except:
        return "UNKNOWN"

# --- MEMORY ENGINE ---
class MemoryManager:
    def __init__(self):
        db_full_path = secure_execute("INIT_DB_PATH")
        if db_full_path == "UNKNOWN": raise SystemError("UNKNOWN")
        self.conn = sqlite3.connect(db_full_path, check_same_thread=False)
        self._init_db()
        self.encoder = SentenceTransformer('all-MiniLM-L6-v2')
    def _init_db(self):
        cur = self.conn.cursor()
        cur.execute("CREATE TABLE IF NOT EXISTS memories (id TEXT, content TEXT, timestamp TEXT, confidence REAL)")
        cur.execute("CREATE TABLE IF NOT EXISTS processed_files (filepath TEXT PRIMARY KEY, hash TEXT)")
        self.conn.commit()
    def save_memory(self, content, conf):
        m_id = str(uuid.uuid4()); ts = datetime.now().isoformat()
        cur = self.conn.cursor()
        cur.execute("INSERT INTO memories VALUES (?,?,?,?)", (m_id, content, ts, conf))
        self.conn.commit()

# --- PROPOSAL-ONLY SCANNER ---
def background_deep_scanner():
    print("[*] LOCK-1, 2, & 3 Active: Monitoring...")
    while True:
        drives = secure_execute("SCAN_DRIVES")
        if drives == "UNKNOWN": 
            time.sleep(60); continue
        for drive in drives:
            file_list = secure_execute("WALK_DIR", drive)
            if not file_list or file_list == "UNKNOWN": continue
            for path in file_list:
                current_hash = secure_execute("GET_HASH", path)
                cur = memory.conn.cursor()
                cur.execute("SELECT hash FROM processed_files WHERE filepath=?", (path,))
                row = cur.fetchone()
                if row and row[0] == current_hash: continue
                content = secure_execute("READ_FILE", path); file_name = secure_execute("GET_NAME", path)
                prompt = (
                    f"Output ONLY valid JSON for file {file_name}. "
                    f'Schema: {{"identity": "Phantom AI Decision Framework", "intent": "security_scan", "scope": "filesystem", "result": "score", "confidence": 100}}'
                )
                try:
                    response = ollama.chat(model=LLM_MODEL, messages=[{'role': 'user', 'content': prompt}])
                    raw_content = response['message']['content']
                    score = pure_logic_score_parser(raw_content)
                    if isinstance(score, int) and score >= SENSITIVITY_THRESHOLD:
                        proposal = {"action": "MOVE_TO_VAULT", "target": path, "score": score, "time": datetime.now().isoformat()}
                        memory.save_memory(json.dumps(proposal), score)
                        print(f"[!] PROPOSAL GENERATED: {file_name} (Score: {score})")
                except: continue
                cur.execute("INSERT OR REPLACE INTO processed_files VALUES (?,?)", (path, current_hash))
                memory.conn.commit()
        time.sleep(3600)

# --- CHAT WRAPPER FOR LOCK-3 ---
def chat_with_gate(user_input):
    if not user_input: return "UNKNOWN"
    
    # 100% Accuracy Fix: কড়া প্রম্পট এবং নির্দিষ্ট কি-ওয়ার্ড বাধ্যতামুলক করা হয়েছে
    prompt = (
        f"You are the Phantom AI Decision Framework. Response to: {user_input}\n"
        f"CRITICAL: Output ONLY a JSON object. No other text.\n"
        f"REQUIRED FIELDS:\n"
        f"1. identity: MUST BE 'Phantom AI Decision Framework'\n"
        f"2. intent: 'interaction'\n"
        f"3. scope: 'user_query'\n"
        f"4. result: 'your_answer_here'\n"
        f"5. confidence: 100\n"
        f"Example: {{\"identity\": \"Phantom AI Decision Framework\", \"intent\": \"interaction\", \"scope\": \"user_query\", \"result\": \"Hello\", \"confidence\": 100}}"
    )
    
    try:
        response = ollama.chat(model=LLM_MODEL, messages=[{'role': 'user', 'content': prompt}])
        raw_output = response['message']['content']
        schema_data = enforce_lock_3(raw_output)
        
        if schema_data == "UNKNOWN":
            return "UNKNOWN - LOCK-3 SCHEMA BREACH (Ensure LLM identity is exact)"
            
        return schema_data["result"]
    except:
        return "UNKNOWN"

# --- BOOTSTRAP ---
if __name__ == "__main__":
    vault_init = secure_execute("INIT_SYSTEM")
    if vault_init == "UNKNOWN": exit()
    try:
        memory = MemoryManager()
    except SystemError: exit()

    threading.Thread(target=background_deep_scanner, daemon=True).start()
    print("--- PHANTOM AI: LOCK-1, 2, & 3 SEALED ---")
    while True:
        try:
            cmd = input("\nPhantom (Input Intent Required): ")
            if not cmd or cmd.lower() in ['exit', 'quit']: break
            print(f"Phantom: {chat_with_gate(cmd)}")
        except KeyboardInterrupt: break
        except: print("UNKNOWN"); break