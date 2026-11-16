import json
import logging
import re
import secrets
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, Any, List, Tuple

import aiosqlite

from config import settings

logger = logging.getLogger(__name__)

MSK_TZ = timezone(timedelta(hours=3))


def get_msk_now() -> datetime:
    """Returns current datetime in Moscow Timezone (UTC+3)."""
    return datetime.now(MSK_TZ)


def format_per_track_badge(price: float, credits: int) -> str:
    """Formats price per track (e.g. '100 ₽ за трек' or '0.7 ₽ за трек')."""
    if credits <= 0:
        return ""
    per_track = price / credits
    if per_track.is_integer():
        return f"{int(per_track)} ₽ за трек"
    val = round(per_track, 2)
    return f"{val:g} ₽ за трек"


TRANSLIT_MAP = {
    'а': 'a', 'б': 'b', 'в': 'v', 'г': 'g', 'д': 'd', 'е': 'e', 'ё': 'yo', 'ж': 'zh',
    'з': 'z', 'и': 'i', 'й': 'y', 'к': 'k', 'л': 'l', 'м': 'm', 'н': 'n', 'о': 'o',
    'п': 'p', 'р': 'r', 'с': 's', 'т': 't', 'у': 'u', 'ф': 'f', 'х': 'h', 'ц': 'ts',
    'ч': 'ch', 'ш': 'sh', 'щ': 'sch', 'ъ': '', 'ы': 'y', 'ь': '', 'э': 'e', 'ю': 'yu', 'я': 'ya'
}


def slugify_artist(name: str) -> str:
    s = name.strip().lower()
    res = []
    for ch in s:
        if ch in TRANSLIT_MAP:
            res.append(TRANSLIT_MAP[ch])
        elif ch.isalnum():
            res.append(ch)
        elif ch in (' ', '-', '_'):
            res.append('_')
    slug = re.sub(r'_+', '_', ''.join(res)).strip('_')
    return slug or "artist"


DEFAULT_POPULAR_ARTISTS = []

DEFAULT_EXTENDED_ARTISTS = [
    {"id": "vxv_prince", "name": "V $ X V PRiNCE", "style": "казахский трэп, мелодичный качающий автотюн, клубный вайб, плотный 808 бас", "aliases": ["v $ x v prince", "vxv prince", "аскер", "принц"]},
    {"id": "lil_morty", "name": "LIL MORTY", "style": "грязный трэп, скейт-рэп, энергетика YungRussia, перегруженный бас", "aliases": ["lil morty", "лил морти", "морти"]},
    {"id": "bumboks", "name": "Бумбокс", "style": "акустический хип-хоп, душевный фанк-рок, виниловый скретч, хриплый эмоциональный вокал", "aliases": ["бумбокс", "хлывнюк", "boombox"]},
    {"id": "lovv66", "name": "LOVV66", "style": "гиперпоп, нью-вейв трэп, сладкий автотюн, заедающие мелодии, клубный кач", "aliases": ["lovv66", "ловв66", "лав66", "ваня"]},
    {"id": "tveth", "name": "TVETH", "style": "мрачный техничный трэп, тяжелый андеграунд, быстрый напористый флоу, холодная атмосфера", "aliases": ["tveth", "твет", "дима"]},
    {"id": "slava_kpss", "name": "Слава КПСС", "style": "концептуальный баттл-рэп, сатира, грайм, хлесткая панч-лирика, саркастичный флоу", "aliases": ["слава кпсс", "гнойный", "соня мармеладова", "валентин дядька"]},
    {"id": "krovostok", "name": "Кровосток", "style": "невозмутимый криминальный сторителлинг, монотонный циничный флоу, минималистичный олдскульный бит", "aliases": ["кровосток", "шило", "фельдман"]},
    {"id": "korzh", "name": "Макс Корж", "style": "стадионный дворовый поп-рэп, душевный припев, акустическая гитара, рейв-дроп", "aliases": ["макс корж", "корж", "max korzh"]},
    {"id": "mona", "name": "Mona", "style": "глубокий чувственный женский поп-вокал, лиричный R&B, кинематографичный саунд", "aliases": ["mona", "мона"]},
    {"id": "rasa", "name": "RASA", "style": "яркий танцевальный поп-хаус, пчеловод, зажигательный клубный дуэт, мощная бочка", "aliases": ["rasa", "раса"]},
    {"id": "rauf_faik", "name": "Rauf & Faik", "style": "лиричный душевный поп-дуэт, высокий фальцет, меланхоличные клавишные, медленный бит", "aliases": ["rauf & faik", "rauf faik", "рауф фаик", "рауф и фаик", "детство"]},
    {"id": "natan", "name": "Natan", "style": "клубный качающий хип-хоп, восточные танцевальные ритмы, харизматичный речитатив", "aliases": ["natan", "натан", "black star"]},
    {"id": "ramil", "name": "Ramil'", "style": "надрывный лиричный кальянный рэп, эмоциональный хриплый вокал, восточные мелодии, медленный бас", "aliases": ["ramil'", "ramil", "рамиль", "сияй"]},
    {"id": "the_limba", "name": "The Limba", "style": "гладкий романтичный R&B, танцевальный поп, мягкий сладкий вокал, легкий грув", "aliases": ["the limba", "лимба", "муха"]},
    {"id": "jony", "name": "JONY", "style": "проникновенный восточный поп, бархатный вокал, драматичные скрипки и пианино, стадионный припев", "aliases": ["jony", "джони", "комета"]},
    {"id": "jah_khalib", "name": "Jah Khalib", "style": "чувственный восточный R&B, глубокий бархатный вокал, романтичный хип-хоп, живой саксофон", "aliases": ["jah khalib", "джа халиб", "халиб", "баха"]},
    {"id": "skrip", "name": "Скриптонит", "style": "тягучий блюз-трэп, фирменный грув, живые барабаны, темная атмосфера", "aliases": ["скриптонит", "скрип", "skriptonit", "skrip"]},
    {"id": "morgenshtern", "name": "MORGENSHTERN", "style": "энергичный трэп, мощный 808 бас, дерзкий флоу, клубный бэнгер", "aliases": ["morgenshtern", "morgen", "моргенштерн", "морген", "алишер"]},
    {"id": "bato", "name": "BATO", "style": "мрачный плотный хип-хоп, низкий густой тембр, классический бум-бэп и трэп, уличный вайб", "aliases": ["bato", "бато"]},
    {"id": "044_rose", "name": "044 ROSE", "style": "психоделический клауд-рэп, сырой lo-fi звук, расслабленный абстрактный флоу", "aliases": ["044 rose", "044 роуз", "роуз"]},
    {"id": "thomas_mraz", "name": "Thomas Mraz", "style": "мелодичный фэнтези-R&B, кинематографичный нео-соул, высокий чистый вокал", "aliases": ["thomas mraz", "томас мраз", "мраз", "алмас"]},
    {"id": "1klas", "name": "1.Kla$", "style": "жесткий баттл-рэп нулевых, агрессивный немецко-русский флоу, грязь и панчи", "aliases": ["1.kla$", "1klas", "первый класс", "клас", "артем"]},
    {"id": "code80", "name": "CODE80", "style": "рейдж-трэп, перегруженный синтезаторный звук, автотюн, быстрый хайпер-ритм", "aliases": ["code80", "код80"]},
    {"id": "sqwoz_bab", "name": "Sqwoz Bab", "style": "ироничный комедийный трэп, забавный сюжетный речитатив, качающий танцевальный бит", "aliases": ["sqwoz bab", "сквоз баб", "сквозь баб", "марат"]},
    {"id": "kai_angel", "name": "Kai Angel", "style": "футуристичный индустриальный рейдж, глитч-трэп, перегруженные басы, темная электроника", "aliases": ["kai angel", "кай ангел", "zavet", "завет", "дима"]},
    {"id": "lizer", "name": "LIZER", "style": "эмо-рэп, акустический поп-рок, подростковая меланхолия, искренний вокал", "aliases": ["lizer", "лайзер", "лизер", "арсен"]},
    {"id": "thrill_pill", "name": "Thrill Pill", "style": "мемфис-трэп, абсурдный флоу, перегруженный 808 бас, клубный угар", "aliases": ["thrill pill", "трилл пилл", "тимур"]},
    {"id": "oxxxymiron", "name": "Oxxxymiron", "style": "быстрый техничный грайм, сложная рифмовка, плотный бит, интеллектуальный хип-хоп", "aliases": ["oxxxymiron", "oxxxy", "оксимирон", "окси", "мирон"]},
    {"id": "basta", "name": "Баста", "style": "лиричный русский рэп, гитарные переборы, хриплый душевный вокал", "aliases": ["basta", "баста", "ноггано", "n1nt3ndo", "василий вакуленко"]},
    {"id": "tape", "name": "Big Baby Tape", "style": "трэп, мемфис-рэп, напористый флоу, мощный перегруженный 808 бас", "aliases": ["big baby tape", "tape", "биг бейби тейп", "тейп", "егор ракитин"]},
    {"id": "kizaru", "name": "Kizaru", "style": "классический мемфис-хип-хоп, расслабленный флоу, мрачный атмосферный трэп", "aliases": ["kizaru", "кизару", "олег", "нечипоренко"]},
    {"id": "kreed", "name": "Егор Крид", "style": "мелодичный поп-хип-хоп, современный коммерческий поп, гладкий вокал", "aliases": ["егор крид", "крид", "kreed", "egor kreed"]},
    {"id": "buda", "name": "OG Buda", "style": "детройт-рэп, оффбит флоу, остроумные панчлайны, быстрый напористый бит", "aliases": ["og buda", "buda", "ог буда", "буда", "гриша"]},
    {"id": "face", "name": "Face", "style": "минималистичный трэп, эмоциональный речитатив, драйвовый молодежный флоу", "aliases": ["face", "фейс", "иван дремин"]},
    {"id": "eljay", "name": "Элджей", "style": "клубный хаус-рэп, неоновый дип-хаус, заедающий припев, автотюн", "aliases": ["элджей", "sayonaraboy", "eljay", "allj", "леша узенюк"]},
    {"id": "pharaoh", "name": "Pharaoh", "style": "мрачный клауд-рэп, дед-династия, холодный меланхоличный саунд, шепчущий флоу", "aliases": ["pharaoh", "фараон", "фара", "глеб голубин"]},
    {"id": "tfest", "name": "T-fest", "style": "мелодичный трэп, высокий эмоциональный вокал, гитарные акустические элементы", "aliases": ["t-fest", "tfest", "т-фест", "тифест", "кирилл"]},
    {"id": "miyagi", "name": "Miyagi", "style": "глубокий регги-хип-хоп, атмосферный саунд, плотный качающий грув", "aliases": ["miyagi", "мияги", "эндшпиль", "hajime", "азамат"]},
    {"id": "saluki", "name": "Saluki", "style": "экспериментальный кинематографичный хип-хоп, сложный продакшн, живые инструменты", "aliases": ["saluki", "салуки", "сеня"]},
    {"id": "instasamka", "name": "INSTASAMKA", "style": "дерзкий поп-трэп, глянцевый бит, ироничный речитатив, клубный кач", "aliases": ["instasamka", "инстасамка", "самка", "даша затеева"]},
    {"id": "jigan", "name": "Джиган", "style": "клубный хип-хоп, плотный танцевальный кач, уверенный бархатный речитатив", "aliases": ["джиган", "geegun", "jigan", "денис"]},
    {"id": "mot", "name": "Мот", "style": "лиричный соул-хип-хоп, R&B, танцевальный поп, мелодичные припевы", "aliases": ["мот", "mot", "матвей мельников"]},
    {"id": "lone", "name": "L'one", "style": "мотивирующий стадионный хип-хоп, эпичные трубы и барабаны, энергичный флоу", "aliases": ["l'one", "lone", "леван", "лван"]},
    {"id": "guf", "name": "Guf", "style": "классический московский андеграунд-рэп, неторопливый размеренный флоу, житейская лирика", "aliases": ["guf", "гуф", "леша долматов"]},
    {"id": "noize", "name": "Noize MC", "style": "фристайл-рок-хип-хоп, живой гаражный панк, остросоциальные стихи, акустическая гитара", "aliases": ["noize mc", "noize", "нойз", "нойз эмси", "иван алексеев"]},
    {"id": "markul", "name": "Markul", "style": "мелодичный лондонский грайм-поп, электронный саунд, мягкий автотюн", "aliases": ["markul", "маркул", "марк маркул"]},
    {"id": "gone_fludd", "name": "GONE.Fludd", "style": "яркий психоделический поп-трэп, комиксовый драйв, быстрый игривый речитатив", "aliases": ["gone.fludd", "gone fludd", "гон флад", "флад", "саша смирнов"]},
    {"id": "soda_luv", "name": "SODA LUV", "style": "агрессивный трэп, низкий хриплый голос, перегруженный бас, мем-панчи", "aliases": ["soda luv", "sodaluv", "сода лав", "сода", "влад"]},
    {"id": "platina", "name": "Платина", "style": "расслабленный автотюновый трэп, минималистичный плагг, меланхоличный клубный вайб", "aliases": ["платина", "роберт", "platina", "рнб клуб"]},
    {"id": "boulevard_depo", "name": "Boulevard Depo", "style": "самобытный тягучий трэп, монотонный гипнотический речитатив, сюрреалистичный бит", "aliases": ["boulevard depo", "бульвар депо", "депо", "артем шатохин"]},
    {"id": "dzhizus", "name": "Джизус", "style": "надрывный гранж-рок, эмоциональный кричащий вокал, перегруженные гитары, пост-панк", "aliases": ["джизус", "dzhizus", "влад кожихов"]},
    {"id": "loqiemean", "name": "Loqiemean", "style": "тяжелый индастриал-метал-хип-хоп, взрывные гитары, яростный флоу, мощный живой звук", "aliases": ["loqiemean", "локи", "локимин", "роман"]},
    {"id": "feduk", "name": "FEDUK", "style": "легкий танцевальный хаус-поп, мелодичный позитивный вокал, летний вайб", "aliases": ["feduk", "федук", "федя"]},
    {"id": "toxis", "name": "Toxi$", "style": "гипер-энергичный рейдж-трэп, высокий забавный питч, быстрый хаотичный флоу", "aliases": ["toxi$", "toxis", "токсис", "андрей"]},
    {"id": "offmi", "name": "OFFMi", "style": "безумный динамичный трэп, ломаный ритм, экспрессивный кричащий флоу", "aliases": ["offmi", "оффми", "никита"]},
    {"id": "rocket", "name": "Rocket", "style": "ультра-расслабленный шепчущий трэп, сонный флоу, глубокий глухой бас", "aliases": ["rocket", "рокет", "дима"]},
    {"id": "i61", "name": "i61", "style": "психоделический глитч-рэп, комиксовый авангард, футуристичные синты", "aliases": ["i61", "айсиксван", "ай61", "федя"]},
    {"id": "obladaet", "name": "Obladaet", "style": "техничный британский дрилл, холодный грайм, уверенный стильный флоу", "aliases": ["obladaet", "обладает", "обла", "назар"]},
    {"id": "yanix", "name": "Yanix", "style": "классический трэп старой школы, мажорный хвастливый флоу, яркие панчлайны", "aliases": ["yanix", "яникс", "яни"]},
    {"id": "yung_trappa", "name": "Yung Trappa", "style": "культовый сырой трэп, непредсказуемый флоу, уличный фристайл", "aliases": ["yung trappa", "янг траппа", "траппа", "влад"]},
    {"id": "may_waves", "name": "May Wave$", "style": "мелодичный душевный поп-трэп, высокий автотюновый вокал, романтика", "aliases": ["may wave$", "may waves", "мей вейвс", "даниил"]},
    {"id": "egor_nats", "name": "Егор Натс", "style": "искренний подростковый инди-поп, акустическая гитара, теплая ламповая лирика", "aliases": ["егор натс", "натс", "nats"]},
    {"id": "zamay", "name": "Замай", "style": "ироничный пост-модернистский рэп, баттловый пафос, стадионные припевы", "aliases": ["замай", "антихрист", "хан замай", "zamay", "андрей"]},
    {"id": "smoki_mo", "name": "Смоки Мо", "style": "легендарный питерский мистический хип-хоп, густой кинематографичный саунд, хриплый авторитетный флоу", "aliases": ["смоки мо", "смоки", "молла", "кара-тэ", "александр"]},
    {"id": "2517", "name": "25/17", "style": "мощный русский рэп-рок, живые барабаны, гитарный драйв, глубокая духовная лирика", "aliases": ["25/17", "2517", "бледный", "ант", "двадцать пять семнадцать"]},
    {"id": "kaspiyskiy_gruz", "name": "Каспийский Груз", "style": "мрачный криминальный баку-рэп, хриплые голоса, житейская уличная драма", "aliases": ["каспийский груз", "весъ", "брутто", "каспийский"]},
    {"id": "loc_dog", "name": "Loc-Dog", "style": "лиричный электро-хип-хоп, задушевный речитатив, мелодичные клубные биты", "aliases": ["loc-dog", "loc dog", "лок-дог", "лок дог", "александр жвакин"]},
    {"id": "mnogotochie", "name": "Многоточие", "style": "классический русский андеграунд 2000-х, щемящая дворовая тоска, фортепианные сэмплы", "aliases": ["многоточие", "руставели", "в жизни так бывает"]},
    {"id": "kasta", "name": "Каста", "style": "эталонный ростовский олдскул, плотный качающий грув, живая повествовательная лирика", "aliases": ["каста", "влади", "шим", "хамиль", "змей"]},
    {"id": "atl", "name": "ATL", "style": "кислотный шаманский электро-рэп, мрачный хаус-бит, глубокая поэзия", "aliases": ["atl", "атл", "сергей семак", "acidhouze"]},
    {"id": "dima_bilan", "name": "Дима Билан", "style": "топовый драматичный евро-поп, мощный эмоциональный вокал, современные клубные аранжировки", "aliases": ["дима билан", "билан", "виктор белан"]},
    {"id": "sergey_lazarev", "name": "Сергей Лазарев", "style": "танцевальный стадионный поп, эпичные припевы, безупречный чистый вокал", "aliases": ["сергей лазарев", "лазарев"]},
    {"id": "ani_lorak", "name": "Ани Лорак", "style": "мощная женская поп-баллада, страстный драматичный вокал, соул-элементы", "aliases": ["ани лорак", "лорак", "каролина"]},
    {"id": "cream_soda", "name": "Cream Soda", "style": "стильный электро-поп, ностальгический синти-диско, танцевальный хаус, нежный женский вокал", "aliases": ["cream soda", "крем сода", "плачу на техно"]},
    {"id": "ariya", "name": "Ария", "style": "классический хеви-метал, виртуозные гитарные соло, высокий оперный метал-вокал, эпичный саунд", "aliases": ["ария", "кипелов", "холстинин", "беркут"]},
    {"id": "mumiy_troll", "name": "Мумий Тролль", "style": "самобытный рокапопс, игривый мурлыкающий вокал, морская романтика, инди-гитары", "aliases": ["мумий тролль", "лагутенко", "илья лагутенко"]},
    {"id": "bi2", "name": "Би-2", "style": "меланхоличный симфонический поп-рок, атмосферные скрипки, гитарный драйв, кинематографичный дуэт", "aliases": ["би-2", "би 2", "bi-2", "bi2", "лева", "шура"]},
]


def _format_artist_row(row: aiosqlite.Row) -> Dict[str, Any]:
    d = dict(row)
    if isinstance(d.get("aliases"), str):
        try:
            d["aliases"] = json.loads(d["aliases"])
        except Exception:
            d["aliases"] = [a.strip() for a in d["aliases"].split(",") if a.strip()]
    elif not d.get("aliases"):
        d["aliases"] = []
    return d


class Database:
    def __init__(self, db_path: str = settings.database_path):
        self.db_path = db_path

    async def init(self) -> None:
        """Create tables if they don't exist."""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    user_id INTEGER PRIMARY KEY,
                    username TEXT,
                    first_name TEXT,
                    balance INTEGER DEFAULT 0,
                    paid_balance INTEGER DEFAULT 0,
                    gift_balance INTEGER DEFAULT 0,
                    referral_balance REAL DEFAULT 0.0,
                    referred_by INTEGER,
                    created_at TIMESTAMP DEFAULT (datetime('now', '+3 hours'))
                )
            """)

            # Ensure referral_balance column exists if table was created previously without it
            try:
                await db.execute("ALTER TABLE users ADD COLUMN referral_balance REAL DEFAULT 0.0")
            except Exception:
                pass

            # Ensure columns exist if table was created previously without them
            try:
                await db.execute("ALTER TABLE users ADD COLUMN paid_balance INTEGER DEFAULT 0")
            except Exception:
                pass

            try:
                await db.execute("ALTER TABLE users ADD COLUMN gift_balance INTEGER DEFAULT 0")
            except Exception:
                pass

            # Migrate legacy balance to gift_balance if needed
            try:
                await db.execute("""
                    UPDATE users
                    SET gift_balance = balance
                    WHERE paid_balance = 0 AND gift_balance = 0 AND balance > 0
                """)
            except Exception:
                pass

            await db.execute("""
                CREATE TABLE IF NOT EXISTS generations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    task_id TEXT UNIQUE NOT NULL,
                    prompt TEXT NOT NULL,
                    artist TEXT,
                    instrumental INTEGER DEFAULT 0,
                    lyrics TEXT,
                    status TEXT DEFAULT 'PENDING',
                    audio_url TEXT,
                    duration REAL,
                    created_at TIMESTAMP DEFAULT (datetime('now', '+3 hours')),
                    FOREIGN KEY (user_id) REFERENCES users (user_id)
                )
            """)

            # Ensure column exists if table was created previously without it
            try:
                await db.execute("ALTER TABLE generations ADD COLUMN artist TEXT")
            except Exception:
                pass

            try:
                await db.execute("ALTER TABLE generations ADD COLUMN genres TEXT")
            except Exception:
                pass

            try:
                await db.execute("ALTER TABLE generations ADD COLUMN error_message TEXT")
            except Exception:
                pass

            try:
                await db.execute("ALTER TABLE generations ADD COLUMN raw_response TEXT")
            except Exception:
                pass

            try:
                await db.execute("ALTER TABLE generations ADD COLUMN delivery_status TEXT DEFAULT 'DELIVERED'")
            except Exception:
                pass

            try:
                await db.execute("ALTER TABLE generations ADD COLUMN image_url TEXT")
            except Exception:
                pass

            await db.execute("CREATE INDEX IF NOT EXISTS idx_generations_delivery ON generations(delivery_status, status)")

            # Uptime & Health logs table
            await db.execute("""
                CREATE TABLE IF NOT EXISTS uptime_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    service TEXT NOT NULL,
                    status TEXT NOT NULL,
                    latency_ms REAL DEFAULT 0.0,
                    error_message TEXT,
                    created_at TIMESTAMP DEFAULT (datetime('now', '+3 hours'))
                )
            """)
            await db.execute("CREATE INDEX IF NOT EXISTS idx_uptime_service_created ON uptime_logs (service, created_at)")

            await db.execute("""
                CREATE TABLE IF NOT EXISTS payments (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    payment_id TEXT UNIQUE NOT NULL,
                    user_id INTEGER NOT NULL,
                    amount REAL NOT NULL,
                    credits INTEGER NOT NULL,
                    status TEXT DEFAULT 'pending',
                    created_at TIMESTAMP DEFAULT (datetime('now', '+3 hours')),
                    updated_at TIMESTAMP DEFAULT (datetime('now', '+3 hours')),
                    FOREIGN KEY (user_id) REFERENCES users (user_id)
                )
            """)

            try:
                await db.execute("ALTER TABLE payments ADD COLUMN promo_activation_id INTEGER")
            except Exception:
                pass

            try:
                await db.execute("ALTER TABLE payments ADD COLUMN provider TEXT DEFAULT 'yookassa'")
            except Exception:
                pass

            try:
                await db.execute("ALTER TABLE payments ADD COLUMN currency TEXT DEFAULT 'RUB'")
            except Exception:
                pass

            try:
                await db.execute("ALTER TABLE payments ADD COLUMN telegram_message_id INTEGER")
            except Exception:
                pass

            await db.execute("""
                CREATE TABLE IF NOT EXISTS tariffs (
                    id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    credits INTEGER NOT NULL,
                    price REAL NOT NULL,
                    emoji TEXT NOT NULL,
                    badge TEXT NOT NULL
                )
            """)

            # Populate tariffs if empty
            async with db.execute("SELECT COUNT(*) FROM tariffs") as cursor:
                tariffs_count = (await cursor.fetchone())[0]

            if tariffs_count == 0:
                default_tariffs = [
                    ("pack_5", "5 генераций", 5, 10.0, "🥉", format_per_track_badge(10.0, 5)),
                    ("pack_15", "15 генераций", 15, 10.0, "🥈", format_per_track_badge(10.0, 15)),
                    ("pack_45", "45 генераций", 45, 10.0, "🥇", format_per_track_badge(10.0, 45)),
                    ("pack_100", "100 генераций", 100, 10.0, "👑", format_per_track_badge(10.0, 100)),
                ]
                await db.executemany(
                    """
                    INSERT INTO tariffs (id, title, credits, price, emoji, badge)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    default_tariffs,
                )
            else:
                # Migrate legacy pack_50 -> pack_45 and pack_150 -> pack_100 if present
                await db.execute(
                    "UPDATE tariffs SET id = 'pack_45', title = '45 генераций', credits = 45 WHERE id = 'pack_50'"
                )
                await db.execute(
                    "UPDATE tariffs SET id = 'pack_100', title = '100 генераций', credits = 100 WHERE id = 'pack_150'"
                )

                # Automatically keep badges in sync as dynamic "X ₽ за трек"
                async with db.execute("SELECT id, credits, price, badge FROM tariffs") as cursor:
                    existing_tariffs = await cursor.fetchall()
                    for row in existing_tariffs:
                        tid, cr, pr, bg = row[0], row[1], row[2], row[3]
                        new_bg = format_per_track_badge(pr, cr)
                        if bg != new_bg:
                            await db.execute(
                                "UPDATE tariffs SET badge = ? WHERE id = ?",
                                (new_bg, tid),
                            )

            # Create artists table
            await db.execute("""
                CREATE TABLE IF NOT EXISTS artists (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    style TEXT NOT NULL,
                    aliases TEXT,
                    is_popular INTEGER DEFAULT 1,
                    display_order INTEGER DEFAULT 0,
                    is_active INTEGER DEFAULT 1,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # Populate default artists if table is empty
            async with db.execute("SELECT COUNT(*) FROM artists") as cursor:
                artists_count = (await cursor.fetchone())[0]

            if artists_count == 0:
                artists_to_insert = []
                for idx, a in enumerate(DEFAULT_POPULAR_ARTISTS, start=1):
                    artists_to_insert.append((
                        a["id"],
                        a["name"],
                        a["style"],
                        json.dumps(a.get("aliases", []), ensure_ascii=False),
                        1,
                        idx,
                        1,
                    ))
                for idx, a in enumerate(DEFAULT_EXTENDED_ARTISTS, start=1):
                    artists_to_insert.append((
                        a["id"],
                        a["name"],
                        a["style"],
                        json.dumps(a.get("aliases", []), ensure_ascii=False),
                        0,
                        idx,
                        1,
                    ))
                await db.executemany(
                    """
                    INSERT INTO artists (id, name, style, aliases, is_popular, display_order, is_active)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    artists_to_insert,
                )

            # Create bot_settings table for dynamic toggles (subscription check, channels, etc.)
            await db.execute("""
                CREATE TABLE IF NOT EXISTS bot_settings (
                    key TEXT PRIMARY KEY,
                    value TEXT,
                    updated_at TIMESTAMP DEFAULT (datetime('now', '+3 hours'))
                )
            """)

            # One-time migration: convert legacy UTC timestamps (+0) to MSK (+3 hours)
            async with db.execute("SELECT value FROM bot_settings WHERE key = 'msk_timestamps_migrated'") as cursor:
                migrated_row = await cursor.fetchone()

            if not migrated_row:
                try:
                    await db.execute("UPDATE generations SET created_at = datetime(created_at, '+3 hours') WHERE created_at IS NOT NULL")
                except Exception:
                    pass
                try:
                    await db.execute("UPDATE payments SET created_at = datetime(created_at, '+3 hours'), updated_at = datetime(updated_at, '+3 hours') WHERE created_at IS NOT NULL")
                except Exception:
                    pass
                try:
                    await db.execute("UPDATE users SET created_at = datetime(created_at, '+3 hours') WHERE created_at IS NOT NULL")
                except Exception:
                    pass
                try:
                    await db.execute("UPDATE uptime_logs SET created_at = datetime(created_at, '+3 hours') WHERE created_at IS NOT NULL")
                except Exception:
                    pass
                try:
                    await db.execute("INSERT OR REPLACE INTO bot_settings (key, value) VALUES ('msk_timestamps_migrated', '1')")
                except Exception:
                    pass
                await db.commit()
                logger.info("Migrated legacy UTC timestamps to MSK (+3 hours) successfully.")

            # Create promo_codes table (exact case-sensitive code matching)
            await db.execute("""
                CREATE TABLE IF NOT EXISTS promo_codes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    code TEXT UNIQUE NOT NULL COLLATE BINARY,
                    promo_type TEXT NOT NULL,
                    reward_data TEXT NOT NULL,
                    max_activations INTEGER NOT NULL,
                    current_activations INTEGER DEFAULT 0,
                    expires_at TEXT NOT NULL,
                    is_active INTEGER DEFAULT 1,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # Ensure promo_activation_id in payments table
            try:
                await db.execute("ALTER TABLE payments ADD COLUMN promo_activation_id INTEGER")
            except Exception:
                pass

            # Create user_promo_activations table (tracks 24h window, usage, reminders)
            await db.execute("""
                CREATE TABLE IF NOT EXISTS user_promo_activations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    promo_code_id INTEGER NOT NULL,
                    promo_type TEXT NOT NULL,
                    discount_data TEXT,
                    activated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    expires_at TEXT,
                    is_used INTEGER DEFAULT 0,
                    reminder_sent INTEGER DEFAULT 0,
                    used_at TIMESTAMP,
                    payment_id TEXT,
                    FOREIGN KEY (promo_code_id) REFERENCES promo_codes (id),
                    FOREIGN KEY (user_id) REFERENCES users (user_id)
                )
            """)

            # Create admin_magic_tokens table for web dashboard authentication
            await db.execute("""
                CREATE TABLE IF NOT EXISTS admin_magic_tokens (
                    token TEXT PRIMARY KEY,
                    user_id INTEGER NOT NULL,
                    expires_at TEXT NOT NULL,
                    used INTEGER DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            await db.commit()
            logger.info("Database initialized successfully at %s", self.db_path)

    def _format_user_row(self, row: aiosqlite.Row) -> Dict[str, Any]:
        d = dict(row)
        paid = d.get("paid_balance") or 0
        gift = d.get("gift_balance") or 0
        ref_bal = float(d.get("referral_balance") or 0.0)
        d["paid_balance"] = paid
        d["gift_balance"] = gift
        d["total_balance"] = paid + gift
        d["balance"] = paid + gift
        d["referral_balance"] = round(ref_bal, 2)
        return d

    async def get_or_create_user(
        self,
        user_id: int,
        username: Optional[str] = None,
        first_name: Optional[str] = None,
        referred_by: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Fetch an existing user or insert a new one with initial credits."""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT * FROM users WHERE user_id = ?", (user_id,)
            ) as cursor:
                row = await cursor.fetchone()
                if row:
                    # Update username/first_name in case they changed
                    await db.execute(
                        "UPDATE users SET username = ?, first_name = ? WHERE user_id = ?",
                        (username, first_name, user_id),
                    )
                    await db.commit()
                    return self._format_user_row(row)

            # Insert new user with initial gift credits
            valid_referrer = (
                referred_by if referred_by and referred_by != user_id else None
            )
            now_str = get_msk_now().strftime("%Y-%m-%d %H:%M:%S")

            await db.execute(
                """
                INSERT INTO users (user_id, username, first_name, balance, paid_balance, gift_balance, referral_balance, referred_by, created_at)
                VALUES (?, ?, ?, ?, 0, ?, 0.0, ?, ?)
                """,
                (
                    user_id,
                    username,
                    first_name,
                    settings.initial_user_credits,
                    settings.initial_user_credits,
                    valid_referrer,
                    now_str,
                ),
            )
            await db.commit()

            async with db.execute(
                "SELECT * FROM users WHERE user_id = ?", (user_id,)
            ) as cursor:
                new_row = await cursor.fetchone()
                return self._format_user_row(new_row)

    async def get_user(self, user_id: int) -> Optional[Dict[str, Any]]:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT * FROM users WHERE user_id = ?", (user_id,)
            ) as cursor:
                row = await cursor.fetchone()
                return self._format_user_row(row) if row else None

    async def add_paid_balance(self, user_id: int, amount: int) -> int:
        """Adds to paid balance. Returns new total balance."""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """
                UPDATE users
                SET paid_balance = coalesce(paid_balance, 0) + ?,
                    balance = coalesce(balance, 0) + ?
                WHERE user_id = ?
                """,
                (amount, amount, user_id),
            )
            await db.commit()
            user = await self.get_user(user_id)
            return user["total_balance"] if user else 0

    async def add_gift_balance(self, user_id: int, amount: int) -> int:
        """Adds to gift/bonus balance (referrals, promos). Returns new total balance."""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """
                UPDATE users
                SET gift_balance = coalesce(gift_balance, 0) + ?,
                    balance = coalesce(balance, 0) + ?
                WHERE user_id = ?
                """,
                (amount, amount, user_id),
            )
            await db.commit()
            user = await self.get_user(user_id)
            return user["total_balance"] if user else 0

    async def add_referral_reward(self, user_id: int, earned_credits: float) -> Dict[str, Any]:
        """
        Adds fractional referral reward to user's referral_balance.
        If referral_balance reaches or exceeds 1.0, atomically transfers whole integer units
        to gift_balance (and total balance) and leaves the fractional remainder.
        Returns a dict:
        {
            "earned": float,
            "transferred": int,
            "referral_balance": float,
            "gift_balance": int,
            "total_balance": int
        }
        """
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT referral_balance, gift_balance, paid_balance FROM users WHERE user_id = ?",
                (user_id,),
            ) as cursor:
                row = await cursor.fetchone()
                if not row:
                    return {
                        "earned": earned_credits,
                        "transferred": 0,
                        "referral_balance": 0.0,
                        "gift_balance": 0,
                        "total_balance": 0,
                    }

                cur_ref = float(row["referral_balance"] or 0.0)
                cur_gift = int(row["gift_balance"] or 0)
                cur_paid = int(row["paid_balance"] or 0)

            total_ref = round(cur_ref + earned_credits, 2)
            transferred = int(total_ref)
            new_ref = round(total_ref - transferred, 2)
            new_gift = cur_gift + transferred
            new_total = cur_paid + new_gift

            await db.execute(
                """
                UPDATE users
                SET referral_balance = ?,
                    gift_balance = gift_balance + ?,
                    balance = balance + ?
                WHERE user_id = ?
                """,
                (new_ref, transferred, transferred, user_id),
            )
            await db.commit()

            return {
                "earned": earned_credits,
                "transferred": transferred,
                "referral_balance": new_ref,
                "gift_balance": new_gift,
                "total_balance": new_total,
            }

    async def consume_generation_credit(self, user_id: int, cost: int = 1) -> Optional[str]:
        """
        Deducts cost from balance atomically. Prioritizes gift_balance first, then paid_balance.
        Returns 'gift' if deducted from gift balance,
        'paid' if deducted from paid balance,
        or None if insufficient funds.
        """
        async with aiosqlite.connect(self.db_path) as db:
            # 1. Attempt atomic deduction from gift_balance
            cursor = await db.execute(
                """
                UPDATE users
                SET gift_balance = gift_balance - ?,
                    balance = max(0, coalesce(balance, 0) - ?)
                WHERE user_id = ? AND coalesce(gift_balance, 0) >= ?
                """,
                (cost, cost, user_id, cost),
            )
            if cursor.rowcount > 0:
                await db.commit()
                return "gift"

            # 2. Attempt atomic deduction from paid_balance
            cursor = await db.execute(
                """
                UPDATE users
                SET paid_balance = paid_balance - ?,
                    balance = max(0, coalesce(balance, 0) - ?)
                WHERE user_id = ? AND (coalesce(gift_balance, 0) + coalesce(paid_balance, 0)) >= ?
                """,
                (cost, cost, user_id, cost),
            )
            if cursor.rowcount > 0:
                await db.commit()
                return "paid"

            return None

    async def refund_generation_credit(
        self, user_id: int, balance_type: str = "gift", cost: int = 1
    ) -> None:
        """Refunds credit back to the appropriate balance (gift or paid)."""
        if balance_type == "paid":
            await self.add_paid_balance(user_id, cost)
        else:
            await self.add_gift_balance(user_id, cost)

    async def change_balance(self, user_id: int, delta: int) -> int:
        """Compatibility method for balance changes. Returns new total balance."""
        if delta >= 0:
            return await self.add_gift_balance(user_id, delta)
        else:
            await self.consume_generation_credit(user_id, abs(delta))
            user = await self.get_user(user_id)
            return user["total_balance"] if user else 0

    async def record_generation(
        self,
        user_id: int,
        task_id: str,
        prompt: str,
        artist: Optional[str] = None,
        genres: Optional[str] = None,
        instrumental: bool = False,
        lyrics: Optional[str] = None,
        status: str = "PENDING",
        error_message: Optional[str] = None,
        raw_response: Optional[str] = None,
        created_at: Optional[str] = None,
    ) -> None:
        if not created_at:
            created_at = get_msk_now().strftime("%Y-%m-%d %H:%M:%S")
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """
                INSERT INTO generations (
                    user_id, task_id, prompt, artist, genres,
                    instrumental, lyrics, status, error_message, raw_response, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    user_id, task_id, prompt, artist, genres,
                    int(instrumental), lyrics, status, error_message, raw_response, created_at
                ),
            )
            await db.commit()

    async def update_generation_status(
        self,
        task_id: str,
        status: str,
        audio_url: Optional[str] = None,
        duration: Optional[float] = None,
        error_message: Optional[str] = None,
        raw_response: Optional[str] = None,
        image_url: Optional[str] = None,
    ) -> None:
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """
                UPDATE generations
                SET status = ?,
                    audio_url = coalesce(?, audio_url),
                    duration = coalesce(?, duration),
                    error_message = coalesce(?, error_message),
                    raw_response = coalesce(?, raw_response),
                    image_url = coalesce(?, image_url)
                WHERE task_id = ?
                """,
                (status, audio_url, duration, error_message, raw_response, image_url, task_id),
            )
            await db.commit()

    async def mark_generation_pending_delivery(self, task_id: str) -> None:
        """Marks a successful generation as waiting for background delivery to Telegram."""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "UPDATE generations SET delivery_status = 'PENDING' WHERE task_id = ?",
                (task_id,),
            )
            await db.commit()

    async def mark_generation_delivered(self, task_id: str) -> None:
        """Marks generation as successfully delivered to the user in Telegram."""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "UPDATE generations SET delivery_status = 'DELIVERED' WHERE task_id = ?",
                (task_id,),
            )
            await db.commit()

    async def mark_generation_delivery_failed(self, task_id: str, reason: str = "") -> None:
        """Marks delivery as failed permanently (e.g. user blocked the bot)."""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "UPDATE generations SET delivery_status = 'FAILED', error_message = coalesce(error_message, ?) WHERE task_id = ?",
                (reason, task_id),
            )
            await db.commit()

    async def get_pending_deliveries(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Retrieves tracks that were generated by AI but not yet delivered to Telegram."""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                """
                SELECT id, user_id, task_id, prompt, artist, instrumental, lyrics,
                       status, audio_url, duration, created_at, genres, image_url, delivery_status
                FROM generations
                WHERE status = 'SUCCESS'
                  AND delivery_status = 'PENDING'
                  AND audio_url IS NOT NULL
                ORDER BY id ASC
                LIMIT ?
                """,
                (limit,),
            ) as cursor:
                rows = await cursor.fetchall()
                return [dict(r) for r in rows]

    async def get_user_stats(self, user_id: int) -> Dict[str, Any]:
        """Get statistics: total generations count, success count, referral count."""
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute(
                "SELECT COUNT(*) FROM generations WHERE user_id = ?", (user_id,)
            ) as cursor:
                total_gens = (await cursor.fetchone())[0]

            async with db.execute(
                "SELECT COUNT(*) FROM generations WHERE user_id = ? AND status = 'SUCCESS'",
                (user_id,),
            ) as cursor:
                success_gens = (await cursor.fetchone())[0]

            async with db.execute(
                "SELECT COUNT(*) FROM users WHERE referred_by = ?", (user_id,)
            ) as cursor:
                referrals_count = (await cursor.fetchone())[0]

            return {
                "total_generations": total_gens,
                "success_generations": success_gens,
                "referrals_count": referrals_count,
            }

    async def create_payment_record(
        self,
        payment_id: str,
        user_id: int,
        amount: float,
        credits: int,
        promo_activation_id: Optional[int] = None,
        provider: str = "yookassa",
        currency: str = "RUB",
    ) -> None:
        now_str = get_msk_now().strftime("%Y-%m-%d %H:%M:%S")
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """
                INSERT INTO payments (payment_id, user_id, amount, credits, status, promo_activation_id, provider, currency, created_at, updated_at)
                VALUES (?, ?, ?, ?, 'pending', ?, ?, ?, ?, ?)
                """,
                (payment_id, user_id, amount, credits, promo_activation_id, provider, currency, now_str, now_str),
            )
            await db.commit()

    async def get_payment_record(self, payment_id: str) -> Optional[Dict[str, Any]]:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT * FROM payments WHERE payment_id = ?", (payment_id,)
            ) as cursor:
                row = await cursor.fetchone()
                return dict(row) if row else None

    async def update_payment_telegram_message_id(self, payment_id: str, message_id: int) -> None:
        """Stores Telegram invoice message_id to allow safe deletion upon payment completion."""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "UPDATE payments SET telegram_message_id = ? WHERE payment_id = ?",
                (message_id, payment_id),
            )
            await db.commit()

    async def mark_payment_succeeded(self, payment_id: str) -> Optional[Dict[str, Any]]:
        """
        Marks payment as succeeded idempotently and atomically.
        Returns the payment row if it was changed to 'succeeded',
        or None if it was already processed before or not found.
        """
        now_str = get_msk_now().strftime("%Y-%m-%d %H:%M:%S")
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                """
                UPDATE payments
                SET status = 'succeeded', updated_at = ?
                WHERE payment_id = ? AND status != 'succeeded'
                """,
                (now_str, payment_id),
            )
            if cursor.rowcount == 0:
                return None

            await db.commit()

            async with db.execute(
                "SELECT * FROM payments WHERE payment_id = ?", (payment_id,)
            ) as select_cursor:
                updated_row = await select_cursor.fetchone()
                return dict(updated_row) if updated_row else None

    async def mark_payment_canceled(self, payment_id: str) -> None:
        now_str = get_msk_now().strftime("%Y-%m-%d %H:%M:%S")
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """
                UPDATE payments
                SET status = 'canceled', updated_at = ?
                WHERE payment_id = ?
                """,
                (now_str, payment_id),
            )
            await db.commit()

    async def get_pending_payments(self, limit: int = 50) -> list[Dict[str, Any]]:
        """Fetch recently created pending payments to check their status in background."""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                """
                SELECT * FROM payments
                WHERE status = 'pending'
                  AND created_at >= datetime('now', '+3 hours', '-2 hours')
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (limit,),
            ) as cursor:
                rows = await cursor.fetchall()
                return [dict(r) for r in rows]

    async def cleanup_stale_payments(self, max_age_hours: int = 2) -> int:
        """Marks pending payments older than max_age_hours as canceled."""
        now_str = get_msk_now().strftime("%Y-%m-%d %H:%M:%S")
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                f"""
                UPDATE payments
                SET status = 'canceled', updated_at = ?
                WHERE status = 'pending'
                  AND created_at <= datetime('now', '+3 hours', '-{max_age_hours} hours')
                """,
                (now_str,)
            )
            await db.commit()
            return cursor.rowcount

    async def get_user_pending_count(self, user_id: int, max_age_minutes: int = 15) -> int:
        """Returns the number of active pending payments created by user in the last N minutes."""
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute(
                f"""
                SELECT COUNT(*) FROM payments
                WHERE user_id = ?
                  AND status = 'pending'
                  AND created_at >= datetime('now', '+3 hours', '-{max_age_minutes} minutes')
                """,
                (user_id,),
            ) as cursor:
                row = await cursor.fetchone()
                return row[0] if row else 0


    async def get_all_tariffs(self) -> list[Dict[str, Any]]:
        """Fetch all pricing packages from database."""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute("SELECT * FROM tariffs ORDER BY credits ASC") as cursor:
                rows = await cursor.fetchall()
                return [dict(r) for r in rows]

    async def get_tariff(self, tariff_id: str) -> Optional[Dict[str, Any]]:
        """Fetch a specific tariff package by id."""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT * FROM tariffs WHERE id = ?", (tariff_id,)
            ) as cursor:
                row = await cursor.fetchone()
                return dict(row) if row else None

    async def update_tariff_price(self, tariff_id: str, new_price: float) -> bool:
        """Update price and recalculate per-track badge for a specific tariff."""
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute("SELECT credits FROM tariffs WHERE id = ?", (tariff_id,)) as cursor:
                row = await cursor.fetchone()
                cr = row[0] if row else 1

            new_badge = format_per_track_badge(new_price, cr)
            await db.execute(
                "UPDATE tariffs SET price = ?, badge = ? WHERE id = ?",
                (new_price, new_badge, tariff_id),
            )
            await db.commit()
            return True

    async def get_all_user_ids(self) -> list[int]:
        """Fetch all user Telegram IDs for broadcast."""
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute("SELECT user_id FROM users") as cursor:
                rows = await cursor.fetchall()
                return [r[0] for r in rows]

    async def get_buyers_user_ids(self) -> list[int]:
        """Fetch Telegram IDs of users who made at least one successful purchase."""
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute("""
                SELECT DISTINCT p.user_id
                FROM payments p
                JOIN users u ON p.user_id = u.user_id
                WHERE p.status = 'succeeded'
            """) as cursor:
                rows = await cursor.fetchall()
                return [r[0] for r in rows]

    async def get_system_stats(self) -> Dict[str, Any]:
        """Calculates system-wide metrics for the admin panel."""
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute("SELECT COUNT(*) FROM users") as c:
                users_count = (await c.fetchone())[0]

            async with db.execute("SELECT COUNT(*) FROM generations") as c:
                total_gens = (await c.fetchone())[0]

            async with db.execute(
                "SELECT COUNT(*) FROM generations WHERE status = 'SUCCESS'"
            ) as c:
                success_gens = (await c.fetchone())[0]

            async with db.execute(
                "SELECT COUNT(*), coalesce(SUM(amount), 0) FROM payments WHERE status = 'succeeded'"
            ) as c:
                pay_row = await c.fetchone()
                payments_count = pay_row[0]
                revenue = pay_row[1]

            return {
                "users_count": users_count,
                "total_generations": total_gens,
                "success_generations": success_gens,
                "payments_count": payments_count,
                "revenue_rub": float(revenue),
            }

    # ---------------------------------------------------------
    # ARTISTS MANAGEMENT (DYNAMIC DB)
    # ---------------------------------------------------------
    async def get_popular_artists(self, active_only: bool = True) -> list[Dict[str, Any]]:
        """Fetch all artists designated for the primary 24-button grid."""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            query = "SELECT * FROM artists WHERE is_popular = 1"
            if active_only:
                query += " AND is_active = 1"
            query += " ORDER BY display_order ASC, id ASC"
            async with db.execute(query) as cursor:
                rows = await cursor.fetchall()
                return [_format_artist_row(r) for r in rows]

    async def get_extended_artists(self, active_only: bool = True) -> list[Dict[str, Any]]:
        """Fetch extended artists (shown in 'All artists' list)."""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            query = "SELECT * FROM artists WHERE is_popular = 0"
            if active_only:
                query += " AND is_active = 1"
            query += " ORDER BY display_order ASC, id ASC"
            async with db.execute(query) as cursor:
                rows = await cursor.fetchall()
                return [_format_artist_row(r) for r in rows]

    async def get_all_artists(self, active_only: bool = True) -> list[Dict[str, Any]]:
        """Fetch all active artists (popular first, then extended)."""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            query = "SELECT * FROM artists"
            if active_only:
                query += " WHERE is_active = 1"
            query += " ORDER BY is_popular DESC, display_order ASC, id ASC"
            async with db.execute(query) as cursor:
                rows = await cursor.fetchall()
                return [_format_artist_row(r) for r in rows]

    async def get_artists_by_tab(self, tab: str = "popular") -> list[Dict[str, Any]]:
        """Fetch artists by tab ('popular' or 'extended') for admin management."""
        is_pop = 1 if tab == "popular" else 0
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT * FROM artists WHERE is_popular = ? AND is_active = 1 ORDER BY display_order ASC, id ASC",
                (is_pop,),
            ) as cursor:
                rows = await cursor.fetchall()
                return [_format_artist_row(r) for r in rows]

    async def get_artist_by_id(self, artist_id: str) -> Optional[Dict[str, Any]]:
        """Fetch a specific artist by ID."""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT * FROM artists WHERE id = ?", (artist_id,)
            ) as cursor:
                row = await cursor.fetchone()
                return _format_artist_row(row) if row else None

    async def find_artist_by_name(self, query: str) -> Optional[Dict[str, Any]]:
        """Search artist by ID, name, or alias (case-insensitive)."""
        q = query.strip().lower()
        if not q:
            return None
        all_artists = await self.get_all_artists(active_only=True)
        # Exact match
        for a in all_artists:
            if q == a["id"].lower() or q == a["name"].lower():
                return a
            for alias in a.get("aliases", []):
                if q == alias.lower():
                    return a
        # Partial match
        for a in all_artists:
            if q in a["name"].lower() or any(q in alias.lower() for alias in a.get("aliases", [])):
                return a
        return None

    async def add_artist(
        self,
        name: str,
        style: str,
        aliases: Optional[list[str]] = None,
        is_popular: bool = True,
        artist_id: Optional[str] = None,
    ) -> str:
        """Create a new artist with auto-generated slug and sequential display_order."""
        if not artist_id:
            base_slug = slugify_artist(name)
            artist_id = base_slug

        aliases_json = json.dumps(aliases or [], ensure_ascii=False)
        pop_int = 1 if is_popular else 0

        async with aiosqlite.connect(self.db_path) as db:
            # Check collision
            async with db.execute("SELECT COUNT(*) FROM artists WHERE id = ?", (artist_id,)) as cursor:
                if (await cursor.fetchone())[0] > 0:
                    artist_id = f"{artist_id}_{int(datetime.utcnow().timestamp())}"

            # Next display order for this popularity group
            async with db.execute(
                "SELECT COALESCE(MAX(display_order), 0) FROM artists WHERE is_popular = ?",
                (pop_int,),
            ) as cursor:
                max_order = (await cursor.fetchone())[0]
                new_order = max_order + 1

            await db.execute(
                """
                INSERT INTO artists (id, name, style, aliases, is_popular, display_order, is_active)
                VALUES (?, ?, ?, ?, ?, ?, 1)
                """,
                (artist_id, name.strip(), style.strip(), aliases_json, pop_int, new_order),
            )
            await db.commit()
            logger.info("Added artist '%s' (id=%s, popular=%s, order=%s)", name, artist_id, pop_int, new_order)
            return artist_id

    async def update_artist(self, artist_id: str, **kwargs) -> bool:
        """Update arbitrary artist fields (name, style, aliases, is_popular, is_active)."""
        if not kwargs:
            return False
        fields = []
        values = []
        for k, v in kwargs.items():
            if k == "aliases" and isinstance(v, list):
                v = json.dumps(v, ensure_ascii=False)
            elif k == "is_popular":
                v = 1 if v else 0
            elif k == "is_active":
                v = 1 if v else 0
            fields.append(f"{k} = ?")
            values.append(v)
        values.append(artist_id)
        sql = f"UPDATE artists SET {', '.join(fields)} WHERE id = ?"
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(sql, tuple(values))
            await db.commit()
            return True

    async def swap_artist_order(self, artist_id: str, direction: str) -> bool:
        """
        Swaps the display_order of an artist with the adjacent artist in the same popularity group.
        direction: 'up' or 'down'
        """
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT id, is_popular, display_order FROM artists WHERE id = ?", (artist_id,)
            ) as cursor:
                curr = await cursor.fetchone()
                if not curr:
                    return False

            pop = curr["is_popular"]
            order = curr["display_order"]

            if direction == "up":
                async with db.execute(
                    """
                    SELECT id, display_order FROM artists
                    WHERE is_popular = ? AND is_active = 1 AND display_order < ?
                    ORDER BY display_order DESC, id DESC LIMIT 1
                    """,
                    (pop, order),
                ) as cursor:
                    neighbor = await cursor.fetchone()
            else:
                async with db.execute(
                    """
                    SELECT id, display_order FROM artists
                    WHERE is_popular = ? AND is_active = 1 AND display_order > ?
                    ORDER BY display_order ASC, id ASC LIMIT 1
                    """,
                    (pop, order),
                ) as cursor:
                    neighbor = await cursor.fetchone()

            if not neighbor:
                return False

            neigh_id = neighbor["id"]
            neigh_order = neighbor["display_order"]

            if order == neigh_order:
                if direction == "up":
                    order += 1
                else:
                    neigh_order += 1

            await db.execute("UPDATE artists SET display_order = ? WHERE id = ?", (neigh_order, artist_id))
            await db.execute("UPDATE artists SET display_order = ? WHERE id = ?", (order, neigh_id))
            await db.commit()
            return True

    async def delete_artist(self, artist_id: str) -> bool:
        """Delete an artist from the database."""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("DELETE FROM artists WHERE id = ?", (artist_id,))
            await db.commit()
            return True

    # ---------------------------------------------------------
    # BOT SETTINGS & MANDATORY SUBSCRIPTION
    # ---------------------------------------------------------
    async def get_setting(self, key: str, default: Optional[str] = None) -> Optional[str]:
        """Fetch a value from bot_settings by key."""
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute(
                "SELECT value FROM bot_settings WHERE key = ?", (key,)
            ) as cursor:
                row = await cursor.fetchone()
                return row[0] if row and row[0] is not None else default

    async def set_setting(self, key: str, value: str) -> None:
        """Store or update a value in bot_settings."""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """
                INSERT INTO bot_settings (key, value, updated_at)
                VALUES (?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = CURRENT_TIMESTAMP
                """,
                (key, str(value)),
            )
            await db.commit()

    async def is_subscription_check_enabled(self) -> bool:
        """Returns True if mandatory channel subscription check is active."""
        val = await self.get_setting("sub_check_enabled", default="0")
        return val == "1"

    async def set_subscription_check_enabled(self, enabled: bool) -> None:
        """Enable or disable mandatory channel subscription check."""
        await self.set_setting("sub_check_enabled", "1" if enabled else "0")

    async def get_required_channel(self) -> Dict[str, str]:
        """Returns configured channel identifier and link (DB setting or config fallback)."""
        channel = await self.get_setting("required_channel") or getattr(settings, "required_channel", "")
        url = await self.get_setting("required_channel_url") or getattr(settings, "required_channel_url", "")
        if not url and channel:
            c_clean = channel.strip().lstrip("@")
            if not c_clean.startswith("-"):
                url = f"https://t.me/{c_clean}"
        return {"channel": channel.strip(), "url": url.strip()}

    async def set_required_channel(self, channel: str, url: Optional[str] = None) -> None:
        """Save required channel identifier and public/invite link."""
        ch_clean = channel.strip()
        await self.set_setting("required_channel", ch_clean)
        if url and url.strip():
            await self.set_setting("required_channel_url", url.strip())
        elif ch_clean:
            c_slug = ch_clean.lstrip("@")
            if not c_slug.startswith("-"):
                await self.set_setting("required_channel_url", f"https://t.me/{c_slug}")

    # ---------------------------------------------------------
    # PROMO CODES MANAGEMENT
    # ---------------------------------------------------------
    async def create_promo_code(
        self,
        code: str,
        promo_type: str,
        reward_data: Dict[str, Any],
        max_activations: int,
        expires_at: Any,
    ) -> int:
        """
        Creates a new promo code.
        promo_type: 'discount_fixed', 'discount_custom', or 'credits'
        reward_data: dict (e.g. {'percent': 20} or {'packs': {'pack_5': 0, ...}} or {'credits': 15})
        expires_at: datetime or str in MSK timezone
        """
        if isinstance(expires_at, datetime):
            exp_str = expires_at.strftime("%Y-%m-%d %H:%M:%S")
        else:
            exp_str = str(expires_at).strip()
        reward_json = json.dumps(reward_data, ensure_ascii=False)
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                """
                INSERT INTO promo_codes (code, promo_type, reward_data, max_activations, current_activations, expires_at, is_active)
                VALUES (?, ?, ?, ?, 0, ?, 1)
                """,
                (code.strip(), promo_type, reward_json, max_activations, exp_str),
            )
            await db.commit()
            return cursor.lastrowid

    async def get_promo_code_by_code(self, code: str) -> Optional[Dict[str, Any]]:
        """Finds promo code with exact case-sensitive match (COLLATE BINARY)."""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT * FROM promo_codes WHERE code = ?", (code.strip(),)
            ) as cursor:
                row = await cursor.fetchone()
                if not row:
                    return None
                d = dict(row)
                try:
                    d["reward_data"] = json.loads(d["reward_data"])
                except Exception:
                    pass
                return d

    async def get_promo_code_by_id(self, promo_id: int) -> Optional[Dict[str, Any]]:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT * FROM promo_codes WHERE id = ?", (promo_id,)
            ) as cursor:
                row = await cursor.fetchone()
                if not row:
                    return None
                d = dict(row)
                try:
                    d["reward_data"] = json.loads(d["reward_data"])
                except Exception:
                    pass
                return d

    async def get_all_promo_codes(self, only_active: bool = False) -> List[Dict[str, Any]]:
        """Returns promo codes sorted by id DESC."""
        query = (
            "SELECT * FROM promo_codes WHERE is_active = 1 ORDER BY id DESC"
            if only_active
            else "SELECT * FROM promo_codes ORDER BY id DESC"
        )
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(query) as cursor:
                rows = await cursor.fetchall()
                res = []
                for r in rows:
                    d = dict(r)
                    try:
                        d["reward_data"] = json.loads(d["reward_data"])
                    except Exception:
                        pass
                    res.append(d)
                return res

    async def deactivate_promo_code(self, promo_id: int) -> bool:
        """Deactivates a promo code so no new users can activate it."""
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                "UPDATE promo_codes SET is_active = 0 WHERE id = ?", (promo_id,)
            )
            await db.commit()
            return cursor.rowcount > 0

    async def has_user_activated_promo(self, user_id: int, promo_code_id: int) -> bool:
        """Checks if user has ever activated this specific promo code."""
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute(
                "SELECT 1 FROM user_promo_activations WHERE user_id = ? AND promo_code_id = ? LIMIT 1",
                (user_id, promo_code_id),
            ) as cursor:
                return (await cursor.fetchone()) is not None

    async def activate_promo_code_for_user(
        self, user_id: int, promo: Dict[str, Any]
    ) -> Tuple[bool, str, Optional[Dict[str, Any]]]:
        """
        Attempts to activate promo code for user.
        Returns:
            (success: bool, status_code: str, data: Optional[Dict])
        """
        now = get_msk_now()
        now_str = now.strftime("%Y-%m-%d %H:%M:%S")
        promo_id = promo["id"]

        # Check if already activated by this user
        if await self.has_user_activated_promo(user_id, promo_id):
            return False, "already_used", None

        # Check if user already has an active discount
        if promo["promo_type"].startswith("discount"):
            active_disc = await self.get_user_active_discount(user_id)
            if active_disc:
                return False, "already_has_discount", active_disc

        # Attempt atomic reservation: increment current_activations if valid
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                """
                UPDATE promo_codes
                SET current_activations = current_activations + 1
                WHERE id = ?
                  AND is_active = 1
                  AND current_activations < max_activations
                  AND expires_at > ?
                """,
                (promo_id, now_str),
            )
            if cursor.rowcount == 0:
                # Determine specific failure reason
                async with db.execute(
                    "SELECT is_active, current_activations, max_activations, expires_at FROM promo_codes WHERE id = ?",
                    (promo_id,),
                ) as check_cur:
                    check_row = await check_cur.fetchone()
                    if not check_row:
                        return False, "not_found", None
                    if not check_row[0]:
                        return False, "inactive", None
                    if check_row[1] >= check_row[2]:
                        return False, "limit_reached", None
                    if check_row[3] <= now_str:
                        return False, "expired", None
                    return False, "failed", None

            await db.commit()

        # Promo activation slot secured! Now process reward
        promo_type = promo["promo_type"]
        reward_data = promo["reward_data"]

        if promo_type == "credits":
            credits_to_give = int(reward_data.get("credits", 0))
            await self.add_gift_balance(user_id, credits_to_give)

            async with aiosqlite.connect(self.db_path) as db:
                await db.execute(
                    """
                    INSERT INTO user_promo_activations (user_id, promo_code_id, promo_type, discount_data, expires_at, is_used, used_at)
                    VALUES (?, ?, ?, ?, NULL, 1, CURRENT_TIMESTAMP)
                    """,
                    (user_id, promo_id, promo_type, json.dumps(reward_data, ensure_ascii=False)),
                )
                await db.commit()
            return True, "credits_success", {"credits": credits_to_give}

        else:
            # Discount promo code: grants 24 hours of active discount
            exp_24h = (now + timedelta(hours=24)).strftime("%Y-%m-%d %H:%M:%S")
            async with aiosqlite.connect(self.db_path) as db:
                cursor = await db.execute(
                    """
                    INSERT INTO user_promo_activations (user_id, promo_code_id, promo_type, discount_data, expires_at, is_used, reminder_sent)
                    VALUES (?, ?, ?, ?, ?, 0, 0)
                    """,
                    (user_id, promo_id, promo_type, json.dumps(reward_data, ensure_ascii=False), exp_24h),
                )
                await db.commit()
                activation_id = cursor.lastrowid

            return True, "discount_success", {
                "activation_id": activation_id,
                "promo_type": promo_type,
                "reward_data": reward_data,
                "expires_at": exp_24h,
            }

    async def replace_active_discount_with_promo(
        self, user_id: int, promo: Dict[str, Any]
    ) -> Tuple[bool, str, Optional[Dict[str, Any]]]:
        """Supersedes user's existing active discount and activates the new one."""
        await self.supersede_user_active_discount(user_id)
        return await self.activate_promo_code_for_user(user_id, promo)

    async def supersede_user_active_discount(self, user_id: int) -> None:
        """Marks any currently active discounts for user as superseded (is_used = 2)."""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "UPDATE user_promo_activations SET is_used = 2 WHERE user_id = ? AND is_used = 0",
                (user_id,),
            )
            await db.commit()

    async def get_user_active_discount(self, user_id: int) -> Optional[Dict[str, Any]]:
        """
        Returns active discount for user if valid and not expired.
        Includes parsed discount_data, promo code string and calculated remaining time.
        """
        now = get_msk_now()
        now_str = now.strftime("%Y-%m-%d %H:%M:%S")

        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                """
                SELECT a.*, p.code as code, p.promo_type as promo_code_type
                FROM user_promo_activations a
                LEFT JOIN promo_codes p ON a.promo_code_id = p.id
                WHERE a.user_id = ? AND a.is_used = 0 AND a.expires_at > ?
                ORDER BY a.id DESC LIMIT 1
                """,
                (user_id, now_str),
            ) as cursor:
                row = await cursor.fetchone()
                if not row:
                    return None
                d = dict(row)
                try:
                    d["discount_data"] = json.loads(d["discount_data"])
                except Exception:
                    pass

                # Calculate remaining time
                try:
                    exp_dt = datetime.strptime(d["expires_at"], "%Y-%m-%d %H:%M:%S").replace(tzinfo=MSK_TZ)
                    diff = exp_dt - now
                    total_sec = max(0, int(diff.total_seconds()))
                    hrs = total_sec // 3600
                    mins = (total_sec % 3600) // 60
                    d["remaining_seconds"] = total_sec
                    d["remaining_time_str"] = f"{hrs} ч. {mins} мин." if hrs > 0 else f"{mins} мин."
                except Exception:
                    d["remaining_seconds"] = 0
                    d["remaining_time_str"] = ""

                return d

    async def mark_user_promo_used(self, activation_id: int, payment_id: str) -> None:
        """Marks a discount activation as consumed upon completed payment."""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """
                UPDATE user_promo_activations
                SET is_used = 1, used_at = CURRENT_TIMESTAMP, payment_id = ?
                WHERE id = ? AND is_used = 0
                """,
                (payment_id, activation_id),
            )
            await db.commit()

    async def get_pending_discount_reminders(self) -> List[Dict[str, Any]]:
        """
        Finds discount activations where remaining time is <= 2 hours (<= 7200 sec),
        expires_at > now, is_used == 0, and reminder_sent == 0.
        """
        now = get_msk_now()
        now_str = now.strftime("%Y-%m-%d %H:%M:%S")
        two_hours_later = (now + timedelta(hours=2)).strftime("%Y-%m-%d %H:%M:%S")

        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                """
                SELECT a.*, p.code as code, p.promo_type as promo_code_type
                FROM user_promo_activations a
                LEFT JOIN promo_codes p ON a.promo_code_id = p.id
                WHERE a.is_used = 0
                  AND a.reminder_sent = 0
                  AND a.expires_at > ?
                  AND a.expires_at <= ?
                """,
                (now_str, two_hours_later),
            ) as cursor:
                rows = await cursor.fetchall()
                res = []
                for r in rows:
                    d = dict(r)
                    try:
                        d["discount_data"] = json.loads(d["discount_data"])
                    except Exception:
                        pass
                    res.append(d)
                return res

    async def mark_discount_reminder_sent(self, activation_id: int) -> None:
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "UPDATE user_promo_activations SET reminder_sent = 1 WHERE id = ?",
                (activation_id,),
            )
            await db.commit()

    async def cancel_user_pending_payments(self, user_id: int) -> None:
        """Cancels any previous pending payments of user so only 1 active payment attempt exists."""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "UPDATE payments SET status = 'canceled', updated_at = CURRENT_TIMESTAMP WHERE user_id = ? AND status = 'pending'",
                (user_id,),
            )
            await db.commit()

    # ---------------------------------------------------------
    # WEB DASHBOARD & MAGIC LINK AUTHENTICATION
    # ---------------------------------------------------------
    async def create_magic_token(self, user_id: int, ttl_seconds: int = 600) -> str:
        """Generate and store a single-use magic login token for admin dashboard."""
        token = secrets.token_urlsafe(32)
        now = get_msk_now()
        expires_at = (now + timedelta(seconds=ttl_seconds)).strftime("%Y-%m-%d %H:%M:%S")
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "INSERT INTO admin_magic_tokens (token, user_id, expires_at, used) VALUES (?, ?, ?, 0)",
                (token, user_id, expires_at),
            )
            await db.commit()
        return token

    async def validate_and_consume_magic_token(self, token: str) -> Optional[int]:
        """Validate magic token and consume it. Returns user_id if valid, else None."""
        if not token:
            return None
        now_str = get_msk_now().strftime("%Y-%m-%d %H:%M:%S")
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute(
                "SELECT user_id, expires_at, used FROM admin_magic_tokens WHERE token = ?",
                (token,),
            ) as cursor:
                row = await cursor.fetchone()
                if not row:
                    return None
                user_id, expires_at, used = row[0], row[1], row[2]
                if used != 0 or expires_at < now_str:
                    return None

            await db.execute(
                "UPDATE admin_magic_tokens SET used = 1 WHERE token = ?",
                (token,),
            )
            await db.commit()
            return user_id

    async def get_detailed_dashboard_stats(self) -> Dict[str, Any]:
        """Returns aggregated KPI metrics for the web dashboard."""
        now = get_msk_now()
        today_date = now.strftime("%Y-%m-%d")
        dt_7d = (now - timedelta(days=7)).strftime("%Y-%m-%d %H:%M:%S")
        dt_30d = (now - timedelta(days=30)).strftime("%Y-%m-%d %H:%M:%S")

        async with aiosqlite.connect(self.db_path) as db:
            # Users
            async with db.execute("SELECT COUNT(*) FROM users") as c:
                users_total = (await c.fetchone())[0]
            async with db.execute("SELECT COUNT(*) FROM users WHERE date(created_at) = ?", (today_date,)) as c:
                users_today = (await c.fetchone())[0]

            # Payments
            async with db.execute("SELECT COUNT(*), coalesce(SUM(amount), 0) FROM payments WHERE status = 'succeeded'") as c:
                row = await c.fetchone()
                pay_total_count, rev_total = row[0], float(row[1])

            async with db.execute(
                "SELECT COUNT(*), coalesce(SUM(amount), 0) FROM payments WHERE status = 'succeeded' AND date(created_at) = ?",
                (today_date,),
            ) as c:
                row = await c.fetchone()
                pay_today_count, rev_today = row[0], float(row[1])

            async with db.execute(
                "SELECT COUNT(*), coalesce(SUM(amount), 0) FROM payments WHERE status = 'succeeded' AND created_at >= ?",
                (dt_7d,),
            ) as c:
                row = await c.fetchone()
                pay_7d_count, rev_7d = row[0], float(row[1])

            async with db.execute(
                "SELECT COUNT(*), coalesce(SUM(amount), 0) FROM payments WHERE status = 'succeeded' AND created_at >= ?",
                (dt_30d,),
            ) as c:
                row = await c.fetchone()
                pay_30d_count, rev_30d = row[0], float(row[1])

            # Generations
            async with db.execute("SELECT COUNT(*) FROM generations") as c:
                gens_total = (await c.fetchone())[0]
            async with db.execute("SELECT COUNT(*) FROM generations WHERE status = 'SUCCESS'") as c:
                gens_success = (await c.fetchone())[0]
            async with db.execute("SELECT COUNT(*) FROM generations WHERE status = 'FAILURE'") as c:
                gens_failure = (await c.fetchone())[0]
            async with db.execute("SELECT COUNT(*) FROM generations WHERE date(created_at) = ?", (today_date,)) as c:
                gens_today = (await c.fetchone())[0]

            # Buyers (unique paying users)
            async with db.execute("SELECT COUNT(DISTINCT user_id) FROM payments WHERE status = 'succeeded'") as c:
                buyers_total = (await c.fetchone())[0]

            avg_check = round(rev_total / pay_total_count, 1) if pay_total_count > 0 else 0.0
            conversion_rate = round((buyers_total / users_total * 100), 1) if users_total > 0 else 0.0

            return {
                "users_total": users_total,
                "users_today": users_today,
                "buyers_total": buyers_total,
                "conversion_rate": conversion_rate,
                "revenue_total": rev_total,
                "revenue_today": rev_today,
                "revenue_7d": rev_7d,
                "revenue_30d": rev_30d,
                "payments_count_total": pay_total_count,
                "payments_count_today": pay_today_count,
                "payments_count_7d": pay_7d_count,
                "payments_count_30d": pay_30d_count,
                "avg_check": avg_check,
                "generations_total": gens_total,
                "generations_success": gens_success,
                "generations_failure": gens_failure,
                "generations_today": gens_today,
            }

    async def get_daily_chart_data(self, days: int = 14) -> Dict[str, Any]:
        """Returns daily series for Chart.js (revenue and track generations)."""
        now = get_msk_now()
        dates_list = [(now - timedelta(days=i)).strftime("%Y-%m-%d") for i in range(days - 1, -1, -1)]
        labels = [(now - timedelta(days=i)).strftime("%d.%m") for i in range(days - 1, -1, -1)]
        dt_start = (now - timedelta(days=days)).strftime("%Y-%m-%d %H:%M:%S")

        revenue_map = {d: 0.0 for d in dates_list}
        gens_map = {d: 0 for d in dates_list}

        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute(
                """
                SELECT date(created_at) as dt, coalesce(SUM(amount), 0)
                FROM payments
                WHERE status = 'succeeded' AND created_at >= ?
                GROUP BY dt
                """,
                (dt_start,),
            ) as cursor:
                async for dt, rev in cursor:
                    if dt in revenue_map:
                        revenue_map[dt] = float(rev)

            async with db.execute(
                """
                SELECT date(created_at) as dt, COUNT(*)
                FROM generations
                WHERE created_at >= ?
                GROUP BY dt
                """,
                (dt_start,),
            ) as cursor:
                async for dt, cnt in cursor:
                    if dt in gens_map:
                        gens_map[dt] = int(cnt)

        return {
            "labels": labels,
            "dates": dates_list,
            "revenue": [revenue_map[d] for d in dates_list],
            "generations": [gens_map[d] for d in dates_list],
        }

    async def get_all_payments_detailed(self, limit: int = 1000) -> List[Dict[str, Any]]:
        """Fetch all payments joined with user and promo info for web table."""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                """
                SELECT
                    p.id, p.payment_id, p.user_id, p.amount, p.credits, p.status, p.created_at, p.updated_at,
                    p.provider, p.currency,
                    u.username, u.first_name,
                    pr.code as promo_code
                FROM payments p
                LEFT JOIN users u ON p.user_id = u.user_id
                LEFT JOIN user_promo_activations pa ON p.promo_activation_id = pa.id
                LEFT JOIN promo_codes pr ON pa.promo_code_id = pr.id
                ORDER BY p.id DESC
                LIMIT ?
                """,
                (limit,),
            ) as cursor:
                rows = await cursor.fetchall()
                return [dict(r) for r in rows]

    async def get_all_generations_detailed(self, limit: int = 1000) -> List[Dict[str, Any]]:
        """Fetch generations history for web table with preview audio url."""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                """
                SELECT
                    g.id, g.task_id, g.user_id, g.prompt, g.artist, g.genres,
                    g.instrumental, g.lyrics, g.status, g.audio_url, g.duration, g.created_at,
                    g.error_message, g.raw_response, g.delivery_status, g.image_url,
                    u.username, u.first_name
                FROM generations g
                LEFT JOIN users u ON g.user_id = u.user_id
                ORDER BY g.id DESC
                LIMIT ?
                """,
                (limit,),
            ) as cursor:
                rows = await cursor.fetchall()
                return [dict(r) for r in rows]

    async def get_all_users_detailed(self, limit: int = 1000) -> List[Dict[str, Any]]:
        """Fetch users table with balances and total spends for web dashboard."""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                """
                SELECT
                    u.user_id, u.username, u.first_name, u.paid_balance, u.gift_balance,
                    u.referral_balance, u.referred_by, u.created_at,
                    coalesce(SUM(case when p.status = 'succeeded' then p.amount else 0 end), 0) as total_spent,
                    coalesce(SUM(case when p.status = 'succeeded' then 1 else 0 end), 0) as successful_orders,
                    (SELECT count(*) FROM generations g WHERE g.user_id = u.user_id) as total_generations
                FROM users u
                LEFT JOIN payments p ON u.user_id = p.user_id
                GROUP BY u.user_id
                ORDER BY total_spent DESC, u.created_at DESC
                LIMIT ?
                """,
                (limit,),
            ) as cursor:
                rows = await cursor.fetchall()
                res = []
                for r in rows:
                    d = dict(r)
                    d["total_balance"] = (d.get("paid_balance") or 0) + (d.get("gift_balance") or 0)
                    res.append(d)
                return res

    async def record_uptime_check(
        self,
        service: str,
        status: str,
        latency_ms: float = 0.0,
        error_message: Optional[str] = None,
    ) -> None:
        """Records an uptime health check result for bot or treblo_api."""
        if service in ("treblo", "treblo_api"):
            service = "treblo_api"
        now_str = get_msk_now().strftime("%Y-%m-%d %H:%M:%S")
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """
                INSERT INTO uptime_logs (service, status, latency_ms, error_message, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (service, status.upper(), latency_ms, error_message, now_str),
            )
            await db.commit()

    async def get_uptime_metrics(self, hours: int = 24) -> Dict[str, Any]:
        """
        Calculates uptime and latency metrics for Bot and Treblo API over the last `hours`.
        Returns summary metrics and hourly chart data.
        """
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row

            # 1. Bot Uptime (last 24 hours)
            async with db.execute(
                """
                SELECT
                    count(*) as total,
                    coalesce(sum(case when status = 'UP' then 1 else 0 end), 0) as up_count
                FROM uptime_logs
                WHERE service = 'bot' AND created_at >= datetime('now', '+3 hours', ? || ' hours')
                """,
                (f"-{hours}",),
            ) as cursor:
                row = await cursor.fetchone()
                bot_total = row["total"] if row else 0
                bot_up = row["up_count"] if row else 0
                bot_pct = round((bot_up / bot_total * 100), 1) if bot_total > 0 else 100.0

            # 2. Treblo API Uptime & Latency (last 24 hours)
            async with db.execute(
                """
                SELECT
                    count(*) as total,
                    coalesce(sum(case when status = 'UP' then 1 else 0 end), 0) as up_count,
                    coalesce(avg(case when status = 'UP' then latency_ms else null end), 0.0) as avg_latency
                FROM uptime_logs
                WHERE service IN ('treblo_api', 'treblo') AND created_at >= datetime('now', '+3 hours', ? || ' hours')
                """,
                (f"-{hours}",),
            ) as cursor:
                row = await cursor.fetchone()
                treblo_total = row["total"] if row else 0
                treblo_up = row["up_count"] if row else 0
                treblo_pct = round((treblo_up / treblo_total * 100), 1) if treblo_total > 0 else 100.0
                treblo_avg_lat = round(row["avg_latency"] if row else 0.0, 1)

            # 3. Treblo 7-day Uptime
            async with db.execute(
                """
                SELECT
                    count(*) as total,
                    coalesce(sum(case when status = 'UP' then 1 else 0 end), 0) as up_count
                FROM uptime_logs
                WHERE service IN ('treblo_api', 'treblo') AND created_at >= datetime('now', '+3 hours', '-7 days')
                """
            ) as cursor:
                row = await cursor.fetchone()
                t7_total = row["total"] if row else 0
                t7_up = row["up_count"] if row else 0
                treblo_7d_pct = round((t7_up / t7_total * 100), 1) if t7_total > 0 else 100.0

            # 4. Latest check for Treblo API
            async with db.execute(
                """
                SELECT status, latency_ms, error_message, created_at
                FROM uptime_logs
                WHERE service IN ('treblo_api', 'treblo')
                ORDER BY id DESC LIMIT 1
                """
            ) as cursor:
                last_row = await cursor.fetchone()
                if last_row:
                    treblo_current_status = last_row["status"]
                    treblo_current_latency = round(last_row["latency_ms"], 1)
                    treblo_last_error = last_row["error_message"]
                    treblo_last_check = last_row["created_at"]
                else:
                    treblo_current_status = "UP"
                    treblo_current_latency = 0.0
                    treblo_last_error = None
                    treblo_last_check = None

            # 5. Hourly series for Chart.js (last 24 hours)
            async with db.execute(
                """
                SELECT
                    strftime('%H:00', created_at) as hour_label,
                    strftime('%Y-%m-%d %H', created_at) as hour_key,
                    service,
                    count(*) as total_checks,
                    coalesce(sum(case when status = 'UP' then 1 else 0 end), 0) as up_checks,
                    coalesce(avg(case when status = 'UP' then latency_ms else null end), 0.0) as avg_lat
                FROM uptime_logs
                WHERE created_at >= datetime('now', '+3 hours', ? || ' hours')
                GROUP BY hour_key, service
                ORDER BY hour_key ASC
                """,
                (f"-{hours}",),
            ) as cursor:
                hourly_rows = await cursor.fetchall()

            # Organize hourly data
            now_dt = get_msk_now()
            slot_keys = []
            slot_labels = []
            for i in range(hours - 1, -1, -1):
                slot_time = now_dt - timedelta(hours=i)
                slot_keys.append(slot_time.strftime("%Y-%m-%d %H"))
                slot_labels.append(slot_time.strftime("%H:00"))

            treblo_by_hour = {}
            bot_by_hour = {}
            for r in hourly_rows:
                hkey = r["hour_key"]
                srv = r["service"]
                tot = r["total_checks"]
                up = r["up_checks"]
                pct = round((up / tot * 100), 1) if tot > 0 else 100.0
                if srv == "treblo_api":
                    treblo_by_hour[hkey] = {
                        "uptime": pct,
                        "latency": round(r["avg_lat"], 1),
                    }
                elif srv == "bot":
                    bot_by_hour[hkey] = {
                        "uptime": pct,
                    }

            hourly_labels = slot_labels
            hourly_treblo_latency = []
            hourly_treblo_uptime = []
            hourly_bot_uptime = []
            hourly_bars = []

            for k in slot_keys:
                t_info = treblo_by_hour.get(k)
                b_info = bot_by_hour.get(k)

                t_lat = t_info["latency"] if t_info else 0.0
                t_up = t_info["uptime"] if t_info else 100.0
                b_up = b_info["uptime"] if b_info else 100.0

                hourly_treblo_latency.append(t_lat)
                hourly_treblo_uptime.append(t_up)
                hourly_bot_uptime.append(b_up)

                if t_info is None and b_info is None:
                    hourly_bars.append({"status": "none", "label": "Нет данных", "latency": 0, "uptime": 100})
                elif t_up >= 99.0 and b_up >= 99.0:
                    hourly_bars.append({"status": "up", "latency": t_lat, "uptime": t_up})
                elif t_up > 50.0 or b_up > 50.0:
                    hourly_bars.append({"status": "partial", "latency": t_lat, "uptime": t_up})
                else:
                    hourly_bars.append({"status": "down", "latency": t_lat, "uptime": t_up})

            return {
                "bot_status": "UP",
                "bot_uptime_24h_pct": bot_pct,
                "treblo_status": treblo_current_status,
                "treblo_last_latency": treblo_current_latency,
                "treblo_avg_latency_24h": treblo_avg_lat,
                "treblo_uptime_24h_pct": treblo_pct,
                "treblo_uptime_7d_pct": treblo_7d_pct,
                "treblo_last_error": treblo_last_error,
                "treblo_last_check": treblo_last_check,
                "hourly_labels": hourly_labels,
                "hourly_treblo_latency": hourly_treblo_latency,
                "hourly_treblo_uptime": hourly_treblo_uptime,
                "hourly_bot_uptime": hourly_bot_uptime,
                "hourly_bars": hourly_bars,
            }

    async def cleanup_old_uptime_logs(self, days: int = 14) -> int:
        """Deletes uptime logs older than specified days."""
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                "DELETE FROM uptime_logs WHERE created_at < datetime('now', '+3 hours', ? || ' days')",
                (f"-{days}",),
            )
            await db.commit()
            return cursor.rowcount


db = Database()
