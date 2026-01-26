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
    # ১. Outcome Score (৫০% ওয়েট)
    outcome_map = {"success": 1.0, "neutral": 0.5, "failure": 0.1}
    outcome_score = outcome_map.get(memory_metadata.get("outcome", "neutral"), 0.5)
    
    # ২. Recency/Decay Score (৩০% ওয়েট)
    # মেমোরি যত পুরনো হবে, সিদ্ধান্ত নেওয়ার ক্ষমতা তত কমবে
    try:
        ts = datetime.fromisoformat(memory_metadata.get("timestamp"))
        hours_old = (datetime.now() - ts).total_seconds() / 3600
        # Decay Formula: মেমোরি ৪৮ ঘণ্টার বেশি পুরনো হলে স্কোর কমতে থাকবে
        decay = max(0.1, 1.0 - (hours_old / 48)) 
    except: decay = 1.0
    
    # ৩. Source Credibility (২০% ওয়েট)
    source = memory_metadata.get("source", "")
    source_credibility = 1.0 if any(x in source for x in ["Admin", "CEO", "Executive"]) else 0.6
    
    # Final Result
    trust_score = (outcome_score * 0.5) + (decay * 0.3) + (source_credibility * 0.2)
    return round(trust_score, 2)
# ----------------------------------------

def calculate_conqueror_score(impact, certainty, reversibility, risk, capital, time_cost, hist_penalty):
    """
    FIX #2: Conqueror Score Engine.
    গাণিতিকভাবে সিদ্ধান্তের মান নির্ধারণ করে।
    """
    try:
        # ফর্মুলা ইমপ্লিমেন্টেশন (Impact-কে ১.৫ পাওয়ার দেওয়া হয়েছে গুরুত্ব বাড়াতে)
        numerator = (impact ** 1.5) * certainty * reversibility
        denominator = risk * capital * time_cost * hist_penalty
        
        # জিরো ডিভিশন এরর হ্যান্ডলিং
        if denominator == 0: return 0
        
        score = numerator / denominator
        return round(score, 2)
    except Exception:
        return 0
    
# --- UPGRADED MEMORY ENGINE (FIX #1, #3, #4) ---
class MemoryManager:
    def __init__(self):
        self.conn = sqlite3.connect("phantom_memory_v2.db", check_same_thread=False)
        self.cursor = self.conn.cursor()
        # ভেক্টর স্টোর করার জন্য BLOB কলাম যোগ করা হয়েছে
        self.cursor.execute('''CREATE TABLE IF NOT EXISTS memories 
                               (id TEXT PRIMARY KEY, content TEXT, timestamp TEXT, 
                                source TEXT, outcome TEXT, confidence REAL, 
                                trust_score REAL, embedding BLOB)''')
        
        self.cursor.execute('''CREATE TABLE IF NOT EXISTS processed_files 
                               (filepath TEXT PRIMARY KEY, hash TEXT)''')
        self.conn.commit()
        
        # অফলাইন এমবেডিং মডেল লোড করা (এটি আপনার পিসিতেই চলবে)
        print("[*] Loading Vector Engine (Sentence-Transformer)...")
        self.encoder = SentenceTransformer('all-MiniLM-L6-v2')

    def save_intelligent_memory(self, brick):
        metadata = brick.to_metadata()
        t_score = calculate_trust_score(metadata)
        
        # কন্টেন্টকে ভেক্টরে রূপান্তর করা (Embedding)
        vector = self.encoder.encode(brick.content).tobytes()
        
        self.cursor.execute("""INSERT INTO memories 
                               (id, content, timestamp, source, outcome, confidence, trust_score, embedding) 
                               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""", 
                            (brick.id, brick.content, brick.timestamp, brick.source, 
                             brick.decision_outcome, brick.confidence_score, t_score, vector))
        self.conn.commit()
        return t_score

    def get_semantic_memories(self, query, limit=5, threshold=0.6):
        """
        FIX #1 (Upgrade): TRUE Semantic Search (RAG).
        ইউজারের প্রশ্নের সাথে মিল আছে এমন মেমোরি খুঁজে বের করে।
        """
        self.cursor.execute("SELECT content, outcome, trust_score, embedding FROM memories WHERE trust_score >= ?", (threshold,))
        all_memories = self.cursor.fetchall()
        
        if not all_memories: return []
        
        # কিউরি এনকোড করা
        query_vec = self.encoder.encode(query)
        
        scored_memories = []
        for content, outcome, t_score, emb_blob in all_memories:
            emb = np.frombuffer(emb_blob, dtype=np.float32)
            # Cosine Similarity ক্যালকুলেশন
            similarity = np.dot(query_vec, emb) / (np.linalg.norm(query_vec) * np.linalg.norm(emb))
            scored_memories.append((content, outcome, t_score, similarity))
        
        # সিমিলারিটি অনুযায়ী সর্ট করা
        scored_memories.sort(key=lambda x: x[3], reverse=True)
        return scored_memories[:limit]
    def forget_memory(self, keyword):
        """
        মেমোরি থেকে নির্দিষ্ট কি-ওয়ার্ড যুক্ত তথ্য মুছে ফেলে বা স্কোর কমিয়ে দেয়।
        """
        try:
            self.cursor.execute("DELETE FROM memories WHERE content LIKE ?", ('%' + keyword + '%',))
            self.conn.commit()
            return True
        except Exception as e:
            print(f"Error forgetting memory: {e}")
            return False
    
# Initialize the upgraded engine
memory = MemoryManager()

# --- ACTIVE TOOLS (AI-এর হাত-পা) ---
# --- ACTIVE TOOLS (AI-এর সুপার পাওয়ার) ---
# --- ACTIVE TOOLS সেকশনের শুরুতে এটি যোগ করুন ---
def get_file_hash(filepath):
    """ফাইলের কন্টেন্ট চেঞ্জ হয়েছে কি না তা বোঝার জন্য হ্যাশ তৈরি করে"""
    hasher = hashlib.md5()
    try:
        with open(filepath, 'rb') as f:
            buf = f.read(65536) # বড় ফাইলের জন্য চাঙ্ক করে পড়া
            while len(buf) > 0:
                hasher.update(buf)
                buf = f.read(65536)
        return hasher.hexdigest()
    except:
        return None
    
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

# ... list_files ফাংশন এখানে শেষ হয়েছে ...

# ... list_files ফাংশন এখানে শেষ হয়েছে ...

# ১. প্রথমে এই নতুন হেল্পার ফাংশনটি অ্যাড করুন
def adaptive_chunking(content, file_type):
    """
    FIX #2: Event-aware chunking.
    Meaning-based splitting instead of fixed length.
    """
    if file_type in ['.log', '.txt']:
        chunks = [c.strip() for c in content.split('\n\n') if len(c.strip()) > 10]
        if not chunks: chunks = [content]
    elif file_type == '.md':
        chunks = [c.strip() for c in content.split('#') if c.strip()]
    else:
        chunks = [content[i:i+1000] for i in range(0, len(content), 1000)]
    return chunks

# ২. এখন পুরনো read_file ফাংশনটি সরিয়ে এই নতুনটি বসান
def read_file(filepath):
    """Upgraded with Adaptive Semantic Chunking"""
    try:
        path = filepath.strip()
        ext = os.path.splitext(path)[1].lower() # ফাইলের এক্সটেনশন চেক করছে (যেমন: .txt)
        if not os.path.exists(path):
            return f"Error: The file '{path}' not found."
        
        with open(path, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read(5000) # ৫০০০ ক্যারেক্টার পর্যন্ত পড়বে
        
        # FIX #2: স্মার্ট চাঙ্কিং অ্যাপ্লাই করা হচ্ছে
        chunks = adaptive_chunking(content, ext)
        
        # সব হিজিবিজি না দেখিয়ে শুধু গুরুত্বপূর্ণ প্রথম ৩টি অংশ দেখাচ্ছে
        processed_content = "\n---\n".join(chunks[:3])
        
        return f"Content of '{path}' (Optimized Chunks):\n{processed_content}..."
    except Exception as e:
        return f"Error reading file: {str(e)}"

# ... এরপর move_to_vault ফাংশন শুরু হয়েছে ...


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

                        # ডাটাবেসে চেক করা হচ্ছে ফাইলটি কি আগে প্রসেস হয়েছে?
                        memory.cursor.execute("SELECT hash FROM processed_files WHERE filepath=?", (file_path,))
                        row = memory.cursor.fetchone()

                        # যদি হ্যাশ মিলে যায়, তবে স্কিপ করো
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
                            memory.cursor.execute("INSERT OR REPLACE INTO processed_files VALUES (?, ?)", (file_path, current_hash))
                            memory.conn.commit()

                        except Exception:
                            continue
                            
        time.sleep(3600)
        
# --- INTELLIGENCE CORE ---
# --- INTELLIGENCE CORE ---
def chat_with_ai(user_input):
    """
    PHANTOM STRATEGIC CORE (v1.3)
    """
    # ১. Forget Memory Logic
    if "forget about" in user_input.lower() or "delete memory" in user_input.lower():
        keyword = user_input.lower().replace("forget about", "").replace("delete memory", "").strip()
        if memory.forget_memory(keyword):
            return f"Understood, Commander. I have wiped all memories related to '{keyword}' from my strategic database."
        else:
            return "Failed to access the memory core for deletion."

    # --- 🚀 100/100 DYNAMIC CONQUEROR PARSER ---
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
                score = calculate_conqueror_score(
                    opt.get('impact', 5), opt.get('certainty', 0.5), opt.get('reversibility', 0.5),
                    opt.get('risk', 5), opt.get('capital', 5), opt.get('time', 5), opt.get('penalty', 1.0)
                )
                final_ranking.append({"name": opt['name'], "score": score})
            
            final_ranking.sort(key=lambda x: x['score'], reverse=True)
            
            output = "\n🏆 PHANTOM DYNAMIC STRATEGIC RANKING:\n"
            output += "---------------------------------------\n"
            for i, r in enumerate(final_ranking):
                medal = "🥇 WINNER" if i == 0 else f"#{i+1}"
                output += f"{medal}: {r['name']} | Conqueror Score: {r['score']}\n"
            output += "---------------------------------------\n"
            return output
        except Exception as e:
            return f"Strategic Parser Error: {e}"
    # --- DYNAMIC PARSER ENDS ---

    # ২. এরপর বাকি ইন্টেন্ট এবং মেমোরি রিট্রিভাল লজিক (intent = user_input.lower() থেকে শুরু)
        
    # ১. প্রশ্নের ধরণ বুঝে Triage নির্ধারণ করা
    intent = user_input.lower()
    if any(x in intent for x in ['danger', 'problem', 'fail', 'security', 'error']):
        triage_mode = "EXISTENTIAL"  # ঝুঁকি এবং ব্যর্থতার মেমোরি খুঁজবে
        threshold = 0.3 # খারাপ মেমোরিও দেখবে যাতে সতর্ক করতে পারে
    elif any(x in intent for x in ['plan', 'strategy', 'future', 'ceo', 'goal']):
        triage_mode = "STRATEGIC"    # সাকসেসফুল দীর্ঘমেয়াদী মেমোরি খুঁজবে
        threshold = 0.7
    else:
        triage_mode = "TACTICAL"     # রিসেন্ট এবং কাজের মেমোরি খুঁজবে
        threshold = 0.6

    # ২. Triage অনুযায়ী মেমোরি রিট্রিভ করা
   # এখন AI শুধু ট্রাস্ট স্কোর না, আপনার প্রশ্নের "মানে" বুঝে মেমোরি আনবে
    trusted_data = memory.get_semantic_memories(user_input, limit=5, threshold=threshold)
    
    # মেমোরিকে স্ট্র্যাটেজিক ফ্রেমিং দেওয়া
    formatted_memory = []
    for m in trusted_data:
        # m[0]=content, m[1]=outcome, m[2]=trust_score, m[3]=similarity
        formatted_memory.append(f"[{str(m[1]).upper()}] (Trust: {str(m[2])}) - {m[0]}")
    
    recent_memories = "\n".join(formatted_memory)
    
    # ৩. CEO Mode System Prompt
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

    # AI Response Logic
    response = ollama.chat(model=LLM_MODEL, messages=[
        {'role': 'system', 'content': system_prompt},
        {'role': 'user', 'content': user_input},
    ])
    ai_msg = response['message']['content'].strip()

    # Tool Execution (আগের মতো থাকবে)
    if "SCAN_DRIVES" in ai_msg:
        tool_result = get_drives()
        final_prompt = f"User: {user_input}\nDrives: {tool_result}\nSummarize available storage."
    elif "LIST_FILES" in ai_msg:
        path = ai_msg.split("LIST_FILES")[-1].strip()
        tool_result = list_files(path)
        final_prompt = f"User: {user_input}\nScan: {tool_result}\nList findings."
    elif "READ_FILE" in ai_msg:
        path = ai_msg.split("READ_FILE")[-1].strip()
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
                memory.cursor.execute("SELECT COUNT(*), AVG(trust_score) FROM memories")
                stats = memory.cursor.fetchone()
                
                memory.cursor.execute("SELECT COUNT(*) FROM processed_files")
                files = memory.cursor.fetchone()
                
                print(f"🧠 Total Institutional Memories: {stats[0]}")
                print(f"🛡️ Average Memory Trust Score: {round(stats[1] or 0, 2)}")
                print(f"📂 Total Files Processed (Delta Sync): {files[0]}")
                print(f"⚙️ Active Triage Engine: Strategic Context Injection v1.0")
                print("---------------------------------------\n")
                continue
                       
            print("Phantom is thinking...", end="\r")
            reply = chat_with_ai(user_msg)
            print(f"Phantom: {reply}")
            
            # --- FIX #4: DECISION FEEDBACK LOOP (NEW) ---
            # উত্তরের ওপর ভিত্তি করে সাকসেস বা নিউট্রাল আউটকাম ডিটেকশন
            outcome = "success" if any(x in reply.lower() for x in ["found", "read", "content", "here is"]) else "neutral"
            
            # নতুন ইন্টেলিজেন্ট মেমোরি ব্রিক তৈরি
            new_brick = PhantomMemoryBrick(
                content=f"User: {user_msg} | AI: {reply}",
                source="Executive_Interaction",
                decision_outcome=outcome,
                confidence_score=0.8
            )
            
            # মেমোরি সেভ (যা অটোমেটিক ট্রাস্ট স্কোর ক্যালকুলেট করবে)
            memory.save_intelligent_memory(new_brick)
        
        except KeyboardInterrupt:
            print("\nExiting...")
            break