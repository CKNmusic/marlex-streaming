import requests
import time
import sys

BASE_URL = "http://localhost:8001/api/v1"

def simulate_device(qr_token, device_name):
    print(f"--- Simulating Device: {device_name} ---")
    
    # 1. Authenticate
    print(f"[*] Authenticating with token: {qr_token}...")
    try:
        response = requests.post(f"{BASE_URL}/devices/auth", json={
            "qr_token": qr_token,
            "stream_url": "rtmp://192.168.1.100:8554/main/av" # Initial guess, but API can provision another protocol
        })
        
        if response.status_code != 200:
            print(f"[!] Auth failed: {response.text}")
            return
            
        data = response.json()
        session_token = data["device_session_token"]
        device_id = data["device_id"]
        ingest_url = data["ingest_url"]
        protocol = data["protocol"]
        stream_key = data["stream_key"]
        
        print(f"[+] Auth Success!")
        print(f"    - Device ID: {device_id}")
        print(f"    - Ingest URL ({protocol}): {ingest_url}")
        print(f"    - Stream Key: {stream_key}")
        
        # 2. Heartbeat Loop
        print(f"[*] Starting heartbeats (every 10s for testing)...")
        count = 0
        while count < 6: # Run for 1 minute
            hb_response = requests.post(
                f"{BASE_URL}/devices/heartbeat", 
                headers={"Authorization": f"Bearer {session_token}"},
                json={
                    "device_id": device_id,
                    "stream_url": f"{ingest_url}/{stream_key}",
                    "status": "ready"
                }
            )
            if hb_response.status_code == 200:
                print(f"    [HB {count+1}] Heartbeat sent. Status: OK")
            else:
                print(f"    [HB {count+1}] Failed: {hb_response.text}")
            
            count += 1
            time.sleep(10)
            
        print("[*] Stopping heartbeats to test timeout...")
        print("[*] Wait 65s for backend to mark as disconnected...")
        time.sleep(65)
        
    except Exception as e:
        print(f"[!] Error: {e}")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python device_simulator.py <qr_token>")
        sys.exit(1)
        
    simulate_device(sys.argv[1], "Simulator_01")
