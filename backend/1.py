import pyautogui
import time
import random
from datetime import datetime
import keyboard

pyautogui.FAILSAFE = True

start_time = time.time()
cycle_count = 0

def get_runtime():
    elapsed = int(time.time() - start_time)
    minutes, seconds = divmod(elapsed, 60)
    return f"{minutes}m {seconds}s"

def log_action(action):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] ({get_runtime()}) {action}")

print("Starting activity loop in 3 seconds... (Press 'q' to quit)")
time.sleep(3)

try:
    while True:
        if keyboard.is_pressed('q'):
            log_action("Detected 'q' key press. Exiting script.")
            break

        cycle_count += 1
        log_action(f"Cycle {cycle_count} started")

        pyautogui.press('shift')
        log_action("Pressed 'Shift' key")

        sleep_time = random.uniform(30, 60)
        log_action(f"Sleeping for {round(sleep_time, 1)} seconds...\n")
        time.sleep(sleep_time)

except Exception as e:
    log_action(f"Error occurred: {e}")


# from pymongo import MongoClient

# try:
#     client = MongoClient("mongodb://192.168.10.50:27017/")
#     print("MongoDB connection successful!")
#     print(client.server_info())
# except Exception as e:
#     print("MongoDB connection failed:", e)





 