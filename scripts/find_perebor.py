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
        
        content = str(entry.get("content", ""))
        thinking = str(entry.get("thinking", ""))
        text = content + " " + thinking
        
        # Look for instances of "перебор" or "автор" or "артист" when testing Treblo API
        if "перебор" in text.lower() or "brute" in text.lower() or ("422" in text and "artist" in text.lower()):
            print(f"Match at step {i}: type={entry.get('type')}")
            print(content[:600])
            print("="*40)
