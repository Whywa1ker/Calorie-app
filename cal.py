import streamlit as st
import pandas as pd
import json
import os

# --- Configuration ---
DATA_FILE = "fitness_db.json"

DEFAULT_FOODS = {
    "milk 3%": {"calories": 60, "protein": 3.2},
    "chicken breast": {"calories": 165, "protein": 31.0},
    "egg": {"calories": 155, "protein": 13.0},
    "cooked rice": {"calories": 130, "protein": 2.7},
    "oats": {"calories": 389, "protein": 16.9},
    "cottage cheese 5%": {"calories": 95, "protein": 11.0}
}

# Initialize the daily log in session state if it doesn't exist
if 'daily_log' not in st.session_state:
    st.session_state.daily_log = []

def load_data():
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, "r") as f:
                return json.load(f)
        except:
            return DEFAULT_FOODS
    return DEFAULT_FOODS

def save_data(data):
    with open(DATA_FILE, "w") as f:
        json.dump(data, f, indent=4)

food_db = load_data()

# --- UI Setup ---
st.set_page_config(page_title="Fitness Calculator", page_icon="⚖️")
st.title("Daily Food Tracker")

# Sidebar - Add new food to DB
st.sidebar.header("Settings")
with st.sidebar.expander("Add New Food to Database"):
    new_name = st.text_input("Food Name").lower().strip()
    new_cals = st.number_input("Cals per 100g", min_value=0.0)
    new_protein = st.number_input("Protein per 100g", min_value=0.0)
    if st.button("Save to DB"):
        if new_name:
            food_db[new_name] = {"calories": new_cals, "protein": new_protein}
            save_data(food_db)
            st.success(f"Added {new_name}!")
            st.rerun()

# --- Main Calculator ---
st.header("1. Calculate & Add Meal")
options = sorted(list(food_db.keys()))
selected_food = st.selectbox("Select Food", options=options)
weight = st.number_input("Weight (grams)", min_value=0.1, value=100.0, step=1.0)

base_data = food_db[selected_food]
current_cals = (base_data['calories'] * weight) / 100
current_protein = (base_data['protein'] * weight) / 100

st.write(f"**Current selection:** {current_cals:.1f} kcal | {current_protein:.1f}g Protein")

if st.button("Add to Daily Log ➕"):
    # Add to the session state list
    entry = {
        "Food": selected_food,
        "Grams": weight,
        "Calories": round(current_cals, 1),
        "Protein": round(current_protein, 1)
    }
    st.session_state.daily_log.append(entry)
    st.success(f"Added {selected_food} to your log!")

# --- Daily Log Display ---
st.markdown("---")
st.header("2. Today's Food Log")

if st.session_state.daily_log:
    log_df = pd.DataFrame(st.session_state.daily_log)
    st.table(log_df)
    
    # Calculate Totals
    total_cals = log_df["Calories"].sum()
    total_protein = log_df["Protein"].sum()
    
    st.subheader("Daily Totals:")
    col1, col2 = st.columns(2)
    col1.metric("Total Calories", f"{total_cals:.1f} kcal")
    col2.metric("Total Protein", f"{total_protein:.1f}g")
    
    if st.button("Clear Log 🗑️"):
        st.session_state.daily_log = []
        st.rerun()
else:
    st.info("Your daily log is empty. Add a meal above!")

# Show DB Checkbox
if st.checkbox("Show Full Database"):
    st.write(pd.DataFrame.from_dict(food_db, orient='index'))