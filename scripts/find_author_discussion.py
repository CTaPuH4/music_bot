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
        
        # Look for user messages
        if step_type == "USER_INPUT":
            print(f"\n--- STEP {i} USER ---")
            print(content[:500])
        elif any(w in content.lower() for w in ["перебор", "список артист", "проверк", "в тегах"]):
            # Also look for relevant assistant content
            if "перебор" in content.lower() or "скриптонит" in content.lower() or "баста" in content.lower():
                print(f"\n--- STEP {i} CONTENT ({step_type}) ---")
                print(content[:500])
