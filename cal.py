import streamlit as st
import pandas as pd
import requests
from PIL import Image, ImageEnhance
from pyzbar.pyzbar import decode
from deep_translator import GoogleTranslator
import plotly.express as px
import base64

# --- 1. Offline Local Database ---
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

# --- 2. APIs & Functions ---
@st.cache_data(show_spinner=False)
def translate_query(query):
    try:
        return GoogleTranslator(source='auto', target='en').translate(query).lower()
    except:
        return query.lower()

@st.cache_data(show_spinner=False)
def get_food_by_barcode(barcode):
    url = f"https://world.openfoodfacts.org/api/v0/product/{barcode}.json"
    try:
        res = requests.get(url, timeout=5)
        if res.status_code == 200 and res.json().get("status") == 1:
            return res.json().get("product")
    except:
        return None
    return None

@st.cache_data(show_spinner=False)
def robust_global_search(en_query):
    results = []
    url = "https://world.openfoodfacts.org/cgi/search.pl"
    try:
        res = requests.get(url, params={"action": "process", "search_terms": en_query, "json": "True", "fields": "product_name,nutriments,brands"}, timeout=5)
        if res.status_code == 200:
            results.extend(res.json().get("products", []))
    except:
        pass
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
    return f'<a href="data:file/csv;base64,{b64}" download="{filename}" style="display:inline-block; padding:8px 16px; background-color:#ff4b4b; color:white; text-align:center; text-decoration:none; border-radius:4px;">📥 Download CSV Log</a>'

# --- 3. Session State ---
if 'daily_log' not in st.session_state: st.session_state.daily_log = []
if 'exercise_log' not in st.session_state: st.session_state.exercise_log = []
if 'water' not in st.session_state: st.session_state.water = 0
if 'body_weight' not in st.session_state: st.session_state.body_weight = 75.0
if 'custom_foods' not in st.session_state: st.session_state.custom_foods = {}

# Merge custom foods into offline DB
COMBINED_DB = {**OFFLINE_DB, **st.session_state.custom_foods}

# --- 4. UI Setup ---
st.set_page_config(page_title="MyFitness Pro", page_icon="💪", layout="centered")

with st.sidebar:
    st.header("🎯 Daily Goals")
    goal_cals = st.number_input("Calories", value=2500, step=100)
    goal_prot = st.number_input("Protein (g)", value=150, step=10)
    goal_carb = st.number_input("Carbs (g)", value=250, step=10)
    goal_fat = st.number_input("Fat (g)", value=80, step=5)
    
    st.markdown("---")
    st.header("⚖️ Body Weight")
    st.session_state.body_weight = st.number_input("Current Weight (kg)", value=st.session_state.body_weight, step=0.5)
    
    st.markdown("---")
    st.header("💧 Water Tracker")
    col1, col2, col3 = st.columns([1,1,1])
    if col1.button("➖"): st.session_state.water = max(0, st.session_state.water - 1)
    col2.markdown(f"<h3 style='text-align:center;'>{st.session_state.water}</h3>", unsafe_allow_html=True)
    if col3.button("➕"): st.session_state.water += 1

st.markdown("<h1 style='text-align: center;'>💪 MyFitness Pro</h1>", unsafe_allow_html=True)
st.write("")

# --- TABS ---
tab_dash, tab_add_food, tab_exercise, tab_custom = st.tabs(["📊 Diary", "🔍 Add Food", "🏃‍♂️ Exercise", "⚙️ Custom"])

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

    # Calories Equation
    st.markdown("### Calories Remaining")
    eq1, eq2, eq3, eq4, eq5, eq6, eq7 = st.columns([2,1,2,1,2,1,2])
    eq1.metric("Goal", f"{goal_cals}")
    eq2.markdown("<h4>-</h4>", unsafe_allow_html=True)
    eq3.metric("Food", f"{total_food_cals:.0f}")
    eq4.markdown("<h4>+</h4>", unsafe_allow_html=True)
    eq5.metric("Exercise", f"{total_burned:.0f}")
    eq6.markdown("<h4>=</h4>", unsafe_allow_html=True)
    eq7.metric("Remaining", f"{cals_remaining:.0f}")
    
    st.progress(min(net_cals / goal_cals, 1.0) if goal_cals > 0 else 0)
    
    if not df_food.empty:
        # Macros Chart
        st.markdown("---")
        st.markdown("### Macros")
        macro_df = pd.DataFrame({"Macro": ["Protein", "Carbs", "Fat"], "Grams": [total_prot, total_carb, total_fat]})
        fig = px.pie(macro_df, values='Grams', names='Macro', hole=0.4, color='Macro', color_discrete_map={'Protein':'#EF553B', 'Carbs':'#636EFA', 'Fat':'#00CC96'})
        fig.update_layout(margin=dict(t=0, b=0, l=0, r=0), height=250)
        st.plotly_chart(fig, use_container_width=True)

    

    st.markdown("---")
    st.markdown("### Meals Diary")
    for meal in ["Breakfast", "Lunch", "Dinner", "Snacks"]:
        meal_data = df_food[df_food["Meal"] == meal] if not df_food.empty else pd.DataFrame()
        meal_cals = meal_data["Calories"].sum() if not meal_data.empty else 0
        with st.expander(f"🍽️ {meal}  |  {meal_cals:.0f} kcal"):
            if not meal_data.empty:
                st.dataframe(meal_data.drop(columns=["Meal"]), hide_index=True, use_container_width=True)
            else:
                st.caption("Empty")

    if not df_food.empty:
        st.write("")
        st.markdown(get_csv_download_link(df_food), unsafe_allow_html=True)
        if st.button("🗑️ Clear Diary", use_container_width=True):
            st.session_state.daily_log = []
            st.session_state.exercise_log = []
            st.rerun()

# ==========================================
# TAB 2: ADD FOOD
# ==========================================
with tab_add_food:
    selected_meal = st.radio("Log to:", ["Breakfast", "Lunch", "Dinner", "Snacks"], horizontal=True)
    
    search_input = st.text_input("🔍 Search Food or Scan Barcode:", placeholder="Enter name in any language or barcode...")
    
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
                    selected_local = st.selectbox("Local/Custom Matches:", local_matches)
                    if selected_local:
                        product_name = selected_local.title()
                        db_item = COMBINED_DB[selected_local]
                        c_100, p_100, ch_100, f_100 = db_item["cals"], db_item["prot"], db_item["carb"], db_item["fat"]
                        found = True
                
                if not found:
                    results = robust_global_search(en_search)
                    if results:
                        options = {f"{p.get('product_name', 'Unknown')} ({p.get('brands', 'N/A')})": p for p in results[:10]}
                        selected_global = st.selectbox("Global Matches:", list(options.keys()))
                        if selected_global:
                            product_name = selected_global
                            n = options[selected_global].get('nutriments', {})
                            c_100, p_100, ch_100, f_100 = n.get("energy-kcal_100g", 0), n.get("proteins_100g", 0), n.get("carbohydrates_100g", 0), n.get("fat_100g", 0)
                            found = True

        if found:
            with st.container(border=True):
                st.markdown(f"#### {product_name}")
                st.caption(f"Per 100g: {c_100}kcal | {p_100}g P | {ch_100}g C | {f_100}g F")
                weight = st.number_input("Amount (grams):", min_value=1.0, value=100.0, step=10.0)
                
                cur_c, cur_p, cur_ch, cur_f = (c_100*weight)/100, (p_100*weight)/100, (ch_100*weight)/100, (f_100*weight)/100
                st.write(f"**Total:** {cur_c:.0f} kcal")
                
                if st.button("➕ ADD", type="primary", use_container_width=True):
                    st.session_state.daily_log.append({
                        "Meal": selected_meal, "Food": product_name, "Grams": weight, 
                        "Calories": round(cur_c, 1), "Protein": round(cur_p, 1), "Carbs": round(cur_ch, 1), "Fat": round(cur_f, 1)
                    })
                    st.success("Added!")

# ==========================================
# TAB 3: EXERCISE
# ==========================================
with tab_exercise:
    st.markdown("### Log Workout")
    ex_name = st.text_input("Exercise Name (e.g., Weightlifting, Running)")
    ex_cals = st.number_input("Calories Burned", min_value=0, step=50)
    
    if st.button("➕ Add Exercise", type="primary"):
        if ex_name and ex_cals > 0:
            st.session_state.exercise_log.append({"Exercise": ex_name, "Burned": ex_cals})
            st.success("Exercise logged! Check Dashboard.")
    
    if st.session_state.exercise_log:
        st.dataframe(pd.DataFrame(st.session_state.exercise_log), use_container_width=True, hide_index=True)

# ==========================================
# TAB 4: CUSTOM FOODS (Recipe Builder)
# ==========================================
with tab_custom:
    st.markdown("### Create Custom Food / Recipe")
    st.caption("Add your own recipes or foods not found in the database. They will be saved to your local search.")
    c_name = st.text_input("Food Name").lower()
    c_cals = st.number_input("Calories per 100g", min_value=0.0)
    c_prot = st.number_input("Protein per 100g", min_value=0.0)
    c_carb = st.number_input("Carbs per 100g", min_value=0.0)
    c_fat = st.number_input("Fat per 100g", min_value=0.0)
    
    if st.button("💾 Save Custom Food", type="primary"):
        if c_name:
            st.session_state.custom_foods[c_name] = {"cals": c_cals, "prot": c_prot, "carb": c_carb, "fat": c_fat}
            st.success(f"{c_name.title()} added to your database!")