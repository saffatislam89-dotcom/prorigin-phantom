import speech_recognition as sr
import pyttsx3
import pywhatkit
import os
import datetime
from groq import Groq

# --- Groq AI Brain Setup ---
client = Groq(api_key="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")

engine = pyttsx3.init()
def speak(text):
    print("Jarvis: " + text)
    engine.say(text)
    engine.runAndWait()

def get_ai_response(user_text):
    try:
        # Notun model 'llama-3.3-70b-versatile' use kora hocche
        chat_completion = client.chat.completions.create(
            messages=[
                {"role": "system", "content": "You are Jarvis from Iron Man. Be smart, helpful and very brief."},
                {"role": "user", "content": user_text}
            ],
            model="llama-3.3-70b-versatile", 
        )
        return chat_completion.choices[0].message.content
    except Exception as e:
        print(f"Error: {e}")
        return "Sir, I am having trouble with my neural link."

def take_command():
    listener = sr.Recognizer()
    with sr.Microphone() as source:
        print("Listening...")
        listener.adjust_for_ambient_noise(source, duration=0.5)
        try:
            voice = listener.listen(source, timeout=5, phrase_time_limit=5)
            query = listener.recognize_google(voice)
            return query.lower()
        except:
            return "none"

if __name__ == "__main__":
    speak("Jarvis is online and systems are green, Sir.")
    while True:
        query = take_command()
        if query == "none": continue
        print(f"User: {query}")

        if 'stop' in query or 'exit' in query:
            speak("Goodbye Sir!")
            break
        elif 'open notepad' in query:
            speak("Opening Notepad.")
            os.system("notepad.exe")
        elif 'play' in query:
            song = query.replace('play', '')
            speak("Playing " + song)
            pywhatkit.playonyt(song)
        elif 'time' in query:
            time = datetime.datetime.now().strftime('%I:%M %p')
            speak(f"The time is {time}")
        else:
            answer = get_ai_response(query)
            speak(answer)