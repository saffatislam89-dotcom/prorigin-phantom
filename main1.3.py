import os
import threading
import time
import sqlite3
import ollama
import string
from datetime import datetime
import shutil
import hashlib
from pathlib import Path

# --- SECURITY CONFIG ---
VAULT_DIR = os.path.join(os.path.expanduser("~"), ".phantom_secure_vault")
SENSITIVITY_THRESHOLD = 80

if not os.path.exists(VAULT_DIR):
    os.makedirs(VAULT_DIR)
    if os.name == 'nt': os.system(f'attrib +h "{VAULT_DIR}"') # ভল্টটি হিডেন করে রাখা


# --- CONFIGURATION ---
LLM_MODEL = "llama3"
# ডিফল্ট ফোল্ডার (তুমি চাইলে চেঞ্জ করতে পারো)
DEFAULT_PATH = os.path.expanduser("~") 

# --- MEMORY ENGINE ---
class MemoryManager:
    def __init__(self):
        self.conn = sqlite3.connect("phantom_memory.db", check_same_thread=False)
        self.cursor = self.conn.cursor()
        self.cursor.execute('''CREATE TABLE IF NOT EXISTS memories 
                               (id INTEGER PRIMARY KEY, content TEXT, timestamp TEXT)''')
        self.conn.commit()

    def save(self, text):
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.cursor.execute("INSERT INTO memories (content, timestamp) VALUES (?, ?)", (text, ts))
        self.conn.commit()

    def get_recent(self, limit=5):
        self.cursor.execute("SELECT content FROM memories ORDER BY id DESC LIMIT ?", (limit,))
        return [row[0] for row in self.cursor.fetchall()]

memory = MemoryManager()

# --- ACTIVE TOOLS (AI-এর হাত-পা) ---
# --- ACTIVE TOOLS (AI-এর সুপার পাওয়ার) ---
def get_drives():
    """ল্যাপটপের সব ড্রাইভ (C:/, D:/ etc) খুঁজে বের করবে"""
    drives = []
    # Windows-এর জন্য ড্রাইভ খোঁজা
    if os.name == 'nt':
        available_drives = ['%s:/' % d for d in string.ascii_uppercase if os.path.exists('%s:/' % d)]
        drives.extend(available_drives)
    else:
        # Linux/Mac-এর জন্য
        drives.append("/")
    return "\n".join(drives)

def list_files(directory):
    """যেকোনো ফোল্ডার বা ড্রাইভের ভেতরের সব ফাইল দেখাবে"""
    try:
        # পাথ ঠিক করা
        path = directory.strip()
        if not os.path.exists(path):
            return f"Error: The path '{path}' does not exist."
        
        items = os.listdir(path)
        # প্রথম ১০০টি আইটেম দেখাবে (বেশি হলে AI কনফিউজড হতে পারে)
        items_str = "\n".join(items[:100]) 
        return f"Contents of '{path}':\n{items_str}"
    except PermissionError:
        return f"Error: Permission denied accessing '{path}'."
    except Exception as e:
        return f"Error listing files: {str(e)}"

def read_file(filepath):
    """ফাইলের ভেতরের লেখা পড়ে শোনাবে"""
    try:
        path = filepath.strip()
        if not os.path.exists(path):
            return f"Error: The file '{path}' not found."
        
        # ফাইল পড়ার চেষ্টা (UTF-8)
        with open(path, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read(3000) # ৩০০০ ক্যারেক্টার পড়বে
        return f"Content of '{path}':\n{content}..."
    except Exception as e:
        return f"Error reading file: {str(e)}"
def move_to_vault(filepath):
    """সেনসিটিভ ফাইলকে ভল্টে মুভ করবে"""
    try:
        if not os.path.exists(filepath): return False
        filename = os.path.basename(filepath)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        dest_path = os.path.join(VAULT_DIR, f"{timestamp}_{filename}")
        
        shutil.move(filepath, dest_path)
        return dest_path
    except Exception as e:
        print(f"Error moving to vault: {e}")
        return None
    

# --- OBSERVER ENGINE (Background Monitor) ---
def background_deep_scanner():
    """সব ড্রাইভের ফাইল স্ক্যান করবে এবং Llama 3 দিয়ে সেনসিটিভিটি চেক করবে"""
    print("[*] Deep Security Scanner Started. Scanning all drives...")
    
    # সব ড্রাইভ খুঁজে বের করা
    drives = []
    if os.name == 'nt':
        drives = ['%s:/' % d for d in 'CDEFGHIJKLMNOPQRSTUVWXYZ' if os.path.exists('%s:/' % d)]
    else:
        drives = ['/']

    while True:
        for drive in drives:
            for root, dirs, files in os.walk(drive):
                # সিস্টেম ফোল্ডার স্কিপ করা (যাতে পিসি ক্র্যাশ না করে)
                if any(x in root for x in ['Windows', 'Program Files', 'AppData', '.git', 'node_modules']):
                    continue
                
                for file in files:
                    file_path = os.path.join(root, file)
                    
                    # শুধু নির্দিষ্ট ফরম্যাট চেক করা (টেক্সট, পিডিএফ, ডক ইত্যাদি)
                    if file.lower().endswith(('.txt', '.docx', '.pdf', '.log', '.md')):
                        try:
                            # ১. ফাইলের অল্প অংশ পড়া
                            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                                snippet = f.read(1000)
                            
                            # ২. Llama 3 কে দিয়ে চেক করানো
                            prompt = f"Analyze if this file content is confidential (Score 0-100). Return ONLY the number.\nFile: {file}\nContent: {snippet}"
                            response = ollama.chat(model=LLM_MODEL, messages=[{'role': 'user', 'content': prompt}])
                            
                            try:
                                score = int(''.join(filter(str.isdigit, response['message']['content'])))
                            except: score = 0

                            # ৩. স্কোর ৮০+ হলে অ্যাকশন নেওয়া
                            if score >= SENSITIVITY_THRESHOLD:
                                print(f"\n[!] HIGH SENSITIVITY ({score}): {file}")
                                vault_path = move_to_vault(file_path)
                                if vault_path:
                                    memory.save(f"SECURITY ACTION: Moved {file} to vault (Score: {score})")
                                    print(f"[✔] Secured: {file} moved to vault.")
                                    
                        except Exception:
                            continue
                            
        time.sleep(3600) # একবার ফুল স্ক্যান শেষ হলে ১ ঘণ্টা বিরতি দেবে

# --- INTELLIGENCE CORE ---
# --- INTELLIGENCE CORE ---
def chat_with_ai(user_input):
    recent_memories = "\n".join(memory.get_recent())
    
    # AI-কে বলা হচ্ছে তার কী কী পাওয়ার আছে
    system_prompt = f"""
    You are Phantom AI, installed on the user's PC with FULL SYSTEM ACCESS.
    
    CAPABILITIES:
    1. SHOW DRIVES: To see hard drives (C:, D:), output ONLY: SCAN_DRIVES
    2. LOOK INSIDE: To see files in a folder, output ONLY: LIST_FILES <path>
    3. READ FILE: To read a file's content, output ONLY: READ_FILE <path>
    
    INSTRUCTIONS:
    - If user asks "what drives do I have?", use SCAN_DRIVES.
    - If user asks "what is in D drive?", use LIST_FILES D:/
    - If user asks "read document.txt in D drive", use READ_FILE D:/document.txt
    - Always output the command ALONE first.
    - Context: {recent_memories}
    """

    # ১. AI-এর ডিসিশন নেওয়া
    response = ollama.chat(model=LLM_MODEL, messages=[
        {'role': 'system', 'content': system_prompt},
        {'role': 'user', 'content': user_input},
    ])
    ai_msg = response['message']['content'].strip()

    # ২. টুল এক্সিকিউশন (Tool Execution)
    tool_result = ""
    
    if "SCAN_DRIVES" in ai_msg:
        tool_result = get_drives()
        final_prompt = f"User asked: {user_input}\nFound Drives:\n{tool_result}\nTell the user what drives are available."
        
    elif "LIST_FILES" in ai_msg:
        path = ai_msg.replace("LIST_FILES", "").strip()
        tool_result = list_files(path)
        final_prompt = f"User asked: {user_input}\nScan Result:\n{tool_result}\nSummarize what files are there."

    elif "READ_FILE" in ai_msg:
        path = ai_msg.replace("READ_FILE", "").strip()
        tool_result = read_file(path)
        final_prompt = f"User asked: {user_input}\nFile Content:\n{tool_result}\nAnalyze or summarize this file content."

    else:
        # কোনো টুল কল না করলে সাধারণ উত্তর
        return ai_msg

    # ৩. টুলের রেজাল্ট নিয়ে ফাইনাল উত্তর
    final_resp = ollama.chat(model=LLM_MODEL, messages=[{'role': 'user', 'content': final_prompt}])
    return final_resp['message']['content']

# --- MAIN LOOP ---
if __name__ == "__main__":
    # ব্যাকগ্রাউন্ড স্ক্যানার চালু
    threading.Thread(target=background_deep_scanner, daemon=True).start()
    
    print("--- Phantom AI 1.3 (Active Access Mode) ---")
    print(f"System connected to: {DEFAULT_PATH}")
    print("Type 'exit' to close.")

    while True:
        try:
            user_msg = input("\nYou: ")
            if user_msg.lower() in ['exit', 'quit']:
                break
            
            print("Phantom is thinking...", end="\r")
            reply = chat_with_ai(user_msg)
            print(f"Phantom: {reply}")
            
            # মেমোরি আপডেট
            memory.save(f"User: {user_msg} | AI: {reply}")
        
        except KeyboardInterrupt:
            print("\nExiting...")
            break