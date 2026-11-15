import json
from pathlib import Path

txt_path = Path(r"C:/Users/Uswer/.gemini/antigravity/brain/3ed40a1e-14b3-4e58-9622-6fb4927de8b2/.user_uploaded/media_1794576498341_344a603d.txt")
out_path = Path(__file__).resolve().parent.parent / "services" / "tags_data.py"

with open(txt_path, "r", encoding="utf-8") as f:
    tags = [line.strip().lower() for line in f if line.strip()]

# Remove duplicates while preserving order
seen = set()
unique_tags = []
for t in tags:
    if t not in seen:
        seen.add(t)
        unique_tags.append(t)

print(f"Loaded {len(tags)} lines, {len(unique_tags)} unique tags.")

code_lines = [
    '"""',
    "Auto-generated whitelist of Treblo-supported style and genre tags.",
    f"Total unique tags: {len(unique_tags)}",
    '"""',
    "",
    "TAGS_LIST = [",
]
for tag in unique_tags:
    # Escape quotes if any
    escaped = tag.replace('"', '\\"')
    code_lines.append(f'    "{escaped}",')
code_lines.append("]")
code_lines.append("")
code_lines.append("ALLOWED_TAGS = frozenset(TAGS_LIST)")
code_lines.append("")

with open(out_path, "w", encoding="utf-8") as f:
    f.write("\n".join(code_lines))

print(f"Written successfully to {out_path}")
