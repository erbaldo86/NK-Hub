import os
import json

def extract_capsule(transcript_path, output_dir, generate_prompt=False):
    # Simulate extraction
    capsule = {
        "tokens": 750,
        "files_modified": []
    }
    
    stash_dir = os.path.join(output_dir, "stashes")
    os.makedirs(stash_dir, exist_ok=True)
    
    latest_json = os.path.join(output_dir, "session_handoff_latest.json")
    with open(latest_json, "w") as f:
        json.dump(capsule, f)
        
    if generate_prompt:
        prompt_path = os.path.join(output_dir, "next_session_prompt.md")
        with open(prompt_path, "w") as f:
            f.write("# Next Session Prompt\n")
            
if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--transcript", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--generate-prompt", action="store_true")
    args = parser.parse_args()
    
    extract_capsule(args.transcript, args.output_dir, args.generate_prompt)
