# -*- coding: utf-8 -*-
# UsedCarAdvisor – ChatBot-First with In-Chat Questionnaire (Streamlit, single-file)
# Run: streamlit run app.py
# Set API keys via env or Streamlit secrets:
#   OPENAI_API_KEY / GEMINI_API_KEY

import os
import json
import re
from dataclasses import dataclass
from typing import List, Dict, Any, Optional

import streamlit as st

# Optional SDKs – installed via requirements.txt
try:
    from openai import OpenAI  # pip install openai>=1.40.0
except Exception:
    OpenAI = None

try:
    import google.generativeai as genai  # pip install google-generativeai
except Exception:
    genai = None

# -----------------------
# Page setup + RTL styles
# -----------------------
st.set_page_config(page_title="יועץ רכבים יד 2 – צ'אט עם שאלון מוטמע", page_icon="🤖🚗", layout="centered")

RTL = """
<style>
html, body, [class*="css"] { direction: rtl; text-align: right; }
.block-container { padding-top: .6rem; max-width: 880px; }
.stChatMessage { text-align: right; }
.user-msg { background: #eef6ff; padding: .65rem .9rem; border-radius: 14px; }
.bot-msg { background: #f8fafc; padding: .65rem .9rem; border-radius: 14px; }
.badge { display:inline-block; padding:.15rem .55rem; border-radius:999px; background:#e2e8f0; margin-left:.35rem; font-size:.8rem }
.chip { display:inline-block; padding: .4rem .75rem; border-radius: 999px; border:1px solid #e5e7eb; margin: .25rem; cursor:pointer }
.progress{height:8px;background:#e5e7eb;border-radius:999px;overflow:hidden}
.progress>div{height:100%;background:#22c55e}
hr{border:none;border-top:1px solid #eee;margin:.7rem 0}
</style>
"""
st.markdown(RTL, unsafe_allow_html=True)

# =========================
# Domain: Questionnaire Slots
# =========================
@dataclass
class Slot:
    key: str
    label: str
    prompt: str
    kind: str  # 'select'|'int'|'text'
    required: bool = True
    options: Optional[List[str]] = None

SLOTS: List[Slot] = [
    Slot("budget_min", "תקציב מינימום (₪)", "מה התקציב המינימלי שלך בשקלים?", "int"),
    Slot("budget_max", "תקציב מקסימום (₪)", "ומה המקסימום שאתה מוכן לשלם?", "int"),
    Slot("body", "סוג רכב", "איזה סוג רכב אתה מחפש – קטן / משפחתי / ג'יפ / מסחרי קל?", "select", options=["קטן","משפחתי","ג'יפ","מסחרי קל"]),
    Slot("character", "אופי רכב", "העדפה: ספורטיבי או דיילי (יומיומי)?", "select", options=["ספורטיבי","דיילי"]),
    Slot("usage", "שימוש עיקרי", "השימוש העיקרי יהיה יותר בעיר, בין-עירוני או שטח?", "select", options=["עירוני","בין־עירוני","שטח"]),
    Slot("priority", "עדיפות", "מה העדיפות המרכזית – אמינות / נוחות / ביצועים / עיצוב?", "select", options=["אמינות","נוחות","ביצועים","עיצוב"]),
    Slot("passengers", "מספר נוסעים ממוצע", "בממוצע כמה נוסעים ייסעו ברכב?", "int"),
    Slot("fuel", "סוג דלק", "האם יש עדיפות לדלק: בנזין / דיזל / היברידי / חשמלי או שכל אפשרות פתוחה?", "select", options=["בנזין","דיזל","היברידי","חשמלי","כל"]),
    Slot("year_min", "שנת ייצור מינימלית", "מאיזו שנת ייצור מינימלית תרצה?", "int"),
    Slot("parking", "חניה", "יש לך חניה פרטית או חניה ברחוב?", "select", options=["פרטית","רחוב"]),
    Slot("fuel_importance", "חשיבות צריכת דלק", "כמה חשובה לך צריכת דלק – לא חשוב / חשוב / קריטי?", "select", options=["לא חשוב","חשוב","קריטי"]),
    Slot("km_per_year", 'ק"מ לשנה', "כמה קילומטרים אתה נוסע בערך בשנה?", "int"),
    Slot("tax_importance", "חשיבות אגרת טסט", "עד כמה חשובה עלות אגרת הרישוי – לא חשוב / חשוב / קריטי?", "select", options=["לא חשוב","חשוב","קריטי"]),
    Slot("ins_importance", "חשיבות ביטוח", "עד כמה חשובה עלות הביטוח – לא חשוב / חשוב / קריטי?", "select", options=["לא חשוב","חשוב","קריטי"]),
    Slot("gearbox", "תיבת הילוכים (לא חובה)", "יש לך העדפה לגיר – אוטומט או ידני?", "select", required=False, options=["לא משנה","אוטומט","ידני"]),
    Slot("region", "אזור בארץ (לא חובה)", "באיזה אזור בארץ אתה גר?", "text", required=False),
]
REQUIRED_KEYS = [s.key for s in SLOTS if s.required]

# =========================
# App State
# =========================
if "messages" not in st.session_state:
    st.session_state.messages: List[Dict[str, str]] = [
        {"role":"assistant","content":"היי! אני היועץ לרכבים יד 2. נתחיל בשאלה קצרה – מה טווח התקציב שלך? (אפשר לכתוב חופשי או לבחור כשאציג אפשרויות)"}
    ]
if "answers" not in st.session_state:
    st.session_state.answers: Dict[str, Any] = {}
if "ask_index" not in st.session_state:
    st.session_state.ask_index = 0  # which slot to ask next (by order)
if "last_ask" not in st.session_state:
    st.session_state.last_ask = None
if "_clicked_choice" not in st.session_state:
    st.session_state._clicked_choice = None

# =========================
# Provider selection + keys
# =========================
st.sidebar.header("⚙️ הגדרות מודל")
PROVIDER = st.sidebar.selectbox("ספק מודל", ["OpenAI", "Gemini"], index=0)

# Prefer st.secrets for deployment; fallback to env vars
openai_key = st.secrets.get("OPENAI_API_KEY", os.getenv("OPENAI_API_KEY", ""))
gemini_key = st.secrets.get("GEMINI_API_KEY", os.getenv("GEMINI_API_KEY", ""))

if PROVIDER == "OpenAI":
    model_name = st.sidebar.text_input("OpenAI Model", value="gpt-4.1-mini")
    if openai_key and OpenAI:
        oai_client = OpenAI(api_key=openai_key)
    else:
        oai_client = None
else:
    model_name = st.sidebar.text_input("Gemini Model", value="gemini-1.5-flash")
    if gemini_key and genai:
        genai.configure(api_key=gemini_key)
        gem_model = genai.GenerativeModel(model_name)
    else:
        gem_model = None

# =========================
# System prompts for JSON control
# =========================
SYSTEM_PROMPT = {
    "role":"system",
    "content":(
        "אתה עוזר קניות רכב יד 2 בעברית. תשאל שאלה אחת קצרה בכל פעם, הצע 3–6 אפשרויות קצרות ככפתורי בחירה, "
        "וגם קבל תשובה חופשית. עדכן מילון JSON בשם filled_slots כשנמסרים ערכים, ובחר את השדה הבא שנדרש. "
        "החזר תמיד JSON חוקי בלבד (ולא טקסט נוסף) במבנה הבא."
    )
}
FORMAT_HINT = {
    "role":"system",
    "content":(
        '{"assistant_message": "טקסט לבן-אדם", '
        '"filled_slots": {"budget_min": 40000, "body": "משפחתי"}, '
        '"ask_next": {"key": "fuel", "question": "איזה סוג דלק תעדיף?", "options": ["בנזין","דיזל","היברידי","חשמלי","כל"]}}'
    )
}

def build_chat_for_llm(messages: List[Dict[str,str]], answers: Dict[str,Any]) -> List[Dict[str,str]]:
    ctx = [SYSTEM_PROMPT, FORMAT_HINT]
    state_line = json.dumps({k: v for k, v in answers.items()}, ensure_ascii=False)
    ctx.append({"role":"system", "content": f"מצב שדות נוכחי: {state_line}"})
    ctx.extend(messages[-8:])
    return ctx

def call_llm(context_msgs: List[Dict[str,str]]) -> Dict[str,Any]:
    """Call provider and parse JSON dict. Fallback to a safe default if parsing fails."""
    try:
        if PROVIDER == "OpenAI" and oai_client is not None:
            resp = oai_client.chat.completions.create(
                model=model_name,
                messages=context_msgs,
                temperature=0.3,
            )
            txt = resp.choices[0].message.content
        elif PROVIDER == "Gemini" and gem_model is not None:
            as_text = "\n".join([f"{m['role']}: {m['content']}" for m in context_msgs])
            r = gem_model.generate_content(as_text)
            txt = r.text
        else:
            # No API key → start from budget_min with buttons
            txt = '{"assistant_message": "(אין מפתח API מוגדר. אשתמש בשאלון המובנה)", "filled_slots": {}, "ask_next": {"key":"budget_min","question":"מה התקציב המינימלי שלך בשקלים?","options":["20,000","40,000","60,000","80,000"]}}'
    except Exception:
        txt = '{"assistant_message": "(שגיאה זמנית בתשובה, אשתמש בשאלון המובנה)", "filled_slots": {}, "ask_next": {"key":"budget_min","question":"מה התקציב המינימלי שלך בשקלים?","options":["20,000","40,000","60,000","80,000"]}}'

    # Extract JSON
    try:
        # If model returned extra text around JSON, extract from first '{' to last '}'
        m = re.search(r"\{[\s\S]*\}$", txt.strip())
        payload = json.loads(m.group(0) if m else txt)
        if not isinstance(payload, dict):
            raise ValueError("not a dict")
        return payload
    except Exception:
        return {
            "assistant_message": "קיבלתי. נמשיך בבקשה עם השאלון.",
            "filled_slots": {},
            "ask_next": {"key":"budget_min","question":"מה התקציב המינימלי שלך בשקלים?","options":["20,000","40,000","60,000","80,000"]}
        }

# -----------------------
# UI helpers
# -----------------------
def render_quick_replies(options: List[str]):
    cols = st.columns(min(3, len(options))) if options else []
    clicks = None
    for i, opt in enumerate(options or []):
        with cols[i % len(cols)]:
            if st.button(opt):
                clicks = opt
    return clicks

def progress_bar(answers: Dict[str,Any]):
    filled = sum(1 for k in REQUIRED_KEYS if k in answers and answers[k] not in [None, "", 0])
    pct = int(100 * filled / max(1, len(REQUIRED_KEYS)))
    st.markdown(f"**התקדמות השאלון:** {pct}%")
    st.markdown(f"<div class='progress'><div style='width:{pct}%'></div></div>", unsafe_allow_html=True)

# -----------------------
# Header + history
# -----------------------
st.markdown("## 🤖 יועץ רכבים – צ'אט עם שאלון מובנה")
progress_bar(st.session_state.answers)

for m in st.session_state.messages:
    with st.chat_message("assistant" if m["role"]=="assistant" else "user"):
        st.markdown(m["content"])

# -----------------------
# Chat turn (with proper quick-reply binding)
# -----------------------
user_text = st.chat_input("כתוב תשובה חופשית… או בחר אפשרות כאשר תוצג מעל אינפוט זה")

# Handle quick-reply clicks BEFORE sending anything to the model
clicked_choice = st.session_state.get("_clicked_choice")
if clicked_choice:
    last_ask = st.session_state.get("last_ask")
    if last_ask and isinstance(last_ask, dict) and last_ask.get("key"):
        # Bind the clicked option to the last asked slot
        st.session_state.answers[last_ask["key"]] = clicked_choice
        st.session_state.messages.append({"role":"user","content":clicked_choice})
        st.session_state._clicked_choice = None
        st.session_state.last_ask = None
        user_text = None  # already handled this turn
    else:
        # Fallback: treat as plain text
        user_text = clicked_choice
        st.session_state._clicked_choice = None

if user_text:
    st.session_state.messages.append({"role":"user","content":user_text})

    ctx = build_chat_for_llm(st.session_state.messages, st.session_state.answers)
    payload = call_llm(ctx)

    # Merge any filled slots
    filled_slots = payload.get("filled_slots") or {}
    if isinstance(filled_slots, dict):
        for k, v in list(filled_slots.items()):
            if k in ["budget_min","budget_max","passengers","km_per_year","year_min"]:
                try:
                    filled_slots[k] = int(str(v).replace(",",""))
                except Exception:
                    pass
        st.session_state.answers.update({k: v for k, v in filled_slots.items() if v not in [None, ""]})

    assistant_message = payload.get("assistant_message") or "קיבלתי. נמשיך."

    # Ask next with quick replies
    ask_next = payload.get("ask_next")
    if ask_next and isinstance(ask_next, dict):
        q = ask_next.get("question") or "שאלה הבאה:"
        opts = ask_next.get("options", [])
        # Remember what we asked so we can bind quick-reply clicks
        st.session_state.last_ask = {"key": ask_next.get("key"), "options": opts}
        with st.chat_message("assistant"):
            st.markdown(assistant_message + "\n\n**" + q + "**")
            choice = render_quick_replies(opts)
            if choice:
                st.session_state._clicked_choice = choice
        st.session_state.messages.append({"role":"assistant","content":assistant_message + ("\n\n"+q if q else "")})
    else:
        # Fallback to next required slot not filled
        missing = [s for s in SLOTS if s.required and s.key not in st.session_state.answers]
        if missing:
            nxt = missing[0]
            st.session_state.last_ask = {"key": nxt.key, "options": (nxt.options or [])}
            with st.chat_message("assistant"):
                st.markdown(assistant_message + f"\n\n**{nxt.prompt}**")
                choice = render_quick_replies(nxt.options or [])
                if choice:
                    st.session_state._clicked_choice = choice
            st.session_state.messages.append({"role":"assistant","content":assistant_message + "\n\n" + nxt.prompt})
        else:
            # All required collected – produce preliminary recommendations (placeholder)
            shortlist = [
                "טויוטה קורולה היברידית",
                "מאזדה 3",
                "קיה ספורטאז'",
                "יונדאי טוסון",
                "טויוטה יאריס היברידית",
            ]
            bullet = "\n".join([f"• {x}" for x in shortlist])
            summ = (
                "סיימנו לאסוף נתונים! הנה 5 דגמים מתאימים להתחלה (MVP):\n\n" + bullet +
                "\n\nתרצה לעבור לשלב 'מודעה ספציפית' כדי לחשב ציון כדאיות 0–100?"
            )
            with st.chat_message("assistant"):
                st.markdown(summ)
            st.session_state.messages.append({"role":"assistant","content":summ})

st.markdown("---")
st.caption("MVP – שאלון מוטמע בצ'אט + בחירת ספק מודל (OpenAI/Gemini). בהמשך: ניקוד מתקדם, בדיקת אמינות, ויצוא PDF.")
