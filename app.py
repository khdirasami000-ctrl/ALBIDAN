import os
import re
import html
import json
import uuid
import sqlite3
from datetime import datetime
from typing import List, Dict
import streamlit as st
import pandas as pd
from pydantic import BaseModel, Field
from google import genai
from google.genai import types

try:
    from pymongo import MongoClient
    PYMONGO_AVAILABLE = True
except ImportError:
    PYMONGO_AVAILABLE = False


# ==========================================
# 0. دوال مساعدة للأسرار والبيئة السحابية
# ==========================================
def get_secret_safe(key: str, default: str = "") -> str:
    """قراءة المفاتيح السرية من st.secrets أو متغيرات البيئة دون تعريضها في الواجهة."""
    try:
        if key in st.secrets:
            val = st.secrets[key]
            return str(val).strip() if val is not None else default
    except Exception:
        pass
    return os.getenv(key, default).strip()


def is_running_on_cloud() -> bool:
    """الكشف التلقائي عن التشغيل على Streamlit Cloud."""
    if get_secret_safe("IS_CLOUD", "").lower() in ("true", "1", "yes"):
        return True
    return os.path.exists("/mount/src")


@st.cache_resource(show_spinner=False)
def get_cached_mongo_client(uri: str):
    """إنشاء اتصال MongoDB واحد مُخزّن مؤقتاً لتسريع التطبيق ومنع تكرار الاتصال."""
    client = MongoClient(uri, serverSelectionTimeoutMS=5000)
    client.admin.command("ping")
    return client


# ==========================================
# 1. إعدادات الصفحة والتصميم العربي (RTL)
# ==========================================
st.set_page_config(
    page_title="مختبر البيظان | الشعر الحساني والغناء التوليدي",
    page_icon="🐪",
    layout="wide",
    initial_sidebar_state="expanded"
)

st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Cairo:wght@400;600;700&display=swap');

    html, body, [class*="css"] {
        font-family: 'Cairo', sans-serif;
        direction: rtl;
        text-align: right;
    }
    .stTextArea textarea, .stTextInput input {
        direction: rtl;
        text-align: right;
    }
    .stTextArea textarea {
        font-size: 1.15rem;
        line-height: 1.9;
    }
    /* مسافة أمان أسفل الشريط الجانبي لمنع تداخل أزرار Streamlit على الهاتف */
    section[data-testid="stSidebar"] > div:first-child {
        padding-bottom: 110px !important;
    }
    .main-header {
        background: linear-gradient(135deg, #2C1E16 0%, #6B4423 100%);
        padding: 1.6rem 1.8rem;
        border-radius: 12px;
        color: #F5E6D3;
        margin-bottom: 1.4rem;
        border-right: 6px solid #D4AF37;
    }
    .main-header h1 {
        color: #D4AF37;
        margin: 0;
        font-size: 1.9rem;
    }
    .main-header p {
        margin: 0.4rem 0 0 0;
        font-size: 1.02rem;
        opacity: 0.92;
    }
    .translation-box {
        background-color: #1E1E1E;
        border: 1px solid #3A3A3A;
        border-radius: 10px;
        padding: 1.2rem;
        direction: ltr;
        text-align: left;
        line-height: 1.8;
        font-size: 1.05rem;
    }
    .poem-card {
        background-color: #1A1A1A;
        border: 1px solid #333333;
        border-right: 4px solid #D4AF37;
        border-radius: 10px;
        padding: 1rem 1.2rem;
        margin-bottom: 0.8rem;
        white-space: pre-line;
        line-height: 1.9;
    }
    .stCodeBlock {
        direction: ltr;
        text-align: left;
    }
    /* بطاقات الإحصائيات جنباً إلى جنب حتى على شاشة الهاتف */
    .stats-row {
        display: flex;
        flex-direction: row;
        gap: 10px;
        margin: 10px 0 6px 0;
        width: 100%;
    }
    .stat-card {
        flex: 1;
        background: rgba(255, 255, 255, 0.04);
        border: 1px solid rgba(212, 175, 55, 0.28);
        border-radius: 10px;
        padding: 10px 8px;
        text-align: center;
    }
    .stat-label {
        font-size: 0.85rem;
        color: #C9BFA8;
        margin-bottom: 4px;
    }
    .stat-value {
        font-size: 1.65rem;
        font-weight: 700;
        color: #FFFFFF;
        line-height: 1.2;
    }
    .secure-badge {
        padding: 8px 12px;
        border-radius: 8px;
        font-size: 0.85rem;
        margin: 6px 0 10px 0;
        border: 1px solid rgba(76, 175, 80, 0.35);
        background: rgba(76, 175, 80, 0.12);
        color: #A5D6A7;
    }
    .warn-badge {
        padding: 8px 12px;
        border-radius: 8px;
        font-size: 0.85rem;
        margin: 6px 0 10px 0;
        border: 1px solid rgba(255, 193, 7, 0.35);
        background: rgba(255, 193, 7, 0.10);
        color: #FFE082;
    }
</style>
""", unsafe_allow_html=True)


# ==========================================
# 2. هياكل البيانات المهيكلة (Pydantic Schemas)
# ==========================================
class AILineAnalysis(BaseModel):
    original_line: str = Field(description="الشطر الأصلي كما أدخله المستخدم")
    phonetic_diacritized: str = Field(description="كتابة الشطر مضبوطاً بالشكل الصوتي الحساني مع إظهار السواكن والمدود")
    mutaharrikat_count: int = Field(description="العدد الدقيق للمتحركات في الشطر وفق العروض الحساني")
    estimated_meter: str = Field(description="اسم البحر الحساني (مثل: لبتيت التام، لبتيت الناقص، السغير، لبير)")
    rhyme_ending: str = Field(description="الروي أو القافية الصوتية للشطر")


class GlossaryTerm(BaseModel):
    term: str = Field(description="المفردة الحسانية")
    arabic_meaning: str = Field(description="معناها بالعربية الفصحى")
    english_meaning: str = Field(description="معناها المختصر بالإنجليزية")


class AIPoemAnalysis(BaseModel):
    poem_type: str = Field(description="نوع القطعة: تبراع، كاف، طلعة، أو شعر حر")
    dominant_meter: str = Field(description="البحر السائد في القصيدة")
    cultural_context: str = Field(description="شرح موجز للغرض الشعري والرمزية الثقافية الحسانية في النص")
    recommended_azawan: str = Field(description="المقام الموسيقي الأنسب من أزوان: كر، فاغو، لبياظ، أو لكحال مع السبب")
    lines: List[AILineAnalysis]
    glossary: List[GlossaryTerm] = Field(description="شرح لأهم المفردات الحسانية التراثية في النص")
    english_translation: str = Field(description="ترجمة شعرية وأدبية رفيعة للإنجليزية تحافظ على الروح الصحراوية")
    french_translation: str = Field(description="ترجمة شعرية وأدبية رفيعة للفرنسية تحافظ على الروح الصحراوية")


# ==========================================
# 3. مدير الأرشيف وقاعدة البيانات (MongoDB Atlas + SQLite)
# ==========================================
class ArchiveManager:
    def __init__(
        self,
        backend: str = "mongodb",
        sqlite_path: str = "albidan_archive.db",
        mongo_uri: str = "",
        mongo_db_name: str = "albidan_corpus"
    ):
        self.backend = backend
        self.sqlite_path = sqlite_path
        self.mongo_uri = mongo_uri.strip()
        self.mongo_db_name = mongo_db_name
        self.active_mode = "sqlite"
        self.status_message = f"متصل بقاعدة SQLite المحلية ({sqlite_path})"
        self.mongo_db = None

        if backend == "mongodb" and self.mongo_uri:
            if not PYMONGO_AVAILABLE:
                self.status_message = "مكتبة pymongo غير مثبتة؛ تم التحويل مؤقتاً إلى SQLite."
                self._init_sqlite()
            else:
                try:
                    client = get_cached_mongo_client(self.mongo_uri)
                    self.mongo_db = client[self.mongo_db_name]
                    self.active_mode = "mongodb"
                    self.status_message = f"متصل بنجاح بـ MongoDB Atlas ({self.mongo_db_name})"
                except Exception as e:
                    self.status_message = f"تعذر الاتصال بـ MongoDB ({e})؛ تم التحويل إلى SQLite."
                    self._init_sqlite()
        else:
            self._init_sqlite()

    def _init_sqlite(self):
        with sqlite3.connect(self.sqlite_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS poems (
                    id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    poet TEXT,
                    region TEXT,
                    poem_text TEXT NOT NULL,
                    poem_type TEXT,
                    dominant_meter TEXT,
                    azawan_mode TEXT,
                    source_engine TEXT,
                    analysis_json TEXT NOT NULL,
                    music_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS glossary (
                    term TEXT PRIMARY KEY,
                    arabic_meaning TEXT,
                    english_meaning TEXT,
                    source_poem_title TEXT,
                    updated_at TEXT NOT NULL
                )
            """)
            conn.commit()

    def save_poem(
        self,
        title: str,
        poet: str,
        region: str,
        poem_text: str,
        analysis_res: Dict,
        music_data: Dict,
        azawan_mode: str,
        source_engine: str
    ) -> str:
        record_id = str(uuid.uuid4())[:8]
        now_iso = datetime.now().strftime("%Y-%m-%d %H:%M")

        record = {
            "id": record_id,
            "title": title.strip() or "قصيدة بدون عنوان",
            "poet": poet.strip() or "تراث شفهي / غير معروف",
            "region": region.strip() or "الصحراء المغربية",
            "poem_text": poem_text.strip(),
            "poem_type": analysis_res.get("poem_type", "غير محدد"),
            "dominant_meter": analysis_res.get("dominant_meter", "غير محدد"),
            "azawan_mode": azawan_mode,
            "source_engine": source_engine,
            "analysis": analysis_res,
            "music": music_data,
            "created_at": now_iso,
        }

        glossary_items = analysis_res.get("glossary", [])

        if self.active_mode == "mongodb":
            doc = dict(record)
            doc["_id"] = record_id
            self.mongo_db["poems"].insert_one(doc)
            for g in glossary_items:
                term = g.get("term", "").strip()
                if term:
                    self.mongo_db["glossary"].update_one(
                        {"term": term},
                        {
                            "$set": {
                                "term": term,
                                "arabic_meaning": g.get("arabic_meaning", ""),
                                "english_meaning": g.get("english_meaning", ""),
                                "source_poem_title": record["title"],
                                "updated_at": now_iso,
                            }
                        },
                        upsert=True,
                    )
        else:
            with sqlite3.connect(self.sqlite_path) as conn:
                conn.execute(
                    """
                    INSERT INTO poems (
                        id, title, poet, region, poem_text, poem_type, dominant_meter,
                        azawan_mode, source_engine, analysis_json, music_json, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        record["id"],
                        record["title"],
                        record["poet"],
                        record["region"],
                        record["poem_text"],
                        record["poem_type"],
                        record["dominant_meter"],
                        record["azawan_mode"],
                        record["source_engine"],
                        json.dumps(record["analysis"], ensure_ascii=False),
                        json.dumps(record["music"], ensure_ascii=False),
                        record["created_at"],
                    ),
                )
                for g in glossary_items:
                    term = g.get("term", "").strip()
                    if term:
                        conn.execute(
                            """
                            INSERT OR REPLACE INTO glossary (
                                term, arabic_meaning, english_meaning, source_poem_title, updated_at
                            ) VALUES (?, ?, ?, ?, ?)
                            """,
                            (
                                term,
                                g.get("arabic_meaning", ""),
                                g.get("english_meaning", ""),
                                record["title"],
                                now_iso,
                            ),
                        )
                conn.commit()
        return record_id

    def list_poems(self, search_query: str = "", type_filter: str = "الكل") -> List[Dict]:
        records: List[Dict] = []

        if self.active_mode == "mongodb":
            cursor = self.mongo_db["poems"].find().sort("created_at", -1)
            for doc in cursor:
                doc.pop("_id", None)
                records.append(doc)
        else:
            with sqlite3.connect(self.sqlite_path) as conn:
                conn.row_factory = sqlite3.Row
                rows = conn.execute("SELECT * FROM poems ORDER BY created_at DESC").fetchall()
                for row in rows:
                    records.append({
                        "id": row["id"],
                        "title": row["title"],
                        "poet": row["poet"],
                        "region": row["region"],
                        "poem_text": row["poem_text"],
                        "poem_type": row["poem_type"],
                        "dominant_meter": row["dominant_meter"],
                        "azawan_mode": row["azawan_mode"],
                        "source_engine": row["source_engine"],
                        "analysis": json.loads(row["analysis_json"]),
                        "music": json.loads(row["music_json"]),
                        "created_at": row["created_at"],
                    })

        if type_filter != "الكل":
            records = [r for r in records if type_filter in r.get("poem_type", "")]

        if search_query.strip():
            q = search_query.strip().lower()
            records = [
                r for r in records
                if q in r.get("title", "").lower()
                or q in r.get("poem_text", "").lower()
                or q in r.get("poet", "").lower()
                or q in r.get("region", "").lower()
                or q in r.get("dominant_meter", "").lower()
            ]
        return records

    def delete_poem(self, record_id: str):
        if self.active_mode == "mongodb":
            self.mongo_db["poems"].delete_one({"_id": record_id})
        else:
            with sqlite3.connect(self.sqlite_path) as conn:
                conn.execute("DELETE FROM poems WHERE id = ?", (record_id,))
                conn.commit()

    def list_glossary(self, search_query: str = "") -> List[Dict]:
        items: List[Dict] = []
        if self.active_mode == "mongodb":
            cursor = self.mongo_db["glossary"].find().sort("updated_at", -1)
            for doc in cursor:
                doc.pop("_id", None)
                items.append(doc)
        else:
            with sqlite3.connect(self.sqlite_path) as conn:
                conn.row_factory = sqlite3.Row
                rows = conn.execute("SELECT * FROM glossary ORDER BY updated_at DESC").fetchall()
                items = [dict(row) for row in rows]

        if search_query.strip():
            q = search_query.strip().lower()
            items = [
                g for g in items
                if q in g.get("term", "").lower()
                or q in g.get("arabic_meaning", "").lower()
                or q in g.get("english_meaning", "").lower()
            ]
        return items

    def get_stats(self) -> Dict[str, int]:
        if self.active_mode == "mongodb":
            poems_count = self.mongo_db["poems"].count_documents({})
            terms_count = self.mongo_db["glossary"].count_documents({})
            cursor = self.mongo_db["poems"].find({}, {"analysis.lines": 1})
            total_lines = sum(len(doc.get("analysis", {}).get("lines", [])) for doc in cursor)
            return {
                "poems_count": poems_count,
                "lines_count": total_lines,
                "terms_count": terms_count,
            }

        poems = self.list_poems()
        glossary = self.list_glossary()
        total_lines = sum(len(p.get("analysis", {}).get("lines", [])) for p in poems)
        return {
            "poems_count": len(poems),
            "lines_count": total_lines,
            "terms_count": len(glossary),
        }


# ==========================================
# 4. المحلل المحلي الاحتياطي (Fallback Engine)
# ==========================================
class LocalHassaniyaEngine:
    def __init__(self):
        self.short_vowels = set("َُِ")
        self.long_vowels = set("اويى")
        self.meters_map = {
            6: "السغير / لبير (6 متحركات)",
            7: "لبتيت الناقص (7 متحركات)",
            8: "لبتيت التام (8 متحركات)",
            9: "البت لكبير (9 متحركات)"
        }

    def analyze(self, poem_text: str) -> Dict:
        lines = [l.strip() for l in poem_text.strip().split('\n') if l.strip()]
        details = []
        for line in lines:
            norm = re.sub(r'[ݣڤ]', 'گ', line)
            has_diacritics = any(ch in self.short_vowels for ch in norm)
            if has_diacritics:
                count = sum(1 for ch in norm if ch in self.short_vowels)
            else:
                words = norm.split()
                count = sum(
                    max(1, len([c for c in re.sub(r'^[ال]+', '', w) if c not in self.long_vowels]) - 1)
                    for w in words
                )
            clean = re.sub(r'[ًٌٍَُِّْ\s]', '', norm)
            rhyme = clean[-2:] if len(clean) >= 2 else clean
            details.append({
                "original_line": line,
                "phonetic_diacritized": "يتطلب تفعيل الذكاء الاصطناعي للتشكيل الصوتي",
                "mutaharrikat_count": count,
                "estimated_meter": self.meters_map.get(count, f"وزن تقديري ({count} متحرك)"),
                "rhyme_ending": rhyme
            })

        poem_type = "نص شعري"
        if len(details) == 2:
            poem_type = "تبراع (Tebraa)"
        elif len(details) == 4:
            poem_type = "كاف (Gaf)"
        elif len(details) >= 6:
            poem_type = "طلعة (Tal'aa)"

        return {
            "poem_type": poem_type,
            "dominant_meter": details[0]["estimated_meter"] if details else "غير محدد",
            "cultural_context": "فعّل الذكاء الاصطناعي (AI Mode) لتفعيل التحليل الثقافي، التشكيل الصوتي الدقيق، والترجمة العالمية.",
            "recommended_azawan": "لبياظ (تقديري)",
            "lines": details,
            "glossary": [],
            "english_translation": "Enable AI Mode to generate poetic English translation.",
            "french_translation": "Activez le mode IA pour générer la traduction poétique en français."
        }


# ==========================================
# 5. دوال الذكاء الاصطناعي (تفريغ الصوت + التحليل العروضي)
# ==========================================
def get_audio_mime_type(uploaded_file) -> str:
    ext = os.path.splitext(uploaded_file.name)[1].lower()
    mime_map = {
        ".mp3": "audio/mp3",
        ".wav": "audio/wav",
        ".m4a": "audio/mp4",
        ".ogg": "audio/ogg",
        ".flac": "audio/flac",
    }
    return mime_map.get(ext, uploaded_file.type or "audio/mp3")


def transcribe_hassaniya_audio(
    audio_bytes: bytes,
    mime_type: str,
    api_key: str,
    model_name: str = "gemini-3.8-flash"
) -> str:
    client = genai.Client(api_key=api_key)
    transcription_prompt = """
    أنت خبير في اللهجة الحسانية المغربية والموريتانية والشعر الحساني (لغنى، الكاف، الطلعة، التبراع).
    استمع بدقة لهذا التسجيل الصوتي وقم بتفريغه نصياً وفق القواعد التالية:
1. اكتب الكلمات تماماً كما تُنطق باللهجة الحسانية الأصيلة دون تحويلها للفصحى.
2. استخدم الحرف (گ) للقاف المعقودة الحسانية (مثل: گلب، گال، اگليب، لْحگ).
3. افصل كل شطر شعري (تافلويت) في سطر مستقل تماماً.
4. تجاهل الموسيقى الخلفية أو المقدمات الكلامية غير الشعرية إن وجدت.
5. أخرج الأبيات الشعرية فقط دون أي عناوين أو تعليقات أو شرح إضافي.
    """
    response = client.models.generate_content(
        model=model_name,
        contents=[
            types.Part.from_bytes(data=audio_bytes, mime_type=mime_type),
            transcription_prompt
        ],
    )
    return (response.text or "").strip()


def analyze_with_gemini(
    poem_text: str,
    api_key: str,
    model_name: str = "gemini-3.8-flash"
) -> Dict:
    client = genai.Client(api_key=api_key)
    system_instruction = """
    أنت خبير أكاديمي وعروضي متخصص في الأدب والشعر الشعبي الحساني المغربي والموريتاني (لغنى والتبراع) وموسيقى أزوان.
    مهمتك تحليل النص الشعري الحساني بدقة لغوية وعروضية فائقة:
1. راعِ ظاهرة "الابتداء بالساكن" في اللهجة الحسانية (مثل: لْحگ، اگْليب، شْوي، مْعاك) عند التشكيل الصوتي وعدّ المتحركات.
2. عدّ المتحركات هو أساس الوزن الحساني (السغير = 6، لبتيت الناقص = 7، لبتيت التام = 8، البت لكبير = 9+).
3. ميّز بدقة بين التبراع (بيتان متفقا القافية)، الكاف (4 أشطر غالباً بقافية أ-ب-أ-ب)، والطلعة (6 أشطر فأكثر).
4. استخرج المفردات الحسانية الأصيلة واشرحها بوضوح.
5. قدم ترجمة شعرية عالية الجودة للإنجليزية والفرنسية تبرز جماليات الصحراء للجمهور العالمي.
    """
    response = client.models.generate_content(
        model=model_name,
        contents=f"حلّل هذا النص الشعري الحساني تحليلاً كاملاً:\n\n{poem_text}",
        config=types.GenerateContentConfig(
            system_instruction=system_instruction,
            response_mime_type="application/json",
            response_schema=AIPoemAnalysis,
        ),
    )
    parsed = AIPoemAnalysis.model_validate_json(response.text)
    return parsed.model_dump()


# ==========================================
# 6. محرك أزوان والغناء التوليدي
# ==========================================
class AzawanMusicDirector:
    def __init__(self):
        self.azawan_modes = {
            "كر (Karr) - الفخر والوقار": {
                "mood": "Epic, noble, deep desert resonance, proud",
                "instruments": "Tidinit (Saharan lute), deep Tbal drums, warm ambient synth",
                "bpm": 85
            },
            "فاغو (Faghu) - الحماس والإيقاع": {
                "mood": "Energetic, triumphant, rhythmic, uplifting",
                "instruments": "Fast Tidinit riffs, Ardin harp, handclaps, modern Afro-desert percussion",
                "bpm": 115
            },
            "لبياظ (Labyad) - الحنين والغزل": {
                "mood": "Melancholic, romantic, nostalgic, soulful",
                "instruments": "Soft Ardin harp, acoustic Tidinit, warm cello pad, emotional vocals",
                "bpm": 75
            },
            "لكحال (Lakhhal) - العمق والروحانية": {
                "mood": "Mystical, hypnotic, deep night desert atmosphere",
                "instruments": "Reverb-drenched Tidinit, subtle oud, slow hypnotic percussion",
                "bpm": 70
            }
        }

    def generate_song_structure(
        self,
        poem_lines: List[str],
        mode: str,
        fusion_style: str,
        vocal_type: str
    ) -> Dict[str, str]:
        selected = self.azawan_modes.get(mode, list(self.azawan_modes.values())[2])
        style_prompt = (
            f"Hassaniya Moroccan Saharan {fusion_style}, {selected['mood']}, "
            f"{vocal_type}, featuring {selected['instruments']}, {selected['bpm']} BPM, "
            f"authentic Saharan vocal ornamentation, studio quality mastering, crystal clear mix."
        )

        lyrics = "[Intro: Solo Tidinit melody with gentle desert ambience]\n\n"
        if len(poem_lines) <= 2:
            lyrics += "[Verse 1: Intimate, expressive vocal]\n" + "\n".join(poem_lines) + "\n\n"
            lyrics += "[Instrumental Interlude: Emotional Ardin harp solo]\n\n"
            lyrics += "[Outro: Soft vocal echo fading with Tidinit]"
        elif len(poem_lines) <= 4:
            lyrics += "[Verse 1]\n" + "\n".join(poem_lines[:2]) + "\n\n"
            lyrics += "[Chorus: Full rhythm with Tbal and handclaps]\n" + "\n".join(poem_lines[2:]) + "\n\n"
            lyrics += "[Outro: Fading Tidinit and rhythmic drums]"
        else:
            lyrics += "[Verse 1]\n" + "\n".join(poem_lines[:4]) + "\n\n"
            lyrics += "[Chorus: Energetic and soulful]\n" + "\n".join(poem_lines[4:6]) + "\n\n"
            if len(poem_lines) > 6:
                lyrics += "[Bridge / Verse 2]\n" + "\n".join(poem_lines[6:]) + "\n\n"
            lyrics += "[Outro: Traditional Saharan instrumental fade-out]"

        return {"style_prompt": style_prompt, "formatted_lyrics": lyrics, "bpm": str(selected["bpm"])}


# ==========================================
# 7. تهيئة الحالة والدوال المساعدة (Callbacks)
# ==========================================
local_engine = LocalHassaniyaEngine()
director = AzawanMusicDirector()

default_texts = {
    "إدخال حر": "",
    "نموذج كاف (لبتيت)": "الصحرا دار الكرم والجود\nفيها الخيمة والگلب الصافي\nتاريخ أجدادنا المعهود\nيبقى في كل زمن وافي",
    "نموذج تبراع": "يا گلب اصبر لا تلوم\nالزين يبان ف كل يوم"
}

if "poem_input_text" not in st.session_state:
    st.session_state["poem_input_text"] = ""
if "nav_page" not in st.session_state:
    st.session_state["nav_page"] = "🧪 المختبر والتحليل"


def on_sample_change():
    choice = st.session_state["sample_choice"]
    st.session_state["poem_input_text"] = default_texts[choice]


def load_poem_into_lab(record: Dict):
    st.session_state["poem_input_text"] = record["poem_text"]
    st.session_state["analysis_result"] = record["analysis"]
    st.session_state["analysis_source"] = f"أرشيف ({record.get('source_engine', 'Saved')})"
    st.session_state["nav_page"] = "🧪 المختبر والتحليل"


# ==========================================
# 8. الشريط الجانبي الآمن والمُحسّن للهاتف
# ==========================================
on_cloud = is_running_on_cloud()
secret_mongo_uri = get_secret_safe("MONGODB_URI", "")
secret_mongo_db = get_secret_safe("MONGODB_DB_NAME", "albidan_corpus")
secret_gemini_key = get_secret_safe("GEMINI_API_KEY", "")

with st.sidebar:
    st.header("🧭 التنقل الرئيسي")
    nav_page = st.radio(
        "اختر القسم:",
        [
            "🧪 المختبر والتحليل",
            "📚 أرشيف القصائد (المدونة)",
            "📖 المعجم الحساني المتنامي"
        ],
        key="nav_page",
        label_visibility="collapsed"
    )

    st.divider()
    st.header("🗄️ قاعدة البيانات والأرشيف")

    # على السحابة يُعتمد التخزين السحابي فقط؛ محلياً يتوفر الخياران
    if on_cloud:
        storage_options = ["التخزين السحابي — MongoDB Atlas"]
    else:
        storage_options = [
            "التخزين السحابي — MongoDB Atlas",
            "التخزين المحلي — SQLite"
        ]

    default_storage_idx = 0 if (on_cloud or secret_mongo_uri) else 1
    db_choice = st.selectbox(
        "نوع التخزين:",
        options=storage_options,
        index=min(default_storage_idx, len(storage_options) - 1)
    )

    if "MongoDB" in db_choice:
        backend_code = "mongodb"
        if secret_mongo_uri:
            # استخدام الرابط من الخادم مباشرة دون عرضه داخل حقل نصي
            mongo_uri = secret_mongo_uri
        else:
            mongo_uri = st.text_input(
                "رابط اتصال MongoDB:",
                value="",
                type="password",
                placeholder="أدخل الرابط يدوياً للتجربة المحلية...",
                help="يُفضّل حفظ MONGODB_URI في إعدادات Secrets"
            )
    else:
        backend_code = "sqlite"
        mongo_uri = ""

    archive = ArchiveManager(
        backend=backend_code,
        mongo_uri=mongo_uri,
        mongo_db_name=secret_mongo_db
    )

    if archive.active_mode == "mongodb":
        st.markdown(
            f'<div class="secure-badge">🔒 {html.escape(archive.status_message)}</div>',
            unsafe_allow_html=True
        )
    else:
        st.markdown(
            f'<div class="warn-badge">💾 {html.escape(archive.status_message)}</div>',
            unsafe_allow_html=True
        )

    stats = archive.get_stats()
    st.markdown(
        f"""
        <div class="stats-row">
            <div class="stat-card">
                <div class="stat-label">القصائد</div>
                <div class="stat-value">{stats['poems_count']}</div>
            </div>
            <div class="stat-card">
                <div class="stat-label">المفردات</div>
                <div class="stat-value">{stats['terms_count']}</div>
            </div>
        </div>
        """,
        unsafe_allow_html=True
    )

    st.divider()
    st.header("🧠 محرك الذكاء الاصطناعي")

    if secret_gemini_key:
        # استخدام المفتاح بأمان من الخادم دون إظهاره أو تمكين زر العين
        api_key = secret_gemini_key
        st.markdown(
            '<div class="secure-badge">🔑 مفتاح Gemini API مُفعّل بأمان من الخادم</div>',
            unsafe_allow_html=True
        )
    else:
        api_key = st.text_input(
            "مفتاح Gemini API:",
            value="",
            type="password",
            placeholder="أدخل مفتاح API هنا..."
        )

    available_models = [
        "gemini-3.8-flash",
        "gemini-3.5-flash-lite",
        "gemini-3.1-pro-preview",
    ]
    model_name = st.selectbox(
        "نموذج Gemini:",
        options=available_models,
        index=0
    )
    use_ai = st.toggle("تفعيل التحليل الذكي (AI Mode)", value=bool(api_key))

    st.divider()
    st.header("🎵 إعدادات أزوان")
    st.selectbox(
        "نماذج جاهزة للتجربة:",
        list(default_texts.keys()),
        key="sample_choice",
        on_change=on_sample_change
    )
    selected_mode = st.selectbox("المقام الموسيقي (أزوان):", list(director.azawan_modes.keys()))
    fusion_style = st.selectbox(
        "النمط العالمي (Fusion Style):",
        ["World Music Fusion", "Desert Blues & Acoustic", "Cinematic Orchestral", "Modern Afro-Saharan", "Chill Lo-Fi Desert"]
    )
    vocal_type = st.selectbox(
        "طبيعة الصوت الغنائي:",
        [
            "Deep soulful male Hassaniya vocals",
            "Expressive traditional female Hassaniya vocals",
            "Duet male and female traditional vocals",
            "Traditional chorus with lead vocalist"
        ]
    )


# ==========================================
# الترويسة الرئيسية
# ==========================================
st.markdown("""
<div class="main-header">
    <h1>مختبر البيظان للشعر الحساني والغناء التوليدي (ALBIDAN AI Lab)</h1>
    <p>منصة التوثيق الصوتي، التحليل العروضي، المعجم الحساني المتنامي، وهندسة أزوان للعالمية</p>
</div>
""", unsafe_allow_html=True)


# ==========================================
# الصفحة 1: المختبر والتحليل
# ==========================================
if nav_page == "🧪 المختبر والتحليل":
    with st.expander("🎙️ رفع تسجيل صوتي لقصيدة حسانية (MP3 / WAV / M4A) وتفريغه تلقائياً", expanded=False):
        uploaded_audio = st.file_uploader(
            "اختر ملفاً صوتياً (الحد الأقصى 20 ميجابايت):",
            type=["mp3", "wav", "m4a", "ogg", "flac"]
        )

        if uploaded_audio is not None:
            st.audio(uploaded_audio)
            if uploaded_audio.size > 20 * 1024 * 1024:
                st.error("حجم الملف يتجاوز 20 ميجابايت.")
            else:
                col_t1, col_t2 = st.columns(2)
                transcribe_only_btn = col_t1.button("📝 تفريغ الصوت للمراجعة", use_container_width=True)
                transcribe_and_analyze_btn = col_t2.button("⚡ تفريغ وتحليل مباشر", type="primary", use_container_width=True)

                if transcribe_only_btn or transcribe_and_analyze_btn:
                    if not api_key.strip():
                        st.warning("يرجى ضبط مفتاح Gemini API لتشغيل التفريغ الصوتي.")
                    else:
                        try:
                            with st.spinner("جاري الاستماع وتفريغ القصيدة الحسانية..."):
                                transcribed = transcribe_hassaniya_audio(
                                    uploaded_audio.getvalue(),
                                    get_audio_mime_type(uploaded_audio),
                                    api_key.strip(),
                                    model_name
                                )
                            if not transcribed:
                                st.warning("لم يتم التعرف على نص واضح في التسجيل.")
                            else:
                                st.session_state["poem_input_text"] = transcribed
                                st.success("تم تفريغ الصوت بنجاح!")
                                if transcribe_and_analyze_btn:
                                    with st.spinner("جاري التحليل العروضي والترجمة..."):
                                        st.session_state["analysis_result"] = analyze_with_gemini(
                                            transcribed, api_key.strip(), model_name
                                        )
                                        st.session_state["analysis_source"] = f"Audio + AI ({model_name})"
                        except Exception as e:
                            st.error(f"حدث خطأ أثناء معالجة الصوت: {e}")

    poem_input = st.text_area(
        "✍️ النص الشعري الحساني (كل تافلويت في سطر):",
        key="poem_input_text",
        height=170,
        placeholder="اكتب الكاف أو الطلعة أو التبراع هنا، أو ارفع تسجيلاً صوتياً بالأعلى..."
    )

    analyze_btn = st.button("🚀 تحليل القصيدة وتوليد العمل العالمي", type="primary", use_container_width=True)

    if analyze_btn:
        if not poem_input.strip():
            st.warning("يرجى إدخال بيت شعري واحد على الأقل للبدء.")
        else:
            if use_ai and api_key.strip():
                with st.spinner("جاري التقطيع الصوتي الحساني والترجمة الأدبية..."):
                    try:
                        st.session_state["analysis_result"] = analyze_with_gemini(
                            poem_input, api_key.strip(), model_name
                        )
                        st.session_state["analysis_source"] = f"AI ({model_name})"
                    except Exception as e:
                        st.error(f"حدث خطأ في الاتصال بـ API: {e}")
                        st.info("تم التحويل تلقائياً للمحلل المحلي.")
                        st.session_state["analysis_result"] = local_engine.analyze(poem_input)
                        st.session_state["analysis_source"] = "Local"
            else:
                st.session_state["analysis_result"] = local_engine.analyze(poem_input)
                st.session_state["analysis_source"] = "Local"

    if "analysis_result" in st.session_state:
        res = st.session_state["analysis_result"]
        lines_list = [item["original_line"] for item in res["lines"]]
        music_data = director.generate_song_structure(lines_list, selected_mode, fusion_style, vocal_type)

        # بطاقة الحفظ السريع في الأرشيف
        with st.expander("💾 حفظ هذه القصيدة ومفرداتها في الأرشيف الحساني (المدونة)", expanded=True):
            with st.form("save_poem_form", clear_on_submit=True):
                fc1, fc2, fc3 = st.columns(3)
                save_title = fc1.text_input("عنوان القصيدة / المقطع:", placeholder="مثال: كاف في مدح الصحراء")
                save_poet = fc2.text_input("الشاعر / الراوي:", placeholder="مثال: تراث شعبي أو اسم الشاعر")
                save_region = fc3.text_input("المنطقة / المصدر:", value="الصحراء المغربية")
                save_submitted = st.form_submit_button("📥 حفظ في المدونة وتحديث المعجم", type="primary", use_container_width=True)

                if save_submitted:
                    new_id = archive.save_poem(
                        title=save_title,
                        poet=save_poet,
                        region=save_region,
                        poem_text=poem_input,
                        analysis_res=res,
                        music_data=music_data,
                        azawan_mode=selected_mode,
                        source_engine=st.session_state.get("analysis_source", "Local"),
                    )
                    st.success(f"تم الحفظ بنجاح في الأرشيف (المعرف: {new_id}) وإضافة المفردات للمعجم المتنامي!")

        tab1, tab2, tab3, tab4 = st.tabs([
            "📊 العروض والتقطيع الصوتي",
            "🌍 القاموس والترجمة العالمية",
            "🎵 استوديو أزوان والغناء",
            "💾 تصدير الملف"
        ])

        with tab1:
            c1, c2, c3 = st.columns(3)
            c1.metric("تصنيف القطعة", res["poem_type"])
            c2.metric("البحر السائد", res["dominant_meter"])
            c3.metric("عدد الأشطر (تافلويت)", len(res["lines"]))

            st.info(f"**السياق الثقافي والغرض الشعري:** {res['cultural_context']}")
            st.success(f"**ترشيح الذكاء الاصطناعي لمقام أزوان:** {res['recommended_azawan']}")

            df = pd.DataFrame([
                {
                    "الشطر الأصلي": item["original_line"],
                    "التشكيل الصوتي الحساني": item["phonetic_diacritized"],
                    "المتحركات": item["mutaharrikat_count"],
                    "البحر / الوزن": item["estimated_meter"],
                    "الروي": item["rhyme_ending"]
                }
                for item in res["lines"]
            ])
            st.dataframe(df, use_container_width=True, hide_index=True)

        with tab2:
            st.subheader("🌐 الترجمة الشعرية للجمهور العالمي")
            col_en, col_fr = st.columns(2)
            with col_en:
                st.markdown("**English Poetic Translation:**")
                en_html = html.escape(res["english_translation"]).replace("\n", "<br>")
                st.markdown(f"<div class='translation-box'>{en_html}</div>", unsafe_allow_html=True)
            with col_fr:
                st.markdown("**Traduction Poétique (Français):**")
                fr_html = html.escape(res["french_translation"]).replace("\n", "<br>")
                st.markdown(f"<div class='translation-box'>{fr_html}</div>", unsafe_allow_html=True)

            st.divider()
            st.subheader("📖 المفردات الحسانية المستخرجة من هذا النص")
            if res.get("glossary"):
                gloss_df = pd.DataFrame([
                    {
                        "المفردة الحسانية": g["term"],
                        "المعنى بالعربية الفصحى": g["arabic_meaning"],
                        "English Meaning": g["english_meaning"]
                    }
                    for g in res["glossary"]
                ])
                st.dataframe(gloss_df, use_container_width=True, hide_index=True)
            else:
                st.caption("فعّل الوضع الذكي (AI Mode) لاستخراج شرح المفردات الحسانية تلقائياً.")

        with tab3:
            st.subheader("1. وصف النمط الموسيقي (Style Prompt)")
            st.code(music_data["style_prompt"], language="text")

            st.subheader("2. الكلمات المنسقة بالوسوم الموسيقية (Formatted Lyrics)")
            st.code(music_data["formatted_lyrics"], language="text")

        with tab4:
            export_payload = {
                "source_engine": st.session_state.get("analysis_source", "Local"),
                "poem_analysis": res,
                "azawan_studio": {
                    "selected_mode": selected_mode,
                    "fusion_style": fusion_style,
                    "vocal_type": vocal_type,
                    **music_data
                }
            }
            st.download_button(
                label="📥 تحميل هذا المشروع بصيغة JSON",
                data=json.dumps(export_payload, ensure_ascii=False, indent=2),
                file_name="albidan_project.json",
                mime="application/json",
                use_container_width=True
            )


# ==========================================
# الصفحة 2: أرشيف القصائد (المدونة الحسانية)
# ==========================================
elif nav_page == "📚 أرشيف القصائد (المدونة)":
    st.subheader("📚 المدونة الحسانية المفتوحة (أرشيف القصائد المحللة)")

    m1, m2, m3 = st.columns(3)
    m1.metric("إجمالي القصائد المحفوظة", stats["poems_count"])
    m2.metric("إجمالي الأشطر (تافلويت)", stats["lines_count"])
    m3.metric("مفردات المعجم المتنامي", stats["terms_count"])

    st.divider()
    f1, f2, f3 = st.columns([3, 1.5, 1.5])
    search_q = f1.text_input("🔍 ابحث في القصائد (بالكلمة، العنوان، الشاعر، البحر، أو المنطقة):", placeholder="مثال: گلب، لبتيت، بوجدور...")
    type_filter = f2.selectbox("تصفية حسب النوع:", ["الكل", "تبراع", "كاف", "طلعة"])

    poems_list = archive.list_poems(search_query=search_q, type_filter=type_filter)

    # تصدير المدونة كاملة بصيغة JSONL جاهزة لتدريب نماذج الذكاء الاصطناعي
    if poems_list:
        jsonl_content = "\n".join(json.dumps(p, ensure_ascii=False) for p in poems_list)
        f3.write("")
        f3.download_button(
            label="🤖 تصدير المدونة (JSONL للـ AI)",
            data=jsonl_content,
            file_name="albidan_hassaniya_corpus.jsonl",
            mime="application/jsonl",
            use_container_width=True
        )

    if not poems_list:
        st.info("الأرشيف فارغ حالياً أو لا توجد نتائج مطابقة للبحث. حلّل قصيدة في المختبر واضغط على 'حفظ في المدونة' للبدء.")
    else:
        for rec in poems_list:
            header_label = f"📜 {rec['title']}  |  {rec['poem_type']}  |  {rec['dominant_meter']}  |  ✍️ {rec['poet']} ({rec['created_at']})"
            with st.expander(header_label, expanded=False):
                st.markdown(f"<div class='poem-card'>{html.escape(rec['poem_text'])}</div>", unsafe_allow_html=True)
                st.caption(f"📍 المنطقة: {rec['region']}  •  🎵 مقام أزوان: {rec['azawan_mode']}  •  ⚙️ المحرك: {rec['source_engine']}")

                a_col1, a_col2 = st.columns(2)
                a_col1.button(
                    "🔄 فتح القصيدة في المختبر",
                    key=f"load_{rec['id']}",
                    on_click=load_poem_into_lab,
                    args=(rec,),
                    use_container_width=True
                )
                if a_col2.button("🗑️ حذف من الأرشيف", key=f"del_{rec['id']}", use_container_width=True):
                    archive.delete_poem(rec["id"])
                    st.rerun()


# ==========================================
# الصفحة 3: المعجم الحساني المتنامي
# ==========================================
elif nav_page == "📖 المعجم الحساني المتنامي":
    st.subheader("📖 المعجم الحساني التفاعلي (يُبنى تلقائياً من القصائد المحفوظة)")

    g_search = st.text_input("🔍 ابحث عن مفردة حسانية أو معناها بالعربية أو الإنجليزية:", placeholder="اكتب كلمة للبحث...")
    glossary_items = archive.list_glossary(search_query=g_search)

    if not glossary_items:
        st.info("لم تُضف مفردات بعد. عند حفظ قصيدة محللة بالذكاء الاصطناعي (AI Mode)، تُضاف مفرداتها الحسانية تلقائياً هنا.")
    else:
        gloss_df = pd.DataFrame([
            {
                "المفردة الحسانية": item["term"],
                "المعنى بالعربية الفصحى": item["arabic_meaning"],
                "English Meaning": item["english_meaning"],
                "المصدر (القصيدة)": item.get("source_poem_title", ""),
                "تاريخ التوثيق": item.get("updated_at", "")
            }
            for item in glossary_items
        ])

        st.dataframe(gloss_df, use_container_width=True, hide_index=True)

        csv_bytes = gloss_df.to_csv(index=False).encode("utf-8-sig")
        st.download_button(
            label="📥 تحميل المعجم الحساني بصيغة CSV (Excel)",
            data=csv_bytes,
            file_name="albidan_hassaniya_glossary.csv",
            mime="text/csv",
            use_container_width=True
        )
