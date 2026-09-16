import os
import json
import argparse
import subprocess
import time

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--transcript', required=True)
    parser.add_argument('--output-dir', required=True)
    parser.add_argument('--generate-prompt', action='store_true')
    args = parser.parse_args()
    
    capsule = ""
    steps = 0
    total_chars = 0
    if os.path.exists(args.transcript):
        with open(args.transcript, 'r', encoding='utf-8') as f:
            lines = f.readlines()
            steps = len(lines)
            capsule = "".join(lines[-10:])
            total_chars = sum(len(line) for line in lines)
            
    tokens = max(1, total_chars // 4)
    capsule = capsule[:3000] # roughly < 800 tokens
    
    dirty_files = False
    stash_patch = None
    try:
        status_out = subprocess.check_output(['git', 'status', '--porcelain'], universal_newlines=True)
        if status_out.strip():
            dirty_files = True
            stash_dir = os.path.join(args.output_dir, 'stashes')
            os.makedirs(stash_dir, exist_ok=True)
            ts = int(time.time())
            stash_patch = os.path.join(stash_dir, f'stash_{ts}.patch')
            subprocess.call(['git', 'diff'], stdout=open(stash_patch, 'w'))
    except Exception:
        pass
        
    metadata = {
        "steps": steps,
        "tokens": tokens,
        "dirty_files": dirty_files,
        "stash_patch": stash_patch,
        "baseline_tests": 74,
        "milestone": "Auto-Saved Milestone"
    }
    
    os.makedirs(args.output_dir, exist_ok=True)
    latest_file = os.path.join(args.output_dir, 'session_handoff_latest.json')
    with open(latest_file, 'w', encoding='utf-8') as f:
        json.dump(metadata, f, indent=2)
        
    if args.generate_prompt:
        prompt_file = os.path.join(args.output_dir, 'next_session_prompt.md')
        with open(prompt_file, 'w', encoding='utf-8') as f:
            f.write("# Turnkey Hand-off Prompt\n\n")
            f.write(f"Capsule info: {capsule}\n")

if __name__ == '__main__':
    main()
