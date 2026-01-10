"""
main.py - The Brain of Jarvis
"""
import time
import sys
import webbrowser
import os
import re
import ctypes
import traceback
import power as pc 
import wifi_controller as wifi
import ss_control as screen
import brightness_control as bc
import bluetooth_controller as bt

try:
    from jarvis_voice_engine import JarvisVoiceEngine
    import app_launcher
except ImportError as e:
    print(f"[!] Critical Error: {e}")
    sys.exit(1)

def is_admin():
    """চেক করবে প্রোগ্রামটি এডমিন মোডে চলছে কি না"""
    try:
        return ctypes.windll.shell32.IsUserAnAdmin() != 0
    except:
        return False

def start_jarvis():
    try:
        voice = JarvisVoiceEngine()
    except Exception as e:
        print(f"[!] Engine Error: {e}")
        return

    voice.greet()
    
    while True:
        try:
            raw_command = voice.listen()
            if not raw_command or len(raw_command.strip()) < 2:
                continue
                
            command = raw_command.lower().strip()
            normalized_command = command.replace("-", "")
            print(f">>> Recognized: {command}")
            
            # --- WiFi Controls ---
            if "turn on wifi" in normalized_command or "enable wifi" in normalized_command:
                if wifi.enable_wifi():
                    voice.speak("WiFi enabled successfully, Boss.")
                else:
                    voice.speak("I need administrator privileges to enable WiFi.")

            elif "turn off wifi" in normalized_command or "disable wifi" in normalized_command:
                if wifi.disable_wifi():
                    voice.speak("WiFi disabled successfully, Boss.")
                else:
                    voice.speak("I need administrator privileges to disable WiFi.")

            elif "wifi status" in normalized_command:
                status = wifi.get_wifi_status()
                if status:
                    voice.speak(f"WiFi is {status}, Boss.")
                else:
                    voice.speak("Unable to check WiFi status.")

            # --- Bluetooth Controls (Fixed with Admin Check) ---
            elif "turn on bluetooth" in normalized_command or "enable bluetooth" in normalized_command:
                if not is_admin():
                    voice.speak("Boss, I need Administrator privileges to change bluetooth settings. Please restart VS Code as an Admin.")
                    continue
                
                if bt.enable_bluetooth():
                    voice.speak("Bluetooth is now on, Boss")
                else:
                    voice.speak("I encountered an error while turning on bluetooth.")

            elif "turn off bluetooth" in normalized_command or "disable bluetooth" in normalized_command:
                if not is_admin():
                    voice.speak("Boss, I need Administrator privileges to change bluetooth settings. Please restart VS Code as an Admin.")
                    continue

                if bt.disable_bluetooth():
                    voice.speak("Bluetooth has been disabled, Sir")
                else:
                    voice.speak("I encountered an error while turning off bluetooth.")

            elif "is bluetooth on" in normalized_command or "check bluetooth status" in normalized_command:
                status = bt.get_bluetooth_status()
                if status is True:
                    voice.speak("Bluetooth is currently enabled")
                elif status is False:
                    voice.speak("Bluetooth is turned off")
                else:
                    voice.speak("I am unable to access bluetooth settings right now.")

            # --- Screenshot Controls ---
            elif "take a screenshot" in command or "capture the screen" in command:
                path = screen.take_ss()
                if path:
                    voice.speak("Screenshot captured and saved, Boss.")
                else:
                    voice.speak("Failed to capture the screenshot.")

            elif "copy screenshot" in command:
                if screen.copy_ss_to_clipboard():
                    voice.speak("Copied to clipboard, Sir.")
                else:
                    voice.speak("Failed to copy screenshot.")

            # --- Brightness Controls ---
            m = re.search(r'set brightness to\s+(\d{1,3})', command)
            if m:
                value = max(10, min(100, int(m.group(1))))
                bc.set_brightness(value)
                voice.speak(f"Setting brightness to {value} percent.")

            elif 'increase brightness' in command:
                cur = int(float(bc.get_brightness() or 50))
                bc.set_brightness(min(100, cur + 20))
                voice.speak("Increasing brightness, Boss.")

            elif 'decrease brightness' in command:
                cur = int(float(bc.get_brightness() or 50))
                bc.set_brightness(max(10, cur - 20))
                voice.speak("Decreasing brightness, Boss.")

            # --- Web & Apps ---
            if "youtube music" in command:
                voice.speak("Opening YouTube Music.")
                webbrowser.open("https://music.youtube.com")
            
            elif "open youtube" in command:
                webbrowser.open("https://www.youtube.com")

            elif "open google" in command:
                webbrowser.open("https://www.google.com")

            elif "open" in command:
                app_name = command.replace("open", "").strip()
                if app_name:
                    app_launcher.open_app(app_name)

            elif "close" in command or "terminate" in command:
                app_name = command.replace("close", "").replace("terminate", "").strip()
                if app_name:
                    app_launcher.close_app(app_name)

            # --- System Controls ---
            if "shutdown" in command:
                voice.speak("Shutting down, Goodbye!")
                pc.shutdown_system()
            elif "restart" in command:
                pc.restart_system()
            elif "goodbye" in command or "exit" in command:
                voice.speak("Goodbye Boss.")
                break

        except Exception as e:
            print(f"[!] Error: {e}")
            continue

        time.sleep(0.1)

if __name__ == "__main__":
    start_jarvis()