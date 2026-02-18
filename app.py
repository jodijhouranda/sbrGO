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

# Fix for Windows asyncio loop policy
if sys.platform == 'win32':
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

# --- AUTHENTICATION LOGIC ---
def check_login(username, password):
    """Verify credentials against TiDB."""
    cert_path = os.path.abspath("isrgrootx1.pem")
    try:
        conn = st.connection('tidb', type='sql', connect_args={"ssl": {"ca": cert_path}})
        from sqlalchemy import text
        with conn.session as session:
            result = session.execute(
                text("SELECT username, is_superuser FROM users WHERE username = :u AND password = :p"),
                {"u": username, "p": password}
            ).fetchone()
            if result:
                return True, result[0], bool(result[1])
    except Exception as e:
        st.error(f"Login error: {e}")
    return False, None, False

def handle_logout():
    st.session_state.authenticated = False
    st.session_state.username = None
    st.session_state.is_superuser = False
    st.rerun()

def show_login_page():
    # Premium Login UI
    st.markdown("""
    <style>
        /* Hide default Streamlit elements on login page */
        [data-testid="stHeader"] { visibility: hidden; }
        
        /* Centering and Background */
        .stApp {
            background: radial-gradient(circle at top right, #f8f9ff 0%, #ffffff 100%);
            display: flex;
            justify-content: center;
            align-items: center;
        }

        /* Target the form container specifically */
        [data-testid="stForm"] {
            border: 1px solid rgba(255, 255, 255, 0.4) !important;
            background: rgba(255, 255, 255, 0.6) !important;
            backdrop-filter: blur(20px) !important;
            border-radius: 28px !important;
            padding: 3rem !important;
            box-shadow: 0 25px 50px -12px rgba(0, 0, 0, 0.1) !important;
            max-width: 450px;
            margin: auto;
        }

        .title-no { color: #6366f1; }
        .title-sbr { color: #1e293b; }
        .title-go { color: #a855f7; }
        .main-title { 
            font-size: 3rem !important; 
            font-weight: 800; 
            margin-bottom: 5px; 
            text-align: center;
            letter-spacing: -1px;
        }
        .subtitle { 
            color: #94a3b8; 
            font-size: 0.75rem !important; 
            font-weight: 600; 
            text-transform: uppercase; 
            letter-spacing: 2px;
            text-align: center;
            margin-bottom: 2.5rem;
        }
        
        /* Input & Button Styling */
        .stTextInput input {
            border-radius: 12px !important;
            border: 1px solid #e2e8f0 !important;
            padding: 12px !important;
        }
        
        .stButton button {
            background: linear-gradient(135deg, #6366f1 0%, #a855f7 100%) !important;
            border-radius: 12px !important;
            padding: 12px 0 !important;
            font-weight: 700 !important;
            letter-spacing: 0.5px !important;
            margin-top: 1rem !important;
        }
    </style>
    """, unsafe_allow_html=True)
    
    # Use columns to position the login form in the center of the screen
    _, col, _ = st.columns([1, 1.5, 1])
    
    with col:
        st.markdown('<p class="main-title"><span class="title-no">No</span><span class="title-sbr">SBR</span><span class="title-go">Go</span></p>', unsafe_allow_html=True)
        st.markdown('<p class="subtitle">Secure Data Access</p>', unsafe_allow_html=True)
        
        with st.form("login_form", clear_on_submit=False):
            user_input = st.text_input("Username", placeholder="Enter your username")
            pass_input = st.text_input("Password", type="password", placeholder="Enter your password")
            submit = st.form_submit_button("SIGN IN", use_container_width=True)
            
            if submit:
                success, user, is_admin = check_login(user_input, pass_input)
                if success:
                    st.session_state.authenticated = True
                    st.session_state.username = user
                    st.session_state.is_superuser = is_admin
                    st.rerun()
                else:
                    st.error("Authentication failed. Please check your credentials.")

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

@st.cache_data(show_spinner=False)
def get_location_description(lat, lng):
    """
    Mengambil data alamat lengkap & administratif Indonesia (Hierarkis).
    Mencakup: Gedung/Tempat, Jalan, Kelurahan, Kecamatan, Kab/Kota.
    """
    if not lat or not lng: return None
    
    headers = {'User-Agent': 'NoSBRGo-App/1.1'}
    url = f"https://nominatim.openstreetmap.org/reverse?format=json&lat={lat}&lon={lng}&zoom=18&addressdetails=1"
    
    try:
        res = requests.get(url, headers=headers, timeout=5)
        if res.status_code == 200:
            data = res.json()
            addr = data.get('address', {})
            
            poi = (addr.get('amenity') or addr.get('building') or 
                   addr.get('shop') or addr.get('office') or addr.get('tourism'))
            jalan = (addr.get('road') or addr.get('street') or addr.get('pedestrian') or addr.get('residential'))
            nomor = addr.get('house_number')
            kelurahan = (addr.get('village') or addr.get('neighbourhood') or 
                         addr.get('quarter') or addr.get('hamlet') or addr.get('suburb_district'))
            kecamatan = (addr.get('suburb') or addr.get('district') or addr.get('city_district') or addr.get('town'))
            kota = (addr.get('city') or addr.get('regency') or addr.get('municipality') or addr.get('county'))
            
            parts = []
            seen_words = set()

            def add_part(label, value, prefix=""):
                if not value: return
                val_clean = str(value).strip()
                val_lower = val_clean.lower()
                if any(word in seen_words for word in val_lower.split()):
                    return
                parts.append(f"{prefix}{val_clean}")
                for word in val_lower.split():
                    seen_words.add(word)

            if poi: add_part("POI", poi)
            full_jalan = f"{jalan} No. {nomor}" if (jalan and nomor) else jalan
            if full_jalan: add_part("Jalan", full_jalan)
            if kelurahan: add_part("Kelurahan", kelurahan, "Kel. ")
            if kecamatan: add_part("Kecamatan", kecamatan, "Kec. ")
            if kota: add_part("Kota", kota)
            
            if len(parts) < 2:
                dn_parts = data.get('display_name', '').split(',')
                return ", ".join([p.strip() for p in dn_parts[:3]])
                
            return ", ".join(parts)
    except Exception:
        pass
    return f"{lat}, {lng}"

def format_wa_link(phone):
    """Konversi nomor telepon Indonesia (08x, +62) ke link WhatsApp wa.me."""
    if pd.isna(phone): return None
    clean_phone = "".join(filter(str.isdigit, str(phone)))
    if not clean_phone: return None
    if clean_phone.startswith('08'):
        return f"https://wa.me/62{clean_phone[1:]}"
    elif clean_phone.startswith('62'):
        return f"https://wa.me/{clean_phone}"
    elif clean_phone.startswith('8'):
        return f"https://wa.me/62{clean_phone}"
    return None

def save_to_tidb(df):
    """Save the dataframe to TiDB table 'scraped_results'."""
    if df is None or df.empty:
        st.warning("No data to save.")
        return
    
    cert_path = os.path.abspath("isrgrootx1.pem")
    if not os.path.exists(cert_path):
        st.error(f"SSL Certificate not found at {cert_path}")
        return

    try:
        conn = st.connection('tidb', type='sql', connect_args={"ssl": {"ca": cert_path}})
    except Exception as e:
        st.error(f"Database connection error: {e}")
        return

    try:
        with st.status("Saving data to TiDB...", expanded=False) as status:
            df_to_save = df.copy()
            df_to_save['scraped_at'] = pd.Timestamp.now()
            df_to_save['username'] = st.session_state.get('username', 'system')
            
            df_to_save.to_sql('scraped_results', con=conn.engine, if_exists='append', index=False)
            
            # Trigger refresh for Database Explorer
            st.cache_data.clear()
            st.session_state.refresh_needed = True
            
            status.update(label="✅ Data successfully saved to TiDB!", state="complete")
        st.success(f"Successfully saved {len(df)} records under user '{st.session_state.username}'.")
    except Exception as e:
        st.error(f"Error saving to database: {e}")
        with st.expander("Show detailed error"):
            st.code(str(e))

def apply_global_styles():
    """Apply consistent premium styling across all pages."""
    st.markdown("""
    <style>
        @import url('https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;600&display=swap');
        html, body, [data-testid="stStandardType"] { font-family: 'Outfit', sans-serif; }
        .stApp { background: radial-gradient(circle at top right, #f8f9ff 0%, #ffffff 100%); }
        .main-title { font-size: 3rem !important; font-weight: 800; margin-bottom: 0px; line-height: 1.1; text-shadow: 0 10px 30px rgba(99, 102, 241, 0.1); }
        .title-no { color: #6366f1; }
        .title-sbr { color: #1e293b; }
        .title-go { color: #a855f7; }
        .logo-container { display: flex; align-items: center; width: 100%; margin-top: -30px; margin-bottom: 15px; padding-top: 1.5rem; overflow: visible !important; }
        .subtitle { color: #94a3b8; font-size: 0.65rem !important; font-weight: 500; text-transform: uppercase; letter-spacing: 1px; margin-top: -10px; margin-bottom: 3rem; opacity: 0.6; }
        div[data-testid="stMetric"] { background: rgba(255, 255, 255, 0.7); backdrop-filter: blur(10px); border: 1px solid rgba(255, 255, 255, 0.3); border-radius: 12px; padding: 1rem; }
        .stButton > button { background: linear-gradient(90deg, #6366f1 0%, #a855f7 100%); color: white !important; border: none; padding: 0.6rem 2rem; border-radius: 8px; font-weight: 600; transition: all 0.3s ease; box-shadow: 0 4px 15px rgba(99, 102, 241, 0.2); }
        .stButton > button:hover { transform: translateY(-2px); box-shadow: 0 8px 25px rgba(99, 102, 241, 0.3); opacity: 0.9; }
        section[data-testid="stSidebar"] { background-color: #fcfdfe; border-right: 1px solid #f1f5f9; }
        div[data-testid="stVerticalBlockBorderWrapper"] { background: rgba(255, 255, 255, 0.4); backdrop-filter: blur(10px); border: 1px solid rgba(255, 255, 255, 0.3) !important; border-radius: 16px !important; padding: 2rem !important; box-shadow: 0 10px 30px rgba(0, 0, 0, 0.05); }
    </style>
    """, unsafe_allow_html=True)

def show_scraper_page():
    st.markdown('<div class="logo-container"><p class="main-title"><span class="title-no">No</span><span class="title-sbr">SBR</span><span class="title-go">Go</span></p></div>', unsafe_allow_html=True)
    st.markdown('<p class="subtitle">Scrape business data from Google Maps in seconds.</p>', unsafe_allow_html=True)

    if 'user_lat' not in st.session_state: st.session_state.user_lat = None
    if 'user_lng' not in st.session_state: st.session_state.user_lng = None
    if 'use_location_toggle' not in st.session_state: st.session_state.use_location_toggle = False
    if 'resolved_address' not in st.session_state: st.session_state.resolved_address = None
    if 'last_results' not in st.session_state: st.session_state.last_results = None

    query_params = st.query_params
    if "lat" in query_params and "lng" in query_params:
        st.session_state.user_lat = str(query_params["lat"])
        st.session_state.user_lng = str(query_params["lng"])
        st.session_state.use_location_toggle = True
        desc = get_location_description(st.session_state.user_lat, st.session_state.user_lng)
        st.session_state.resolved_address = desc if desc else f"{st.session_state.user_lat}, {st.session_state.user_lng}"

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
        
        st.markdown("---")
        conf_col1, conf_col2 = st.columns(2)
        with conf_col1:
            use_gpt = st.toggle("AI For KBLI", value=True, help="Use AI to extract KBLI and clean addresses")
            secret_api_key = st.secrets.get("OPENAI_API_KEY")
            api_key = str(secret_api_key).strip() if secret_api_key else None
            show_map = st.toggle("Show Map", value=True)
            use_location = st.toggle("Near Me", value=st.session_state.use_location_toggle, key="loc_toggle")
        
        if use_location != st.session_state.use_location_toggle:
            st.session_state.use_location_toggle = use_location
            if not use_location:
                st.session_state.user_lat = None; st.session_state.user_lng = None; st.session_state.resolved_address = None
                st.rerun()

        if use_location and not st.session_state.resolved_address:
            with st.status("📍 Sedang mengunci lokasi Anda...", expanded=False) as status:
                location_data = streamlit_js_eval(
                    js_expressions='new Promise(resolve => navigator.geolocation.getCurrentPosition(pos => resolve({latitude: pos.coords.latitude, longitude: pos.coords.longitude}), err => resolve(null)))', 
                    key='geo_silent_logic_final_v5', want_output=True
                )
                if location_data:
                    lat, lng = location_data.get('latitude'), location_data.get('longitude')
                    if lat and lng:
                        st.session_state.user_lat = str(lat); st.session_state.user_lng = str(lng)
                        st.session_state.resolved_address = get_location_description(lat, lng)
                        status.update(label="✅ Lokasi Siap!", state="complete")
                        time.sleep(0.5); st.rerun()

    target_loc = location_input if location_input else st.session_state.resolved_address
    modified_query = f"{search_term} di sekitar {target_loc}" if search_term and target_loc else search_term if search_term else ""

    st.markdown("---")
    if search_term and target_loc:
        st.markdown(f'<div style="background: rgba(99,102,241,0.1); border-left: 5px solid #6366f1; padding: 15px; border-radius: 12px; border: 1px solid rgba(99,102,241,0.1);"><p style="color:#4338ca; font-size:0.7rem; font-weight:800; text-transform:uppercase; margin:0;">🎯 Targeting Keyword:</p><p style="color:#1e293b; font-size:1.1rem; font-weight:600; margin:0;">"{modified_query}"</p></div>', unsafe_allow_html=True)

    is_detecting = use_location and not st.session_state.resolved_address
    start_idx = st.button("🚀 Start Extraction" if not is_detecting else "⏳ Sedang Mencari Lokasi...", use_container_width=True, disabled=is_detecting or not search_term)

    if start_idx:
        try:
            scraper = GoogleMapsScraper(api_key=api_key if use_gpt else None)
            progress_bar = st.progress(0); status_text = st.empty()
            def update_progress(current, total, message):
                progress_bar.progress(current / total); status_text.text(message)
            
            with st.spinner("Scraping..."):
                results = scraper.run(modified_query, total_results, True, progress_callback=update_progress, 
                                    user_lat=st.session_state.user_lat if use_location else None, 
                                    user_lng=st.session_state.user_lng if use_location else None)
            if results:
                scraper.enrich_results(progress_callback=update_progress)
                if use_gpt: scraper.process_with_gpt(progress_callback=update_progress)
                st.session_state.last_results = scraper.results
                st.success("Complete!"); time.sleep(1); st.rerun() 
        except Exception as e:
            st.error(f"Error: {e}")

    if st.session_state.last_results:
        df = pd.DataFrame(st.session_state.last_results)
        if show_map:
            st.markdown("---")
            st.markdown('<p style="font-size:1.3rem; font-weight:600; color:#1e293b;">🗺️ Interactive Competitor Map</p>', unsafe_allow_html=True)
            map_df = df.copy(); map_df['lat'] = pd.to_numeric(map_df['Latitude'], errors='coerce'); map_df['lng'] = pd.to_numeric(map_df['Longitude'], errors='coerce')
            map_df = map_df.dropna(subset=['lat', 'lng'])
            if not map_df.empty:
                m = folium.Map(location=[map_df['lat'].mean(), map_df['lng'].mean()], zoom_start=13)
                for _, row in map_df.iterrows():
                    wa_link = format_wa_link(row['Phone']) if 'Phone' in row else None
                    wa_html = f'<br><a href="{wa_link}" target="_blank">💬 WhatsApp</a>' if wa_link else ""
                    gmap_html = f'<br><a href="{row["URL"]}" target="_blank">📍 Google Maps</a>' if 'URL' in row else ""
                    popup_html = f"<b>{row['Name']}</b>{wa_html}{gmap_html}"
                    folium.Marker([row['lat'], row['lng']], popup=popup_html, icon=folium.Icon(color="indigo")).add_to(m)
                st_folium(m, width="100%", height=500, returned_objects=[], key="results_map_v2")

        if 'Phone' in df.columns: df['WhatsApp Link'] = df['Phone'].apply(format_wa_link)
        ordered_cols = ["Name", "Kategori OSM", "WhatsApp Link", "Phone", "Negara", "Provinsi", "Kabupaten", "Kecamatan", "Kelurahan", "Hamlet/Quarter", "Kode Pos", "Jalan", "Nomor", "Address", "Latitude", "Longitude", "URL", "KBLI", "Nama Resmi KBLI", "Keterangan KBLI", "Rating", "Reviews", "Operation Hours", "Latest Review", "Website"]
        final_cols = [c for c in ordered_cols if c in df.columns]
        st.dataframe(df[final_cols + [c for c in df.columns if c not in ordered_cols]], column_config={"URL": st.column_config.LinkColumn("G-Maps"), "WhatsApp Link": st.column_config.LinkColumn("Chat WA"), "Website": st.column_config.LinkColumn("Website")}, use_container_width=True)
        
        dl1, dl2, dl3 = st.columns(3)
        with dl1: st.download_button("Download CSV", data=df.to_csv(index=False).encode('utf-8'), file_name="gmaps.csv", use_container_width=True)
        with dl2:
            buf = io.BytesIO()
            with pd.ExcelWriter(buf, engine='openpyxl') as wr: df.to_excel(wr, index=False)
            st.download_button("Download Excel", data=buf.getvalue(), file_name="gmaps.xlsx", use_container_width=True)
        with dl3:
            if st.button("💾 Save to Database (TiDB)", use_container_width=True): save_to_tidb(df)

    st.markdown("<br><p style='text-align: center; color: #94a3b8; font-size: 0.8rem;'>Created with ❤️ by JJS</p>", unsafe_allow_html=True)

# Main Multi-page Entry Point
st.set_page_config(page_title="NoSBRGo", page_icon="favicon.svg", layout="wide")

if 'authenticated' not in st.session_state: st.session_state.authenticated = False
if 'username' not in st.session_state: st.session_state.username = None
if 'is_superuser' not in st.session_state: st.session_state.is_superuser = False

if not st.session_state.authenticated:
    show_login_page()
else:
    # Apply Persistent Styling
    apply_global_styles()
    
    # Persistent Sidebar Logout
    with st.sidebar:
        st.markdown(f"👤 Logged in as: **{st.session_state.username}**")
        if st.session_state.is_superuser:
            st.markdown("👑 (Superuser)")
        if st.button("🚪 Logout", use_container_width=True):
            handle_logout()
        st.markdown("---")

    scraper_page = st.Page(show_scraper_page, title="Scraper", icon=":material/travel_explore:", default=True)
    db_explorer_page = st.Page("pages/1_Database_Explorer.py", title="Database Explorer", icon=":material/grid_on:")
    pages = [scraper_page, db_explorer_page]
    if st.session_state.is_superuser:
        pages.append(st.Page("pages/2_User_Management.py", title="User Management", icon=":material/manage_accounts:"))
    st.navigation(pages).run()