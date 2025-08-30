import os
import re
import time
import json
import requests
import streamlit as st
import pandas as pd
from openai import OpenAI

# =============================
# מפתחות API
# =============================
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
PERPLEXITY_API_KEY = os.getenv("PERPLEXITY_API_KEY")

if not OPENAI_API_KEY or not PERPLEXITY_API_KEY:
    st.error("❌ לא נמצאו מפתחות API. ודא שהגדרת אותם ב-secrets.")
    st.stop()

client = OpenAI(api_key=OPENAI_API_KEY)

# =============================
# Cache פנימי (24 שעות)
# =============================
cache = {}

def make_key(answers):
    return f"{answers['budget_min']}-{answers['budget_max']}-{answers['engine']}-{answers['usage']}-{answers['size']}-{answers['car_type']}-{answers['turbo']}-{answers['gearbox']}-{answers['engine_size']}-{answers['year_range']}"

def get_from_cache(answers, max_age_hours=24):
    key = make_key(answers)
    if key in cache:
        ts, result = cache[key]
        if time.time() - ts < max_age_hours * 3600:
            return result
    return None

def save_to_cache(answers, result):
    key = make_key(answers)
    cache[key] = (time.time(), result)

# =============================
# קריאה בטוחה ל-Perplexity
# =============================
def safe_perplexity_call(payload):
    url = "https://api.perplexity.ai/chat/completions"
    headers = {"Authorization": f"Bearer {PERPLEXITY_API_KEY}", "Content-Type": "application/json"}
    try:
        r = requests.post(url, headers=headers, json=payload, timeout=90)
        data = r.json()
        if "choices" not in data:
            return f"שגיאת API: {data}"
        return data["choices"][0]["message"]["content"]
    except Exception as e:
        return f"שגיאה: {e}"

# =============================
# שלב 1 – GPT מציע דגמים ראשוניים
# =============================
def analyze_needs_with_gpt(answers):
    prompt = f"""
    המשתמש נתן את ההעדפות:
    {answers}

    החזר רשימה של 7–10 דגמי רכבים אפשריים (שם בלבד).
    אל תוסיף מפרטים (שנה/מחיר/מנוע).
    """
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.2,
    )
    text = response.choices[0].message.content
    models = []
    for line in text.split("\n"):
        line = line.strip()
        if not line or ":" in line:
            continue
        line = re.sub(r"^[0-9\.\-\•\*\s]+", "", line)
        if line:
            models.append(line)
    return models

# =============================
# שלב 2 – סינון מוקדם ב-GPT (Pre-Filter)
# =============================
def prefilter_models_with_gpt(models, answers):
    prompt = f"""
    דגמים מוצעים: {models}
    תנאי סינון: תקציב {answers['budget_min']}–{answers['budget_max']} ₪,
    מנוע {answers['engine']} {answers['engine_size']} סמ״ק,
    שנות ייצור {answers['year_range']},
    גיר {answers['gearbox']}, טורבו {answers['turbo']}.

    החזר רשימה קצרה של 3–4 דגמים רלוונטיים בלבד.
    """
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}],
        temperature=0,
    )
    text = response.choices[0].message.content
    return [re.sub(r"^[0-9\.\-\•\*\s]+", "", l.strip()) for l in text.split("\n") if l.strip()]

# =============================
# שלב 3 – בקשה אחת לפרפליסיטי (Batch JSON)
# =============================
def fetch_models_data_with_perplexity(models, answers):
    models_str = ", ".join(models)
    payload = {
        "model": "sonar-pro",
        "messages": [
            {"role": "system", "content": "ענה בפורמט JSON בלבד. אל תוסיף טקסט חופשי."},
            {"role": "user", "content": f"""
            הבא מידע עדכני על הדגמים הבאים בישראל: {models_str}.

            עבור כל דגם החזר בפורמט JSON עם השדות:
            {{
              "Model Name": {{
                 "price_range": "טווח מחירון ממוצע ביד שנייה",
                 "availability": "זמינות בישראל",
                 "insurance": "עלות ביטוח ממוצעת",
                 "license_fee": "אגרת רישוי/טסט שנתית",
                 "maintenance": "תחזוקה שנתית ממוצעת",
                 "common_issues": "תקלות נפוצות",
                 "fuel_consumption": "צריכת דלק אמיתית",
                 "depreciation": "ירידת ערך ממוצעת",
                 "safety": "דירוג בטיחות",
                 "parts_availability": "זמינות חלפים בישראל"
              }}
            }}
            אל תוסיף טקסט מעבר ל-JSON.
            """}
        ]
    }
    answer = safe_perplexity_call(payload)
    try:
        return json.loads(answer)
    except:
        return {"error": "JSON לא תקין", "raw": answer}

# =============================
# שלב 4 – GPT מסכם המלצה
# =============================
def final_recommendation_with_gpt(answers, models, models_data):
    text = f"""
    תשובות המשתמש:
    {answers}

    דגמים זמינים:
    {models}

    נתוני Perplexity:
    {models_data}

    צור המלצה בעברית:
    - עד 5 דגמים בלבד
    - יתרונות וחסרונות
    - נימוקים אישיים לפי התקציב, סוג מנוע, שנות ייצור, טורבו וגיר
    """
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": text}],
        temperature=0.5,
    )
    return response.choices[0].message.content

# =============================
# UI
# =============================
st.set_page_config(page_title="Car-Advisor", page_icon="🚗")
st.title("🚗 Car-Advisor – יועץ רכבים חכם")

COLUMN_TRANSLATIONS = {
    "price_range": "טווח מחירון",
    "availability": "זמינות בישראל",
    "insurance": "עלות ביטוח",
    "license_fee": "אגרת רישוי",
    "maintenance": "תחזוקה שנתית",
    "common_issues": "תקלות נפוצות",
    "fuel_consumption": "צריכת דלק",
    "depreciation": "ירידת ערך",
    "safety": "בטיחות",
    "parts_availability": "חלפים בישראל"
}

with st.form("car_form"):
    answers = {}
    answers["budget_range"] = st.selectbox("טווח תקציב:", ["5–10K", "10–20K", "20–40K", "40K+"])
    answers["budget_min"] = int(st.text_input("תקציב מינימלי (₪)", "10000"))
    answers["budget_max"] = int(st.text_input("תקציב מקסימלי (₪)", "20000"))
    answers["engine"] = st.radio("מנוע מועדף:", ["בנזין", "דיזל", "היברידי", "חשמלי"])
    answers["engine_size"] = st.selectbox("נפח מנוע (סמ״ק):", ["1200", "1600", "2000", "3000+"])
    answers["year_range"] = st.selectbox("שנות ייצור:", ["2010–2015", "2016–2020", "2021+"])
    answers["car_type"] = st.selectbox("סוג רכב:", ["סדאן", "האצ'בק", "SUV", "טנדר", "משפחתי"])
    answers["turbo"] = st.radio("מנוע טורבו:", ["לא משנה", "כן", "לא"])
    answers["gearbox"] = st.radio("גיר:", ["לא משנה", "אוטומט", "ידני", "רובוטי"])
    answers["usage"] = st.radio("שימוש עיקרי:", ["עירוני", "בין-עירוני", "מעורב"])
    answers["size"] = st.selectbox("גודל רכב:", ["קטן", "משפחתי", "SUV", "טנדר"])
    answers["extra"] = st.text_area("משהו נוסף?")

    submitted = st.form_submit_button("שלח וקבל המלצה")

if submitted:
    cached = get_from_cache(answers)
    if cached:
        st.success("✅ תוצאה מהמאגר")
        summary = cached
    else:
        with st.spinner("🤖 מחפש דגמים מתאימים..."):
            initial = analyze_needs_with_gpt(answers)
            st.info(f"📋 דגמים ראשוניים: {initial}")

            filtered = prefilter_models_with_gpt(initial, answers)
            st.success(f"✅ דגמים לאחר סינון מוקדם: {filtered}")

            data = fetch_models_data_with_perplexity(filtered, answers)

            try:
                df = pd.DataFrame(data).T
                df.rename(columns=COLUMN_TRANSLATIONS, inplace=True)
                st.subheader("📊 השוואת נתונים")
                st.dataframe(df, use_container_width=True)
                # כפתור הורדה ל-CSV
                csv = df.to_csv(index=True, encoding="utf-8-sig")
                st.download_button("⬇️ הורד כ-CSV", csv, "car_advisor.csv", "text/csv")
            except:
                st.warning("⚠️ בעיה בנתוני JSON")
                st.write(data)

            with st.spinner("⚡ מסכם המלצה..."):
                summary = final_recommendation_with_gpt(answers, filtered, data)

            st.subheader("🔎 ההמלצה הסופית שלך")
            st.write(summary)

            save_to_cache(answers, summary)

    st.markdown("---")
    st.markdown("⚠️ **חשוב לדעת:**")
    col1, col2 = st.columns(2)
    with col1:
        st.markdown(
            f'<a href="https://infocar.co.il/" target="_blank">'
            f'<button style="background-color:#117A65;color:white;padding:10px 20px;'
            f'border:none;border-radius:8px;font-size:16px;cursor:pointer;">'
            f'🔗 בדוק עבר ביטוחי ב-InfoCar</button></a>',
            unsafe_allow_html=True
        )
    with col2:
        st.markdown("🚗 רצוי לקחת את הרכב לבדיקה במכון בדיקה מורשה לפני רכישה.")
