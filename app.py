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

# ================= CUSTOM CSS (PROFESSIONAL LOOK) =================
st.markdown("""
<style>
    .stApp { background-color: #f8f9fa; }
    div[data-testid="stMetricValue"] { font-size: 24px; color: #333; }
    .risk-critical { color: #d9534f; font-weight: bold; }
    .risk-high { color: #f0ad4e; font-weight: bold; }
    .risk-safe { color: #5cb85c; font-weight: bold; }
    .big-font { font-size: 18px !important; }
</style>
""", unsafe_allow_html=True)

# ================= HELPER FUNCTIONS =================

def clean_label(text):
    """Converts 'Extreme_Rain_Prob_%' to 'Extreme Rain Risk %' for display"""
    return text.replace("_", " ").replace("Pct", "%").replace("Prob", "Risk").title()

def get_risk_color(score):
    if score < 30: return "green"
    if score < 60: return "orange"
    return "red"

def generate_narrative(row, score):
    """Generates the 'Explain what could happen' text."""
    narrative = []
    
    # 1. Hazard Narrative (The Trigger)
    rain_val = row.get('Precipitation', 0)
    heat_val = row.get('Wet_Bulb', 0)
    
    if rain_val > 100:
        narrative.append(f"🌧️ **Severe Hazard:** Heavy rainfall detected ({rain_val:.1f} mm).")
    elif heat_val > 30:
        narrative.append(f"🔥 **Severe Hazard:** Dangerous Heat Stress conditions (Wet Bulb: {heat_val:.1f}°C).")
        
    # 2. Vulnerability Narrative (Why is it bad?)
    # We infer based on the score being high
    vuln_status = row.get('Vulnerability_Status', 'Unknown')
    
    if score > 60:
        if vuln_status == "High":
            narrative.append("🏠 **High Vulnerability:** Risk is amplified by weak housing infrastructure (Kuccha houses) or high agricultural dependence.")
        else:
            narrative.append("⚠️ **Moderate Vulnerability:** Infrastructure is average, but the hazard intensity is driving the risk.")
        
    # 3. Coping Narrative (Can they handle it?)
    coping_status = row.get('Coping_Status', 'Unknown')
    
    if score > 80:
        if coping_status == "Low":
            narrative.append("📡 **Critical Coping Gap:** Warning dissemination is severely limited by poor mobile coverage or lack of shelters.")
        else:
            narrative.append("📢 **Action Required:** Despite decent coping capacity, the hazard is too severe. Immediate mobilization required.")
        
    if not narrative:
        narrative.append("✅ **Status Normal:** No significant risk factors detected for this period.")
        
    return narrative

# ================= DATA LOADING =================
@st.cache_data
def load_data():
    # Load all Final files
    files = glob.glob("*_DETAILED_PREDICTIONS_FINAL.xlsx")
    data_map = {}
    for f in files:
        # Extract State Name (e.g. "ASSAM_DETAILED..." -> "ASSAM")
        state_name = os.path.basename(f).split("_DETAILED")[0].replace("_", " ")
        try:
            # Load all sheets
            xls = pd.ExcelFile(f)
            state_data = {}
            for district in xls.sheet_names:
                df = pd.read_excel(xls, sheet_name=district)
                state_data[district] = df
            data_map[state_name] = state_data
        except:
            pass
    return data_map

@st.cache_data
def load_shapefile():
    shp_files = glob.glob("*.shp")
    if shp_files:
        gdf = gpd.read_file(shp_files[0])
        # Ensure standard coordinate system for web maps
        if gdf.crs != "EPSG:4326":
            gdf = gdf.to_crs(epsg=4326)
        return gdf
    return None

# ================= MAIN APP =================
def main():
    st.title("🛡️ TRI Climate Risk Decision Support System")
    st.markdown("### Integrated Hazard, Vulnerability & Coping Capacity Assessment")
    st.divider()

    # --- 1. LOAD DATA ---
    data_map = load_data()
    if not data_map:
        st.error("🚨 No '_FINAL.xlsx' files found. Please run 'master_processor.py' first.")
        st.stop()

    # --- 2. SIDEBAR CONTROLS ---
    st.sidebar.header("📍 Location & Time")
    
    # State Selector
    selected_state = st.sidebar.selectbox("Select State", list(data_map.keys()))
    state_data = data_map[selected_state]
    district_list = list(state_data.keys())
    
    # Time Selector
    col_y, col_m = st.sidebar.columns(2)
    with col_y:
        year = st.selectbox("Year", [2016, 2017, 2018, 2019, 2020, 2021, 2022, 2023, 2024, 2025, 2026], index=10)
    with col_m:
        month = st.selectbox("Month", range(1, 13), format_func=lambda x: datetime(2000, x, 1).strftime('%B'))
        
    # Day Selector (mapped to Week)
    days_in_month = (datetime(year, month % 12 + 1, 1) - timedelta(days=1)).day if month < 12 else 31
    day = st.sidebar.slider("Select Day", 1, days_in_month, 15)
    
    # Calculate Week Number
    selected_date = datetime(year, month, day)
    target_week = selected_date.isocalendar().week
    
    st.sidebar.info(f"📅 **Selected:** {selected_date.strftime('%d %b %Y')}\n\n📊 **Week Number:** {target_week}")

    # Risk Type Selector (CRITICAL FIX: Matches Excel Column Names)
    risk_type = st.sidebar.radio(
        "Visualize Risk:", 
        ["Extreme_Rain_Prob_%", "Heat_Prob_%"],
        format_func=clean_label
    )
    clean_risk_name = clean_label(risk_type)

    # --- 3. MAP PREPARATION ---
    map_rows = []
    for dist, df in state_data.items():
        # Find row for this week
        week_row = df[df['Week'] == target_week]
        if not week_row.empty:
            # Safe Get: Returns 0 if column is missing, preventing crash
            val = week_row.iloc[0].get(risk_type, 0)
            rain_amt = week_row.iloc[0].get('Precipitation', 0)
            
            map_rows.append({
                'District': str(dist).upper().strip(), # Normalize for matching
                'Risk Score': float(val),
                'Rainfall (mm)': f"{rain_amt:.1f}"
            })
            
    risk_df = pd.DataFrame(map_rows)

    # --- 4. VISUALIZATION: LAYER 1 (THE MAP) ---
    col_map, col_details = st.columns([2, 1])
    
    with col_map:
        st.subheader(f"🗺️ State Risk Map: {clean_risk_name}")
        gdf = load_shapefile()
        
        if gdf is not None and not risk_df.empty:
            # Match State Name (Fuzzy Match)
            map_states = gdf['STATE'].unique()
            match = difflib.get_close_matches(selected_state.upper(), [str(x).upper() for x in map_states], n=1)
            
            if match:
                state_gdf = gdf[gdf['STATE'].str.upper() == match[0]].copy()
                
                # Prepare Merge Keys
                state_gdf['DIST_CLEAN'] = state_gdf['District'].str.upper().str.strip()
                
                # Merge Data
                merged = state_gdf.merge(risk_df, left_on='DIST_CLEAN', right_on='District', how='left')
                merged['Risk Score'] = merged['Risk Score'].fillna(0)
                
                # Plot Map
                fig = px.choropleth_mapbox(
                    merged,
                    geojson=merged.geometry,
                    locations=merged.index,
                    color='Risk Score',
                    color_continuous_scale="RdYlGn_r", # Red=High Risk (Reversed Green-Yellow-Red)
                    range_color=(0, 100),
                    mapbox_style="carto-positron",
                    center={"lat": merged.geometry.centroid.y.mean(), "lon": merged.geometry.centroid.x.mean()},
                    zoom=5.5,
                    hover_name='District',
                    hover_data={'Risk Score': True, 'Rainfall (mm)': True}
                )
                fig.update_layout(margin={"r":0,"t":0,"l":0,"b":0})
                st.plotly_chart(fig, use_container_width=True)
            else:
                st.warning(f"⚠️ Could not match state '{selected_state}' in Shapefile.")
        else:
            st.info("Map data not available (check .shp file) or no risk data for this week.")

    # --- 5. VISUALIZATION: LAYER 2 (DIAGNOSTICS) ---
    with col_details:
        st.subheader("🧐 Risk Diagnostics")
        selected_dist_map = st.selectbox("Select District for Deep Dive", district_list)
        
        if selected_dist_map:
            d_df = state_data[selected_dist_map]
            row = d_df[d_df['Week'] == target_week]
            
            if not row.empty:
                r = row.iloc[0]
                curr_score = r.get(risk_type, 0)
                
                # Score Card
                st.metric(label=f"{clean_risk_name}", value=f"{curr_score:.1f}%", 
                          delta="Critical" if curr_score > 80 else "Normal", delta_color="inverse")
                
                st.markdown("---")
                
                # Narrative Engine
                st.markdown("### 📝 Analysis & Potential Impacts")
                narratives = generate_narrative(r, curr_score)
                for n in narratives:
                    st.write(n)
                
                st.markdown("---")
                
                # Underlying Factors
                st.markdown("#### 🔍 Underlying Factors")
                c1, c2 = st.columns(2)
                with c1:
                    st.write("**Hazard (Weather)**")
                    st.caption(f"Rainfall: {r.get('Precipitation', 0):.1f} mm")
                    st.caption(f"Wet Bulb: {r.get('Wet_Bulb', 0):.1f} °C")
                with c2:
                    st.write("**Socio-Economic**")
                    v_stat = r.get('Vulnerability_Status', 'Unknown')
                    c_stat = r.get('Coping_Status', 'Unknown')
                    st.caption(f"Vulnerability: {v_stat}")
                    st.caption(f"Coping Capacity: {c_stat}")
                        
            else:
                st.warning(f"No data available for Week {target_week}")

    # --- 6. VISUALIZATION: LAYER 3 (TRENDS) ---
    st.markdown("---")
    st.subheader(f"📈 52-Week Risk Trend: {clean_label(selected_dist_map) if selected_dist_map else ''}")
    
    if selected_dist_map:
        trend_df = state_data[selected_dist_map]
        
        # Line Chart
        fig_line = px.line(trend_df, x='Week', y=risk_type, markers=True, 
                          title=f"Annual Risk Profile: {selected_dist_map}")
        
        # Reference Lines
        fig_line.add_hline(y=60, line_dash="dot", annotation_text="High Risk", annotation_position="bottom right")
        fig_line.add_hline(y=80, line_dash="dash", line_color="red", annotation_text="Critical")
        
        st.plotly_chart(fig_line, use_container_width=True)

if __name__ == "__main__":
    main()
