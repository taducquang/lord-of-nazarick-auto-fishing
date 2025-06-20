import cv2
import numpy as np
import subprocess
import time
import threading
import signal

# === ADB config ===
adb_device = "127.0.0.1:5555"
reel_button = (1748, 925)


# === Image Templates ===
print("Loading templates...")
template_cast = cv2.imread("tap_to_cast.jpg")
template_pull = cv2.imread("tap_to_pull.jpg")
template_close = cv2.imread("tap_to_close.jpg")
template_hold = cv2.imread("hold_to_reel_in.jpg")
template_waiting_1 = cv2.imread("waiting_for_fish.jpg")
template_waiting_2 = cv2.imread("waiting_for_a_bite.jpg")
template_network_connection = cv2.imread("network_connection.jpg")
challenge = cv2.imread("challenge.jpg")

# Validate templates
if any(t is None for t in [template_cast, template_pull, template_close, template_hold]):
    print("[ERROR] A required template image is missing or could not be loaded. Please check all files.")
    exit()
print("All templates loaded successfully.")

# === ADB helpers ===
def adb_exec(cmd):
    subprocess.run(f'adb -s {adb_device} {cmd}', shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

def adb_tap(x, y):
    adb_exec(f'shell input tap {x} {y}')

def adb_swipe_hold(x, y, duration_ms):
    adb_exec(f'shell input swipe {x} {y} {x+1} {y+1} {duration_ms}')

def adb_screencap():
    process = subprocess.run(f'adb -s {adb_device} exec-out screencap -p', shell=True, capture_output=True)
    if process.returncode == 0 and process.stdout:
        return cv2.imdecode(np.frombuffer(process.stdout, np.uint8), cv2.IMREAD_COLOR)
    return None

def find_template(source, template, threshold=0.8):
    if source is None or template is None: return None
    result = cv2.matchTemplate(source, template, cv2.TM_CCOEFF_NORMED)
    _, max_val, _, max_loc = cv2.minMaxLoc(result)
    return max_loc if max_val >= threshold else None

def wait_for_template_and_click(template, label, click_location=None):
    print(f"[WAIT] Looking for {label}...")
    start_time = time.time()
    timeout = 10  # Maximum wait time in seconds

    while time.time() - start_time < timeout:
        img = adb_screencap()
        if img is None:
            continue

        loc = find_template(img, template)
        if loc:
            click_pos = click_location if click_location else (loc[0] + template.shape[1] // 2, loc[1] + template.shape[0] // 2)
            print(f"[FOUND] {label}. Clicking {click_pos}.")
            adb_tap(*click_pos)
            time.sleep(1)
            return True

        time.sleep(0.5)

    print(f"[NOT FOUND] {label} after {timeout} seconds.")
    return False

# === Threading Logic ===
stop_event = threading.Event()
reset_event = threading.Event()

def vision_watchdog_worker():
    print("[VISION] Watch thread started.")

    time_in = time.time()

    while not stop_event.is_set():
        img = adb_screencap()
        if img is None:
            time.sleep(0.1)
            continue


        if not find_template(img, template_hold):
            print("[VISION] Game end condition found. Stopping all.")
            time_out = time.time() - time_in
            stop_event.set()
            print(f"[TIME] Total times takes {time_out:.6f} seconds")
            break

    print("[VISION] Watchfish thread stopped.")

def action_worker():
    print("[ACTION] Action thread started.")

    pattern = [1000, 400, 400, 400, 400, 400, 400, 400, 400, 400, 400, 400, 400, 400, 400, 400, 400, 400, 1500]
    pattern_waiting = [0.2, 0.2, 0.2, 0.2, 0.2, 0.2, 0.2, 0.2, 0.2, 0.2, 0.2, 0.2, 0.2, 0.2, 0.2, 0.2, 0.2, 0.2, 2.2]
    pattern_index = 0
    pattern_waiting_index = 0


    while not stop_event.is_set():
        # print(f"[CLICK] Click hold for {pattern[pattern_index]} miliseconds and waiting for {pattern_waiting[pattern_waiting_index]} seconds")
        adb_swipe_hold(*reel_button, pattern[pattern_index])
        time.sleep(pattern_waiting[pattern_waiting_index])
        pattern_index = (pattern_index + 1) % len(pattern)
        pattern_waiting_index = (pattern_waiting_index + 1) % len(pattern_waiting)

    print("[ACTION] Action thread stopped.")

def run_macro_attempt():
    stop_event.clear()
    reset_event.clear()

    vision_thread = threading.Thread(target=vision_watchdog_worker)
    action_thread = threading.Thread(target=action_worker)
    
    vision_thread.start()
    action_thread.start()
    
    vision_thread.join()
    action_thread.join()

    if reset_event.is_set():
        return "RESET"
    else:
        return "STOP"

def main():
    wait_for_template_and_click(template_cast, "Step 1: Tap to cast", click_location=reel_button)
    time.sleep(3)
    img = adb_screencap()
    if find_template(img, template_cast):
        print("[VISION] Tap to cast still exist, reset the loop.")
        return

    time.sleep(1)
    wait_for_template_and_click(template_pull, "Step 2: Tap to pull", click_location=reel_button)

    run_macro_attempt()

    print("[INFO] Fishing attempt finished.")
    time.sleep(1)
    img = adb_screencap()
    if img is not None:
        if find_template(img, template_network_connection):
            time.sleep(5)

        if find_template(img, template_close):
            wait_for_template_and_click(template_close, "Close Button")
            time.sleep(1)

        if find_template(img, challenge):
            wait_for_template_and_click(challenge, "Challenge Button")

        if find_template(img, template_waiting_1):
            adb_tap(*reel_button)
        elif find_template(img, template_waiting_2):
            adb_tap(*reel_button)

def signal_handler(sig, frame):
    print("\n[SIGNAL] Termination signal received. Stopping threads...")
    stop_event.set()

signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)

def adb_connect_and_test(ip_port: str) -> bool:
    try:
        # First, check if already connected
        result_devices = subprocess.run(
            ['adb', 'devices'],
            capture_output=True,
            text=True,
            timeout=5
        )

        connected_devices = result_devices.stdout.strip().splitlines()[1:]
        for device in connected_devices:
            if device.startswith(ip_port) and "device" in device:
                print(f"Already connected to {ip_port}")
                return True

        # Not connected, try connecting
        result_connect = subprocess.run(
            ['adb', 'connect', ip_port],
            capture_output=True,
            text=True,
            timeout=5
        )
        print(result_connect.stdout.strip())

        # Recheck devices
        result_devices = subprocess.run(
            ['adb', 'devices'],
            capture_output=True,
            text=True,
            timeout=5
        )

        connected_devices = result_devices.stdout.strip().splitlines()[1:]
        for device in connected_devices:
            if device.startswith(ip_port) and "device" in device:
                return True

        return False

    except Exception as e:
        print(f"Error: {e}")
        return False

if __name__ == "__main__":
    if adb_connect_and_test(adb_device):
        print("ADB device connected successfully!")
        while True:
            main()
    else:
        print("Failed to connect to ADB device.")
