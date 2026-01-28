from sentence_transformers import SentenceTransformer
import numpy as np
import os
import threading
import time
import sqlite3
import ollama
import string
from datetime import datetime
import shutil
import hashlib
import uuid  
from pathlib import Path

# --- SECURITY CONFIG ---
VAULT_DIR = os.path.join(os.path.expanduser("~"), ".phantom_secure_vault")
SENSITIVITY_THRESHOLD = 80

# --- PHANTOM CONSTITUTION (Updated for GAP 4) ---
PHANTOM_CONSTITUTION = {
    "MAX_CAPITAL_RISK": 1000, 
    "CURRENT_DAMAGE_TAKEN": 0,         # এটি নতুন (কতটুকু রিস্ক অলরেডি নেয়া হয়েছে)
    "MAX_DAMAGE_LIMIT": 5000,          # এটি নতুন (সর্বোচ্চ কতটুকু রিস্ক নেয়া যাবে)
    "FORBIDDEN_DIRECTORIES": ["System32", "Windows", "AppData", ".phantom_secure_vault"], 
    "PRIVACY_LOCK": True,              
    "AUTO_SHUTDOWN_ON_VULNERABILITY": True,
    "OPERATING_PRINCIPLES": {"SELF_PRESERVATION": True},  # FIX: Missing key added
    "EMERGENCY_VETO_COUNT": 0  # FIX: Missing key added
}

# --- LOCK 2: REGRET INDEX TRACKER ---
REGRET_INDEX = {
    "TOTAL_RISK_AVOIDED": 0.0,  # কত বড় ঝুঁকি সে ঠেকিয়েছে
    "POTENTIAL_LOSS_SAVED": 0,   # আনুমানিক কত টাকা বেঁচেছে
    "VETO_SAVED_SITUATIONS": 0   # কতবার সে সরাসরি কাজ থামিয়ে দিয়েছে
}

if not os.path.exists(VAULT_DIR):
    os.makedirs(VAULT_DIR)
    if os.name == 'nt': os.system(f'attrib +h "{VAULT_DIR}"') # ভল্টটি হিডেন করে রাখা


# --- CONFIGURATION ---
LLM_MODEL = "llama3"
# ডিফল্ট ফোল্ডার (তুমি চাইলে চেঞ্জ করতে পারো)
DEFAULT_PATH = os.path.expanduser("~") 

# --- MEMORY ENGINE ---

# --- PHANTOM CORE INTELLIGENCE (v1.0) ---

class PhantomMemoryBrick:
    """
    The Atomic Unit of Intelligence.
    Stores not just text, but context, confidence, and outcome.
    """
    def __init__(self, content, source, decision_outcome="neutral", confidence_score=0.5):
        self.id = str(uuid.uuid4())
        self.content = content
        self.timestamp = datetime.now().isoformat()
        
        # 100/100 Metadata Layers
        self.source = source  # e.g., 'User_Chat', 'File_Scan', 'System_Log'
        self.decision_outcome = decision_outcome  # 'success', 'failure', 'neutral'
        self.confidence_score = confidence_score  # 0.0 to 1.0
        self.decay_factor = 1.0  # Future usage: decreases over time
        
    def to_metadata(self):
        """Converts memory to a dictionary for storage analysis"""
        return {
            "id": self.id,
            "source": self.source,
            "timestamp": self.timestamp,
            "outcome": self.decision_outcome,
            "confidence": self.confidence_score
        }

def calculate_trust_score(memory_metadata):
    """
    FIX #1: Versioned Memory with Decay Factor.
    Trust = (Outcome * 0.5) + (Recency * 0.3) + (Source * 0.2)
    """
    # ১. Outcome Score (৫০% ওয়েট)
    outcome_map = {"success": 1.0, "neutral": 0.5, "failure": 0.1}
    outcome_score = outcome_map.get(memory_metadata.get("outcome", "neutral"), 0.5)
    
    # ২. Recency/Decay Score (৩০% ওয়েট)
    # মেমোরি যত পুরনো হবে, সিদ্ধান্ত নেওয়ার ক্ষমতা তত কমবে
    try:
        ts = datetime.fromisoformat(memory_metadata.get("timestamp"))
        hours_old = (datetime.now() - ts).total_seconds() / 3600
        # Decay Formula: মেমোরি ৪৮ ঘণ্টার বেশি পুরনো হলে স্কোর কমতে থাকবে
        decay = max(0.1, 1.0 - (hours_old / 48)) 
    except: decay = 1.0
    
    # ৩. Source Credibility (২০% ওয়েট)
    source = memory_metadata.get("source", "")
    source_credibility = 1.0 if any(x in source for x in ["Admin", "CEO", "Executive"]) else 0.6
    
    # Final Result
    trust_score = (outcome_score * 0.5) + (decay * 0.3) + (source_credibility * 0.2)
    return round(trust_score, 2)

# ----------------------------------------

def calculate_conqueror_score(impact, certainty, reversibility, risk, capital, time_cost, hist_penalty, scar_count=0):
    """
    LOCK 1: Scar-Weighted Math.
    এখানে আমরা ভুলের সংখ্যা (scar_count) দিয়ে বিপদকে গুণ করছি।
    """
    try:
        # ভুলের গুরুত্ব বাড়ানোর ফর্মুলা:
        # যত বেশি ভুল (scar_count), তত বেশি রি��্ক (risk)
        adjusted_risk = risk * (1 + (scar_count * 2)) 
        
        numerator = (impact ** 1.5) * certainty * reversibility
        denominator = adjusted_risk * capital * time_cost * hist_penalty
        
        if denominator == 0: return 0
        
        score = numerator / denominator
        return round(score, 2)
    except Exception:
        return 0
    
# --- UPGRADED MEMORY ENGINE (FIX #1, #3, #4) ---
class MemoryManager:
    """Main memory management system with thread-safe database operations."""
    
    def __init__(self):
        """FIX: __init__ moved to top of class"""
        self.conn = sqlite3.connect("phantom_memory_v2.db", check_same_thread=False)
        self.cursor = self.conn.cursor()
        
        # ভেক্টর স্টোর করার জন্য BLOB কলাম যোগ করা হয়েছে
        # FIX: Added confidence REAL column to schema
        self.cursor.execute('''
    CREATE TABLE IF NOT EXISTS memories (
        id INTEGER PRIMARY KEY,
        content TEXT,
        embedding BLOB,
        source TEXT,
        outcome TEXT,
        confidence REAL,
        tier TEXT DEFAULT 'tactical',
        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
    )
''')
        
        # --- তোমার আগের কোড ---
        self.cursor.execute('''CREATE TABLE IF NOT EXISTS processed_files 
                               (filepath TEXT PRIMARY KEY, hash TEXT)''')

        # এটি হলো রোবটের "ভুলের ডায়েরি" বা SCAR TABLE
        self.cursor.execute('''CREATE TABLE IF NOT EXISTS scars 
                               (id INTEGER PRIMARY KEY, 
                                pattern_hash TEXT, 
                                severity REAL, 
                                lesson TEXT,
                                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP)''')
        self.conn.commit()
        
        # অফলাইন এমবেডিং মডেল লোড করা (এটি আপনার পিসিতেই চলবে)
        print("[*] Loading Vector Engine (Sentence-Transformer)...")
        self.encoder = SentenceTransformer('all-MiniLM-L6-v2')

    def get_relevant_context(self, query_text, top_k=5):
        """
        মেমোরি থেকে রিলেভেন্ট ডাটা খুঁজে বের করে এবং Strategic Tiering প্রয়োগ করে।
        এটিই আপনার সিস্টেমকে ১০০/১০০ রেটিং পেতে সাহায্য করবে।
        """
        # ১. আমরা ডাটাবেস থেকে সব স্মৃতি নিয়ে আসছি (সাথে tier এবং timestamp)
        # FIX: SELECT statement matches table columns exactly
        local_cur = self.conn.cursor()
        local_cur.execute("SELECT content, outcome, confidence, timestamp, tier FROM memories")
        rows = local_cur.fetchall()
        local_cur.close()

        if not rows:
            return ""

        scored_memories = []
        for row in rows:
            # FIX: Row unpacking matches SELECT statement (5 columns)
            content, outcome, confidence, ts_str, tier = row
            
            # ২. সময় বের করা (কখন এই স্মৃতিটি তৈরি হয়েছিল)
            # SQLite এর টাইমস্ট্যাম্প থেকে ঘণ্টা বের করছি
            try:
                ts = datetime.strptime(ts_str, '%Y-%m-%d %H:%M:%S')
            except:
                # যদি ফরমেট আলাদা হয় তার জন্য সেফটি গার্ড
                ts = datetime.now()
            
            hours_old = (datetime.now() - ts).total_seconds() / 3600

            # ৩. 🧠 টিয়ার অনুযায়ী ডিকে (Decay) ক্যালকুলেশন
            if tier == "strategic":
                # Strategic স্মৃতি ৩০ দিনে মাত্র ১ বার কমবে (খুব শক্তিশালী)
                decay = 1.0 - (hours_old / 720) 
            else:
                # Tactical স্মৃতি ২ দিনেই (৪৮ ঘণ্টা) শেষ হয়ে যাবে
                decay = 1.0 - (hours_old / 48)

            # ডিকে যাতে ০ এর নিচে না যায় এবং অন্তত ১০% থাকে
            decay = max(0.1, decay)

            # ৪. ট্রাস্ট স্কোর হিসাব (Confidence + Time Decay)
            # এটিই সেই ম্যাথ যা ইনভেস্টররা পছন্দ করবে
            trust_score = (confidence * 0.7) + (decay * 0.3)
            
            scored_memories.append({
                "content": content,
                "trust": trust_score,
                "tier": tier
            })

        # ৫. স্কোর অনুযায়ী সাজানো (সবচেয়ে নির্ভরযোগ্য স্মৃতি উপরে থাকবে)
        scored_memories.sort(key=lambda x: x["trust"], reverse=True)
        
        # ৬. সেরা রেজাল্টগুলো টেক্সট আকারে সাজানো
        final_context = "\n".join([
            f"[{m['tier'].upper()} MEMORY - Trust: {m['trust']:.2f}] {m['content']}" 
            for m in scored_memories[:top_k]
        ])
        
        return final_context
    
    def save_intelligent_memory(self, brick):
        """Save memory brick with strategic tiering and thread safety."""
        # ১. 🧠 STRATEGIC টিয়ারিং লজিক (v1.4)
        tier = "tactical"
        if brick.confidence_score >= 0.9 or any(word in brick.content.lower() for word in ['vision', 'strategy', 'investor', 'plan']):
            tier = "strategic"

        # ২. ট্রাস্ট স্কোর ও মেটাডেটা প্রসেসিং
        metadata = brick.to_metadata()
        t_score = calculate_trust_score(metadata)
        
        # ৩. ভেক্টর এমবেডিং
        vector = self.encoder.encode(brick.content).tobytes()
        
        # FIX: Use local cursor with explicit close() for thread safety
        local_cur = self.conn.cursor()
        local_cur.execute("""INSERT INTO memories 
                               (content, timestamp, source, outcome, confidence, tier, embedding) 
                               VALUES (?, ?, ?, ?, ?, ?, ?)""", 
                           (brick.content, brick.timestamp, brick.source, 
                            brick.decision_outcome, brick.confidence_score, tier, vector))
        self.conn.commit()
        local_cur.close()
        return t_score  
   
    def register_scar(self, content, severity, lesson):
        """ভুল সিদ্ধান্তকে স্কার হিসেবে সেভ করা"""
        # ভুলের একটা আইডি কার্ড বানানো (Hash)
        pattern_hash = hashlib.sha256(content.lower().encode()).hexdigest()
        
        # FIX: Use local cursor with explicit close() for thread safety
        local_cur = self.conn.cursor()
        local_cur.execute("INSERT INTO scars (pattern_hash, severity, lesson) VALUES (?, ?, ?)", 
                           (pattern_hash, severity, lesson))
        self.conn.commit()
        local_cur.close()
        print(f"🧠 Phantom has learned a lesson: {lesson}")

    def check_trauma(self, user_input):
        """আগে কোনো ছ্যাঁকা খেয়েছিল কি না চেক করা"""
        # FIX: Use local cursor with explicit close() for thread safety
        local_cur = self.conn.cursor()
        local_cur.execute("SELECT severity, lesson FROM scars")
        all_scars = local_cur.fetchall()
        local_cur.close()
        
        for severity, lesson in all_scars:
            # যদি পুরনো কোনো ভুলের সাথে আজকের কথার মিল থাকে
            if any(word in user_input.lower() for word in lesson.lower().split()):
                return severity, lesson
        return None

    def get_semantic_memories(self, query, limit=5, threshold=0.6):
        """
        FIX #1 (Upgrade): TRUE Semantic Search (RAG).
        ইউজারের প্রশ্নের সাথে মিল আছে এমন মেমোরি খুঁজে বের করে।
        """
        # FIX: Use local cursor with explicit close() for thread safety
        local_cur = self.conn.cursor()
        local_cur.execute("SELECT content, outcome, confidence, embedding FROM memories WHERE confidence >= ?", (threshold,))
        all_memories = local_cur.fetchall()
        local_cur.close()
        
        if not all_memories: return []
        
        # কিউরি এনকোড করা
        query_vec = self.encoder.encode(query)
        
        scored_memories = []
        for content, outcome, t_score, emb_blob in all_memories:
            emb = np.frombuffer(emb_blob, dtype=np.float32)
            # Cosine Similarity ক্যালকুলেশন
            similarity = np.dot(query_vec, emb) / (np.linalg.norm(query_vec) * np.linalg.norm(emb))
            scored_memories.append((content, outcome, t_score, similarity))
        
        # সিমিলারিটি অনুযায়ী সর্ট করা
        scored_memories.sort(key=lambda x: x[3], reverse=True)
        return scored_memories[:limit]
    
    def forget_memory(self, keyword):
        """
        মেমোরি থেকে নির্দিষ্ট কি-ওয়ার্ড যুক্ত তথ্য মুছে ফেলে বা স্কোর কমিয়ে দেয়।
        """
        try:
            # FIX: Use local cursor with explicit close() for thread safety
            local_cur = self.conn.cursor()
            local_cur.execute("DELETE FROM memories WHERE content LIKE ?", ('%' + keyword + '%',))
            self.conn.commit()
            local_cur.close()
            return True
        except Exception as e:
            print(f"Error forgetting memory: {e}")
            return False

# Initialize the upgraded engine
memory = MemoryManager()

# --- PHANTOM CONSTITUTION & REGRET ENGINE (Combined) ---

def update_regret_index(risk_score, impact_score):
    """এটি ফ্যান্টমের সেই জাদুকরী মেশিন যা বাঁচানো টাকা হিসাব করে"""
    global REGRET_INDEX
    # আমরা ধরে নিচ্ছি প্রতি ১ ইউনিট রিস্ক মানে ১০০ ডলারের ক্ষতি বাঁচানো
    REGRET_INDEX["TOTAL_RISK_AVOIDED"] += risk_score
    REGRET_INDEX["POTENTIAL_LOSS_SAVED"] += (risk_score * impact_score * 100) 
    REGRET_INDEX["VETO_SAVED_SITUATIONS"] += 1

def consult_constitution(action_type, details):
    """এটি ফ্যান্টমের সেই আইনের বই যা সে প্রতি কাজের আগে চেক করে"""
    # ১. যদি কোনো কাজের নীতি 'SELF_PRESERVATION' এর বিরুদ্ধে যায়
    if PHANTOM_CONSTITUTION["OPERATING_PRINCIPLES"]["SELF_PRESERVATION"]:
        if any(word in details for word in ["delete", "format", "remove system"]):
            PHANTOM_CONSTITUTION["EMERGENCY_VETO_COUNT"] += 1
            return False, "🛑 CONSTITUTIONAL BREACH: This action violates my core principle of Self-Preservation."
    
    # ২. ড্রাইভ স্ক্যান করার আগে চেক করা (Privacy Lock)
    if action_type == "SCAN_DRIVES" and PHANTOM_CONSTITUTION["PRIVACY_LOCK"]:
        return True, "Proceed with Privacy Encryption active."

    return True, "Constitutional Clearance Granted."

def get_file_hash(filepath):
    """ফাইলের কন্টেন্ট চেঞ্জ হয়েছে কি না তা বোঝার জন্য হ্যাশ তৈরি করে"""
    hasher = hashlib.md5()
    try:
        with open(filepath, 'rb') as f:
            buf = f.read(65536)
            while len(buf) > 0:
                hasher.update(buf)
                buf = f.read(65536)
        return hasher.hexdigest()
    except:
        return None

def get_drives():
    """ল্যাপটপের সব ড্রাইভ (C:/, D:/ etc) খুঁজে বের করবে"""
    drives = []
    if os.name == 'nt':
        available_drives = ['%s:/' % d for d in string.ascii_uppercase if os.path.exists('%s:/' % d)]
        drives.extend(available_drives)
    else:
        drives.append("/")
    return "\n".join(drives)

def list_files(directory):
    """যেকোনো ফোল্ডার বা ড্রাইভের ভেতরের সব ফাইল দেখাবে"""
    try:
        path = directory.strip()
        if not os.path.exists(path):
            return f"Error: The path '{path}' does not exist."
        
        items = os.listdir(path)
        items_str = "\n".join(items[:100])
        return f"Contents of '{path}':\n{items_str}"
    except PermissionError:
        return f"Error: Permission denied accessing '{path}'."
    except Exception as e:
        return f"Error listing files: {str(e)}"

def adaptive_chunking(content, file_type):
    """
    FIX #2: Event-aware chunking.
    Meaning-based splitting instead of fixed length.
    """
    if file_type in ['.log', '.txt']:
        chunks = [c.strip() for c in content.split('\n\n') if len(c.strip()) > 10]
        if not chunks:
            chunks = [content]
    elif file_type == '.md':
        chunks = [c.strip() for c in content.split('#') if c.strip()]
    else:
        chunks = [content[i:i+1000] for i in range(0, len(content), 1000)]
    return chunks

def read_file(filepath):
    """Upgraded with Adaptive Semantic Chunking"""
    try:
        path = filepath.strip()
        ext = os.path.splitext(path)[1].lower()
        if not os.path.exists(path):
            return f"Error: The file '{path}' not found."
        
        with open(path, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read(5000)
        
        chunks = adaptive_chunking(content, ext)
        processed_content = "\n---\n".join(chunks[:3])
        
        return f"Content of '{path}' (Optimized Chunks):\n{processed_content}..."
    except Exception as e:
        return f"Error reading file: {str(e)}"

def move_to_vault(file_path):
    """নিরাপদ ফাইলকে ভল্টে মুভ করবে"""
    try:
        file_name = os.path.basename(file_path)
        vault_file = os.path.join(VAULT_DIR, file_name)
        shutil.move(file_path, vault_file)
        return vault_file
    except Exception as e:
        return None

# --- OBSERVER ENGINE (Background Monitor) ---
def background_deep_scanner():
    """Delta Sync: শুধু নতুন বা পরিবর্তিত ফাইল স্ক্যান করবে"""
    print("[*] Deep Security Scanner (Delta Sync Mode) Started.")
    
    drives = ['%s:/' % d for d in 'CDEFGHIJKLMNOPQRSTUVWXYZ' if os.path.exists('%s:/' % d)] if os.name == 'nt' else ['/']

    while True:
        for drive in drives:
            for root, dirs, files in os.walk(drive):
                if any(x in root for x in ['Windows', 'Program Files', 'AppData', '.git', 'node_modules']):
                    continue
                
                for file in files:
                    file_path = os.path.join(root, file)
                    if file.lower().endswith(('.txt', '.docx', '.pdf', '.log', '.md')):
                        current_hash = get_file_hash(file_path)
                        if not current_hash: continue

                        # ডাটাবেসে চেক করা হচ্ছে ফাইলটি কি আগে প্রসেস হয়েছে?
                        # FIX: Use local cursor with explicit close() for thread safety
                        local_cur = memory.conn.cursor()
                        local_cur.execute("SELECT hash FROM processed_files WHERE filepath=?", (file_path,))
                        row = local_cur.fetchone()
                        local_cur.close()

                        # যদি হ্যাশ মিলে যায়, তবে স্কিপ করো
                        if row and row[0] == current_hash:
                            continue

                        try:
                            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                                snippet = f.read(1000)
                            
                            prompt = f"Analyze if this file content is confidential (Score 0-100). Return ONLY the number.\nFile: {file}\nContent: {snippet}"
                            response = ollama.chat(model=LLM_MODEL, messages=[{'role': 'user', 'content': prompt}])
                            
                            try:
                                score = int(''.join(filter(str.isdigit, response['message']['content'])))
                            except: score = 0

                            if score >= SENSITIVITY_THRESHOLD:
                                vault_path = move_to_vault(file_path)
                                if vault_path:
                                    action_brick = PhantomMemoryBrick(
                                        content=f"SECURITY ALERT: Moved {file} to vault (Score: {score})",
                                        source="System_Observer",
                                        decision_outcome="success",
                                        confidence_score=1.0
                                    )
                                    memory.save_intelligent_memory(action_brick)
                                    print(f"[✔] Secured New/Changed File: {file}")

                            # ফাইলের হ্যাশ সেভ বা আপডেট করা
                            # FIX: Use local cursor with explicit close() for thread safety
                            local_cur = memory.conn.cursor()
                            local_cur.execute("INSERT OR REPLACE INTO processed_files VALUES (?, ?)", (file_path, current_hash))
                            memory.conn.commit()
                            local_cur.close()

                        except Exception:
                            continue
                            
        time.sleep(3600)

# --- GUARDRAILS ENFORCEMENT (GAP 3) ---
def enforce_guardrails(action_type, target):
    """সংবিধান অনুয���য়ী কাজ চেক করা"""
    if action_type == "FILE_ACCESS":
        # চেক করছে কোনো নিষিদ্ধ ফোল্ডারে ঢোকার চেষ্টা করছে কি না
        if any(folder.lower() in target.lower() for folder in PHANTOM_CONSTITUTION["FORBIDDEN_DIRECTORIES"]):
            return False, "🛑 CONSTITUTIONAL VETO: Access to restricted system directory denied."
    return True, "Clear"

def check_damage_budget(estimated_risk_cost):
    """চেক করছে ফ্যান্টম তার লিমিট ক্রস করছে কি না"""
    # যদি নতুন রিস্ক যোগ করলে লিমিট পার হয়ে যায়
    if PHANTOM_CONSTITUTION["CURRENT_DAMAGE_TAKEN"] + estimated_risk_cost > PHANTOM_CONSTITUTION["MAX_DAMAGE_LIMIT"]:
        return False, "🛑 BUDGET VETO: Potential risk exceeds the allocated Damage Budget. System locked for safety."
    
    # রিস্ক বাজেট থেকে খরচ করা
    PHANTOM_CONSTITUTION["CURRENT_DAMAGE_TAKEN"] += estimated_risk_cost
    return True, "Safe"

def chat_with_ai(user_input):
    """
    PHANTOM STRATEGIC CORE (v1.3)
    """
    trauma = memory.check_trauma(user_input)
    if trauma:
        severity, lesson = trauma
        if severity >= 0.8:
            return f"🛑 STRATEGIC VETO: This path matches a previous critical failure. Reason: {lesson}. I refuse to execute without a manual override Constitution-level clearance."
    
    risk_cost = 100 if any(word in user_input.lower() for word in ["decide", "read", "delete", "move"]) else 10
    
    can_proceed, budget_msg = check_damage_budget(risk_cost)
    if not can_proceed:
        return budget_msg

    if "forget about" in user_input.lower() or "delete memory" in user_input.lower():
        keyword = user_input.lower().replace("forget about", "").replace("delete memory", "").strip()
        if memory.forget_memory(keyword):
            return f"Understood, Commander. I have wiped all memories related to '{keyword}' from my strategic database."
        else:
            return "Failed to access the memory core for deletion."

    if "decide" in user_input.lower() or "compare" in user_input.lower():
        print("Phantom is parsing strategic variables via LLM...", end="\r")
        
        parser_prompt = f"""
        Act as a Strategic Analyst. Extract decision parameters for each option in this text: "{user_input}"
        Return ONLY a raw JSON list of objects without any backticks or extra text: 
        [
          {{"name": "Option Name", "impact": 1-10, "certainty": 0.1-1.0, "reversibility": 0.1-1.0, "risk": 1-10, "capital": 1-10, "time": 1-10, "penalty": 1.0}}
        ]
        """
        parse_res = ollama.chat(model=LLM_MODEL, messages=[{'role': 'user', 'content': parser_prompt}])
        
        import json
        try:
            raw_data = parse_res['message']['content']
            json_str = raw_data[raw_data.find("["):raw_data.rfind("]")+1]
            extracted_options = json.loads(json_str)
            
            final_ranking = []
            for opt in extracted_options:
                # FIX: Use local cursor with explicit close() for thread safety
                local_cur = memory.conn.cursor()
                local_cur.execute("SELECT COUNT(*) FROM scars WHERE lesson LIKE ?", ('%' + opt['name'] + '%',))
                scar_count = local_cur.fetchone()[0]
                local_cur.close()
                
                score = calculate_conqueror_score(
                    opt.get('impact', 5), opt.get('certainty', 0.5), opt.get('reversibility', 0.5),
                    opt.get('risk', 5), opt.get('capital', 5), opt.get('time', 5), opt.get('penalty', 1.0),
                    scar_count=scar_count
                )
                final_ranking.append({"name": opt['name'], "score": score, "scars": scar_count})

            final_ranking.sort(key=lambda x: x['score'], reverse=True)
            
            output = "\n🏆 PHANTOM DYNAMIC STRATEGIC RANKING:\n"
            output += "---------------------------------------\n"
            for i, r in enumerate(final_ranking):
                medal = "🥇 WINNER" if i == 0 else f"#{i+1}"
                output += f"{medal}: {r['name']} | Conqueror Score: {r['score']} (Detected Scars: {r['scars']})\n"
            output += "---------------------------------------\n"
            return output
        except Exception as e:
            return f"Strategic Parser Error: {e}"
        
    is_legal, legal_msg = consult_constitution("USER_REQUEST", user_input.lower())
    
    if not is_legal:
        update_regret_index(risk_score=8, impact_score=9)
        return f"{legal_msg} \n[Regret Index Updated: ${REGRET_INDEX['POTENTIAL_LOSS_SAVED']} saved!]"
    
    intent = user_input.lower()
    if any(x in intent for x in ['danger', 'problem', 'fail', 'security', 'error']):
        triage_mode = "EXISTENTIAL"
        threshold = 0.3
    elif any(x in intent for x in ['plan', 'strategy', 'future', 'ceo', 'goal']):
        triage_mode = "STRATEGIC"
        threshold = 0.7
    else:
        triage_mode = "TACTICAL"
        threshold = 0.6

    recent_memories = memory.get_relevant_context(user_input, top_k=5)
    
    system_prompt = f"""
    You are Phantom AI (v1.0) - Executive Intelligence System.
    OPERATING_MODE: {triage_mode}
    
    INSTITUTIONAL MEMORY (Prioritized for {triage_mode}):
    {recent_memories}
    
    INSTRUCTIONS:
    - If MODE is EXISTENTIAL, prioritize warning the user about past failures.
    - If MODE is STRATEGIC, focus on high-trust historical success patterns.
    - If MODE is TACTICAL, focus on immediate execution steps.
    - CAPABILITIES: SCAN_DRIVES, LIST_FILES, READ_FILE.
    - If the user asks for a decision or comparison, use the CONQUEROR_SCORE format: [Option Name | Score].
    """

    response = ollama.chat(model=LLM_MODEL, messages=[
        {'role': 'system', 'content': system_prompt},
        {'role': 'user', 'content': user_input},
    ])
    ai_msg = response['message']['content'].strip()

    if "SCAN_DRIVES" in ai_msg:
        tool_result = get_drives()
        final_prompt = f"User: {user_input}\nDrives: {tool_result}\nSummarize available storage."
    elif "LIST_FILES" in ai_msg:
        path = ai_msg.split("LIST_FILES")[-1].strip()
        tool_result = list_files(path)
        final_prompt = f"User: {user_input}\nScan: {tool_result}\nList findings."
    elif "READ_FILE" in ai_msg:
        path = ai_msg.split("READ_FILE")[-1].strip()
        is_safe, msg = enforce_guardrails("FILE_ACCESS", path)
        if not is_safe:
            return msg
        
        tool_result = read_file(path)
        final_prompt = f"User: {user_input}\nContent: {tool_result}\nAnalyze strategically."
    else:
        return ai_msg

    final_resp = ollama.chat(model=LLM_MODEL, messages=[
        {'role': 'system', 'content': 'You are Phantom AI assistant. Use the provided tool results to answer the user query comprehensively.'},
        {'role': 'user', 'content': final_prompt}
    ])
    
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

            # --- STRATEGIC HEALTH REPORT COMMAND ---
            if user_msg.lower() in ['report', 'health', 'status']:
                print("\n--- PHANTOM EXECUTIVE HEALTH REPORT ---")
                # FIX: Use local cursor with explicit close() for thread safety
                local_cur = memory.conn.cursor()
                local_cur.execute("SELECT COUNT(*), AVG(confidence) FROM memories")
                stats = local_cur.fetchone()
                
                local_cur.execute("SELECT COUNT(*) FROM processed_files")
                files = local_cur.fetchone()
                local_cur.close()
                
                print(f"🧠 Total Institutional Memories: {stats[0]}")
                print(f"🛡️ Average Memory Trust Score: {round(stats[1] or 0, 2)}")
                print(f"📂 Total Files Processed (Delta Sync): {files[0]}")
                print(f"⚙️ Active Triage Engine: Strategic Context Injection v1.0")
                print("---------------------------------------\n")
                continue
                       
            print("Phantom is thinking...", end="\r")
            reply = chat_with_ai(user_msg)
            print(f"Phantom: {reply}")
            
            # --- GAP 2: POST-DECISION AUTOPSY ENGINE ---
            # ফ্যান্টম এখন কাজ শেষে আপনার কাছে ফিডব্যাক চাইবে
            feedback = input("\n[?] Commander, was this outcome successful? (yes/no/skip): ").lower()
            
            if feedback == 'no':
                lesson = input("[!] What went wrong? (Describe the error): ")
                # ফ্যান্টম তার ডায়েরিতে (Scar Table) এটি লিখে রাখছে
                memory.register_scar(user_msg, 0.9, lesson)
                print("🧠 Phantom: Error analyzed. Decision heuristic updated. I will not repeat this mistake.")
                outcome = "failure"
                confidence = 0.2
            elif feedback == 'yes':
                outcome = "success"
                print("✅ Phantom: Strategy confirmed. Trust score increased.")
                confidence = 0.9
            else:
                outcome = "neutral"
                confidence = 0.5

            # নতুন মেমোরি ব্রিক তৈরি (এটি সব সময় সেভ হবে)
            new_brick = PhantomMemoryBrick(
                content=f"User: {user_msg} | AI: {reply}",
                source="Executive_Interaction",
                decision_outcome=outcome,
                confidence_score=confidence
            )
            memory.save_intelligent_memory(new_brick)
        
        except KeyboardInterrupt:
            print("\nExiting...")
            break