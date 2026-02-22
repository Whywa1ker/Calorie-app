import streamlit as st
import pandas as pd
import requests
from PIL import Image, ImageEnhance
from pyzbar.pyzbar import decode
from deep_translator import GoogleTranslator

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
    "bissli": {"cals": 490, "prot": 9.0, "carb": 60.0, "fat": 24.0},
    "tuna": {"cals": 116, "prot": 26.0, "carb": 0.0, "fat": 1.0}
}

# --- 2. Data Fetching & Translation Functions ---
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
        response = requests.get(url, timeout=5)
        if response.status_code == 200:
            data = response.json()
            if data.get("status") == 1:
                return data.get("product")
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
        
    seen = set()
    unique = []
    for p in results:
        name = p.get('product_name')
        if name and name not in seen:
            seen.add(name)
            unique.append(p)
    return unique

# --- Session State Initializations ---
if 'daily_log' not in st.session_state:
    st.session_state.daily_log = []

# --- UI Setup ---
st.set_page_config(page_title="Macro Tracker Pro", page_icon="💪", layout="centered")

# --- SIDEBAR: Daily Goals ---
with st.sidebar:
    st.header("🎯 Your Daily Targets")
    st.caption("Set your nutrition goals to track your progress throughout the day.")
    
    goal_cals = st.number_input("🔥 Calories Goal:", min_value=1000, max_value=6000, value=2500, step=100)
    goal_prot = st.number_input("🥩 Protein Goal (g):", min_value=50, max_value=300