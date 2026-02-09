import os
import time
import sqlite3
import ollama
import numpy as np
import shutil
import hashlib
import uuid
import threading
import string
import json
from datetime import datetime
from sentence_transformers import SentenceTransformer

VAULT_DIR_NAME = ".phantom_secure_vault"
LLM_MODEL = "llama3"

def secure_execute(action, target=None):
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
            return ["/"]

        elif action == "WALK_DIR":
            files_found = []
            forbidden = ["System32", "Windows", "AppData", VAULT_DIR_NAME, ".git", "node_modules"]
            for root, dirs, files in os.walk(target):
                if any(x in root for x in forbidden):
                    continue
                for f in files:
                    if f.lower().endswith(('.txt', '.docx', '.pdf', '.log', '.md')):
                        files_found.append(os.path.join(root, f))
            return files_found

        elif action == "READ_FILE":
            with open(target, 'r', encoding='utf-8', errors='ignore') as f:
                return f.read(5000)

        elif action == "GET_HASH":
            if not os.path.exists(target):
                return None
            hasher = hashlib.md5()
            with open(target, 'rb') as f:
                for chunk in iter(lambda: f.read(65536), b""):
                    hasher.update(chunk)
            return hasher.hexdigest()

        elif action == "MOVE_FILE":
            src, dst = target
            shutil.move(src, dst)
            return dst

        elif action == "LIST_DIR":
            return os.listdir(target)

        elif action == "BASENAME":
            return os.path.basename(target)

    except Exception as e:
        return str(e)

class PhantomMemoryBrick:
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

class MemoryManager:
    def __init__(self):
        db_path = secure_execute("INIT_DB_PATH")
        self.conn = sqlite3.connect(db_path, check_same_thread=False)
        self.cursor = self.conn.cursor()
        self.cursor.execute("""CREATE TABLE IF NOT EXISTS memories
            (id TEXT PRIMARY KEY, content TEXT, timestamp TEXT,
             source TEXT, outcome TEXT, confidence REAL,
             trust_score REAL, tier TEXT, embedding BLOB)""")
        self.conn.commit()
        self.encoder = SentenceTransformer('all-MiniLM-L6-v2')

    def save_intelligent_memory(self, brick):
        tier = "tactical"
        if brick.confidence_score >= 0.9 or any(w in brick.content.lower() for w in ['vision','strategy','investor','plan']):
            tier = "strategic"
        metadata = brick.to_metadata()
        t_score = calculate_trust_score(metadata)
        vector = self.encoder.encode(brick.content).tobytes()
        self.cursor.execute("""INSERT INTO memories VALUES (?,?,?,?,?,?,?,?,?)""",
            (brick.id, brick.content, brick.timestamp, brick.source,
             brick.decision_outcome, brick.confidence_score, t_score, tier, vector))
        self.conn.commit()
        return t_score

    def get_relevant_context(self, query_text, top_k=5):
        self.cursor.execute("SELECT content, confidence, timestamp, tier FROM memories")
        rows = self.cursor.fetchall()
        if not rows:
            return ""
        scored = []
        for content, conf, ts_str, tier in rows:
            try:
                ts = datetime.fromisoformat(ts_str)
            except:
                ts = datetime.now()
            hours_old = (datetime.now() - ts).total_seconds() / 3600
            decay = 1.0 - (hours_old / (720 if tier=="strategic" else 48))
            decay = max(0.1, decay)
            score = (conf * 0.7) + (decay * 0.3)
            scored.append((score, tier, content))
        scored.sort(reverse=True)
        return "\n".join([f"[{t.upper()}] {c}" for _,t,c in scored[:top_k]])

def chat_with_ai(user_input, memory_engine):
    if not user_input:
        return "NO_INPUT"

    recent_memories = memory_engine.get_relevant_context(user_input, 5)

    prompt = (
        f"Context:\n{recent_memories}\n\n"
        f"User: {user_input}\n"
    )

    try:
        raw = ollama.chat(model=LLM_MODEL, messages=[{"role": "user", "content": prompt}])
        raw_str = str(raw)  # LOCK-free, direct string
    except Exception as e:
        raw_str = f"ERROR: {e}"

    return raw_str  # no enforce_lock_2, no UNKNOWN

if __name__ == "__main__":
    vault = secure_execute("INIT_SYSTEM")
    if not vault:
        print("FAILED_TO_INIT_VAULT")
        exit()

    memory = MemoryManager()
    print("--- PHANTOM AI (LOCKS REMOVED) ---")

    while True:
        try:
            msg = input("\nYou: ")
            if msg.lower() in ["exit","quit"]:
                break
            reply = chat_with_ai(msg, memory)
            print("Phantom:", reply)
            brick = PhantomMemoryBrick(
                content=f"User: {msg} | AI: {reply}",
                source="Executive_Interaction",
                decision_outcome="neutral",
                confidence_score=0.8
            )
            memory.save_intelligent_memory(brick)
        except KeyboardInterrupt:
            break
        except Exception as e:
            print(f"ERROR: {e}")
            break
