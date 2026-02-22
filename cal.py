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
    water_liters = round((weight * 35) / 1000 + (0.75 if "active" in activity.lower() else 0), 1)
    return cals, prot, carb, fat, water_liters

# --- 3. Session State Init ---
if 'logged_in' not in st.session_state: st.session_state.logged_in = False
if 'current_user' not in st.session_state: st.session_state.current_user = None
if 'auth_mode' not in st.session_state: st.session_state.auth_mode = "Login"
if 'verify_code_sent' not in st.session_state: st.session_state.verify_code_sent = False
if 'temp_reg_data' not in st.session_state: st.session_state.temp_reg_data = {}

# --- 4. UI Config ---
st.set_page_config(page_title="MyFitness Pro", page_icon="💪", layout="centered")
st.markdown("""
<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
<style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;800&display=swap');
    html, body, [class*="css"] { font-family: 'Inter', sans-serif; }
    .stTabs [data-baseweb="tab-list"] { gap: 4px; border-bottom: 2px solid #e5e7eb; }
    .stTabs [data-baseweb="tab"] { border-radius: 8px 8px 0px 0px; padding: 12px 16px; color: #6b7280; font-weight: 500; }
    .stTabs [aria-selected="true"] { background-color: #f3f4f6; color: #111827 !important; border-bottom: 3px solid #2e66ff; }
    .app-title { text-align: center; color: #111827; font-weight: 800; font-size: 2.5rem; margin-bottom: 0px; }
    .app-subtitle { text-align: center; color: #6b7280; font-weight: 400; font-size: 1rem; margin-top: -10px; margin-bottom: 30px; }
</style>
""", unsafe_allow_html=True)

# ==========================================
# AUTHENTICATION
# ==========================================
if not st.session_state.logged_in:
    st.markdown("<h1 class='app-title'><i class='fa-solid fa-bolt' style='color:#f59e0b;'></i> MyFitness Pro</h1>", unsafe_allow_html=True)
    st.markdown("<p class='app-subtitle'>Professional Nutrition & Fitness Tracking</p>", unsafe_allow_html=True)
    col1, col2, col3 = st.columns([1,2,1])
    with col2:
        with st.container(border=True):
            if st.session_state.auth_mode == "Login":
                st.markdown("### <i class='fa-solid fa-lock'></i> Login", unsafe_allow_html=True)
                log_email = st.text_input("Email").lower().strip()
                log_pass = st.text_input("Password", type="password")
                if st.button("Login", type="primary", use_container_width=True):
                    if log_email in db["users"] and db["users"][log_email]["password"] == log_pass:
                        st.session_state.logged_in, st.session_state.current_user = True, log_email
                        st.rerun()
                    else: st.error("Invalid email or password.")
                if st.button("Create an Account"): st.session_state.auth_mode = "Register"; st.rerun()
            elif st.session_state.auth_mode == "Register":
                st.markdown("### <i class='fa-solid fa-user-plus'></i> Register", unsafe_allow_html=True)
                if not st.session_state.verify_code_sent:
                    reg_email = st.text_input("Email").lower().strip()
                    reg_pass = st.text_input("Password", type="password")
                    if st.button("Send Verification Code", type="primary", use_container_width=True):
                        if reg_email in db["users"]: st.error("Account exists!")
                        elif reg_email and len(reg_pass) >= 4:
                            st.session_state.temp_reg_data = {"email": reg_email, "pass": reg_pass}
                            st.session_state.verify_code_sent = True; st.rerun()
                    if st.button("Back to Login"): st.session_state.auth_mode = "Login"; st.rerun()
                else:
                    st.info("Mock Mode: Enter '1234'")
                    v_code = st.text_input("Enter 4-digit code:")
                    if st.button("Verify", type="primary", use_container_width=True):
                        if v_code == "1234":
                            email = st.session_state.temp_reg_data["email"]
                            db["users"][email] = {"password": st.session_state.temp_reg_data["pass"], "onboarding_done": False, "profile": {}, "daily_log": [], "exercise_log": [], "weight_log": [], "custom_foods": {}, "water_liters": 0.0}
                            sync_db(); st.session_state.logged_in, st.session_state.current_user = True, email; st.rerun()
                        else: st.error("Invalid code.")

# ==========================================
# MAIN APP
# ==========================================
else:
    user_data = db["users"][st.session_state.current_user]
    
    if not user_data.get("onboarding_done", False):
        st.markdown("<h2 style='text-align: center;'>Welcome! Let's set up.</h2>", unsafe_allow_html=True)
        with st.container(border=True):
            gen = st.selectbox("Gender", ["Male", "Female"])
            age = st.number_input("Age", min_value=10, value=21)
            weight = st.number_input("Current Weight (kg)", min_value=30.0, value=75.0)
            height = st.number_input("Height (cm)", min_value=100.0, value=175.0)
            act = st.selectbox("Activity Level", ["Sedentary", "Lightly active", "Moderately active", "Very active", "Super active"])
            goal = st.selectbox("Goal", ["Weight Loss (Cut)", "Maintenance", "Lean Muscle Gain", "Bodybuilding (Bulk)"])
            if st.button("Generate Plan", type="primary", use_container_width=True):
                cals, prot, carb, fat, water = calculate_targets(gen, age, weight, height, act, goal)
                user_data.update({"profile": {"gender": gen, "age": age, "height": height, "activity": act, "goal": goal, "targets": {"cals": cals, "prot": prot, "carb": carb, "fat": fat, "water": water}}, "weight_log": [{"Date": str(date.today()), "Weight": weight}], "onboarding_done": True})
                sync_db(); st.rerun()
    else:
        profile = user_data["profile"]
        targets = profile["targets"]
        
        # Safeguard: if weight_log is empty, fallback to 75.0
        if user_data.get("weight_log"):
            try:
                log_sorted = sorted(user_data["weight_log"], key=lambda x: x["Date"])
                current_weight = log_sorted[-1]["Weight"]
            except (KeyError, IndexError):
                current_weight = 75.0
        else:
            current_weight = 75.0
            
        recommended_water = calculate_targets(profile["gender"], profile["age"], current_weight, profile["height"], profile["activity"], profile["goal"])[4]

        with st.sidebar:
            st.markdown(f"**<i class='fa-solid fa-user'></i> {st.session_state.current_user.split('@')[0]}**", unsafe_allow_html=True)
            if st.button("Logout"):
                st.session_state.logged_in = False; st.rerun()
            st.markdown("---")
            t_cals = st.number_input("Calories", value=targets["cals"], step=50)
            t_prot = st.number_input("Protein", value=targets["prot"], step=5)
            t_carb = st.number_input("Carbs", value=targets["carb"], step=5)
            t_fat = st.number_input("Fat", value=targets["fat"], step=5)
            if t_cals != targets["cals"] or t_prot != targets["prot"] or t_carb != targets["carb"] or t_fat != targets["fat"]:
                user_data["profile"]["targets"].update({"cals": t_cals, "prot": t_prot, "carb": t_carb, "fat": t_fat}); sync_db()
            
            st.markdown("---")
            st.markdown("### <i class='fa-solid fa-glass-water' style='color:#38bdf8;'></i> Hydration", unsafe_allow_html=True)
            st.caption(f"Recommended: {recommended_water} L")
            t_water = st.number_input("Goal (L)", value=float(targets.get("water", recommended_water)), step=0.25)
            if t_water != targets.get("water"): user_data["profile"]["targets"]["water"] = t_water; sync_db()
            w_c1, w_c2, w_c3 = st.columns([1,1,1])
            if w_c1.button("-0.25"): user_data["water_liters"] = max(0.0, user_data.get("water_liters", 0.0) - 0.25); sync_db()
            w_c2.markdown(f"<h3 style='text-align:center;'>{user_data.get('water_liters', 0.0):.2f}L</h3>", unsafe_allow_html=True)
            if w_c3.button("+0.25"): user_data["water_liters"] = user_data.get("water_liters", 0.0) + 0.25; sync_db()
            st.progress(min(user_data.get("water_liters", 0.0) / t_water, 1.0) if t_water > 0 else 0)

        st.markdown("<h1 class='app-title'><i class='fa-solid fa-bolt' style='color:#f59e0b;'></i> MyFitness Pro</h1>", unsafe_allow_html=True)
        t_dash, t_add, t_ex, t_weight, t_custom = st.tabs(["Dashboard", "Add Food", "Exercise", "Weight", "Custom"])

        with t_dash:
            df_f = pd.DataFrame(user_data["daily_log"])
            df_e = pd.DataFrame(user_data["exercise_log"])
            t_food = df_f['Calories'].sum() if not df_f.empty else 0
            t_p, t_c, t_f = (df_f[m].sum() if not df_f.empty else 0 for m in ['Protein', 'Carbs', 'Fat'])
            t_burn = df_e['Burned'].sum() if not df_e.empty else 0
            rem_c = t_cals - (t_food - t_burn)
            with st.container(border=True):
                st.markdown("### <i class='fa-solid fa-scale-balanced'></i> Energy Balance", unsafe_allow_html=True)
                m1, m2, m3, m4 = st.columns(4)
                m1.metric("Goal", t_cals)
                m2.metric("Food", f"{t_food:.0f}")
                m3.metric("Burned", f"{t_burn:.0f}")
                m4.metric("Remaining", f"{rem_c:.0f}" if rem_c >= 0 else f"⚠️ Over {abs(rem_c):.0f}")
                st.progress(min(max(0, (t_food - t_burn) / t_cals), 1.0) if t_cals > 0 else 0)
            if not df_f.empty:
                st.write("")
                col_ma, col_pi = st.columns([1.2, 1])
                with col_ma:
                    for m, cur, goal, color in [("Protein", t_p, t_prot, "#EF553B"), ("Carbs", t_c, t_carb, "#636EFA"), ("Fat", t_f, t_fat, "#00CC96")]:
                        diff = goal - cur
                        status = f"{diff:.0f}g left" if diff >= 0 else f"⚠️ Over {abs(diff):.0f}g"
                        st.markdown(f"**{m}:** {cur:.0f}g / {goal}g | <span style='color:{color if diff >= 0 else '#dc2626'}; font-weight:bold;'>{status}</span>", unsafe_allow_html=True)
                        st.progress(min(cur / goal, 1.0) if goal > 0 else 0)
                with col_pi:
                    fig = px.pie(pd.DataFrame({"M": ["P", "C", "F"], "G": [t_p, t_c, t_f]}), values='G', names='M', hole=0.5, color_discrete_sequence=['#EF553B', '#636EFA', '#00CC96'])
                    fig.update_layout(height=180, showlegend=False, margin=dict(t=0, b=0, l=0, r=0)); st.plotly_chart(fig, use_container_width=True)
                for meal in ["Breakfast", "Lunch", "Dinner", "Snacks"]:
                    m_data = df_f[df_f["Meal"] == meal]
                    with st.expander(f"{meal} | {m_data['Calories'].sum() if not m_data.empty else 0:.0f} kcal"):
                        if not m_data.empty:
                            edited = st.data_editor(m_data.drop(columns=["Meal"]), hide_index=True, use_container_width=True, key=f"d_{meal}")
                            if not edited.equals(m_data.drop(columns=["Meal"])):
                                edited["Meal"] = meal
                                user_data["daily_log"] = pd.concat([df_f[df_f["Meal"] != meal], edited]).to_dict('records')
                                sync_db(); st.rerun()
                st.write(""); st.markdown(get_csv_download_link(df_f), unsafe_allow_html=True)
                if st.button("Reset Day"): user_data.update({"daily_log": [], "exercise_log": [], "water_liters": 0.0}); sync_db(); st.rerun()

        with t_add:
            meal = st.radio("Log to:", ["Breakfast", "Lunch", "Dinner", "Snacks"], horizontal=True)
            with st.expander("📷 Scan Barcode"):
                cam = st.camera_input("Scanner", label_visibility="collapsed")
            code = ""
            if cam:
                dec = decode(Image.open(cam))
                if not dec: dec = decode(ImageEnhance.Contrast(Image.open(cam).convert('L')).enhance(3.0))
                if dec: code = dec[0].data.decode("utf-8"); st.success(f"Barcode: {code}")
            query = st.text_input("Search:", value=code, placeholder="Name or Barcode")
            if query:
                name, c100, p100, ch100, f100, found = "", 0, 0, 0, 0, False
                with st.spinner("Searching..."):
                    if query.isdigit():
                        prod = get_food_by_barcode(query)
                        if prod: name, n = prod.get('product_name', 'Unknown'), prod.get('nutriments', {}); c100, p100, ch100, f100, found = n.get("energy-kcal_100g",0), n.get("proteins_100g",0), n.get("carbohydrates_100g",0), n.get("fat_100g",0), True
                    else:
                        en = translate_query(query)
                        CDB = {**OFFLINE_DB, **user_data.get("custom_foods", {})}
                        matches = [k for k in CDB.keys() if en in k or query.lower() in k]
                        if matches:
                            sel = st.selectbox("Matches:", matches)
                            if sel: name, d = sel.title(), CDB[sel]; c100, p100, ch100, f100, found = d["cals"], d["prot"], d["carb"], d["fat"], True
                        if not found:
                            res = robust_global_search(en)
                            if res:
                                opt = {f"{p.get('product_name','U')} ({p.get('brands','N/A')})": p for p in res[:10]}
                                sel_g = st.selectbox("Global Results:", list(opt.keys()))
                                if sel_g: name, n = sel_g, opt[sel_g].get('nutriments', {}); c100, p100, ch100, f100, found = n.get("energy-kcal_100g",0), n.get("proteins_100g",0), n.get("carbohydrates_100g",0), n.get("fat_100g",0), True
                if found:
                    with st.container(border=True):
                        st.markdown(f"#### {name}")
                        w = st.number_input("Grams:", min_value=1.0, value=100.0, step=10.0)
                        cv, pv, chv, fv = (c100*w)/100, (p100*w)/100, (ch100*w)/100, (f_100*w)/100
                        st.success(f"Total: {cv:.0f} kcal")
                        if st.button(f"Add to {meal}", type="primary", use_container_width=True):
                            user_data["daily_log"].append({"Meal": meal, "Food": name, "Grams": w, "Calories": round(cv, 1), "Protein": round(pv, 1), "Carbs": round(chv, 1), "Fat": round(fv, 1)})
                            sync_db(); st.rerun()

        with t_ex:
            st.markdown("### <i class='fa-solid fa-person-running'></i> Burn Calories", unsafe_allow_html=True)
            sel_e = st.selectbox("Activity:", list(EXERCISE_METS.keys()))
            if sel_e == "Custom (Manual Input)":
                en, burn = st.text_input("Name:"), st.number_input("Burned:", min_value=0)
            else:
                en, dur = sel_e, st.number_input("Duration (min):", min_value=1, value=45)
                burn = int((EXERCISE_METS[sel_e] * 3.5 * current_weight) / 200 * dur)
                st.info(f"💡 Burned: ~**{burn} kcal**.")
            if st.button("Log Workout", type="primary", use_container_width=True):
                if en and burn > 0: user_data["exercise_log"].append({"Exercise": en, "Burned": burn}); sync_db(); st.rerun()
            if user_data["exercise_log"]: st.dataframe(pd.DataFrame(user_data["exercise_log"]), use_container_width=True, hide_index=True)

        with t_weight:
            st.markdown("### <i class='fa-solid fa-chart-line'></i> Weight Tracker", unsafe_allow_html=True)
            
            # --- Input Area ---
            with st.container(border=True):
                wc1, wc2 = st.columns(2)
                ld, lw = wc1.date_input("Entry Date", value=date.today()), wc2.number_input("Weight (Kg)", min_value=30.0, value=float(current_weight))
                if st.button("Save Entry", type="primary", use_container_width=True):
                    ds = str(ld)
                    # Filter out existing date to allow override
                    user_data["weight_log"] = [e for e in user_data["weight_log"] if e["Date"] != ds]
                    user_data["weight_log"].append({"Date": ds, "Weight": lw})
                    user_data["weight_log"] = sorted(user_data["weight_log"], key=lambda x: x["Date"])
                    sync_db(); st.rerun()

            if user_data["weight_log"]:
                df_w = pd.DataFrame(user_data["weight_log"])
                df_w['Date'] = pd.to_datetime(df_w['Date'])
                
                # --- Trend Calculations ---
                sd, sw, g = df_w['Date'].iloc[0], df_w['Weight'].iloc[0], profile.get("goal")
                dr = -0.07 if "Weight Loss" in g else (0.035 if "Muscle" in g else (0.07 if "Bodybuilding" in g else 0))
                df_w['Days'] = (df_w['Date'] - sd).dt.days
                df_w['Ideal'] = sw + (df_w['Days'] * dr)
                
                # --- Visual Chart (View Only) ---
                fig_w = go.Figure()
                fig_w.add_trace(go.Scatter(x=df_w['Date'], y=df_w['Weight'], mode='lines+markers', name='Actual', line=dict(color='#2e66ff', width=3)))
                fig_w.add_trace(go.Scatter(x=df_w['Date'], y=df_w['Ideal'], mode='lines', name='Trend', line=dict(color='#00CC96', dash='dash')))
                fig_w.update_layout(height=300, margin=dict(t=10, b=0, l=0, r=0), legend=dict(orientation="h", y=1.1))
                st.plotly_chart(fig_w, use_container_width=True)

                # --- READ ONLY TABLE (Safety Lock) ---
                st.markdown("#### 📋 History (Read Only)")
                # Formatting date to be clean string without time
                display_df = df_w[['Date', 'Weight']].copy()
                display_df['Date'] = display_df['Date'].dt.strftime('%Y-%m-%d')
                st.dataframe(display_df.sort_values(by='Date', ascending=False), use_container_width=True, hide_index=True)
                
                if st.button("🗑️ Reset Weight Log (Careful!)"):
                    user_data["weight_log"] = [{"Date": str(date.today()), "Weight": current_weight}]
                    sync_db(); st.rerun()

        with t_custom:
            st.markdown("### <i class='fa-solid fa-utensils'></i> My Foods", unsafe_allow_html=True)
            cn = st.text_input("Food Name:").lower()
            cc, cp, cch, cf = st.number_input("Calories:"), st.number_input("Protein:"), st.number_input("Carbs:"), st.number_input("Fat:")
            if st.button("Save to My Library"):
                if cn: 
                    if "custom_foods" not in user_data: user_data["custom_foods"] = {}
                    user_data["custom_foods"][cn] = {"cals":cc, "prot":cp, "carb":cch, "fat":cf}
                    sync_db(); st.success(f"Saved {cn}!")