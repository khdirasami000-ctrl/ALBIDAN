import os
import re
import html
import json
import uuid
import base64
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
# 0. دوال الأسرار والاتصال السحابي الآمن
# ==========================================
def get_secret_safe(key: str, default: str = "") -> str:
    try:
        if key in st.secrets:
            val = st.secrets[key]
            return str(val).strip() if val is not None else default
    except Exception:
        pass
    return os.getenv(key, default).strip()


def is_running_on_cloud() -> bool:
    if get_secret_safe("IS_CLOUD", "").lower() in ("true", "1", "yes"):
        return True
    return os.path.exists("/mount/src")


@st.cache_resource(show_spinner=False)
def get_cached_mongo_client(uri: str):
    client = MongoClient(uri, serverSelectionTimeoutMS=5000)
    client.admin.command("ping")
    return client


def get_founder_avatar_html() -> str:
    """عرض صورة المؤسس تلقائياً عند وجود ملف founder.jpg أو founder.png، وإلا عرض شعار فخم."""
    for filename, mime in (
        ("founder.jpg", "image/jpeg"),
        ("founder.jpeg", "image/jpeg"),
        ("founder.png", "image/png"),
        ("founder.webp", "image/webp"),
    ):
        if os.path.exists(filename):
            try:
                with open(filename, "rb") as f:
                    b64 = base64.b64encode(f.read()).decode("utf-8")
                return f'<img src="data:{mime};base64,{b64}" class="founder-photo" alt="أڭــار الحبيب" />'
            except Exception:
                pass
    return """
    <div class="founder-monogram">
        <div class="founder-monogram-letters">أ ح</div>
        <div class="founder-monogram-sub">ALBIDAN</div>
    </div>
    """


# ==========================================
# 1. إعدادات الصفحة والتصميم المستوحى من البوابات الثقافية
# ==========================================
st.set_page_config(
    page_title="مختبر البيظان | ALBIDAN — الشعر الحساني وهندسة أزوان",
    page_icon="🐪",
    layout="wide",
    initial_sidebar_state="collapsed"
)

st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Amiri:wght@400;700&family=Cairo:wght@400;600;700;800;900&display=swap');

    :root {
        --bg-page: #F8F7F4;
        --bg-card: #FFFFFF;
        --ink-primary: #162133;
        --ink-secondary: #526075;
        --brand-blue: #1E3A5F;
        --brand-blue-dark: #142842;
        --brand-gold: #C27803;
        --brand-gold-soft: #FEF3C7;
        --border-soft: #E7E2D8;
        --shadow-card: 0 6px 24px rgba(22, 33, 51, 0.05);
        --shadow-hover: 0 14px 32px rgba(22, 33, 51, 0.10);
    }

    /* الإعدادات العامة والاتجاه العربي */
    .stApp {
        background-color: var(--bg-page) !important;
        color: var(--ink-primary) !important;
    }

    html, body, [class*="css"] {
        font-family: 'Cairo', sans-serif !important;
        direction: rtl;
        text-align: right;
        color: var(--ink-primary);
    }

    /* إخفاء عناصر Streamlit التطويرية مع الإبقاء على زر القائمة الجانبية */
    #MainMenu, footer, .stDeployButton, [data-testid="stToolbarActions"] {
        visibility: hidden !important;
        display: none !important;
    }
    header[data-testid="stHeader"] {
        background: transparent !important;
    }
    .block-container {
        padding-top: 1.2rem !important;
        padding-bottom: 5rem !important;
        max-width: 1200px !important;
    }

    /* الشريط الجانبي (إعدادات النظام) */
    section[data-testid="stSidebar"] {
        background-color: #FFFFFF !important;
        border-left: 1px solid var(--border-soft) !important;
    }
    section[data-testid="stSidebar"] > div:first-child {
        padding-bottom: 110px !important;
    }

    /* شريط التنقل العلوي */
    .brand-logo {
        display: flex;
        align-items: center;
        gap: 10px;
        padding-top: 4px;
    }
    .brand-icon {
        width: 38px;
        height: 38px;
        border-radius: 10px;
        background: linear-gradient(135deg, #1E3A5F 0%, #2E5A88 100%);
        color: #FDE68A;
        display: inline-flex;
        align-items: center;
        justify-content: center;
        font-size: 1.25rem;
        font-weight: 800;
        flex-shrink: 0;
    }
    .brand-text-main {
        font-size: 1.15rem;
        font-weight: 900;
        color: var(--brand-blue);
        line-height: 1.15;
    }
    .brand-text-sub {
        font-size: 0.72rem;
        color: var(--brand-gold);
        font-weight: 700;
        letter-spacing: 0.5px;
    }

    /* قسم البداية (Hero Section) */
    .hero-eyebrow {
        display: inline-flex;
        align-items: center;
        gap: 6px;
        background: #FEF3C7;
        color: #92400E;
        border: 1px solid #FDE68A;
        padding: 5px 14px;
        border-radius: 999px;
        font-size: 0.82rem;
        font-weight: 700;
        margin-bottom: 1rem;
    }
    .hero-headline {
        font-size: 2.35rem;
        font-weight: 900;
        color: var(--ink-primary);
        line-height: 1.3;
        margin: 0 0 1rem 0;
    }
    .hero-headline span {
        color: var(--brand-gold);
    }
    .hero-desc {
        font-size: 1.06rem;
        color: var(--ink-secondary);
        line-height: 1.85;
        margin-bottom: 1.5rem;
    }

    /* بطاقة العرض المرئية بجانب الـ Hero */
    .hero-visual-card {
        background: linear-gradient(145deg, #1E3A5F 0%, #13253D 65%, #2B2118 100%);
        border-radius: 22px;
        padding: 1.8rem;
        color: #FFFFFF;
        box-shadow: 0 18px 42px rgba(30, 58, 95, 0.22);
        position: relative;
        overflow: hidden;
        border: 1px solid rgba(253, 230, 138, 0.25);
    }
    .hero-visual-top {
        display: flex;
        justify-content: space-between;
        align-items: center;
        margin-bottom: 1.1rem;
    }
    .hero-visual-pill {
        background: rgba(255, 255, 255, 0.12);
        border: 1px solid rgba(255, 255, 255, 0.2);
        color: #FDE68A;
        font-size: 0.78rem;
        font-weight: 700;
        padding: 4px 12px;
        border-radius: 999px;
    }
    .hero-poem-quote {
        font-family: 'Amiri', serif !important;
        font-size: 1.48rem;
        line-height: 2.05;
        color: #FFFDF7;
        background: rgba(255, 255, 255, 0.06);
        border-right: 4px solid #F59E0B;
        border-radius: 12px;
        padding: 1rem 1.2rem;
        margin-bottom: 1.2rem;
    }
    .hero-mini-stats {
        display: grid;
        grid-template-columns: repeat(3, 1fr);
        gap: 10px;
    }
    .hero-mini-box {
        background: rgba(255, 255, 255, 0.08);
        border: 1px solid rgba(255, 255, 255, 0.14);
        border-radius: 12px;
        padding: 10px 8px;
        text-align: center;
    }
    .hero-mini-num {
        font-size: 1.35rem;
        font-weight: 800;
        color: #FDE68A;
        line-height: 1.1;
    }
    .hero-mini-lbl {
        font-size: 0.75rem;
        color: #CBD5E1;
        margin-top: 3px;
    }

    /* عناوين الأقسام (Section Headers) */
    .section-head {
        text-align: center;
        margin: 2.4rem 0 1.6rem 0;
    }
    .section-head h2 {
        font-size: 1.75rem;
        font-weight: 900;
        color: var(--ink-primary);
        margin: 0 0 0.4rem 0;
    }
    .section-head p {
        font-size: 1rem;
        color: var(--ink-secondary);
        margin: 0 auto;
        max-width: 640px;
    }

    /* تنسيق حاويات البطاقات */
    div[data-testid="stVerticalBlockBorderWrapper"] {
        background-color: var(--bg-card) !important;
        border: 1px solid var(--border-soft) !important;
        border-radius: 18px !important;
        padding: 0.45rem !important;
        box-shadow: var(--shadow-card) !important;
        transition: transform 0.2s ease, box-shadow 0.2s ease, border-color 0.2s ease !important;
    }
    div[data-testid="stVerticalBlockBorderWrapper"]:hover {
        transform: translateY(-3px);
        box-shadow: var(--shadow-hover) !important;
        border-color: #D6C9B4 !important;
    }

    /* محتوى البطاقة التفاعلية */
    .feature-card-body {
        padding: 0.35rem 0.25rem 0.6rem 0.25rem;
        min-height: 185px;
    }
    .feature-top-row {
        display: flex;
        justify-content: space-between;
        align-items: center;
        margin-bottom: 0.85rem;
    }
    .feature-icon-box {
        width: 46px;
        height: 46px;
        border-radius: 12px;
        display: inline-flex;
        align-items: center;
        justify-content: center;
        font-size: 1.45rem;
    }
    .badge-pill {
        display: inline-block;
        font-size: 0.74rem;
        font-weight: 800;
        padding: 4px 11px;
        border-radius: 999px;
    }
    .badge-amber  { background: #FEF3C7; color: #92400E; }
    .badge-blue   { background: #DBEAFE; color: #1E40AF; }
    .badge-teal   { background: #CCFBF1; color: #115E59; }
    .badge-purple { background: #EDE9FE; color: #5B21B6; }
    .badge-rose   { background: #FFE4E6; color: #9F1239; }
    .badge-emerald{ background: #D1FAE5; color: #065F46; }

    .feature-title {
        font-size: 1.15rem;
        font-weight: 800;
        color: var(--ink-primary);
        margin: 0 0 0.2rem 0;
    }
    .feature-subtitle {
        font-size: 0.82rem;
        font-weight: 700;
        color: var(--brand-gold);
        margin: 0 0 0.55rem 0;
    }
    .feature-desc {
        font-size: 0.9rem;
        color: var(--ink-secondary);
        line-height: 1.65;
        margin: 0;
    }

    /* الأزرار (Primary / Secondary) */
    .stButton > button[kind="primary"],
    .stFormSubmitButton > button[kind="primary"] {
        background: linear-gradient(135deg, #1E3A5F 0%, #274C77 100%) !important;
        color: #FFFFFF !important;
        border: none !important;
        border-radius: 12px !important;
        font-weight: 700 !important;
        padding: 0.58rem 1.2rem !important;
        box-shadow: 0 4px 14px rgba(30, 58, 95, 0.20) !important;
        transition: all 0.2s ease !important;
    }
    .stButton > button[kind="primary"]:hover,
    .stFormSubmitButton > button[kind="primary"]:hover {
        background: linear-gradient(135deg, #142842 0%, #1E3A5F 100%) !important;
        box-shadow: 0 6px 18px rgba(30, 58, 95, 0.28) !important;
    }
    .stButton > button[kind="secondary"],
    .stDownloadButton > button {
        background: #F8F7F4 !important;
        color: var(--brand-blue) !important;
        border: 1px solid #DCD5C7 !important;
        border-radius: 11px !important;
        font-weight: 700 !important;
        transition: all 0.2s ease !important;
    }
    .stButton > button[kind="secondary"]:hover,
    .stDownloadButton > button:hover {
        background: #FEF3C7 !important;
        border-color: #D97706 !important;
        color: #92400E !important;
    }

    /* حقول الإدخال والكتابة الشعرية */
    .stTextArea textarea {
        font-family: 'Amiri', 'Cairo', serif !important;
        font-size: 1.38rem !important;
        line-height: 2.1 !important;
        background-color: #FFFFFF !important;
        color: #162133 !important;
        border: 1.5px solid #DCD5C7 !important;
        border-radius: 14px !important;
        padding: 1rem 1.2rem !important;
        direction: rtl;
        text-align: right;
    }
    .stTextArea textarea:focus, .stTextInput input:focus {
        border-color: var(--brand-blue) !important;
        box-shadow: 0 0 0 2px rgba(30, 58, 95, 0.14) !important;
    }
    .stTextInput input, div[data-baseweb="select"] > div {
        background-color: #FFFFFF !important;
        border: 1px solid #DCD5C7 !important;
        border-radius: 10px !important;
        color: #162133 !important;
        direction: rtl;
        text-align: right;
    }

    /* التبويبات (Tabs) */
    .stTabs [data-baseweb="tab-list"] {
        gap: 6px;
        background: #EFECE5;
        padding: 6px;
        border-radius: 13px;
    }
    .stTabs [data-baseweb="tab"] {
        border-radius: 9px !important;
        padding: 8px 16px !important;
        color: #526075 !important;
        font-weight: 700 !important;
    }
    .stTabs [aria-selected="true"] {
        background: #FFFFFF !important;
        color: #1E3A5F !important;
        box-shadow: 0 2px 8px rgba(0, 0, 0, 0.06);
    }
    .stTabs [data-baseweb="tab-highlight"] {
        display: none !important;
    }

    /* ترويسة صفحات الأدوات */
    .tool-header-card {
        background: #FFFFFF;
        border: 1px solid var(--border-soft);
        border-right: 5px solid var(--brand-gold);
        border-radius: 16px;
        padding: 1.3rem 1.5rem;
        margin-bottom: 1.2rem;
        box-shadow: var(--shadow-card);
    }
    .tool-header-card h2 {
        margin: 0.35rem 0 0.25rem 0;
        font-size: 1.55rem;
        font-weight: 900;
        color: var(--ink-primary);
    }
    .tool-header-card p {
        margin: 0;
        color: var(--ink-secondary);
        font-size: 0.96rem;
    }

    /* بطاقات الإحصائيات والنتائج */
    .metric-grid {
        display: grid;
        grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
        gap: 12px;
        margin: 0.8rem 0 1.2rem 0;
    }
    .metric-box {
        background: #FFFFFF;
        border: 1px solid var(--border-soft);
        border-radius: 14px;
        padding: 1rem;
        text-align: center;
        box-shadow: 0 2px 10px rgba(0, 0, 0, 0.03);
    }
    .metric-box-label {
        font-size: 0.82rem;
        color: var(--ink-secondary);
        margin-bottom: 5px;
    }
    .metric-box-value {
        font-size: 1.22rem;
        font-weight: 800;
        color: var(--brand-blue);
    }

    .info-card {
        background: #FFFFFF;
        border: 1px solid var(--border-soft);
        border-right: 4px solid var(--brand-blue);
        border-radius: 14px;
        padding: 1.1rem 1.3rem;
        margin-bottom: 1rem;
    }
    .info-card-title {
        font-size: 0.85rem;
        font-weight: 800;
        color: var(--brand-gold);
        margin-bottom: 0.35rem;
    }
    .info-card-body {
        font-size: 0.98rem;
        color: var(--ink-primary);
        line-height: 1.75;
    }

    .poem-card {
        font-family: 'Amiri', serif !important;
        font-size: 1.35rem;
        background: #FCFBF8;
        border: 1px solid var(--border-soft);
        border-right: 4px solid var(--brand-gold);
        border-radius: 14px;
        padding: 1.2rem 1.4rem;
        margin-bottom: 0.9rem;
        white-space: pre-line;
        line-height: 2.15;
        color: var(--ink-primary);
    }
    .tag-row {
        display: flex;
        flex-wrap: wrap;
        gap: 8px;
        margin-bottom: 0.85rem;
    }
    .tag-pill {
        font-size: 0.78rem;
        font-weight: 700;
        background: #F1F5F9;
        border: 1px solid #CBD5E1;
        color: #1E3A5F;
        padding: 4px 11px;
        border-radius: 999px;
    }

    /* صناديق الترجمة */
    .translation-box {
        background: #FFFFFF;
        border: 1px solid var(--border-soft);
        border-radius: 14px;
        padding: 1.25rem 1.4rem;
        direction: ltr;
        text-align: left;
        line-height: 1.85;
        font-size: 1.02rem;
        color: #1E293B;
        min-height: 130px;
    }
    .lang-header {
        font-size: 0.8rem;
        font-weight: 800;
        text-transform: uppercase;
        letter-spacing: 0.7px;
        color: var(--brand-gold);
        margin-bottom: 0.55rem;
        direction: ltr;
        text-align: left;
    }

    /* قسم حول المشروع */
    .about-box {
        background: #FFFFFF;
        border: 1px solid var(--border-soft);
        border-radius: 20px;
        padding: 2rem;
        margin-top: 2.2rem;
        box-shadow: var(--shadow-card);
    }
    .about-grid {
        display: grid;
        grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
        gap: 1.2rem;
        margin-top: 1.2rem;
    }
    .about-pillar {
        background: #F8F7F4;
        border-radius: 14px;
        padding: 1.1rem 1.2rem;
        border: 1px solid var(--border-soft);
    }
    .about-pillar h4 {
        margin: 0 0 0.4rem 0;
        font-size: 1rem;
        font-weight: 800;
        color: var(--brand-blue);
    }
    .about-pillar p {
        margin: 0;
        font-size: 0.88rem;
        color: var(--ink-secondary);
        line-height: 1.65;
    }

    /* قسم مؤسس المشروع (بأسلوب Tamazight For All) */
    .founder-section {
        background: linear-gradient(135deg, #FFFFFF 0%, #FDFBF7 100%);
        border: 1px solid var(--border-soft);
        border-top: 4px solid var(--brand-blue);
        border-radius: 22px;
        padding: 2.2rem 2.4rem;
        margin-top: 2rem;
        box-shadow: var(--shadow-card);
    }
    .founder-layout {
        display: flex;
        flex-direction: row;
        align-items: center;
        gap: 2.2rem;
    }
    .founder-avatar-col {
        flex-shrink: 0;
        text-align: center;
    }
    .founder-photo {
        width: 175px;
        height: 175px;
        border-radius: 22px;
        object-fit: cover;
        border: 4px solid #FDE68A;
        box-shadow: 0 12px 28px rgba(30, 58, 95, 0.18);
    }
    .founder-monogram {
        width: 170px;
        height: 170px;
        border-radius: 24px;
        background: linear-gradient(145deg, #1E3A5F 0%, #13253D 65%, #3B2A1A 100%);
        border: 3px solid #EAB308;
        box-shadow: 0 14px 30px rgba(30, 58, 95, 0.22);
        display: flex;
        flex-direction: column;
        align-items: center;
        justify-content: center;
        color: #FDE68A;
    }
    .founder-monogram-letters {
        font-family: 'Amiri', serif !important;
        font-size: 3.4rem;
        font-weight: 700;
        line-height: 1.1;
    }
    .founder-monogram-sub {
        font-size: 0.72rem;
        letter-spacing: 2.2px;
        color: #CBD5E1;
        margin-top: 6px;
        font-weight: 700;
    }
    .founder-content {
        flex: 1;
    }
    .founder-name {
        font-size: 1.75rem;
        font-weight: 900;
        color: var(--ink-primary);
        margin: 0.45rem 0 0.15rem 0;
        line-height: 1.25;
    }
    .founder-latin {
        font-size: 0.92rem;
        font-weight: 700;
        color: var(--brand-gold);
        margin: 0 0 0.9rem 0;
        letter-spacing: 0.4px;
    }
    .founder-bio {
        font-size: 0.98rem;
        color: var(--ink-secondary);
        line-height: 1.85;
        margin: 0 0 1.1rem 0;
    }
    .founder-tags {
        display: flex;
        flex-wrap: wrap;
        gap: 8px;
    }
    .founder-tag {
        font-size: 0.8rem;
        font-weight: 700;
        background: #F1F5F9;
        color: var(--brand-blue);
        border: 1px solid #DBEAFE;
        padding: 5px 13px;
        border-radius: 999px;
    }

    /* التذييل السفلي */
    .site-footer {
        margin-top: 3rem;
        padding: 1.7rem 1.2rem;
        background: #162133;
        color: #E2E8F0;
        border-radius: 18px;
        text-align: center;
    }
    .site-footer-brand {
        font-size: 1.15rem;
        font-weight: 800;
        color: #FDE68A;
        margin-bottom: 0.4rem;
    }
    .site-footer-text {
        font-size: 0.86rem;
        color: #94A3B8;
        margin: 0;
        line-height: 1.7;
    }

    .secure-badge {
        padding: 8px 12px;
        border-radius: 10px;
        font-size: 0.82rem;
        margin: 6px 0 10px 0;
        border: 1px solid #BBF7D0;
        background: #F0FDF4;
        color: #166534;
        font-weight: 600;
    }
    .warn-badge {
        padding: 8px 12px;
        border-radius: 10px;
        font-size: 0.82rem;
        margin: 6px 0 10px 0;
        border: 1px solid #FDE68A;
        background: #FFFBEB;
        color: #92400E;
        font-weight: 600;
    }

    .stCodeBlock {
        direction: ltr;
        text-align: left;
    }

    @media (max-width: 768px) {
        .hero-headline {
            font-size: 1.7rem;
        }
        .feature-card-body {
            min-height: auto;
        }
        .founder-section {
            padding: 1.5rem 1.25rem;
        }
        .founder-layout {
            flex-direction: column;
            text-align: center;
            gap: 1.3rem;
        }
        .founder-content, .founder-bio, .founder-name, .founder-latin {
            text-align: center;
        }
        .founder-tags {
            justify-content: center;
        }
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
        self.status_message = f"قاعدة SQLite المحلية ({sqlite_path})"
        self.mongo_db = None

        if backend == "mongodb" and self.mongo_uri:
            if not PYMONGO_AVAILABLE:
                self.status_message = "مكتبة pymongo غير مثبتة؛ تم التحويل إلى SQLite."
                self._init_sqlite()
            else:
                try:
                    client = get_cached_mongo_client(self.mongo_uri)
                    self.mongo_db = client[self.mongo_db_name]
                    self.active_mode = "mongodb"
                    self.status_message = f"متصل سحابياً بـ {self.mongo_db_name}"
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
# 4. المحلل المحلي الاحتياطي
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
            "cultural_context": "فعّل التحليل الذكي (AI Mode) من القائمة الجانبية للحصول على التشكيل الصوتي الدقيق، الشرح الثقافي، والترجمة الأدبية.",
            "recommended_azawan": "لبياظ (تقديري)",
            "lines": details,
            "glossary": [],
            "english_translation": "Enable AI Mode to generate poetic English translation.",
            "french_translation": "Activez le mode IA pour générer la traduction poétique en français."
        }


# ==========================================
# 5. دوال الذكاء الاصطناعي (Gemini)
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
            "كر (Karr) — الفخر والوقار": {
                "mood": "Epic, noble, deep desert resonance, proud",
                "instruments": "Tidinit (Saharan lute), deep Tbal drums, warm ambient synth",
                "bpm": 85
            },
            "فاغو (Faghu) — الحماس والإيقاع": {
                "mood": "Energetic, triumphant, rhythmic, uplifting",
                "instruments": "Fast Tidinit riffs, Ardin harp, handclaps, modern Afro-desert percussion",
                "bpm": 115
            },
            "لبياظ (Labyad) — الحنين والغزل": {
                "mood": "Melancholic, romantic, nostalgic, soulful",
                "instruments": "Soft Ardin harp, acoustic Tidinit, warm cello pad, emotional vocals",
                "bpm": 75
            },
            "لكحال (Lakhhal) — العمق والروحانية": {
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
# 7. تهيئة الحالة والدوال المساعدة للتنقل
# ==========================================
local_engine = LocalHassaniyaEngine()
director = AzawanMusicDirector()

SAMPLES = {
    "كاف": "الصحرا دار الكرم والجود\nفيها الخيمة والگلب الصافي\nتاريخ أجدادنا المعهود\nيبقى في كل زمن وافي",
    "تبراع": "يا گلب اصبر لا تلوم\nالزين يبان ف كل يوم",
}

FUSION_STYLES = [
    "World Music Fusion",
    "Desert Blues & Acoustic",
    "Cinematic Orchestral",
    "Modern Afro-Saharan",
    "Chill Lo-Fi Desert",
]

VOCAL_TYPES = [
    "Deep soulful male Hassaniya vocals",
    "Expressive traditional female Hassaniya vocals",
    "Duet male and female traditional vocals",
    "Traditional chorus with lead vocalist",
]

if "current_view" not in st.session_state:
    st.session_state["current_view"] = "home"
if "expand_audio" not in st.session_state:
    st.session_state["expand_audio"] = False
if "poem_input_text" not in st.session_state:
    st.session_state["poem_input_text"] = ""
if "azawan_mode" not in st.session_state:
    st.session_state["azawan_mode"] = list(director.azawan_modes.keys())[2]
if "fusion_style" not in st.session_state:
    st.session_state["fusion_style"] = FUSION_STYLES[0]
if "vocal_type" not in st.session_state:
    st.session_state["vocal_type"] = VOCAL_TYPES[0]


def go_to(view_name: str, open_audio: bool = False):
    st.session_state["current_view"] = view_name
    st.session_state["expand_audio"] = open_audio


def set_poem_text(text: str):
    st.session_state["poem_input_text"] = text


def load_poem_into_lab(record: Dict):
    st.session_state["poem_input_text"] = record["poem_text"]
    st.session_state["analysis_result"] = record["analysis"]
    st.session_state["analysis_source"] = f"أرشيف ({record.get('source_engine', 'Saved')})"
    st.session_state["current_view"] = "lab"
    st.session_state["expand_audio"] = False


# ==========================================
# 8. الشريط الجانبي (إعدادات النظام المخفية بأمان)
# ==========================================
on_cloud = is_running_on_cloud()
secret_mongo_uri = get_secret_safe("MONGODB_URI", "")
secret_mongo_db = get_secret_safe("MONGODB_DB_NAME", "albidan_corpus")
secret_gemini_key = get_secret_safe("GEMINI_API_KEY", "")

with st.sidebar:
    st.markdown("### ⚙️ إعدادات المنصة")
    st.caption("إدارة الذكاء الاصطناعي والاتصال السحابي")

    with st.expander("🧠 محرك الذكاء الاصطناعي", expanded=True):
        if secret_gemini_key:
            api_key = secret_gemini_key
            st.markdown(
                '<div class="secure-badge">🔑 مفتاح Gemini مُفعّل بأمان</div>',
                unsafe_allow_html=True
            )
        else:
            api_key = st.text_input(
                "مفتاح Gemini API:",
                value="",
                type="password",
                placeholder="أدخل مفتاح API..."
            )

        available_models = [
            "gemini-3.8-flash",
            "gemini-3.5-flash-lite",
            "gemini-3.1-pro-preview",
        ]
        model_name = st.selectbox("نموذج الذكاء الاصطناعي:", options=available_models, index=0)
        use_ai = st.toggle("تفعيل التحليل الذكي (AI)", value=bool(api_key))

    with st.expander("🗄️ قاعدة البيانات", expanded=False):
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
                mongo_uri = secret_mongo_uri
            else:
                mongo_uri = st.text_input(
                    "رابط MongoDB:",
                    value="",
                    type="password",
                    placeholder="أدخل الرابط للتجربة المحلية..."
                )
        else:
            backend_code = "sqlite"
            mongo_uri = ""

        archive = ArchiveManager(
            backend=backend_code,
            mongo_uri=mongo_uri,
            mongo_db_name=secret_mongo_db
        )

        badge_cls = "secure-badge" if archive.active_mode == "mongodb" else "warn-badge"
        badge_icon = "🔒" if archive.active_mode == "mongodb" else "💾"
        st.markdown(
            f'<div class="{badge_cls}">{badge_icon} {html.escape(archive.status_message)}</div>',
            unsafe_allow_html=True
        )

stats = archive.get_stats()


# ==========================================
# 9. شريط التنقل العلوي الموحد (Top Navbar)
# ==========================================
nav_c0, nav_c1, nav_c2, nav_c3, nav_c4, nav_c5 = st.columns([2.3, 1.05, 1.15, 1.1, 1.05, 1.15])

with nav_c0:
    st.markdown(
        """
        <div class="brand-logo">
            <div class="brand-icon">🐪</div>
            <div>
                <div class="brand-text-main">مختبر البيظان</div>
                <div class="brand-text-sub">ALBIDAN AI LAB</div>
            </div>
        </div>
        """,
        unsafe_allow_html=True
    )

view = st.session_state["current_view"]
nav_c1.button(
    "الرئيسية",
    key="nav_home",
    type="primary" if view == "home" else "secondary",
    on_click=go_to,
    args=("home",),
    use_container_width=True
)
nav_c2.button(
    "المختبر العروضي",
    key="nav_lab",
    type="primary" if view == "lab" else "secondary",
    on_click=go_to,
    args=("lab",),
    use_container_width=True
)
nav_c3.button(
    "استوديو أزوان",
    key="nav_azawan",
    type="primary" if view == "azawan" else "secondary",
    on_click=go_to,
    args=("azawan",),
    use_container_width=True
)
nav_c4.button(
    "المدونة",
    key="nav_archive",
    type="primary" if view == "archive" else "secondary",
    on_click=go_to,
    args=("archive",),
    use_container_width=True
)
nav_c5.button(
    "المعجم",
    key="nav_glossary",
    type="primary" if view == "glossary" else "secondary",
    on_click=go_to,
    args=("glossary",),
    use_container_width=True
)

st.markdown("<div style='height: 10px; border-bottom: 1px solid #E7E2D8; margin-bottom: 1.4rem;'></div>", unsafe_allow_html=True)


# ==========================================
# الصفحة الرئيسية (Home)
# ==========================================
if view == "home":
    hero_right, hero_left = st.columns([1.25, 1], gap="large")

    with hero_right:
        st.markdown(
            """
            <div class="hero-eyebrow">✨ منصة التراث الحساني والذكاء الاصطناعي</div>
            <h1 class="hero-headline">اكتشف جمال <span>الشعر الحساني</span> وهندسة أزوان للعالمية</h1>
            <p class="hero-desc">
                من التقطيع العروضي الدقيق لبحور لغنى والتبراع، إلى التفريغ الصوتي الآلي وبناء المعجم الحساني المتنامي وإخراج الأعمال الغنائية التوليدية بمقامات أزوان الأصيلة.
            </p>
            """,
            unsafe_allow_html=True
        )
        cta1, cta2 = st.columns(2)
        cta1.button(
            "🚀 ابدأ التحليل الآن",
            type="primary",
            on_click=go_to,
            args=("lab", False),
            use_container_width=True
        )
        cta2.button(
            "📚 تصفح المدونة الحسانية",
            type="secondary",
            on_click=go_to,
            args=("archive",),
            use_container_width=True
        )

    with hero_left:
        st.markdown(
            f"""
            <div class="hero-visual-card">
                <div class="hero-visual-top">
                    <span class="hero-visual-pill">🏜️ نموذج كاف — بحر لبتيت التام</span>
                    <span style="font-size: 0.8rem; color: #CBD5E1;">8 متحركات</span>
                </div>
                <div class="hero-poem-quote">
                    الصحرا دار الكرم والجود<br>
                    فيها الخيمة والگلب الصافي<br>
                    تاريخ أجدادنا المعهود<br>
                    يبقى في كل زمن وافي
                </div>
                <div class="hero-mini-stats">
                    <div class="hero-mini-box">
                        <div class="hero-mini-num">{stats['poems_count']}</div>
                        <div class="hero-mini-lbl">قصيدة موثقة</div>
                    </div>
                    <div class="hero-mini-box">
                        <div class="hero-mini-num">{stats['lines_count']}</div>
                        <div class="hero-mini-lbl">شطر (تافلويت)</div>
                    </div>
                    <div class="hero-mini-box">
                        <div class="hero-mini-num">{stats['terms_count']}</div>
                        <div class="hero-mini-lbl">مفردة معجمية</div>
                    </div>
                </div>
            </div>
            """,
            unsafe_allow_html=True
        )

    # شبكة البطاقات التفاعلية
    st.markdown(
        """
        <div class="section-head">
            <h2>أدوات ومختبرات المنصة</h2>
            <p>اختر الأداة التي تريدها وابدأ مباشرة في التوثيق والتحليل والإبداع الموسيقي الحساني مجاناً</p>
        </div>
        """,
        unsafe_allow_html=True
    )

    cards_row1 = [
        {
            "badge": "أداة ذكية",
            "badge_cls": "badge-blue",
            "icon": "🔬",
            "icon_bg": "#EFF6FF",
            "title": "المُحلل العروضي الحساني",
            "sub": "تقطيع صوتي وعدّ المتحركات",
            "desc": "أدخل أي كاف أو طلعة أو تبراع للحصول على التشكيل الصوتي الحساني وتحديد البحر والروي والغرض الثقافي.",
            "btn": "ابدأ التحليل ←",
            "target": ("lab", False),
            "key": "card_lab"
        },
        {
            "badge": "ذكاء صوتي",
            "badge_cls": "badge-amber",
            "icon": "🎙️",
            "icon_bg": "#FFFBEB",
            "title": "التفريغ الصوتي للتراث",
            "sub": "من الصوت إلى نص بحرف الگاف",
            "desc": "ارفع تسجيلاً صوتياً (MP3 / WAV / M4A) لتحويله تلقائياً إلى أبيات حسانية مضبوطة ومرتبة شطراً بشطر.",
            "btn": "ارفع تسجيلاً ←",
            "target": ("lab", True),
            "key": "card_audio"
        },
        {
            "badge": "إبداع موسيقي",
            "badge_cls": "badge-purple",
            "icon": "🎵",
            "icon_bg": "#F5F3FF",
            "title": "استوديو أزوان التوليدي",
            "sub": "مقامات كر • فاغو • لبياظ • لكحال",
            "desc": "حوّل القصائد الحسانية إلى وصف موسيقي احترافي وكلمات منسقة جاهزة للغناء التوليدي بآلات التيدينيت والآردين.",
            "btn": "افتح الاستوديو ←",
            "target": ("azawan", False),
            "key": "card_azawan"
        },
    ]

    cards_row2 = [
        {
            "badge": "تراث حي",
            "badge_cls": "badge-emerald",
            "icon": "📚",
            "icon_bg": "#ECFDF5",
            "title": "المدونة الحسانية المفتوحة",
            "sub": f"{stats['poems_count']} قصيدة • {stats['lines_count']} شطر",
            "desc": "أرشيف سحابي منظم للقصائد المحللة حسب الشاعر والمنطقة والبحر، مع إمكانية التصدير بصيغة JSONL.",
            "btn": "استكشف المدونة ←",
            "target": ("archive", False),
            "key": "card_archive"
        },
        {
            "badge": "معجم متنامي",
            "badge_cls": "badge-teal",
            "icon": "📖",
            "icon_bg": "#F0FDFA",
            "title": "المعجم الحساني التفاعلي",
            "sub": f"{stats['terms_count']} مفردة موثقة",
            "desc": "قاموس يتوسع تلقائياً مع كل قصيدة تُحفظ، يشرح المفردات الحسانية الأصيلة بالعربية الفصحى والإنجليزية.",
            "btn": "تصفح المعجم ←",
            "target": ("glossary", False),
            "key": "card_glossary"
        },
        {
            "badge": "ترجمة عالمية",
            "badge_cls": "badge-rose",
            "icon": "🌍",
            "icon_bg": "#FFF1F2",
            "title": "الترجمة الشعرية العالمية",
            "sub": "الإنجليزية والفرنسية الأدبية",
            "desc": "انقل جماليات الشعر الحساني ورمزية الخيمة والصحراء إلى الجمهور العالمي بترجمة شعرية تحافظ على الروح والمعنى.",
            "btn": "جرّب الترجمة ←",
            "target": ("lab", False),
            "key": "card_trans"
        },
    ]

    for row_cards in (cards_row1, cards_row2):
        cols = st.columns(3, gap="medium")
        for col, card in zip(cols, row_cards):
            with col:
                with st.container(border=True):
                    st.markdown(
                        f"""
                        <div class="feature-card-body">
                            <div class="feature-top-row">
                                <span class="feature-icon-box" style="background: {card['icon_bg']};">{card['icon']}</span>
                                <span class="badge-pill {card['badge_cls']}">{card['badge']}</span>
                            </div>
                            <h3 class="feature-title">{card['title']}</h3>
                            <div class="feature-subtitle">{card['sub']}</div>
                            <p class="feature-desc">{card['desc']}</p>
                        </div>
                        """,
                        unsafe_allow_html=True
                    )
                    st.button(
                        card["btn"],
                        key=card["key"],
                        on_click=go_to,
                        args=card["target"],
                        use_container_width=True
                    )
        st.markdown("<div style='height: 12px;'></div>", unsafe_allow_html=True)

    # قسم حول المشروع
    st.markdown(
        """
        <div class="about-box">
            <span class="badge-pill badge-amber">حول المشروع</span>
            <h2 style="margin: 0.5rem 0 0.5rem 0; font-size: 1.55rem; font-weight: 900; color: #162133;">
                لماذا مختبر البيظان (ALBIDAN AI Lab)؟
            </h2>
            <p style="color: #526075; font-size: 0.98rem; line-height: 1.8; margin: 0;">
                مبادرة رقمية رائدة تهدف إلى صون التراث الشعري والموسيقي الحساني وتوظيف أحدث تقنيات الذكاء الاصطناعي لخدمة الباحثين، الشعراء، وعشاق الثقافة الصحراوية في المغرب وموريتانيا والعالم.
            </p>
            <div class="about-grid">
                <div class="about-pillar">
                    <h4>⚖️ دقة العروض الحساني</h4>
                    <p>مراعاة ظاهرة الابتداء بالساكن وعدّ المتحركات لتمييز السغير، لبتيت الناقص والتام، والبت لكبير.</p>
                </div>
                <div class="about-pillar">
                    <h4>🏛️ ذاكرة رقمية مفتوحة</h4>
                    <p>توثيق سحابي دائم للقصائد والمفردات النادرة وتصديرها بصيغ معيارية قابلة للبحث والتطوير.</p>
                </div>
                <div class="about-pillar">
                    <h4>🎶 جسر نحو العالمية</h4>
                    <p>دمج مقامات أزوان الأصيلة مع أدوات الترجمة الأدبية والغناء التوليدي لإيصال الإبداع الحساني للعالم.</p>
                </div>
            </div>
        </div>
        """,
        unsafe_allow_html=True
    )

    # قسم مؤسس المشروع (أڭــار الحبيب)
    founder_avatar = get_founder_avatar_html()
    st.markdown(
        f"""
        <div class="founder-section">
            <div class="founder-layout">
                <div class="founder-avatar-col">
                    {founder_avatar}
                </div>
                <div class="founder-content">
                    <span class="badge-pill badge-blue">مؤسس المشروع</span>
                    <h2 class="founder-name">أڭــار الحبيب</h2>
                    <div class="founder-latin">Aggar El Habib • مؤسس ومطور مختبر البيظان</div>
                    <p class="founder-bio">
                        باحث ومطور مهتم بالشعر الشعبي الحساني وتقنيات الذكاء الاصطناعي من إقليم بوجدور بالصحراء المغربية. يكرّس جهوده لتوظيف البرمجة ومعالجة اللغات الطبيعية في توثيق وحفظ الذاكرة الشفهية الحسانية، وبناء أدوات ذكية للتحليل العروضي، المعجم الحساني المتنامي، وهندسة موسيقى أزوان لإيصال إبداعات ثقافة البيظان إلى الباحثين والجمهور العالمي.
                    </p>
                    <div class="founder-tags">
                        <span class="founder-tag">📜 الشعر الحساني والعروض</span>
                        <span class="founder-tag">🤖 الذكاء الاصطناعي وتطوير التطبيقات</span>
                        <span class="founder-tag">🎵 هندسة أزوان التوليدية</span>
                        <span class="founder-tag">🏛️ الرقمنة والأرشفة الثقافية</span>
                    </div>
                </div>
            </div>
        </div>
        """,
        unsafe_allow_html=True
    )


# ==========================================
# صفحة 1: المختبر العروضي والتفريغ الصوتي
# ==========================================
elif view == "lab":
    back_c, _ = st.columns([1.4, 5])
    back_c.button("→ العودة للرئيسية", on_click=go_to, args=("home",), use_container_width=True)

    st.markdown(
        """
        <div class="tool-header-card">
            <span class="badge-pill badge-blue">أداة ذكية • العروض والترجمة</span>
            <h2>المُحلل العروضي والتفريغ الصوتي الحساني</h2>
            <p>اكتب أبياتك الحسانية أو ارفع تسجيلاً صوتياً لتحصل على التقطيع الصوتي الدقيق، المعجم، والترجمة الأدبية.</p>
        </div>
        """,
        unsafe_allow_html=True
    )

    with st.expander(
        "🎙️ رفع تسجيل صوتي لقصيدة حسانية (MP3 / WAV / M4A) وتفريغه تلقائياً",
        expanded=st.session_state.get("expand_audio", False)
    ):
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
                transcribe_only_btn = col_t1.button("📝 تفريغ النص للمراجعة", use_container_width=True)
                transcribe_and_analyze_btn = col_t2.button("⚡ تفريغ وتحليل فوري", type="primary", use_container_width=True)

                if transcribe_only_btn or transcribe_and_analyze_btn:
                    if not api_key.strip():
                        st.warning("يرجى ضبط مفتاح Gemini API من القائمة الجانبية لتشغيل التفريغ الصوتي.")
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

    with st.container(border=True):
        q1, q2, q3, q4 = st.columns([2.6, 1.1, 1.1, 0.9])
        q1.markdown("**✍️ أدخل النص الشعري الحساني** *(ضع كل تافلويت في سطر مستقل)*")
        q2.button("✨ نموذج كاف", on_click=set_poem_text, args=(SAMPLES["كاف"],), use_container_width=True)
        q3.button("✨ نموذج تبراع", on_click=set_poem_text, args=(SAMPLES["تبراع"],), use_container_width=True)
        q4.button("🧹 مسح", on_click=set_poem_text, args=("",), use_container_width=True)

        poem_input = st.text_area(
            "النص الشعري:",
            key="poem_input_text",
            height=175,
            label_visibility="collapsed",
            placeholder="اكتب الكاف أو الطلعة أو التبراع هنا، أو اختر نموذجاً جاهزاً بالأعلى..."
        )

        analyze_btn = st.button("🚀 تحليل القصيدة وتوليد العمل العالمي", type="primary", use_container_width=True)

    if analyze_btn:
        if not poem_input.strip():
            st.warning("يرجى إدخال بيت شعري واحد على الأقل للبدء.")
        else:
            if use_ai and api_key.strip():
                with st.spinner("جاري التقطيع الصوتي الحساني واستخراج المعجم والترجمة الأدبية..."):
                    try:
                        st.session_state["analysis_result"] = analyze_with_gemini(
                            poem_input, api_key.strip(), model_name
                        )
                        st.session_state["analysis_source"] = f"AI ({model_name})"
                    except Exception as e:
                        st.error(f"تعذر الاتصال بـ Gemini API: {e}")
                        st.info("تم التحويل مؤقتاً للمحلل المحلي.")
                        st.session_state["analysis_result"] = local_engine.analyze(poem_input)
                        st.session_state["analysis_source"] = "Local"
            else:
                st.session_state["analysis_result"] = local_engine.analyze(poem_input)
                st.session_state["analysis_source"] = "Local"

    if "analysis_result" in st.session_state:
        res = st.session_state["analysis_result"]
        lines_list = [item["original_line"] for item in res["lines"]]
        music_data = director.generate_song_structure(
            lines_list,
            st.session_state["azawan_mode"],
            st.session_state["fusion_style"],
            st.session_state["vocal_type"]
        )

        st.markdown("<div style='height: 12px;'></div>", unsafe_allow_html=True)

        tab1, tab2, tab3, tab4 = st.tabs([
            "📊 العروض والتقطيع الصوتي",
            "🌍 الترجمة العالمية والمعجم",
            "🎵 هندسة أزوان",
            "💾 التوثيق والتصدير"
        ])

        with tab1:
            st.markdown(
                f"""
                <div class="metric-grid">
                    <div class="metric-box">
                        <div class="metric-box-label">تصنيف القطعة</div>
                        <div class="metric-box-value">{html.escape(str(res['poem_type']))}</div>
                    </div>
                    <div class="metric-box">
                        <div class="metric-box-label">البحر السائد</div>
                        <div class="metric-box-value">{html.escape(str(res['dominant_meter']))}</div>
                    </div>
                    <div class="metric-box">
                        <div class="metric-box-label">عدد الأشطر (تافلويت)</div>
                        <div class="metric-box-value">{len(res['lines'])}</div>
                    </div>
                </div>
                """,
                unsafe_allow_html=True
            )

            col_ctx, col_azw = st.columns(2)
            with col_ctx:
                st.markdown(
                    f"""
                    <div class="info-card">
                        <div class="info-card-title">🏜️ السياق الثقافي والغرض الشعري</div>
                        <div class="info-card-body">{html.escape(str(res['cultural_context']))}</div>
                    </div>
                    """,
                    unsafe_allow_html=True
                )
            with col_azw:
                st.markdown(
                    f"""
                    <div class="info-card">
                        <div class="info-card-title">🎶 ترشيح الذكاء الاصطناعي لمقام أزوان</div>
                        <div class="info-card-body">{html.escape(str(res['recommended_azawan']))}</div>
                    </div>
                    """,
                    unsafe_allow_html=True
                )

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
            col_en, col_fr = st.columns(2)
            with col_en:
                en_html = html.escape(res["english_translation"]).replace("\n", "<br>")
                st.markdown(
                    f"""
                    <div class="translation-box">
                        <div class="lang-header">🇬🇧 English Poetic Translation</div>
                        {en_html}
                    </div>
                    """,
                    unsafe_allow_html=True
                )
            with col_fr:
                fr_html = html.escape(res["french_translation"]).replace("\n", "<br>")
                st.markdown(
                    f"""
                    <div class="translation-box">
                        <div class="lang-header">🇫🇷 Traduction Poétique (Français)</div>
                        {fr_html}
                    </div>
                    """,
                    unsafe_allow_html=True
                )

            st.markdown("<div style='height: 16px;'></div>", unsafe_allow_html=True)
            st.markdown("#### 📖 المفردات الحسانية المستخرجة")
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
                st.info("فعّل التحليل الذكي (AI) لاستخراج شرح المفردات الحسانية تلقائياً.")

        with tab3:
            mc1, mc2, mc3 = st.columns(3)
            selected_mode = mc1.selectbox(
                "المقام الموسيقي (أزوان):",
                list(director.azawan_modes.keys()),
                key="azawan_mode"
            )
            fusion_style = mc2.selectbox(
                "النمط العالمي (Fusion):",
                FUSION_STYLES,
                key="fusion_style"
            )
            vocal_type = mc3.selectbox(
                "طبيعة الصوت الغنائي:",
                VOCAL_TYPES,
                key="vocal_type"
            )
            music_data = director.generate_song_structure(lines_list, selected_mode, fusion_style, vocal_type)

            st.markdown("**1. وصف النمط الموسيقي (Style Prompt):**")
            st.code(music_data["style_prompt"], language="text")

            st.markdown("**2. الكلمات المنسقة بالوسوم الموسيقية (Formatted Lyrics):**")
            st.code(music_data["formatted_lyrics"], language="text")

        with tab4:
            with st.container(border=True):
                st.markdown("#### 💾 توثيق القصيدة في المدونة السحابية")
                with st.form("save_poem_form", clear_on_submit=True):
                    fc1, fc2, fc3 = st.columns(3)
                    save_title = fc1.text_input("عنوان القصيدة:", placeholder="مثال: كاف في مدح الصحراء")
                    save_poet = fc2.text_input("الشاعر / الراوي:", placeholder="مثال: تراث شعبي أو اسم الشاعر")
                    save_region = fc3.text_input("المنطقة / المصدر:", value="الصحراء المغربية")
                    save_submitted = st.form_submit_button(
                        "📥 حفظ في المدونة وتحديث المعجم",
                        type="primary",
                        use_container_width=True
                    )

                    if save_submitted:
                        new_id = archive.save_poem(
                            title=save_title,
                            poet=save_poet,
                            region=save_region,
                            poem_text=poem_input,
                            analysis_res=res,
                            music_data=music_data,
                            azawan_mode=st.session_state["azawan_mode"],
                            source_engine=st.session_state.get("analysis_source", "Local"),
                        )
                        st.success(f"تم التوثيق بنجاح في الأرشيف (المعرّف: {new_id}) وتحديث المعجم الحساني!")

            export_payload = {
                "source_engine": st.session_state.get("analysis_source", "Local"),
                "poem_analysis": res,
                "azawan_studio": {
                    "selected_mode": st.session_state["azawan_mode"],
                    "fusion_style": st.session_state["fusion_style"],
                    "vocal_type": st.session_state["vocal_type"],
                    **music_data
                }
            }
            st.download_button(
                label="📥 تحميل ملف المشروع الكامل (JSON)",
                data=json.dumps(export_payload, ensure_ascii=False, indent=2),
                file_name="albidan_project.json",
                mime="application/json",
                use_container_width=True
            )


# ==========================================
# صفحة 2: استوديو أزوان المستقل
# ==========================================
elif view == "azawan":
    back_c, _ = st.columns([1.4, 5])
    back_c.button("→ العودة للرئيسية", on_click=go_to, args=("home",), use_container_width=True)

    st.markdown(
        """
        <div class="tool-header-card">
            <span class="badge-pill badge-purple">إبداع موسيقي • أزوان × Suno AI</span>
            <h2>استوديو أزوان والغناء التوليدي</h2>
            <p>صمّم الهوية الموسيقية للقصيدة الحسانية حسب المقامات التقليدية (كر، فاغو، لبياظ، لكحال) واحصل على أمر جاهز للتوليد.</p>
        </div>
        """,
        unsafe_allow_html=True
    )

    with st.container(border=True):
        s_col1, s_col2 = st.columns([2, 1])
        studio_text = s_col1.text_area(
            "✍️ الأبيات الحسانية المراد تلحينها (كل شطر في سطر):",
            value=st.session_state.get("poem_input_text") or SAMPLES["كاف"],
            height=190
        )
        with s_col2:
            s_mode = st.selectbox("المقام الموسيقي (أزوان):", list(director.azawan_modes.keys()), key="studio_mode")
            s_fusion = st.selectbox("النمط العالمي (Fusion):", FUSION_STYLES, key="studio_fusion")
            s_vocal = st.selectbox("طبيعة الصوت الغنائي:", VOCAL_TYPES, key="studio_vocal")

    studio_lines = [l.strip() for l in studio_text.split("\n") if l.strip()]
    if studio_lines:
        studio_music = director.generate_song_structure(studio_lines, s_mode, s_fusion, s_vocal)
        st.markdown("<div style='height: 10px;'></div>", unsafe_allow_html=True)

        m_left, m_right = st.columns(2)
        with m_left:
            with st.container(border=True):
                st.markdown(f"**🎛️ وصف النمط الموسيقي (Style Prompt — {studio_music['bpm']} BPM):**")
                st.code(studio_music["style_prompt"], language="text")
        with m_right:
            with st.container(border=True):
                st.markdown("**🎤 الكلمات المنسقة بالوسوم الموسيقية (Formatted Lyrics):**")
                st.code(studio_music["formatted_lyrics"], language="text")
    else:
        st.info("أدخل شطراً واحداً على الأقل لتوليد الوصف الموسيقي.")


# ==========================================
# صفحة 3: المدونة والأرشيف
# ==========================================
elif view == "archive":
    back_c, _ = st.columns([1.4, 5])
    back_c.button("→ العودة للرئيسية", on_click=go_to, args=("home",), use_container_width=True)

    st.markdown(
        f"""
        <div class="tool-header-card">
            <span class="badge-pill badge-emerald">تراث حي • {stats['poems_count']} قصيدة موثقة</span>
            <h2>المدونة الحسانية المفتوحة (أرشيف القصائد)</h2>
            <p>استعرض القصائد الحسانية المحللة والموثقة، ابحث بالبحر أو المنطقة، أو صدّر المدونة لتدريب نماذج الذكاء الاصطناعي.</p>
        </div>
        """,
        unsafe_allow_html=True
    )

    with st.container(border=True):
        f1, f2, f3 = st.columns([3, 1.4, 1.4])
        search_q = f1.text_input(
            "🔍 ابحث في المدونة:",
            placeholder="ابحث بكلمة، عنوان، شاعر، بحر، أو مدينة (بوجدور، العيون...)"
        )
        type_filter = f2.selectbox("تصنيف القطعة:", ["الكل", "تبراع", "كاف", "طلعة"])

        poems_list = archive.list_poems(search_query=search_q, type_filter=type_filter)

        with f3:
            st.markdown("<div style='height: 28px;'></div>", unsafe_allow_html=True)
            if poems_list:
                jsonl_content = "\n".join(json.dumps(p, ensure_ascii=False) for p in poems_list)
                st.download_button(
                    label="🤖 تصدير JSONL",
                    data=jsonl_content,
                    file_name="albidan_hassaniya_corpus.jsonl",
                    mime="application/jsonl",
                    use_container_width=True
                )

    st.markdown("<div style='height: 10px;'></div>", unsafe_allow_html=True)

    if not poems_list:
        st.info("الأرشيف فارغ حالياً أو لا توجد نتائج مطابقة. حلّل قصيدة في المختبر واحفظها لتظهر هنا.")
    else:
        for rec in poems_list:
            header_label = f"📜 {rec['title']}  —  {rec['poet']}  ({rec['created_at']})"
            with st.expander(header_label, expanded=False):
                st.markdown(
                    f"""
                    <div class="tag-row">
                        <span class="tag-pill">🏷️ {html.escape(str(rec['poem_type']))}</span>
                        <span class="tag-pill">⚖️ {html.escape(str(rec['dominant_meter']))}</span>
                        <span class="tag-pill">📍 {html.escape(str(rec['region']))}</span>
                        <span class="tag-pill">🎵 {html.escape(str(rec['azawan_mode']))}</span>
                    </div>
                    <div class="poem-card">{html.escape(rec['poem_text'])}</div>
                    """,
                    unsafe_allow_html=True
                )

                a_col1, a_col2 = st.columns(2)
                a_col1.button(
                    "🔄 فتح في المختبر",
                    key=f"load_{rec['id']}",
                    on_click=load_poem_into_lab,
                    args=(rec,),
                    type="primary",
                    use_container_width=True
                )
                if a_col2.button("🗑️ حذف من الأرشيف", key=f"del_{rec['id']}", use_container_width=True):
                    archive.delete_poem(rec["id"])
                    st.rerun()


# ==========================================
# صفحة 4: المعجم الحساني
# ==========================================
elif view == "glossary":
    back_c, _ = st.columns([1.4, 5])
    back_c.button("→ العودة للرئيسية", on_click=go_to, args=("home",), use_container_width=True)

    st.markdown(
        f"""
        <div class="tool-header-card">
            <span class="badge-pill badge-teal">معجم متنامي • {stats['terms_count']} مفردة</span>
            <h2>المعجم الحساني التفاعلي</h2>
            <p>موسوعة مفردات حسانية تُبنى وتُثرى تلقائياً من كل قصيدة يتم تحليلها وتوثيقها في المختبر.</p>
        </div>
        """,
        unsafe_allow_html=True
    )

    with st.container(border=True):
        c_search, c_dl = st.columns([3.5, 1.3])
        g_search = c_search.text_input(
            "🔍 ابحث في المعجم الحساني:",
            placeholder="اكتب مفردة حسانية أو معناها بالعربية أو الإنجليزية..."
        )
        glossary_items = archive.list_glossary(search_query=g_search)

        if glossary_items:
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
            with c_dl:
                st.markdown("<div style='height: 28px;'></div>", unsafe_allow_html=True)
                csv_bytes = gloss_df.to_csv(index=False).encode("utf-8-sig")
                st.download_button(
                    label="📥 تصدير CSV (Excel)",
                    data=csv_bytes,
                    file_name="albidan_hassaniya_glossary.csv",
                    mime="text/csv",
                    use_container_width=True
                )

    st.markdown("<div style='height: 10px;'></div>", unsafe_allow_html=True)

    if not glossary_items:
        st.info("لم تُضف مفردات بعد. عند حفظ أي قصيدة محللة بالذكاء الاصطناعي، تُضاف مفرداتها تلقائياً هنا.")
    else:
        st.dataframe(gloss_df, use_container_width=True, hide_index=True)


# ==========================================
# 10. التذييل السفلي (Footer)
# ==========================================
st.markdown(
    """
    <div class="site-footer">
        <div class="site-footer-brand">🐪 مختبر البيظان — ALBIDAN AI LAB</div>
        <p class="site-footer-text">
            منصة رقمية مكرّسة لصون الشعر الحساني، المعجم التراثي، وهندسة موسيقى أزوان للعالمية<br>
            © 2026 مختبر البيظان — فكرة وتطوير <strong>أڭــار الحبيب</strong>. جميع الحقوق محفوظة.
        </p>
    </div>
    """,
    unsafe_allow_html=True
)
