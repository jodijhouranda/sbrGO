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
    # addressdetails=1 & zoom=18 memberikan detail level jalan + POI
    url = f"https://nominatim.openstreetmap.org/reverse?format=json&lat={lat}&lon={lng}&zoom=18&addressdetails=1"
    
    try:
        res = requests.get(url, headers=headers, timeout=5)
        if res.status_code == 200:
            data = res.json()
            addr = data.get('address', {})
            
            # 1. POI / BANGUNAN / GEDUNG
            poi = (addr.get('amenity') or addr.get('building') or 
                   addr.get('shop') or addr.get('office') or addr.get('tourism'))
            
            # 2. JALAN & NOMOR
            jalan = (addr.get('road') or addr.get('street') or addr.get('pedestrian') or addr.get('residential'))
            nomor = addr.get('house_number')
            
            # 3. KELURAHAN / DESA
            kelurahan = (addr.get('village') or addr.get('neighbourhood') or 
                         addr.get('quarter') or addr.get('hamlet') or addr.get('suburb_district'))
            
            # 4. KECAMATAN
            kecamatan = (addr.get('suburb') or addr.get('district') or addr.get('city_district') or addr.get('town'))
            
            # 5. KABUPATEN / KOTA
            kota = (addr.get('city') or addr.get('regency') or addr.get('municipality') or addr.get('county'))
            
            # --- PENYUSUNAN STRING YANG CERDAS ---
            parts = []
            seen_words = set()

            def add_part(label, value, prefix=""):
                if not value: return
                val_clean = str(value).strip()
                val_lower = val_clean.lower()
                
                # Cek agar tidak ada repetisi (e.g., "Kec. Sleman, Sleman")
                if any(word in seen_words for word in val_lower.split()):
                    return
                
                parts.append(f"{prefix}{val_clean}")
                for word in val_lower.split():
                    seen_words.add(word)

            # Tambahkan urutan dari paling spesifik
            if poi: add_part("POI", poi)
            
            full_jalan = f"{jalan} No. {nomor}" if (jalan and nomor) else jalan
            if full_jalan: add_part("Jalan", full_jalan)
            
            if kelurahan: add_part("Kelurahan", kelurahan, "Kel. ")
            if kecamatan: add_part("Kecamatan", kecamatan, "Kec. ")
            if kota: add_part("Kota", kota)
            
            # Fallback ke display_name jika parts masih terlalu dikit
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
    # Bersihkan karakter non-digit
    clean_phone = "".join(filter(str.isdigit, str(phone)))
    
    if not clean_phone: return None
    
    if clean_phone.startswith('08'):
        return f"https://wa.me/62{clean_phone[1:]}"
    elif clean_phone.startswith('62'):
        return f"https://wa.me/{clean_phone}"
    elif clean_phone.startswith('8'): # handle "812..."
        return f"https://wa.me/62{clean_phone}"
        
    return None

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
    # Premium UI Styling (Exactly as requested)
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

    # Geolocation & UI state
    if 'user_lat' not in st.session_state: st.session_state.user_lat = None
    if 'user_lng' not in st.session_state: st.session_state.user_lng = None
    if 'use_location_toggle' not in st.session_state: st.session_state.use_location_toggle = False
    if 'resolved_address' not in st.session_state: st.session_state.resolved_address = None
    if 'last_results' not in st.session_state: st.session_state.last_results = None

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
        
        st.markdown("---")
        conf_col1, conf_col2 = st.columns(2)
        with conf_col1:
            use_gpt = st.toggle("🤖 AI (GPT) Enhancement", value=True, help="Use AI to extract KBLI and clean addresses")
            secret_api_key = st.secrets.get("OPENAI_API_KEY")
            if secret_api_key:
                api_key = str(secret_api_key).strip()
            else:
                api_key_input = st.text_input("OpenAI API Key", type="password")
                api_key = api_key_input.strip() if api_key_input else None
            show_map = st.toggle("🗺️ Tampilkan Peta Visual", value=True)
            use_location = st.toggle("📍 Near Me (Auto-Detect)", value=st.session_state.use_location_toggle, key="loc_toggle")
        
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
                    key='geo_silent_logic_final_v5',
                    want_output=True
                )
                if location_data:
                    lat, lng = location_data.get('latitude'), location_data.get('longitude')
                    if lat and lng:
                        status.update(label="🛰️ Berhasil mengunci GPS! Mencari info wilayah...", state="running")
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
                    st.success(f"Scraping complete! Found {len(scraper.results)} results.")
                    time.sleep(1)
                    st.rerun() 
            except Exception as e:
                st.error(f"Error: {e}")

    # Display results if they exist in session state
    if st.session_state.last_results:
        df = pd.DataFrame(st.session_state.last_results)
        
        # --- MAP VISUALIZATION (Exactly as requested) ---
        if show_map:
            st.markdown("---")
            st.markdown('<p style="color:#64748b; font-size:0.8rem; text-transform:uppercase; letter-spacing:1px; margin-bottom:5px;">Mapping Distribution</p>', unsafe_allow_html=True)
            st.markdown('<p style="font-size:1.3rem; font-weight:600; color:#1e293b; margin-top:0;">🗺️ Interactive Competitor Map</p>', unsafe_allow_html=True)
            
            map_df = df.copy()
            map_df['latitude'] = pd.to_numeric(map_df['Latitude'], errors='coerce')
            map_df['longitude'] = pd.to_numeric(map_df['Longitude'], errors='coerce')
            map_df = map_df.dropna(subset=['latitude', 'longitude'])
            
            if not map_df.empty:
                avg_lat = map_df['latitude'].mean()
                avg_lng = map_df['longitude'].mean()
                m = folium.Map(location=[avg_lat, avg_lng], zoom_start=13, control_scale=True)
                for _, row in map_df.iterrows():
                    popup_html = f"""
                    <div style="font-family: 'Outfit', sans-serif; min-width: 200px;">
                        <h4 style="margin-bottom: 5px; color: #1e293b;">{row['Name']}</h4>
                        <p style="margin: 0; color: #6366f1; font-weight: 600;">⭐ {row['Rating']} ({row['Reviews']} reviews)</p>
                        <p style="margin-top: 5px; font-size: 0.9rem; color: #64748b;">{row.get('Kecamatan', '')} {row.get('Kabupaten', '')}</p>
                        <a href="{row['URL']}" target="_blank" style="display: inline-block; margin-top: 10px; color: #6366f1; text-decoration: none; font-weight: 600;">Buka G-Maps ↗</a>
                    </div>
                    """
                    folium.Marker(
                        [row['latitude'], row['longitude']],
                        popup=folium.Popup(popup_html, max_width=300),
                        tooltip=row['Name'],
                        icon=folium.Icon(color="indigo", icon="info-sign")
                    ).add_to(m)
                st_folium(m, width="100%", height=500, returned_objects=[], key="results_map_v2")

        if 'Phone' in df.columns:
            df['WhatsApp Link'] = df['Phone'].apply(format_wa_link)

        # Restored Table Column Order
        ordered_cols = [
            "Name", "Kategori OSM",                     
            "WhatsApp Link", "Phone",                   
            "Negara", "Provinsi", "Kabupaten",          
            "Kecamatan", "Kelurahan", "Hamlet/Quarter",
            "Kode Pos", "Jalan", "Nomor", "Address",    
            "Latitude", "Longitude", "URL",
            "KBLI", "Nama Resmi KBLI", "Keterangan KBLI", 
            "Rating", "Reviews", "Operation Hours",      
            "Latest Review", "Website"
        ]
        final_cols = [c for c in ordered_cols if c in df.columns]
        other_cols = [c for c in df.columns if c not in ordered_cols]
        df_display = df[final_cols + other_cols]

        st.markdown("---")
        st.markdown(f'<p style="color:#64748b; font-size:0.8rem; text-transform:uppercase; letter-spacing:1px; margin-bottom:-10px;">Scrape Results</p>', unsafe_allow_html=True)
        st.markdown(f'<p style="font-size:1.5rem; font-weight:600; color:#1e293b;">{search_term if search_term else "Results"}</p>', unsafe_allow_html=True)
        
        st.dataframe(
            df_display,
            column_config={
                "URL": st.column_config.LinkColumn("G-Maps"),
                "WhatsApp Link": st.column_config.LinkColumn("Chat WA", help="Klik untuk chat WhatsApp langsung"),
                "Website": st.column_config.LinkColumn("Website"),
                "Reviews": st.column_config.NumberColumn("Reviews", format="%d"),
                "KBLI": st.column_config.TextColumn("Kode KBLI")
            },
            use_container_width=True
        )
        
        # Download & Save Actions
        dl_col1, dl_col2, dl_col3 = st.columns(3)
        with dl_col1:
            csv = df.to_csv(index=False).encode('utf-8')
            st.download_button("Download CSV", data=csv, file_name=f"gmaps_{int(time.time())}.csv", mime="text/csv", use_container_width=True)
        with dl_col2:
            buffer = io.BytesIO()
            with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
                df.to_excel(writer, index=False)
            st.download_button("Download Excel", data=buffer.getvalue(), file_name=f"gmaps_{int(time.time())}.xlsx", mime="application/vnd.ms-excel", use_container_width=True)
        with dl_col3:
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