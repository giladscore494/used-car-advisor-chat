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
cache = {}  # { hash_key: (timestamp, result) }

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
        r = requests.post(url, headers=headers, json=payload, timeout=60)
        data = r.json()
        if "choices" not in data:
            return f"שגיאת API: {data}"
        return data["choices"][0]["message"]["content"]
    except Exception as e:
        return f"שגיאה: {e}"

def extract_numbers_from_text(text):
    numbers = re.findall(r'\d{1,3}(?:[ ,]\d{3})*|\d+', text)
    return [int(n.replace(",", "").replace(" ", "")) for n in numbers]

# =============================
# שלב 1 – GPT מציע דגמים ראשוניים
# =============================
def analyze_needs_with_gpt(answers):
    prompt = f"""
    המשתמש נתן את ההעדפות:
    {answers}

    החזר רשימה של 5–7 דגמי רכבים מתאימים.
    דרישות חובה:
    - רק דגמים שנמכרים בישראל ביד שנייה.
    - רק רכבים שהמחירון שלהם ביד שנייה נמצא בטווח {answers['budget_min']}–{answers['budget_max']} ₪.
    - מנוע {answers['engine']}, נפח {answers['engine_size']} סמ״ק.
    - שנות ייצור: {answers['year_range']}.
    - סוג רכב מועדף: {answers['car_type']}
    - העדפת תיבת הילוכים: {answers['gearbox']}
    - העדפת טורבו: {answers['turbo']}
    """
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.2,
    )
    text = response.choices[0].message.content
    clean_models = [re.sub(r"^[0-9\.\-\•\*\s]+", "", line.strip()) for line in text.split("\n") if line.strip()]
    return clean_models

# =============================
# שלב 2 – סינון עם Perplexity
# =============================
def filter_models_for_israel(models, min_budget, max_budget, engine, gearbox, turbo, engine_size, year_range):
    filtered, debug_info = [], {}
    for model_name in models:
        payload = {
            "model": "sonar",
            "messages": [
                {"role": "system", "content": "החזר תשובה בעברית ובקצרה בלבד."},
                {"role": "user", "content": f"האם {model_name} נמכר בישראל ביד שנייה עם מנוע {engine} {engine_size} סמ\"ק, גיר {gearbox}, {'טורבו' if turbo=='כן' else 'ללא טורבו'}, שנות ייצור {year_range}? ומה טווח המחירים האמיתי שלו?"}
            ]
        }
        answer = safe_perplexity_call(payload)
        debug_info[model_name] = answer

        if isinstance(answer, str):
            ans = answer.lower()
            if "לא נפוץ" in ans or "לא נמכר" in ans:
                continue
            nums = extract_numbers_from_text(answer)
            if len(nums) >= 2:
                low, high = min(nums), max(nums)
                if low <= max_budget and high >= min_budget:
                    filtered.append(model_name)
            else:
                if "נפוץ" in ans or "נמכר" in ans:
                    filtered.append(model_name)
    return filtered, debug_info

# =============================
# שלב 3 – נתונים מלאים ב-JSON
# =============================
def fetch_models_data_with_perplexity(models, answers):
    all_data = {}
    for model_name in models:
        payload = {
            "model": "sonar-pro",
            "messages": [
                {"role": "system", "content": "ענה בפורמט JSON בלבד. אל תוסיף טקסט חופשי."},
                {"role": "user", "content": f"""
                הבא מידע עדכני על {model_name} בישראל.
                החזר תשובה בפורמט JSON עם השדות הבאים:
                {{
                 "price_range": "טווח מחירון ממוצע ביד שנייה",
                 "availability": "זמינות ונפוצות בישראל",
                 "insurance": "עלות ביטוח ממוצעת",
                 "license_fee": "אגרת רישוי/טסט שנתית",
                 "maintenance": "תחזוקה שנתית ממוצעת",
                 "common_issues": "תקלות נפוצות ידועות",
                 "fuel_consumption": "צריכת דלק אמיתית",
                 "depreciation": "ירידת ערך ממוצעת",
                 "safety": "דירוג בטיחות",
                 "parts_availability": "זמינות חלפים בישראל"
                }}
                """}
            ]
        }
        answer = safe_perplexity_call(payload)
        try:
            parsed = json.loads(answer)
        except:
            parsed = {"price_range": answer}  # fallback
        all_data[model_name] = parsed
    return all_data

# =============================
# שלב 4 – GPT מסכם המלצה
# =============================
def final_recommendation_with_gpt(answers, models, models_data):
    text = f"""
    תשובות המשתמש:
    {answers}

    דגמים זמינים בישראל:
    {models}

    נתוני Perplexity (JSON):
    {models_data}

    צור המלצה סופית בעברית:
    - הצג עד 5 דגמים בלבד
    - פרט יתרונות וחסרונות
    - כלול נימוקים אישיים לפי התקציב, סוג המנוע, נפח מנוע, שנות ייצור, טורבו וגיר
    """
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": text}],
        temperature=0.5,
    )
    return response.choices[0].message.content

# =============================
# Streamlit UI
# =============================
st.set_page_config(page_title="Car-Advisor", page_icon="🚗")
st.title("🚗 Car-Advisor – יועץ רכבים חכם")

with st.form("car_form"):
    st.write("ענה על השאלון:")

    answers = {}
    answers["budget_range"] = st.selectbox("מה טווח התקציב שלך לרכב?", ["5–10K", "10–20K", "20–40K", "40K+"])
    answers["budget_min"] = int(st.text_input("תקציב מינימלי (₪)", "10000"))
    answers["budget_max"] = int(st.text_input("תקציב מקסימלי (₪)", "20000"))
    answers["km"] = st.selectbox("כמה קילומטרים אתה נוסע בחודש?", ["<1000", "1000–2000", "2000–4000", "4000+"])
    answers["engine"] = st.radio("איזה סוג מנוע אתה מעדיף?", ["בנזין", "דיזל", "היברידי", "חשמלי"])
    answers["engine_size"] = st.selectbox("מה נפח המנוע המועדף?", ["1200", "1600", "2000", "3000+"])
    answers["year_range"] = st.selectbox("מה שנות הייצור הרצויות?", ["2010–2015", "2016–2020", "2021+"])
    answers["usage"] = st.radio("מה השימוש העיקרי ברכב?", ["עירוני", "בין-עירוני", "מעורב"])
    answers["size"] = st.selectbox("איזה גודל רכב מתאים לך?", ["קטן", "משפחתי", "SUV", "טנדר"])
    answers["car_type"] = st.selectbox("איזה סוג רכב מתאים לך?", ["סדאן", "האצ'בק", "SUV", "טנדר", "משפחתי"])
    answers["turbo"] = st.radio("אתה מעדיף מנוע עם טורבו?", ["לא משנה", "כן", "לא"])
    answers["gearbox"] = st.radio("איזה סוג תיבת הילוכים אתה מעדיף?", ["לא משנה", "אוטומט", "ידני", "רובוטי"])
    answers["passengers"] = st.radio("כמה אנשים נוסעים לרוב ברכב?", ["1", "2–3", "4–5", "6+"])
    answers["fuel_eff"] = st.radio("עד כמה חשוב חסכון בדלק?", ["לא חשוב", "בינוני", "חשוב מאוד"])
    answers["safety"] = st.radio("עד כמה חשובה רמת בטיחות?", ["נמוך", "בינוני", "גבוה מאוד"])
    answers["extra"] = st.text_area("יש משהו נוסף שחשוב לציין?")

    submitted = st.form_submit_button("שלח וקבל המלצה")

if submitted:
    cached_result = get_from_cache(answers)
    if cached_result:
        st.success("✅ התוצאה נטענה מהמאגר (Cache, 24 שעות)")
        summary = cached_result
    else:
        with st.spinner("🤖 GPT בוחר דגמים ראשוניים..."):
            initial_models = analyze_needs_with_gpt(answers)
        st.info(f"📋 דגמים ראשוניים: {initial_models}")

        with st.spinner("🇮🇱 מסנן דגמים מול מחירון אמיתי וסוג מנוע..."):
            israeli_models, debug_info = filter_models_for_israel(
                initial_models, answers["budget_min"], answers["budget_max"],
                answers["engine"], answers["gearbox"], answers["turbo"],
                answers["engine_size"], answers["year_range"]
            )

        with st.expander("🔎 תשובות Perplexity לסינון"):
            st.write(debug_info)

        if not israeli_models:
            st.error("❌ לא נמצאו דגמים זמינים בישראל בהתאם לדרישות.")
        else:
            st.success(f"✅ דגמים זמינים בישראל: {israeli_models}")

            with st.spinner("🌐 שולף נתונים מלאים מ־Perplexity..."):
                models_data = fetch_models_data_with_perplexity(israeli_models, answers)

            # טבלת השוואה
            df = pd.DataFrame(models_data).T
            st.subheader("📊 השוואת נתונים בין הדגמים")
            st.dataframe(df)

            with st.spinner("⚡ יוצר המלצה סופית עם GPT..."):
                summary = final_recommendation_with_gpt(answers, israeli_models, models_data)

            st.subheader("🔎 ההמלצה הסופית שלך")
            st.write(summary)

            save_to_cache(answers, summary)

    # הערות חשובות בסוף
    st.markdown("---")
    st.markdown("⚠️ **חשוב לדעת:**")
    st.markdown("1. מומלץ לבדוק את [מאגר העבר הביטוחי של מרכז הסליקה](https://www.cbc.org.il/) לקבלת היסטוריית תאונות על הרכב.")
    st.markdown("2. רצוי לקחת את הרכב לבדיקה במכון בדיקה מורשה לפני רכישה.")
