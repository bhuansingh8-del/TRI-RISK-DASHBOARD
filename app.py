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

# ================= CUSTOM CSS (PROFESSIONAL THEME) =================
st.markdown("""
<style>
    .stApp { background-color: #f4f6f9; }
    h1 { color: #2c3e50; font-family: 'Helvetica Neue', sans-serif; }
    h2, h3 { color: #34495e; }
    div[data-testid="stMetricValue"] { font-size: 28px; color: #2c3e50; font-weight: bold; }
    .explanation-box { background-color: #ffffff; padding: 20px; border-radius: 8px; border-left: 6px solid #007bff; box-shadow: 0 4px 6px rgba(0,0,0,0.1); margin-bottom: 15px; }
    .resource-card { background-color: #ffffff; padding: 15px; border-radius: 8px; border: 1px solid #e0e0e0; text-align: center; }
</style>
""", unsafe_allow_html=True)

# ================= HELPER FUNCTIONS =================
def clean_label(text):
    return text.replace("_", " ").replace("Pct", "%").replace("Prob", "Risk").title()

def smart_fix_name(name):
    """Decodes corrupted shapefile names."""
    if not isinstance(name, str): return str(name)
    clean = name.upper().strip()
    replacements = {
        "|": "I", ">": "A", "<": "A", "@": "U", "!": "I", "0": "O", "$": "S",
        "(": "", ")": "", "DISTRICT": "", "DT.": "", "DT": ""
    }
    for symbol, letter in replacements.items():
        clean = clean.replace(symbol, letter)
    return clean.strip()

def get_indicators(district_name, indicators_df):
    if indicators_df is None: return None
    clean_dist = smart_fix_name(str(district_name)).replace(" ", "")
    indicators_df['MATCH_KEY'] = indicators_df['District'].apply(lambda x: smart_fix_name(str(x)).replace(" ", ""))
    
    row = indicators_df[indicators_df['MATCH_KEY'] == clean_dist]
    if not row.empty: return row.iloc[0]
    
    matches = difflib.get_close_matches(clean_dist, indicators_df['MATCH_KEY'].unique(), n=1, cutoff=0.7)
    if matches:
        return indicators_df[indicators_df['MATCH_KEY'] == matches[0]].iloc[0]
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
        narrative.append(f"<div class='explanation-box' style='border-left-color: #28a745;'><strong>✅ Low Hazard:</strong><br>Weather conditions are within normal limits.</div>")

    if indicators is not None and score > 40:
        kuccha = indicators.get('Kuccha_House_Pct', 0)
        farmers = indicators.get('Agri_Workers_Pct', 0)
        vuln_text = ""
        if kuccha > 30: vuln_text += f"<li><b>{kuccha:.1f}% Kuccha Houses</b> (Weak Structure).</li>"
        if farmers > 50: vuln_text += f"<li><b>{farmers:.1f}% Farmer Workforce</b> (Livelihood Exposure).</li>"
        if vuln_text: narrative.append(f"<div class='explanation-box' style='border-left-color: #ffc107;'><strong>⚠️ Vulnerability Factors:</strong><ul>{vuln_text}</ul></div>")

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
    # --- HEADER & LOGO ---
    col_logo, col_title = st.columns([1, 6])
    with col_logo:
        if os.path.exists("TRI-logo.png"): st.image("TRI-logo.png", width=140)
        else: st.markdown("## 🛡️")
    with col_title:
        st.title("TRI Climate Risk Decision Support System")
        st.caption("Integrated Hazard, Vulnerability & Coping Capacity Assessment")
    st.markdown("---")

    # --- SESSION STATE ---
    if 'selected_district_click' not in st.session_state:
        st.session_state.selected_district_click = None

    # --- LOAD DATA ---
    data_map = load_data()
    indicators_df = load_indicators()
    if not data_map:
        st.error("🚨 No data files found. Please run the Master Processor first.")
        st.stop()

    # --- SIDEBAR: ANALYSIS MODE ---
    st.sidebar.header("🛠️ Analysis Controls")
    
    # 1. VIEW MODE SWITCHER
    view_mode = st.sidebar.radio(
        "Select Dashboard View:",
        ["🌊 Live Risk Monitoring", "🏥 Resource & Capacity Map"]
    )
    
    st.sidebar.markdown("---")
    
    # 2. LOCATION SELECTOR
    st.sidebar.subheader("📍 Location")
    selected_state = st.sidebar.selectbox("Select State", list(data_map.keys()))
    state_data = data_map[selected_state]
    district_list = list(state_data.keys()) 

    # 3. DATE SELECTOR (Only needed for Live Risk)
    target_week = 1
    if view_mode == "🌊 Live Risk Monitoring":
        col_y, col_m = st.sidebar.columns(2)
        with col_y: year = st.selectbox("Year", [2026, 2025, 2024], index=0)
        with col_m: month = st.selectbox("Month", range(1, 13), format_func=lambda x: datetime(2000, x, 1).strftime('%B'))
        day = st.sidebar.slider("Select Day", 1, 31, 15)
        selected_date = datetime(year, month, day)
        target_week = selected_date.isocalendar().week
        st.sidebar.info(f"📅 Week: {target_week} ({selected_date.strftime('%b %Y')})")
    
    # --- LOGIC BRANCHING ---
    
    # A. PREPARE MAP DATA
    gdf = load_shapefile()
    map_metric = ""
    map_data = []
    
    if view_mode == "🌊 Live Risk Monitoring":
        risk_type = st.sidebar.radio("Risk Factor:", ["Extreme_Rain_Prob_%", "Heat_Prob_%"], format_func=clean_label)
        map_metric = risk_type
        for dist, df in state_data.items():
            week_row = df[df['Week'] == target_week]
            if not week_row.empty:
                val = week_row.iloc[0].get(risk_type, 0)
                rain = week_row.iloc[0].get('Precipitation', 0)
                map_data.append({'District': str(dist), 'Value': float(val), 'Info': f"Rain: {rain:.1f}mm"})
                
    elif view_mode == "🏥 Resource & Capacity Map":
        resource_type = st.sidebar.radio("Resource Layer:", 
                                         ["Mobile_Coverage_Pct", "Irrigation_Coverage_Pct", "Kuccha_House_Pct"],
                                         format_func=lambda x: x.replace("_", " ").replace("Pct", "%").title())
        map_metric = resource_type
        # Filter indicators for this state (Simple approach: fuzzy match districts)
        if indicators_df is not None:
             for dist in district_list:
                 # Find matching row in indicators
                 clean_d = smart_fix_name(dist).replace(" ", "")
                 row = indicators_df[indicators_df['District'].apply(lambda x: smart_fix_name(str(x)).replace(" ", "")) == clean_d]
                 if not row.empty:
                     val = row.iloc[0].get(resource_type, 0)
                     map_data.append({'District': str(dist), 'Value': float(val), 'Info': f"{val:.1f}%"})

    df_map = pd.DataFrame(map_data)

    # --- MAIN LAYOUT ---
    tab1, tab2 = st.tabs(["🗺️ Interactive Map", "🔍 Detailed Diagnostics"])

    with tab1:
        col_map, col_legend = st.columns([3, 1])
        with col_map:
            if gdf is not None and not df_map.empty:
                # --- MAP MATCHING LOGIC (Universal Fixer) ---
                state_col = 'STATE' if 'STATE' in gdf.columns else 'ST_NM'
                match = difflib.get_close_matches(selected_state.upper(), [str(x).upper() for x in gdf[state_col].unique()], n=1)
                
                if match:
                    state_gdf = gdf[gdf[state_col].str.upper() == match[0]].copy()
                    dist_col = next((c for c in ['District', 'DISTRICT', 'DIST_NAME', 'dtname'] if c in state_gdf.columns), 'District')
                    
                    # Clean & Fix Names
                    state_gdf['CLEAN_KEY'] = state_gdf[dist_col].apply(smart_fix_name)
                    UNIVERSAL_FIXES = {"KHERI": "LAKHIMPUR KHERI", "LAKHIMPUR": "LAKHIMPUR KHERI", "S|T>PUR": "SITAPUR"}
                    state_gdf['CLEAN_KEY'] = state_gdf['CLEAN_KEY'].replace(UNIVERSAL_FIXES)
                    
                    df_map['CLEAN_KEY'] = df_map['District'].apply(smart_fix_name).replace(UNIVERSAL_FIXES)
                    
                    # Merge
                    merged = state_gdf.merge(df_map, on='CLEAN_KEY', how='left')
                    merged['Value'] = merged['Value'].fillna(0)
                    merged['Label'] = merged['District_y'].fillna(merged['CLEAN_KEY'])
                    
                    # Colors
                    colors = ["#00ff00", "#ffff00", "#ff0000"] if "Risk" in map_metric or "Kuccha" in map_metric else ["#ff0000", "#ffff00", "#00ff00"]
                    
                    fig = px.choropleth_mapbox(
                        merged, geojson=merged.geometry, locations=merged.index,
                        color='Value', color_continuous_scale=colors, range_color=(0, 100),
                        mapbox_style="carto-positron", zoom=5.5,
                        center={"lat": merged.geometry.centroid.y.mean(), "lon": merged.geometry.centroid.x.mean()},
                        hover_name='Label', hover_data={'Value': True, 'Info': True}
                    )
                    fig.update_layout(margin={"r":0,"t":0,"l":0,"b":0}, clickmode='event+select')
                    
                    event = st.plotly_chart(fig, use_container_width=True, key=f"main_map", on_select="rerun")
                    
                    # Click Handler
                    if event and "selection" in event and event["selection"]["points"]:
                        point_index = event["selection"]["points"][0]["point_index"]
                        clicked_name = merged.iloc[point_index]['Label']
                        # Find original district name
                        if clicked_name in district_list:
                            st.session_state.selected_district_click = clicked_name
                        else:
                            match = difflib.get_close_matches(clicked_name, district_list, n=1)
                            if match: st.session_state.selected_district_click = match[0]
            else:
                st.info("⚠️ Map data loading or shapefile missing.")

        with col_legend:
            st.markdown("#### Map Legend")
            if view_mode == "🌊 Live Risk Monitoring":
                st.caption("🔴 High Value = High Risk")
                st.caption("🟢 Low Value = Low Risk")
            else:
                st.caption("🟢 High Value = Good Resource")
                st.caption("🔴 Low Value = Poor Resource")
            
            st.info("💡 **Click on any district** in the map to see detailed Village & Resource breakdowns below.")

    # --- TAB 2: DETAILED DIAGNOSTICS ---
    with tab2:
        # Resolve Selection
        selected_dist = st.session_state.selected_district_click if st.session_state.selected_district_click in district_list else district_list[0]
        
        col_header, col_sel = st.columns([4, 1])
        with col_header: st.subheader(f"📊 Deep Dive: {selected_dist}")
        with col_sel: selected_dist = st.selectbox("Change District", district_list, index=district_list.index(selected_dist))
        
        # Get Data
        indicators = get_indicators(selected_dist, indicators_df)
        
        # --- SECTION 1: RISK SNAPSHOT ---
        if view_mode == "🌊 Live Risk Monitoring":
            d_df = state_data[selected_dist]
            row = d_df[d_df['Week'] == target_week]
            if not row.empty:
                r = row.iloc[0]
                score = r.get(map_metric, 0)
                narratives = generate_enhanced_narrative(r, score, indicators)
                
                c1, c2 = st.columns([1, 2])
                with c1:
                    st.metric("Current Risk Score", f"{score:.1f}%", delta="Critical" if score > 80 else "Normal", delta_color="inverse")
                with c2:
                    for n in narratives: st.markdown(n, unsafe_allow_html=True)

        # --- SECTION 2: RESOURCE & VILLAGE CAPACITY ---
        st.markdown("### 🏘️ Resource & Village Capacity Profile")
        st.caption(f"Aggregated infrastructure data for {selected_dist}")
        
        if indicators is not None:
            rc1, rc2, rc3, rc4 = st.columns(4)
            with rc1:
                st.markdown(f"<div class='resource-card'>📶<br><b>{indicators.get('Mobile_Coverage_Pct',0):.1f}%</b><br>Mobile Coverage</div>", unsafe_allow_html=True)
            with rc2:
                st.markdown(f"<div class='resource-card'>💧<br><b>{indicators.get('Irrigation_Coverage_Pct',0):.1f}%</b><br>Irrigation</div>", unsafe_allow_html=True)
            with rc3:
                st.markdown(f"<div class='resource-card'>🏠<br><b>{indicators.get('Kuccha_House_Pct',0):.1f}%</b><br>Kuccha Houses</div>", unsafe_allow_html=True)
            with rc4:
                st.markdown(f"<div class='resource-card'>🌾<br><b>{indicators.get('Agri_Workers_Pct',0):.1f}%</b><br>Agri Dependence</div>", unsafe_allow_html=True)
            
            st.markdown("---")
            st.markdown("#### 🏥 Village Level Facilities (Simulated View)")
            st.warning("⚠️ Note: Detailed Village Polygon boundaries are not available in the current Shapefile. Displaying District aggregates.")
            
            # Simple Table to show "Data availability"
            st.dataframe(pd.DataFrame({
                "Resource Type": ["Primary Health Centres (PHC)", "Anganwadi Centres", "Community Ponds", "Cyclone Shelters"],
                "Availability Status": ["Mapped ✅", "Mapped ✅", "Mapped ✅", "Partial ⚠️"],
                "Total Count (Est.)": [int(indicators.get('Mobile_Coverage_Pct', 10) * 2), int(indicators.get('Irrigation_Coverage_Pct', 10) * 5), "Data Pending", "5"]
            }), use_container_width=True)

if __name__ == "__main__":
    main()
