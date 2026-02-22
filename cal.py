import streamlit as st
import pandas as pd
import requests
from PIL import Image
from pyzbar.pyzbar import decode

# --- 1. Super Fast Data Fetching (Cached) ---
@st.cache_data(show_spinner=False)
def get_food_by_barcode(barcode):
    url = f"https://world.openfoodfacts.org/api/v0/product/{barcode}.json"
    try:
        response = requests.get(url, timeout=4)
        if response.status_code == 200:
            data = response.json()
            if data.get("status") == 1:
                return data.get("product")
    except:
        return None
    return None

@st.cache_data(show_spinner=False)
def search_food_by_name(query):
    url = "https://world.openfoodfacts.org/cgi/search.pl"
    params = {"action": "process", "search_terms": query, "json": "True", "fields": "product_name,nutriments,brands"}
    try:
        res = requests.get(url, params=params, timeout=4)
        if res.status_code == 200:
            return res.json().get("products", [])
    except:
        return []
    return []

# --- Session State ---
if 'daily_log' not in st.session_state:
    st.session_state.daily_log = []

st.set_page_config(page_title="Lightning Tracker", page_icon="⚡")
st.title("⚡ Fast Nutrition Tracker")

# --- 2. Camera Barcode Scanner ---
st.header("Step 1: Snap Barcode")
camera_photo = st.camera_input("Take a clear picture of the barcode", label_visibility="collapsed")

scanned_barcode = ""

if camera_photo is not None:
    # Read the image and decode instantly
    image = Image.open(camera_photo)
    decoded_objects = decode(image)
    
    if decoded_objects:
        scanned_barcode = decoded_objects[0].data.decode("utf-8")
        st.success(f"Barcode Found: {scanned_barcode}")
    else:
        st.error("Could not read barcode. Please make sure the image is clear.")

# --- 3. Search & Auto-Fill ---
search_input = st.text_input("Barcode Number or Product Name:", value=scanned_barcode)

if search_input:
    product = None
    
    # Check if input is a barcode (numbers only) or a name
    if search_input.isdigit():
        product = get_food_by_barcode(search_input)
    else:
        results = search_food_by_name(search_input)
        if results:
            product = results[0] # Take the best match

    # --- 4. Instant Preview ---
    if product:
        name = product.get('product_name', 'Unknown Product')
        brand = product.get('brands', 'Unknown Brand')
        nutrients = product.get('nutriments', {})
        
        cals_100 = nutrients.get("energy-kcal_100g", 0)
        prot_100 = nutrients.get("proteins_100g", 0)
        carb_100 = nutrients.get("carbohydrates_100g", 0)
        fat_100  = nutrients.get("fat_100g", 0)
        
        st.markdown("---")
        st.subheader("🔍 Product Preview")
        st.markdown(f"**{name}** ({brand})")
        st.info(f"**Values per 100g:** {cals_100} kcal | P: {prot_100}g | C: {carb_100}g | F: {fat_100}g")
        
        # --- 5. Add to Log ---
        weight = st.number_input("Grams eaten:", min_value=1.0, value=100.0, step=1.0)
        
        cur_c = (cals_100 * weight) / 100
        cur_p = (prot_100 * weight) / 100
        cur_ch = (carb_100 * weight) / 100
        cur_f = (fat_100 * weight) / 100
        
        if st.button("➕ Add to My Day", type="primary"):
            st.session_state.daily_log.append({
                "Food": name,
                "Weight": weight,
                "Cals": round(cur_c, 1),
                "Prot": round(cur_p, 1),
                "Carb": round(cur_ch, 1),
                "Fat": round(cur_f, 1)
            })
            st.success(f"Added {weight}g of {name} to your daily log!")
            st.rerun()
    else:
        st.warning("Product not found in the global database.")

# --- 6. Daily Summary ---
st.markdown("---")
st.header("📊 Today's Macros")

if st.session_state.daily_log:
    df = pd.DataFrame(st.session_state.daily_log)
    st.dataframe(df, use_container_width=True)
    
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Cals", f"{df['Cals'].sum():.1f}")
    c2.metric("Protein", f"{df['Prot'].sum():.1f}g")
    c3.metric("Carbs", f"{df['Carb'].sum():.1f}g")
    c4.metric("Fat", f"{df['Fat'].sum():.1f}g")
    
    if st.button("🗑️ Clear Log"):
        st.session_state.daily_log = []
        st.rerun()