import json
from pathlib import Path

transcript_path = Path(r"C:/Users/Uswer/.gemini/antigravity/brain/3ed40a1e-14b3-4e58-9622-6fb4927de8b2/.system_generated/logs/transcript.jsonl")

with open(transcript_path, "r", encoding="utf-8") as f:
    for i, line in enumerate(f):
        if not line.strip():
            continue
        try:
            entry = json.loads(line)
        except Exception:
            continue
        
        step_type = entry.get("type", "")
        content = str(entry.get("content", ""))
        
        if step_type == "USER_INPUT":
            # Print user requests
            clean = content.replace("<USER_REQUEST>", "").replace("</USER_REQUEST>", "").strip()
            # Remove metadata
            if "<ADDITIONAL_METADATA>" in clean:
                clean = clean.split("<ADDITIONAL_METADATA>")[0].strip()
            print(f"Step {i}: {clean[:150]}")
