import streamlit as st
import pandas as pd
import requests
from streamlit.components.v1 import html

# --- Function: Fetch Data from Open Food Facts ---
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

# --- Session State Management ---
if 'daily_log' not in st.session_state:
    st.session_state.daily_log = []
if 'scanned_barcode' not in st.session_state:
    st.session_state.scanned_barcode = None

st.set_page_config(page_title="Auto-Barcode Tracker", page_icon="🚀")
st.title("Auto-Scan Nutrition Tracker")

# --- 1. The Automatic Barcode Scanner ---
st.header("Step 1: Scan Product")

# Custom JS Scanner that sends data back to Streamlit
scanner_code = """
<div id="scanner-container" style="width: 100%; height: 300px; border: 2px solid #ff4b4b; border-radius: 10px; overflow: hidden;"></div>
<script src="https://cdnjs.cloudflare.com/ajax/libs/quagga/0.12.1/quagga.min.js"></script>
<script>
    const streamlitDoc = window.parent.document;
    
    Quagga.init({
        inputStream : { name : "Live", type : "LiveStream", target: document.querySelector('#scanner-container'), constraints: { facingMode: "environment" } },
        decoder : { readers : ["ean_reader", "ean_8_reader", "upc_reader", "code_128_reader"] }
    }, function(err) {
        if (err) { console.error(err); return; }
        Quagga.start();
    });

    Quagga.onDetected(function(data) {
        const code = data.codeResult.code;
        // Sending the code to Streamlit hidden input
        const input = streamlitDoc.querySelector('input[aria-label="barcode_hidden"]');
        if (input) {
            input.value = code;
            input.dispatchEvent(new Event('input', { bubbles: true }));
            Quagga.stop();
        }
    });
</script>
"""

# Hidden input to receive JS data
barcode_val = st.text_input("barcode_hidden", key="barcode_hidden", label_visibility="collapsed")

with st.expander("📸 Open Camera Scanner", expanded=True):
    html(scanner_code, height=320)
    st.caption("Point at barcode. It will auto-fill the search below.")

# Manual search or Auto-filled from scanner
search_input = st.text_input("Detected Barcode / Search Name:", value=barcode_val)

# --- 2. Preview & Calculation ---
if search_input:
    with st.spinner("Fetching product data..."):
        if search_input.isdigit():
            product = get_food_by_barcode(search_input)
        else:
            # Fallback to text search if not a number
            search_url = "https://world.openfoodfacts.org/cgi/search.pl"
            params = {"action": "process", "search_terms": search_input, "json": "True", "fields": "product_name,nutriments,brands"}
            res = requests.get(search_url, params=params)
            products = res.json().get("products", [])
            product = products[0] if products else None

    if product:
        name = product.get('product_name', 'Unknown')
        brand = product.get('brands', 'Unknown Brand')
        nutrients = product.get('nutriments', {})
        
        # Values per 100g
        c100 = nutrients.get("energy-kcal_100g", 0)
        p100 = nutrients.get("proteins_100g", 0)
        ch100 = nutrients.get("carbohydrates_100g", 0)
        f100 = nutrients.get("fat_100g", 0)
        
        st.markdown(f"### 🔍 Preview: {name}")
        st.write(f"**Brand:** {brand} | **Per 100g:** {c100}kcal, P:{p100}g, C:{ch100}g, F:{f100}g")
        
        # Input Weight
        weight = st.number_input("Enter grams consumed:", min_value=1.0, value=100.0, step=1.0)
        
        # Calculate current portion
        cur_c = (c100 * weight) / 100
        cur_p = (p100 * weight) / 100
        cur_ch = (ch100 * weight) / 100
        cur_f = (f100 * weight) / 100
        
        st.info(f"**Portion Values:** {cur_c:.1f} kcal | P: {cur_p:.1f}g | C: {cur_ch:.1f}g | F: {cur_f:.1f}g")
        
        if st.button("Add to Daily Log ➕"):
            st.session_state.daily_log.append({
                "Food": name, "Weight": weight, "Cals": round(cur_c, 1), 
                "Prot": round(cur_p, 1), "Carb": round(cur_ch, 1), "Fat": round(cur_f, 1)
            })
            st.success(f"Added {name} to your log!")
    else:
        st.error("Product not found. Please try manual search or another barcode.")

# --- 3. Daily Summary ---
st.markdown("---")
st.header("Today's Summary")

if st.session_state.daily_log:
    df = pd.DataFrame(st.session_state.daily_log)
    st.table(df)
    
    total_c = df["Cals"].sum()
    total_p = df["Prot"].sum()
    
    c1, c2 = st.columns(2)
    c1.metric("Total Calories", f"{total_c:.1f} kcal")
    c2.metric("Total Protein", f"{total_p:.1f} g")
    
    if st.button("Reset Day"):
        st.session_state.daily_log = []
        st.rerun()