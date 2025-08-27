# -*- coding: utf-8 -*-
# UsedCarAdvisor – Free-text enabled chatbot
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

st.set_page_config(page_title="יועץ רכבים יד 2 – צ'אט חכם", page_icon="🤖🚗", layout="centered")

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
    st.rerun()

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
# App state
# =========================
if "messages" not in st.session_state:
    st.session_state.messages: List[Dict[str, str]] = [
        {"role":"assistant","content":"היי! ספר לי במילים שלך איזה רכב אתה מחפש – אפשר חופשי (לדוגמה: 'בא לי חיית כביש איטלקית עד 80 אלף')."}
    ]
if "answers" not in st.session_state:
    st.session_state.answers: Dict[str, Any] = {}

# =========================
# Helpers
# =========================
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
    return "(אין חיבור למודל)"

def interpret_free_text(user_text: str) -> Dict[str, Any]:
    prompt = f"""
    המשתמש כתב: "{user_text}"
    עליך לנתח זאת לדרישות רכב.
    השדות האפשריים:
    - budget_min, budget_max (מספרים בשקלים אם צוין)
    - body (משפחתי, האצ'בק, ג'יפ, סדאן, קופה...)
    - character (ספורטיבי, יומיומי)
    - fuel (בנזין, דיזל, היברידי, חשמלי)
    - turbo (עם טורבו / בלי טורבו אם הוזכר)
    - brand (מותג אם צוין, אחרת null)
    - engine_size (נפח מנוע אם צוין, אחרת null)

    החזר JSON בלבד. למשל:
    {{
      "budget_min": 40000,
      "budget_max": 80000,
      "body": "האצ'בק",
      "character": "ספורטיבי",
      "fuel": "בנזין",
      "turbo": "עם טורבו",
      "brand": "אלפא רומיאו",
      "engine_size": 1700
    }}
    """
    txt = call_model(prompt)
    try:
        data = json.loads(re.search(r"\{.*\}", txt, re.S).group())
        return data
    except Exception:
        return {}

def progress_bar(answers: Dict[str,Any]):
    required = ["budget_min","budget_max","body","character","fuel","year_min","engine_size","turbo"]
    filled = sum(1 for k in required if k in answers and answers[k] not in [None,"",0])
    pct = int(100 * filled / len(required))
    st.markdown(f"**התקדמות השאלון:** {pct}%")
    st.progress(pct)

# =========================
# Display history
# =========================
st.markdown("## 🤖 יועץ רכבים – צ'אט חכם")
progress_bar(st.session_state.answers)

for m in st.session_state.messages:
    with st.chat_message("assistant" if m["role"]=="assistant" else "user"):
        st.markdown(m["content"])

# =========================
# Chat input
# =========================
user_text = st.chat_input("כתוב בחופשיות מה אתה מחפש...")

if user_text:
    st.session_state.messages.append({"role":"user","content":user_text})
    parsed = interpret_free_text(user_text)
    st.session_state.answers.update({k:v for k,v in parsed.items() if v not in [None,"",0]})

    # סיכום דרישות עד כה
    answers = st.session_state.answers
    summary_lines = []
    for k,v in answers.items():
        summary_lines.append(f"- {k}: {v}")
    summary_text = "### סיכום דרישותיך (עד כה)\n" + "\n".join(summary_lines)
    with st.chat_message("assistant"):
        st.markdown(summary_text)
    st.session_state.messages.append({"role":"assistant","content":summary_text})

    # אם מולאו נתונים מספיקים → חיפוש דגמים
    if "budget_max" in answers and "body" in answers:
        with st.chat_message("assistant"):
            st.markdown("✅ מחפש רכבים מתאימים בישראל...")

        prompt = f"""
        בהתבסס על הקריטריונים: {json.dumps(answers, ensure_ascii=False)},
        בחר 5 דגמי רכבים יד שנייה הנמכרים בישראל בלבד.
        אם המשתמש ביקש טורבו – אל תחזיר דגמים בלי טורבו.
        אם המשתמש ציין מותג (brand) – החזר רק דגמים של מותג זה.
        החזר JSON:
        {{"recommendations":[{{"model":"דגם","why":"נימוק קצר"}}]}}
        """
        txt = call_model(prompt)
        try:
            recs = json.loads(re.search(r"\{.*\}", txt, re.S).group())
        except Exception:
            recs = {"recommendations":[]}

        # טבלה ראשונית
        if recs.get("recommendations"):
            table_md = "| דגם | נימוק |\n|---|---|\n"
            for r in recs["recommendations"]:
                table_md += f"| {r['model']} | {r['why']} |\n"
            with st.chat_message("assistant"):
                st.markdown("### הצעות ראשוניות\n" + table_md)
            st.session_state.messages.append({"role":"assistant","content":table_md})

st.markdown("---")
st.caption("האפליקציה מקבלת טקסט חופשי מהמשתמש, מפענחת לשדות מובנים (כולל מותג אם צוין), ומחזירה המלצות רלוונטיות בלבד.")
