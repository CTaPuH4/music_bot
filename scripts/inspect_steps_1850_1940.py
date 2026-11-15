import json
from pathlib import Path

transcript_path = Path(r"C:/Users/Uswer/.gemini/antigravity/brain/3ed40a1e-14b3-4e58-9622-6fb4927de8b2/.system_generated/logs/transcript.jsonl")

with open(transcript_path, "r", encoding="utf-8") as f:
    for i, line in enumerate(f):
        if 1850 <= i <= 1940:
            entry = json.loads(line)
            st = entry.get("type")
            content = entry.get("content", "")
            thinking = entry.get("thinking", "")
            if "перебор" in (content + " " + thinking).lower() or "422" in (content + " " + thinking).lower() or "tag" in (content + " " + thinking).lower():
                print(f"=== STEP {i} ({st}) ===")
                if content:
                    print("CONTENT:", content[:500])
                if thinking:
                    print("THINKING:", thinking[:500])
