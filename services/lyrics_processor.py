import re
from typing import Optional


def _process_lyrics_line(l_str: str) -> str:
    l_str = l_str.strip()
    if not l_str:
        return ""

    # Pre-Chorus
    if re.match(r"^\[?\s*(?:предприпев|пре-припев|pre-chorus)\s*:?\s*\]?$", l_str, re.IGNORECASE):
        return "[Pre-Chorus]"

    # Verse (Куплет)
    m_verse = re.match(
        r"^\[?\s*(?:(\d+)[\s-]*[йеяа]?\s*)?(?:куплет|verse)(?:[\s-]*(\d+))?(?:\s*:\s*([^\]]+))?\s*:?\s*\]?$",
        l_str,
        re.IGNORECASE,
    )
    if m_verse:
        num = m_verse.group(1) or m_verse.group(2) or ""
        extra = (m_verse.group(3) or "").strip()
        tag = f"[Verse {num}]" if num else "[Verse]"
        if extra:
            tag = f"{tag[:-1]}: {extra}]"
        return tag

    # Chorus / Hook (Припев, Хук)
    m_chorus = re.match(
        r"^\[?\s*(?:(\d+)[\s-]*[йеяа]?\s*)?(?:припев|chorus|hook|хук)(?:[\s-]*(\d+))?(?:\s*[:(]\s*([^\]]+))?\s*:?\s*\]?$",
        l_str,
        re.IGNORECASE,
    )
    if m_chorus:
        extra = (m_chorus.group(3) or "").strip(" :)")
        if extra:
            return f"[Chorus ({extra})]"
        return "[Chorus]"

    # Bridge (Бридж)
    if re.match(r"^\[?\s*(?:бридж|bridge)\s*:?\s*\]?$", l_str, re.IGNORECASE):
        return "[Bridge]"

    # Intro (Интро, Вступление)
    if re.match(r"^\[?\s*(?:интро|вступление|intro)\s*:?\s*\]?$", l_str, re.IGNORECASE):
        return "[Intro]"

    # Outro (Аутро, Концовка, Финал)
    if re.match(r"^\[?\s*(?:аутро|концовка|финал|outro)\s*:?\s*\]?$", l_str, re.IGNORECASE):
        return "[Outro]"

    # Drop (Дроп)
    if re.match(r"^\[?\s*(?:дроп|drop)\s*:?\s*\]?$", l_str, re.IGNORECASE):
        return "[Drop]"

    # Solo (Соло, Гитарное соло)
    if re.match(r"^\[?\s*(?:гитарное\s+)?(?:соло|solo)\s*:?\s*\]?$", l_str, re.IGNORECASE):
        return "[Solo]"

    return l_str


def normalize_and_structure_lyrics(text: str) -> str:
    """
    Normalizes lyrics for generative audio models (Treblo / Suno / Melodia):
    1. Normalizes line endings and removes excessive blank lines.
    2. Converts Russian structural labels and loose headers (e.g. '1-й куплет:', '[Припев]')
       into canonical Suno tags ([Verse 1], [Chorus], [Bridge], [Outro], [Intro], [Pre-Chorus], [Drop], [Solo]).
    3. If lyrics contain no structural tags at all, automatically tags stanzas with
       [Verse 1], [Chorus], [Verse 2], etc. so the AI understands song boundaries and
       never confuses lyrical text with musical style directions.
    """
    if not text or not text.strip():
        return ""

    text = text.replace("\r\n", "\n").replace("\r", "\n").strip()
    raw_lines = text.splitlines()

    processed_lines = []
    has_any_tag = False
    for line in raw_lines:
        conv = _process_lyrics_line(line)
        if conv.startswith("[") and conv.endswith("]"):
            has_any_tag = True
        processed_lines.append(conv)

    result = "\n".join(processed_lines)

    # If no tags at all were detected or created, tag raw stanzas
    if not has_any_tag:
        stanzas = [s.strip() for s in re.split(r"\n\s*\n", result) if s.strip()]
        if len(stanzas) == 1:
            result = f"[Verse]\n{stanzas[0]}"
        elif len(stanzas) == 2:
            result = f"[Verse]\n{stanzas[0]}\n\n[Chorus]\n{stanzas[1]}"
        elif len(stanzas) == 3:
            result = f"[Verse 1]\n{stanzas[0]}\n\n[Chorus]\n{stanzas[1]}\n\n[Verse 2]\n{stanzas[2]}"
        elif len(stanzas) >= 4:
            tagged = []
            for i, st in enumerate(stanzas):
                if i == 0:
                    tagged.append(f"[Verse 1]\n{st}")
                elif i == 1:
                    tagged.append(f"[Chorus]\n{st}")
                elif i == 2:
                    tagged.append(f"[Verse 2]\n{st}")
                elif i == 3:
                    tagged.append(f"[Chorus]\n{st}")
                elif i == len(stanzas) - 1:
                    tagged.append(f"[Outro]\n{st}")
                else:
                    tagged.append(f"[Verse {i}]\n{st}")
            result = "\n\n".join(tagged)

    # Cleanup excessive newlines (max 2 consecutive newlines)
    result = re.sub(r"\n{3,}", "\n\n", result).strip()
    return result


def build_treblo_style_prompt(
    genre_tags_str: str,
    artist_clause: str,
    prompt: str,
    is_custom_lyrics: bool = False,
) -> str:
    """
    Builds the style prompt sent to Treblo / Suno API:
    - If is_custom_lyrics is True: Strictly isolates musical style and artist reference.
      Never appends lyrics or prompt text. Appends strong rhythm and tempo anchor to
      prevent neural network from changing genre/tempo based on words in the lyrics.
    - If is_custom_lyrics is False: Combines genre, artist, and user's idea prompt.
    """
    if is_custom_lyrics:
        style_parts = []
        if genre_tags_str:
            style_parts.append(f"Жанры: {genre_tags_str}")
        if artist_clause:
            style_parts.append(artist_clause.strip(" ,."))
        style_parts.append("строгий единый бит, сохранять стиль и темп на протяжении всего трека")
        return ". ".join(style_parts)

    return f"Жанры: {genre_tags_str}. {artist_clause}{prompt}".strip()
