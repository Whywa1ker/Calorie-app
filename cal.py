import streamlit as st
import pandas as pd
import requests
from PIL import Image, ImageEnhance
from pyzbar.pyzbar import decode
from deep_translator import GoogleTranslator
import plotly.express as px
import base64
from datetime import date

# --- 1. Scientific MET Values ---
EXERCISE_METS = {
    "Weightlifting (Standard/Hypertrophy)": 5.0,
    "Weightlifting (Heavy/Powerlifting)": 6.0,
    "Running (Moderate, 10 km/h)": 9.8,
    "Running (Fast, 12 km/h)": 11.8,
    "Walking (Brisk)": 4.3,
    "Cycling (Moderate)": 6.8,
    "Swimming (Freestyle, Moderate)": 8.3,
    "HIIT / Circuit Training": 8.0,
    "Yoga / Stretching": 2.5,
    "Custom (Manual Input)": 0.0
}

# --- 2. Offline Local Database ---
OFFLINE_DB = {
    "white bread": {"cals": 265, "prot": 8.0, "carb": 50.0, "fat": 3.0},
    "whole wheat bread": {"cals": 247, "prot": 11.0, "carb": 41.0, "fat": 3.0},
    "pita": {"cals": 275, "prot": 9.0, "carb": 55.0, "fat": 1.2},
    "chicken breast": {"cals": 165, "prot": 31.0, "carb": 0.0, "fat": 3.6},
    "egg": {"cals": 155, "prot": 13.0, "carb": 1.1, "fat": 11.0},
    "cooked rice": {"cals": 130, "prot": 2.7, "carb": 28.0, "fat": 0.3},
    "cottage cheese": {"cals": 95, "prot": 11.0, "carb": 4.0, "fat": 5.0},
    "milk": {"cals": 60, "prot": 3.2, "carb": 4.7, "fat": 3.0},
    "tahini": {"cals": 640, "prot": 24.0, "carb": 12.0, "fat": 54.0},
    "hummus": {"cals": 250, "prot": 8.0, "carb": 14.0, "fat": 18.0},
    "oats": {"cals": 389, "prot": 16.9, "carb": 66.0, "fat": 6.9},
    "buckwheat": {"cals": 343, "prot": 13.2, "carb": 71.5, "fat": 3.4},
    "bamba": {"cals": 534, "prot": 15.0, "carb": 40.0, "fat": 35.0},
    "tuna": {"cals": 116, "prot": 26.0, "carb": 0.0, "fat": 1.0}
}

# --- 3. APIs & Functions ---
@st.cache_data(show_spinner=False)
def translate_query(query):
    try: return GoogleTranslator(source='auto', target='en').translate(query).lower()
    except: return query.lower()

@st.cache_data(show_spinner=False)
def get_food_by_barcode(barcode):
    url = f"https://world.openfoodfacts.org/api/v0/product/{barcode}.json"
    try:
        res = requests.get(url, timeout=5)
        if res.status_code == 200 and res.json().get("status") == 1:
            return res.json().get("product")
    except: return None
    return None

@st.cache_data(show_spinner=False)
def robust_global_search(en_query):
    results = []
    url = "https://world.openfoodfacts.org/cgi/search.pl"
    try:
        res = requests.get(url, params={"action": "process", "search_terms": en_query, "json": "True", "fields": "product_name,nutriments,brands"}, timeout=5)
        if res.status_code == 200: results.extend(res.json().get("products", []))
    except: pass
    seen, unique = set(), []
    for p in results:
        name = p.get('product_name')
        if name and name not in seen:
            seen.add(name)
            unique.append(p)
    return unique

def get_csv_download_link(df, filename="my_nutrition_log.csv"):
    csv = df.to_csv(index=False)
    b64 = base64.b64encode(csv.encode()).decode()
    return f'<a href="data:file/csv;base64,{b64}" download="{filename}" style="display:inline-block; padding:10px 20px; background-color:#2e66ff; color:white; text-align:center; font-weight:bold; text-decoration:none; border-radius:8px;">📥 Export Data to CSV</a>'

# --- 4. Session State Initializations ---
if 'daily_log' not in st.session_state: st.session_state.daily_log = []
if 'exercise_log' not in st.session_state: st.session_state.exercise_log = []
if 'water_glasses' not in st.session_state: st.session_state.water_glasses = 0
if 'custom_foods' not in st.session_state: st.session_state.custom_foods = {}
if 'weight_log' not in st.session_state:
    # Initialize with a default starting weight
    st.session_state.weight_log = [{"Date": str(date.today()), "Weight": 75.0}]

COMBINED_DB = {**OFFLINE_DB, **st.session_state.custom_foods}

# Get the latest weight from the log for calculations
current_weight = sorted(st.session_state.weight_log, key=lambda x: x["Date"])[-1]["Weight"] if st.session_state.weight_log else 75.0

# --- 5. UI Setup & Custom CSS ---
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

# --- SIDEBAR: Settings & Water ---
with st.sidebar:
    st.header("⚙️ Smart Settings")
    
    calc_mode = st.radio("Target Method:", ["Auto-Calculate (TDEE)", "Manual Setup"])
    
    if calc_mode == "Auto-Calculate (TDEE)":
        st.markdown("### 🧑 Profile")
        gender = st.selectbox("Gender", ["Male", "Female"])
        age = st.number_input("Age", min_value=10, max_value=100, value=21)
        # Weight is now pulled from the latest entry in the Weight Tracker!
        st.info(f"**Current Weight:** {current_weight} kg *(Updates from Weight Tracker tab)*")
        height = st.number_input("Height (cm)", min_value=100.0, max_value=250.0, value=175.0, step=1.0)
        
        st.markdown("### 🏃 Activity & Goal")
        activity_level = st.selectbox("Daily Activity", [
            "Sedentary (Desk job)", "Lightly active (1-3 days/wk)", 
            "Moderately active (3-5 days/wk)", "Very active (6-7 days/wk)", "Super active (Physical job)"
        ])
        fitness_goal = st.selectbox("Objective", ["Weight Loss (Cut)", "Maintenance", "Lean Muscle Gain", "Bodybuilding (Bulk)"])
        
        # Target Math
        multipliers = {
            "Sedentary (Desk job)": 1.2, "Lightly active (1-3 days/wk)": 1.375,
            "Moderately active (3-5 days/wk)": 1.55, "Very active (6-7 days/wk)": 1.725, "Super active (Physical job)": 1.9
        }
        
        if gender == "Male": bmr = (10 * current_weight) + (6.25 * height) - (5 * age) + 5
        else: bmr = (10 * current_weight) + (6.25 * height) - (5 * age) - 161
        tdee = bmr * multipliers[activity_level]
        
        if fitness_goal == "Weight Loss (Cut)": goal_cals = int(tdee - 500); p_pct, c_pct, f_pct = 0.40, 0.35, 0.25
        elif fitness_goal == "Maintenance": goal_cals = int(tdee); p_pct, c_pct, f_pct = 0.30, 0.40, 0.30
        elif fitness_goal == "Lean Muscle Gain": goal_cals = int(tdee + 300); p_pct, c_pct, f_pct = 0.25, 0.50, 0.25
        else: goal_cals = int(tdee + 500); p_pct, c_pct, f_pct = 0.30, 0.50, 0.20
            
        goal_prot = int((goal_cals * p_pct) / 4)
        goal_carb = int((goal_cals * c_pct) / 4)
        goal_fat = int((goal_cals * f_pct) / 9)
        
        base_water_ml = current_weight * 35
        if "active" in activity_level.lower() and "lightly" not in activity_level.lower(): base_water_ml += 750
        goal_water_glasses = int(base_water_ml / 250)
        st.success("✅ **Targets Calibrated**")

    else:
        st.markdown("### ✍️ Manual Entry")
        goal_cals = st.number_input("Calories", value=2500, step=100)
        goal_prot = st.number_input("Protein (g)", value=150, step=10)
        goal_carb = st.number_input("Carbs (g)", value=250, step=10)
        goal_fat = st.number_input("Fat (g)", value=80, step=5)
        goal_water_glasses = st.number_input("Water Target (Glasses)", value=10, step=1)

    st.markdown("---")
    st.header("💧 Hydration Station")
    st.caption(f"Goal: {goal_water_glasses} Glasses ({goal_water_glasses * 0.25:.1f}L)")
    
    w_col1, w_col2, w_col3 = st.columns([1,1,1])
    if w_col1.button("➖"): st.session_state.water_glasses = max(0, st.session_state.water_glasses - 1)
    w_col2.markdown(f"<h3 style='text-align:center; color:#2e66ff;'>{st.session_state.water_glasses} 🥤</h3>", unsafe_allow_html=True)
    if w_col3.button("➕"): st.session_state.water_glasses += 1
    
    st.progress(min(st.session_state.water_glasses / goal_water_glasses, 1.0) if goal_water_glasses > 0 else 0)

# --- MAIN APP HEADER ---
st.markdown("<h1 style='text-align: center; color: #1f2937;'>⚡ MyFitness Pro</h1>", unsafe_allow_html=True)
st.write("")

tab_dash, tab_add_food, tab_exercise, tab_weight, tab_custom = st.tabs(["📊 Diary", "🥑 Add Food", "🏃‍♂️ Exercise", "⚖️ Weight", "⚙️ Custom"])

# ==========================================
# TAB 1: DIARY & DASHBOARD
# ==========================================
with tab_dash:
    df_food = pd.DataFrame(st.session_state.daily_log)
    df_ex = pd.DataFrame(st.session_state.exercise_log)
    
    total_food_cals = df_food['Calories'].sum() if not df_food.empty else 0
    total_prot = df_food['Protein'].sum() if not df_food.empty else 0
    total_carb = df_food['Carbs'].sum() if not df_food.empty else 0
    total_fat = df_food['Fat'].sum() if not df_food.empty else 0
    total_burned = df_ex['Burned'].sum() if not df_ex.empty else 0
    
    net_cals = total_food_cals - total_burned
    cals_remaining = goal_cals - net_cals

    with st.container(border=True):
        st.markdown("### ⚖️ Energy Balance")
        eq1, eq2, eq3, eq4, eq5, eq6, eq7 = st.columns([2,1,2,1,2,1,2])
        eq1.metric("Goal", f"{goal_cals}")
        eq2.markdown("<h2 style='text-align:center; color:#9ca3af;'>-</h2>", unsafe_allow_html=True)
        eq3.metric("Food", f"{total_food_cals:.0f}")
        eq4.markdown("<h2 style='text-align:center; color:#9ca3af;'>+</h2>", unsafe_allow_html=True)
        eq5.metric("Burned", f"{total_burned:.0f}")
        eq6.markdown("<h2 style='text-align:center; color:#9ca3af;'>=</h2>", unsafe_allow_html=True)
        eq7.metric("Remaining", f"{cals_remaining:.0f}")
        st.progress(min(net_cals / goal_cals, 1.0) if goal_cals > 0 else 0)
    
    if not df_food.empty:
        st.write("")
        col_macro, col_pie = st.columns([1, 1])
        with col_macro:
            st.markdown("### 🥩 Macros Progress")
            st.caption(f"**Protein:** {total_prot:.0f}g / {goal_prot}g")
            st.progress(min(total_prot / goal_prot, 1.0) if goal_prot > 0 else 0)
            st.caption(f"**Carbs:** {total_carb:.0f}g / {goal_carb}g")
            st.progress(min(total_carb / goal_carb, 1.0) if goal_carb > 0 else 0)
            st.caption(f"**Fat:** {total_fat:.0f}g / {goal_fat}g")
            st.progress(min(total_fat / goal_fat, 1.0) if goal_fat > 0 else 0)
            
        with col_pie:
            macro_df = pd.DataFrame({"Macro": ["Protein", "Carbs", "Fat"], "Grams": [total_prot, total_carb, total_fat]})
            fig = px.pie(macro_df, values='Grams', names='Macro', hole=0.5, color='Macro', color_discrete_map={'Protein':'#EF553B', 'Carbs':'#636EFA', 'Fat':'#00CC96'})
            fig.update_layout(margin=dict(t=20, b=0, l=0, r=0), height=200, showlegend=False)
            st.plotly_chart(fig, use_container_width=True)

        st.markdown("---")
        st.markdown("### 🍽️ Meals Diary")
        for meal in ["Breakfast", "Lunch", "Dinner", "Snacks"]:
            meal_data = df_food[df_food["Meal"] == meal] if not df_food.empty else pd.DataFrame()
            meal_cals = meal_data["Calories"].sum() if not meal_data.empty else 0
            with st.expander(f"**{meal}** |  {meal_cals:.0f} kcal"):
                if not meal_data.empty: st.dataframe(meal_data.drop(columns=["Meal"]), hide_index=True, use_container_width=True)
                else: st.caption("No items logged.")

        st.write("")
        st.markdown(get_csv_download_link(df_food, "daily_food_log.csv"), unsafe_allow_html=True)
        st.write("")
        if st.button("🗑️ Reset Entire Day", use_container_width=True):
            st.session_state.daily_log = []
            st.session_state.exercise_log = []
            st.session_state.water_glasses = 0
            st.rerun()

# ==========================================
# TAB 2: ADD FOOD
# ==========================================
with tab_add_food:
    st.markdown("### 🔍 Find & Log")
    selected_meal = st.radio("Select Meal:", ["Breakfast", "Lunch", "Dinner", "Snacks"], horizontal=True)
    search_input = st.text_input("Search or Scan Barcode:", placeholder="Type anything...")
    
    if search_input:
        product_name = ""
        c_100 = p_100 = ch_100 = f_100 = 0
        found = False
        
        with st.spinner("Searching..."):
            if search_input.isdigit():
                product = get_food_by_barcode(search_input)
                if product:
                    product_name = f"{product.get('product_name', 'Unknown')}"
                    n = product.get('nutriments', {})
                    c_100, p_100, ch_100, f_100 = n.get("energy-kcal_100g", 0), n.get("proteins_100g", 0), n.get("carbohydrates_100g", 0), n.get("fat_100g", 0)
                    found = True
            else:
                en_search = translate_query(search_input)
                local_matches = [name for name in COMBINED_DB.keys() if en_search in name.lower() or search_input.lower() in name.lower()]
                if local_matches:
                    selected_local = st.selectbox("Quick Matches:", local_matches)
                    if selected_local:
                        product_name = selected_local.title()
                        db_item = COMBINED_DB[selected_local]
                        c_100, p_100, ch_100, f_100 = db_item["cals"], db_item["prot"], db_item["carb"], db_item["fat"]
                        found = True
                
                if not found:
                    results = robust_global_search(en_search)
                    if results:
                        options = {f"{p.get('product_name', 'Unknown')} ({p.get('brands', 'N/A')})": p for p in results[:10]}
                        selected_global = st.selectbox("Global Database Matches:", list(options.keys()))
                        if selected_global:
                            product_name = selected_global
                            n = options[selected_global].get('nutriments', {})
                            c_100, p_100, ch_100, f_100 = n.get("energy-kcal_100g", 0), n.get("proteins_100g", 0), n.get("carbohydrates_100g", 0), n.get("fat_100g", 0)
                            found = True

        if found:
            with st.container(border=True):
                st.markdown(f"#### 🍽️ {product_name}")
                st.caption(f"Base Values (100g) ➔ {c_100} kcal | {p_100}g P")
                food_weight = st.number_input("⚖️ Portion Amount (grams):", min_value=1.0, value=100.0, step=10.0)
                
                cur_c, cur_p, cur_ch, cur_f = (c_100*food_weight)/100, (p_100*food_weight)/100, (ch_100*food_weight)/100, (f_100*food_weight)/100
                st.success(f"**Total: {cur_c:.0f} kcal**")
                
                if st.button(f"➕ Add to {selected_meal}", type="primary", use_container_width=True):
                    st.session_state.daily_log.append({
                        "Meal": selected_meal, "Food": product_name, "Grams": food_weight, 
                        "Calories": round(cur_c, 1), "Protein": round(cur_p, 1), "Carbs": round(cur_ch, 1), "Fat": round(cur_f, 1)
                    })
                    st.rerun()

# ==========================================
# TAB 3: EXERCISE
# ==========================================
with tab_exercise:
    st.markdown("### 🏃‍♂️ Scientific Calorie Burner")
    selected_exercise = st.selectbox("Select Activity Type:", list(EXERCISE_METS.keys()))
    
    if selected_exercise == "Custom (Manual Input)":
        ex_name = st.text_input("Custom Exercise Name:")
        final_cals_burned = st.number_input("Calories Burned", min_value=0, step=50)
    else:
        ex_name = selected_exercise
        duration_min = st.number_input("Duration (minutes):", min_value=1, value=45, step=5)
        met_value = EXERCISE_METS[selected_exercise]
        # Uses the dynamically updated current_weight
        calc_cals = (met_value * 3.5 * current_weight) / 200 * duration_min
        final_cals_burned = int(calc_cals)
        st.info(f"💡 Based on your weight ({current_weight}kg) and {duration_min} mins of {selected_exercise} (MET {met_value}), you burned approximately **{final_cals_burned} kcal**.")

    if st.button("➕ Log Workout", type="primary", use_container_width=True):
        if ex_name and final_cals_burned > 0:
            st.session_state.exercise_log.append({"Exercise": ex_name, "Burned": final_cals_burned})
            st.success("Workout logged! Calories have been added back to your daily budget.")
    
    if st.session_state.exercise_log:
        st.dataframe(pd.DataFrame(st.session_state.exercise_log), use_container_width=True, hide_index=True)

# ==========================================
# TAB 4: WEIGHT TRACKER
# ==========================================
with tab_weight:
    st.markdown("### 📈 Body Weight Progress")
    st.caption("Log your weight daily, weekly, or whenever you want. The graph will connect the dots automatically.")
    
    with st.container(border=True):
        st.markdown("#### Log New Entry")
        w_col1, w_col2 = st.columns(2)
        log_date = w_col1.date_input("Date", value=date.today())
        log_weight = w_col2.number_input("Weight (kg)", min_value=30.0, max_value=250.0, value=float(current_weight), step=0.1)
        
        if st.button("💾 Save Weight", type="primary", use_container_width=True):
            date_str = str(log_date)
            # Remove existing entry for the same date if it exists to overwrite
            st.session_state.weight_log = [entry for entry in st.session_state.weight_log if entry["Date"] != date_str]
            # Add new entry
            st.session_state.weight_log.append({"Date": date_str, "Weight": log_weight})
            # Sort chronologically
            st.session_state.weight_log = sorted(st.session_state.weight_log, key=lambda x: x["Date"])
            st.success("Weight saved! Calculations have been updated.")
            st.rerun()

    if len(st.session_state.weight_log) > 0:
        st.markdown("---")
        df_weight = pd.DataFrame(st.session_state.weight_log)
        
        # Plotly Line Chart
        fig_weight = px.line(df_weight, x="Date", y="Weight", markers=True, text="Weight", title="Weight Journey")
        fig_weight.update_traces(textposition="top center", line_color="#2e66ff", marker=dict(size=8))
        fig_weight.update_layout(margin=dict(t=40, b=0, l=0, r=0), yaxis_title="Kg", xaxis_title="")
        st.plotly_chart(fig_weight, use_container_width=True)
        
        st.markdown("#### 📋 History Log")
        st.caption("You can edit or delete entries directly in the table below.")
        edited_weight_df = st.data_editor(df_weight, num_rows="dynamic", use_container_width=True, hide_index=True)
        
        # Save edits if the user changed the table manually
        if not edited_weight_df.equals(df_weight):
            st.session_state.weight_log = edited_weight_df.to_dict('records')
            st.rerun()
            
        st.write("")
        st.markdown(get_csv_download_link(df_weight, "weight_history.csv"), unsafe_allow_html=True)

# ==========================================
# TAB 5: CUSTOM RECIPES
# ==========================================
with tab_custom:
    st.markdown("### 👨‍🍳 Recipe Builder")
    c_name = st.text_input("Food/Recipe Name").lower()
    c_cals = st.number_input("Calories (per 100g)", min_value=0.0)
    c_prot = st.number_input("Protein (per 100g)", min_value=0.0)
    c_carb = st.number_input("Carbs (per 100g)", min_value=0.0)
    c_fat = st.number_input("Fat (per 100g)", min_value=0.0)
    
    if st.button("💾 Save to My Database", type="primary"):
        if c_name:
            st.session_state.custom_foods[c_name] = {"cals": c_cals, "prot": c_prot, "carb": c_carb, "fat": c_fat}
            st.success(f"'{c_name.title()}' saved!")