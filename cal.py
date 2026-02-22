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
    "cottage cheese 5%": {"cals": 95, "prot": 11.0, "carb": 4.0, "fat": 5.0},
    "milk 3%": {"cals": 60, "prot": 3.2, "carb": 4.7, "fat": 3.0},
    "raw tahini": {"cals": 640, "prot": 24.0, "carb": 12.0, "fat": 54.0},
    "hummus": {"cals": 250, "prot": 8.0, "carb": 14.0, "fat": 18.0},
    "oats": {"cals": 389, "prot": 16.9, "carb": 66.0, "fat": 6.9},
    "buckwheat": {"cals": 343, "prot": 13.2, "carb": 71.5, "fat": 3.4},
    "bamba": {"cals": 534, "prot": 15.0, "carb": 40.0, "fat": 35.0},
    "bissli": {"cals": 490, "prot": 9.0, "carb": 60.0, "fat": 24.0}
}

# --- 2. Data Fetching & Translation Functions ---
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
def robust_search(query):
    results = []
    url = "https://world.openfoodfacts.org/cgi/search.pl"
    
    # Logic A: Search the exact input first (best for brands/local names)
    try:
        res = requests.get(url, params={"action": "process", "search_terms": query, "json": "True", "fields": "product_name,nutriments,brands"}, timeout=5)
        if res.status_code == 200:
            results.extend(res.json().get("products", []))
    except:
        pass
        
    # Logic B: Try translating to English as a fallback
    try:
        translated_query = GoogleTranslator(source='auto', target='en').translate(query)
        if translated_query.lower() != query.lower():
            res_trans = requests.get(url, params={"action": "process", "search_terms": translated_query, "json": "True", "fields": "product_name,nutriments,brands"}, timeout=5)
            if res_trans.status_code == 200:
                results.extend(res_trans.json().get("products", []))
    except:
        pass
        
    # Remove duplicates
    seen = set()
    unique = []
    for p in results:
        name = p.get('product_name')
        if name and name not in seen:
            seen.add(name)
            unique.append(p)
    return unique

# --- Session State ---
if 'daily_log' not in st.session_state:
    st.session_state.daily_log = []

st.set_page_config(page_title="Global Tracker", page_icon="🌍")
st.title("🌍 Multi-Language Tracker")

# --- 3. Camera Barcode Scanner ---
st.header("Step 1: Scan Barcode")
camera_photo = st.camera_input("Take a picture of the barcode", label_visibility="collapsed")
scanned_barcode = ""

if camera_photo is not None:
    image = Image.open(camera_photo)
    decoded_objects = decode(image)
    
    if not decoded_objects:
        gray_image = image.convert('L')
        enhancer = ImageEnhance.Contrast(gray_image)
        enhanced_image = enhancer.enhance(3.0)
        decoded_objects = decode(enhanced_image)

    if decoded_objects:
        scanned_barcode = decoded_objects[0].data.decode("utf-8")
        st.success(f"Barcode Found: {scanned_barcode}")
    else:
        st.error("Could not read barcode. Try to ensure good lighting.")

# --- 4. Multi-Language Search & Auto-Fill ---
search_input = st.text_input("Barcode or Food Name (Any Language):", value=scanned_barcode)

if search_input:
    product_name = ""
    cals_100 = prot_100 = carb_100 = fat_100 = 0
    found = False
    
    if search_input.isdigit():
        product = get_food_by_barcode(search_input)
        if product:
            product_name = f"{product.get('product_name', 'Unknown')} ({product.get('brands', 'Unknown')})"
            nutrients = product.get('nutriments', {})
            cals_100 = nutrients.get("energy-kcal_100g", 0)
            prot_100 = nutrients.get("proteins_100g", 0)
            carb_100 = nutrients.get("carbohydrates_100g", 0)
            fat_100  = nutrients.get("fat_100g", 0)
            found = True
    else:
        # Check Offline DB first
        local_matches = [name for name in OFFLINE_DB.keys() if search_input.lower() in name.lower()]
        
        if local_matches:
            selected_local = st.selectbox("Found in local database:", local_matches)
            if selected_local:
                product_name = selected_local.title()
                cals_100 = OFFLINE_DB[selected_local]["cals"]
                prot_100 = OFFLINE_DB[selected_local]["prot"]
                carb_100 = OFFLINE_DB[selected_local]["carb"]
                fat_100  = OFFLINE_DB[selected_local]["fat"]
                found = True
        
        if not found:
            results = robust_search(search_input)
            if results:
                # Show top 10 options to give the user a good selection
                options = {f"{p.get('product_name', 'Unknown')} ({p.get('brands', 'N/A')})": p for p in results[:10]}
                selected_global = st.selectbox("Found in global database:", list(options.keys()))
                if selected_global:
                    product = options[selected_global]
                    product_name = selected_global
                    nutrients = product.get('nutriments', {})
                    cals_100 = nutrients.get("energy-kcal_100g", 0)
                    prot_100 = nutrients.get("proteins_100g", 0)
                    carb_100 = nutrients.get("carbohydrates_100g", 0)
                    fat_100  = nutrients.get("fat_100g", 0)
                    found = True

    # --- 5. Instant Preview & Logging ---
    if found:
        st.markdown("---")
        st.subheader("🔍 Product Preview")
        st.markdown(f"**{product_name}**")
        st.info(f"**Values per 100g:** {cals_100} kcal | P: {prot_100}g | C: {carb_100}g | F: {fat_100}g")
        
        weight = st.number_input("Grams eaten:", min_value=1.0, value=100.0, step=1.0)
        
        cur_c = (cals_100 * weight) / 100
        cur_p = (prot_100 * weight) / 100
        cur_ch = (carb_100 * weight) / 100
        cur_f = (fat_100 * weight) / 100
        
        if st.button("➕ Add to My Day", type="primary"):
            st.session_state.daily_log.append({
                "Food": product_name, "Weight": weight, "Cals": round(cur_c, 1),
                "Prot": round(cur_p, 1), "Carb": round(cur_ch, 1), "Fat": round(cur_f, 1)
            })
            st.success("Added to your daily log!")
            st.rerun()
    else:
        st.warning("Product not found. Try a different term.")

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