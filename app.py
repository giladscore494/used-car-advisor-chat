import os
import re
import requests
import streamlit as st
from openai import OpenAI

# =============================
# שליפת מפתחות API
# =============================
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
PERPLEXITY_API_KEY = os.getenv("PERPLEXITY_API_KEY")

if not OPENAI_API_KEY or not PERPLEXITY_API_KEY:
    st.error("❌ לא נמצאו מפתחות API. ודא שהגדרת אותם בסיקרטס.")
    st.stop()

client = OpenAI(api_key=OPENAI_API_KEY)

# =============================
# פונקציית קריאה בטוחה ל־Perplexity
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

# =============================
# שאלון – 40 שאלות (מקוצר כאן)
# =============================
questions = [
    "מה טווח התקציב שלך לרכב?",
    "מה התקציב המינימלי שלך בשקלים?",
    "מה התקציב המקסימלי שלך בשקלים?",
    "כמה קילומטרים אתה נוסע בממוצע בחודש?",
    "האם הרכב מיועד בעיקר לנסיעות עירוניות או בין-עירוניות?",
    "כמה אנשים יושבים בדרך כלל ברכב?",
    "האם אתה זקוק לתא מטען גדול?",
    "אתה מתכנן לנסוע הרבה עם ציוד כבד או גרירה?",
    "אתה מעדיף רכב בנזין, דיזל, היברידי או חשמלי?",
    "האם חסכון בדלק קריטי עבורך?",
    # ... (שאר ה־40 שאלות כמו קודם)
]

# =============================
# פונקציות Pipeline
# =============================

def analyze_needs_with_gpt(answers):
    """שלב 1 – GPT: רשימת דגמים ראשונית"""
    prompt = f"""
    אלו התשובות מהמשתמש:
    {answers}

    החזר רשימה של 5–7 דגמי רכבים מתאימים.
    חשוב:
    - הצע רק רכבים שנמכרים בישראל בפועל (חדשים או יד שנייה).
    - אל תציע גרסאות מנוע/תצורה שלא נמכרו בישראל.
    - החזר רשימה נקייה: רק שם הדגם, כל דגם בשורה נפרדת, בלי מספרים ובלי הסברים.
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
        if not line:
            continue
        line = re.sub(r"^[0-9\.\-\•\*\s]+", "", line)
        if len(line.split()) <= 6:
            clean_models.append(line)
    return clean_models

def filter_models_for_israel(models):
    """שלב 2 – סינון לפי זמינות בישראל + מחירון/הערכה"""
    filtered, debug_info = [], {}
    for model_name in models:
        payload = {
            "model": "sonar-medium-online",
            "messages": [
                {"role": "system", "content": "ענה בקצרה, למשל: 'נפוץ בישראל ויש מחירון', 'נפוץ בישראל ויש הערכת מחיר', או 'לא נפוץ בישראל'."},
                {"role": "user", "content": f"האם {model_name} נמכר בישראל בשוק היד שנייה, והאם יש לו מחירון או לפחות הערכת מחיר?"}
            ]
        }
        answer = safe_perplexity_call(payload)
        debug_info[model_name] = answer
        if isinstance(answer, str):
            ans = answer.lower()
            if "לא נפוץ" in ans or "לא נמכר" in ans:
                continue
            if any(w in ans for w in ["נפוץ", "נמכר", "קיים", "כן"]) and any(w in ans for w in ["מחיר", "שווי", "הערכה"]):
                filtered.append(model_name)
    return filtered, debug_info

def fetch_models_data_with_perplexity(models, answers):
    """שלב 3 – Perplexity: נתונים מלאים"""
    all_data = {}
    for model_name in models:
        payload = {
            "model": "sonar-medium-online",
            "messages": [
                {"role": "system", "content": "החזר מידע עובדתי ותמציתי בלבד, בעברית."},
                {"role": "user", "content": f"""
                תשובות המשתמש: {answers}

                הבא מידע עדכני על {model_name} בישראל:
                - מחירון ממוצע ליד שנייה
                - עלות ביטוח ממוצעת
                - אגרת רישוי וטסט שנתית
                - עלות טיפולים שנתית ממוצעת
                - תקלות נפוצות
                - צריכת דלק אמיתית
                - ירידת ערך ממוצעת
                - דירוג בטיחות
                - זמינות חלפים ועלותם
                - ביקוש בשוק היד שנייה
                """}
            ]
        }
        answer = safe_perplexity_call(payload)
        all_data[model_name] = answer
    return all_data

def final_recommendation_with_gpt(answers, models, models_data):
    """שלב 4 – GPT: המלצה סופית"""
    text = f"""
    תשובות המשתמש:
    {answers}

    דגמים זמינים בישראל:
    {models}

    נתוני Perplexity:
    {models_data}

    צור המלצה סופית בעברית:
    - הצג עד 5 דגמים בלבד
    - הוסף נימוק אישי לכל דגם
    - השווה יתרונות וחסרונות
    - כלול שיקולים כלכליים ושימושיים
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
    for q in questions:
        answers[q] = st.text_input(q, "")
    submitted = st.form_submit_button("שלח וקבל המלצה")

if submitted:
    with st.spinner("🤖 GPT בוחר דגמים ראשוניים..."):
        initial_models = analyze_needs_with_gpt(answers)
    st.info(f"📋 דגמים ראשוניים: {initial_models}")

    with st.spinner("🇮🇱 מסנן דגמים (ישראל + מחירון/הערכה)..."):
        israeli_models, debug_info = filter_models_for_israel(initial_models)

    with st.expander("🔎 תשובות Perplexity לסינון"):
        st.write(debug_info)

    if not israeli_models:
        st.error("❌ לא נמצאו דגמים זמינים בישראל עם מחירון או הערכת מחיר.")
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
