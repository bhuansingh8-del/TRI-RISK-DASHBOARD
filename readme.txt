🛡️ Integrated Climate Risk Decision Support System (IDS-DRR)
Project Overview
This dashboard provides a district-level relative risk ranking for Flood and Heat hazards across 6 Indian states (Assam, Uttar Pradesh, Maharashtra, Jharkhand, Chhattisgarh, and Madhya Pradesh). Unlike standard weather apps, this system follows an integrated risk framework:

Risk = Hazard × Vulnerability / Coping Capacity

How the Model Works
The backend processing engine (master_processor.py) calculates risks by merging two primary data streams:

Dynamic Climate Hazards:

Flood Risk: Based on 10-year historical rainfall signals and IMD thresholds for "Heavy" and "Extreme" precipitation.

Heat Risk: Derived from Wet Bulb Temperature (calculated using Air Temperature and Humidity) to assess actual heat stress on the human body.

Static Socio-Economic Indicators:

Vulnerability: Integrated data from Mission Antyodaya and Census/NFHS on farming dependence and housing types (Kuccha vs. Pucca houses).

Coping Capacity: Assessed based on district-level infrastructure, specifically mobile connectivity and irrigation coverage to determine early warning effectiveness.

Dashboard Features
State-wise Risk Maps: Choropleth maps visualizing the final calculated risk probability (0-100%).

Risk Diagnostics: A deep-dive menu that explains the "Why" behind a district's risk (e.g., whether the risk is driven by weather intensity or infrastructure weakness).

52-Week Trend Analysis: Historical signals identifying which months are most prone to specific disasters based on 10 years of data.

Plain English Narratives: Translates complex data into actionable warnings for decision-makers.

File Structure
app.py: The Streamlit application interface.

master_processor.py: The logic engine that combines climate and vulnerability data.

District_Indicators.xlsx: Compiled district-level indicators from Mission Antyodaya.

*_DETAILED_PREDICTIONS_FINAL.xlsx: The final processed datasets for each state.

requirements.txt: List of Python dependencies for deployment.

Data Sources
Climate Data: 10-year historical daily gridded data (Temperature & Precipitation).

Vulnerability Data: Mission Antyodaya Survey (Govt. of India).

Humidity: Open-Meteo Historical Weather API.