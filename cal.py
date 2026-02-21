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
st.set_page_config(page_title="Fitness Calculator