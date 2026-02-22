import streamlit as st
import pandas as pd
import requests

# --- API Configuration ---
# We use Open Food Facts API (Free and Open Source)
SEARCH_URL = "https://world.openfoodfacts.org/cgi/search.pl"

def search_food(query):
    """Searches the Open Food Facts database for a specific product."""
    params = {
        "action": "process",
        "tagtype_0": "categories",
        "tag_contains_0": "contains",
        "tag_0": query,
        "json": "True",
        "page_size": 10,
        "fields": "product_name,nutriments,brands"
    }
    response = requests.get(SEARCH_URL, params=params)
    if response.status_code == 200:
        return response.json().get("products", [])
    return []

if 'daily_log' not in st.session_state:
    st.session_state.daily_log = []

# --- UI Setup ---
st.set_page_config(page_title="Smart Fitness Tracker", page_icon="🥗")
st.title("Auto-Search Nutrition Tracker")

st.markdown("---")

# --- Step 1: Search ---
st.header("1. Search Global Database")
search_query = st.text_input("Enter product name (e.g., 'Cottage Cheese', 'Bamba'):")

if search_query:
    results = search_food(search_query)
    
    if results:
        # Create a list for the dropdown
        options = {f"{p.get('product_name')} ({p.get('brands', 'Unknown')})": p for p in results}
        selection = st.selectbox("Select the exact product:", list(options.keys()))
        
        if selection:
            product = options[selection]
            nutrients = product.get("nutriments", {})
            
            # Extract values per 100g (defaulting to 0 if not found)
            cals_100g = nutrients.get("energy-kcal_100g", 0)
            prot_100g = nutrients.get("proteins_100g", 0)
            carb_100g = nutrients.get("carbohydrates_100g", 0)
            fat_100g = nutrients.get("fat_100g", 0)
            
            st.write(f"**Values per 100g:** {cals_100g} kcal | P: {prot_100g}g | C: {carb_100g}g | F: {fat_100g}g")
            
            # --- Step 2: Calculate ---
            weight = st.number_input("How many grams did you eat?", min_value=1.0, value=100.0)
            
            final_cals = (cals_100g * weight) / 100
            final_prot = (prot_100g * weight) / 100
            final_carb = (carb_100g * weight) / 100
            final_fat = (fat_100g * weight) / 100
            
            st.success(f"**Total:** {final_cals:.1f} kcal | P: {final_prot:.1f}g | C: {final_carb:.1f}g | F: {final_fat:.1f}g")
            
            if st.button("Add to Daily Log ➕"):
                st.session_state.daily_log.append({
                    "Food": selection,
                    "Grams": weight,
                    "Calories": round(final_cals, 1),
                    "Protein": round(final_prot, 1),
                    "Carbs": round(final_carb, 1),
                    "Fat": round(final_fat, 1)
                })
                st.rerun()
    else:
        st.warning("No products found. Try a different name.")

# --- Step 3: Daily Summary ---
st.markdown("---")
st.header("2. Today's Totals")

if st.session_state.daily_log:
    df = pd.DataFrame(st.session_state.daily_log)
    st.dataframe(df, use_container_width=True)
    
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Calories", f"{df['Calories'].sum():.1f}")
    col2.metric("Protein", f"{df['Protein'].sum():.1f}g")
    col3.metric("Carbs", f"{df['Carbs'].sum():.1f}g")
    col4.metric("Fat", f"{df['Fat'].sum():.1f}g")
    
    if st.button("Clear Log"):
        st.session_state.daily_log = []
        st.rerun()