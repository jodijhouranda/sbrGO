import streamlit as st
import pandas as pd
from scraper import GoogleMapsScraper
import io
import requests
import os
import asyncio
import sys
import time

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
    if not lat or not lng: return None
    try:
        headers = {'User-Agent': 'sbrGO-App/1.0'}
        geo_url = f"https://nominatim.openstreetmap.org/reverse?format=json&lat={lat}&lon={lng}&zoom=18"
        res = requests.get(geo_url, headers=headers, timeout=5)
        if res.status_code == 200:
            data = res.json()
            addr = data.get('address', {})
            jalan = addr.get('road') or addr.get('suburb') or ""
            kabupaten = addr.get('city') or addr.get('regency') or addr.get('county') or addr.get('state_district') or ""
            if jalan or kabupaten:
                return f"{jalan} {kabupaten}".strip()
            return f"{lat}, {lng}"
    except Exception:
        pass
    return None

# Geolocation & UI state
if 'user_lat' not in st.session_state: st.session_state.user_lat = None
if 'user_lng' not in st.session_state: st.session_state.user_lng = None
if 'resolved_address' not in st.session_state: st.session_state.resolved_address = None
if 'loc_step' not in st.session_state: st.session_state.loc_step = 0 # 0: None, 1: GPS, 2: Geocoding

@st.dialog("🛰️ Deteksi Lokasi Otomatis")
def location_progress_dialog():
    if not st.session_state.user_lat:
        st.write("### Tahap 1/2: Mengunci Titik GPS")
        st.markdown("Mohon beri izin lokasi jika muncul permintaan dari browser.")
        st.progress(40, text="Sedang menunggu sinyal satelit...")
        
        # Automatic GPS Script inside Dialog
        st.components.v1.html(
            """
            <script>
                function getLoc() {
                    navigator.geolocation.getCurrentPosition(function(pos) {
                        const lat = pos.coords.latitude.toFixed(6);
                        const lng = pos.coords.longitude.toFixed(6);
                        const params = new URLSearchParams(window.parent.location.search);
                        params.set('lat', lat);
                        params.set('lng', lng);
                        window.parent.location.search = params.toString();
                    }, function(err) {
                        console.log("GPS Seek: " + err.message);
                    }, {enableHighAccuracy: true, timeout: 5000, maximumAge: 0});
                }
                setTimeout(getLoc, 500); // Small delay to ensure dialog is ready
            </script>
            """, height=0
        )
    else:
        st.write("### Tahap 2/2: Menerjemahkan Alamat")
        st.markdown(f"Koordinat terkunci: `{st.session_state.user_lat}, {st.session_state.user_lng}`")
        st.progress(85, text="Mencari nama jalan & wilayah...")
        
        # Server-side address resolution
        with st.spinner("Mencari alamat..."):
            addr = get_location_description(st.session_state.user_lat, st.session_state.user_lng)
            if addr:
                st.session_state.resolved_address = addr
                st.success(f"Ditemukan: **{addr}**")
                time.sleep(1)
                st.rerun() # This will close dialog because resolved_address is now set
            else:
                st.error("Gagal mendapatkan alamat. Silakan input manual.")
                if st.button("Tutup"): st.rerun()

# --- 1. PULL GEOLOCATION FROM URL FIRST ---
query_params = st.query_params
if "lat" in query_params and "lng" in query_params:
    st.session_state.user_lat = str(query_params["lat"])
    st.session_state.user_lng = str(query_params["lng"])
    # If coordinates are in URL, auto-enable the toggle
    st.session_state.use_location_toggle = True
    # Auto-resolve if we have coordinates but no address yet
    if not st.session_state.resolved_address:
        loc_msg = st.empty()
        loc_bar = st.progress(50, text="🔍 Menerjemahkan Alamat...")
        
        # Resolve address
        st.session_state.resolved_address = get_location_description(st.session_state.user_lat, st.session_state.user_lng)
        
        loc_bar.progress(100, text="✅ Alamat Berhasil Ditemukan")
        time.sleep(0.8)
        loc_msg.empty()
        loc_bar.empty()
        st.rerun()

# Unified Main UI layout
main_container = st.container(border=True)
with main_container:
    # 1. Search Details (Business Name & Location)
    row1_col1, row1_col2 = st.columns([3, 1])
    with row1_col1:
        search_term = st.text_input("🔍 Nama Bisnis / Kategori", placeholder="e.g., Coffee Shop, Bengkel, PT...")
    with row1_col2:
        total_results = st.number_input("Limit", min_value=1, max_value=50, value=5)
    
    row2_col1 = st.columns(1)[0]
    with row2_col1:
        location_input = st.text_input("📍 Lokasi / Wilayah", 
                                      value=st.session_state.resolved_address if st.session_state.resolved_address else "",
                                      placeholder="e.g., Sleman, Jakarta Selatan, atau aktifkan 'Near Me'")
        
        if st.session_state.use_location_toggle and st.session_state.resolved_address:
             st.markdown(f'<p style="color:#10b981; font-size:0.8rem; margin-top:-10px; font-weight:600;">✅ Lokasi: {st.session_state.resolved_address}</p>', unsafe_allow_html=True)
    
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
        use_location = st.toggle("📍 Near Me (Auto-Detect)", value=st.session_state.use_location_toggle, key="loc_toggle")
    
    # --- 3. HANDLE LOCATION LOGIC & PREVIEW ---
    if use_location != st.session_state.use_location_toggle:
        st.session_state.use_location_toggle = use_location
        if not use_location:
            st.session_state.user_lat = None
            st.session_state.user_lng = None
            st.session_state.resolved_address = None
            st.query_params.clear()
            st.rerun()

    # Trigger Pop-up Progress Dialog
    if use_location and not st.session_state.resolved_address:
        location_progress_dialog()

    # Construct final query
    target_loc = location_input if location_input else st.session_state.resolved_address
    
    if search_term and target_loc:
        modified_query = f"{search_term} di sekitar {target_loc}"
    elif search_term:
        modified_query = search_term
    else:
        modified_query = ""

    st.markdown("---")
    
    # 3. EXTRACTION TRIGGER & PREVIEW
    if search_term and target_loc:
        st.markdown(f"""
            <div style="background: linear-gradient(135deg, rgba(99, 102, 241, 0.1), rgba(99, 102, 241, 0.05)); 
                        border-left: 5px solid #6366f1; padding: 15px; border-radius: 12px; margin-bottom: 15px; 
                        box-shadow: 0 4px 12px rgba(99, 102, 241, 0.08); border: 1px solid rgba(99, 102, 241, 0.1);">
                <p style="color:#4338ca; font-size:0.7rem; font-weight:800; text-transform:uppercase; letter-spacing:1px; margin:0 0 4px 0;">🎯 Targeting Keyword:</p>
                <p style="color:#1e293b; font-size:1.1rem; font-weight:600; margin:0;">"{modified_query}"</p>
            </div>
        """, unsafe_allow_html=True)

    is_detecting = use_location and not st.session_state.resolved_address
    btn_label = "🚀 Start Extraction" if not is_detecting else "⏳ Sedang Mencari Lokasi..."
    start_idx = st.button(btn_label, use_container_width=True, disabled=is_detecting or not search_term)

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
