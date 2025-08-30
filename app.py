import os
import re
import requests
import streamlit as st
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
    clean = []
    for n in numbers:
        try:
            clean.append(int(n.replace(",", "").replace(" ", "")))
        except:
            pass
    return clean

# =============================
# שלב 1 – GPT מציע דגמים ראשוניים
# =============================
def analyze_needs_with_gpt(answers):
    min_budget = answers["budget_min"]
    max_budget = answers["budget_max"]
    engine = answers["engine"]

    prompt = f"""
    המשתמש נתן את ההעדפות:
    {answers}

    החזר רשימה של 5–7 דגמי רכבים מתאימים.
    דרישות חובה:
    - רק דגמים שנמכרים בישראל ביד שנייה.
    - רק רכבים שהמחירון שלהם ביד שנייה נמצא בטווח {min_budget}–{max_budget} ₪.
    - רק רכבים עם מנוע {engine}, אם קיים בישראל.
    החזר רשימה נקייה: כל שורה שם דגם בלבד, בלי מספרים ובלי הסברים.
    """
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.2,
    )
    text = response.choices[0].message.content
    clean_models = []
    for line in text.split("\n"):
        line = line.strip()
        if line:
            line = re.sub(r"^[0-9\.\-\•\*\s]+", "", line)
            if len(line.split()) <= 6:
                clean_models.append(line)
    return clean_models

# =============================
# שלב 2 – סינון עם Perplexity
# =============================
def filter_models_for_israel(models, min_budget, max_budget, engine):
    filtered, debug_info = [], {}
    for model_name in models:
        payload = {
            "model": "sonar",
            "messages": [
                {"role": "system", "content": "ענה בקצרה, למשל: 'נפוץ בישראל, מחירון 12-18 אלף ₪, מנוע דיזל'."},
                {"role": "user", "content": f"האם {model_name} נמכר בישראל ביד שנייה עם מנוע {engine}? ומה טווח המחירים האמיתי שלו?"}
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
# שלב 3 – נתונים מלאים מ-Perplexity
# =============================
def fetch_models_data_with_perplexity(models, answers):
    all_data = {}
    engine = answers["engine"]
    for model_name in models:
        payload = {
            "model": "sonar-pro",
            "messages": [
                {"role": "system", "content": "החזר מידע עובדתי ותמציתי בלבד, בעברית."},
                {"role": "user", "content": f"""
                הבא מידע עדכני על {model_name} בישראל עם מנוע {engine}, לפי:
                1. טווח מחירון ממוצע ביד שנייה (מספרים!)
                2. זמינות ונפוצות בישראל
                3. עלות ביטוח ממוצעת
                4. אגרת רישוי/טסט שנתית
                5. תחזוקה שנתית ממוצעת
                6. תקלות נפוצות ידועות
                7. צריכת דלק אמיתית
                8. ירידת ערך ממוצעת
                9. דירוג בטיחות
                10. זמינות חלפים בישראל
                """}
            ]
        }
        answer = safe_perplexity_call(payload)
        all_data[model_name] = answer
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

    נתוני Perplexity:
    {models_data}

    צור המלצה סופית בעברית:
    - הצג עד 5 דגמים בלבד
    - פרט יתרונות וחסרונות
    - כלול נימוקים אישיים לפי התקציב, סוג המנוע והשימושים
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
    answers["usage"] = st.radio("מה השימוש העיקרי ברכב?", ["עירוני", "בין-עירוני", "מעורב"])
    answers["size"] = st.selectbox("איזה גודל רכב מתאים לך?", ["קטן", "משפחתי", "SUV", "טנדר"])
    answers["passengers"] = st.radio("כמה אנשים נוסעים לרוב ברכב?", ["1", "2–3", "4–5", "6+"])
    answers["fuel_eff"] = st.radio("עד כמה חשוב חסכון בדלק?", ["לא חשוב", "בינוני", "חשוב מאוד"])
    answers["safety"] = st.radio("עד כמה חשובה רמת בטיחות?", ["נמוך", "בינוני", "גבוה מאוד"])
    answers["extra"] = st.text_area("יש משהו נוסף שחשוב לציין?")

    submitted = st.form_submit_button("שלח וקבל המלצה")

if submitted:
    with st.spinner("🤖 GPT בוחר דגמים ראשוניים..."):
        initial_models = analyze_needs_with_gpt(answers)
    st.info(f"📋 דגמים ראשוניים: {initial_models}")

    min_budget = answers["budget_min"]
    max_budget = answers["budget_max"]
    engine = answers["engine"]

    with st.spinner("🇮🇱 מסנן דגמים מול מחירון אמיתי וסוג מנוע..."):
        israeli_models, debug_info = filter_models_for_israel(initial_models, min_budget, max_budget, engine)

    with st.expander("🔎 תשובות Perplexity לסינון"):
        st.write(debug_info)

    if not israeli_models:
        st.error("❌ לא נמצאו דגמים זמינים בישראל בהתאם לתקציב ולסוג המנוע שבחרת.")
    else:
        st.success(f"✅ דגמים זמינים בישראל: {israeli_models}")

        with st.spinner("🌐 שולף נתונים מלאים מ־Perplexity..."):
            models_data = fetch_models_data_with_perplexity(israeli_models, answers)

        with st.expander("📊 נתוני Perplexity גולמיים"):
            st.write(models_data)

        with st.spinner("⚡ יוצר המלצה סופית עם GPT..."):
            summary = final_recommendation_with_gpt(answers, israeli_models, models_data)

        st.subheader("🔎 ההמלצה הסופית שלך")
        st.write(summary)
