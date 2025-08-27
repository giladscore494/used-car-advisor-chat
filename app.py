# -*- coding: utf-8 -*-
# UsedCarAdvisor – ChatBot-First with In-Chat Questionnaire (Streamlit, single-file)
# Run: streamlit run app.py

import os
import json
import re
from dataclasses import dataclass
from typing import List, Dict, Any, Optional
import time

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
# כפתור התחל מחדש
# =========================
if st.sidebar.button("🔄 התחל מחדש"):
    for key in list(st.session_state.keys()):
        del st.session_state[key]
    st.experimental_rerun()

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
    Slot("budget_min", "תקציב מינימום (₪)", "מה התקציב המינימלי שלך בשקלים? (לדוגמה: 40,000 או 40 אלף)", "int"),
    Slot("budget_max", "תקציב מקסימום (₪)", "מה התקציב המקסימלי שלך בשקלים? (לדוגמה: 80,000 או 80 אלף)", "int"),
    Slot("body", "סוג רכב", "איזה סוג רכב אתה מחפש? (לדוגמה: משפחתי, קטן, ג'יפ)", "text"),
    Slot("character", "אופי רכב", "האם אתה מחפש רכב ספורטיבי או יומיומי?", "text"),
    Slot("usage", "שימוש עיקרי", "השימוש העיקרי יהיה בעיר, בין-עירוני או שטח?", "text"),
    Slot("priority", "עדיפות מרכזית", "מה הכי חשוב לך – אמינות, נוחות, ביצועים או עיצוב?", "text"),
    Slot("passengers", "מספר נוסעים ממוצע", "בממוצע כמה נוסעים ייסעו ברכב? (לדוגמה: 5)", "int"),
    Slot("fuel", "סוג דלק", "איזה סוג דלק תעדיף – בנזין, דיזל, היברידי או חשמלי?", "text"),
    Slot("year_min", "שנת ייצור מינימלית", "מאיזו שנת ייצור מינימלית תרצה? (לדוגמה: 2015)", "int"),
    Slot("km_per_year", "ק\"מ לשנה", "כמה קילומטרים אתה נוסע בערך בשנה? (לדוגמה: 15000)", "int"),
    Slot("gearbox", "תיבת הילוכים", "יש לך העדפה לגיר – אוטומט או ידני?", "text"),
    Slot("gearbox_type", "סוג תיבת אוטומט", "אם תבחר אוטומט – האם חשוב לך שתהיה תיבה פלנטרית רגילה או שזה לא משנה (רובוטית / CVT)?", "text", required=False),
    Slot("region", "אזור בארץ", "באיזה אזור בארץ אתה גר?", "text"),
    Slot("engine_size", "נפח מנוע", "מה נפח המנוע המועדף עליך? (לדוגמה: 1600)", "int"),
    Slot("turbo", "טורבו", "האם אתה מחפש מנוע עם טורבו או בלי טורבו?", "text"),
]
REQUIRED_KEYS = [s.key for s in SLOTS if s.required]

# =========================
# App state
# =========================
if "messages" not in st.session_state:
    st.session_state.messages: List[Dict[str, str]] = [
        {"role":"assistant","content":"היי! אני היועץ לרכבים יד 2. נתחיל בשאלה קצרה – מה התקציב המינימלי שלך בשקלים? (לדוגמה: 40,000 או 40 אלף)"}
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
    text = text.lower().replace(",", "").replace(" ", "")
    if "אלף" in text:
        nums = re.findall(r"\d+", text)
        if nums:
            return int(nums[0]) * 1000
    nums = re.findall(r"\d+", text)
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

def normalize_costs(ac: Dict[str,int]) -> Dict[str,int]:
    if ac["insurance"] < 6000 or ac["insurance"] > 12000:
        ac["insurance"] = 9000
    if ac["fuel"] < 3000 or ac["fuel"] > 15000:
        ac["fuel"] = 8000
    if ac["maintenance"] < 1000 or ac["maintenance"] > 6000:
        ac["maintenance"] = 3000
    if ac["repairs"] < 500 or ac["repairs"] > 5000:
        ac["repairs"] = 2000
    if ac["depreciation"] < 2000 or ac["depreciation"] > 15000:
        ac["depreciation"] = 5000
    return ac

def check_model_reliability(model: str, answers: Dict[str,Any], repeats:int=2) -> Dict[str,Any]:
    results = []
    for _ in range(repeats):
        sub_prompt = f"""
        בדוק עבור הדגם {model} (יד שנייה בישראל).
        ודא שהדגם נמכר בפועל בישראל ובמחיר בין {answers.get('budget_min')} ל-{answers.get('budget_max')} ₪
        לפי מחירון לוי יצחק או אתר יד2. אם הדגם לא נכנס לתקציב – החזר "valid": false.

        החזר JSON:
        {{
          "model":"{model}",
          "price": 78000,
          "year": 2019,
          "valid": true,
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
        return {"model":model,"valid":False,"price":0,"year":0,"reliability":50,"annual_cost":{"insurance":9000,"fuel":8000,"maintenance":3000,"repairs":2000,"depreciation":5000},"issues":["נתון חסר"]}

    avg = {"model":model,"valid":True,"price":0,"year":0,"reliability":0,"annual_cost":{"insurance":0,"fuel":0,"maintenance":0,"repairs":0,"depreciation":0},"issues":[]}
    for r in results:
        if not r.get("valid", True):
            avg["valid"] = False
            continue
        avg["reliability"] += r.get("reliability",0)
        avg["price"] += r.get("price",0)
        avg["year"] = max(avg["year"], r.get("year",0))
        for k in avg["annual_cost"]:
            avg["annual_cost"][k] += r.get("annual_cost",{}).get(k,0)
        avg["issues"].extend(r.get("issues",[]))
    n = len(results)
    if n > 0:
        avg["reliability"] = int(avg["reliability"]/n)
        avg["price"] = int(avg["price"]/n) if avg["price"] else 0
        for k in avg["annual_cost"]:
            avg["annual_cost"][k] = int(avg["annual_cost"][k]/n)

    avg["annual_cost"] = normalize_costs(avg["annual_cost"])
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

        # סיכום דרישות
        summary_lines = []
        for s in SLOTS:
            val = answers.get(s.key)
            if val not in [None,"",0]:
                summary_lines.append(f"- {s.label}: {val}")
        summary_text = "### סיכום דרישותיך\n" + "\n".join(summary_lines)
        with st.chat_message("assistant"):
            st.markdown(summary_text)
        st.session_state.messages.append({"role":"assistant","content":summary_text})

        # Progress bar
        with st.chat_message("assistant"):
            progress_text = st.empty()
            bar = st.progress(0)
            for i in range(100):
                time.sleep(0.01)
                bar.progress(i+1)
                progress_text.markdown("⏳ מחפש רכבים מתאימים בישראל...")
            bar.empty()
            progress_text.empty()

        # חיפוש רכבים – עד 100
        prompt = f"""בהתבסס על הקריטריונים: {json.dumps(answers, ensure_ascii=False)},
החזר עד 100 דגמי רכבים יד שנייה הנמכרים בישראל בלבד.
לכל דגם כלול:
- model: שם מלא של הדגם
- price: מחיר ממוצע בשקלים (₪)
- year: שנתון מומלץ
- why: נימוק קצר
- valid: true/false (האם עומד בתקציב {answers.get('budget_min')}–{answers.get('budget_max')} ₪ לפי מחירון לוי יצחק או יד2)

החזר JSON:
{{"recommendations":[{{"model":"דגם","price":75000,"year":2018,"why":"נימוק קצר","valid":true}}]}}"""
        txt = call_model(prompt)
        try:
            recs = json.loads(re.search(r"\{.*\}", txt, re.S).group())
        except Exception:
            recs = {"recommendations":[]}

        all_recs = recs.get("recommendations", [])
        valid_recs = [r for r in all_recs if r.get("valid", True) and answers.get("budget_min") <= r.get("price",0) <= answers.get("budget_max")]

        results = []
        for r in valid_recs:
            checked = check_model_reliability(r["model"], answers, repeats=2)
            checked["price"] = r.get("price")
            checked["year"] = r.get("year")
            results.append(checked)

        # דירוג – אמינות גבוהה + עלות נמוכה
        def score(item):
            ac = item["annual_cost"]
            total = sum(ac.values())
            return (-item["reliability"], total)

        results_sorted = sorted(results, key=score)[:5]

        # טבלה
        table_md = "| דגם | שנתון מומלץ | מחיר (₪) | אמינות | ביטוח | דלק | תחזוקה | תיקונים | ירידת ערך | סה\"כ | תקלות |\n|---|---|---|---|---|---|---|---|---|---|---|\n"
        best_model = None
        for r in results_sorted:
            ac = r["annual_cost"]
            total = sum(ac.values())
            table_md += f"| {r['model']} | {r.get('year','-')} | {r.get('price','-')} | {r['reliability']} | {ac['insurance']} | {ac['fuel']} | {ac['maintenance']} | {ac['repairs']} | {ac['depreciation']} | {total} | {', '.join(r['issues'])} |\n"
        if results_sorted:
            best_model = results_sorted[0]["model"]

        final_msg = "### תוצאות בדיקת אמינות ותחזוקה\n" + table_md
        if best_model:
            final_msg += f"\n✅ ההמלצה המובילה: **{best_model}**"
        with st.chat_message("assistant"):
            st.markdown(final_msg)
        st.session_state.messages.append({"role":"assistant","content":final_msg})

st.markdown("---")
st.caption("האפליקציה מסכמת את דרישות המשתמש, מחפשת עד 100 דגמים, מסננת רק את אלו שבתקציב, בודקת אמינות ועלויות, ומציגה את 5 המתאימים ביותר.")