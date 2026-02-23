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

# --- 0. Database Setup ---
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

# --- 1. Constants ---
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
    "bamba": {"cals": 534, "prot": 15.0, "carb": 40.0, "fat": 35.0}
}

# --- 2. Core Functions ---
@st.cache_data(show_spinner=False)
def translate_query(query):
    try: return GoogleTranslator(source='auto', target='en').translate(query).lower()
    except: return query.lower()

def get_food_by_barcode(barcode):
    url = f"https://world.openfoodfacts.org/api/v0/product/{barcode}.json"
    try:
        res = requests.get(url, timeout=5)
        if res.status_code == 200 and res.json().get("status") == 1: return res.json().get("product")
    except: return None
    return None

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
    if "Weight Loss" in goal: cals = int(tdee - 500); p_pct, c_pct, f_pct = 0.40, 0.35, 0.25
    elif "Maintenance" in goal: cals = int(tdee); p_pct, c_pct, f_pct = 0.30, 0.40, 0.30
    elif "Muscle" in goal: cals = int(tdee + 300); p_pct, c_pct, f_pct = 0.25, 0.50, 0.25
    else: cals = int(tdee + 500); p_pct, c_pct, f_pct = 0.30, 0.50, 0.20
    prot, carb, fat = int((cals*p_pct)/4), int((cals*c_pct)/4), int((cals*f_pct)/9)
    water = round((weight * 35) / 1000 + (0.75 if "active" in activity.lower() else 0), 1)
    return cals, prot, carb, fat, water

# --- 3. UI Config ---
st.set_page_config(page_title="MyFitness Pro", page_icon="💪", layout="centered")
st.markdown("""
<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
<style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;800&display=swap');
    html, body, [class*="css"] { font-family: 'Inter', sans-serif; }
    
    /* Clean Tabs UI */
    .stTabs [data-baseweb="tab-list"] { gap: 4px; border-bottom: 2px solid #e5e7eb; }
    .stTabs [data-baseweb="tab"] { border-radius: 8px 8px 0px 0px; padding: 12px 16px; color: #6b7280; font-weight: 500; font-size: 0.9rem; }
    .stTabs [aria-selected="true"] { background-color: #f3f4f6; color: #111827 !important; border-bottom: 3px solid #2e66ff; }
    .app-title { text-align: center; color: #111827; font-weight: 800; font-size: 2.2rem; margin-bottom: 0px; }
    
    /* Native App Feel - Hide all toolbars, headers, and footers */
    header {visibility: hidden;}
    footer {visibility: hidden;}
    [data-testid="stToolbar"] {visibility: hidden;}
    [data-testid="stElementToolbar"] {display: none;}
</style>
""", unsafe_allow_html=True)

# --- 4. Auth State & "Remember Me" Auto-Login ---
if 'logged_in' not in st.session_state: 
    st.session_state.logged_in = False
if 'current_user' not in st.session_state: 
    st.session_state.current_user = None
if 'auth_mode' not in st.session_state: 
    st.session_state.auth_mode = "Login"
if 'camera_active' not in st.session_state:
    st.session_state.camera_active = False

if not st.session_state.logged_in and "user" in st.query_params:
    saved_user = st.query_params["user"]
    if saved_user in db["users"]:
        st.session_state.logged_in = True
        st.session_state.current_user = saved_user

# ==========================================
# AUTHENTICATION SCREEN
# ==========================================
if not st.session_state.logged_in:
    st.markdown("<h1 class='app-title'><i class='fa-solid fa-bolt' style='color:#f59e0b;'></i> MyFitness Pro</h1>", unsafe_allow_html=True)
    col1, col2, col3 = st.columns([0.1, 0.8, 0.1])
    with col2:
        with st.container(border=True):
            if st.session_state.auth_mode == "Login":
                st.markdown("### Login")
                le = st.text_input("Email").lower().strip()
                lp = st.text_input("Password", type="password")
                remember = st.checkbox("Remember Me") 
                
                if st.button("Login", type="primary", use_container_width=True):
                    if le in db["users"] and db["users"][le]["password"] == lp:
                        st.session_state.logged_in = True
                        st.session_state.current_user = le
                        if remember:
                            st.query_params["user"] = le 
                        st.rerun()
                    else: st.error("Wrong email or password.")
                if st.button("Create Account"): st.session_state.auth_mode = "Register"; st.rerun()
                
            elif st.session_state.auth_mode == "Register":
                st.markdown("### Register")
                re = st.text_input("Email").lower().strip()
                rp = st.text_input("Password", type="password")
                if st.button("Get Started", type="primary", use_container_width=True):
                    if re and len(rp) >= 4:
                        st.session_state.temp_reg = {"e": re, "p": rp}
                        st.session_state.auth_mode = "Verify"; st.rerun()
                    else: st.error("Enter valid email and password (min 4 chars)")
                if st.button("Back"): st.session_state.auth_mode = "Login"; st.rerun()
                
            elif st.session_state.auth_mode == "Verify":
                st.info("Code: 1234")
                vc = st.text_input("Enter 4-digit code")
                if st.button("Verify", type="primary", use_container_width=True):
                    if vc == "1234":
                        email = st.session_state.temp_reg["e"]
                        db["users"][email] = {"password": st.session_state.temp_reg["p"], "onboarding_done": False, "profile": {}, "daily_log": [], "exercise_log": [], "weight_log": [], "custom_foods": {}, "water_liters": 0.0}
                        sync_db()
                        st.session_state.logged_in = True
                        st.session_state.current_user = email
                        st.query_params["user"] = email 
                        st.rerun()

# ==========================================
# MAIN APP
# ==========================================
else:
    user_data = db["users"][st.session_state.current_user]
    
    if not user_data.get("onboarding_done", False):
        st.markdown("<h2 style='text-align: center;'>Welcome! Let's build your plan.</h2>", unsafe_allow_html=True)
        with st.container(border=True):
            col1, col2 = st.columns(2)
            gen = col1.selectbox("Gender", ["Male", "Female"])
            age = col2.number_input("Age", min_value=10, value=21)
            weight = col1.number_input("Weight (kg)", min_value=30.0, value=75.0)
            height = col2.number_input("Height (cm)", min_value=100.0, value=175.0)
            act = st.selectbox("Activity Level", ["Sedentary", "Lightly active", "Moderately active", "Very active", "Super active"])
            goal = st.selectbox("Your Goal", ["Weight Loss (Cut)", "Maintenance", "Lean Muscle Gain", "Bodybuilding (Bulk)"])
            if st.button("Calculate My Plan", type="primary", use_container_width=True):
                cals, prot, carb, fat, water = calculate_targets(gen, age, weight, height, act, goal)
                user_data.update({
                    "profile": {"gender": gen, "age": age, "height": height, "activity": act, "goal": goal, "targets": {"cals": cals, "prot": prot, "carb": carb, "fat": fat, "water": water}},
                    "weight_log": [{"Date": str(date.today()), "Weight": weight}],
                    "onboarding_done": True
                })
                sync_db(); st.rerun()

    else:
        profile = user_data["profile"]
        targets = profile["targets"]
        w_log = user_data.get("weight_log", [])
        
        try: current_weight = sorted(w_log, key=lambda x: x["Date"])[-1]["Weight"] if w_log else 75.0
        except: current_weight = 75.0
            
        recommended_water = calculate_targets(profile["gender"], profile["age"], current_weight, profile["height"], profile["activity"], profile["goal"])[4]

        with st.sidebar:
            st.markdown(f"👤 **{st.session_state.current_user}**")
            if st.button("Logout"): 
                st.session_state.logged_in = False
                st.query_params.clear()
                st.rerun()
            st.divider()
            
            st.markdown("### <i class='fa-solid fa-user-gear'></i> Edit Profile", unsafe_allow_html=True)
            new_gen = st.selectbox("Gender", ["Male", "Female"], index=["Male", "Female"].index(profile.get("gender", "Male")))
            new_age = st.number_input("Age", value=int(profile.get("age", 21)), min_value=10)
            new_height = st.number_input("Height (cm)", value=int(profile.get("height", 175)), min_value=100)
            new_act = st.selectbox("Activity", ["Sedentary", "Lightly active", "Moderately active", "Very active", "Super active"], index=["Sedentary", "Lightly active", "Moderately active", "Very active", "Super active"].index(profile["activity"]))
            new_goal = st.selectbox("Goal", ["Weight Loss (Cut)", "Maintenance", "Lean Muscle Gain", "Bodybuilding (Bulk)"], index=["Weight Loss (Cut)", "Maintenance", "Lean Muscle Gain", "Bodybuilding (Bulk)"].index(profile["goal"]))
            
            if st.button("Update Profile & Recalculate"):
                c, p, cb, f, w = calculate_targets(new_gen, new_age, current_weight, new_height, new_act, new_goal)
                user_data["profile"].update({"gender": new_gen, "age": new_age, "height": new_height, "activity": new_act, "goal": new_goal, "targets": {"cals": c, "prot": p, "carb": cb, "fat": f, "water": w}})
                sync_db(); st.success("Updated!"); st.rerun()
                
            st.divider()
            st.markdown("### <i class='fa-solid fa-sliders'></i> Manual Override", unsafe_allow_html=True)
            with st.expander("Edit Targets Manually"):
                t_cals = st.number_input("Calories", value=targets["cals"], step=50)
                t_prot = st.number_input("Protein (g)", value=targets["prot"], step=5)
                t_carb = st.number_input("Carbs (g)", value=targets["carb"], step=5)
                t_fat = st.number_input("Fat (g)", value=targets["fat"], step=5)
                if st.button("Save Manual Targets"):
                    user_data["profile"]["targets"].update({"cals": t_cals, "prot": t_prot, "carb": t_carb, "fat": t_fat}); sync_db(); st.rerun()

            st.divider()
            st.markdown("### <i class='fa-solid fa-glass-water' style='color:#38bdf8;'></i> Hydration", unsafe_allow_html=True)
            st.caption(f"Recommended: {recommended_water}L")
            user_water_goal = st.number_input("Personal Goal (L)", value=float(targets.get("water", recommended_water)), step=0.25)
            if user_water_goal != targets.get("water"): user_data["profile"]["targets"]["water"] = user_water_goal; sync_db()
            
            w_c1, w_c2, w_c3 = st.columns([1,1,1])
            if w_c1.button("-0.25L"): user_data["water_liters"] = max(0.0, user_data.get("water_liters", 0.0) - 0.25); sync_db()
            w_c2.markdown(f"<h4 style='text-align:center;'>{user_data.get('water_liters', 0.0):.2f}L</h4>", unsafe_allow_html=True)
            if w_c3.button("+0.25L"): user_data["water_liters"] = user_data.get("water_liters", 0.0) + 0.25; sync_db()
            st.progress(min(user_data.get("water_liters", 0.0) / user_water_goal, 1.0) if user_water_goal > 0 else 0)

        st.markdown("<h1 class='app-title'><i class='fa-solid fa-bolt' style='color:#f59e0b;'></i> MyFitness Pro</h1>", unsafe_allow_html=True)
        t_dash, t_add, t_ex, t_weight, t_custom = st.tabs(["Dashboard", "Add Food", "Workouts", "Weight", "Custom"])

        # DASHBOARD
        with t_dash:
            df_f = pd.DataFrame(user_data.get("daily_log", []))
            if df_f.empty: df_f = pd.DataFrame(columns=["Meal", "Food", "Grams", "Calories", "Protein", "Carbs", "Fat"])
            df_e = pd.DataFrame(user_data.get("exercise_log", []))
            if df_e.empty: df_e = pd.DataFrame(columns=["Exercise", "Burned"])

            t_food, t_burn = df_f['Calories'].sum(), df_e['Burned'].sum()
            rem_c = targets["cals"] - (t_food - t_burn)
            
            with st.container(border=True):
                st.markdown("### Calorie Balance")
                m1, m2, m3, m4 = st.columns(4)
                m1.metric("Goal", targets["cals"])
                m2.metric("Food", f"{t_food:.0f}")
                m3.metric("Burned", f"{t_burn:.0f}")
                m4.metric("Remaining", f"{rem_c:.0f}" if rem_c >= 0 else f"⚠️ Over {abs(rem_c):.0f}")
                st.progress(min(max(0, (t_food - t_burn) / targets["cals"]), 1.0) if targets["cals"] > 0 else 0)
            
            st.write("")
            col_ma, col_pi = st.columns([1.2, 1])
            with col_ma:
                for m, cur, goal, color in [("Protein", df_f['Protein'].sum(), targets["prot"], "#EF553B"), ("Carbs", df_f['Carbs'].sum(), targets["carb"], "#636EFA"), ("Fat", df_f['Fat'].sum(), targets["fat"], "#00CC96")]:
                    diff = goal - cur
                    status = f"{diff:.0f}g left" if diff >= 0 else f"⚠️ Over {abs(diff):.0f}g"
                    st.markdown(f"**{m}:** {cur:.0f}g / {goal}g | <span style='color:{color if diff >= 0 else '#dc2626'}; font-weight:bold;'>{status}</span>", unsafe_allow_html=True)
                    st.progress(min(cur / goal, 1.0) if goal > 0 else 0)
            with col_pi:
                fig = px.pie(pd.DataFrame({"M": ["P", "C", "F"], "G": [df_f['Protein'].sum(), df_f['Carbs'].sum(), df_f['Fat'].sum()]}), values='G', names='M', hole=0.5, color_discrete_sequence=['#EF553B', '#636EFA', '#00CC96'])
                fig.update_layout(height=180, showlegend=False, margin=dict(t=0, b=0, l=0, r=0))
                # --- FIXED: Added config to hide ModeBar in Pie Chart ---
                st.plotly_chart(fig, use_container_width=True, config={'displayModeBar': False})

            for meal in ["Breakfast", "Lunch", "Dinner", "Snacks"]:
                m_data = df_f[df_f["Meal"] == meal]
                with st.expander(f"{meal} | {m_data['Calories'].sum():.0f} kcal"):
                    if not m_data.empty:
                        edited = st.data_editor(m_data.drop(columns=["Meal"]), hide_index=True, use_container_width=True, key=f"d_{meal}")
                        if not edited.equals(m_data.drop(columns=["Meal"])):
                            edited["Meal"] = meal
                            user_data["daily_log"] = pd.concat([df_f[df_f["Meal"] != meal], edited]).to_dict('records')
                            sync_db(); st.rerun()

            if st.button("Reset Entire Day"): 
                user_data.update({"daily_log": [], "exercise_log": [], "water_liters": 0.0}); sync_db(); st.rerun()

        # ADD FOOD
        with t_add:
            meal = st.radio("Log to:", ["Breakfast", "Lunch", "Dinner", "Snacks"], horizontal=True)
            
            if st.button("📷 Open Camera Scanner" if not st.session_state.camera_active else "❌ Close Camera", type="secondary"):
                st.session_state.camera_active = not st.session_state.camera_active
                st.rerun()
            
            code = ""
            if st.session_state.camera_active:
                cam = st.camera_input("Point at barcode", label_visibility="collapsed")
                if cam:
                    dec = decode(Image.open(cam))
                    if not dec: dec = decode(ImageEnhance.Contrast(Image.open(cam).convert('L')).enhance(3.0))
                    if dec: 
                        code = dec[0].data.decode("utf-8")
                        st.success("Barcode Detected!")
                        st.session_state.camera_active = False 
                    else:
                        st.error("Barcode not read. Try moving closer.")

            query = st.text_input("🔍 Search Food:", value=code, placeholder="Type name or scan barcode")
            if query:
                en = translate_query(query)
                CDB = {**OFFLINE_DB, **user_data.get("custom_foods", {})}
                matches = [k for k in CDB.keys() if en in k or query.lower() in k]
                if matches:
                    sel = st.selectbox("Matches:", matches)
                    w = st.number_input("Grams eaten:", value=100.0)
                    if st.button("Add to Diary"):
                        d = CDB[sel]
                        user_data["daily_log"].append({"Meal": meal, "Food": sel.title(), "Grams": w, "Calories": round(d["cals"]*w/100,1), "Protein": round(d["prot"]*w/100,1), "Carbs": round(d["carb"]*w/100,1), "Fat": round(d["fat"]*w/100,1)})
                        sync_db(); st.rerun()
                else:
                    res = robust_global_search(en)
                    if res:
                        opt = {f"{p.get('product_name','U')} ({p.get('brands','N/A')})": p for p in res[:10]}
                        sel_g = st.selectbox("Global Search Results:", list(opt.keys()))
                        w = st.number_input("Grams eaten:", value=100.0)
                        if st.button("Add to Diary"):
                            n = opt[sel_g].get('nutriments', {})
                            user_data["daily_log"].append({
                                "Meal": meal, "Food": sel_g, "Grams": w,
                                "Calories": round((n.get("energy-kcal_100g",0)*w)/100, 1),
                                "Protein": round((n.get("proteins_100g",0)*w)/100, 1),
                                "Carbs": round((n.get("carbohydrates_100g",0)*w)/100, 1),
                                "Fat": round((n.get("fat_100g",0)*w)/100, 1)
                            })
                            sync_db(); st.rerun()

        # WORKOUTS
        with t_ex:
            sel_e = st.selectbox("Activity Type:", list(EXERCISE_METS.keys()))
            dur = st.number_input("Duration (min):", value=45)
            burn = int((EXERCISE_METS[sel_e] * 3.5 * current_weight) / 200 * dur)
            st.info(f"Approx Burned: **{burn} kcal** (Based on {current_weight}kg weight)")
            if st.button("Log Workout"):
                user_data["exercise_log"].append({"Exercise": sel_e, "Burned": burn}); sync_db(); st.rerun()
            if user_data["exercise_log"]: st.dataframe(pd.DataFrame(user_data["exercise_log"]), use_container_width=True, hide_index=True)

        # WEIGHT TRACKER
        with t_weight:
            with st.container(border=True):
                w_in = st.number_input("Enter Today's Weight (kg)", value=float(current_weight), step=0.1)
                if st.button("Log Weight", use_container_width=True):
                    ds = str(date.today())
                    user_data["weight_log"] = [e for e in user_data["weight_log"] if e["Date"] != ds]
                    user_data["weight_log"].append({"Date": ds, "Weight": w_in})
                    user_data["weight_log"] = sorted(user_data["weight_log"], key=lambda x: x["Date"])
                    sync_db(); st.rerun()
            
            if len(user_data["weight_log"]) > 0:
                df_w = pd.DataFrame(user_data["weight_log"])
                df_w['Date'] = pd.to_datetime(df_w['Date'])
                
                sd, sw, g = df_w['Date'].iloc[0], df_w['Weight'].iloc[0], profile.get("goal")
                dr = -0.07 if "Weight Loss" in g else (0.035 if "Muscle" in g else (0.07 if "Bodybuilding" in g else 0))
                df_w['Days'] = (df_w['Date'] - sd).dt.days
                df_w['Ideal'] = sw + (df_w['Days'] * dr)
                
                fig = go.Figure()
                fig.add_trace(go.Scatter(x=df_w['Date'], y=df_w['Weight'], mode='lines+markers', name='Actual', line=dict(color='#2e66ff', width=4)))
                fig.add_trace(go.Scatter(x=df_w['Date'], y=df_w['Ideal'], mode='lines', name='Target', line=dict(color='#00CC96', dash='dash')))
                fig.update_layout(height=350, margin=dict(l=10, r=10, t=10, b=10), hovermode="x unified", legend=dict(orientation="h", y=-0.2))
                st.plotly_chart(fig, use_container_width=True, config={'displayModeBar': False})
                
                st.markdown("#### Weight History (Read Only)")
                disp_df = df_w[['Date', 'Weight']].copy()
                disp_df['Date'] = disp_df['Date'].dt.strftime('%Y-%m-%d')
                st.dataframe(disp_df.sort_values(by='Date', ascending=False), use_container_width=True, hide_index=True)

        # CUSTOM FOODS
        with t_custom:
            cn = st.text_input("New Food Name:").lower()
            c1, c2, c3, c4 = st.columns(4)
            cc = c1.number_input("Cals:")
            cp = c2.number_input("Pro:")
            cch = c3.number_input("Carb:")
            cf = c4.number_input("Fat:")
            if st.button("Save to My Library"):
                if cn: 
                    if "custom_foods" not in user_data: user_data["custom_foods"] = {}
                    user_data["custom_foods"][cn] = {"cals":cc, "prot":cp, "carb":cch, "fat":cf}
                    sync_db(); st.success(f"Saved {cn}!")