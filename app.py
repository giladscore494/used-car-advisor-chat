import os
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
# 40 שאלות
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
    "עד כמה חשובים לך ביצועים (כוח מנוע, תאוצה)?",
    "מה רמת הבטיחות המינימלית שאתה דורש (כוכבי בטיחות, מערכות מתקדמות)?",
    "האם חשוב לך מערכות עזר מתקדמות (בלימה אוטונומית, בקרת שיוט אדפטיבית)?",
    "אתה מעדיף רכב חדש או יד שנייה?",
    "כמה שנים אתה מתכנן להחזיק ברכב?",
    "כמה חשוב לך שמירת ערך (ירידת ערך איטית)?",
    "איזה גודל רכב אתה מחפש (קטן, משפחתי, ג'יפון, SUV, טנדר)?",
    "האם יש מגבלת חניה/גודל באזור המגורים שלך?",
    "מהי רמת הגימור שחשובה לך (בסיסי, בינוני, גבוה)?",
    "עד כמה חשוב לך נוחות בנסיעות ארוכות?",
    "יש העדפה ליצרן/מותג מסוים?",
    "יש העדפה למדינה יצרנית (יפן, גרמניה, קוריאה וכו')?",
    "אתה מחפש רכב אמין מאוד עם תחזוקה זולה או מוכן להשקיע בתחזוקה גבוהה יותר?",
    "כמה חשוב לך שהרכב יהיה חדשני מבחינת טכנולוגיה?",
    "האם חשוב לך חיבורי מולטימדיה (CarPlay/Android Auto)?",
    "האם חשוב לך מושבים חשמליים/עור/אוורור?",
    "מהי רמת רעש סבירה מבחינתך בנסיעה?",
    "כמה חשוב לך בידוד רעשים?",
    "יש צורך ביכולות שטח (4x4)?",
    "אתה מתכנן לנסוע בעיקר לבד או עם משפחה?",
    "יש לך ילדים קטנים? (דרוש Isofix, דלתות רחבות)",
    "מה תדירות הנסיעות הארוכות שלך?",
    "מהי רמת התקציב השוטף שאתה מוכן להשקיע בביטוח וטיפולים?",
    "יש לך העדפה לידני/אוטומטי?",
    "כמה חשוב לך עיצוב הרכב (1-10)?",
    "מה טווח השנים של הרכב שתרצה (למשל 2015 ומעלה)?",
    "כמה חשוב לך לוח מחוונים דיגיטלי?",
    "האם תעדיף רכב עם אחריות יצרן עדיין בתוקף?",
    "כמה חשוב לך צריכת דלק אמיתית לעומת נתוני יצרן?",
    "יש משהו נוסף שחשוב לציין?"
]

# =============================
# פונקציות Pipeline
# =============================

def analyze_needs_with_gpt(answers):
    """שלב 1 – GPT: ניתוח תשובות והצעת רשימת דגמים ראשונית"""
    prompt = f"""
    אלו התשובות מהמשתמש:
    {answers}

    על בסיס זה, הצע רשימה של 5-7 דגמי רכבים מתאימים לדרישות.
    החזר רק רשימה נקייה של שמות דגמים, כל אחד בשורה חדשה, ללא הסברים.
    """
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.3,
    )
    return [m.strip() for m in response.choices[0].message.content.split("\n") if m.strip()]

def filter_models_for_israel(models):
    """בודק עם Perplexity אם הדגם נמכר בישראל בכמות מספקת"""
    url = "https://api.perplexity.ai/chat/completions"
    headers = {
        "Authorization": f"Bearer {PERPLEXITY_API_KEY}",
        "Content-Type": "application/json"
    }
    filtered = []
    for model_name in models:
        query = f"האם {model_name} נמכר בישראל בכמות גבוהה יחסית כך שקל למצוא אותו בשוק היד שנייה בישראל? ענה 'כן' או 'לא' בלבד."
        payload = {
            "model": "sonar-medium-online",
            "messages": [
                {"role": "system", "content": "ענה רק 'כן' או 'לא'."},
                {"role": "user", "content": query}
            ]
        }
        try:
            r = requests.post(url, headers=headers, json=payload, timeout=30)
            answer = r.json()["choices"][0]["message"]["content"].strip().lower()
            if "כן" in answer:
                filtered.append(model_name)
        except Exception:
            pass
    return filtered

def fetch_models_data_with_perplexity(models):
    """שלב 2 – Perplexity: חיפוש חי על כל דגם"""
    url = "https://api.perplexity.ai/chat/completions"
    headers = {
        "Authorization": f"Bearer {PERPLEXITY_API_KEY}",
        "Content-Type": "application/json"
    }
    all_data = {}
    for model_name in models:
        query = f"מידע עדכני על {model_name} בישראל: אמינות, מחירון יד שנייה, צריכת דלק, יתרונות וחסרונות."
        payload = {
            "model": "sonar-medium-online",
            "messages": [
                {"role": "system", "content": "תחזיר מידע עובדתי ועדכני בלבד."},
                {"role": "user", "content": query}
            ]
        }
        try:
            r = requests.post(url, headers=headers, json=payload, timeout=30)
            all_data[model_name] = r.json()["choices"][0]["message"]["content"]
        except Exception:
            all_data[model_name] = "❌ שגיאה בשליפת מידע"
    return all_data

def final_recommendation_with_gpt(answers, models, models_data):
    """שלב 3 – GPT: שילוב הכל להמלצה סופית"""
    text = f"""
    תשובות המשתמש:
    {answers}

    דגמים זמינים בישראל:
    {models}

    מידע עובדתי מ־Perplexity:
    {models_data}

    צור המלצה סופית בעברית:
    - הצג 5 דגמים בלבד (אם יש פחות – הצג את מה שנמצא)
    - הוסף נימוק לכל דגם בהתבסס על הדרישות של המשתמש
    - השווה יתרונות וחסרונות
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

    with st.spinner("🇮🇱 מסנן דגמים שלא זמינים בישראל..."):
        israeli_models = filter_models_for_israel(initial_models)

    if not israeli_models:
        st.error("❌ לא נמצאו דגמים זמינים בישראל לפי הדרישות שלך.")
    else:
        st.success(f"✅ דגמים זמינים בישראל: {israeli_models}")

        with st.spinner("🌐 שולף מידע חי מ־Perplexity..."):
            models_data = fetch_models_data_with_perplexity(israeli_models)

        with st.spinner("⚡ יוצר המלצה סופית עם GPT..."):
            summary = final_recommendation_with_gpt(answers, israeli_models, models_data)

        st.subheader("🔎 ההמלצה הסופית שלך")
        st.write(summary)
