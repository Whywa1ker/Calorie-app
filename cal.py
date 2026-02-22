import streamlit as st
import pandas as pd
import requests
from PIL import Image, ImageEnhance
from pyzbar.pyzbar import decode
from deep_translator import GoogleTranslator
import plotly.express as px
import base64
from datetime import date
import json
import os

# --- 0. Database & Multi-User Setup ---
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

def get_csv_download_link(df, filename="log.csv"):
    b64 = base64.b64encode(df.to_csv(index=False).encode()).decode()
    return f'<a href="data:file/csv;base64,{b64}" download="{filename}" style="display:inline-block; padding:10px 20px; background-color:#2e66ff; color:white; text-align:center; font-weight:bold; text-decoration:none; border-radius:8px;">📥 Export Data</a>'

def calculate_targets(gender, age, weight, height, activity, goal):
    multipliers = {"Sedentary": 1.2, "Lightly active": 1.375, "Moderately active": 1.55, "Very active": 1.725, "Super active": 1.9}
    bmr = (10 * weight) + (6.25 * height) - (5 * age) + (5 if gender == "Male" else -161)
    tdee = bmr * multipliers[activity]
    
    if goal == "Weight Loss (Cut)": cals = int(tdee - 500); p_pct, c_pct, f_pct = 0.40, 0.35, 0.25
    elif goal == "Maintenance": cals = int(tdee); p_pct, c_pct, f_pct = 0.30, 0.40, 0.30
    elif goal == "Lean Muscle Gain": cals = int(tdee + 300); p_pct, c_pct, f_pct = 0.25, 0.50, 0.25
    else: cals = int(tdee + 500); p_pct, c_pct, f_pct = 0.30, 0.50, 0.20
        
    prot, carb, fat = int((cals*p_pct)/4), int((cals*c_pct)/4), int((cals*f_pct)/9)
    water = int((weight * 35 + (750 if "active" in activity.lower() else 0)) / 250)
    return cals, prot, carb, fat, water

# --- 3. Session State Init ---
if 'logged_in' not in st.session_state: st.session_state.logged_in = False
if 'current_user' not in st.session_state: st.session_state.current_user = None
if 'auth_mode' not in st.session_state: st.session_state.auth_mode = "Login"
if 'verify_code_sent' not in st.session_state: st.session_state.verify_code_sent = False
if 'temp_reg_data' not in st.session_state: st.session_state.temp_reg_data = {}

# --- 4. UI Config & CSS ---
st.set_page_config(page_title="MyFitness Pro", page_icon="⚡", layout="centered")
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;600;800&display=swap');
    html, body, [class*="css"]  { font-family: 'Inter', sans-serif; }
    .stTabs [data-baseweb="tab-list"] { gap: 8px; }
    .stTabs [data-baseweb="tab"] { border-radius: 6px 6px 0px 0px; padding: 10px 16px; background-color: #f0f2f6; }
    .stTabs [aria-selected="true"] { background-color: #2e66ff; color: white !important; }
    [data-testid="stMetricValue"] { font-weight: 800; color: #1f2937; }
</style>
""", unsafe_allow_html=True)


# ==========================================
# AUTHENTICATION ROUTING
# ==========================================
if not st.session_state.logged_in:
    st.markdown("<h1 style='text-align: center;'>⚡ MyFitness Pro</h1>", unsafe_allow_html=True)
    st.markdown("<p style='text-align: center; color: gray;'>Your Personal Nutrition & Fitness Tracker</p>", unsafe_allow_html=True)
    st.write("")
    
    col1, col2, col3 = st.columns([1,2,1])
    with col2:
        with st.container(border=True):
            if st.session_state.auth_mode == "Login":
                st.markdown("### 🔐 Login")
                log_email = st.text_input("Email").lower().strip()
                log_pass = st.text_input("Password", type="password")
                
                if st.button("Login", type="primary", use_container_width=True):
                    if log_email in db["users"] and db["users"][log_email]["password"] == log_pass:
                        st.session_state.logged_in = True
                        st.session_state.current_user = log_email
                        st.rerun()
                    else:
                        st.error("Invalid email or password.")
                
                st.write("")
                st.write("Don't have an account?")
                if st.button("Create an Account"):
                    st.session_state.auth_mode = "Register"
                    st.rerun()
                    
            elif st.session_state.auth_mode == "Register":
                st.markdown("### 📝 Register")
                
                if not st.session_state.verify_code_sent:
                    reg_email = st.text_input("Email").lower().strip()
                    reg_pass = st.text_input("Password", type="password")
                    
                    if st.button("Send Verification Code", type="primary", use_container_width=True):
                        if reg_email in db["users"]:
                            st.error("Account already exists!")
                        elif reg_email and len(reg_pass) >= 4:
                            st.session_state.temp_reg_data = {"email": reg_email, "pass": reg_pass}
                            st.session_state.verify_code_sent = True
                            st.rerun()
                        else:
                            st.error("Please enter a valid email and a password (min 4 chars).")
                            
                    st.write("")
                    if st.button("Back to Login"):
                        st.session_state.auth_mode = "Login"
                        st.rerun()
                else:
                    st.success(f"Code sent to {st.session_state.temp_reg_data['email']}!")
                    st.info("*(Mock Mode: Enter '1234' to verify)*")
                    v_code = st.text_input("Enter 4-digit code:")
                    
                    if st.button("Verify & Create Account", type="primary", use_container_width=True):
                        if v_code == "1234":
                            new_email = st.session_state.temp_reg_data["email"]
                            db["users"][new_email] = {
                                "password": st.session_state.temp_reg_data["pass"],
                                "onboarding_done": False,
                                "profile": {},
                                "daily_log": [], "exercise_log": [], "weight_log": [], "custom_foods": {}, "water": 0
                            }
                            sync_db()
                            st.session_state.logged_in = True
                            st.session_state.current_user = new_email
                            st.session_state.verify_code_sent = False
                            st.rerun()
                        else:
                            st.error("Invalid code.")
                    if st.button("Cancel Registration"):
                        st.session_state.verify_code_sent = False
                        st.session_state.auth_mode = "Login"
                        st.rerun()

# ==========================================
# APP ROUTING (ONBOARDING vs MAIN DASHBOARD)
# ==========================================
else:
    user_data = db["users"][st.session_state.current_user]
    
    # --- ONBOARDING FLOW ---
    if not user_data.get("onboarding_done", False):
        st.markdown("<h2 style='text-align: center;'>Welcome to MyFitness Pro! 🎉</h2>", unsafe_allow_html=True)
        st.markdown("<p style='text-align: center;'>Let's set up your personal profile to calculate your exact targets.</p>", unsafe_allow_html=True)
        
        with st.container(border=True):
            st.markdown("#### Physical Details")
            col1, col2 = st.columns(2)
            gen = col1.selectbox("Gender", ["Male", "Female"])
            age = col2.number_input("Age", min_value=10, max_value=100, value=21)
            weight = col1.number_input("Current Weight (kg)", min_value=30.0, max_value=200.0, value=75.0, step=0.5)
            height = col2.number_input("Height (cm)", min_value=100.0, max_value=250.0, value=175.0, step=