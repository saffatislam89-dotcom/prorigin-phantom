"""
jarvis_voice_engine.py - Senior Engineer Version
Fixes: Male voice priority, Resource safety, Precision rate, and Noise suppression.
"""

from __future__ import annotations
import threading

class JarvisVoiceEngine:
    def __init__(self) -> None:
        """Initialize placeholders. No hardware overhead at startup."""
        self._tts_engine = None
        self._recognizer = None
        self._lock = threading.Lock() # Ensures voice commands don't overlap

    def _init_tts(self) -> bool:
        """Lazily initialize TTS with Jarvis-like persona."""
        if self._tts_engine is not None:
            return True
        try:
            import pyttsx3
            engine = pyttsx3.init()
            
            # --- JARVIS VOICE SETTINGS ---
            voices = engine.getProperty("voices")
            if voices:
                # Priority: Look for a Male voice (e.g., Microsoft David)
                selected_voice = voices[0].id
                for v in voices:
                    name = v.name.lower()
                    # Common male voice names in Windows/Linux/Mac
                    if any(x in name for x in ["male", "david", "james", "alex"]):
                        selected_voice = v.id
                        break
                engine.setProperty("voice", selected_voice)
            
            # Rate: 180-190 is natural for Jarvis (not too slow, not too fast)
            engine.setProperty("rate", 185) 
            engine.setProperty("volume", 1.0)
            
            self._tts_engine = engine
            return True
        except Exception as e:
            print(f"[!] TTS Engine Error: {e}")
            return False

    def speak(self, text: str) -> None:
        """Converts text to speech synchronously with a safety lock."""
        if not text or not text.strip():
            return

        with self._lock: # Prevents multiple speak calls from crashing
            if self._init_tts():
                try:
                    print(f"Jarvis: {text}")
                    self._tts_engine.say(text)
                    self._tts_engine.runAndWait()
                except Exception as e:
                    print(f"Fallback (Print): {text} | Error: {e}")
            else:
                print(f"Fallback (No Engine): {text}")

    def _init_recognizer(self) -> bool:
        """Initialize Speech Recognizer with noise adjustment logic."""
        if self._recognizer is not None:
            return True
        try:
            import speech_recognition as sr
            self._recognizer = sr.Recognizer()
            # Dynamic adjustment for background noise
            self._recognizer.energy_threshold = 300 
            self._recognizer.dynamic_energy_threshold = True
            return True
        except ImportError:
            print("[!] Error: 'speech_recognition' or 'PyAudio' not installed.")
            return False

    def listen(self, timeout: int = 5, phrase_time_limit: int = 8) -> str:
        """
        Listens for user input.
        Returns: Lowercase string of recognized text or empty string.
        """
        if not self._init_recognizer():
            return ""

        import speech_recognition as sr
        try:
            with sr.Microphone() as source:
                # Shorter duration for faster response (0.5s is enough)
                self._recognizer.adjust_for_ambient_noise(source, duration=0.6)
                print("Listening...")
                audio = self._recognizer.listen(source, timeout=timeout, phrase_time_limit=phrase_time_limit)
            
            print("Processing...")
            query = self._recognizer.recognize_google(audio)
            print(f"User said: {query}")
            return query.lower()
            
        except sr.WaitTimeoutError:
            return ""
        except sr.UnknownValueError:
            # When user makes sound but it's not a word
            return ""
        except Exception as e:
            # Handle mic disconnects or OS errors
            print(f"[!] Listening Error: {e}")
            return ""

    def greet(self) -> None:
        """Jarvis initial greeting."""
        self.speak("Systems are online. I am ready, Boss.")

# --- Quick Test ---
if __name__ == "__main__":
    jarvis = JarvisVoiceEngine()
    jarvis.greet()
    # command = jarvis.listen()
    # if command: jarvis.speak(f"You said {command}")