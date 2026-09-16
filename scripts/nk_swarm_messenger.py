import os
import sys
import argparse
import hashlib
import tempfile

def process_payload(payload):
    if len(payload) <= 1800:
        return payload
        
    sha256 = hashlib.sha256(payload.encode('utf-8')).hexdigest()
    temp_dir = os.path.join(tempfile.gettempdir(), 'nk_diagnostics')
    os.makedirs(temp_dir, exist_ok=True)
    dump_file = os.path.join(temp_dir, f'swarm_spillover_{sha256[:8]}.txt')
    
    with open(dump_file, 'w', encoding='utf-8') as f:
        f.write(payload)
        
    head = payload[:400]
    tail = payload[-800:]
    
    return f"{head}\n\n[...TRUNCATED, FULL PAYLOAD SAVED TO {dump_file}...]\n\n{tail}"

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--sender')
    parser.add_argument('--recipient')
    parser.add_argument('--payload')
    parser.add_argument('--payload-file')
    args = parser.parse_args()
    
    payload = ""
    if args.payload:
        payload = args.payload
    elif args.payload_file:
        with open(args.payload_file, 'r', encoding='utf-8') as f:
            payload = f.read()
            
    result = process_payload(payload)
    print(result)

if __name__ == '__main__':
    main()
