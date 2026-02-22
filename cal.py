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

# --- 2. Data Fetching Functions ---
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
    try:
        res = requests.get(url, params={"action": "process", "search_terms": query, "json": "True", "fields": "product_name,nutriments,brands"}, timeout=5)
        if res.status_code == 200:
            results.extend(res.json().get("products", []))
    except:
        pass
    try:
        translated_query = GoogleTranslator(source='auto', target='en').translate(query)
        if translated_query.lower() != query.lower():
            res_trans = requests.get(url, params={"action": "process", "search_terms": translated_query, "json": "True", "fields": "product_name,nutriments,brands"}, timeout=5)
            if res_trans.status_code == 200:
                results.extend(res_trans.json().get("products", []))
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

# --- Session State ---
if 'daily_log' not in st.session_state:
    st.session_state.daily_log = []

# --- UI Setup ---
st.set_page_config(page_title="Macro Tracker Pro", page_icon="🍏", layout="centered")

st.markdown("<h1 style='text-align: center;'>🍏 Macro Tracker Pro</h1>", unsafe_allow_html=True)
st.markdown("<p style='text-align: center; color: gray;'>Scan, search, and track your daily nutrition effortlessly.</p>", unsafe_allow_html=True)
st.write("")

# --- TABS FOR CLEAN UI ---
tab_add, tab_log = st.tabs(["🔍 Add Food", "📊 My Daily Log"])

with tab_add:
    # 1. Expandable Camera Scanner
    with st.expander("📷 Open Camera to Scan Barcode", expanded=False):
        camera_photo = st.camera_input("Take a clear picture of the barcode", label_visibility="collapsed")
    
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
            st.success(f"Barcode Detected: {scanned_barcode}")
        else:
            st.error("Could not read barcode. Try again with better lighting.")

    # 2. Search Box
    st.markdown("### 🔎 Search Database")
    search_input = st.text_input("Enter Barcode or Food Name (Any Language):", value=scanned_barcode, placeholder="e.g., Cottage cheese, לחם, Apple...")

    if search_input:
        product_name = ""
        cals_100 = prot_100 = carb_100 = fat_100 = 0
        found = False
        
        with st.spinner("Searching..."):
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
                local_matches = [name for name in OFFLINE_DB.keys() if search_input.lower() in name.lower()]
                if local_matches:
                    selected_local = st.selectbox("Select exact match:", local_matches)
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
                        options = {f"{p.get('product_name', 'Unknown')} ({p.get('brands', 'N/A')})": p for p in results[:10]}
                        selected_global = st.selectbox("Select exact match:", list(options.keys()))
                        if selected_global:
                            product = options[selected_global]
                            product_name = selected_global
                            nutrients = product.get('nutriments', {})
                            cals_100 = nutrients.get("energy-kcal_100g", 0)
                            prot_100 = nutrients.get("proteins_100g", 0)
                            carb_100 = nutrients.get("carbohydrates_100g", 0)
                            fat_100  = nutrients.get("fat_100g", 0)
                            found = True

        # 3. Dynamic Preview Card
        if found:
            st.write("")
            with st.container(border=True):
                st.markdown(f"#### 🍽️ {product_name}")
                st.caption(f"Base values (100g): {cals_100} kcal | Protein: {prot_100}g | Carbs: {carb_100}g | Fat: {fat_100}g")
                
                weight = st.number_input("⚖️ Amount eaten (grams):", min_value=1.0, value=100.0, step=5.0)
                
                cur_c = (cals_100 * weight) / 100
                cur_p = (prot_100 * weight) / 100
                cur_ch = (carb_100 * weight) / 100
                cur_f = (fat_100 * weight) / 100
                
                st.markdown("##### Total for this portion:")
                p_col1, p_col2, p_col3, p_col4 = st.columns(4)
                p_col1.metric("Calories", f"{cur_c:.0f}")
                p_col2.metric("Protein", f"{cur_p:.1f}g")
                p_col3.metric("Carbs", f"{cur_ch:.1f}g")
                p_col4.metric("Fat", f"{cur_f:.1f}g")
                
                st.write("")
                if st.button("➕ Add to Daily Log", type="primary", use_container_width=True):
                    st.session_state.daily_log.append({
                        "Food": product_name, "Weight": weight, "Calories": round(cur_c, 1),
                        "Protein": round(cur_p, 1), "Carbs": round(cur_ch, 1), "Fat": round(cur_f, 1)
                    })
                    st.success("Added! Check the 'My Daily Log' tab.")
        else:
            if search_input:
                st.warning("Product not found. Try a different term or scan the barcode.")

with tab_log:
    st.markdown("### 📈 Today's Summary")
    
    if st.session_state.daily_log:
        df = pd.DataFrame(st.session_state.daily_log)
        
        # Dashboard Metrics
        total_cals = df['Calories'].sum()
        total_prot = df['Protein'].sum()
        total_carb = df['Carbs'].sum()
        total_fat = df['Fat'].sum()

        m_col1, m_col2, m_col3, m_col4 = st.columns(4)
        m_col1.metric("🔥 Calories", f"{total_cals:.0f}")
        m_col2.metric("🥩 Protein", f"{total_prot:.1f}g")
        m_col3.metric("🍞 Carbs", f"{total_carb:.1f}g")
        m_col4.metric("🥑 Fat", f"{total_fat:.1f}g")
        
        st.write("")
        st.markdown("#### 📋 Food List")
        # Clean display of the dataframe without the index
        st.dataframe(df, use_container_width=True, hide_index=True)
        
        st.write("")
        if st.button("🗑️ Clear All Entries", use_container_width=True):
            st.session_state.daily_log = []
            st.rerun()
    else:
        st.info("Your log is empty. Search and add some food from the other tab!")