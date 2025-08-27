# -*- coding: utf-8 -*-
# UsedCarAdvisor – ChatBot-First with In-Chat Questionnaire (Streamlit, single-file)
# Run: streamlit run app.py

import os
import json
import re
import time
import requests
from bs4 import BeautifulSoup
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
    st.session_state.messages = [
        {"role":"assistant","content":"היי! אני היועץ לרכבים יד 2. נתחיל בשאלה קצרה – מה התקציב המינימלי שלך בשקלים? (לדוגמה: 40,000 או 40 אלף)"}
    ]
if "answers" not in st.session_state:
    st.session_state.answers = {}
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
# Search price via DuckDuckGo
# =========================
def search_price_from_google(query: str) -> Optional[tuple]:
    url = f"https://duckduckgo.com/html/?q={query}+מחירון+site:yad2.co.il"
    try:
        r = requests.get(url, timeout=10, headers={"User-Agent":"Mozilla/5.0"})
        r.raise_for_status()
    except Exception:
        return None

    soup = BeautifulSoup(r.text, "html.parser")
    links = [a["href"] for a in soup.find_all("a", href=True) if "yad2.co.il" in a["href"]]
    if not links:
        return None

    try:
        r2 = requests.get(links[0], timeout=10, headers={"User-Agent":"Mozilla/5.0"})
        text = r2.text
        # מציאת מספרים בדף
        prices = re.findall(r"\d{1,3}(?:,\d{3})", text)
        prices = [int(p.replace(",","")) for p in prices]
        prices = [p for p in prices if 1000 < p < 500000]  # טווח רלוונטי למחיר רכב
        if len(prices) >= 2:
            return min(prices), max(prices)
    except Exception:
        return None

    return None

# =========================
# Model Call Helper
# =========================
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
# Reliability Check
# =========================
def check_model_reliability(model: str, answers: Dict[str,Any]) -> Dict[str,Any]:
    price_range = search_price_from_google(model)
    if price_range:
        low, high = price_range
        context_price = f"נמצאו מחירים ב-Yad2 בגוגל בטווח {low}–{high} ₪"
    else:
        context_price = "לא נמצאו מחירים בגוגל, השתמש בהערכה"

    sub_prompt = f"""
    בדוק עבור הדגם {model} (יד שנייה בישראל).
    {context_price}.
    ודא שהמחיר בתוך הטווח {answers.get('budget_min')}–{answers.get('budget_max')} ₪.
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
        return json.loads(re.search(r"\{.*\}", txt, re.S).group())
    except Exception:
        return {"model":model,"valid":False,"price":0,"year":0,"reliability":50,
                "annual_cost":{"insurance":9000,"fuel":8000,"maintenance":3000,"repairs":2000,"depreciation":5000},
                "issues":["נתון חסר"]}

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
    if any(s.key not in st.session_state.answers for s in SLOTS if s.required):
        nxt = next(s for s in SLOTS if s.required and s.key not in st.session_state.answers)
        st.session_state.last_ask = nxt
        with st.chat_message("assistant"):
            st.markdown(nxt.prompt)
        st.session_state.messages.append({"role":"assistant","content":nxt.prompt})
    else:
        answers = st.session_state.answers
        summary_lines = [f"- {s.label}: {answers.get(s.key)}" for s in SLOTS if answers.get(s.key)]
        summary_text = "### סיכום דרישותיך\n" + "\n".join(summary_lines)
        with st.chat_message("assistant"):
            st.markdown(summary_text)
        st.session_state.messages.append({"role":"assistant","content":summary_text})

        # Progress
        with st.chat_message("assistant"):
            bar = st.progress(0)
            for i in range(100):
                time.sleep(0.01)
                bar.progress(i+1)
            bar.empty()

        # בקשת 10 דגמים
        prompt = f"""בהתבסס על הקריטריונים: {json.dumps(answers, ensure_ascii=False)},
בחר את 10 דגמי הרכבים היד שנייה שנמכרים בישראל שאתה מעריך שהם הכי מתאימים.
החזר JSON:
{{"recommendations":[{{"model":"דגם","price":75000,"year":2018,"why":"נימוק קצר","valid":true}}]}}"""
        txt = call_model(prompt)
        try:
            recs = json.loads(re.search(r"\{.*\}", txt, re.S).group())
        except:
            recs = {"recommendations":[]}

        all_recs = recs.get("recommendations", [])
        results = []
        for r in all_recs:
            checked = check_model_reliability(r["model"], answers)
            checked["price"] = r.get("price", checked["price"])
            checked["year"] = r.get("year", checked["year"])
            results.append(checked)

        # דירוג 5 מובילים
        def score(item):
            total = sum(item["annual_cost"].values())
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
st.caption("האפליקציה מחפשת 10 דגמים, בודקת מחירים חיים ב-Yad2 דרך חיפוש גוגל, בודקת אמינות ועלויות, ומציגה את 5 המומלצים ביותר.")