import streamlit as st
import pandas as pd
import geopandas as gpd
import plotly.express as px
import glob
import os
import warnings
import difflib
from datetime import datetime, timedelta

# 1. Suppress Warnings for cleaner output
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
    """Converts 'Extreme_Rain_Prob_%' to 'Extreme Rain Risk %'"""
    return text.replace("_", " ").replace("Pct", "%").replace("Prob", "Risk").title()

def get_indicators(district_name, indicators_df):
    """Fetches the static vulnerability data for a specific district."""
    if indicators_df is None: return None
    
    # Normalize names for matching (remove spaces, uppercase)
    clean_dist = str(district_name).upper().strip().replace(" ", "")
    # Create a match key in the dataframe on the fly
    indicators_df['MATCH_KEY'] = indicators_df['District'].astype(str).str.upper().str.strip().str.replace(" ", "")
    
    row = indicators_df[indicators_df['MATCH_KEY'] == clean_dist]
    if not row.empty:
        return row.iloc[0]
    return None

def generate_enhanced_narrative(row, score, indicators):
    """Generates the 'Why is this happening?' text."""
    narrative = []
    
    # --- 1. HAZARD ANALYSIS (The Trigger) ---
    rain_val = row.get('Precipitation', 0)
    heat_val = row.get('Wet_Bulb', 0)
    
    if rain_val > 64.5:
        narrative.append(f"""
        <div class='explanation-box' style='border-left-color: #dc3545;'>
            <strong>🔥 Severe Hazard (Trigger):</strong><br>
            Heavy rainfall of <b>{rain_val:.1f} mm</b> detected this week. 
            This exceeds the heavy flood threshold (64.5mm).
        </div>
        """)
    elif heat_val > 30:
        narrative.append(f"""
        <div class='explanation-box' style='border-left-color: #fd7e14;'>
            <strong>🔥 Severe Hazard (Trigger):</strong><br>
            Dangerous Heat Stress (Wet Bulb: <b>{heat_val:.1f}°C</b>). 
            Human body cooling mechanisms are compromised at this level.
        </div>
        """)
    elif score < 30:
        narrative.append(f"""
        <div class='explanation-box' style='border-left-color: #28a745;'>
            <strong>✅ Low Hazard:</strong><br>
            Weather conditions are within normal limits.
        </div>
        """)

    # --- 2. VULNERABILITY ANALYSIS (The Multiplier) ---
    if indicators is not None and score > 40:
        kuccha = indicators.get('Kuccha_House_Pct', 0)
        farmers = indicators.get('Agri_Workers_Pct', 0)
        
        vuln_text = ""
        if kuccha > 30:
            vuln_text += f"<li><b>{kuccha:.1f}% of houses are Kuccha</b> (weak structure).</li>"
        if farmers > 50:
            vuln_text += f"<li><b>{farmers:.1f}% of the workforce are farmers</b> (livelihood exposure).</li>"
            
        if vuln_text:
            narrative.append(f"""
            <div class='explanation-box' style='border-left-color: #ffc107;'>
                <strong>⚠️ Vulnerability Factors:</strong><br>
                Risk is amplified by local conditions:
                <ul>{vuln_text}</ul>
            </div>
            """)

    # --- 3. COPING CAPACITY (The Defense) ---
    if indicators is not None and score > 60:
        mobile = indicators.get('Mobile_Coverage_Pct', 0)
        irrigation = indicators.get('Irrigation_Coverage_Pct', 0)
        
        coping_text = ""
        if mobile < 70:
            coping_text += f"<li><b>Low Mobile Coverage ({mobile:.1f}%)</b> limits early warning reach.</li>"
        if irrigation < 30 and heat_val > 28:
            coping_text += f"<li><b>Low Irrigation ({irrigation:.1f}%)</b> increases crop heat stress.</li>"
            
        if coping_text:
            narrative.append(f"""
            <div class='explanation-box' style='border-left-color: #17a2b8;'>
                <strong>🛡️ Coping Gap:</strong><br>
                Response capacity is limited:
                <ul>{coping_text}</ul>
            </div>
            """)
            
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
        except:
            pass
    return data_map

@st.cache_data
def load_indicators():
    if os.path.exists("District_Indicators.xlsx"):
        return pd.read_excel("District_Indicators.xlsx")
    return None

@st.cache_data
def load_shapefile():
    shp_files = glob.glob("*.shp")
    if shp_files:
        try:
            gdf = gpd.read_file(shp_files[0])
            # Fix Missing Projection (The .prj error)
            if gdf.crs is None:
                gdf.set_crs(epsg=4326, inplace=True)
            elif gdf.crs != "EPSG:4326":
                gdf = gdf.to_crs(epsg=4326)
            return gdf
        except:
            return None
    return None

# ================= MAIN APP =================
def main():
    st.title("🛡️ TRI Climate Risk Decision Support System")
    st.markdown("### Integrated Hazard, Vulnerability & Coping Capacity Assessment")
    st.divider()

    # --- LOAD DATA ---
    data_map = load_data()
    indicators_df = load_indicators()
    
    if not data_map:
        st.error("🚨 No '_FINAL.xlsx' files found. Please run 'master_processor.py' first.")
        st.stop()

    # --- SIDEBAR ---
    st.sidebar.header("📍 Location & Time")
    selected_state = st.sidebar.selectbox("Select State", list(data_map.keys()))
    state_data = data_map[selected_state]
    district_list = list(state_data.keys())
    
    col_y, col_m = st.sidebar.columns(2)
    with col_y:
        year = st.selectbox("Year", [2016, 2017, 2018, 2019, 2020, 2021, 2022, 2023, 2024, 2025, 2026], index=10)
    with col_m:
        month = st.selectbox("Month", range(1, 13), format_func=lambda x: datetime(2000, x, 1).strftime('%B'))
    
    days_in_month = (datetime(year, month % 12 + 1, 1) - timedelta(days=1)).day if month < 12 else 31
    day = st.sidebar.slider("Select Day", 1, days_in_month, 15)
    
    selected_date = datetime(year, month, day)
    target_week = selected_date.isocalendar().week
    
    st.sidebar.info(f"📅 **Selected:** {selected_date.strftime('%d %b %Y')}\n\n📊 **Week:** {target_week}")

    risk_type = st.sidebar.radio(
        "Visualize Risk:", 
        ["Extreme_Rain_Prob_%", "Heat_Prob_%"],
        format_func=clean_label
    )
    clean_risk_name = clean_label(risk_type)

    # --- MAP PREPARATION ---
    map_rows = []
    for dist, df in state_data.items():
        week_row = df[df['Week'] == target_week]
        if not week_row.empty:
            val = week_row.iloc[0].get(risk_type, 0)
            rain_amt = week_row.iloc[0].get('Precipitation', 0)
            map_rows.append({
                'District': str(dist).upper().strip(),
                'Risk Score': float(val),
                'Rainfall (mm)': f"{rain_amt:.1f}"
            })
    risk_df = pd.DataFrame(map_rows)

    # --- LAYOUT ---
    col_map, col_details = st.columns([1.8, 1.2])
    
    with col_map:
        st.subheader(f"🗺️ State Risk Map: {clean_risk_name}")
        gdf = load_shapefile()
        
        if gdf is not None and not risk_df.empty:
            # 1. Match State (Fuzzy Logic)
            state_col = 'STATE' if 'STATE' in gdf.columns else 'ST_NM'
            map_states = gdf[state_col].unique()
            match = difflib.get_close_matches(selected_state.upper(), [str(x).upper() for x in map_states], n=1)
            
            if match:
                state_gdf = gdf[gdf[state_col].str.upper() == match[0]].copy()
                
                # 2. Find District Column
                dist_col = 'District'
                for candidate in ['District', 'DISTRICT', 'DIST_NAME', 'dtname', 'dist_name']:
                    if candidate in state_gdf.columns:
                        dist_col = candidate
                        break

                # 3. Clean Keys & Merge
                state_gdf['MATCH_KEY'] = state_gdf[dist_col].astype(str).str.upper().str.strip()
                risk_df['MATCH_KEY'] = risk_df['District'].astype(str).str.upper().str.strip()
                
                merged = state_gdf.merge(risk_df, on='MATCH_KEY', how='left')
                merged['Risk Score'] = merged['Risk Score'].fillna(0) # 0 = Safe (Green)
                
                # 4. Set Label for Hover
                if dist_col in merged.columns:
                    merged['District_Label'] = merged[dist_col]
                else:
                    merged['District_Label'] = merged['MATCH_KEY']

                # 5. Plot Map (With Fixed Colors)
                fig = px.choropleth_mapbox(
                    merged, geojson=merged.geometry, locations=merged.index,
                    color='Risk Score', 
                    color_continuous_scale=["#00ff00", "#ffff00", "#ff0000"], # Green -> Yellow -> Red
                    range_color=(0, 100),
                    mapbox_style="carto-positron", zoom=5.5,
                    center={"lat": merged.geometry.centroid.y.mean(), "lon": merged.geometry.centroid.x.mean()},
                    hover_name='District_Label', 
                    hover_data={'Risk Score': True, 'Rainfall (mm)': True}
                )
                fig.update_layout(margin={"r":0,"t":0,"l":0,"b":0})
                
                # Force Redraw on Change
                st.plotly_chart(fig, use_container_width=True, key=f"map_{risk_type}_{selected_state}")
            else:
                st.warning(f"Could not match state '{selected_state}' in shapefile.")
        else:
            st.info("Map data loading...")

    with col_details:
        st.subheader("🧐 Detailed Risk Diagnostics")
        selected_dist_map = st.selectbox("Select District for Analysis", district_list)
        
        if selected_dist_map:
            d_df = state_data[selected_dist_map]
            row = d_df[d_df['Week'] == target_week]
            
            if not row.empty:
                r = row.iloc[0]
                curr_score = r.get(risk_type, 0)
                indicators = get_indicators(selected_dist_map, indicators_df)
                
                # Score Card
                st.metric(label=f"Total {clean_risk_name}", value=f"{curr_score:.1f}%", 
                          delta="Critical" if curr_score > 80 else "Normal", delta_color="inverse")
                st.markdown("---")
                
                # Narrative
                st.markdown("### 📝 Impact Analysis")
                narratives = generate_enhanced_narrative(r, curr_score, indicators)
                for n in narratives:
                    st.markdown(n, unsafe_allow_html=True)
                
                # Raw Data
                if indicators is not None:
                    st.markdown("#### 📊 District Profile (Original Data)")
                    i_col1, i_col2 = st.columns(2)
                    with i_col1:
                        st.caption("Kuccha Houses")
                        st.write(f"**{indicators.get('Kuccha_House_Pct', 0):.1f}%**")
                        st.caption("Farming Workforce")
                        st.write(f"**{indicators.get('Agri_Workers_Pct', 0):.1f}%**")
                    with i_col2:
                        st.caption("Mobile Coverage")
                        st.write(f"**{indicators.get('Mobile_Coverage_Pct', 0):.1f}%**")
                        st.caption("Irrigation")
                        st.write(f"**{indicators.get('Irrigation_Coverage_Pct', 0):.1f}%**")

    # --- TRENDS ---
    st.markdown("---")
    st.subheader(f"📈 52-Week Risk Trend: {clean_label(selected_dist_map) if selected_dist_map else ''}")
    if selected_dist_map:
        trend_df = state_data[selected_dist_map]
        fig_line = px.line(trend_df, x='Week', y=risk_type, markers=True, title=f"Annual Risk Profile: {selected_dist_map}")
        fig_line.add_hline(y=60, line_dash="dot", annotation_text="High Risk")
        fig_line.add_hline(y=80, line_dash="dash", line_color="red", annotation_text="Critical")
        st.plotly_chart(fig_line, use_container_width=True)

if __name__ == "__main__":
    main()
