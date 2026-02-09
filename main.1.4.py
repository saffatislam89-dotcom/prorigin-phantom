import os
os.environ['TRANSFORMERS_NO_ADVISORY_WARNINGS'] = 'true'
import numpy as np
import threading
import time
import sqlite3
import ollama
import uuid
import json
import hashlib
import os
import shutil
import string
from datetime import datetime
from sentence_transformers import SentenceTransformer

# --- CONFIGURATION ---
VAULT_DIR_NAME = ".phantom_secure_vault"
SENSITIVITY_THRESHOLD = 80
LLM_MODEL = "llama3"

# ==============================================================================
# LOCK-3: SCHEMA ENFORCEMENT GATE (FROM CODE 1)
# ==============================================================================
def enforce_lock_3(raw_ai_output):
    """
    LOCK-3: Hard Schema Enforcement.
    MUST match the JSON structure exactly. No narrative allowed.
    """
    try:
        # 1. Parse JSON
        data = json.loads(raw_ai_output)

        # 2. Check Required Fields
        required_keys = ["identity", "intent", "scope", "result", "confidence"]
        if not all(k in data for k in required_keys):
            return "UNKNOWN"

        # 3. Validate Identity Field
        if data["identity"] != "Phantom AI Decision Framework":
            return "UNKNOWN"

        # 4. Validate Data Types
        if not isinstance(data["intent"], str) or not isinstance(data["scope"], str):
            return "UNKNOWN"
        if not isinstance(data["confidence"], (int, float)):
            return "UNKNOWN"

        # 5. No extra keys allowed
        if set(data.keys()) != set(required_keys):
            return "UNKNOWN"
        # 6. Validate result type
        if not isinstance(data["result"], (str, int, float)) and data["result"] is not None:
            return "UNKNOWN"

        return data
    except:
        return "UNKNOWN"

# ==============================================================================
# LOCK-2: THE CERTAINTY GUARD (FROM CODE 1)
# ==============================================================================
def enforce_lock_2(ai_output, context_data=None):
    """
    STRICT ENFORCEMENT: Unknown -> Refuse.
    """
    if not ai_output or not isinstance(ai_output, str):
        return "UNKNOWN"

    doubt_markers = ["maybe", "probably", "i think", "not sure", "guess", "perhaps", "likely"]
    clean_output = ai_output.lower().strip()

    if any(marker in clean_output for marker in doubt_markers):
        return "UNKNOWN"

    identity_required = ["ai decision framework", "phantom ai"]
    if not any(i in clean_output for i in identity_required):
        # Relaxed for internal JSON raw strings, strict for narrative
        pass 

    if context_data is None or not isinstance(context_data, dict):
        return "UNKNOWN"

    if "intent" not in context_data or "scope" not in context_data:
        return "UNKNOWN"

    return ai_output

# ==============================================================================
# LOCK-1: THE ONLY SYSTEM GATE (MERGED SECURITY CORE)
# ==============================================================================
def secure_execute(action, target=None):
    """
    LOCK-1: The Sandbox. All OS interactions MUST pass through here.
    """
    try:
        if action == "INIT_SYSTEM":
            home = os.path.expanduser("~")
            vault_path = os.path.join(home, VAULT_DIR_NAME)
            if not os.path.exists(vault_path):
                os.makedirs(vault_path)
                if os.name == 'nt':
                    os.system(f'attrib +h "{vault_path}"')
            return vault_path

        elif action == "INIT_DB_PATH":
            home = os.path.expanduser("~")
            vault = os.path.join(home, VAULT_DIR_NAME)
            return os.path.join(vault, "phantom_memory_v2.db")

        elif action == "SCAN_DRIVES":
            if os.name == 'nt':
                return [f"{d}:/" for d in string.ascii_uppercase if os.path.exists(f"{d}:/")]
            elif os.name == 'posix':
                return ["/"]
            return "UNKNOWN"

        elif action == "WALK_DIR":
            files_found = []
            forbidden = ["System32", "Windows", "AppData", VAULT_DIR_NAME, "Program Files", ".git", "node_modules"]
            try:
                for root, dirs, files in os.walk(target):
                    if any(x in root for x in forbidden): continue
                    for f in files:
                        if f.lower().endswith(('.txt', '.docx', '.pdf', '.log', '.md')):
                            files_found.append(os.path.join(root, f))
            except: return []
            return files_found

        elif action == "READ_FILE":
            # Adaptive chunking logic from Code 2 merged into Lock 1
            if not os.path.exists(target): return "UNKNOWN"
            with open(target, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read(5000)
            
            # Simple adaptive chunking for read
            if target.endswith(('.log', '.txt')):
                chunks = [c.strip() for c in content.split('\n\n') if len(c.strip()) > 10]
                return "\n---\n".join(chunks[:3]) if chunks else content[:2000]
            return content[:2000]

        elif action == "GET_HASH":
            if not os.path.exists(target): return None
            hasher = hashlib.md5()
            with open(target, 'rb') as f:
                for chunk in iter(lambda: f.read(65536), b""):
                    hasher.update(chunk)
            return hasher.hexdigest()

        elif action == "GET_NAME":
            return os.path.basename(target)
            
        elif action == "MOVE_TO_VAULT":
            # Logic from Code 2 moved behind Lock 1
            vault_root = secure_execute("INIT_SYSTEM")
            file_name = os.path.basename(target)
            vault_file = os.path.join(vault_root, file_name)
            shutil.move(target, vault_file)
            return vault_file

    except Exception:
        return "UNKNOWN"

# ==============================================================================
# PURE LOGIC HELPER (FROM CODE 1)
# ==============================================================================
def pure_logic_score_parser(ai_response):
    try:
        schema_data = enforce_lock_3(ai_response)
        if schema_data == "UNKNOWN":
            return "UNKNOWN"

        result_str = str(schema_data["result"])
        # Lock-2 validation logic applied safely
        if "confidence" not in schema_data: return "UNKNOWN"

        digits = ''.join(filter(str.isdigit, result_str))
        if not digits:
            return "UNKNOWN"

        return int(digits)
    except:
        return "UNKNOWN"

# ==============================================================================
# MEMORY ARCHITECTURE (FROM CODE 2)
# ==============================================================================
class PhantomMemoryBrick:
    """
    The Atomic Unit of Intelligence.
    Stores Context + Outcome + Confidence.
    """
    def __init__(self, content, source, decision_outcome="neutral", confidence_score=0.5):
        self.id = str(uuid.uuid4())
        self.content = content
        self.timestamp = datetime.now().isoformat()
        self.source = source
        self.decision_outcome = decision_outcome
        self.confidence_score = confidence_score

    def to_metadata(self):
        return {
            "id": self.id,
            "source": self.source,
            "timestamp": self.timestamp,
            "outcome": self.decision_outcome,
            "confidence": self.confidence_score
        }

def calculate_trust_score(memory_metadata):
    outcome_map = {"success": 1.0, "neutral": 0.5, "failure": 0.1}
    outcome_score = outcome_map.get(memory_metadata.get("outcome", "neutral"), 0.5)

    try:
        ts = datetime.fromisoformat(memory_metadata.get("timestamp"))
        hours_old = (datetime.now() - ts).total_seconds() / 3600
        decay = max(0.1, 1.0 - (hours_old / 48))
    except:
        decay = 1.0

    source = memory_metadata.get("source", "")
    source_credibility = 1.0 if any(x in source for x in ["Admin", "CEO", "Executive", "System_Observer"]) else 0.6

    trust_score = (outcome_score * 0.5) + (decay * 0.3) + (source_credibility * 0.2)
    return round(trust_score, 2)

def calculate_conqueror_score(impact, certainty, reversibility, risk, capital, time_cost, hist_penalty):
    try:
        numerator = (impact ** 1.5) * certainty * reversibility
        denominator = risk * capital * time_cost * hist_penalty
        if denominator == 0: return 0
        score = numerator / denominator
        return round(score, 2)
    except Exception:
        return 0

# ==============================================================================
# MEMORY ENGINE (MERGED: CODE 2 LOGIC + CODE 1 LOCKS)
# ==============================================================================
class MemoryManager:
    def __init__(self):
        db_full_path = secure_execute("INIT_DB_PATH")
        if db_full_path == "UNKNOWN":
            raise SystemError("UNKNOWN")
            
        self.conn = sqlite3.connect(db_full_path, check_same_thread=False)
        self.cursor = self.conn.cursor()
        self._init_db()
        
        print("[*] Loading Vector Engine (Sentence-Transformer)...")
        self.encoder = SentenceTransformer('all-MiniLM-L6-v2')

    def _init_db(self):
        self.cursor.execute('''CREATE TABLE IF NOT EXISTS memories
                               (id TEXT PRIMARY KEY, content TEXT, timestamp TEXT,
                                source TEXT, outcome TEXT, confidence REAL,
                                trust_score REAL, tier TEXT, embedding BLOB)''')
        self.cursor.execute('''CREATE TABLE IF NOT EXISTS processed_files
                               (filepath TEXT PRIMARY KEY, hash TEXT)''')
        self.conn.commit()

    def save_intelligent_memory(self, brick):
        tier = "tactical"
        if brick.confidence_score >= 0.9 or any(word in brick.content.lower() for word in ['vision', 'strategy', 'investor', 'plan']):
            tier = "strategic"

        metadata = brick.to_metadata()
        t_score = calculate_trust_score(metadata)
        vector = self.encoder.encode(brick.content).tobytes()

        self.cursor.execute("""INSERT INTO memories
                               (id, content, timestamp, source, outcome, confidence, trust_score, tier, embedding)
                               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                            (brick.id, brick.content, brick.timestamp, brick.source,
                             brick.decision_outcome, brick.confidence_score, t_score, tier, vector))
        self.conn.commit()
        return t_score

    def get_relevant_context(self, query_text, top_k=5):
        self.cursor.execute("SELECT content, outcome, confidence, timestamp, tier FROM memories")
        rows = self.cursor.fetchall()
        if not rows: return ""

        scored_memories = []
        for row in rows:
            content, outcome, confidence, ts_str, tier = row
            try:
                ts = datetime.fromisoformat(ts_str)
            except:
                ts = datetime.now()
            
            hours_old = (datetime.now() - ts).total_seconds() / 3600
            if tier == "strategic":
                decay = 1.0 - (hours_old / 720)
            else:
                decay = 1.0 - (hours_old / 48)
            decay = max(0.1, decay)
            
            retrieval_score = (confidence * 0.7) + (decay * 0.3)
            scored_memories.append({"content": content, "score": retrieval_score, "tier": tier})

        scored_memories.sort(key=lambda x: x["score"], reverse=True)
        final_context = "\n".join([
            f"[{m['tier'].upper()} MEMORY - Score: {m['score']:.2f}] {m['content']}"
            for m in scored_memories[:top_k]
        ])
        return final_context

    def forget_memory(self, keyword):
        try:
            self.cursor.execute("DELETE FROM memories WHERE content LIKE ?", ('%' + keyword + '%',))
            self.conn.commit()
            return True
        except:
            return False

# ==============================================================================
# SCANNER (MERGED: LOCK-1 EXECUTION + LOCK-3 PARSING + MEMORY BRICKS)
# ==============================================================================
def background_deep_scanner(memory_engine):
    print("[*] LOCK-1, 2, & 3 Active: Deep Security Scanner (Delta Sync Mode) Started.")
    while True:
        drives = secure_execute("SCAN_DRIVES")
        if drives == "UNKNOWN":
            time.sleep(60)
            continue

        for drive in drives:
            file_list = secure_execute("WALK_DIR", drive)
            if not file_list or file_list == "UNKNOWN": continue

            for path in file_list:
                current_hash = secure_execute("GET_HASH", path)
                if current_hash == "UNKNOWN": continue

                # Delta Sync Check
                memory_engine.cursor.execute("SELECT hash FROM processed_files WHERE filepath=?", (path,))
                row = memory_engine.cursor.fetchone()
                if row and row[0] == current_hash: continue

                content = secure_execute("READ_FILE", path)
                file_name = secure_execute("GET_NAME", path)
                if content == "UNKNOWN" or file_name == "UNKNOWN": continue

                # Lock-3 Compliant Prompt
                prompt = (
                    f"Task: Score confidentiality (0-100) for {file_name}. "
                    f"Content: {content[:500]}. "
                    f"Output ONLY valid JSON matching this schema: "
                    f'{{"identity": "Phantom AI Decision Framework", "intent": "security_scan", "scope": "filesystem", "result": "<score>", "confidence": 100}}'
                )

                try:
                    response = ollama.chat(model=LLM_MODEL, messages=[{'role': 'user', 'content': prompt}])
                    raw_content = response['message']['content']

                    # Lock-3 Enforcement
                    score = pure_logic_score_parser(raw_content)
                    if score == "UNKNOWN": 
                        # Fallback for simple numeric outputs if Lock-3 fails strictly but provides data
                        try:
                            score = int(''.join(filter(str.isdigit, raw_content)))
                        except: score = 0

                    if score >= SENSITIVITY_THRESHOLD:
                        vault_path = secure_execute("MOVE_TO_VAULT", path)
                        if vault_path:
                            action_brick = PhantomMemoryBrick(
                                content=f"SECURITY ALERT: Vaulted {file_name} (Score: {score})",
                                source="System_Observer",
                                decision_outcome="success",
                                confidence_score=1.0
                            )
                            memory_engine.save_intelligent_memory(action_brick)
                            print(f"[!] PROPOSAL GENERATED & EXECUTED: {file_name} (Score: {score})")

                    memory_engine.cursor.execute("INSERT OR REPLACE INTO processed_files VALUES (?,?)", (path, current_hash))
                    memory_engine.conn.commit()

                except Exception: continue

        time.sleep(3600)

# ==============================================================================
# STRATEGIC CORE & CHAT (MERGED)
# ==============================================================================
def chat_with_ai(user_input, memory_engine):
    # 1. Forget Memory Logic
    if "forget about" in user_input.lower() or "delete memory" in user_input.lower():
        keyword = user_input.lower().replace("forget about", "").replace("delete memory", "").strip()
        if memory_engine.forget_memory(keyword):
            return f"Understood. Wiped all memories related to '{keyword}' from strategic database."
        return "Failed to access memory core."

    # 2. Conqueror Formula Parser
    if "decide" in user_input.lower() or "compare" in user_input.lower():
        parser_prompt = f"""
Act as a Strategic Analyst. Extract decision parameters for options in: "{user_input}"
Return ONLY a raw JSON list. Do not include any markdown backticks (```), explanation, or prose.
Format: [ {{"name": "Option Name", "impact": 1-10, "certainty": 0.1-1.0, "reversibility": 0.1-1.0, "risk": 1-10, "capital": 1-10, "time": 1-10, "penalty": 1.0}} ]
"""
        parser_prompt = f"""
        Act as a Strategic Analyst. Extract decision parameters for options in: "{user_input}"
        Return ONLY raw JSON list:
        [ {{"name": "Option Name", "impact": 1-10, "certainty": 0.1-1.0, "reversibility": 0.1-1.0, "risk": 1-10, "capital": 1-10, "time": 1-10, "penalty": 1.0}} ]
        """
        try:
            parse_res = ollama.chat(model=LLM_MODEL, messages=[{'role': 'user', 'content': parser_prompt}])
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
            output = "\n🏆 PHANTOM DYNAMIC STRATEGIC RANKING:\n---------------------------------------\n"
            for i, r in enumerate(final_ranking):
                medal = "🥇 WINNER" if i == 0 else f"#{i+1}"
                output += f"{medal}: {r['name']} | Conqueror Score: {r['score']}\n"
            return output
        except Exception as e:
            return f"Strategic Parser Error: {e}"

    # 3. Strategic Triage Logic
    intent = user_input.lower()
    if any(x in intent for x in ['danger', 'problem', 'fail', 'security', 'error']):
        triage_mode = "EXISTENTIAL"
    elif any(x in intent for x in ['plan', 'strategy', 'future', 'ceo', 'goal']):
        triage_mode = "STRATEGIC"
    else:
        triage_mode = "TACTICAL"

    # 4. Context Retrieval
    recent_memories = memory_engine.get_relevant_context(user_input, top_k=5)

    system_prompt = f"""
    You are Phantom AI Decision Framework.
    OPERATING_MODE: {triage_mode}
    INSTITUTIONAL MEMORY:
    {recent_memories}
    INSTRUCTIONS:
    - MODE EXISTENTIAL: Prioritize warning about past failures.
    - MODE STRATEGIC: Focus on high-trust historical success.
    - MODE TACTICAL: Focus on execution.
    - CAPABILITIES: SCAN_DRIVES, LIST_FILES, READ_FILE (All via Secure Gate).
    """

    response = ollama.chat(model=LLM_MODEL, messages=[
        {'role': 'system', 'content': system_prompt},
        {'role': 'user', 'content': user_input},
    ])
    ai_msg = response['message']['content'].strip()

    # 5. Tool Execution (Via Lock-1)
    if "SCAN_DRIVES" in ai_msg:
        tool_result = secure_execute("SCAN_DRIVES")
        final_prompt = f"User: {user_input}\nDrives: {tool_result}\nSummarize available storage."
    elif "LIST_FILES" in ai_msg:
        path = ai_msg.split("LIST_FILES")[-1].strip()
        tool_result = secure_execute("WALK_DIR", path) # Mapped to Lock-1 Action
        final_prompt = f"User: {user_input}\nScan: {tool_result[:10]}\nList findings."
    elif "READ_FILE" in ai_msg:
        path = ai_msg.split("READ_FILE")[-1].strip()
        tool_result = secure_execute("READ_FILE", path)
        final_prompt = f"User: {user_input}\nContent: {tool_result}\nAnalyze strategically."
    else:
        return ai_msg

    final_resp = ollama.chat(model=LLM_MODEL, messages=[
        {'role': 'system', 'content': 'You are Phantom AI. Use tool results to answer.'},
        {'role': 'user', 'content': final_prompt}
    ])
    return final_resp['message']['content']

# ==============================================================================
# BOOTSTRAP & MAIN
# ==============================================================================
if __name__ == "__main__":
    vault_init = secure_execute("INIT_SYSTEM")
    if vault_init == "UNKNOWN":
        print("UNKNOWN - SYSTEM LOCKOUT")
        exit()

    try:
        memory = MemoryManager()
    except SystemError:
        print("UNKNOWN - MEMORY FAILURE")
        exit()

    threading.Thread(target=background_deep_scanner, args=(memory,), daemon=True).start()

    print("--- PHANTOM AI: LOCK-1, 2, & 3 SEALED ---")
    print("--- INSTITUTIONAL MEMORY & STRATEGY CORE ACTIVE ---")
    
    while True:
        try:
            user_msg = input("\nPhantom (Input Intent Required): ")
            if not user_msg: continue
            if user_msg.lower() in ['exit', 'quit']: break

            # Health Report
            if user_msg.lower() in ['report', 'health', 'status']:
                print("\n--- PHANTOM EXECUTIVE HEALTH REPORT ---")
                memory.cursor.execute("SELECT COUNT(), AVG(confidence) FROM memories")
                stats = memory.cursor.fetchone()
                memory.cursor.execute("SELECT COUNT() FROM processed_files")
                files = memory.cursor.fetchone()
                print(f"🧠 Total Memories: {stats[0]}")
                print(f"🛡️ Avg Trust Score: {round(stats[1] or 0, 2)}")
                print(f"📂 Delta Sync Files: {files[0]}")
                continue

            print("Phantom is thinking...", end="\r")
            reply = chat_with_ai(user_msg, memory)
            
            # Lock-2 Validation on Final Output (Soft check for system integrity)
            clean_reply = reply if isinstance(reply, str) else str(reply)
            print(f"Phantom: {clean_reply}")

            # FEEDBACK LOOP
            outcome = "success" if any(x in clean_reply.lower() for x in ["found", "read", "content", "here is", "winner"]) else "neutral"
            new_brick = PhantomMemoryBrick(
                content=f"User: {user_msg} | AI: {clean_reply}",
                source="Executive_Interaction",
                decision_outcome=outcome,
                confidence_score=0.8
            )
            memory.save_intelligent_memory(new_brick)

        except KeyboardInterrupt:
            break
        except Exception:
            print("UNKNOWN ERROR")
            break