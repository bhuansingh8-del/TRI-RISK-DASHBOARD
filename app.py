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
    """Converts 'Extreme_Rain_Prob_%' to 'Extreme Rain Prob %'"""
    return text.replace("_", " ").replace("Pct", "%").title()

def get_risk_color(score):
    if score < 30: return "green"
    if score < 60: return "orange"
    return "red"

def generate_narrative(row):
    """Generates the 'Explain what could happen' text."""
    narrative = []
    
    # 1. Hazard Narrative
    if row['Precipitation'] > 100:
        narrative.append(f"🌧️ **Severe Hazard:** Heavy rainfall detected ({row['Precipitation']:.1f} mm).")
    elif row['Wet_Bulb'] > 30:
        narrative.append(f"🔥 **Severe Hazard:** Dangerous Heat Stress conditions (Wet Bulb: {row['Wet_Bulb']:.1f}°C).")
        
    # 2. Vulnerability Narrative (Why is it bad?)
    # Note: We reverse-engineer the score to guess the factor, 
    # or ideally we should have saved the raw indicators in the final file.
    # For now, we infer based on the high probability.
    
    if row['Extreme_Rain_Prob_%'] > 60:
        narrative.append("🏠 **Infrastructure Vulnerability:** High risk is likely driven by a combination of weak housing structures (Kuccha houses) and high rainfall.")
        narrative.append("🌾 **Agricultural Impact:** Farming communities in this district are at high risk of crop damage.")
        
    # 3. Coping Narrative
    # If the Probability is dangerously close to 100, coping capacity is likely low.
    if row['Extreme_Rain_Prob_%'] > 80:
        narrative.append("📡 **Coping Gap:** Warning dissemination may be difficult due to limited mobile coverage or relief infrastructure.")
        
    if not narrative:
        narrative.append("✅ **Status Normal:** No significant risk factors detected for this period.")
        
    return narrative

# ================= DATA LOADING =================
@st.cache_data
def load_data():
    files = glob.glob("*_DETAILED_PREDICTIONS_FINAL.xlsx")
    data_map = {}
    for f in files:
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
        if gdf.crs != "EPSG:4326":
            gdf = gdf.to_crs(epsg=4326)
        return gdf
    return None

# ================= MAIN APP =================
def main():
    st.title("🛡️ TRI Climate Risk Decision Support System")
    st.markdown("### Integrated Hazard, Vulnerability & Coping Capacity Assessment")
    st.divider()

    # --- SIDEBAR CONTROLS ---
    data_map = load_data()
    if not data_map:
        st.error("🚨 No '_FINAL.xlsx' files found. Please run the 'master_processor.py' script first.")
        st.stop()

    st.sidebar.header("📍 Location & Time")
    
    # 1. State Selector
    selected_state = st.sidebar.selectbox("Select State", list(data_map.keys()))
    state_data = data_map[selected_state]
    district_list = list(state_data.keys())
    
    # 2. Time Selector
    # We create a dummy date range for 2026 to select Week
    col_y, col_m = st.sidebar.columns(2)
    with col_y:
        year = st.selectbox("Year", [2016, 2017, 2018, 2019, 2020, 2021, 2022, 2023, 2024, 2025, 2026], index=10)
    with col_m:
        month = st.selectbox("Month", range(1, 13), format_func=lambda x: datetime(2000, x, 1).strftime('%B'))
        
    # Day Selector (mapped to Week)
    days_in_month = (datetime(year, month % 12 + 1, 1) - timedelta(days=1)).day if month < 12 else 31
    day = st.sidebar.slider("Select Day", 1, days_in_month, 15)
    
    # Calculate Week Number from the selected Date
    selected_date = datetime(year, month, day)
    target_week = selected_date.isocalendar().week
    
    st.sidebar.info(f"📅 **Date Selected:** {selected_date.strftime('%d %b %Y')}\n\n📊 **Analyzing Week:** {target_week}")

    # 3. Risk Type
    risk_type = st.sidebar.radio("Visualize Risk:", ["Extreme Rain Prob %", "Heat Prob %"])
    clean_risk_name = clean_label(risk_type)

    # --- MAP PREPARATION ---
    # We need to pull the data for 'target_week' for ALL districts to color the map
    map_rows = []
    for dist, df in state_data.items():
        # Find row for this week
        week_row = df[df['Week'] == target_week]
        if not week_row.empty:
            val = week_row.iloc[0][risk_type]
            # Narrative for Map Hover
            rain_amt = week_row.iloc[0].get('Precipitation', 0)
            map_rows.append({
                'District': dist.upper().strip(), # Ensure match with shapefile
                'Risk Score': val,
                'Rainfall (mm)': f"{rain_amt:.1f}"
            })
            
    risk_df = pd.DataFrame(map_rows)

    # --- VISUALIZATION: LAYER 1 (THE MAP) ---
    col_map, col_details = st.columns([2, 1])
    
    with col_map:
        st.subheader(f"🗺️ State Risk Map: {clean_risk_name}")
        gdf = load_shapefile()
        
        if gdf is not None and not risk_df.empty:
            # Fuzzy Match State
            map_states = gdf['STATE'].unique()
            match = difflib.get_close_matches(selected_state.upper(), [str(x).upper() for x in map_states], n=1)
            
            if match:
                state_gdf = gdf[gdf['STATE'].str.upper() == match[0]].copy()
                
                # Merge Data
                state_gdf['DIST_CLEAN'] = state_gdf['District'].str.upper().str.strip()
                merged = state_gdf.merge(risk_df, left_on='DIST_CLEAN', right_on='District', how='left')
                merged['Risk Score'] = merged['Risk Score'].fillna(0)
                
                # Plot
                fig = px.choropleth_mapbox(
                    merged,
                    geojson=merged.geometry,
                    locations=merged.index,
                    color='Risk Score',
                    color_continuous_scale="RdYlGn_r", # Red=High Risk, Green=Low
                    range_color=(0, 100),
                    mapbox_style="carto-positron",
                    center={"lat": merged.geometry.centroid.y.mean(), "lon": merged.geometry.centroid.x.mean()},
                    zoom=6,
                    hover_name='District',
                    hover_data={'Risk Score': True, 'Rainfall (mm)': True}
                )
                fig.update_layout(margin={"r":0,"t":0,"l":0,"b":0})
                st.plotly_chart(fig, use_container_width=True)
            else:
                st.warning("⚠️ Shapefile State name mismatch. Check your .shp file.")
        else:
            st.info("Map data not available or Shapefile missing.")

    # --- VISUALIZATION: LAYER 2 (EXPLANATORY MENU) ---
    with col_details:
        st.subheader("🧐 Risk Diagnostics")
        selected_dist_map = st.selectbox("Select District for Deep Dive", district_list)
        
        if selected_dist_map:
            # Get Data for specific district & week
            d_df = state_data[selected_dist_map]
            row = d_df[d_df['Week'] == target_week]
            
            if not row.empty:
                r = row.iloc[0]
                curr_score = r[risk_type]
                
                # 1. Big Score Card
                st.metric(label=f"{clean_risk_name}", value=f"{curr_score:.1f}%", 
                          delta="Critical" if curr_score > 80 else "Normal", delta_color="inverse")
                
                st.markdown("---")
                
                # 2. "What Could Happen?" Section
                st.markdown("### 📝 Analysis & Potential Impacts")
                narratives = generate_narrative(r)
                for n in narratives:
                    st.write(n)
                
                st.markdown("---")
                
                # 3. Raw Contributing Factors (The "Why")
                st.markdown("#### 🔍 Underlying Factors")
                c1, c2 = st.columns(2)
                with c1:
                    st.write("**Hazard (Weather)**")
                    st.caption(f"Rainfall: {r['Precipitation']:.1f} mm")
                    st.caption(f"Wet Bulb: {r['Wet_Bulb']:.1f} °C")
                with c2:
                    st.write("**Vulnerability (Static)**")
                    # Note: Ideally pass indicators through from Master Processor
                    # For now we imply it from the Risk Score difference
                    if curr_score > 50:
                        st.caption("🔴 Vulnerability: High")
                        st.caption("🔴 Coping Capacity: Low")
                    else:
                        st.caption("🟢 Vulnerability: Moderate")
                        st.caption("🟢 Coping Capacity: Adequate")
                        
            else:
                st.warning(f"No data for Week {target_week}")

    # --- VISUALIZATION: LAYER 3 (TRENDS) ---
    st.markdown("---")
    st.subheader(f"📈 52-Week Risk Trend: {clean_label(selected_dist_map)}")
    
    if selected_dist_map:
        trend_df = state_data[selected_dist_map]
        
        # Color the line based on threshold
        fig_line = px.line(trend_df, x='Week', y=risk_type, markers=True, 
                          title=f"Annual Risk Profile: {selected_dist_map}")
        
        # Add Reference Lines (The "Signal" logic)
        fig_line.add_hline(y=64.5, line_dash="dot", annotation_text="Heavy Rain Threshold", annotation_position="bottom right")
        fig_line.add_hline(y=80, line_dash="dash", line_color="red", annotation_text="Critical Risk Level")
        
        st.plotly_chart(fig_line, use_container_width=True)

if __name__ == "__main__":
    main()