import streamlit as st
import pandas as pd
import geopandas as gpd
import plotly.express as px
import glob
import os
import warnings
import difflib
from datetime import datetime, timedelta

# 1. Suppress Warnings
warnings.filterwarnings("ignore")
st.set_page_config(page_title="TRI Risk Decision Support System", layout="wide", page_icon="🛡️")

# ================= CUSTOM CSS =================
st.markdown("""
<style>
    .stApp { background-color: #f8f9fa; }
    div[data-testid="stMetricValue"] { font-size: 24px; color: #333; }
    .explanation-box { background-color: #ffffff; padding: 15px; border-radius: 10px; border-left: 5px solid #007bff; box-shadow: 0 2px 4px rgba(0,0,0,0.1); margin-bottom: 10px; }
</style>
""", unsafe_allow_html=True)

# ================= HELPER FUNCTIONS =================
def clean_label(text):
    return text.replace("_", " ").replace("Pct", "%").replace("Prob", "Risk").title()

def get_indicators(district_name, indicators_df):
    if indicators_df is None: return None
    clean_dist = str(district_name).upper().strip().replace(" ", "")
    indicators_df['MATCH_KEY'] = indicators_df['District'].astype(str).str.upper().str.strip().str.replace(" ", "")
    row = indicators_df[indicators_df['MATCH_KEY'] == clean_dist]
    if not row.empty: return row.iloc[0]
    return None

def generate_enhanced_narrative(row, score, indicators):
    narrative = []
    rain_val = row.get('Precipitation', 0)
    heat_val = row.get('Wet_Bulb', 0)
    
    if rain_val > 64.5:
        narrative.append(f"<div class='explanation-box' style='border-left-color: #dc3545;'><strong>🔥 Severe Hazard (Trigger):</strong><br>Heavy rainfall of <b>{rain_val:.1f} mm</b> detected.</div>")
    elif heat_val > 30:
        narrative.append(f"<div class='explanation-box' style='border-left-color: #fd7e14;'><strong>🔥 Severe Hazard (Trigger):</strong><br>Dangerous Heat Stress (Wet Bulb: <b>{heat_val:.1f}°C</b>).</div>")
    elif score < 30:
        narrative.append(f"<div class='explanation-box' style='border-left-color: #28a745;'><strong>✅ Low Hazard:</strong><br>Normal conditions.</div>")

    if indicators is not None and score > 40:
        kuccha = indicators.get('Kuccha_House_Pct', 0)
        farmers = indicators.get('Agri_Workers_Pct', 0)
        vuln_text = ""
        if kuccha > 30: vuln_text += f"<li><b>{kuccha:.1f}% Kuccha Houses</b>.</li>"
        if farmers > 50: vuln_text += f"<li><b>{farmers:.1f}% Farmer Workforce</b>.</li>"
        if vuln_text: narrative.append(f"<div class='explanation-box' style='border-left-color: #ffc107;'><strong>⚠️ Vulnerability:</strong><ul>{vuln_text}</ul></div>")

    if indicators is not None and score > 60:
        mobile = indicators.get('Mobile_Coverage_Pct', 0)
        irrigation = indicators.get('Irrigation_Coverage_Pct', 0)
        coping_text = ""
        if mobile < 70: coping_text += f"<li><b>Low Mobile Coverage ({mobile:.1f}%)</b>.</li>"
        if irrigation < 30: coping_text += f"<li><b>Low Irrigation ({irrigation:.1f}%)</b>.</li>"
        if coping_text: narrative.append(f"<div class='explanation-box' style='border-left-color: #17a2b8;'><strong>🛡️ Coping Gap:</strong><ul>{coping_text}</ul></div>")
            
    return narrative

# ================= DATA LOADING =================
@st.cache_data
def load_data():
    files = glob.glob("*_DETAILED_PREDICTIONS_FINAL.xlsx")
    data_map = {}
    for f in files:
        state_name = os.path.basename(f).split("_DETAILED")[0].replace("_", " ")
        try:
            xls = pd.ExcelFile(f)
            state_data = {}
            for district in xls.sheet_names:
                df = pd.read_excel(xls, sheet_name=district)
                state_data[district] = df
            data_map[state_name] = state_data
        except: pass
    return data_map

@st.cache_data
def load_indicators():
    if os.path.exists("District_Indicators.xlsx"): return pd.read_excel("District_Indicators.xlsx")
    return None

@st.cache_data
def load_shapefile():
    shp_files = glob.glob("*.shp")
    if shp_files:
        try:
            gdf = gpd.read_file(shp_files[0])
            if gdf.crs is None: gdf.set_crs(epsg=4326, inplace=True)
            elif gdf.crs != "EPSG:4326": gdf = gdf.to_crs(epsg=4326)
            return gdf
        except: return None
    return None

# ================= MAIN APP =================
def main():
    st.title("🛡️ TRI Climate Risk Decision Support System")
    st.markdown("### Integrated Hazard, Vulnerability & Coping Capacity Assessment")
    st.divider()

    # --- SESSION STATE (For Click Interaction) ---
    if 'selected_district_click' not in st.session_state:
        st.session_state.selected_district_click = None

    # --- LOAD DATA ---
    data_map = load_data()
    indicators_df = load_indicators()
    if not data_map:
        st.error("🚨 No '_FINAL.xlsx' files found.")
        st.stop()

    # --- SIDEBAR ---
    st.sidebar.header("📍 Location & Time")
    selected_state = st.sidebar.selectbox("Select State", list(data_map.keys()))
    state_data = data_map[selected_state]
    district_list = list(state_data.keys()) # Excel Districts

    col_y, col_m = st.sidebar.columns(2)
    with col_y: year = st.selectbox("Year", [2026, 2025, 2024], index=0)
    with col_m: month = st.selectbox("Month", range(1, 13), format_func=lambda x: datetime(2000, x, 1).strftime('%B'))
    
    days_in_month = (datetime(year, month % 12 + 1, 1) - timedelta(days=1)).day if month < 12 else 31
    day = st.sidebar.slider("Select Day", 1, days_in_month, 15)
    
    selected_date = datetime(year, month, day)
    target_week = selected_date.isocalendar().week
    st.sidebar.info(f"📅 **Selected:** {selected_date.strftime('%d %b %Y')}\n\n📊 **Week:** {target_week}")

    risk_type = st.sidebar.radio("Visualize Risk:", ["Extreme_Rain_Prob_%", "Heat_Prob_%"], format_func=clean_label)
    clean_risk_name = clean_label(risk_type)

    # --- DATA PREP ---
    map_rows = []
    for dist, df in state_data.items():
        week_row = df[df['Week'] == target_week]
        if not week_row.empty:
            val = week_row.iloc[0].get(risk_type, 0)
            rain_amt = week_row.iloc[0].get('Precipitation', 0)
            map_rows.append({'Excel_District': str(dist), 'Risk Score': float(val), 'Rainfall (mm)': f"{rain_amt:.1f}"})
    risk_df = pd.DataFrame(map_rows)

    # --- LAYOUT ---
    col_map, col_details = st.columns([1.8, 1.2])
    
    with col_map:
        st.subheader(f"🗺️ State Risk Map: {clean_risk_name}")
        gdf = load_shapefile()
        
        if gdf is not None and not risk_df.empty:
            # Match State
            state_col = 'STATE' if 'STATE' in gdf.columns else 'ST_NM'
            map_states = gdf[state_col].unique()
            match = difflib.get_close_matches(selected_state.upper(), [str(x).upper() for x in map_states], n=1)
            
            if match:
                state_gdf = gdf[gdf[state_col].str.upper() == match[0]].copy()
                
                # Find District Column
                dist_col = 'District'
                for candidate in ['District', 'DISTRICT', 'DIST_NAME', 'dtname', 'dist_name']:
                    if candidate in state_gdf.columns:
                        dist_col = candidate
                        break

                # --- 🛠️ MANUAL REPAIR SHOP 🛠️ ---
                # 1. Clean Map Names
                state_gdf['CLEAN_MAP_NAME'] = state_gdf[dist_col].astype(str).str.upper().str.replace("DISTRICT", "").str.replace("DT", "").str.strip()
                
                # 2. Apply Specific Fixes (Map Name -> Correct Name)
                # If the map says "S|T>PUR", we force it to match "SITAPUR"
                MANUAL_FIXES = {
                    "S|T>PUR": "SITAPUR",
                    "CHANDAULI": "CHANDAULI", 
                    "PRATAPGARH": "PRATAPGARH",
                    "KHERI": "LAKHIMPUR KHERI", # Common mismatch
                    "LAKHIMPUR": "LAKHIMPUR KHERI",
                    "RAE BARELI": "RAE BARELI"
                }
                # Apply fixes: If name is in dictionary, replace it. Else keep original.
                state_gdf['CLEAN_MAP_NAME'] = state_gdf['CLEAN_MAP_NAME'].replace(MANUAL_FIXES)
                
                # 3. Fuzzy Match
                risk_df['CLEAN_EXCEL_NAME'] = risk_df['Excel_District'].astype(str).str.upper().str.strip()
                map_names = state_gdf['CLEAN_MAP_NAME'].unique()
                mapping = {}
                
                for excel_name in risk_df['CLEAN_EXCEL_NAME'].unique():
                    # Try Exact Match First (Manual fixes help here)
                    if excel_name in map_names:
                        mapping[excel_name] = excel_name
                    else:
                        # Try
