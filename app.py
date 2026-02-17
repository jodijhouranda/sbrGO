import streamlit as st
import pandas as pd
from scraper import GoogleMapsScraper
import io
import requests
import os
import asyncio
import sys
import time
from streamlit_js_eval import streamlit_js_eval
import folium
from streamlit_folium import st_folium
from sqlalchemy import create_engine

# Fix for Windows asyncio loop policy
if sys.platform == 'win32':
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

@st.cache_resource
def install_playwright():
    """Install Playwright browsers silently."""
    try:
        # Only install chromium to save time/space
        os.system("playwright install chromium")
    except:
        pass

# Ensure browsers are installed
install_playwright()

def get_location_description(lat, lng):
    """Get a human-readable address from lat/lng using Reverse Geocoding with full Indo admin levels."""
    try:
        url = f"https://nominatim.openstreetmap.org/reverse?format=json&lat={lat}&lon={lng}&zoom=18&addressdetails=1"
        headers = {'User-Agent': 'NoSBRGo/1.2'}
        response = requests.get(url, headers=headers, timeout=10)
        if response.status_code == 200:
            data = response.json()
            addr = data.get('address', {})
            
            # Very comprehensive parsing for Indonesian administrative divisions
            road = addr.get('road') or addr.get('street')
            village = addr.get('village') or addr.get('hamlet') or addr.get('village_district')
            suburb = addr.get('suburb') or addr.get('neighbourhood') or addr.get('quarter')
            kecamatan = addr.get('city_district') or addr.get('district') or addr.get('municipality')
            kota_kab = addr.get('city') or addr.get('town') or addr.get('county')
            
            # Filter duplicates and build parts
            all_parts = [road, village, suburb, kecamatan, kota_kab]
            unique_parts = []
            for p in all_parts:
                if p and p not in unique_parts:
                    unique_parts.append(str(p))
            
            return ", ".join(unique_parts) if unique_parts else data.get('display_name')
        return None
    except:
        return None

def create_wa_link(phone_number):
    """Generate a clean WhatsApp link."""
    if not phone_number or pd.isna(phone_number):
        return None
    # Remove non-digits
    clean_num = ''.join(filter(str.isdigit, str(phone_number)))
    # Indonesian context: if starts with 0, change to 62
    if clean_num.startswith('0'):
        final_num = '62' + clean_num[1:]
    else:
        final_num = clean_num
        
    import urllib.parse
    msg = "Halo, saya menghubungi Anda melalui informasi dari NoSBRGo (BPS Kalimantan Barat)."
    encoded_msg = urllib.parse.quote(msg)
    return f"https://wa.me/{final_num}?text={encoded_msg}"

def save_to_tidb(df):
    """Save the dataframe to TiDB table 'scraped_results'."""
    if df is None or df.empty:
        st.warning("No data to save.")
        return
    
    try:
        conn = st.connection('tidb', type='sql')
    except Exception as e:
        st.error(f"Database connection error: {e}")
        return

    try:
        with st.status("Saving data to TiDB...", expanded=False) as status:
            # Add a timestamp column
            df_to_save = df.copy()
            df_to_save['scraped_at'] = pd.Timestamp.now()
            
            # Save to table 'scraped_results'
            # if_exists='append' to add to existing data
            df_to_save.to_sql('scraped_results', con=conn.engine, if_exists='append', index=False)
            status.update(label="✅ Data successfully saved to TiDB!", state="complete")
        st.success(f"Successfully saved {len(df)} records to TiDB.")
    except Exception as e:
        st.error(f"Error saving to database: {e}")
        with st.expander("Show detailed error"):
            st.code(str(e))

def show_scraper_page():
    # Premium UI Styling
    st.markdown("""
    <style>
        @import url('https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;600&display=swap');
        
        html, body, [data-testid="stStandardType"] {
            font-family: 'Outfit', sans-serif;
        }
        
        .stApp {
            background: radial-gradient(circle at top right, #f8f9ff 0%, #ffffff 100%);
        }
        
        /* Global Title Styling */
        .main-title {
            font-size: 3rem !important;
            font-weight: 800;
            margin-bottom: 0px;
            letter-spacing: normal !important; 
            line-height: 1.1 !important;
            text-shadow: 0 10px 30px rgba(99, 102, 241, 0.1);
            white-space: nowrap;
        }
        
        .title-no { color: #6366f1; }
        .title-sbr { color: #1e293b; }
        .title-go { color: #a855f7; }
        
        .logo-container {
            display: flex;
            align-items: center;
            width: 100%;
            margin-top: -30px;
            margin-bottom: 15px;
            padding-top: 1.5rem;
            overflow: visible !important;
        }
        
        .subtitle {
            color: #94a3b8;
            font-size: 0.65rem !important;
            font-weight: 500;
            text-transform: uppercase;
            letter-spacing: 1px;
            margin-top: -10px;
            margin-bottom: 3rem;
            opacity: 0.6;
        }
        
        /* Card-like containers */
        div[data-testid="stMetric"] {
            background: rgba(255, 255, 255, 0.7);
            backdrop-filter: blur(10px);
            border: 1px solid rgba(255, 255, 255, 0.3);
            border-radius: 12px;
            padding: 1rem;
        }
        
        /* Button Styling */
        .stButton > button {
            background: linear-gradient(90deg, #6366f1 0%, #a855f7 100%);
            color: white !important;
            border: none;
            padding: 0.6rem 2rem;
            border-radius: 8px;
            font-weight: 600;
            transition: all 0.3s ease;
            box-shadow: 0 4px 15px rgba(99, 102, 241, 0.2);
        }
    </style>
    """, unsafe_allow_html=True)

    # --- Header Navigation Row ---
    st.markdown(f"""
        <div class="logo-container">
            <h1 class="main-title">
                <span class="title-no">No</span><span class="title-sbr">SBR</span><span class="title-go">Go</span>
            </h1>
        </div>
    """, unsafe_allow_html=True)
    st.markdown('<p class="subtitle">Google Maps Business Intelligence Scraper</p>', unsafe_allow_html=True)

    # Geolocation & UI state
    if 'user_lat' not in st.session_state: st.session_state.user_lat = None
    if 'user_lng' not in st.session_state: st.session_state.user_lng = None
    if 'use_location_toggle' not in st.session_state: st.session_state.use_location_toggle = False
    if 'resolved_address' not in st.session_state: st.session_state.resolved_address = None
    
    # --- 1. PULL GEOLOCATION FROM URL FIRST ---
    query_params = st.query_params
    if "lat" in query_params and "lng" in query_params:
        st.session_state.user_lat = str(query_params["lat"])
        st.session_state.user_lng = str(query_params["lng"])
        st.session_state.use_location_toggle = True
        desc = get_location_description(st.session_state.user_lat, st.session_state.user_lng)
        st.session_state.resolved_address = desc if desc else f"{st.session_state.user_lat}, {st.session_state.user_lng}"

    # Unified Main UI layout
    main_container = st.container(border=True)
    with main_container:
        search_term = st.text_input("🔍 Nama Bisnis / Kategori", placeholder="e.g., Coffee Shop, Bengkel, PT...")
        row2_col1, row2_col2 = st.columns([3, 1])
        with row2_col1:
            location_input = st.text_input("📍 Lokasi / Wilayah", 
                                          value=st.session_state.resolved_address if st.session_state.resolved_address else "",
                                          placeholder="e.g., Sleman, Jakarta Selatan, atau aktifkan 'Near Me'")
            if st.session_state.use_location_toggle:
                if st.session_state.resolved_address:
                     st.markdown(f'<p style="color:#10b981; font-size:0.8rem; margin-top:-10px; font-weight:600;">✅ Lokasi Terkunci: {st.session_state.resolved_address}</p>', unsafe_allow_html=True)
                else:
                     st.markdown('<p style="color:#6366f1; font-size:0.8rem; margin-top:-10px; font-weight:600;">🛰️ Sedang mengunci koordinat...</p>', unsafe_allow_html=True)
        with row2_col2:
            total_results = st.number_input("Limit", min_value=1, max_value=50, value=5)
        
        conf_col1, conf_col2 = st.columns(2)
        with conf_col1:
            use_gpt = st.toggle("AI KBLI Classification", value=True)
            # Use top-level secret as requested
            secret_api_key = st.secrets.get("OPENAI_API_KEY")
            if secret_api_key:
                api_key = str(secret_api_key).strip()
            else:
                api_key_input = st.text_input("OpenAI API Key", type="password")
                api_key = api_key_input.strip() if api_key_input else None
            show_map = st.toggle("Show Map Visualization", value=True)
            use_location = st.toggle("Near Me Search", value=st.session_state.use_location_toggle, key="loc_toggle")
        
        if use_location != st.session_state.use_location_toggle:
            st.session_state.use_location_toggle = use_location
            if not use_location:
                st.session_state.user_lat = None
                st.session_state.user_lng = None
                st.session_state.resolved_address = None
                st.rerun()

        if use_location and not st.session_state.resolved_address:
            with st.status("📍 Sedang mengunci lokasi Anda...", expanded=False) as status:
                location_data = streamlit_js_eval(
                    js_expressions='new Promise(resolve => navigator.geolocation.getCurrentPosition(pos => resolve({latitude: pos.coords.latitude, longitude: pos.coords.longitude}), err => resolve(null)))', 
                    key='geo_silent_logic_v6',
                    want_output=True
                )
                if location_data:
                    lat, lng = location_data.get('latitude'), location_data.get('longitude')
                    if lat and lng:
                        status.update(label="🛰️ Berhasil mengunci GPS!", state="running")
                        human_address = get_location_description(lat, lng)
                        st.session_state.user_lat = str(lat)
                        st.session_state.user_lng = str(lng)
                        st.session_state.resolved_address = human_address if human_address else f"{lat}, {lng}"
                        status.update(label="✅ Lokasi Siap!", state="complete")
                        time.sleep(0.5)
                        st.rerun()

    target_loc = location_input if location_input else st.session_state.resolved_address
    modified_query = f"{search_term} di sekitar {target_loc}" if search_term and target_loc else search_term if search_term else ""

    st.markdown("---")
    if search_term and target_loc:
        st.markdown(f"""
            <div style="background: linear-gradient(135deg, rgba(99, 102, 241, 0.1), rgba(99, 102, 241, 0.05)); border-left: 5px solid #6366f1; padding: 15px; border-radius: 12px; margin-bottom: 15px; border: 1px solid rgba(99, 102, 241, 0.1);">
                <p style="color:#4338ca; font-size:0.7rem; font-weight:800; text-transform:uppercase; letter-spacing:1px; margin:0 0 4px 0;">🎯 Targeting Keyword:</p>
                <p style="color:#1e293b; font-size:1.1rem; font-weight:600; margin:0;">"{modified_query}"</p>
            </div>
        """, unsafe_allow_html=True)

    is_detecting = use_location and not st.session_state.resolved_address
    btn_label = "🚀 Start Extraction" if not is_detecting else "⏳ Sedang Mencari Lokasi..."
    start_idx = st.button(btn_label, use_container_width=True, disabled=is_detecting or not search_term)

    if 'last_results' not in st.session_state: st.session_state.last_results = None

    if start_idx:
        if not search_term:
            st.error("Please enter a search term.")
        elif use_gpt and not api_key:
            st.error("Please enter an OpenAI API Key or disable GPT enhancement.")
        else:
            try:
                scraper = GoogleMapsScraper(api_key=api_key if use_gpt else None)
                progress_bar = st.progress(0)
                status_text = st.empty()
                
                def update_progress(current, total, message):
                    progress = current / total
                    progress_bar.progress(progress)
                    status_text.text(message)
                
                with st.spinner("Scraping Google Maps..."):
                    lat = st.session_state.user_lat if use_location else None
                    lng = st.session_state.user_lng if use_location else None
                    results = scraper.run(modified_query, total_results, True, progress_callback=update_progress, user_lat=lat, user_lng=lng)
                if results:
                    with st.spinner("Enriching with Administrative Data..."):
                        scraper.enrich_results(progress_callback=update_progress)
                    if use_gpt:
                        with st.spinner("AI is analyzing KBLI..."):
                            scraper.process_with_gpt(progress_callback=update_progress)
                    
                    st.session_state.last_results = scraper.results
                    # Ensure results are locked in
                    st.success(f"Scraping complete! Found {len(scraper.results)} results.")
                    time.sleep(1)
                    st.rerun() 
            except Exception as e:
                st.error(f"Error: {e}")

    # Display results if they exist in session state
    if st.session_state.last_results:
        df = pd.DataFrame(st.session_state.last_results)
        
        if show_map:
            map_df = df.copy()
            map_df['latitude'] = pd.to_numeric(map_df['Latitude'], errors='coerce')
            map_df['longitude'] = pd.to_numeric(map_df['Longitude'], errors='coerce')
            map_df = map_df.dropna(subset=['latitude', 'longitude'])
            if not map_df.empty:
                m = folium.Map(location=[map_df['latitude'].mean(), map_df['longitude'].mean()], zoom_start=13)
                for _, row in map_df.iterrows():
                    folium.Marker([row['latitude'], row['longitude']], popup=row['Name']).add_to(m)
                st_folium(m, width=1200, height=400, key="results_map")

        # Export Logic
        cols = ["Name", "Rating", "Reviews", "Address", "Phone", "Website", "WhatsApp Link", "KBLI", "Nama Resmi KBLI"]
        st.dataframe(df[[c for c in cols if c in df.columns]], use_container_width=True)
        
        if st.button("💾 Save to Database (TiDB)", use_container_width=True):
            save_to_tidb(df)

    st.markdown("<br><br>", unsafe_allow_html=True)
    st.markdown("<p style='text-align: center; color: #94a3b8; font-size: 0.8rem;'>Created with ❤️ using Playwright and Streamlit by JJS</p>", unsafe_allow_html=True)

# Main Multi-page Entry Point
st.set_page_config(page_title="NoSBRGo", page_icon="favicon.svg", layout="wide")

scraper_page = st.Page(show_scraper_page, title="Scraper", icon="🔍", default=True)
db_explorer_page = st.Page("pages/1_Database_Explorer.py", title="Database Explorer", icon="📦")

pg = st.navigation([scraper_page, db_explorer_page])
pg.run()