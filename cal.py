import streamlit as st
import pandas as pd
import requests
from streamlit_barcode_scanner import st_barcode_scanner

# Function to get data by Barcode
def get_product_by_barcode(barcode):
    url = f"https://world.openfoodfacts.org/api/v0/product/{barcode}.json"
    response = requests.get(url)
    if response.status_code == 200:
        data = response.json()
        if data.get("status") == 1:
            return data.get("product")
    return None

if 'daily_log' not in st.session_state:
    st.session_state.daily_log = []

st.set_page_config(page_title="Barcode Fitness Scanner", page_icon="📸")
st.title("Scan & Track Your Food")

# --- Step 1: Barcode Scanning ---
st.header("1. Scan Barcode")
st.write("Point your camera at the product's barcode")

# This opens the camera in the browser
barcode = st_barcode_scanner()

if barcode:
    st.write(f"Scanned Barcode: {barcode}")
    product = get_product_by_barcode(barcode)
    
    if product:
        name = product.get("product_name", "Unknown Product")
        brand = product.get("brands", "Unknown Brand")
        nutrients = product.get("nutriments", {})
        
        # Values per 100g
        cals_100g = nutrients.get("energy-kcal_100g", 0)
        prot_100g = nutrients.get("proteins_100g", 0)
        carb_100g = nutrients.get("carbohydrates_100g", 0)
        fat_100g = nutrients.get("fat_100g", 0)
        
        st.success(f"Found: {name} by {brand}")
        st.write(f"**Nutrition (per 100g):** {cals_100g} kcal | P: {prot_100g}g | C: {carb_100g}g | F: {fat_100g}g")
        
        # --- Step 2: Weight & Add ---
        weight = st.number_input("How many grams did you eat?", min_value=1.0, value=100.0)
        
        final_cals = (cals_100g * weight) / 100
        final_prot = (prot_100g * weight) / 100
        final_carb = (carb_100g * weight) / 100
        final_fat = (fat_100g * weight) / 100
        
        if st.button("Add to Daily Log ➕"):
            st.session_state.daily_log.append({
                "Food": f"{name} ({brand})",
                "Grams": weight,
                "Calories": round(final_cals, 1),
                "Protein": round(final_prot, 1),
                "Carbs": round(final_carb, 1),
                "Fat": round(final_fat, 1)
            })
            st.success("Added!")
            st.rerun()
    else:
        st.error("Product not found in database. You can still add it manually in the sidebar.")

# --- Step 3: Summary ---
st.markdown("---")
st.header("2. Today's Totals")
if st.session_state.daily_log:
    df = pd.DataFrame(st.session_state.daily_log)
    st.dataframe(df, use_container_width=True)
    st.metric("Total Calories Today", f"{df['Calories'].sum():.1f} kcal")
    if st.button("Clear Today"):
        st.session_state.daily_log = []
        st.rerun()