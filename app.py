# -*- coding: utf-8 -*-
# UsedCarAdvisor – Structured Questionnaire + Free-text input
# Run: streamlit run app.py

import os, json, re
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

st.set_page_config(page_title="יועץ רכבים יד 2 – שאלון + חופשי", page_icon="🤖🚗", layout="centered")

RTL = """
<style>
html, body, [class*="css"] { direction: rtl; text-align: right; }
.block-container { padding-top: .6rem; max-width: 880px; }
.stChatMessage { text-align: right; }
</style>
"""
st.markdown(RTL, unsafe_allow_html=True)

# כפתור איפוס
if st.sidebar.button("🔄 התחל מחדש"):
    for key in list(st.session_state.keys()):
        del st.session_state[key]
    st.rerun()

# ספק מודל
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

# מצבים
if "messages" not in st.session_state:
    st.session_state.messages = [
        {"role":"assistant","content":"היי! נתחיל בשאלון, אבל אפשר גם לכתוב חופשי (למשל: 'בא לי חיית כביש איטלקית עם טורבו עד 80 אלף')."}
    ]
if "answers" not in st.session_state:
    st.session_state.answers = {}
if "last_ask" not in st.session_state:
    st.session_state.last_ask = None

# שאלון
@dataclass
class Slot:
    key: str
    label: str
    prompt: str
    kind: str
    required: bool = True

SLOTS: List[Slot] = [
    Slot("budget_min", "תקציב מינימום (₪)", "מה התקציב המינימלי שלך בשקלים?", "int"),
    Slot("budget_max", "תקציב מקסימום (₪)", "ומה המקסימום שאתה מוכן לשלם?", "int"),
    Slot("body", "סוג רכב", "איזה סוג רכב אתה מחפש? (משפחתי, האצ'בק, ג'יפ...)", "text"),
    Slot("character", "אופי רכב", "העדפה: ספורטיבי או יומיומי?", "text"),
    Slot("fuel", "סוג דלק", "איזה סוג דלק תעדיף – בנזין, דיזל, היברידי, חשמלי?", "text"),
    Slot("year_min", "שנת ייצור מינימלית", "מאיזו שנת ייצור מינימלית תרצה?", "int"),
    Slot("engine_size", "נפח מנוע", "איזה נפח מנוע בערך מתאים לך? (למשל 1600)", "int"),
    Slot("turbo", "טורבו", "האם חשוב לך טורבו?", "text"),
]
REQUIRED_KEYS = [s.key for s in SLOTS if s.required]

# פונקציות עזר
def call_model(prompt: str) -> str:
    try:
        if PROVIDER == "OpenAI" and has_key and oai_client:
            resp = oai_client.chat.completions.create(
                model=model_name,
                messages=[{"role":"user","content":prompt}],
                temperature=0.2,
            )
            return resp.choices[0].message.content
        elif PROVIDER == "Gemini" and has_key and gem_model:
            r = gem_model.generate_content(prompt)
            return r.text or ""
    except Exception as e:
        return f"(שגיאה בקריאה למודל: {e})"
    return ""

def interpret_free_text(user_text: str) -> Dict[str, Any]:
    prompt = f"""
    המשתמש כתב: "{user_text}"
    נתח זאת לדרישות רכב:
    - budget_min, budget_max (מספרים בשקלים אם יש)
    - body (משפחתי, האצ'בק, ג'יפ, סדאן...)
    - character (ספורטיבי, יומיומי)
    - fuel (בנזין, דיזל, היברידי, חשמלי)
    - turbo (עם טורבו / בלי טורבו)
    - brand (מותג אם צוין, אחרת null)
    - engine_size (נפח מנוע אם צוין)

    החזר JSON בלבד.
    """
    txt = call_model(prompt)
    try:
        return json.loads(re.search(r"\{.*\}", txt, re.S).group())
    except Exception:
        return {}

def next_missing_required():
    for s in SLOTS:
        if s.key not in st.session_state.answers:
            return s
    return None

def progress_bar(answers: Dict[str,Any]):
    filled = sum(1 for k in REQUIRED_KEYS if k in answers and answers[k] not in [None,"",0])
    pct = int(100 * filled / len(REQUIRED_KEYS))
    st.markdown(f"**התקדמות השאלון:** {pct}%")
    st.progress(pct)

# הצגת צ'אט
st.markdown("## 🤖 יועץ רכבים – שאלון + טקסט חופשי")
progress_bar(st.session_state.answers)
for m in st.session_state.messages:
    with st.chat_message(m["role"]):
        st.markdown(m["content"])

# קלט משתמש
user_text = st.chat_input("כתוב תשובה חופשית או לפי השאלה...")
if user_text:
    st.session_state.messages.append({"role":"user","content":user_text})

    # אם יש שאלה פתוחה בשאלון → נעדכן ישירות
    if st.session_state.last_ask:
        st.session_state.answers[st.session_state.last_ask.key] = user_text.strip()
        st.session_state.last_ask = None

    # ניתוח טקסט חופשי → הכנסת ערכים
    parsed = interpret_free_text(user_text)
    for k,v in parsed.items():
        if v not in [None,"",0,"null"]:
            st.session_state.answers[k] = v

    # אם עדיין חסרים שדות → המשך שאלון
    nxt = next_missing_required()
    if nxt:
        st.session_state.last_ask = nxt
        with st.chat_message("assistant"):
            st.markdown(nxt.prompt)
        st.session_state.messages.append({"role":"assistant","content":nxt.prompt})
    else:
        # הכל מולא → סיכום דרישות + פרומפט חיפוש
        answers = st.session_state.answers
        summary = "### סיכום דרישותיך\n" + "\n".join([f"- {k}: {v}" for k,v in answers.items()])
        with st.chat_message("assistant"):
            st.markdown(summary)
        st.session_state.messages.append({"role":"assistant","content":summary})

        # חיפוש רכבים
        search_prompt = f"""
        בהתבסס על הדרישות: {json.dumps(answers, ensure_ascii=False)},
        בחר 5 דגמי רכבים יד שנייה הנמכרים בישראל בלבד.
        אם המשתמש ביקש טורבו – אל תציע דגם בלי טורבו.
        אם ציין מותג – כלול רק דגמים מאותו מותג.
        החזר JSON:
        {{"recommendations":[{{"model":"דגם","why":"נימוק קצר"}}]}}
        """
        txt = call_model(search_prompt)
        try:
            recs = json.loads(re.search(r"\{.*\}", txt, re.S).group())
        except Exception:
            recs = {"recommendations":[]}

        table_md = "| דגם | נימוק |\n|---|---|\n"
        for r in recs.get("recommendations",[]):
            table_md += f"| {r['model']} | {r['why']} |\n"

        with st.chat_message("assistant"):
            st.markdown("### הצעות רכבים מתאימות\n" + table_md)
        st.session_state.messages.append({"role":"assistant","content":table_md})

st.markdown("---")
st.caption("האפליקציה משלבת שאלון מובנה + הבנת טקסט חופשי. התשובות החופשיות מוזרקות לפרומפט כדי לחדד את ההמלצות.")
