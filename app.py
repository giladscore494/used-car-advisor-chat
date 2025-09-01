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
# פונקציית נרמול
# =============================
def normalize_text(val):
    if not isinstance(val, str):
        return ""
    return val.strip().replace("-", "").replace("־", "").replace(" ", "").lower()

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

    # נרמול
    df["fuel_norm"] = df["fuel"].apply(normalize_text)
    engine_norm = normalize_text(answers["engine"])

    df["gearbox_norm"] = df["automatic"].apply(lambda x: "אוטומט" if x == 1 else "ידני")

    st.write("🔍 DEBUG – ערכי fuel ייחודיים:", df["fuel"].unique())
    st.write("🔍 DEBUG – ערכי fuel_norm ייחודיים:", df["fuel_norm"].unique())

    # סינון
    year_min = int(answers["year_min"])
    year_max = int(answers["year_max"])
    cc_min = int(answers["engine_cc_min"])
    cc_max = int(answers["engine_cc_max"])

    mask_year = df["year"].between(year_min, year_max, inclusive="both")
    mask_cc = df["engine_cc"].between(cc_min, cc_max, inclusive="both")
    mask_fuel = (answers["engine"] == "לא משנה") | (df["fuel_norm"] == engine_norm)
    mask_gear = (answers["gearbox"] == "לא משנה") | (df["gearbox_norm"] == answers["gearbox"])

    df_filtered = df[mask_year & mask_cc & mask_fuel & mask_gear].copy()

    return df_filtered.to_dict(orient="records")

# =============================
# שלב 2 – Perplexity בונה טבלת פרמטרים
# =============================
def fetch_models_10params(answers, verified_models):
    if not verified_models:
        models_text = "[]"
    else:
        models_text = json.dumps(verified_models[:10], ensure_ascii=False)

    prompt = f"""
המשתמש נתן את ההעדפות הבאות:
{answers}

רשימת דגמים ממאגר משרד התחבורה (JSON עד 10 שורות לדוגמה):
{models_text}

החזר אך ורק JSON תקין בפורמט הבא, ללא טקסט נוסף:
{{
  "BMW X1 XDRIVE25E 2020 היברידי-בנזין": {{
     "price_range": "₪80,000–₪120,000",
     "availability": "נפוץ בישראל",
     "insurance_total": "₪6,000",
     "license_fee": "₪2,200",
     "maintenance": "₪4,000",
     "common_issues": "תקלות במערכת חשמלית",
     "fuel_consumption": "15 ק״מ לליטר",
     "depreciation": "10%",
     "safety": "5 כוכבים",
     "parts_availability": "גבוהה",
     "turbo": 1,
     "out_of_budget": false
  }}
}}

חוקים:
- עבור על כל דגם ברשימה שסופקה.
- חובה להחזיר JSON בלבד.
- אם טווח המחיר מחוץ לתקציב ({answers['budget_min']}–{answers['budget_max']} ₪) → החזר "out_of_budget": true.
- אם בטווח → "out_of_budget": false.
- אסור להמציא מחירים לא קשורים – אם לא ידוע כתוב "לא ידוע".
"""
    answer = safe_perplexity_call(prompt)
    return parse_perplexity_json(answer)

# =============================
# שלב 3 – GPT מסכם ומדרג
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
# פונקציית לוג
# =============================
def save_log(answers, params_data, summary, filename="car_advisor_logs.csv"):
    record = {
        "timestamp": datetime.datetime.now().isoformat(),
        "answers": json.dumps(answers, ensure_ascii=False),
        "params_data": json.dumps(params_data, ensure_ascii=False),
        "summary": summary,
    }
    if os.path.exists(filename):
        existing = pd.read_csv(filename)
        new_df = pd.DataFrame([record])
        final = pd.concat([existing, new_df], ignore_index=True)
    else:
        final = pd.DataFrame([record])
    final.to_csv(filename, index=False, encoding="utf-8-sig")

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
    answers["driver_age"] = st.selectbox("גיל הנהג הראשי:", ["עד 21", "21–24", "25–34", "35+"])
    answers["license_years"] = st.selectbox("ותק רישיון נהיגה:", ["פחות משנה", "1–3 שנים", "3–5 שנים", "מעל 5 שנים"])
    answers["insurance_history"] = st.selectbox("עבר ביטוחי/תעבורתי:", ["ללא", "תאונה אחת", "מספר תביעות"])
    answers["annual_km"] = st.selectbox("נסועה שנתית (ק״מ):", ["עד 10,000", "10,000–20,000", "20,000–30,000", "מעל 30,000"])
    answers["passengers"] = st.selectbox("מספר נוסעים עיקרי:", ["לרוב לבד", "2 אנשים", "3–5 נוסעים", "מעל 5"])
    answers["maintenance_budget"] = st.selectbox("יכולת תחזוקה:", ["מתחת 3,000 ₪", "3,000–5,000 ₪", "מעל 5,000 ₪"])
    answers["reliability_vs_comfort"] = st.selectbox("מה חשוב יותר?", ["אמינות מעל הכול", "איזון אמינות ונוחות", "נוחות/ביצועים"])
    answers["eco_pref"] = st.selectbox("שיקולי איכות סביבה:", ["חשוב רכב ירוק/חסכוני", "לא משנה"])
    answers["resale_value"] = st.selectbox("שמירת ערך עתידית:", ["חשוב לשמור על ערך", "פחות חשוב"])
    answers["extra"] = st.text_area("משהו נוסף שתרצה לציין?")

    submitted = st.form_submit_button("שלח וקבל המלצה")

# =============================
# טיפול אחרי שליחה
# =============================
if submitted:
    with st.spinner("📊 סינון ראשוני מול מאגר משרד התחבורה..."):
        verified_models = filter_with_mot(answers)
        st.write("🔍 DEBUG – דגמים אחרי סינון MOT:", verified_models)

    with st.spinner("🌐 Perplexity בונה טבלת פרמטרים..."):
        params_data = fetch_models_10params(answers, verified_models)
        st.write("🔍 DEBUG – פלט Perplexity גולמי:", params_data)

    try:
        df_params = pd.DataFrame(params_data).T

        COLUMN_TRANSLATIONS = {
            "price_range": "טווח מחירון",
            "availability": "זמינות בישראל",
            "insurance_total": "ביטוח חובה + צד ג׳",
            "license_fee": "אגרת רישוי",
            "maintenance": "תחזוקה שנתית",
            "common_issues": "תקלות נפוצות",
            "fuel_consumption": "צריכת דלק",
            "depreciation": "ירידת ערך",
            "safety": "בטיחות",
            "parts_availability": "חלפים בישראל",
            "turbo": "טורבו",
            "out_of_budget": "מחוץ לתקציב"
        }
        df_params.rename(columns=COLUMN_TRANSLATIONS, inplace=True)

        st.session_state["df_params"] = df_params

        st.subheader("🟩 טבלת פרמטרים")
        st.dataframe(df_params, use_container_width=True)

    except Exception as e:
        st.warning("⚠️ בעיה בנתוני JSON")
        st.write(params_data)

    with st.spinner("⚡ GPT מסכם ומדרג..."):
        summary = final_recommendation_with_gpt(answers, params_data)
        st.session_state["summary"] = summary

    st.subheader("🔎 ההמלצה הסופית שלך")
    st.write(st.session_state["summary"])

    save_log(answers, params_data, st.session_state["summary"])

# =============================
# הורדת טבלה מה-session
# =============================
if "df_params" in st.session_state:
    csv2 = st.session_state["df_params"].to_csv(index=True, encoding="utf-8-sig")
    st.download_button("⬇️ הורד טבלת פרמטרים", csv2, "params_data.csv", "text/csv")

# =============================
# כפתור הורדה של כל ההיסטוריה
# =============================
log_file = "car_advisor_logs.csv"
if os.path.exists(log_file):
    with open(log_file, "rb") as f:
        st.download_button(
            "⬇️ הורד את כל היסטוריית השאלונים",
            f,
            file_name="car_advisor_logs.csv",
            mime="text/csv"
        )
