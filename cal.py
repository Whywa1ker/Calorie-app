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
    return f'<a href="data:file/csv;base64,{b64}" download="{filename}" style="display:inline-block; padding:10px 20px; background-color:#1f2937; color:white; text-align:center; font-weight:600; text-decoration:none; border-radius:6px;"><i class="fa-solid fa-download"></i> Export Data</a>'

def calculate_targets(gender, age, weight, height, activity, goal):
    multipliers = {"Sedentary": 1.2, "Lightly active": 1.375, "Moderately active": 1.55, "Very active": 1.725, "Super active": 1.9}
    bmr = (10 * weight) + (6.25 * height) - (5 * age) + (5 if gender == "Male" else -161)
    tdee = bmr * multipliers[activity]
    
    if goal == "Weight Loss (Cut)": cals = int(tdee - 500); p_pct, c_pct, f_pct = 0.40, 0.35, 0.25
    elif goal == "Maintenance": cals = int(tdee); p_pct, c_pct, f_pct = 0.30, 0.40, 0.30
    elif goal == "Lean Muscle Gain": cals = int(tdee + 300); p_pct, c_pct, f_pct = 0.25, 0.50, 0.25
    else: cals = int(tdee + 500); p_pct, c_pct, f_pct = 0.30, 0.50, 0.20
        
    prot, carb, fat = int((cals*p_pct)/4), int((cals*c_pct)/4), int((cals*f_pct)/9)
    
    water_liters = (weight * 35) / 1000
    if age > 55: water_liters = (weight * 30) / 1000 
    if "active" in activity.lower() and "lightly" not in activity.lower():
        water_liters += 0.75
    water_liters = round(water_liters, 1)
    
    return cals, prot, carb, fat, water_liters

# --- 3. Session State Init ---
if 'logged_in' not in st.session_state: st.session_state.logged_in = False
if 'current_user' not in st.session_state: st.session_state.current_user = None
if 'auth_mode' not in st.session_state: st.session_state.auth_mode = "Login"
if 'verify_code_sent' not in st.session_state: st.session_state.verify_code_sent = False
if 'temp_reg_data' not in st.session_state: st.session_state.temp_reg_data = {}

# --- 4. UI Config & Base CSS (FontAwesome Injected) ---
st.set_page_config(page_title="MyFitness Pro", page_icon="💪", layout="centered")
st.markdown("""
<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
<style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;800&display=swap');
    html, body, [class*="css"] { font-family: 'Inter', sans-serif; }
    
    /* Clean up the tabs - remove emojis and make them look like a sleek iOS app */
    .stTabs [data-baseweb="tab-list"] { gap: 4px; border-bottom: 2px solid #e5e7eb; }
    .stTabs [data-baseweb="tab"] { border-radius: 8px 8px 0px 0px; padding: 12px 16px; color: #6b7280; font-weight: 500; }
    .stTabs [aria-selected="true"] { background-color: #f3f4f6; color: #111827 !important; border-bottom: 3px solid #2e66ff; }
    
    .metric-icon { font-size: 1.2rem; margin-right: 8px; }
    .app-title { text-align: center; color: #111827; font-weight: 800; font-size: 2.5rem; margin-bottom: 0px; }
    .app-subtitle { text-align: center; color: #6b7280; font-weight: 400; font-size: 1rem; margin-top: -10px; margin-bottom: 30px; }
</style>
""", unsafe_allow_html=True)

# ==========================================
# AUTHENTICATION ROUTING
# ==========================================
if not st.session_state.logged_in:
    st.markdown("<h1 class='app-title'><i class='fa-solid fa-bolt' style='color:#f59e0b;'></i> MyFitness Pro</h1>", unsafe_allow_html=True)
    st.markdown("<p class='app-subtitle'>Professional Nutrition & Fitness Tracking</p>", unsafe_allow_html=True)
    
    col1, col2, col3 = st.columns([1,2,1])
    with col2:
        with st.container(border=True):
            if st.session_state.auth_mode == "Login":
                st.markdown("### <i class='fa-solid fa-lock' style='color:#6b7280;'></i> Login", unsafe_allow_html=True)
                log_email = st.text_input("Email").lower().strip()
                log_pass = st.text_input("Password", type="password")
                
                if st.button("Login", type="primary", use_container_width=True):
                    if log_email in db["users"] and db["users"][log_email]["password"] == log_pass:
                        st.session_state.logged_in = True
                        st.session_state.current_user = log_email
                        st.rerun()
                    else: st.error("Invalid email or password.")
                
                st.write("")
                st.write("Don't have an account?")
                if st.button("Create an Account"):
                    st.session_state.auth_mode = "Register"
                    st.rerun()
                    
            elif st.session_state.auth_mode == "Register":
                st.markdown("### <i class='fa-solid fa-user-plus' style='color:#6b7280;'></i> Register", unsafe_allow_html=True)
                
                if not st.session_state.verify_code_sent:
                    reg_email = st.text_input("Email").lower().strip()
                    reg_pass = st.text_input("Password", type="password")
                    
                    if st.button("Send Verification Code", type="primary", use_container_width=True):
                        if reg_email in db["users"]: st.error("Account already exists!")
                        elif reg_email and len(reg_pass) >= 4:
                            st.session_state.temp_reg_data = {"email": reg_email, "pass": reg_pass}
                            st.session_state.verify_code_sent = True; st.rerun()
                        else: st.error("Please enter a valid email and a password (min 4 chars).")
                            
                    st.write("")
                    if st.button("Back to Login"): st.session_state.auth_mode = "Login"; st.rerun()
                else:
                    st.success(f"Code sent to {st.session_state.temp_reg_data['email']}!")
                    st.info("*(Mock Mode: Enter '1234' to verify)*")
                    v_code = st.text_input("Enter 4-digit code:")
                    
                    if st.button("Verify & Create Account", type="primary", use_container_width=True):
                        if v_code == "1234":
                            new_email = st.session_state.temp_reg_data["email"]
                            db["users"][new_email] = {
                                "password": st.session_state.temp_reg_data["pass"], "onboarding_done": False,
                                "profile": {}, "daily_log": [], "exercise_log": [], "weight_log": [], "custom_foods": {}, "water_liters": 0.0
                            }
                            sync_db()
                            st.session_state.logged_in = True; st.session_state.current_user = new_email; st.session_state.verify_code_sent = False; st.rerun()
                        else: st.error("Invalid code.")
                    if st.button("Cancel Registration"): st.session_state.verify_code_sent = False; st.session_state.auth_mode = "Login"; st.rerun()

# ==========================================
# APP ROUTING
# ==========================================
else:
    user_data = db["users"][st.session_state.current_user]
    if "water_liters" not in user_data: user_data["water_liters"] = 0.0
    
    # --- ONBOARDING FLOW ---
    if not user_data.get("onboarding_done", False):
        st.markdown("<h2 style='text-align: center;'><i class='fa-solid fa-hand-wave'></i> Welcome to MyFitness Pro!</h2>", unsafe_allow_html=True)
        st.markdown("<p style='text-align: center;'>Let's set up your personal profile.</p>", unsafe_allow_html=True)
        
        with st.container(border=True):
            st.markdown("#### <i class='fa-solid fa-id-card' style='color:#6b7280;'></i> Physical Details", unsafe_allow_html=True)
            col1, col2 = st.columns(2)
            gen = col1.selectbox("Gender", ["Male", "Female"])
            age = col2.number_input("Age", min_value=10, max_value=100, value=21)
            weight = col1.number_input("Current Weight (kg)", min_value=30.0, max_value=200.0, value=75.0, step=0.5)
            height = col2.number_input("Height (cm)", min_value=100.0, max_value=250.0, value=175.0, step=1.0)
            
            st.markdown("#### <i class='fa-solid fa-bullseye' style='color:#6b7280;'></i> Lifestyle & Goals", unsafe_allow_html=True)
            act = st.selectbox("Daily Activity Level", ["Sedentary", "Lightly active", "Moderately active", "Very active", "Super active"])
            goal = st.selectbox("Current Goal", ["Weight Loss (Cut)", "Maintenance", "Lean Muscle Gain", "Bodybuilding (Bulk)"])
            
            st.write("")
            if st.button("Calculate My Plan", type="primary", use_container_width=True):
                cals, prot, carb, fat, water = calculate_targets(gen, age, weight, height, act, goal)
                user_data["profile"] = {
                    "gender": gen, "age": age, "height": height, "activity": act, "goal": goal,
                    "targets": {"cals": cals, "prot": prot, "carb": carb, "fat": fat, "water": water}
                }
                user_data["weight_log"] = [{"Date": str(date.today()), "Weight": weight}]
                user_data["onboarding_done"] = True
                sync_db()
                st.success("Profile Setup Complete!")
                st.info("Privacy Notice: All data is local and private.")
                st.button("Enter Dashboard", on_click=lambda: st.rerun())

    # --- MAIN APP FLOW ---
    else:
        profile = user_data["profile"]
        targets = profile["targets"]
        COMBINED_DB = {**OFFLINE_DB, **user_data.get("custom_foods", {})}
        current_weight = sorted(user_data["weight_log"], key=lambda x: x["Date"])[-1]["Weight"] if user_data["weight_log"] else 75.0
        recommended_water = calculate_targets(profile["gender"], profile["age"], current_weight, profile["height"], profile["activity"], profile["goal"])[4]

        # --- SIDEBAR ---
        with st.sidebar:
            st.markdown(f"**<i class='fa-solid fa-user'></i> {st.session_state.current_user.split('@')[0]}**", unsafe_allow_html=True)
            if st.button("Logout"):
                st.session_state.logged_in = False; st.session_state.current_user = None; st.rerun()
                
            st.markdown("---")
            st.markdown("### <i class='fa-solid fa-sliders' style='color:#6b7280;'></i> Targets", unsafe_allow_html=True)
            t_cals = st.number_input("Calories", value=targets["cals"], step=50)
            t_prot = st.number_input("Protein (g)", value=targets["prot"], step=5)
            t_carb = st.number_input("Carbs (g)", value=targets["carb"], step=5)
            t_fat = st.number_input("Fat (g)", value=targets["fat"], step=5)
            
            if t_cals != targets["cals"] or t_prot != targets["prot"] or t_carb != targets["carb"] or t_fat != targets["fat"]:
                user_data["profile"]["targets"]["cals"] = t_cals
                user_data["profile"]["targets"]["prot"] = t_prot
                user_data["profile"]["targets"]["carb"] = t_carb
                user_data["profile"]["targets"]["fat"] = t_fat
                sync_db()

            st.markdown("---")
            st.markdown("### <i class='fa-solid fa-glass-water' style='color:#38bdf8;'></i> Hydration", unsafe_allow_html=True)
            st.caption(f"Recommended: {recommended_water} L")
            
            t_water = st.number_input("Goal (Liters):", value=float(targets.get("water", recommended_water)), step=0.25)
            if t_water != targets.get("water"):
                user_data["profile"]["targets"]["water"] = t_water; sync_db()

            w_col1, w_col2, w_col3 = st.columns([1,1,1])
            if w_col1.button("- 0.25L"): user_data["water_liters"] = max(0.0, user_data.get("water_liters", 0.0) - 0.25); sync_db()
            w_col2.markdown(f"<h3 style='text-align:center;'>{user_data.get('water_liters', 0.0):.2f}L</h3>", unsafe_allow_html=True)
            if w_col3.button("+ 0.25L"): user_data["water_liters"] = user_data.get("water_liters", 0.0) + 0.25; sync_db()
            st.progress(min(user_data.get("water_liters", 0.0) / t_water, 1.0) if t_water > 0 else 0)

        # --- MAIN DASHBOARD ---
        st.markdown("<h1 class='app-title'><i class='fa-solid fa-bolt' style='color:#f59e0b;'></i> MyFitness Pro</h1>", unsafe_allow_html=True)
        st.write("")

        # Clean Tabs without Emojis
        tab_dash, tab_add_food, tab_exercise, tab_weight, tab_custom = st.tabs(["Dashboard", "Add Food", "Exercise", "Weight", "Custom"])

        # TAB 1: DIARY
        with tab_dash:
            df_food = pd.DataFrame(user_data["daily_log"])
            df_ex = pd.DataFrame(user_data["exercise_log"])
            
            tot_food_cals = df_food['Calories'].sum() if not df_food.empty else 0
            tot_prot, tot_carb, tot_fat = (df_food[m].sum() if not df_food.empty else 0 for m in ['Protein', 'Carbs', 'Fat'])
            tot_burned = df_ex['Burned'].sum() if not df_ex.empty else 0
            net_cals = tot_food_cals - tot_burned
            cals_remaining = t_cals - net_cals

            with st.container(border=True):
                st.markdown("### <i class='fa-solid fa-scale-balanced' style='color:#8b5cf6;'></i> Energy Balance", unsafe_allow_html=True)
                eq1, eq2, eq3, eq4, eq5, eq6, eq7 = st.columns([2,1,2,1,2,1,2])
                eq1.metric("Goal", f"{t_cals}")
                eq2.markdown("<h2 style='text-align:center; color:#9ca3af;'>-</h2>", unsafe_allow_html=True)
                eq3.metric("Food", f"{tot_food_cals:.0f}")
                eq4.markdown("<h2 style='text-align:center; color:#9ca3af;'>+</h2>", unsafe_allow_html=True)
                eq5.metric("Burned", f"{tot_burned:.0f}")
                eq6.markdown("<h2 style='text-align:center; color:#9ca3af;'>=</h2>", unsafe_allow_html=True)
                
                if cals_remaining >= 0: eq7.metric("Remaining", f"{cals_remaining:.0f}")
                else: eq7.metric("Remaining", f"Over {abs(cals_remaining):.0f}")
                    
                st.progress(min(net_cals / t_cals, 1.0) if t_cals > 0 else 0)
            
            if not df_food.empty:
                st.write("")
                col_m, col_p = st.columns([1.2, 1])
                with col_m:
                    st.markdown("### <i class='fa-solid fa-chart-pie' style='color:#ec4899;'></i> Macros Status", unsafe_allow_html=True)
                    
                    diff_prot = t_prot - tot_prot
                    if diff_prot >= 0: prot_str = f"<span style='color:#EF553B;'>**{diff_prot:.0f}g left**</span>"
                    else: prot_str = f"<span style='color:#dc2626; font-weight:bold;'><i class='fa-solid fa-circle-exclamation'></i> Over by {abs(diff_prot):.0f}g</span>"
                    st.markdown(f"**Protein:** {tot_prot:.0f}g / {t_prot}g | {prot_str}", unsafe_allow_html=True)
                    st.progress(min(tot_prot / t_prot, 1.0) if t_prot > 0 else 0)
                    
                    diff_carb = t_carb - tot_carb
                    if diff_carb >= 0: carb_str = f"<span style='color:#636EFA;'>**{diff_carb:.0f}g left**</span>"
                    else: carb_str = f"<span style='color:#dc2626; font-weight:bold;'><i class='fa-solid fa-circle-exclamation'></i> Over by {abs(diff_carb):.0f}g</span>"
                    st.markdown(f"**Carbs:** {tot_carb:.0f}g / {t_carb}g | {carb_str}", unsafe_allow_html=True)
                    st.progress(min(tot_carb / t_carb, 1.0) if t_carb > 0 else 0)
                    
                    diff_fat = t_fat - tot_fat
                    if diff_fat >= 0: fat_str = f"<span style='color:#00CC96;'>**{diff_fat:.0f}g left**</span>"
                    else: fat_str = f"<span style='color:#dc2626; font-weight:bold;'><i class='fa-solid fa-circle-exclamation'></i> Over by {abs(diff_fat):.0f}g</span>"
                    st.markdown(f"**Fat:** {tot_fat:.0f}g / {t_fat}g | {fat_str}", unsafe_allow_html=True)
                    st.progress(min(tot_fat / t_fat, 1.0) if t_fat > 0 else 0)
                    
                with col_p:
                    fig = px.pie(pd.DataFrame({"M": ["Pro", "Carb", "Fat"], "G": [tot_prot, tot_carb, tot_fat]}), values='G', names='M', hole=0.5, color='M', color_discrete_map={'Pro':'#EF553B', 'Carb':'#636EFA', 'Fat':'#00CC96'})
                    fig.update_layout(margin=dict(t=20, b=0, l=0, r=0), height=200, showlegend=False)
                    st.plotly_chart(fig, use_container_width=True)

                st.markdown("---")
                st.markdown("### <i class='fa-solid fa-book-open' style='color:#14b8a6;'></i> Meals Diary", unsafe_allow_html=True)
                for meal in ["Breakfast", "Lunch", "Dinner", "Snacks"]:
                    meal_data = df_food[df_food["Meal"] == meal] if not df_food.empty else pd.DataFrame()
                    meal_cals = meal_data["Calories"].sum() if not meal_data.empty else 0
                    with st.expander(f"{meal} | {meal_cals:.0f} kcal"):
                        if not meal_data.empty:
                            edited_df = st.data_editor(meal_data.drop(columns=["Meal"]), hide_index=True, use_container_width=True, key=f"edit_{meal}")
                            if not edited_df.equals(meal_data.drop(columns=["Meal"])):
                                edited_df["Meal"] = meal
                                user_data["daily_log"] = pd.concat([df_food[df_food["Meal"] != meal], edited_df]).to_dict('records')
                                sync_db(); st.rerun()
                        else: st.caption("Empty.")

                st.write("")
                st.markdown(get_csv_download_link(df_food, "diary.csv"), unsafe_allow_html=True)
                if st.button("Reset Entire Day", use_container_width=True):
                    user_data["daily_log"] = []; user_data["exercise_log"] = []; user_data["water_liters"] = 0.0
                    sync_db(); st.rerun()

        # TAB 2: ADD FOOD
        with tab_add_food:
            st.markdown("### <i class='fa-solid fa-magnifying-glass' style='color:#636EFA;'></i> Find & Log Food", unsafe_allow_html=True)
            selected_meal = st.radio("Select Meal:", ["Breakfast", "Lunch", "Dinner", "Snacks"], horizontal=True)
            
            with st.expander("Open Camera Scanner", expanded=False):
                camera_photo = st.camera_input("Barcode Scanner", label_visibility="collapsed")
            
            scanned_barcode = ""
            if camera_photo:
                image = Image.open(camera_photo)
                decoded = decode(image)
                if not decoded: decoded = decode(ImageEnhance.Contrast(image.convert('L')).enhance(3.0))
                if decoded:
                    scanned_barcode = decoded[0].data.decode("utf-8")
                    st.success(f"Barcode Detected: {scanned_barcode}")
                else: st.error("Barcode not read.")

            search_input = st.text_input("Search or Scan Barcode:", value=scanned_barcode, placeholder="Type anything...")
            
            if search_input:
                p_name, c_100, p_100, ch_100, f_100, found = "", 0, 0, 0, 0, False
                with st.spinner("Searching..."):
                    if search_input.isdigit():
                        product = get_food_by_barcode(search_input)
                        if product:
                            p_name = f"{product.get('product_name', 'Unknown')}"
                            n = product.get('nutriments', {})
                            c_100, p_100, ch_100, f_100 = n.get("energy-kcal_100g",0), n.get("proteins_100g",0), n.get("carbohydrates_100g",0), n.get("fat_100g",0)
                            found = True
                    else:
                        en_search = translate_query(search_input)
                        local_matches = [name for name in COMBINED_DB.keys() if en_search in name.lower() or search_input.lower() in name.lower()]
                        if local_matches:
                            sel_local = st.selectbox("Quick Matches:", local_matches)
                            if sel_local:
                                p_name = sel_local.title()
                                db_item = COMBINED_DB[sel_local]
                                c_100, p_100, ch_100, f_100 = db_item["cals"], db_item["prot"], db_item["carb"], db_item["fat"]
                                found = True
                        if not found:
                            results = robust_global_search(en_search)
                            if results:
                                options = {f"{p.get('product_name','Unknown')} ({p.get('brands','N/A')})": p for p in results[:10]}
                                sel_global = st.selectbox("Global Matches:", list(options.keys()))
                                if sel_global:
                                    p_name = sel_global
                                    n = options[sel_global].get('nutriments', {})
                                    c_100, p_100, ch_100, f_100 = n.get("energy-kcal_100g",0), n.get("proteins_100g",0), n.get("carbohydrates_100g",0), n.get("fat_100g",0)
                                    found = True

                if found:
                    with st.container(border=True):
                        st.markdown(f"#### {p_name}")
                        st.caption(f"100g ➔ {c_100} kcal | {p_100}g P")
                        f_weight = st.number_input("Amount (g):", min_value=1.0, value=100.0, step=10.0)
                        cur_c, cur_p, cur_ch, cur_f = (c_100*f_weight)/100, (p_100*f_weight)/100, (ch_100*f_weight)/100, (f_100*f_weight)/100
                        st.success(f"**Total: {cur_c:.0f} kcal**")
                        
                        if st.button(f"Add to {selected_meal}", type="primary", use_container_width=True):
                            user_data["daily_log"].append({
                                "Meal": selected_meal, "Food": p_name, "Grams": f_weight, 
                                "Calories": round(cur_c, 1), "Protein": round(cur_p, 1), "Carbs": round(cur_ch, 1), "Fat": round(cur_f, 1)
                            })
                            sync_db(); st.rerun()

        # TAB 3: EXERCISE
        with tab_exercise:
            st.markdown("### <i class='fa-solid fa-person-running' style='color:#f97316;'></i> Scientific Calorie Burner", unsafe_allow_html=True)
            sel_ex = st.selectbox("Select Activity:", list(EXERCISE_METS.keys()))
            if sel_ex == "Custom (Manual Input)":
                ex_name = st.text_input("Custom Exercise Name:")
                f_cals_burned = st.number_input("Calories Burned", min_value=0, step=50)
            else:
                ex_name = sel_ex
                dur_min = st.number_input("Duration (min):", min_value=1, value=45, step=5)
                f_cals_burned = int((EXERCISE_METS[sel_ex] * 3.5 * current_weight) / 200 * dur_min)
                st.info(f"💡 Approx. burned: **{f_cals_burned} kcal**.")

            if st.button("Log Workout", type="primary", use_container_width=True):
                if ex_name and f_cals_burned > 0:
                    user_data["exercise_log"].append({"Exercise": ex_name, "Burned": f_cals_burned})
                    sync_db(); st.success("Logged!"); st.rerun()
            if user_data["exercise_log"]: st.dataframe(pd.DataFrame(user_data["exercise_log"]), use_container_width=True, hide_index=True)

        # TAB 4: WEIGHT TRACKER
        with tab_weight:
            st.markdown("### <i class='fa-solid fa-chart-line' style='color:#2e66ff;'></i> Body Weight Progress", unsafe_allow_html=True)
            with st.container(border=True):
                w_col1, w_col2 = st.columns(2)
                log_date = w_col1.date_input("Date", value=date.today())
                log_weight = w_col2.number_input("Weight (kg)", min_value=30.0, max_value=250.0, value=float(current_weight), step=0.1)
                if st.button("Save Weight", type="primary", use_container_width=True):
                    date_str = str(log_date)
                    user_data["weight_log"] = [e for e in user_data["weight_log"] if e["Date"] != date_str]
                    user_data["weight_log"].append({"Date": date_str, "Weight": log_weight})
                    user_data["weight_log"] = sorted(user_data["weight_log"], key=lambda x: x["Date"])
                    sync_db(); st.success("Saved!"); st.rerun()

            if len(user_data["weight_log"]) > 0:
                df_w = pd.DataFrame(user_data["weight_log"])
                df_w['Date'] = pd.to_datetime(df_w['Date'])
                
                start_date = df_w['Date'].iloc[0]
                start_weight = df_w['Weight'].iloc[0]
                goal = profile.get("goal", "Maintenance")
                
                if goal == "Weight Loss (Cut)": daily_rate = -0.5 / 7
                elif goal == "Lean Muscle Gain": daily_rate = 0.25 / 7
                elif goal == "Bodybuilding (Bulk)": daily_rate = 0.5 / 7
                else: daily_rate = 0.0
                
                df_w['Days Passed'] = (df_w['Date'] - start_date).dt.days
                df_w['Ideal Goal'] = start_weight + (df_w['Days Passed'] * daily_rate)
                
                fig_w = go.Figure()
                fig_w.add_trace(go.Scatter(x=df_w['Date'], y=df_w['Weight'], mode='lines+markers+text', name='Actual Weight', text=df_w['Weight'], textposition="top center", line=dict(color='#2e66ff', width=3), marker=dict(size=8)))
                fig_w.add_trace(go.Scatter(x=df_w['Date'], y=df_w['Ideal Goal'], mode='lines', name='Ideal Target', line=dict(color='#00CC96', width=2, dash='dash')))
                
                fig_w.update_layout(margin=dict(t=30, b=0, l=0, r=0), yaxis_title="Kg", xaxis_title="", legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1))
                st.plotly_chart(fig_w, use_container_width=True)
                
                df_w['Date'] = df_w['Date'].dt.strftime('%Y-%m-%d')
                df_w_display = df_w[['Date', 'Weight']] 
                
                edited_w = st.data_editor(df_w_display, num_rows="dynamic", use_container_width=True, hide_index=True)
                if not edited_w.equals(df_w_display):
                    user_data["weight_log"] = edited_w.to_dict('records')
                    sync_db(); st.rerun()

        # TAB 5: CUSTOM RECIPES
        with tab_custom:
            st.markdown("### <i class='fa-solid fa-utensils' style='color:#ef4444;'></i> Recipe Builder", unsafe_allow_html=True)
            c_name = st.text_input("Food Name").lower()
            c_cals = st.number_input("Cals / 100g", min_value=0.0)
            c_prot = st.number_input("Protein / 100g", min_value=0.0)
            c_carb = st.number_input("Carbs / 100g", min_value=0.0)
            c_fat = st.number_input("Fat / 100g", min_value=0.0)
            if st.button("Save Database", type="primary"):
                if c_name:
                    if "custom_foods" not in user_data: user_data["custom_foods"] = {}
                    user_data["custom_foods"][c_name] = {"cals": c_cals, "prot": c_prot, "carb": c_carb, "fat": c_fat}
                    sync_db(); st.success("Saved!")