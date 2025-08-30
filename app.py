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
# שלב 1 – Perplexity מחזיר טבלה מלאה
# =============================
def fetch_models_data_with_perplexity(answers):
    payload = {
        "model": "sonar-pro",
        "messages": [
            {"role": "system", "content": "ענה בפורמט JSON בלבד. אל תוסיף טקסט חופשי."},
            {"role": "user", "content": f"""
            המשתמש נתן את ההעדפות הבאות:
            {answers}

            הצע עד 7 דגמים מתאימים שנמכרים בישראל בטווח התקציב {answers['budget_min']}–{answers['budget_max']} ₪.

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
# שלב 2 – GPT מסנן ומסכם
# =============================
def final_recommendation_with_gpt(answers, models_data):
    text = f"""
    תשובות המשתמש:
    {answers}

    נתוני הדגמים מ-Perplexity:
    {models_data}

    צור המלצה בעברית:
    - כלול עד 5 דגמים בלבד
    - הסבר יתרונות וחסרונות
    - הסבר התאמה אישית לפי התקציב, מנוע, שנות ייצור, נוחות, חסכוניות
    - אל תמציא מחירים או נתונים חדשים, הסתמך רק על המידע שניתן
    """
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": text}],
        temperature=0.4,
    )
    return response.choices[0].message.content

# =============================
# Streamlit UI
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
    with st.spinner("🌐 Perplexity בודק דגמים מתאימים..."):
        models_data = fetch_models_data_with_perplexity(answers)

    try:
        df = pd.DataFrame(models_data).T
        df.rename(columns=COLUMN_TRANSLATIONS, inplace=True)
        st.subheader("📊 השוואת נתונים בין הדגמים")
        st.dataframe(df, use_container_width=True)

        # כפתור הורדה ל-CSV
        csv = df.to_csv(index=True, encoding="utf-8-sig")
        st.download_button("⬇️ הורד כ-CSV", csv, "car_advisor.csv", "text/csv")

    except:
        st.warning("⚠️ בעיה בנתוני JSON")
        st.write(models_data)

    with st.spinner("⚡ GPT מסנן ומסכם..."):
        summary = final_recommendation_with_gpt(answers, models_data)

    st.subheader("🔎 ההמלצה הסופית שלך")
    st.write(summary)

    # הערות חשובות
    st.markdown("---")
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
