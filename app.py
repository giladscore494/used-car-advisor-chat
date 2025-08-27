import os
import json
import re
from dataclasses import dataclass
from typing import List, Dict, Any, Optional

import streamlit as st

# Optional SDKs – install according to chosen provider
try:
    from openai import OpenAI  # pip install openai>=1.40.0
except Exception:
    OpenAI = None

try:
    import google.generativeai as genai  # pip install google-generativeai
except Exception:
    genai = None

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
    Slot("region", "אזור בארץ (לא חובה)", "באיזו עיר/אזור בארץ אתה גר?", "text", required=False),
]
REQUIRED_KEYS = [s.key for s in SLOTS if s.required]

# =========================
# App State
# =========================
if "messages" not in st.session_state:
    st.session_state.messages: List[Dict[str, str]] = [
        {"role":"assistant","content":"היי! אני היועץ לרכבים יד 2. נתחיל בשאלה קצרה – מה טווח התקציב שלך? (אפשר לכתוב חופשי או לבחור בפתקיות כאן למטה)"}
    ]
if "answers" not in st.session_state:
    st.session_state.answers: Dict[str, Any] = {}
if "ask_index" not in st.session_state:
    st.session_state.ask_index = 0
if "last_ask" not in st.session_state:
    st.session_state.last_ask = None
if "_clicked_choice" not in st.session_state:
    st.session_state._clicked_choice = None

# =========================
# Providers & status
# =========================
PROVIDER = st.sidebar.selectbox("ספק מודל", ["OpenAI", "Gemini"], index=0)

openai_key = os.getenv("OPENAI_API_KEY", "")
gemini_key = os.getenv("GEMINI_API_KEY", "") or os.getenv("GOOGLE_API_KEY", "")  # accept both names

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
# Small helpers (normalization & coercion)
# =========================
def _norm(s: str) -> str:
    s = s or ""
    s = s.replace("״", '"').replace("”", '"').replace("“", '"').replace("׳","'").replace("’","'").replace("־","-")
    s = s.replace("ג׳יפ", "ג'יפ")
    return re.sub(r"\s+", " ", s.strip())

def coerce_for_slot(slot: Slot, text: str) -> Any:
    t = _norm(text)
    if slot.kind == "int":
        nums = re.findall(r"\d+", t.replace(",", ""))
        if nums:
            try:
                return int(nums[0])
            except Exception:
                return None
        return None
    if slot.kind == "select" and slot.options:
        tn = t.lower()
        if slot.key == "fuel" and "בנזין" in tn:
            return "בנזין"
        for opt in slot.options:
            if _norm(opt).lower() in tn or tn in _norm(opt).lower():
                return opt
        for opt in slot.options:
            if _norm(opt)[0] == t[:1]:
                return opt
        return t
    return t if t else None

def parse_budget_range(text: str) -> Optional[Dict[str,int]]:
    t = text.replace(",", "")
    nums = [int(n) for n in re.findall(r"\d+", t)]
    if len(nums) >= 2:
        lo, hi = sorted(nums[:2])
        return {"budget_min": lo, "budget_max": hi}
    return None

def next_missing_required() -> Optional[Slot]:
    for s in SLOTS:
        if s.required and (s.key not in st.session_state.answers or st.session_state.answers[s.key] in [None,"",0]):
            return s
    return None

# =========================
# LLM call
# =========================
SYSTEM_PROMPT = {
    "role":"system",
    "content":(
        "אתה עוזר קניות רכב יד 2 בעברית. תשאל שאלה אחת קצרה בכל פעם, הצע 3–6 אפשרויות קצרות ככפתורי בחירה,"
        " וגם קבל תשובה חופשית. עדכן מילון JSON בשם filled_slots כשנמסרים ערכים, ובחר את השדה הבא שנדרש."
        " תמיד החזר בפורמט JSON תקין:")
}
FORMAT_HINT = {
    "role":"system",
    "content":(
        '{"assistant_message": "טקסט לבן-אדם",'
        ' "filled_slots": {"budget_min": 40000, "body": "משפחתי"},'
        ' "ask_next": {"key": "fuel", "question": "איזה סוג דלק תעדיף?", "options": ["בנזין","דיזל","היברידי","חשמלי","כל"]}}')
}

def build_chat_for_llm(messages: List[Dict[str,str]], answers: Dict[str,Any]) -> List[Dict[str,str]]:
    ctx = [SYSTEM_PROMPT, FORMAT_HINT]
    state_line = json.dumps({k: v for k, v in answers.items()}, ensure_ascii=False)
    ctx.append({"role":"system", "content": f"מצב שדות נוכחי: {state_line}"})
    ctx.extend(messages[-8:])
    return ctx

def call_llm(context_msgs: List[Dict[str,str]]) -> Dict[str,Any]:
    try:
        if PROVIDER == "OpenAI" and has_key and oai_client:
            resp = oai_client.chat.completions.create(
                model=model_name,
                messages=context_msgs,
                temperature=0.3,
            )
            txt = resp.choices[0].message.content
        elif PROVIDER == "Gemini" and has_key and gem_model:
            as_text = "\n".join([f"{m['role']}: {m['content']}" for m in context_msgs])
            r = gem_model.generate_content(as_text)
            txt = r.text or ""
        else:
            txt = '{"assistant_message": "(אין חיבור לספק – מצב מקומי)", "filled_slots": {}, "ask_next": null}'
    except Exception:
        txt = '{"assistant_message": "(שגיאה אצל הספק – מצב מקומי)", "filled_slots": {}, "ask_next": null}'

    try:
        m = re.search(r"\{[\s\S]*\}$", txt.strip())
        payload = json.loads(m.group(0) if m else txt)
        if not isinstance(payload, dict):
            raise ValueError("not a dict")
        return payload
    except Exception:
        return {"assistant_message":"", "filled_slots":{}, "ask_next":None}

# =========================
# UI helpers
# =========================
def render_quick_replies(options: List[str]):
    if not options:
        return None
    cols = st.columns(min(3, len(options)))
    clicks = None
    for i, opt in enumerate(options):
        with cols[i % len(cols)]:
            if st.button(opt, key=f"qr-{opt}-{i}"):
                clicks = opt
    return clicks

def progress_bar(answers: Dict[str,Any]):
    filled = sum(1 for k in REQUIRED_KEYS if k in answers and answers[k] not in [None, "", 0])
    pct = int(100 * filled / max(1, len(REQUIRED_KEYS)))
    st.markdown(f"**התקדמות השאלון:** {pct}%")
    st.markdown(f"<div class='progress'><div style='width:{pct}%'></div></div>", unsafe_allow_html=True)

# =========================
# Display history
# =========================
st.markdown("## 🤖 יועץ רכבים – צ'אט עם שאלון מובנה")
progress_bar(st.session_state.answers)

for m in st.session_state.messages:
    with st.chat_message("assistant" if m["role"]=="assistant" else "user"):
        st.markdown(m["content"])

# =========================
# In-chat questionnaire turn
# =========================
user_text = st.chat_input("כתוב תשובה חופשית… או בחר אפשרות כאשר תוצג מעל אינפוט זה")

# Handle quick-reply clicks BEFORE sending anything to the model
clicked_choice = st.session_state.get("_clicked_choice")
if clicked_choice:
    last_ask = st.session_state.get("last_ask")
    if last_ask and isinstance(last_ask, dict) and last_ask.get("key"):
        st.session_state.answers[last_ask["key"]] = clicked_choice
        st.session_state.messages.append({"role":"user","content":clicked_choice})
        st.session_state._clicked_choice = None
        st.session_state.last_ask = None
        user_text = None
    else:
        user_text = clicked_choice
        st.session_state._clicked_choice = None

if user_text:
    st.session_state.messages.append({"role":"user","content":user_text})

    # Bind free-text to the last asked slot in ALL modes (prevents loops)
    if st.session_state.get("last_ask") and st.session_state.last_ask.get("key"):
        key = st.session_state.last_ask["key"]
        slot = next((s for s in SLOTS if s.key == key), None)
        if slot:
            val = coerce_for_slot(slot, user_text or "")
            if val not in [None, ""]:
                st.session_state.answers[key] = val
        st.session_state.last_ask = None

    # Try infer budget range from any free text
    rng = parse_budget_range(user_text or "")
    if rng:
        st.session_state.answers.setdefault("budget_min", rng["budget_min"])
        st.session_state.answers.setdefault("budget_max", rng["budget_max"])

    # LLM path (if connected), else local logic
    if has_key:
        ctx = build_chat_for_llm(st.session_state.messages, st.session_state.answers)
        payload = call_llm(ctx)

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

        ask_next = payload.get("ask_next")
        # Guard: if model asks again for a field already filled, skip to next missing
        if ask_next and isinstance(ask_next, dict):
            next_key = ask_next.get("key")
            if next_key and next_key in st.session_state.answers and st.session_state.answers[next_key] not in [None,"",0]:
                ask_next = None

        if ask_next and isinstance(ask_next, dict):
            q = ask_next.get("question") or "שאלה הבאה:"
            opts = ask_next.get("options", [])
            st.session_state.last_ask = {"key": ask_next.get("key"), "options": opts}
            with st.chat_message("assistant"):
                st.markdown(assistant_message + f"\n\n**{q}**")
                choice = render_quick_replies(opts)
                if choice:
                    st.session_state._clicked_choice = choice
            st.session_state.messages.append({"role":"assistant","content":assistant_message + ("\n\n" + q if q else "")})
        else:
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
    else:
        # Local (no provider) – ask next missing or finish
        missing = [s for s in SLOTS if s.required and s.key not in st.session_state.answers]
        if missing:
            nxt = missing[0]
            st.session_state.last_ask = {"key": nxt.key, "options": (nxt.options or [])}
            with st.chat_message("assistant"):
                st.markdown("תודה!\n\n**" + nxt.prompt + "**")
                choice = render_quick_replies(nxt.options or [])
                if choice:
                    st.session_state._clicked_choice = choice
            st.session_state.messages.append({"role":"assistant","content":"תודה!\n\n" + nxt.prompt})
        else:
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

# =========================
# Footer / Next steps
# =========================
st.markdown("---")
st.caption("""גרסת MVP: שאלון מוטמע בצ'אט + בחירת ספק מודל (OpenAI/Gemini).
בהמשך: ניקוד מתקדם, בדיקת אמינות, ויצוא PDF.""")
