"""
Service for cleaning, transliterating, and validating user-entered style/genre tags
against the official Treblo Melodia v3 API whitelist.
"""

import re
from typing import Dict, List, Optional, Tuple

from services.tags_data import ALLOWED_TAGS

# Precomputed map of stripped alphanumeric strings to canonical tags in ALLOWED_TAGS
# e.g. "lofi" -> "lo-fi", "hiphop" -> "hip hop", "deep_house" -> "deep house"
NORMALIZED_TAGS: Dict[str, str] = {}
for _tag in ALLOWED_TAGS:
    _key = re.sub(r"[^a-z0-9]", "", _tag.lower())
    if _key and _key not in NORMALIZED_TAGS:
        NORMALIZED_TAGS[_key] = _tag


# Cyrillic to Latin transliteration tables
CYRILLIC_TO_LATIN_KH: Dict[str, str] = {
    "а": "a", "б": "b", "в": "v", "г": "g", "д": "d",
    "е": "e", "ё": "yo", "ж": "zh", "з": "z", "и": "i",
    "й": "y", "к": "k", "л": "l", "м": "m", "н": "n",
    "о": "o", "п": "p", "р": "r", "с": "s", "т": "t",
    "у": "u", "ф": "f", "х": "kh", "ц": "ts", "ч": "ch",
    "ш": "sh", "щ": "shch", "ъ": "", "ы": "y", "ь": "",
    "э": "e", "ю": "yu", "я": "ya",
}

CYRILLIC_TO_LATIN_H: Dict[str, str] = {
    **CYRILLIC_TO_LATIN_KH,
    "х": "h",
}

# Extensive Russian synonyms and slang mapping to canonical Treblo tags
RUSSIAN_GENRE_SYNONYMS: Dict[str, str] = {
    # Core genres
    "рок": "rock",
    "поп": "pop",
    "попса": "pop",
    "рэп": "rap",
    "реп": "rap",
    "хип хоп": "hip hop",
    "хипхоп": "hip hop",
    "хип-хоп": "hip hop",
    "хаус": "house",
    "дип хаус": "deep house",
    "дип-хаус": "deep house",
    "дипхаус": "deep house",
    "техно": "techno",
    "мелодик техно": "melodic techno",
    "дип техно": "deep techno",
    "минимал техно": "minimal techno",
    "транс": "trance",
    "психоделик транс": "psytrance",
    "пситранс": "psytrance",
    "пси-транс": "psytrance",
    "электроника": "electronic",
    "электронная": "electronic",
    "электронная музыка": "electronic music",
    "эдйем": "edm",
    "едйем": "edm",
    "метал": "metal",
    "металл": "metal",
    "хэви метал": "heavy metal",
    "хэви металл": "heavy metal",
    "хеви метал": "heavy metal",
    "хеви металл": "heavy metal",
    "хэви-метал": "heavy metal",
    "хэви-металл": "heavy metal",
    "хеви-метал": "heavy metal",
    "хеви-металл": "heavy metal",
    "хэвиметал": "heavy metal",
    "хэвиметалл": "heavy metal",
    "хевиметал": "heavy metal",
    "хевиметалл": "heavy metal",
    "ньювейв": "new wave",
    "ньювэйв": "new wave",
    "нью вейв": "new wave",
    "нью вэйв": "new wave",
    "нью-вейв": "new wave",
    "нью-вэйв": "new wave",
    "новая волна": "new wave",
    "пауэр метал": "power metal",
    "пауэр-метал": "power metal",
    "дэт метал": "death metal",
    "дет метал": "death metal",
    "дэт-метал": "death metal",
    "блэк метал": "black metal",
    "блэк-метал": "black metal",
    "дум метал": "doom metal",
    "дум-метал": "doom metal",
    "трэш метал": "thrash metal",
    "треш метал": "thrash metal",
    "трэш-метал": "thrash metal",
    "ню метал": "nu-metal",
    "ню-метал": "nu-metal",
    "симфоник метал": "symphonic metal",
    "симфо-метал": "symphonic metal",
    "фолк метал": "folk metal",
    "прогрессив метал": "progressive metal",
    "прог метал": "prog metal",
    "панк": "punk",
    "панк рок": "punk rock",
    "панк-рок": "punk rock",
    "поп панк": "pop punk",
    "поп-панк": "pop punk",
    "пост панк": "post-punk",
    "пост-панк": "post-punk",
    "постпанк": "post-punk",
    "фонк": "phonk",
    "дрифт фонк": "drift phonk",
    "дрилл": "drill",
    "трэп": "trap",
    "трап": "trap",
    "лофай": "lo-fi",
    "ло-фай": "lo-fi",
    "лоуфай": "lo-fi",
    "лоу-фай": "lo-fi",
    "синтвейв": "synthwave",
    "синтпоп": "synthpop",
    "синт-поп": "synthpop",
    "дарквейв": "darkwave",
    "дарксинт": "darksynth",
    "блюз": "blues",
    "джаз": "jazz",
    "соул": "soul",
    "нео соул": "neo-soul",
    "нео-соул": "neo-soul",
    "фанк": "funk",
    "диско": "disco",
    "итало диско": "italo-disco",
    "итало-диско": "italo-disco",
    "регги": "reggae",
    "реггей": "reggae",
    "даб": "dub",
    "дабстеп": "dubstep",
    "инди": "indie",
    "инди рок": "indie rock",
    "инди-рок": "indie rock",
    "инди поп": "indie pop",
    "инди-поп": "indie pop",
    "классика": "classical",
    "классическая музыка": "classical",
    "неоклассика": "neoclassicism",
    "эмбиент": "ambient",
    "дарк эмбиент": "dark ambient",
    "днб": "dnb",
    "драм": "drum and bass",
    "драм энд бейс": "drum and bass",
    "драм энд бэйс": "drum and bass",
    "драм-н-бейс": "drum and bass",
    "драм-н-бэйс": "drum and bass",
    "драмнбейс": "drum and bass",
    "фолк": "folk",
    "кантри": "country",
    "шансон": "chanson",
    "русский шансон": "russian chanson",
    "русский рок": "russian rock",
    "русский дрилл": "русский дрилл (russian drill)",
    "акустика": "acoustic",
    "акустическая гитара": "acoustic guitar",
    "гитара": "guitar",
    "электрогитара": "electric guitar",
    "пианино": "piano",
    "фортепиано": "grand piano",
    "вокал": "vocal",
    "женский вокал": "female vocal",
    "мужской вокал": "male vocal",
    "мужской": "male vocal",
    "женский": "female vocal",
    "бас": "bass",
    "саундтрек": "soundtrack",
    "чилл": "chillout",
    "чиллаут": "chillout",
    "чиптюн": "chiptune",
    "хардкор": "hardcore",
    "гранж": "grunge",
    "грандж": "grunge",
    "шугейз": "shoegaze",
    "шугейзинг": "shoegaze",
    "ска": "ska",
    "к-поп": "k-pop",
    "кпоп": "k-pop",
    "джей-поп": "j-pop",
    "джейпоп": "j-pop",
    "рнб": "r&b",
    "эрэнби": "r&b",
    "арэнби": "r&b",
    "хард рок": "hard rock",
    "хард-рок": "hard rock",
    "дрим поп": "dream pop",
    "дрим-поп": "dream pop",
    "электропоп": "electropop",
    "электро-поп": "electropop",
    "электро свинг": "electro swing",
    "электро рок": "electro rock",
    "киберпанк": "cyberpunk",
    "дарк электро": "dark electro",
    "лаундж": "lounge",
    "лаунж": "lounge",
    "евроденс": "eurodance",
    "евродэнс": "eurodance",
    "гетто": "ghetto",
    "гетто хаус": "ghetto house",
    "дэнс": "dance music",
    "денс": "dance music",
    "танцевальная": "dance music",
    "танцевальная музыка": "dance music",
    "брейкбит": "breakbeat",
    "дип": "deep house",
    "инструментал": "instrumental",
    "инструментальная": "instrumental",
    "саксофон": "saxophone",
    "скрипка": "violin",
    "флейта": "flute",
    "духовые": "brass",
    "барабаны": "drums",
    "синтезатор": "synth",
    "оркестр": "orchestral",
    "оркестровая": "orchestral",
    "эпик": "epic",
    "эпическая": "epic",
    "кинематографичная": "cinematic",
    "кинематографическая": "cinematic",
    "фьюче бас": "future bass",
    "фьючер бас": "future bass",
    "фьюче бейс": "future bass",
    "фьючер бейс": "future bass",
    "витч хаус": "witch house",
    "вич хаус": "witch house",
    "вичуха": "witch house",
    "мелодик хаус": "melodic house",
    "глитч": "glitch",
    "глитч хоп": "glitch hop",
    "хардстайл": "hardstyle",
    "нью эйдж": "new age",
    "нью-эйдж": "new age",
    "прогрессив хаус": "progressive house",
    "трип хоп": "trip hop",
    "трип-хоп": "trip hop",
    "реггетон": "reggaeton",
    "бачата": "bachata",
    "сальса": "salsa",
    "клауд рэп": "cloud rap",
    "клауд реп": "cloud rap",
    "индастриал": "industrial",
    "сладж": "sludge",
    "стоунер": "stoner rock",
    "стоунер рок": "stoner rock",
    "дримпоп": "dream pop",
    "синтипоп": "synthpop",
    "альтернатива": "alternative",
    "альтернативный рок": "alternative rock",
    "альт рок": "alt rock",
    "пост рок": "post-rock",
    "гаражный рок": "garage rock",
    "мат рок": "math rock",
    "нойз": "noise",
    "нойз рок": "noise rock",
    "хардкор панк": "hardcore punk",
    "краст": "crust punk",
    "грайндкор": "grindcore",
    "дэткор": "deathcore",
    "деткор": "deathcore",
    "металкор": "metalcore",
    "пост хардкор": "post-hardcore",
    "пост-хардкор": "post-hardcore",
    "эмо": "emo",
    "мидвест эмо": "midwest emo",
    "скримо": "screamo",
    "блэкгейз": "blackgaze",
    "колдвейв": "coldwave",
    "вейпорвейв": "vaporwave",
    "вапорвейв": "vaporwave",
    "ретровейв": "retrowave",
    "нью вейв": "new wave",
    "новая волна": "new wave",
    "психоделик": "psychedelic",
    "психоделический рок": "psychedelic rock",
    "краут рок": "krautrock",
    "краутрок": "krautrock",
    "глэм": "glam rock",
    "глэм рок": "glam rock",
    "рокабилли": "rockabilly",
    "сайкобилли": "psychobilly",
    "дарк кабаре": "dark cabaret",
    "дарк фолк": "dark folk",
    "неофолк": "neofolk",
    "готик": "gothic",
    "готик рок": "gothic rock",
    "готика": "gothic",
    "симфония": "symphony",
    "опера": "opera",
    "хор": "choir",
    "босса нова": "bossa nova",
    "боссанова": "bossa nova",
    "самба": "samba",
    "латина": "latin",
    "латино": "latin",
    "афробит": "afrobeats",
    "рэгги": "reggae",
    "рутс регги": "roots reggae",
    "дэнсхолл": "dancehall",
    "денсхолл": "dancehall",
    "сока": "soca",
    "буги": "boogie",
    "электро": "electro",
    "бигбит": "big beat",
    "джангл": "jungle",
    "ликвид фанк": "liquid drum and bass",
    "ликвид днб": "liquid drum and bass",
    "нейрофанк": "neurofunk",
    "габба": "gabber",
    "габбер": "gabber",
    "хэппи хардкор": "happy hardcore",
    "спидкор": "speedcore",
    "френчкор": "frenchcore",
    "эсид": "acid",
    "эйсид": "acid",
    "эйсид хаус": "acid house",
    "эйсид техно": "acid techno",
    "минимал": "minimal",
    "гэридж": "uk garage",
    "гараж": "uk garage",
    "юк гэридж": "uk garage",
    "басслайн": "bassline",
    "грайм": "grime",
    "витчхаус": "witch house",
    "вичхаус": "witch house",
    "8бит": "8bit",
    "8-бит": "8bit",
    "16бит": "16-bit",
    "16-бит": "16-bit",
    "ост": "soundtrack",
    # Decades
    "80s": "1980s",
    "80-е": "1980s",
    "80е": "1980s",
    "восьмидесятые": "1980s",
    "90s": "1990s",
    "90-е": "1990s",
    "90е": "1990s",
    "девяностые": "1990s",
    "70s": "1970s",
    "70-е": "1970s",
    "70е": "1970s",
    "семидесятые": "1970s",
    "60s": "1960s",
    "60-е": "1960s",
    "60е": "1960s",
    "шестидесятые": "1960s",
    "50s": "1950s",
    "50-е": "1950s",
    "50е": "1950s",
    "пятидесятые": "1950s",
    "2000s": "2000s",
    "00s": "00s",
    "нулевые": "2000s",
}

# Single word mappings for compound translations (e.g. "дарк" + "эмбиент" -> "dark ambient")
RUSSIAN_WORD_MAP: Dict[str, str] = {
    "дарк": "dark",
    "светлый": "light",
    "мелодик": "melodic",
    "прогрессив": "progressive",
    "прог": "prog",
    "минимал": "minimal",
    "эпик": "epic",
    "эпический": "epic",
    "кинематографичный": "cinematic",
    "кинематографический": "cinematic",
    "инструментальный": "instrumental",
    "инструментал": "instrumental",
    "акустический": "acoustic",
    "акустика": "acoustic",
    "вокальный": "vocal",
    "вокал": "vocal",
    "ретро": "retro",
    "винтаж": "vintage",
    "винтажный": "vintage",
    "космический": "cosmic",
    "космос": "cosmic",
    "атмосферный": "atmospheric",
    "тяжелый": "heavy",
    "тяжёлый": "heavy",
    "быстрый": "fast",
    "медленный": "slow",
    "грустный": "sad",
    "веселый": "happy",
    "весёлый": "happy",
    "энергичный": "energetic",
    "русский": "russian",
    "французский": "french",
    "японский": "japanese",
    "британский": "british",
    "немецкий": "german",
    "итальянский": "italian",
    "дип": "deep",
    "хаус": "house",
    "техно": "techno",
    "транс": "trance",
    "рок": "rock",
    "поп": "pop",
    "метал": "metal",
    "металл": "metal",
    "панк": "punk",
    "рэп": "rap",
    "реп": "rap",
    "джаз": "jazz",
    "блюз": "blues",
    "соул": "soul",
    "фанк": "funk",
    "фолк": "folk",
    "эмбиент": "ambient",
    "дрилл": "drill",
    "трэп": "trap",
    "трап": "trap",
    "фонк": "phonk",
    "бас": "bass",
    "волна": "wave",
}


def clean_tag_token(raw_token: str) -> str:
    """Clean a single tag token of excess punctuation, symbols, and formatting."""
    t = raw_token.strip()
    # Strip leading/trailing punctuation and non-alphanumeric chars (preserving internal hyphens, spaces, etc.)
    t = re.sub(r"^[^\w\dа-яА-ЯёЁ]+|[^\w\dа-яА-ЯёЁ]+$", "", t)
    # Normalize multiple spaces inside
    t = re.sub(r"\s+", " ", t)
    return t.lower()


def transliterate_cyrillic(text: str, h_for_kh: bool = False) -> str:
    """Transliterate Cyrillic string to Latin."""
    charmap = CYRILLIC_TO_LATIN_H if h_for_kh else CYRILLIC_TO_LATIN_KH
    result = []
    for ch in text.lower():
        result.append(charmap.get(ch, ch))
    return "".join(result)


# Phonetic building blocks for Russian genre borrowings and fused compound words
# (e.g. "хэвиметалл", "ньювейв", "постпанк", "чиллстеп")
PHONETIC_REPLACEMENTS: List[Tuple[str, str]] = [
    ("хэвиметалл", "heavy metal"), ("хевиметалл", "heavy metal"),
    ("хэвиметал", "heavy metal"), ("хевиметал", "heavy metal"),
    ("хэви", "heavy"), ("хеви", "heavy"),
    ("ньювейв", "new wave"), ("ньювэйв", "new wave"),
    ("ньюэйдж", "new age"), ("ньюэйджи", "new age"),
    ("нью", "new"), ("нов", "new"),
    ("вейв", "wave"), ("вэйв", "wave"),
    ("металл", "metal"), ("метал", "metal"),
    ("пост", "post"),
    ("синтивейв", "synthwave"), ("синтвейв", "synthwave"),
    ("синтипоп", "synthpop"), ("синтпоп", "synthpop"),
    ("синти", "synth"), ("синт", "synth"),
    ("дарквейв", "darkwave"), ("дарксинт", "darksynth"), ("дарк", "dark"),
    ("попса", "pop"), ("поп", "pop"),
    ("панк", "punk"),
    ("рок", "rock"),
    ("витчхаус", "witch house"), ("вичхаус", "witch house"),
    ("витч", "witch"), ("вич", "witch"),
    ("клаудрап", "cloud rap"), ("клаудрэп", "cloud rap"), ("клауд", "cloud"),
    ("дримпоп", "dream pop"), ("дрим", "dream"),
    ("хардкор", "hardcore"), ("хард", "hard"), ("софт", "soft"),
    ("дипхаус", "deep house"), ("дип", "deep"),
    ("чиллстеп", "chillstep"), ("чиллаут", "chillout"), ("чилл", "chill"),
    ("блэкметалл", "black metal"), ("блэкметал", "black metal"),
    ("блэк", "black"), ("блек", "black"),
    ("дэтметалл", "death metal"), ("дэтметал", "death metal"),
    ("детметалл", "death metal"), ("детметал", "death metal"),
    ("дэткор", "deathcore"), ("деткор", "deathcore"),
    ("дэт", "death"), ("дет", "death"),
    ("трэшметалл", "thrash metal"), ("трэшметал", "thrash metal"),
    ("трешметалл", "thrash metal"), ("трешметал", "thrash metal"),
    ("трэш", "thrash"), ("треш", "thrash"),
    ("пауэрметалл", "power metal"), ("пауэрметал", "power metal"),
    ("пауэр", "power"), ("пауер", "power"),
    ("нойз", "noise"), ("мат", "math"),
    ("степ", "step"), ("кор", "core"),
    ("бит", "beat"),
    ("хипхоп", "hip hop"), ("хип-хоп", "hip hop"), ("хип", "hip"), ("хоп", "hop"),
    ("хаус", "house"), ("техно", "techno"), ("транс", "trance"),
    ("джаз", "jazz"), ("блюз", "blues"),
    ("соул", "soul"), ("фанк", "funk"), ("фолк", "folk"),
    ("рэп", "rap"), ("реп", "rap"), ("рап", "rap"),
    ("дрилл", "drill"), ("трэп", "trap"), ("трап", "trap"),
    ("фонк", "phonk"),
    ("гараж", "garage"), ("гэридж", "garage"),
    ("грайм", "grime"), ("свинг", "swing"),
    ("басс", "bass"), ("бас", "bass"), ("бейс", "bass"), ("бэйс", "bass"),
    ("инди", "indie"), ("электро", "electro"),
    ("рэгги", "reggae"), ("регги", "reggae"),
    ("даб", "dub"), ("ска", "ska"),
    ("грандж", "grunge"), ("гранж", "grunge"),
    ("шугейз", "shoegaze"), ("эмбиент", "ambient"),
    ("диско", "disco"), ("евро", "euro"), ("афро", "afro"),
    ("латин", "latin"), ("латино", "latin"),
    ("психоделик", "psychedelic"),
    ("прогрессив", "progressive"), ("прог", "prog"),
    ("альт", "alt"), ("альтернатив", "alternative"),
    ("глитч", "glitch"), ("чиптюн", "chiptune"),
    ("мидвест", "midwest"), ("скримо", "screamo"),
    ("колд", "cold"),
    ("вапор", "vapor"), ("вейпор", "vapor"),
    ("эмо", "emo"), ("краут", "kraut"), ("глэм", "glam"),
    ("босса", "bossa"), ("нова", "nova"),
    ("самба", "samba"), ("буги", "boogie"),
    ("джангл", "jungle"), ("габбер", "gabber"), ("габба", "gabber"),
    ("спид", "speed"), ("френч", "french"),
    ("эйсид", "acid"), ("эсид", "acid"),
    ("минимал", "minimal"), ("мелодик", "melodic"),
    ("русский", "russian"), ("рус", "russian"),
    ("лоуфай", "lo-fi"), ("лофай", "lo-fi"), ("лофи", "lo-fi"),
]
# Sort descending by Russian token length so longest prefixes match first
PHONETIC_REPLACEMENTS.sort(key=lambda x: len(x[0]), reverse=True)


def resolve_single_tag(raw_token: str) -> Optional[str]:
    """
    Attempt to resolve a raw user-provided token into an official whitelist tag.
    Returns canonical tag string if resolved, or None if unrecognized.
    """
    cleaned = clean_tag_token(raw_token)
    if not cleaned:
        return None

    # 1. Exact direct match in whitelist
    if cleaned in ALLOWED_TAGS:
        return cleaned

    # 2. Direct lookup in Russian synonyms dictionary
    if cleaned in RUSSIAN_GENRE_SYNONYMS:
        target = RUSSIAN_GENRE_SYNONYMS[cleaned]
        if target in ALLOWED_TAGS:
            return target

    # 3. Normalized alphanumeric lookup (e.g. "lofi" -> "lo-fi", "hiphop" -> "hip hop")
    norm_key = re.sub(r"[^a-z0-9]", "", cleaned)
    if norm_key and norm_key in NORMALIZED_TAGS:
        return NORMALIZED_TAGS[norm_key]

    # 4. If token contains Cyrillic characters, try phonetic morphemes, translation and transliteration
    has_cyrillic = bool(re.search(r"[а-яё]", cleaned))
    if has_cyrillic:
        # 4a. Phonetic morpheme replacement (handles fused words like "хэвиметалл", "ньювейв")
        cand_phonetic = cleaned
        for ru, en in PHONETIC_REPLACEMENTS:
            cand_phonetic = cand_phonetic.replace(ru, en)

        if cand_phonetic in ALLOWED_TAGS:
            return cand_phonetic
        norm_ph = re.sub(r"[^a-z0-9]", "", cand_phonetic)
        if norm_ph and norm_ph in NORMALIZED_TAGS:
            return NORMALIZED_TAGS[norm_ph]

        # In case some Cyrillic letters remain, transliterate them as well
        cand_pt = transliterate_cyrillic(cand_phonetic, h_for_kh=True)
        if cand_pt in ALLOWED_TAGS:
            return cand_pt
        norm_pt = re.sub(r"[^a-z0-9]", "", cand_pt)
        if norm_pt and norm_pt in NORMALIZED_TAGS:
            return NORMALIZED_TAGS[norm_pt]

        # 4b. Transliterate directly to Latin
        translit_kh = transliterate_cyrillic(cleaned, h_for_kh=False)
        if translit_kh in ALLOWED_TAGS:
            return translit_kh
        norm_translit_kh = re.sub(r"[^a-z0-9]", "", translit_kh)
        if norm_translit_kh in NORMALIZED_TAGS:
            return NORMALIZED_TAGS[norm_translit_kh]

        translit_h = transliterate_cyrillic(cleaned, h_for_kh=True)
        if translit_h in ALLOWED_TAGS:
            return translit_h
        norm_translit_h = re.sub(r"[^a-z0-9]", "", translit_h)
        if norm_translit_h in NORMALIZED_TAGS:
            return NORMALIZED_TAGS[norm_translit_h]

        # 4b. Word-by-word compound translation for multi-word Russian tags
        # e.g. "дарк эмбиент" -> "dark ambient", "мелодик рок" -> "melodic rock"
        words = re.split(r"[\s\-]+", cleaned)
        if len(words) > 1:
            translated_words = []
            for w in words:
                tr = (
                    RUSSIAN_GENRE_SYNONYMS.get(w)
                    or RUSSIAN_WORD_MAP.get(w)
                    or transliterate_cyrillic(w, h_for_kh=True)
                )
                translated_words.append(tr)

            # Try spaced combination
            candidate_space = " ".join(translated_words)
            if candidate_space in ALLOWED_TAGS:
                return candidate_space
            norm_space = re.sub(r"[^a-z0-9]", "", candidate_space)
            if norm_space in NORMALIZED_TAGS:
                return NORMALIZED_TAGS[norm_space]

            # Try hyphenated combination
            candidate_hyphen = "-".join(translated_words)
            if candidate_hyphen in ALLOWED_TAGS:
                return candidate_hyphen
            norm_hyphen = re.sub(r"[^a-z0-9]", "", candidate_hyphen)
            if norm_hyphen in NORMALIZED_TAGS:
                return NORMALIZED_TAGS[norm_hyphen]

    # Not recognized in whitelist
    return None


def resolve_user_tags(text: str) -> Tuple[List[str], List[str]]:
    """
    Parse a comma-, semicolon-, or newline-separated string from the user,
    clean each tag, and validate against the Treblo whitelist.

    Returns:
        (valid_tags, invalid_raw_tags)
        - valid_tags: list of deduplicated canonical whitelist tags in original order
        - invalid_raw_tags: list of raw user tokens that could not be matched
    """
    if not text:
        return [], []

    # Split by commas, semicolons, or newlines
    raw_pieces = re.split(r"[,;\n]+", text)

    valid_tags: List[str] = []
    invalid_tags: List[str] = []
    seen = set()

    for piece in raw_pieces:
        raw_token = piece.strip()
        if not raw_token:
            continue

        resolved = resolve_single_tag(raw_token)
        if resolved:
            if resolved not in seen:
                seen.add(resolved)
                valid_tags.append(resolved)
        else:
            cleaned_display = clean_tag_token(raw_token) or raw_token
            invalid_tags.append(cleaned_display)

    return valid_tags, invalid_tags
