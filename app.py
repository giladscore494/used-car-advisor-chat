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
    Slot("engine_size", "נפח מנוע", "מה נפח המנוע המועדף עליך? (לדוגמה: 1600)", "int"),
    Slot("turbo", "טורבו", "האם אתה מחפש מנוע עם טורבו או בלי טורבו?", "text"),
]
REQUIRED_KEYS = [s.key for s in SLOTS if s.required]

# מותגים מוכרים בישראל
allowed_brands = ["טויוטה","מאזדה","יונדאי","קיה","פולקסווגן","סקודה",
"סוזוקי","מיצובישי","ניסאן","הונדה","פיג'ו","סיטרואן","רנו",
"שברולט","פורד","סיאט","אופל"]

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

def normalize_costs(ac: Dict[str,int], model:str) -> Dict[str,int]:
    if ac["insurance"] < 6000 or ac["insurance"] > 12000:
        ac["insurance"] = 9000
    if ac["fuel"] < 3000 or ac["fuel"] > 15000:
        ac["fuel"] = 8000
    if ac["maintenance"] < 1000 or ac["maintenance"] > 6000:
        ac["maintenance"] = 3000
    if ac["repairs"] < 500 or ac["repairs"] > 5000:
        ac["repairs"] = 2000
    if ac["depreciation"] < 2000 or ac["depreciation"] > 15000:
        if any(b in model for b in ["טויוטה","מאזדה","הונדה","סוזוקי","ניסאן","מיצובישי"]):
            ac["depreciation"] = 4000
        elif any(b in model for b in ["יונדאי","קיה"]):
            ac["depreciation"] = 5000
        elif any(b in model for b in ["פולקסווגן","סקודה","סיאט","אופל"]):
            ac["depreciation"] = 6000
        elif any(b in model for b in ["פיג'ו","סיטרואן","רנו"]):
            ac["depreciation"] = 7000
        else:
            ac["depreciation"] = 5000
    return ac

def check_model_reliability(model: str, answers: Dict[str,Any], repeats:int=3) -> Dict[str,Any]:
    results = []
    for _ in range(repeats):
        sub_prompt = f"""
        בדוק עבור הדגם {model} (יד שנייה בישראל, מחירים והערכות בשקלים חדשים – ₪ בלבד).
        התחשב בערכי יסוד מקומיים:
        - מחיר ליטר בנזין בישראל ~7 ₪
        - ביטוח שנתי לנהג צעיר: 7,000–10,000 ₪
        - טיפולים שנתיים: 2,000–3,500 ₪
        - ירידת ערך: רכבים יפניים 8–10%, קוריאניים 10–12%, אירופאיים 12–15%, צרפתיים 15–18%
        
        החזר JSON:
        {{
          "model":"{model}",
          "reliability":88,
          "annual_cost":{{
             "insurance": 8500,
             "fuel": 7500,
             "maintenance": 3000,
             "repairs": 2000,
             "depreciation": 4000
          }},
          "issues":["גיר","מערכת חשמל"]
        }}
        """
        txt = call_model(sub_prompt)
        try:
            data = json.loads(re.search(r"\{.*\}", txt, re.S).group())
            results.append(data)
        except Exception:
            pass

    if not results: 
        return {"model":model,"reliability":50,"annual_cost":{"insurance":9000,"fuel":8000,"maintenance":3000,"repairs":2000,"depreciation":5000},"issues":["נתון חסר"]}

    avg = {"model":model,"reliability":0,"annual_cost":{"insurance":0,"fuel":0,"maintenance":0,"repairs":0,"depreciation":0},"issues":[]}
    for r in results:
        avg["reliability"] += r.get("reliability",0)
        for k in avg["annual_cost"]:
            avg["annual_cost"][k] += r.get("annual_cost",{}).get(k,0)
        avg["issues"].extend(r.get("issues",[]))
    n = len(results)
    avg["reliability"] = int(avg["reliability"]/n)
    for k in avg["annual_cost"]:
        avg["annual_cost"][k] = int(avg["annual_cost"][k]/n)

    avg["annual_cost"] = normalize_costs(avg["annual_cost"], model)
    avg["issues"] = list(set(avg["issues"]))
    return avg

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
        if slot.kind == "int":
            val = parse_int(user_text)
            if val: st.session_state.answers[slot.key] = val
        else:
            st.session_state.answers[slot.key] = user_text.strip()
        st.session_state.last_ask = None

    nxt = next_missing_required()
    if nxt:
        st.session_state.last_ask = nxt
        with st.chat_message("assistant"):
            st.markdown(nxt.prompt)
        st.session_state.messages.append({"role":"assistant","content":nxt.prompt})
    else:
        answers = st.session_state.answers

        # 🔹 סיכום דרישות המשתמש
        summary_lines = []
        for s in SLOTS:
            val = answers.get(s.key)
            if val not in [None,"",0]:
                summary_lines.append(f"- {s.label}: {val}")
        summary_text = "### סיכום דרישותיך\n" + "\n".join(summary_lines)
        with st.chat_message("assistant"):
            st.markdown(summary_text)
        st.session_state.messages.append({"role":"assistant","content":summary_text})

        # 🔹 חיפוש רכבים
        with st.chat_message("assistant"):
            st.markdown("✅ מחפש רכבים מתאימים בישראל...")

        prompt = f"""בהתבסס על הקריטריונים: {json.dumps(answers, ensure_ascii=False)},
בחר 5 דגמי רכבים יד שנייה הנמכרים בישראל בלבד (יבוא סדיר או מקביל).
אל תכלול דגמים שלא נמכרים בפועל בישראל.
החזר JSON:
{{"recommendations":[{{"model":"דגם","why":"נימוק קצר"}}]}}"""
        txt = call_model(prompt)
        try:
            recs = json.loads(re.search(r"\{.*\}", txt, re.S).group())
        except Exception:
            recs = {"recommendations":[]}

        filtered = []
        for r in recs.get("recommendations",[]):
            if any(brand in r["model"] for brand in allowed_brands):
                filtered.append(r)
        if not filtered:
            filtered = [{"model":"טויוטה קורולה","why":"אמינה מאוד ובשוק הישראלי"},
                        {"model":"מאזדה 3","why":"פופולרית ושמירת ערך"},
                        {"model":"יונדאי i30","why":"נפוצה מאוד"},
                        {"model":"קיה סיד","why":"משפחתית חסכונית"},
                        {"model":"סקודה אוקטביה","why":"מרווחת ופופולרית בציים"}]

        all_models = [r["model"] for r in filtered]

        results = []
        for model in all_models:
            results.append(check_model_reliability(model, answers, repeats=3))

        # 🔹 טבלה מפורטת
        table_md = "| דגם | אמינות | ביטוח | דלק | תחזוקה | תיקונים | ירידת ערך | סה\"כ | תקלות |\n|---|---|---|---|---|---|---|---|---|\n"
        best_model = None
        best_total = 10**9
        for r in results:
            ac = r["annual_cost"]
            total = sum(ac.values())
            if total < best_total:
                best_total = total
                best_model = r["model"]
            table_md += f"| {r['model']} | {r['reliability']} | {ac['insurance']} | {ac['fuel']} | {ac['maintenance']} | {ac['repairs']} | {ac['depreciation']} | {total} | {', '.join(r['issues'])} |\n"

        final_msg = "### תוצאות בדיקת אמינות ותחזוקה\n" + table_md + f"\n✅ ההמלצה המובילה: **{best_model}**"
        with st.chat_message("assistant"):
            st.markdown(final_msg)
        st.session_state.messages.append({"role":"assistant","content":final_msg})

st.markdown("---")
st.caption("האפליקציה בודקת רק דגמים זמינים בישראל, מסכמת את דרישות המשתמש, מבצעת 3 בדיקות ממוצעות לכל דגם, מתקנת ערכים לא הגיוניים, ומחזירה עלויות מפורטות בשקלים חדשים.")
