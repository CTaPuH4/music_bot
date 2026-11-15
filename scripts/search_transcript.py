import json
from pathlib import Path

transcript_path = Path(r"C:/Users/Uswer/.gemini/antigravity/brain/3ed40a1e-14b3-4e58-9622-6fb4927de8b2/.system_generated/logs/transcript.jsonl")

print(f"Reading {transcript_path}...")
matches = []
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
        thinking = str(entry.get("thinking", ""))
        combined = (content + " " + thinking).lower()

        keywords = ["422", "перебор", "treblo", "sonauto", "melodia", "артист", "автор", "tags"]
        hit = [k for k in keywords if k in combined]
        if hit:
            matches.append((i, step_type, entry.get("source"), hit, content[:300]))

print(f"Total matching lines: {len(matches)}")
for idx, st, src, hits, snippet in matches:
    if st == "USER_INPUT" or "перебор" in hits or "422" in hits:
        print(f"[{idx}] {st} ({src}) - Hits: {hits}")
        print(f"   Snippet: {snippet.replace(chr(10), ' ')}")
