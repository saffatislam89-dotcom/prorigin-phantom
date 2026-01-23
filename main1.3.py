"""
main1.3.py - Minimalist Phantom AI (local-only Ollama reasoning + Memory)

Purpose (per request):
- Keep only the local Ollama (llama3) integration that runs on your laptop/GPU.
- Keep the MemoryManager (SQLite) for long-term memory to help reasoning.
- Remove all external hardware/app control modules and tool-calling logic.
- Provide a very small main loop that accepts user input (voice if available) and returns
  LLM-driven replies only. The assistant cannot call external tools; it can "think" and "reply".
- Robust parsing of the model's JSON response and graceful fallbacks.

Usage:
- Ensure ollama is installed and the "llama3" model is available locally.
- Optionally have JarvisVoiceEngine available for voice I/O; otherwise the script will use console I/O.
"""

import os
import re
import sys
import json
import time
import sqlite3
import traceback
from datetime import datetime
from collections import deque

# Local Ollama client (must be installed and server/model present)
import ollama

# Try to import voice engine if available; otherwise fall back to console IO
try:
    from jarvis_voice_engine import JarvisVoiceEngine  # optional
except Exception:
    JarvisVoiceEngine = None

# -------------------
# Config
# -------------------
LLM_MODEL = "llama3"
MEMORY_DB_DEFAULT = os.path.join(os.path.expanduser("~"), ".phantom_memory.db")
MODEL_CHECK_RETRIES = 2
MODEL_CHECK_DELAY = 2.0


# -------------------
# MemoryManager (kept)
# -------------------
class MemoryManager:
    """
    Simple local long-term memory using SQLite.
    Stores 'content', optional 'tags', and 'created_at'.
    """

    def __init__(self, db_path: str = None):
        self.db_path = db_path or MEMORY_DB_DEFAULT
        self._ensure_db()

    def _get_conn(self):
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
            cur.execute("CREATE INDEX IF NOT EXISTS idx_memories_content ON memories(content)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_memories_tags ON memories(tags)")
            conn.commit()
        except Exception:
            traceback.print_exc()
        finally:
            try:
                conn.close()
            except Exception:
                pass

    def store(self, content: str, tags=None) -> bool:
        if not content:
            return False
        if isinstance(tags, (list, tuple)):
            tags = ",".join([t.strip().lower() for t in tags if t])
        elif isinstance(tags, str):
            tags = tags.strip().lower()
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
        if not keywords:
            return []
        try:
            conn = self._get_conn()
            cur = conn.cursor()
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
                results.append({"content": r[0], "tags": r[1] or "", "created_at": r[2] or ""})
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
        if not query_text:
            return []
        tokens = re.findall(r"\w{4,}", query_text.lower())
        seen = []
        for t in tokens:
            if t not in seen:
                seen.append(t)
            if len(seen) >= 8:
                break
        return self.retrieve_by_keywords(seen, limit=limit)


# instantiate memory manager
memory = MemoryManager()


def save_memory(user_input: str, ai_response: str, tags=None) -> bool:
    try:
        content = f"User: {user_input}\nAssistant: {ai_response}"
        return memory.store(content, tags=tags)
    except Exception:
        traceback.print_exc()
        return False


def get_relevant_memories(user_input: str, limit=5):
    try:
        rows = memory.search(user_input, limit=limit)
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
# Fallback (simple conversational fallback)
# -------------------
def local_keyword_fallback(user_text: str):
    t = (user_text or "").lower()
    if any(w in t for w in ("exit", "quit", "goodbye", "stop")):
        return {"action": "reply", "args": {}, "reply": "Goodbye."}
    if "time" in t:
        return {"action": "reply", "args": {}, "reply": f"The time is {datetime.now().strftime('%I:%M %p')}."}
    # Generic fallback
    return {"action": "reply", "args": {}, "reply": "I'm sorry, I couldn't interpret that. Could you rephrase?"}


# -------------------
# Ollama LLM integration (core)
# -------------------
def query_llama_for_action(user_text: str, context: str = None, timeout: int = 8):
    """
    Query local Ollama (llama3) for a structured JSON: {"action":"reply","args":{},"reply":"..."}
    Injects relevant memories to system prompt to improve reasoning.
    Robustly extracts the JSON substring between first '{' and last '}'.
    Falls back to local_keyword_fallback on errors.
    """
    # Prepare memories and system prompt
    try:
        past = get_relevant_memories(user_text, limit=5)
        memories_block = ""
        if past:
            memories_block = "Past Memories (most relevant):\n" + "\n".join(f"- {m}" for m in past) + "\n\n"

        system_message = (
            "You are Phantom AI, a local assistant running on the user's machine. You have access to a local long-term memory\n"
            "which is provided below. Use it when relevant to produce better replies.\n\n"
            f"{memories_block}"
            "IMPORTANT: You MUST respond with EXACTLY one valid JSON object and NOTHING ELSE. The JSON object must have keys:\n"
            '  "action": "reply"\n'
            '  "args": {}  (can be empty)\n'
            '  "reply": "the assistant response text"\n\n'
            "Do NOT include any commentary, explanations, or markdown. Return only the JSON object."
        )

        user_message = f"User said: {user_text}\n\nContext: {context or ''}"

        # Call Ollama
        response = ollama.chat(
            model=LLM_MODEL,
            messages=[
                {"role": "system", "content": system_message},
                {"role": "user", "content": user_message},
            ],
        )
    except Exception as e:
        print(f"[!] Ollama call failed: {e}")
        traceback.print_exc()
        return local_keyword_fallback(user_text)

    # Extract textual content
    try:
        response_text = ""
        if isinstance(response, dict):
            # common shapes
            if "message" in response and isinstance(response["message"], dict):
                response_text = response["message"].get("content", "") or ""
            elif "choices" in response and response["choices"]:
                first = response["choices"][0]
                if isinstance(first, dict):
                    msg = first.get("message")
                    if isinstance(msg, dict):
                        response_text = msg.get("content", "") or ""
                    else:
                        response_text = first.get("text", "") or ""
        else:
            # attribute-style
            msg = getattr(response, "message", None)
            if msg is not None and getattr(msg, "content", None) is not None:
                response_text = msg.content
            else:
                choices = getattr(response, "choices", None)
                if choices and len(choices) > 0:
                    c0 = choices[0]
                    if getattr(c0, "message", None) and getattr(c0.message, "content", None):
                        response_text = c0.message.content
                    elif getattr(c0, "text", None):
                        response_text = c0.text
        if not response_text:
            response_text = str(response)
    except Exception:
        response_text = str(response)

    if not response_text:
        return local_keyword_fallback(user_text)

    # Robust JSON extraction: slice from first '{' to last '}' and parse
    try:
        first = response_text.find("{")
        last = response_text.rfind("}")
        if first == -1 or last == -1 or last <= first:
            # nothing parsable
            print("[!] No JSON found in LLM response; returning fallback.")
            return local_keyword_fallback(user_text)
        json_chunk = response_text[first:last + 1]
        # Clean common trailing commas or minor issues, then parse
        try:
            parsed = json.loads(json_chunk)
        except json.JSONDecodeError:
            cleaned = re.sub(r",\s*}", "}", json_chunk)
            cleaned = re.sub(r",\s*]", "]", cleaned)
            parsed = json.loads(cleaned)

        # Validate format: must contain 'action' and 'reply'
        if not isinstance(parsed, dict) or "action" not in parsed or "reply" not in parsed:
            print("[!] Parsed JSON missing required keys; falling back.")
            return local_keyword_fallback(user_text)

        # Ensure action is 'reply' (we only support reply)
        parsed_action = parsed.get("action", "").strip().lower()
        if parsed_action != "reply":
            # convert to reply by moving any textual content into reply
            reply_text = parsed.get("reply") or str(parsed.get("args") or parsed)
            return {"action": "reply", "args": {}, "reply": reply_text}

        return parsed

    except Exception as e:
        print(f"[!] Error parsing LLM response: {e}")
        traceback.print_exc()
        return local_keyword_fallback(user_text)


# -------------------
# Dispatcher (minimal)
# -------------------
def dispatch_action(action_obj, voice):
    """
    Minimal dispatcher: the assistant can only reply (no tool calls).
    action_obj expected shape: {"action":"reply","args":{},"reply":"..."}
    voice: an object with speak(text) method, or None (falls back to print).
    """
    action = (action_obj.get("action") or "").strip().lower()
    reply_text = action_obj.get("reply") or ""

    if not reply_text:
        reply_text = "I have nothing to say."

    # Speak or print
    try:
        if voice:
            voice.speak(reply_text)
        else:
            print("Phantom:", reply_text)
    except Exception:
        print("Phantom:", reply_text)

    # Save memory of the exchange (optional)
    try:
        save_memory("", reply_text)
    except Exception:
        pass

    return True


# -------------------
# Ollama availability check (lightweight)
# -------------------
def check_ollama_available(retries=MODEL_CHECK_RETRIES, delay=MODEL_CHECK_DELAY):
    for i in range(retries):
        try:
            resp = ollama.list()
            model_names = []
            if isinstance(resp, dict):
                for m in resp.get("models", []):
                    if isinstance(m, dict):
                        model_names.append(m.get("name", ""))
            else:
                try:
                    for m in resp:
                        if isinstance(m, dict):
                            model_names.append(m.get("name", ""))
                except Exception:
                    pass
            if LLM_MODEL in model_names:
                print(f"[*] Ollama ready (model '{LLM_MODEL}' available).")
                return True
            else:
                print(f"[!] Ollama reachable but model '{LLM_MODEL}' not present. Available: {model_names}")
                return False
        except Exception as e:
            print(f"[!] Ollama check attempt {i+1}/{retries} failed: {e}")
            if i < retries - 1:
                time.sleep(delay)
            else:
                return False
    return False


# -------------------
# Main loop (voice or console)
# -------------------
def main_loop():
    # Prepare voice interface if available
    voice = None
    if JarvisVoiceEngine is not None:
        try:
            voice = JarvisVoiceEngine()
            voice.greet()
        except Exception:
            voice = None

    if voice is None:
        print("Phantom AI (console mode). Type 'exit' to quit.")

    # Lightweight Ollama check
    if not check_ollama_available():
        print("[!] Ollama not ready or model missing. Exiting.")
        return

    while True:
        try:
            if voice:
                raw = voice.listen()
            else:
                raw = input("You: ")
        except Exception as e:
            print(f"[!] Input error: {e}")
            continue

        if not raw or not raw.strip():
            continue

        cmd = raw.strip()
        if cmd.lower() in ("exit", "quit", "stop", "goodbye"):
            if voice:
                voice.speak("Goodbye.")
            else:
                print("Phantom: Goodbye.")
            break

        # Query local LLM for action/reply
        action_obj = query_llama_for_action(cmd, context=None, timeout=8)

        # Dispatch (will only speak reply)
        dispatch_action(action_obj, voice)

        # small delay to avoid tight loop
        time.sleep(0.05)


if __name__ == "__main__":
    try:
        main_loop()
    except KeyboardInterrupt:
        print("\n[*] Interrupted by user. Exiting.")
    except Exception as e:
        print(f"[!] Fatal error: {e}")
        traceback.print_exc()