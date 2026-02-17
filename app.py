import streamlit as st
import pandas as pd
from scraper import GoogleMapsScraper
import io
import requests
import os
import asyncio
import sys

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

st.set_page_config(page_title="sbrGO - Google Maps Scraper", page_icon="🗺️", layout="wide")

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
        font-size: 3rem !important; /* Added !important to ensure override */
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
        font-size: 0.65rem !important; /* Forces the small size */
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
    
    .stButton > button:hover {
        transform: translateY(-2px);
        box-shadow: 0 8px 25px rgba(99, 102, 241, 0.3);
        opacity: 0.9;
    }
    
    /* Sidebar styling */
    section[data-testid="stSidebar"] {
        background-color: #fcfdfe;
        border-right: 1px solid #f1f5f9;
    }
    
    /* Container styling */
    div[data-testid="stVerticalBlockBorderWrapper"] {
        background: rgba(255, 255, 255, 0.4);
        backdrop-filter: blur(10px);
        border: 1px solid rgba(255, 255, 255, 0.3) !important;
        border-radius: 16px !important;
        padding: 2rem !important;
        box-shadow: 0 10px 30px rgba(0, 0, 0, 0.05);
    }
</style>
""", unsafe_allow_html=True)

# App Header
st.markdown('<div class="logo-container"><p class="main-title"><span class="title-no">No</span><span class="title-sbr">SBR</span><span class="title-go">Go</span></p></div>', unsafe_allow_html=True)
st.markdown('<p class="subtitle">Scrape business data from Google Maps in seconds.</p>', unsafe_allow_html=True)

@st.cache_data(show_spinner=False)
def get_location_description(lat, lng):
    """Resolve coordinates to a short location description (Jalan + Kabupaten)."""
    try:
        headers = {'User-Agent': 'sbrGO-App/1.0'}
        geo_url = f"https://nominatim.openstreetmap.org/reverse?format=json&lat={lat}&lon={lng}&zoom=18"
        res = requests.get(geo_url, headers=headers, timeout=5)
        if res.status_code == 200:
            data = res.json()
            addr = data.get('address', {})
            jalan = addr.get('road') or ""
            kabupaten = addr.get('city') or addr.get('regency') or addr.get('county') or ""
            if jalan or kabupaten:
                return f"{jalan} {kabupaten}".strip()
    except:
        pass
    return None

# Geolocation & UI state
if 'user_lat' not in st.session_state: st.session_state.user_lat = None
if 'user_lng' not in st.session_state: st.session_state.user_lng = None
if 'use_location_toggle' not in st.session_state: st.session_state.use_location_toggle = False
if 'resolved_address' not in st.session_state: st.session_state.resolved_address = None
if 'show_loc_dialog' not in st.session_state: st.session_state.show_loc_dialog = False

@st.dialog("📍 Pencarian Lokasi")
def show_location_dialog(search_term):
    st.markdown(f"Sedang mengoptimalkan pencarian untuk: **{search_term}**")
    
    if not st.session_state.user_lat:
        st.info("📡 Sedang meminta akses GPS dari browser...")
        st.components.v1.html(
            """
            <script>
                navigator.geolocation.getCurrentPosition(function(pos) {
                    const lat = pos.coords.latitude.toFixed(6);
                    const lng = pos.coords.longitude.toFixed(6);
                    const params = new URLSearchParams(window.parent.location.search);
                    if (params.get('lat') != lat) {
                        params.set('lat', lat);
                        params.set('lng', lng);
                        window.parent.location.search = params.toString();
                    }
                }, function(err) {
                    window.parent.alert("Gagal GPS: " + err.message);
                }, {enableHighAccuracy: true, timeout: 5000});
            </script>
            """, height=0
        )
    else:
        p_bar = st.progress(0, text="📡 Koordinat Terkunci...")
        # Step 1: Resolve Address
        p_bar.progress(40, text="🔍 Mencari nama jalan dan kabupaten...")
        loc = get_location_description(st.session_state.user_lat, st.session_state.user_lng)
        
        if loc:
            st.session_state.resolved_address = loc
            p_bar.progress(100, text="✅ Alamat Berhasil Ditemukan")
            st.success(f"Target Lokasi: **{loc}**")
        else:
            st.session_state.resolved_address = f"{st.session_state.user_lat}, {st.session_state.user_lng}"
            st.warning("⚠️ Berhasil dapet titik GPS, tapi gagal ambil nama jalan.")
            
        if st.button("Konfirmasi & Lanjutkan", use_container_width=True):
            st.session_state.show_loc_dialog = False
            st.rerun()

# --- 1. PULL GEOLOCATION FROM URL FIRST ---
query_params = st.query_params
if "lat" in query_params and "lng" in query_params:
    st.session_state.user_lat = str(query_params["lat"])
    st.session_state.user_lng = str(query_params["lng"])
    # If coordinates are in URL, auto-enable the toggle
    st.session_state.use_location_toggle = True

# Unified Main UI layout
main_container = st.container(border=True)
with main_container:
    # 1. Search & Limit
    row1_col1, row1_col2 = st.columns([3, 1])
    with row1_col1:
        search_term = st.text_input("Search Query", placeholder="e.g., PT or Coffee shop")
    with row1_col2:
        total_results = st.number_input("Limit", min_value=1, max_value=20, value=5)
    
    st.markdown("---")
    
    # 2. Configuration
    conf_col1, conf_col2 = st.columns(2)
    with conf_col1:
        use_gpt = st.toggle("🤖 AI (GPT) Enhancement", value=True, help="Use AI to extract KBLI and clean addresses")
        # Try to get API key from secrets
        secret_api_key = st.secrets.get("OPENAI_API_KEY") or (st.secrets.get("openai", {}).get("openapi") if isinstance(st.secrets.get("openai"), dict) else None)
        
        if secret_api_key:
            api_key = str(secret_api_key).strip()
        else:
            api_key_input = st.text_input("OpenAI API Key", type="password")
            api_key = api_key_input.strip() if api_key_input else None
        
        show_map = st.toggle("🗺️ Tampilkan Peta Visual", value=True)
    
    # --- 3. INITIALIZE SEARCH QUERY & STATUS ---
    modified_query = search_term
    is_detecting = False
    
    with conf_col2:
        # Toggle triggers the dialog if activated and no address is stored
        use_location = st.toggle("📍 Gunakan Lokasi Saya (Near Me)", value=st.session_state.use_location_toggle, key="loc_toggle")
        st.session_state.use_location_toggle = use_location
        
        if use_location:
            # Trigger dialog if we don't have a resolved name yet
            if not st.session_state.resolved_address:
                show_location_dialog(search_term)
            
            # If address resolved, show the targeting card
            if st.session_state.resolved_address:
                modified_query = f"{search_term} di sekitar {st.session_state.resolved_address}"
                st.markdown(f"""
                    <div style="background: linear-gradient(135deg, rgba(99, 102, 241, 0.1), rgba(99, 102, 241, 0.05)); 
                                border-left: 5px solid #6366f1; padding: 15px; border-radius: 12px; margin-top: 10px; 
                                box-shadow: 0 4px 12px rgba(99, 102, 241, 0.08); border: 1px solid rgba(99, 102, 241, 0.1);">
                        <p style="color:#4338ca; font-size:0.7rem; font-weight:800; text-transform:uppercase; letter-spacing:1px; margin:0 0 4px 0;">🎯 Targeting Keyword:</p>
                        <p style="color:#1e293b; font-size:1.05rem; font-weight:600; margin:0;">"{modified_query}"</p>
                    </div>
                """, unsafe_allow_html=True)
                
                # Small status footer
                if st.session_state.user_lat:
                    st.markdown(f'<div style="font-size:0.65rem; color:#94a3b8; text-align:right; margin-top:5px;">GPS Sync: {st.session_state.user_lat}, {st.session_state.user_lng}</div>', unsafe_allow_html=True)
            else:
                is_detecting = True # Disable button if we are supposed to have location but don't yet

    st.markdown("---")
    # Disable button if detecting
    btn_label = "🚀 Start Extraction" if not is_detecting else "⏳ Tunggu Lokasi..."
    start_idx = st.button(btn_label, use_container_width=True, disabled=is_detecting)

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
                # Geolocation refining
                lat = st.session_state.user_lat if use_location else None
                lng = st.session_state.user_lng if use_location else None
                
                results = scraper.run(
                    modified_query, 
                    total_results, 
                    True, 
                    progress_callback=update_progress,
                    user_lat=lat,
                    user_lng=lng
                )
            
            if results:
                # 1. Enrichment with Administrative Data
                with st.spinner("Enriching with Administrative Data..."):
                    scraper.enrich_results(progress_callback=update_progress)

                # 2. AI (GPT) Analysis
                if use_gpt:
                    with st.spinner("AI is analyzing KBLI..."):
                        scraper.process_with_gpt(progress_callback=update_progress)
                
                results = scraper.results
                df = pd.DataFrame(results)
                
                # --- 3. MAP VISUALIZATION ---
                if show_map:
                    st.markdown("---")
                    st.markdown('<p style="color:#64748b; font-size:0.8rem; text-transform:uppercase; letter-spacing:1px; margin-bottom:5px;">Mapping Distribution</p>', unsafe_allow_html=True)
                    st.markdown('<p style="font-size:1.3rem; font-weight:600; color:#1e293b; margin-top:0;">🗺️ Business Locations Mapping</p>', unsafe_allow_html=True)
                    
                    # Filter rows with valid Lat/Lng and convert to numeric
                    map_df = df.copy()
                    map_df['latitude'] = pd.to_numeric(map_df['Latitude'], errors='coerce')
                    map_df['longitude'] = pd.to_numeric(map_df['Longitude'], errors='coerce')
                    map_df = map_df.dropna(subset=['latitude', 'longitude'])
                    
                    if not map_df.empty:
                        st.map(map_df[['latitude', 'longitude']])
                    else:
                        st.warning("No location coordinates available to map.")

                # --- 4. DATA TABLE DISPLAY ---
                # Define logical order: Identity -> Position -> KBLI -> Other
                ordered_cols = [
                    "Name", "Kategori OSM",                     # Identity & Verification
                    "Negara", "Provinsi", "Kabupaten",          # Position (Admin)
                    "Kecamatan", "Kelurahan", "Hamlet/Quarter",
                    "Kode Pos", "Jalan", "Nomor", "Address",    # Position (Detailed)
                    "Latitude", "Longitude", "URL",
                    "KBLI", "Nama Resmi KBLI", "Keterangan KBLI", # KBLI
                    "Rating", "Reviews", "Operation Hours",      # Other
                    "Latest Review", "Phone", "Website"
                ]
                
                # Filter out columns that might not exist (defensive)
                final_cols = [c for c in ordered_cols if c in df.columns]
                # Append any unexpected columns at the end
                other_cols = [c for c in df.columns if c not in ordered_cols]
                df = df[final_cols + other_cols]

                st.markdown("---")
                st.markdown(f'<p style="color:#64748b; font-size:0.8rem; text-transform:uppercase; letter-spacing:1px; margin-bottom:-10px;">Scrape Results</p>', unsafe_allow_html=True)
                st.markdown(f'<p style="font-size:1.5rem; font-weight:600; color:#1e293b;">{search_term}</p>', unsafe_allow_html=True)
                
                # Show data with clickable links
                st.dataframe(
                    df,
                    column_config={
                        "URL": st.column_config.LinkColumn("G-Maps"),
                        "Website": st.column_config.LinkColumn("Website"),
                        "Reviews": st.column_config.NumberColumn("Reviews", format="%d"),
                        "KBLI": st.column_config.TextColumn("Kode KBLI")
                    },
                    use_container_width=True
                )
                
                # Download actions
                dl_col1, dl_col2 = st.columns(2)
                with dl_col1:
                    csv = df.to_csv(index=False).encode('utf-8')
                    st.download_button(
                        label="Download CSV",
                        data=csv,
                        file_name=f"gmaps_{search_term.replace(' ', '_')}.csv",
                        mime="text/csv",
                        use_container_width=True
                    )
                with dl_col2:
                    try:
                        import io
                        buffer = io.BytesIO()
                        with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
                            df.to_excel(writer, index=False)
                        st.download_button(
                            label="Download Excel",
                            data=buffer.getvalue(),
                            file_name=f"gmaps_{search_term.replace(' ', '_')}.xlsx",
                            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                            use_container_width=True
                        )
                    except:
                        pass
                
            else:
                st.warning("No results found. Please refine your query.")
                
        except Exception as e:
            st.error(f"Error: {e}")
            with st.expander("Click for details"):
                import traceback
                st.code(traceback.format_exc())

st.markdown("<br><br>", unsafe_allow_html=True)
st.markdown("<p style='text-align: center; color: #94a3b8; font-size: 0.8rem;'>Created with ❤️ using Playwright and Streamlit by JJS</p>", unsafe_allow_html=True)
