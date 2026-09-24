import os
import json
import argparse
import sys
import tempfile

def calculate_state(steps):
    if steps < 60:
        return "GREEN"
    elif steps < 85:
        return "CAUTION"
    elif steps < 100:
        return "CRITICAL"
    return "RED"

def run_sentinel(transcript_path):
    steps = 0
    total_chars = 0
    
    if os.path.exists(transcript_path):
        with open(transcript_path, 'r', encoding='utf-8') as f:
            for line in f:
                steps += 1
                total_chars += len(line)
    
    tokens = max(1, total_chars // 4)
    state = calculate_state(steps)
    
    result = {
        "steps": steps,
        "tokens": tokens,
        "state": state
    }
    
    temp_dir = os.path.join(tempfile.gettempdir(), 'nk_diagnostics')
    os.makedirs(temp_dir, exist_ok=True)
    state_file = os.path.join(temp_dir, 'sentinel_state.json')
    
    with open(state_file, 'w', encoding='utf-8') as f:
        json.dump(result, f)
        
    return result

monitor_transcript = run_sentinel

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--transcript', required=True)
    parser.add_argument('--check', action='store_true')
    parser.add_argument('--json', action='store_true')
    args = parser.parse_args()
    
    result = run_sentinel(args.transcript)
    
    if args.json:
        print(json.dumps(result))
        
    if args.check and result['state'] == 'RED':
        sys.exit(1)

if __name__ == '__main__':
    main()
