import streamlit as st
import pandas as pd
import json
import os

# --- Configuration ---
DATA_FILE = "fitness_db.json"

# Basic items that will always be available
DEFAULT_FOODS = {
    "milk 3%": {"calories": 60, "protein": 3.2},
    "chicken breast": {"calories": 165, "protein": 31.0},
    "egg": {"calories": 155, "protein": 13.0},
    "cooked rice": {"calories": 130, "protein": 2.7},
    "oats": {"calories": 389, "protein": 16.9},
    "cottage cheese 5%": {"calories": 95, "protein": 11.0}
}

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

# Load database
food_db = load_data()

# --- UI Setup ---
st.set_page_config(page_title="Fitness Calculator", page_icon="⚖️")
st.title("Calories & Macros Calculator")

# Sidebar for adding new food
st.sidebar.header("Add New Food Item")
new_name = st.sidebar.text_input("Food Name").lower().strip()
new_cals = st.sidebar.number_input("Calories (per 100g)", min_value=0.0)
new_protein = st.sidebar.number_input("Protein (per 100g)", min_value=0.0)

if st.sidebar.button("Save to Database"):
    if new_name:
        food_db[new_name] = {"calories": new_cals, "protein": new_protein}
        save_data(food_db)
        st.sidebar.success(f"Added {new_name}!")
        st.rerun()
    else:
        st.sidebar.error("Please enter a name.")

# Main area for calculation
st.header("Calculate Your Portion")

if food_db:
    # Sort options alphabetically for easier search
    options = sorted(list(food_db.keys()))
    selected_food = st.selectbox("Select Food", options=options)
    
    # Input weight (e.g., 45g)
    weight = st.number_input("Weight (grams)", min_value=0.1, value=100.0, step=1.0)

    if selected_food:
        base_data = food_db[selected_food]
        total_cals = (base_data['calories'] * weight) / 100
        total_protein = (base_data['protein'] * weight) / 100

        st.markdown(f"### Summary for {weight}g of {selected_food}")
        
        col1, col2 = st.columns(2)
        col1.metric("Total Calories", f"{total_cals:.1f} kcal")
        col2.metric("Total Protein", f"{total_protein:.1f}g")
else:
    st.info("Your database is empty. Add food in the sidebar!")

st.markdown("---")

# Display database table
if st.checkbox("Show Food Database"):
    st.subheader("Nutritional Values (per 100g)")
    df = pd.DataFrame.from_dict(food_db, orient='index')
    st.table(df)