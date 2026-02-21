import streamlit as st
import pandas as pd
import json
import os

# --- Configuration ---
DATA_FILE = "fitness_db.json"


def load_data():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r") as f:
            return json.load(f)
    return {}


def save_data(data):
    with open(DATA_FILE, "w") as f:
        json.dump(data, f, indent=4)


# Load database
food_db = load_data()

# --- UI Setup ---
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
    else:
        st.sidebar.error("Please enter a name.")

# Main area for calculation
st.header("Calculate Your Meal")
if food_db:
    selected_food = st.selectbox("Select Food", options=list(food_db.keys()))
    weight = st.number_input("Weight (grams)", min_value=1.0, value=100.0)

    if selected_food:
        base_data = food_db[selected_food]
        total_cals = (base_data['calories'] * weight) / 100
        total_protein = (base_data['protein'] * weight) / 100

        col1, col2 = st.columns(2)
        col1.metric("Total Calories", f"{total_cals:.1f} kcal")
        col2.metric("Total Protein", f"{total_protein:.1f}g")
else:
    st.info("Your database is empty. Add some food in the sidebar first!")

# Display database
if st.checkbox("Show Database"):
    st.table(pd.DataFrame.from_dict(food_db, orient='index'))