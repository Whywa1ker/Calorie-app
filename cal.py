import streamlit as st
import pandas as pd
import requests
from PIL import Image, ImageEnhance
from pyzbar.pyzbar import decode
from deep_translator import GoogleTranslator
import plotly.express as px
import plotly.graph_objects as go
import base64
from datetime import date
import json
import os

# --- 0. Database & Auth Setup ---
DB_FILE = "myfitness_users_db.json"

def load_db():
    if os.path.exists(DB_FILE):
        try:
            with open(DB_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except: return {"users": {}}
    return {"users": {}}

def sync_db():
    with open(DB_FILE, "w", encoding="utf-8") as f:
        json.dump(db, f, indent=4)

db = load_db()

# --- 1. Constants & Offline DB ---
EXERCISE_METS = {
    "Weightlifting (Standard)": 5.0, "Weightlifting (Heavy)": 6.0,
    "Running (10 km/h)": 9.8, "Running (12 km/h)": 11.8,
    "Walking (Brisk)": 4.3, "Cycling (Moderate)": 6.8,
    "Swimming (Freestyle)": 8.3, "HIIT / Circuit": 8.0,
    "Yoga / Stretching": 2.5, "Custom (Manual Input)": 0.0
}

OFFLINE_DB = {
    "white bread": {"cals": 265, "prot": 8.0, "carb": 50.0, "fat": 3.0},
    "chicken breast": {"cals": 165, "prot": 31.0, "carb": 0.0, "fat": 3.6},
    "egg": {"cals": 155, "prot": 13.0, "carb": 1.1, "fat": 11.0},
    "cooked rice": {"cals": 130, "prot": 2.7, "carb": 28.0, "fat": 0.3},
    "cottage cheese": {"cals": 95, "prot": 11.0, "carb": 4.0, "fat": 5.0},
    "milk": {"cals": 60, "prot": 3.2, "carb": 4.7, "fat": 3.0},
    "tahini": {"cals": 640, "prot": 24.0, "carb": 12.0, "fat": 54.0},
    "hummus": {"cals": 250, "prot": 8.0, "carb": 14.0, "fat": 18.0},
    "oats": {"cals": 389, "prot": 16.9, "carb": 66.0, "fat": 6.9},
    "bamba": {"cals": 534, "prot": 15.0, "carb": 40.0, "fat": 35.0},
    "tuna": {"cals": 116, "prot": 26.0, "carb": 0.0, "fat": 1.0}
}

# --- 2. Helper Functions ---
@st.cache_data(show_spinner=False)
def translate_query(query):
    try: return GoogleTranslator(source='auto', target='en').translate(query).lower()
    except: return query.lower()

@st.cache_data(show_spinner=False)
def get_food_by_barcode(barcode):
    url = f"https://world.openfoodfacts.org/api/v0/product/{barcode}.json"
    try:
        res = requests.get(url, timeout=5)
        if res.status_code == 200 and res.json().get("status") == 1: return res.json().get("product")
    except: return None
    return None

@st.cache_data(show_spinner=False)
def robust_global_search(en_query):
    results, url = [], "https://world.openfoodfacts.org/cgi/search.pl"
    try:
        res = requests.get(url, params={"action": "process", "search_terms": en_query, "json": "True", "fields": "product_name,nutriments,brands"}, timeout=5)
        if res.status_code == 200: results.extend(res.json().get("products", []))
    except: pass
    seen, unique = set(), []
    for p in results:
        name = p.get('product_name')
        if name and name not in seen: seen.add(name); unique.append(p)
    return unique

def calculate_targets(gender, age, weight, height, activity, goal):
    multipliers = {"Sedentary": 1.2, "Lightly active": 1.375, "Moderately active": 1.55, "Very active": 1.725, "Super active": 1.9}
    bmr = (10 * weight) + (6.25 * height) - (5 * age) + (5 if gender == "Male" else -161)
    tdee = bmr * multipliers[activity]
    if goal == "Weight Loss (Cut)": cals = int(tdee - 500); p_pct, c_pct, f_pct = 0.40, 0.35, 0.25
    elif goal == "Maintenance": cals = int(tdee); p_pct, c_pct, f_pct = 0.30, 0.40, 0.30
    elif goal == "Lean Muscle Gain": cals = int(tdee + 300); p_pct, c_pct, f_pct = 0.25, 0.50, 0.25
    else: cals = int(tdee + 500); p_pct, c_pct, f_pct = 0.30, 0.50, 0.20
    prot, carb, fat = int((cals*p_pct)/4), int((cals*c_pct)/4), int((cals*f_pct)/9)
    water_liters = round((weight * 35) / 1000 + (0.75 if "active" in activity.lower() else 0), 1)
    return cals, prot, carb, fat, water_liters

# --- 3. Session State ---
if 'logged_in' not in st.session_state: st.session_state.logged_in = False
if 'current_user' not in st.session_state: st.session_state.current_user = None
if 'auth_mode' not in st.session_state: st.session_state.auth_mode = "Login"

# --- 4. UI Config ---
st.set_page_config(page_title="MyFitness Pro", page_icon="💪", layout="centered")
st.markdown("""
<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
<style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;800&display=swap');
    html, body, [class*="css"] { font-family: 'Inter', sans-serif; }
    .stTabs [data-baseweb="tab-list"] { gap: 4px; border-bottom: 2px solid #e5e7eb; }
    .stTabs [data-baseweb="tab"] { border-radius: 8px 8px 0px 0px; padding: 12px 16px; color: #6b7280; font-weight: 500; font-size: 0.9rem; }
    .stTabs [aria-selected="true"] { background-color: #f3f4f6; color: #111827 !important; border-bottom: 3px solid #2e66ff; }
    .app-title { text-align: center; color: #111827; font-weight: 800; font-size: 2.2rem; margin-bottom: 0px; }
    .app-subtitle { text-align: center; color: #6b7280; font-size: 0.9rem; margin-top: -5px; margin-bottom: 20px; }
</style>
""", unsafe_allow_html=True)

# ==========================================
# AUTHENTICATION
# ==========================================
if not st.session_state.logged_in:
    st.markdown("<h1 class='app-title'><i class='fa-solid fa-bolt' style='color:#f59e0b;'></i> MyFitness Pro</h1>", unsafe_allow_html=True)
    st.markdown("<p class='app-subtitle'>Professional Nutrition Tracker</p>", unsafe_allow_html=True)
    col1, col2, col3 = st.columns([0.1, 0.8, 0.1])
    with col2:
        with st.container(border=True):
            if st.session_state.auth_mode == "Login":
                st.markdown("### <i class='fa-solid fa-user-check'></i> Login", unsafe_allow_html=True)
                log_email = st.text_input("Email", placeholder="yourname@email.com").lower().strip()
                log_pass = st.text_input("Password", type="password", placeholder="••••••••")
                if st.button("Login", type="primary", use_container_width=True):
                    if log_email in db["users"] and db["users"][log_email]["password"] == log_pass:
                        st.session_state.logged_in, st.session_state.current_user = True, log_email
                        st.rerun()
                    else: st.error("Invalid credentials.")
                st.divider()
                if st.button("Create an Account", use_container_width=True):
                    st.session_state.auth_mode = "Register"; st.rerun()
            
            elif st.session_state.auth_mode == "Register":
                st.markdown("### <i class='fa-solid fa-user-plus'></i> Register", unsafe_allow_html=True)
                reg_email = st.text_input("Email").lower().strip()
                reg_pass = st.text_input("Password", type="password")
                if st.button("Register & Get Code", type="primary", use_container_width=True):
                    if reg_email and len(reg_pass) >= 4:
                        st.session_state.temp_reg = {"e": reg_email, "p": reg_pass}
                        st.session_state.auth_mode = "Verify"; st.rerun()
                if st.button("Back to Login", use_container_width=True):
                    st.session_state.auth_mode = "Login"; st.rerun()
            
            elif st.session_state.auth_mode == "Verify":
                st.info("Enter '1234' to verify (Mock)")
                v_code = st.text_input("Enter Code:")
                if st.button("Verify Account", type="primary", use_container_width=True):
                    if v_code == "1234":
                        email = st.session_state.temp_reg["e"]
                        db["users"][email] = {"password": st.session_state.temp_reg["p"], "onboarding_done": False, "profile": {}, "daily_log": [], "exercise_log": [], "weight_log": [], "custom_foods": {}, "water_liters": 0.0}
                        sync_db(); st.session_state.logged_in, st.session_state.current_user = True, email; st.rerun()

# ==========================================
# MAIN APP FLOW
# ==========================================
else:
    user_data = db["users"][st.session_state.current_user]
    
    if not user_data.get("onboarding_done", False):
        st.markdown("<h2 style='text-align: center;'>Setting Up Your Profile</h2>", unsafe_allow_html=True)
        with st.container(border=True):
            gen = st.selectbox("Gender", ["Male", "Female"])
            age = st.number_input("Age", min_value=10, value=21)
            weight = st.number_input("Current Weight (kg)", min_value=30.0, value=75.0)
            height = st.number_input("Height (cm)", min_value=100.0, value=175.0)
            act = st.selectbox("Activity Level", ["Sedentary", "Lightly active", "Moderately active", "Very active", "Super active"])
            goal = st.selectbox("Goal", ["Weight Loss (Cut)", "Maintenance", "Lean Muscle Gain", "Bodybuilding (Bulk)"])
            if st.button("Calculate Plan", type="primary", use_container_width=True):
                cals, prot, carb, fat, water = calculate_targets(gen, age, weight, height, act, goal)
                user_data.update({"profile": {"gender": gen, "age": age, "height": height, "activity": act, "goal": goal, "targets": {"cals": cals, "prot": prot, "carb": carb, "fat": fat, "water": water}}, "weight_log": [{"Date": str(date.today()), "Weight": weight}], "onboarding_done": True})
                sync_db(); st.rerun()
    else:
        profile = user_data["profile"]; targets = profile["targets"]
        w_log = user_data.get("weight_log", [])
        current_weight = sorted(w_log, key=lambda x: x["Date"])[-1]["Weight"] if w_log else 75.0
        recommended_water = calculate_targets(profile["gender"], profile["age"], current_weight, profile["height"], profile["activity"], profile["goal"])[4]

        with st.sidebar:
            st.markdown(f"**<i class='fa-solid fa-user-circle'></i> {st.session_state.current_user}**", unsafe_allow_html=True)
            if st.button("Logout"): st.session_state.logged_in = False; st.rerun()
            st.divider()
            st.markdown("### <i class='fa-solid fa-glass-water' style='color:#38bdf8;'></i> Water Tracker", unsafe_allow_html=True)
            t_water = st.number_input("Goal (L)", value=float(targets.get("water", recommended_water)), step=0.25)
            w_c1, w_c2, w_c3 = st.columns([1,1,1])
            if w_c1.button("-0.25"): user_data["water_liters"] = max(0.0, user_data.get("water_liters", 0.0) - 0.25); sync_db()
            w_c2.markdown(f"<h3 style='text-align:center;'>{user_data.get('water_liters', 0.0):.1f}L</h3>", unsafe_allow_html=True)
            if w_c3.button("+0.25"): user_data["water_liters"] = user_data.get("water_liters", 0.0) + 0.25; sync_db()
            st.progress(min(user_data.get("water_liters", 0.0) / t_water, 1.0) if t_water > 0 else 0)

        st.markdown("<h1 class='app-title'><i class='fa-solid fa-bolt' style='color:#f59e0b;'></i> MyFitness Pro</h1>", unsafe_allow_html=True)
        tabs = st.tabs(["Dashboard", "Add Food", "Workouts", "Weight"])

        with tabs[0]: # Dashboard
            # --- FIXED ERROR HERE: Initialize DataFrame with columns ---
            df_f = pd.DataFrame(user_data.get("daily_log", []))
            if df_f.empty:
                df_f = pd.DataFrame(columns=["Meal", "Food", "Grams", "Calories", "Protein", "Carbs", "Fat"])
            
            df_e = pd.DataFrame(user_data.get("exercise_log", []))
            if df_e.empty:
                df_e = pd.DataFrame(columns=["Exercise", "Burned"])

            t_food = df_f['Calories'].sum()
            t_burn = df_e['Burned'].sum()
            rem_c = targets["cals"] - (t_food - t_burn)
            
            with st.container(border=True):
                st.markdown("### <i class='fa-solid fa-fire-flame-curved'></i> Calorie Balance", unsafe_allow_html=True)
                st.metric("Remaining", f"{rem_c:.0f} kcal" if rem_c >= 0 else f"⚠️ Over {abs(rem_c):.0f} kcal")
                st.progress(min(max(0, (t_food - t_burn) / targets["cals"]), 1.0) if targets["cals"] > 0 else 0)
            
            # Macros
            col_ma, col_pi = st.columns([1.5, 1])
            with col_ma:
                t_p, t_c, t_f = df_f['Protein'].sum(), df_f['Carbs'].sum(), df_f['Fat'].sum()
                for m, cur, goal, color in [("Protein", t_p, targets["prot"], "#EF553B"), ("Carbs", t_c, targets["carb"], "#636EFA"), ("Fat", t_f, targets["fat"], "#00CC96")]:
                    diff = goal - cur
                    st.markdown(f"**{m}:** {cur:.0f}g / {goal}g ({f'{diff:.0f}g left' if diff>=0 else f'Over {abs(diff):.0f}g'})")
                    st.progress(min(cur / goal, 1.0) if goal > 0 else 0)
            
            # Diary Categories
            st.divider()
            for meal in ["Breakfast", "Lunch", "Dinner", "Snacks"]:
                m_data = df_f[df_f["Meal"] == meal]
                with st.expander(f"{meal} ({m_data['Calories'].sum():.0f} kcal)"):
                    if not m_data.empty: st.dataframe(m_data[["Food", "Grams", "Calories"]], use_container_width=True, hide_index=True)
                    else: st.caption("No items logged yet.")
            
            if st.button("Reset Entire Day"): 
                user_data.update({"daily_log": [], "exercise_log": [], "water_liters": 0.0}); sync_db(); st.rerun()

        with tabs[1]: # Add Food
            selected_meal = st.radio("Logging to:", ["Breakfast", "Lunch", "Dinner", "Snacks"], horizontal=True)
            with st.expander("📷 Scan Barcode"):
                cam = st.camera_input("Barcode", label_visibility="collapsed")
            query = st.text_input("🔍 Search Food", placeholder="Name or Barcode")
            if cam or query:
                code = ""
                if cam:
                    dec = decode(Image.open(cam))
                    if dec: code = dec[0].data.decode("utf-8")
                final_q = code if code else query
                
                # Search logic (omitted for brevity, keeping existing robust search)
                en = translate_query(final_q)
                res = robust_global_search(en)
                if res:
                    opt = {f"{p.get('product_name','U')} ({p.get('brands','N/A')})": p for p in res[:10]}
                    sel_g = st.selectbox("Select Result:", list(opt.keys()))
                    w = st.number_input("Grams eaten:", value=100.0)
                    if st.button("Add to Diary"):
                        n = opt[sel_g].get('nutriments', {})
                        user_data["daily_log"].append({
                            "Meal": selected_meal, "Food": sel_g, "Grams": w,
                            "Calories": round((n.get("energy-kcal_100g",0)*w)/100, 1),
                            "Protein": round((n.get("proteins_100g",0)*w)/100, 1),
                            "Carbs": round((n.get("carbohydrates_100g",0)*w)/100, 1),
                            "Fat": round((n.get("fat_100g",0)*w)/100, 1)
                        })
                        sync_db(); st.success("Added!"); st.rerun()

        with tabs[2]: # Workouts
            sel_e = st.selectbox("Activity:", list(EXERCISE_METS.keys()))
            dur = st.number_input("Duration (min):", min_value=1, value=45)
            burn = int((EXERCISE_METS[sel_e] * 3.5 * current_weight) / 200 * dur)
            if st.button("Log Exercise"):
                user_data["exercise_log"].append({"Exercise": sel_e, "Burned": burn}); sync_db(); st.rerun()

        with tabs[3]: # Weight
            w_in = st.number_input("Today's Weight (kg)", value=float(current_weight))
            if st.button("Save Weight"):
                ds = str(date.today())
                user_data["weight_log"] = [e for e in user_data["weight_log"] if e["Date"] != ds]
                user_data["weight_log"].append({"Date": ds, "Weight": w_in})
                sync_db(); st.rerun()
            if len(user_data["weight_log"]) > 1:
                df_w = pd.DataFrame(user_data["weight_log"])
                fig = px.line(df_w, x="Date", y="Weight", markers=True)
                st.plotly_chart(fig, use_container_width=True)