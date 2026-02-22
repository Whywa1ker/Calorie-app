import streamlit as st
import pandas as pd
import requests

# Function to fetch data from Open Food Facts API
def get_food_data(search_term):
    # If the input is a number, search by barcode, otherwise search by name
    if search_term.isdigit():
        url = f"https://world.openfoodfacts.org/api/v0/product/{search_term}.json"
        response = requests.get(url)
        if response.status_code == 200:
            data = response.json()
            if data.get("status") == 1:
                return [data.get("product")]
    else:
        url = "https://world.openfoodfacts.org/cgi/search.pl"
        params = {
            "action": "process",
            "search_terms": search_term,
            "json": "True",
            "page_size": 20,
            "fields": "product_name,nutriments,brands,code"
        }
        response = requests.get(url, params=params)
        if response.status_code == 200:
            return response.json().get("products", [])
    return []

# App Config
st.set_page_config(page_title="Fitness Tracker", page_icon="🏋️")
st.title("Nutrition Tracker & Barcode Search")

if 'daily_log' not in st.session_state:
    st.session_state.daily_log = []

# --- Search Section ---
st.header("1. Find Your Food")
user_input = st.text_input("Enter Product Name or Paste Barcode Number:")

if user_input:
    results = get_food_data(user_input)
    
    if results:
        # Create a display list for the dropdown
        options = {f"{p.get('product_name', 'Unknown')} ({p.get('brands', 'N/A')})": p for p in results}
        selection = st.selectbox("Is this the correct product?", list(options.keys()))
        
        if selection:
            item = options[selection]
            nutrients = item.get("nutriments", {})
            
            # Values per 100g
            cals_100g = nutrients.get("energy-kcal_100g", 0)
            prot_100g = nutrients.get("proteins_100g", 0)
            carb_100g = nutrients.get("carbohydrates_100g", 0)
            fat_100g = nutrients.get("fat_100g", 0)
            
            st.write(f"**Nutrients per 100g:** {cals_100g} kcal | P: {prot_100g}g | C: {carb_100g}g | F: {fat_100g}g")
            
            # --- Weight & Log ---
            weight = st.number_input("Weight consumed (grams):", min_value=1.0, value=100.0)
            
            f_cals = (cals_100g * weight) / 100
            f_prot = (prot_100g * weight) / 100
            f_carb = (carb_100g * weight) / 100
            f_fat = (fat_100g * weight) / 100
            
            if st.button("Add to Daily Log"):
                st.session_state.daily_log.append({
                    "Product": selection,
                    "Weight": weight,
                    "Cals": round(f_cals, 1),
                    "Prot": round(f_prot, 1),
                    "Carb": round(f_carb, 1),
                    "Fat": round(f_fat, 1)
                })
                st.success("Meal Added!")
                st.rerun()
    else:
        st.error("No data found. Check the name or barcode.")

# --- Summary Section ---
st.markdown("---")
st.header("2. Daily Log")

if st.session_state.daily_log:
    df = pd.DataFrame(st.session_state.daily_log)
    st.dataframe(df, use_container_width=True)
    
    # Totals
    st.subheader("Total Daily Intake")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Calories", f"{df['Cals'].sum():.1f}")
    c2.metric("Protein", f"{df['Prot'].sum():.1f}g")
    c3.metric("Carbs", f"{df['Carb'].sum():.1f}g")
    c4.metric("Fat", f"{df['Fat'].sum():.1f}g")
    
    if st.button("Clear Log"):
        st.session_state.daily_log = []
        st.rerun()