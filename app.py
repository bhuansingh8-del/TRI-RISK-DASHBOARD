import streamlit as st
import pandas as pd
import geopandas as gpd
import plotly.express as px
import glob
import os
import warnings
import difflib
import folium 
from streamlit_folium import st_folium
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

# ================= HELPER FUNCTIONS (UNCHANGED) =================
def clean_label(text):
    return text.replace("_", " ").replace("Pct", "%").replace("Prob", "Risk").title()

def smart_fix_name(name):
    if not isinstance(name, str): return str(name)
    clean = name.upper().strip()
    replacements = {
        "|": "I", ">": "A", "<": "A", "@": "U", "!": "I", "0": "O",
        "$": "S", "(": "", ")": "", "DISTRICT": "", "DT.": "", "DT": ""
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
    all_keys = indicators_df['MATCH_KEY'].unique()
    matches = difflib.get_close_matches(clean_dist, all_keys, n=1, cutoff=0.7)
    if matches: return indicators_df[indicators_df['MATCH_KEY'] == matches[0]].iloc[0]
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

# ================= NEW HELPERS (FOR JHARKHAND ONLY) =================
@st.cache_data
def load_jharkhand_village_map():
    # Looks for the ZIP file map
    map_path = "data/jharkhand_villages.zip"
    if os.path.exists(map_path):
        try:
            gdf = gpd.read_file(map_path)
            if gdf.crs != "EPSG:4326": gdf = gdf.to_crs("EPSG:4326")
            return gdf
        except: return None
    return None

@st.cache_data
def load_jharkhand_amenities_csv():
    # Looks for the CSV file you uploaded
    csv_path = "data/Final_Dashboard_Data.csv"
    if os.path.exists(csv_path):
        try:
            df = pd.read_csv(csv_path)
            return df
        except: return pd.DataFrame()
    return pd.DataFrame()

# ================= DATA LOADING (UNCHANGED) =================
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
    col_logo, col_title = st.columns([1, 5])
    with col_logo:
        if os.path.exists("TRI-logo.png"): st.image("TRI-logo.png", width=200)
        else: st.markdown("# 🛡️")
    with col_title:
        st.title("TRI Climate Risk Decision Support System")
        st.markdown("### Integrated Hazard, Vulnerability & Coping Capacity Assessment")
    st.divider()

    if 'selected_district_click' not in st.session_state:
        st.session_state.selected_district_click = None

    data_map = load_data()
    indicators_df = load_indicators()
    if not data_map:
        st.error("🚨 No '_FINAL.xlsx' files found.")
        st.stop()

    # --- SIDEBAR ---
    st.sidebar.header("📍 Location & Time")
    selected_state = st.sidebar.selectbox("Select State", list(data_map.keys()))
    state_data = data_map[selected_state]
    district_list = list(state_data.keys()) 

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
            state_col = 'STATE' if 'STATE' in gdf.columns else 'ST_NM'
            map_states = gdf[state_col].unique()
            match = difflib.get_close_matches(selected_state.upper(), [str(x).upper() for x in map_states], n=1)
            
            if match:
                state_gdf = gdf[gdf[state_col].str.upper() == match[0]].copy()
                dist_col = 'District'
                for candidate in ['District', 'DISTRICT', 'DIST_NAME', 'dtname', 'dist_name']:
                    if candidate in state_gdf.columns:
                        dist_col = candidate
                        break

                state_gdf['CLEAN_MAP_NAME'] = state_gdf[dist_col].apply(smart_fix_name)
                UNIVERSAL_FIXES = {
                    "KHERI": "LAKHIMPUR KHERI", "LAKHIMPUR": "LAKHIMPUR KHERI",
                    "BHADOHI": "SANT RAVIDAS NAGAR", "SANT RAVIDAS NAGAR": "BHADOHI",
                    "KUSHI NAGAR": "KUSHINAGAR", "SIDDHARTH NAGAR": "SIDDHARTHNAGAR",
                    "AMROHA": "JYOTIBA PHULE NAGAR", "HATHRAS": "MAHAMAYA NAGAR",
                    "KASGANJ": "KANSHIRAM NAGAR", "SAMBHAL": "BHIM NAGAR",
                    "SHAMLI": "PRABUDDH NAGAR", "HAPUR": "PANCHSHEEL NAGAR",
                    "SHRAWASTI": "SHRAVASTI"
                }
                state_gdf['CLEAN_MAP_NAME'] = state_gdf['CLEAN_MAP_NAME'].replace(UNIVERSAL_FIXES)
                
                risk_df['CLEAN_EXCEL_NAME'] = risk_df['Excel_District'].apply(smart_fix_name)
                risk_df['CLEAN_EXCEL_NAME'] = risk_df['CLEAN_EXCEL_NAME'].replace(UNIVERSAL_FIXES)
                
                map_names = state_gdf['CLEAN_MAP_NAME'].unique()
                mapping = {}
                for excel_name in risk_df['CLEAN_EXCEL_NAME'].unique():
                    if excel_name in map_names: mapping[excel_name] = excel_name
                    else:
                        closest = difflib.get_close_matches(excel_name, map_names, n=1, cutoff=0.7)
                        if closest: mapping[excel_name] = closest[0]
                        else: mapping[excel_name] = None
                
                risk_df['MERGE_KEY'] = risk_df['CLEAN_EXCEL_NAME'].map(mapping)
                merged = state_gdf.merge(risk_df, left_on='CLEAN_MAP_NAME', right_on='MERGE_KEY', how='left')
                merged['Display_Label'] = merged['Excel_District'].fillna(merged['CLEAN_MAP_NAME'])
                merged['Risk Score'] = merged['Risk Score'].fillna(0)
              
                fig = px.choropleth_mapbox(
                    merged, geojson=merged.geometry, locations=merged.index,
                    color='Risk Score', 
                    color_continuous_scale=["#00ff00", "#ffff00", "#ff0000"],
                    range_color=(0, 100),
                    mapbox_style="carto-positron", zoom=5.5,
                    center={"lat": merged.geometry.centroid.y.mean(), "lon": merged.geometry.centroid.x.mean()},
                    hover_name='Display_Label', 
                    hover_data={'Risk Score': True, 'Rainfall (mm)': True}
                )
                fig.update_layout(margin={"r":0,"t":0,"l":0,"b":0}, clickmode='event+select')
                
                event = st.plotly_chart(fig, use_container_width=True, key=f"map_{risk_type}_{selected_state}", on_select="rerun")
                
                if event and "selection" in event and event["selection"]["points"]:
                    point_index = event["selection"]["points"][0]["point_index"]
                    clicked_district = merged.iloc[point_index]['Display_Label']
                    if pd.notna(clicked_district):
                        if clicked_district in district_list:
                            st.session_state.selected_district_click = clicked_district
                        else:
                            match = difflib.get_close_matches(clicked_district.upper(), [d.upper() for d in district_list], n=1)
                            if match:
                                orig = next(d for d in district_list if d.upper() == match[0])
                                st.session_state.selected_district_click = orig
            else:
                st.warning(f"Could not match state '{selected_state}' in shapefile.")

    with col_details:
        st.subheader("🧐 Detailed Risk Diagnostics")
        
        default_index = 0
        if st.session_state.selected_district_click in district_list:
            default_index = district_list.index(st.session_state.selected_district_click)
            
        selected_dist_map = st.selectbox("Select District for Analysis", district_list, index=default_index)
        
        if selected_dist_map:
            d_df = state_data[selected_dist_map]
            row = d_df[d_df['Week'] == target_week]
            
            if not row.empty:
                r = row.iloc[0]
                curr_score = r.get(risk_type, 0)
                indicators = get_indicators(selected_dist_map, indicators_df)
                
                st.metric(label=f"Total {clean_risk_name}", value=f"{curr_score:.1f}%", 
                          delta="Critical" if curr_score > 80 else "Normal", delta_color="inverse")
                st.markdown("---")
                
                st.markdown("### 📝 Impact Analysis")
                narratives = generate_enhanced_narrative(r, curr_score, indicators)
                for n in narratives: st.markdown(n, unsafe_allow_html=True)

                # ========================================================
                # 🛡️ HYBRID LOGIC: JHARKHAND VS OTHERS 🛡️
                # ========================================================
                
                if selected_state == "Jharkhand":
                    # --- JHARKHAND: SHOW MAP AND USE CSV DATA ---
                    st.markdown("---")
                    st.markdown("### 🏘️ Village Amenities Drill-Down")
                    
                    with st.spinner(f"Loading Village Data for {selected_dist_map}..."):
                        villages_gdf = load_jharkhand_village_map()
                        amenities_df = load_jharkhand_amenities_csv() # Using your uploaded CSV
                        
                        if villages_gdf is not None:
                            # Filter Village Map for this district
                            possible_dist_cols = ['District', 'DISTRICT', 'dtname', 'dist_name', 'Name_1']
                            v_dist_col = next((c for c in possible_dist_cols if c in villages_gdf.columns), None)
                            
                            if v_dist_col:
                                v_districts = villages_gdf[v_dist_col].unique()
                                v_match = difflib.get_close_matches(selected_dist_map, v_districts, n=1, cutoff=0.6)
                                
                                if v_match:
                                    local_villages = villages_gdf[villages_gdf[v_dist_col] == v_match[0]]
                                    
                                    # Create Folium Map
                                    centroid = local_villages.geometry.centroid
                                    m = folium.Map(location=[centroid.y.mean(), centroid.x.mean()], zoom_start=10)
                                    
                                    # Identify Village Name Column
                                    v_name_col = next((c for c in ['Name', 'NAME', 'vilname', 'Village'] if c in local_villages.columns), local_villages.columns[0])

                                    # Draw Villages
                                    folium.GeoJson(
                                        local_villages,
                                        name="Villages",
                                        style_function=lambda x: {'fillColor': '#ffaf00', 'color': 'black', 'weight': 0.5, 'fillOpacity': 0.2},
                                        tooltip=folium.GeoJsonTooltip(fields=[v_name_col], aliases=["Village:"]),
                                        highlight_function=lambda x: {'weight': 3, 'color': 'red'}
                                    ).add_to(m)
                                    
                                    # Handle Clicks
                                    map_out = st_folium(m, height=400, width=500)
                                    
                                    if map_out['last_active_drawing']:
                                        props = map_out['last_active_drawing']['properties']
                                        if props and v_name_col in props:
                                            clicked_v = props[v_name_col]
                                            st.info(f"📍 **{clicked_v}**")
                                            
                                            # --- FASTER LOOKUP FROM CSV ---
                                            # We check if this village exists in your amenities CSV
                                            if not amenities_df.empty and 'Village_Name' in amenities_df.columns:
                                                amenity_row = amenities_df[amenities_df['Village_Name'] == clicked_v]
                                                
                                                if not amenity_row.empty:
                                                    h_count = amenity_row.iloc[0]['Hospital_Count']
                                                    p_count = amenity_row.iloc[0]['Pond_Count']
                                                    
                                                    c1, c2 = st.columns(2)
                                                    c1.metric("🏥 Hospitals", h_count)
                                                    c2.metric("💧 Ponds", p_count)
                                                else:
                                                    st.caption("No specific amenity data for this village.")
                                            else:
                                                st.caption("Amenities database not loaded.")
                                    else:
                                        st.caption("👈 Click a village on the map above to see Ponds & Hospitals.")
                                else:
                                    st.warning(f"District map data not found for {selected_dist_map}")
                        else:
                            st.error("Jharkhand Village Map (zip) not found in data/ folder.")

                else:
                    # --- OTHERS (AGRA, ETC): SHOW STANDARD INDICATORS (UNCHANGED) ---
                    if indicators is not None:
                        st.markdown("#### 📊 District Profile")
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
