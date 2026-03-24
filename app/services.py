import json

import requests
import streamlit as st
from deep_translator import GoogleTranslator

from app.constants import MOTIVATIONS, OFFLINE_DB_FALLBACK


@st.cache_data(show_spinner=False)
def translate_query(query: str) -> str:
    try:
        return GoogleTranslator(source="auto", target="en").translate(query).lower()
    except Exception:
        return query.lower()


@st.cache_data(show_spinner=False)
def load_fitness_db(path: str = "fitness_db.json") -> dict:
    try:
        with open(path, "r", encoding="utf-8") as f:
            raw = json.load(f)
            normalized = {}
            for food, vals in raw.items():
                normalized[food.lower()] = {
                    "cals": float(vals.get("calories", 0)),
                    "prot": float(vals.get("protein", 0)),
                    "carb": float(vals.get("carbs", 0)),
                    "fat": float(vals.get("fat", 0)),
                }
            return normalized
    except Exception:
        return OFFLINE_DB_FALLBACK


def robust_global_search(en_query: str) -> list:
    results = []
    url = "https://world.openfoodfacts.org/cgi/search.pl"
    try:
        res = requests.get(
            url,
            params={
                "action": "process",
                "search_terms": en_query,
                "json": "True",
                "fields": "product_name,nutriments,brands",
            },
            timeout=5,
        )
        if res.status_code == 200:
            results.extend(res.json().get("products", []))
    except Exception:
        return []

    seen = set()
    unique = []
    for product in results:
        name = product.get("product_name")
        if name and name not in seen:
            seen.add(name)
            unique.append(product)
    return unique


def calculate_targets(gender, age, weight, height, activity, goal):
    multipliers = {
        "Sedentary": 1.2,
        "Lightly active": 1.375,
        "Moderately active": 1.55,
        "Very active": 1.725,
        "Super active": 1.9,
    }
    bmr = (10 * weight) + (6.25 * height) - (5 * age) + (5 if gender == "Male" else -161)
    tdee = bmr * multipliers[activity]
    if "Weight Loss" in goal:
        cals = int(tdee - 500)
        p_pct, c_pct, f_pct = 0.40, 0.35, 0.25
    elif "Maintenance" in goal:
        cals = int(tdee)
        p_pct, c_pct, f_pct = 0.30, 0.40, 0.30
    elif "Muscle" in goal:
        cals = int(tdee + 300)
        p_pct, c_pct, f_pct = 0.25, 0.50, 0.25
    else:
        cals = int(tdee + 500)
        p_pct, c_pct, f_pct = 0.30, 0.50, 0.20
    prot = int((cals * p_pct) / 4)
    carb = int((cals * c_pct) / 4)
    fat = int((cals * f_pct) / 9)
    water = round((weight * 35) / 1000 + (0.75 if "active" in activity.lower() else 0), 1)
    return cals, prot, carb, fat, water


def generate_sms_alert(rem_c, rem_p, rem_water, goal):
    msg = ""
    if rem_water > 0.5:
        msg += f"💧 חסר לך עדיין {rem_water:.1f} ליטר מים ליעד! אל תשכח לשתות.\n"
    if rem_p > 20:
        msg += f"🥩 יש לך עוד {rem_p:.0f} גרם חלבון להשלים היום בשביל השרירים.\n"
    if rem_c > 300:
        msg += f"🔥 נשארו לך {rem_c:.0f} קלוריות! זמן לארוחה טובה.\n"
    if not msg:
        msg = "🏆 עמדת בכל היעדים שלך להיום! עבודה מדהימה."
    msg += f"\n💡 {MOTIVATIONS.get(goal, '')}"
    return msg


def suggest_meal(rem_cals: float, rem_protein: float) -> str:
    if rem_cals <= 0:
        return "הגעת ליעד הקלורי שלך. עדיף ארוחה קלה ועשירה בירקות."
    if rem_protein > 35:
        return "הצעה: חזה עוף + יוגורט/קוטג' + ירקות לסגירת חלבון בצורה נקייה."
    if rem_cals > 600:
        return "הצעה: ארוחה מלאה עם חלבון, פחמימה מורכבת ושומן טוב (למשל אורז, עוף, אבוקדו)."
    return "הצעה: נשנוש חכם כמו יוגורט חלבון, פרי וקצת שקדים."


def send_real_sms_mock(phone_number: str, text_message: str) -> bool:
    print(f"MOCK SMS SENT TO {phone_number}: {text_message}")
    return True
