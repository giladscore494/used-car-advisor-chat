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
# שאלון – 40 שאלות (רק דוגמאות כאן)
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
    """שלב 1 – GPT: רשימת דגמים ראשונית (מותאמים לישראל + תקציב)"""
    min_budget = answers.get("מה התקציב המינימלי שלך בשקלים?", "")
    max_budget = answers.get("מה התקציב המקסימלי שלך בשקלים?", "")

    prompt = f"""
    אלו התשובות מהמשתמש:
    {answers}

    החזר רשימה של 5–7 דגמי רכבים מתאימים.
    חשוב:
    - הצע רק רכבים שנמכרים בישראל בפועל (יד שנייה).
    - כלול רק רכבים שהמחירון שלהם ביד שנייה נמצא בטווח {min_budget} עד {max_budget} שקלים.
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

def extract_numbers_from_text(text):
    """מחלץ מספרים מהטקסט"""
    numbers = re.findall(r'\d{1,3}(?:[ ,]\d{3})*|\d+', text)
    clean_numbers = []
    for n in numbers:
        try:
            clean_numbers.append(int(n.replace(",", "").replace(" ", "")))
        except:
            pass
    return clean_numbers

def filter_models_for_israel(models, min_budget, max_budget):
    """שלב 2 – סינון לפי זמינות בישראל + מחירון אמיתי מול התקציב"""
    filtered, debug_info = [], {}
    for model_name in models:
        payload = {
            "model": "sonar-medium-chat",
            "messages": [
                {"role": "system", "content": "ענה בקצרה, למשל: 'נפוץ בישראל, מחירון 12-18 אלף ₪' או 'לא נפוץ בישראל'."},
                {"role": "user", "content": f"האם {model_name} נמכר בישראל, ומה טווח המחירים האמיתי שלו ביד שנייה?"}
            ]
        }
        answer = safe_perplexity_call(payload)
        debug_info[model_name] = answer

        if isinstance(answer, str):
            ans = answer.lower()
            if "לא נפוץ" in ans or "לא נמכר" in ans:
                continue

            # חילוץ טווח מחיר והשוואה לתקציב
            nums = extract_numbers_from_text(answer)
            if len(nums) >= 2:
                low, high = min(nums), max(nums)
                if low <= max_budget and high >= min_budget:
                    filtered.append(model_name)
            else:
                # אם לא מצא מספרים אבל כן כתוב נפוץ → נאשר גמיש
                if "נפוץ" in ans or "נמכר" in ans:
                    filtered.append(model_name)

    return filtered, debug_info

def fetch_models_data_with_perplexity(models, answers):
    """שלב 2 – Perplexity: נתונים מלאים (10 פרמטרים)"""
    all_data = {}
    for model_name in models:
        payload = {
            "model": "sonar-medium-chat",
            "messages": [
                {"role": "system", "content": "החזר מידע עובדתי ותמציתי בלבד, בעברית."},
                {"role": "user", "content": f"""
                תשובות המשתמש: {answers}

                הבא מידע עדכני על {model_name} בישראל, לפי:
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

                החזר תשובה כרשימה ממוספרת 1–10 בלבד.
                """}
            ]
        }
        answer = safe_perplexity_call(payload)
        all_data[model_name] = answer
    return all_data

def final_recommendation_with_gpt(answers, models, models_data):
    """שלב 3 – GPT: המלצה סופית"""
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
    - כלול שיקולים כלכליים (מחירון, ביטוח, תחזוקה) ושימושיים (בטיחות, נוחות, אמינות)
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

    # תקציב מהשאלון
    try:
        min_budget = int(answers.get("מה התקציב המינימלי שלך בשקלים?", "0").replace("אלף","000").replace(" ",""))
    except:
        min_budget = 0
    try:
        max_budget = int(answers.get("מה התקציב המקסימלי שלך בשקלים?", "999999").replace("אלף","000").replace(" ",""))
    except:
        max_budget = 999999

    with st.spinner("🇮🇱 מסנן דגמים מול מחירון האמיתי..."):
        israeli_models, debug_info = filter_models_for_israel(initial_models, min_budget, max_budget)

    with st.expander("🔎 תשובות Perplexity לסינון"):
        st.write(debug_info)

    if not israeli_models:
        st.error("❌ לא נמצאו דגמים זמינים בישראל בטווח המחירים שציינת.")
    else:
        st.success(f"✅ דגמים זמינים בישראל בתקציב: {israeli_models}")

        with st.spinner("🌐 שולף נתונים מלאים מ־Perplexity..."):
            models_data = fetch_models_data_with_perplexity(israeli_models, answers)

        with st.expander("📊 נתוני Perplexity גולמיים"):
            st.write(models_data)

        with st.spinner("⚡ יוצר המלצה סופית עם GPT..."):
            summary = final_recommendation_with_gpt(answers, israeli_models, models_data)

        st.subheader("🔎 ההמלצה הסופית שלך")
        st.write(summary)
