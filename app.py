# -*- coding: utf-8 -*-
# UsedCarAdvisor – ChatBot-First with In-Chat Questionnaire (Streamlit, single-file)
# Run: streamlit run app.py

import os
from dataclasses import dataclass
from typing import List, Dict, Any, Optional
import streamlit as st

# =========================
# הגדרות בסיסיות
# =========================
st.set_page_config(page_title="יועץ רכבים יד 2 – צ'אט עם שאלון", page_icon="🤖🚗", layout="centered")

RTL = """
<style>
html, body, [class*="css"] { direction: rtl; text-align: right; }
.block-container { padding-top: .6rem; max-width: 880px; }
.stChatMessage { text-align: right; }
</style>
"""
st.markdown(RTL, unsafe_allow_html=True)

# =========================
# כפתור התחל מחדש
# =========================
if st.sidebar.button("🔄 התחל מחדש"):
    for key in list(st.session_state.keys()):
        del st.session_state[key]
    st.experimental_rerun()

# =========================
# Questionnaire slots (מורחב ל~40)
# =========================
@dataclass
class Slot:
    key: str
    label: str
    prompt: str
    kind: str
    required: bool = True

SLOTS: List[Slot] = [
    Slot("budget_min", "תקציב מינימום (₪)", "מה התקציב המינימלי שלך בשקלים?", "int"),
    Slot("budget_max", "תקציב מקסימום (₪)", "מה התקציב המקסימלי שלך בשקלים?", "int"),
    Slot("body", "סוג רכב", "איזה סוג רכב אתה מחפש? (לדוגמה: משפחתי, קטן, ג'יפ)", "text"),
    Slot("character", "אופי רכב", "האם אתה מחפש רכב ספורטיבי או יומיומי?", "text"),
    Slot("usage", "שימוש עיקרי", "השימוש העיקרי יהיה בעיר, בין-עירוני או שטח?", "text"),
    Slot("priority", "עדיפות מרכזית", "מה הכי חשוב לך – אמינות, נוחות, ביצועים או עיצוב?", "text"),
    Slot("passengers", "מספר נוסעים ממוצע", "כמה נוסעים ייסעו ברכב?", "int"),
    Slot("fuel", "סוג דלק", "איזה סוג דלק תעדיף – בנזין, דיזל, היברידי או חשמלי?", "text"),
    Slot("year_min", "שנת ייצור מינימלית", "מאיזו שנת ייצור מינימלית תרצה?", "int"),
    Slot("km_per_year", "ק\"מ לשנה", "כמה ק\"מ אתה נוסע בערך בשנה?", "int"),
    Slot("gearbox", "תיבת הילוכים", "אוטומט או ידני?", "text"),
    Slot("gearbox_type", "סוג גיר אוטומט", "אם אוטומט – פלנטרי, רובוטי או CVT?", "text", required=False),
    Slot("region", "אזור בארץ", "באיזה אזור בארץ אתה גר?", "text"),
    Slot("engine_size", "נפח מנוע", "מה נפח המנוע המועדף עליך (סמ\"ק)?", "int"),
    Slot("turbo", "טורבו", "האם אתה מחפש מנוע עם טורבו או בלי טורבו?", "text"),

    # שאלות נוספות לדיוק
    Slot("max_km", "קילומטראז' מקסימלי", "מה הקילומטראז' המקסימלי לרכב שתרצה?", "int"),
    Slot("brand_pref", "מותג מועדף", "האם יש מותג מועדף עבורך?", "text", required=False),
    Slot("color_pref", "צבע מועדף", "יש צבע מועדף או לא חשוב?", "text", required=False),
    Slot("doors", "מספר דלתות", "כמה דלתות תרצה ברכב?", "int", required=False),
    Slot("safety", "בטיחות", "האם חשוב לך מערכות בטיחות מתקדמות?", "text"),
    Slot("multimedia", "מולטימדיה", "חשוב לך CarPlay/Android Auto?", "text"),
    Slot("warranty", "אחריות", "האם חשוב לך רכב עם אחריות יבואן קיימת?", "text"),
    Slot("depreciation", "ירידת ערך", "כמה חשובה לך ירידת הערך?", "text"),
    Slot("insurance_importance", "עלות ביטוח", "עד כמה חשוב לך שהביטוח יהיה זול?", "text"),
    Slot("age_driver", "גיל נהג", "בן כמה הנהג העיקרי?", "int"),
    Slot("ownership_time", "תקופת החזקה", "כמה זמן מתוכנן להחזיק את הרכב?", "text"),
    Slot("trunk", "תא מטען", "האם חשוב לך תא מטען גדול?", "text"),
    Slot("fuel_efficiency", "חסכון דלק", "האם חשוב לך רכב חסכוני מאוד בדלק?", "text"),
    Slot("daily_trip", "נסיעות יומיומיות", "נסיעות קצרות או ארוכות ביום?", "text"),
    Slot("performance", "ביצועים", "האם חשוב לך מנוע חזק?", "text"),
    Slot("resale_value", "שמירת ערך", "כמה חשוב לך שהרכב ישמור על ערכו?", "text"),
    Slot("daily_hours", "שעות נהיגה ביום", "כמה שעות בממוצע אתה נוהג ביום?", "int"),
    Slot("equipment", "אבזור", "חשוב לך רכב מאובזר (גג נפתח, מצלמות, חיישנים)?", "text"),
    Slot("reliability_type", "סוג אמינות", "האם חשוב לך מותג עם אמינות מוכחת (יפני/קוריאני) או מוכן לקחת סיכון?", "text"),
    Slot("annual_tax", "עלות טסט", "עד כמה קריטית עבורך עלות אגרת הרישוי?", "text"),
    Slot("parking_difficulty", "חניה", "האם יש לך קושי עם רכב גדול בעיר (חניה)?", "text"),
    Slot("new_vs_old", "חדש מול ישן", "מה חשוב יותר: חדש יחסית או חזק/מאובזר יותר גם אם ישן?", "text"),
    Slot("service", "שירות מוסכים", "כמה חשוב לך שירות ומוסכים של יבואן גדול?", "text"),
    Slot("tow_option", "גרירה", "האם חשוב לך אפשרות גרירת נגרר/קרוואן?", "text"),
    Slot("light_offroad", "שטח קל", "האם חשוב לך שהרכב יתאים לשטח קל?", "text"),
]
REQUIRED_KEYS = [s.key for s in SLOTS if s.required]

# =========================
# App state
# =========================
if "messages" not in st.session_state:
    st.session_state.messages = [
        {"role":"assistant","content":"היי! אני היועץ לרכבים יד 2. נתחיל בשאלה קצרה – מה התקציב המינימלי שלך בשקלים?"}
    ]
if "answers" not in st.session_state:
    st.session_state.answers = {}
if "last_ask" not in st.session_state:
    st.session_state.last_ask = None

# =========================
# Display history
# =========================
st.markdown("## 🤖 יועץ רכבים – צ'אט עם שאלון")
for m in st.session_state.messages:
    with st.chat_message("assistant" if m["role"]=="assistant" else "user"):
        st.markdown(m["content"])

# =========================
# Chat input
# =========================
user_text = st.chat_input("כתוב תשובה כאן והקש אנטר...")

if user_text:
    st.session_state.messages.append({"role":"user","content":user_text})
    if st.session_state.get("last_ask"):
        slot = st.session_state.last_ask
        st.session_state.answers[slot.key] = user_text.strip()
        st.session_state.last_ask = None

    # בדוק אם יש עוד שאלות
    missing = [s for s in SLOTS if s.required and s.key not in st.session_state.answers]
    if missing:
        nxt = missing[0]
        st.session_state.last_ask = nxt
        with st.chat_message("assistant"):
            st.markdown(nxt.prompt)
        st.session_state.messages.append({"role":"assistant","content":nxt.prompt})
    else:
        # סיכום דרישות
        answers = st.session_state.answers
        summary_lines = [f"- {s.label}: {answers.get(s.key)}" for s in SLOTS if answers.get(s.key)]
        summary_text = "### סיכום דרישותיך\n" + "\n".join(summary_lines)
        with st.chat_message("assistant"):
            st.markdown(summary_text)
        st.session_state.messages.append({"role":"assistant","content":summary_text})

        # Placeholder ל-Perplexity
        with st.chat_message("assistant"):
            st.markdown("🔎 השאלון הושלם. החלק הבא יתחבר ל־Perplexity API כדי למשוך מחירים ועלויות אמיתיות ולשלוח ל־GPT לעיבוד.")
