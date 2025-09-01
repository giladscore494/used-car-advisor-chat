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
# שלב 1 – סינון ראשוני מול מאגר משרד התחבורה
# =============================
def filter_with_mot(answers, mot_file="car_models_israel_clean.csv"):
    if not os.path.exists(mot_file):
        st.error(f"❌ קובץ המאגר '{mot_file}' לא נמצא בתיקייה. ודא שהעלית אותו.")
        return []

    df = pd.read_csv(mot_file, encoding="utf-8-sig", on_bad_lines="skip")
    for col in ["year", "engine_cc"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    df["gearbox_norm"] = df["automatic"].apply(lambda x: "אוטומט" if x == 1 else "ידני")

    year_min = int(answers["year_min"])
    year_max = int(answers["year_max"])
    cc_min = int(answers["engine_cc_min"])
    cc_max = int(answers["engine_cc_max"])

    mask_year = df["year"].between(year_min, year_max, inclusive="both")
    mask_cc = df["engine_cc"].between(cc_min, cc_max, inclusive="both")
    mask_fuel = (answers["engine"] == "לא משנה") | (df["fuel"] == answers["engine"])
    mask_gear = (answers["gearbox"] == "לא משנה") | (df["gearbox_norm"] == answers["gearbox"])

    df_filtered = df[mask_year & mask_cc & mask_fuel & mask_gear].copy()
    return df_filtered.to_dict(orient="records")

# =============================
# שלב 2 – Perplexity בונה טבלת פרמטרים
# =============================
def fetch_models_10params(answers, verified_models):
    if not verified_models:
        return pd.DataFrame()

    models_text = pd.DataFrame(verified_models[:10]).to_markdown(index=False)

    prompt = f"""
המשתמש נתן את ההעדפות הבאות:
{answers}

רשימת דגמים מסוננים (עד 10 שורות לדוגמה):
{models_text}

החזר טבלה בפורמט Markdown עם הכותרות הבאות:
| דגם | טווח מחירון | זמינות בישראל | ביטוח חובה + צד ג׳ | אגרת רישוי | תחזוקה שנתית | תקלות נפוצות | צריכת דלק | ירידת ערך | בטיחות | חלפים בישראל | טורבו | מחוץ לתקציב |

חוקים:
- עבור על כל הדגמים שסופקו ברשימה.
- אל תחזיר טקסט חופשי או הסברים – אך ורק טבלה Markdown.
- אם טווח המחיר מחוץ לתקציב ({answers['budget_min']}–{answers['budget_max']} ₪) → בעמודת "מחוץ לתקציב" רשום כן, אחרת לא.
- אם לא ידוע ערך מסוים כתוב "לא ידוע".
"""

    answer = safe_perplexity_call(prompt)

    try:
        tables = pd.read_html(answer)
        if tables:
            return tables[0]
    except Exception:
        return pd.DataFrame()

    return pd.DataFrame()

# =============================
# שלב 3 – GPT מסכם ומדרג
# =============================
def final_recommendation_with_gpt(answers, df_params):
    text = f"""
    תשובות המשתמש:
    {answers}

    טבלת פרמטרים:
    {df_params.to_markdown(index=False)}

    צור סיכום בעברית:
    - בחר עד 5 דגמים בלבד
    - אל תכלול דגמים עם "מחוץ לתקציב" = כן
    - פרט יתרונות וחסרונות
    - התייחס לעלות ביטוח, תחזוקה, ירידת ערך, אמינות ושימוש עיקרי
    - הצג טבלה מסכמת עם 10 פרמטרים
    - הסבר למה הדגמים הכי מתאימים
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

with st.form("car_form"):
    answers = {}
    answers["budget_min"] = int(st.text_input("תקציב מינימלי (₪)", "5000"))
    answers["budget_max"] = int(st.text_input("תקציב מקסימלי (₪)", "20000"))

    answers["engine"] = st.radio("מנוע מועדף:", ["לא משנה", "בנזין", "דיזל", "היברידי-בנזין", "היברידי-דיזל", "חשמל"])
    answers["engine_cc_min"] = int(st.text_input("נפח מנוע מינימלי (סמ״ק):", "1200"))
    answers["engine_cc_max"] = int(st.text_input("נפח מנוע מקסימלי (סמ״ק):", "2000"))
    answers["year_min"] = st.text_input("שנת ייצור מינימלית:", "2000")
    answers["year_max"] = st.text_input("שנת ייצור מקסימלית:", "2020")

    answers["car_type"] = st.selectbox("סוג רכב:", ["סדאן", "האצ'בק", "SUV", "מיני", "סטיישן", "טנדר", "משפחתי"])
    answers["gearbox"] = st.radio("גיר:", ["לא משנה", "אוטומט", "ידני"])
    answers["turbo"] = st.radio("מנוע טורבו:", ["לא משנה", "כן", "לא"])
    answers["usage"] = st.radio("שימוש עיקרי:", ["עירוני", "בין-עירוני", "מעורב"])

    submitted = st.form_submit_button("שלח וקבל המלצה")

if submitted:
    with st.spinner("📊 סינון ראשוני מול מאגר משרד התחבורה..."):
        verified_models = filter_with_mot(answers)

    with st.spinner("🌐 Perplexity בונה טבלת פרמטרים..."):
        df_params = fetch_models_10params(answers, verified_models)

    if not df_params.empty:
        with st.spinner("⚡ GPT מסכם ומדרג..."):
            summary = final_recommendation_with_gpt(answers, df_params)

        st.subheader("🔎 ההמלצה הסופית שלך")
        st.write(summary)
    else:
        st.warning("⚠️ לא התקבלה טבלת פרמטרים תקינה מ-Perplexity")
