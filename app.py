import os
import re
import json
import requests
import datetime
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
def safe_perplexity_call(prompt, model="llama-3.1-sonar-large-128k-online"):
    """
    שולח שאילתה ל-Perplexity ומחזיר טקסט
    """
    url = "https://api.perplexity.ai/chat/completions"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {PERPLEXITY_API_KEY}"
    }
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.3
    }
    try:
        r = requests.post(url, headers=headers, json=payload, timeout=120)
        data = r.json()
        if "choices" not in data:
            return f"שגיאת Perplexity: {data}"
        return data["choices"][0]["message"]["content"]
    except Exception as e:
        return f"שגיאה: {e}"

# =============================
# פיענוח JSON
# =============================
def parse_perplexity_json(answer):
    cleaned = answer.strip()
    if "```" in cleaned:
        match = re.search(r"```(?:json)?(.*?)```", cleaned, re.DOTALL)
        if match:
            cleaned = match.group(1).strip()
    try:
        return json.loads(cleaned)
    except Exception:
        return {}

# =============================
# שלב 1 – סינון ראשוני מול מאגר משרד התחבורה
# =============================
def filter_with_mot(answers, mot_file="car_models_israel_clean.csv"):
    if not os.path.exists(mot_file):
        st.error(f"❌ קובץ המאגר '{mot_file}' לא נמצא בתיקייה. ודא שהעלית אותו.")
        return []

    df = pd.read_csv(mot_file)

    for col in ["year", "engine_cc"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    year_min = int(answers["year_min"])
    year_max = int(answers["year_max"])
    cc_min = int(answers["engine_cc_min"])
    cc_max = int(answers["engine_cc_max"])

    mask_year = df["year"].between(year_min, year_max, inclusive="both")
    mask_cc = df["engine_cc"].between(cc_min, cc_max, inclusive="both")

    mask_fuel = df["fuel"] == answers["engine"]
    mask_gear = (answers["gearbox"] == "לא משנה") | \
                ((answers["gearbox"] == "אוטומט") & (df["automatic"] == 1)) | \
                ((answers["gearbox"] == "ידני") & (df["automatic"] == 0))

    df_filtered = df[mask_year & mask_cc & mask_fuel & mask_gear].copy()

    return df_filtered.to_dict(orient="records")

# =============================
# שלב 2 – Perplexity בונה טבלת פרמטרים
# =============================
def fetch_models_10params(answers, verified_models):
    prompt = f"""
    המשתמש נתן את ההעדפות הבאות:
    {answers}

    רשימת דגמים ממאגר משרד התחבורה:
    {verified_models}

    עבור כל דגם החזר JSON בפורמט:
    {{
      "Model (year, engine, fuel)": {{
         "price_range": "טווח מחירון ביד שנייה בישראל (₪)",
         "availability": "זמינות בישראל",
         "insurance_total": "עלות ביטוח חובה + צד ג' (₪)",
         "license_fee": "אגרת רישוי/טסט שנתית (₪)",
         "maintenance": "תחזוקה שנתית ממוצעת (₪)",
         "common_issues": "תקלות נפוצות",
         "fuel_consumption": "צריכת דלק אמיתית (ק״מ לליטר)",
         "depreciation": "ירידת ערך ממוצעת (%)",
         "safety": "דירוג בטיחות (כוכבים)",
         "parts_availability": "זמינות חלפים בישראל",
         "turbo": 0/1,
         "out_of_budget": false
      }}
    }}

    חוקים:
    - חובה להחזיר טווח מחירון אמיתי מהשוק הישראלי בלבד.
    - אם טווח המחיר מחוץ לתקציב ({answers['budget_min']}–{answers['budget_max']} ₪) → החזר "out_of_budget": true.
    - אם בטווח → "out_of_budget": false.
    - אסור להמציא מחירים. אם לא ידוע → "לא ידוע".
    """
    answer = safe_perplexity_call(prompt)
    return parse_perplexity_json(answer)

# =============================
# שלב 3 – GPT מסכם ומדרג (נשאר כמו קודם)
# =============================
def final_recommendation_with_gpt(answers, params_data):
    text = f"""
    תשובות המשתמש:
    {answers}

    נתוני פרמטרים:
    {params_data}

    צור סיכום בעברית:
    - בחר עד 5 דגמים בלבד
    - אל תכלול דגמים עם "out_of_budget": true
    - פרט יתרונות וחסרונות
    - התייחס לעלות ביטוח, תחזוקה, ירידת ערך, אמינות ושימוש עיקרי
    - הסבר למה הדגמים הכי מתאימים
    """
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": text}],
        temperature=0.4,
    )
    return response.choices[0].message.content

# =============================
# שאר הקוד – UI, לוג, הורדות
# =============================
# (העתק מהגרסה שלך – זהה לחלוטין, רק שלב 2 שונה)
