import json
from pathlib import Path

transcript_path = Path(r"C:/Users/Uswer/.gemini/antigravity/brain/3ed40a1e-14b3-4e58-9622-6fb4927de8b2/.system_generated/logs/transcript_full.jsonl")

with open(transcript_path, "r", encoding="utf-8") as f:
    for i, line in enumerate(f):
        if i == 1890:
            entry = json.loads(line)
            print(entry.get("content"))
