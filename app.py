# -*- coding: utf-8 -*-
# UsedCarAdvisor – ChatBot-First with In-Chat Questionnaire (Streamlit, single-file)
# Run: streamlit run app.py

import os
import json
import re
from dataclasses import dataclass
from typing import List, Dict, Any, Optional

import streamlit as st

try:
    from openai import OpenAI
except Exception:
    OpenAI = None

try:
    import google.generativeai as genai
except Exception:
    genai = None

st.set_page_config(page_title="יועץ רכבים יד 2 – צ'אט עם שאלון מוטמע", page_icon="🤖🚗", layout="centered")

RTL = """
<style>
html, body, [class*="css"] { direction: rtl; text-align: right; }
.block-container { padding-top: .6rem; max-width: 880px; }
.stChatMessage { text-align: right; }
</style>
"""
st.markdown(RTL, unsafe_allow_html=True)

# =========================
# Questionnaire slots
# =========================
@dataclass
class Slot:
    key: str
    label: str
    prompt: str
    kind: str
    required: bool = True

SLOTS: List[Slot] = [
    Slot("budget_min", "תקציב מינימום (₪)", "מה התקציב המינימלי שלך בשקלים? (לדוגמה: 40,000)", "int"),
    Slot("budget_max", "תקציב מקסימום (₪)", "מה התקציב המקסימלי שלך בשקלים? (לדוגמה: 80,000)", "int"),
    Slot("body", "סוג רכב", "איזה סוג רכב אתה מחפש? (לדוגמה: משפחתי, קטן, ג'יפ)", "text"),
    Slot("character", "אופי רכב", "האם אתה מחפש רכב ספורטיבי או יומיומי?", "text"),
    Slot("usage", "שימוש עיקרי", "השימוש העיקרי יהיה בעיר, בין-עירוני או שטח?", "text"),
    Slot("priority", "עדיפות מרכזית", "מה הכי חשוב לך – אמינות, נוחות, ביצועים או עיצוב?", "text"),
    Slot("passengers", "מספר נוסעים ממוצע", "בממוצע כמה נוסעים ייסעו ברכב? (לדוגמה: 5)", "int"),
    Slot("fuel", "סוג דלק", "איזה סוג דלק תעדיף – בנזין, דיזל, היברידי או חשמלי?", "text"),
    Slot("year_min", "שנת ייצור מינימלית", "מאיזו שנת ייצור מינימלית תרצה? (לדוגמה: 2015)", "int"),
    Slot("km_per_year", "ק\"מ לשנה", "כמה קילומטרים אתה נוסע בערך בשנה? (לדוגמה: 15000)", "int"),
    Slot("gearbox", "תיבת הילוכים", "יש לך העדפה לגיר – אוטומט או ידני?", "text"),
    Slot("region", "אזור בארץ", "באיזה אזור בארץ אתה גר?", "text"),
    # חדשים:
    Slot("engine_size", "נפח מנוע", "מה נפח המנוע המועדף עליך? (לדוגמה: 1600)", "int"),
    Slot("turbo", "טורבו", "האם אתה מחפש מנוע עם טורבו או בלי טורבו?", "text"),
]
REQUIRED_KEYS = [s.key for s in SLOTS if s.required]

# =========================
# App state
# =========================
if "messages" not in st.session_state:
    st.session_state.messages: List[Dict[str, str]] = [
        {"role":"assistant","content":"היי! אני היועץ לרכבים יד 2. נתחיל בשאלה קצרה – מה התקציב המינימלי שלך בשקלים? (לדוגמה: 40,000)"}
    ]
if "answers" not in st.session_state:
    st.session_state.answers: Dict[str, Any] = {}
if "last_ask" not in st.session_state:
    st.session_state.last_ask = None

# =========================
# Provider setup
# =========================
PROVIDER = st.sidebar.selectbox("ספק מודל", ["OpenAI", "Gemini"], index=0)
openai_key = os.getenv("OPENAI_API_KEY", "")
gemini_key = os.getenv("GEMINI_API_KEY", "") or os.getenv("GOOGLE_API_KEY", "")

if PROVIDER == "OpenAI":
    has_key = bool(openai_key and OpenAI)
    model_name = st.sidebar.text_input("OpenAI Model", value="gpt-4.1-mini")
    oai_client = OpenAI(api_key=openai_key) if has_key else None
else:
    has_key = bool(gemini_key and genai)
    model_name = st.sidebar.text_input("Gemini Model", value="gemini-1.5-flash")
    if has_key:
        genai.configure(api_key=gemini_key)
        gem_model = genai.GenerativeModel(model_name)
    else:
        gem_model = None

st.sidebar.markdown(f"**סטטוס ספק:** {'✅ מחובר' if has_key else '❌ ללא מפתח/ספריה'}")

# =========================
# Helpers
# =========================
def parse_int(text: str) -> Optional[int]:
    nums = re.findall(r"\d+", text.replace(",", ""))
    if nums:
        try:
            return int(nums[0])
        except Exception:
            return None
    return None

def next_missing_required() -> Optional[Slot]:
    for s in SLOTS:
        if s.required and (s.key not in st.session_state.answers or st.session_state.answers[s.key] in [None,"",0,""]):
            return s
    return None

def call_model(prompt: str) -> str:
    try:
        if PROVIDER == "OpenAI" and has_key and oai_client:
            resp = oai_client.chat.completions.create(
                model=model_name,
                messages=[{"role":"user","content":prompt}],
                temperature=0.3,
            )
            return resp.choices[0].message.content
        elif PROVIDER == "Gemini" and has_key and gem_model:
            r = gem_model.generate_content(prompt)
            return r.text or ""
    except Exception as e:
        return f"(שגיאה בקריאה למודל: {e})"
    return "(אין חיבור למודל)"

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
    # שמירה לתוך תשובות
    if st.session_state.get("last_ask"):
        slot = st.session_state.last_ask
        if slot.kind == "int":
            val = parse_int(user_text)
            if val: st.session_state.answers[slot.key] = val
        else:
            st.session_state.answers[slot.key] = user_text.strip()
        st.session_state.last_ask = None

    # מציאת השאלה הבאה
    nxt = next_missing_required()
    if nxt:
        st.session_state.last_ask = nxt
        with st.chat_message("assistant"):
            st.markdown(nxt.prompt)
        st.session_state.messages.append({"role":"assistant","content":nxt.prompt})
    else:
        # === כל השאלון מולא ===
        answers = st.session_state.answers
        with st.chat_message("assistant"):
            st.markdown("✅ סיימנו את שלב השאלון. מחפש רכבים מתאימים...")

        # שלב ראשון: בקשת דגמים
        prompt = f"""בהתבסס על הקריטריונים: {json.dumps(answers, ensure_ascii=False)},
תן רשימת 5 דגמי רכבים מתאימים (יד 2 בישראל). החזר JSON:
{{"recommendations":[{{"model":"דגם","why":"נימוק קצר"}}]}}"""
        txt = call_model(prompt)
        try:
            recs = json.loads(re.search(r"\{.*\}", txt, re.S).group())
        except Exception:
            recs = {"recommendations":[]}

        all_models = [r["model"] for r in recs.get("recommendations",[])]
        if not all_models:
            all_models = ["טויוטה קורולה", "מאזדה 3", "קיה סיד"]

        results = []
        # שלב שני: בדיקת אמינות לכל דגם
        for model in all_models:
            sub_prompt = f"""בדוק עבור הדגם {model} (יד שנייה בישראל):
- ציון אמינות כללי (0–100),
- עלויות תחזוקה שנתיות ממוצעות (ש"ח),
- תקלות נפוצות.
החזר JSON:
{{"model":"{model}","reliability":90,"annual_cost":4500,"issues":["גיר","חשמל"]}}"""
            sub_txt = call_model(sub_prompt)
            try:
                data = json.loads(re.search(r"\{.*\}", sub_txt, re.S).group())
                results.append(data)
            except Exception:
                results.append({"model":model,"reliability":50,"annual_cost":5000,"issues":["נתון חסר"]})

        # טבלה מסכמת
        table_md = "| דגם | אמינות | עלות שנתית | תקלות נפוצות |\n|---|---|---|---|\n"
        best_model = None
        best_score = -1
        for r in results:
            score = r.get("reliability",0) - int(r.get("annual_cost",0)/1000)
            if score > best_score:
                best_score = score
                best_model = r["model"]
            table_md += f"| {r['model']} | {r.get('reliability','?')} | {r.get('annual_cost','?')} | {', '.join(r.get('issues',[]))} |\n"

        final_msg = "### תוצאות בדיקת אמינות ותחזוקה\n" + table_md + f"\n✅ ההמלצה המובילה: **{best_model}**"
        with st.chat_message("assistant"):
            st.markdown(final_msg)
        st.session_state.messages.append({"role":"assistant","content":final_msg})

st.markdown("---")
st.caption("בסיום השאלון: שלב המלצות חכמות כולל אמינות, עלויות ותקלות נפוצות.")
