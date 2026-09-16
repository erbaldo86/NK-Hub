import os
import json

def send_message(sender, recipient, payload, payload_file=None):
    if payload_file and os.path.exists(payload_file):
        with open(payload_file, "r") as f:
            payload = f.read()
            
    if len(payload) > 1800:
        head = payload[:400]
        tail = payload[-800:]
        payload = f"{head}\n...\n{tail}"
        
        # Spillover
        temp_dir = os.path.expandvars("%TEMP%\\nk_diagnostics")
        os.makedirs(temp_dir, exist_ok=True)
        spillover_path = os.path.join(temp_dir, "spillover.txt")
        with open(spillover_path, "w") as f:
            f.write(payload)
            
    return payload

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--sender", required=True)
    parser.add_argument("--recipient", required=True)
    parser.add_argument("--payload", required=True)
    parser.add_argument("--payload-file")
    args = parser.parse_args()
    
    send_message(args.sender, args.recipient, args.payload, args.payload_file)
