import streamlit as st
import pandas as pd
import requests
import streamlit.components.v1 as components

# --- Function: Get Data by Barcode ---
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

# --- Session State ---
if 'daily_log' not in st.session_state:
    st.session_state.daily_log = []

st.set_page_config(page_title="Pro Fitness Scanner", page_icon="💪")
st.title("Smart Nutrition Tracker")

# --- Step 1: Barcode Scanner (JavaScript Component) ---
st.header("1. Scan or Search Product")

# Custom JavaScript Barcode Scanner
st.markdown("### 📸 Quick Scan")
barcode_input = st.text_input("Barcode detected (Manual or Scanned):", key="barcode_input")

# JS Code to use browser camera for scanning
scanner_html = """
<div id="interactive" class="viewport" style="width: 100%; height: 300px;"></div>
<script src="https://cdnjs.cloudflare.com/ajax/libs/quagga/0.12.1/quagga.min.js"></script>
<script>
    Quagga.init({
        inputStream : { name : "Live", type : "LiveStream", target: document.querySelector('#interactive') },
        decoder : { readers : ["ean_reader", "ean_8_reader", "upc_reader", "code_128_reader"] }
    }, function(err) {
        if (err) { console.log(err); return }
        Quagga.start();
    });
    Quagga.onDetected(function(data) {
        const code = data.codeResult.code;
        window.parent.postMessage({type: 'barcode', value: code}, '*');
        Quagga.stop();
    });
</script>
"""

with st.expander("Open Barcode Camera"):
    st.components.v1.html(scanner_html, height=350)
    st.info("Point camera at barcode. When detected, copy the code into the box above.")

# --- Step 2: Product Processing ---
search_term = barcode_input if barcode_input else st.text_input("Or type product name:")

if search_term:
    with st.spinner("Searching..."):
        # Logic to decide if searching by barcode or name
        if search_term.isdigit():
            product = get_food_by_barcode(search_term)
            results = [product] if product else []
        else:
            search_url = "https://world.openfoodfacts.org/cgi/search.pl"
            params = {"action": "process", "search_terms": search_term, "json": "True", "fields": "product_name,nutriments,brands"}
            res = requests.get(search_url, params=params)
            results = res.json().get("products", []) if res.status_code == 200 else []

    if results and results[0]:
        item = results[0]
        name = item.get('product_name', 'Unknown')
        nutrients = item.get('nutriments', {})
        
        cals_100g = nutrients.get("energy-kcal_100g", 0)
        prot_100g = nutrients.get("proteins_100g", 0)
        carb_100g = nutrients.get("carbohydrates_100g", 0)
        fat_100g = nutrients.get("fat_100g", 0)
        
        st.success(f"Found: {name}")
        weight = st.number_input("Grams eaten:", min_value=1.0, value=100.0)
        
        # Calculations
        c = (cals_100g * weight) / 100
        p = (prot_100g * weight) / 100
        ch = (carb_100g * weight) / 100
        f = (fat_100g * weight) / 100
        
        if st.button("Add to Log"):
            st.session_state.daily_log.append({
                "Food": name, "Weight": weight, "Cals": round(c, 1), 
                "Prot": round(p, 1), "Carb": round(ch, 1), "Fat": round(f, 1)
            })
            st.rerun()
    else:
        st.error("Not found. Try manual entry.")

# --- Step 3: Daily Summary ---
st.markdown("---")
st.header("2. Today's Totals")
if st.session_state.daily_log:
    df = pd.DataFrame(st.session_state.daily_log)
    st.table(df)
    st.metric("Total Calories Today", f"{df['Cals'].sum():.1f} kcal")
    if st.button("Clear Today"):
        st.session_state.daily_log = []
        st.rerun()