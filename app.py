import streamlit as st
import pandas as pd
from scraper import GoogleMapsScraper
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

st.sidebar.header("Configuration")

use_gpt = st.sidebar.checkbox("GPT Enhancement", value=True, help="Use AI to extract KBLI and clean addresses")

# Try to get API key from secrets (support multiple formats)
secret_api_key = st.secrets.get("OPENAI_API_KEY") or (st.secrets.get("openai", {}).get("openapi") if isinstance(st.secrets.get("openai"), dict) else None)

if secret_api_key:
    st.sidebar.success("API Key Loaded")
    api_key = str(secret_api_key).strip()
else:
    api_key_input = st.sidebar.text_input("OpenAI API Key", type="password")
    api_key = api_key_input.strip() if api_key_input else None

st.sidebar.markdown("---")
with st.sidebar.expander("Usage Guide"):
    st.markdown("""
    - **Search**: Enter business name + city.
    - **Limit**: Strictly capped at 20 for stability.
    - **Results**: Export to CSV or Excel.
    """)

# Geolocation state
if 'user_lat' not in st.session_state:
    st.session_state.user_lat = None
if 'user_lng' not in st.session_state:
    st.session_state.user_lng = None

# Main UI layout
with st.container(border=True):
    col1, col2 = st.columns([3, 1])
    with col1:
        search_term = st.text_input("Search Query", placeholder="e.g., PT or Coffee shop")
    with col2:
        total_results = st.number_input("Limit", min_value=1, max_value=20, value=5)
    
    # Geolocation Toggle
    use_location = st.toggle("📍 Gunakan Lokasi Saya (Near Me)", value=False)
    
    if use_location:
        # Custom HTML/JS to get geolocation
        st.components.v1.html(
            """
            <div id="location-status" style="color: #64748b; font-size: 0.8rem; font-family: sans-serif;">
                Detecting location...
            </div>
            <script>
                if ("geolocation" in navigator) {
                    navigator.geolocation.getCurrentPosition(function(position) {
                        const lat = position.coords.latitude;
                        const lng = position.coords.longitude;
                        document.getElementById('location-status').innerHTML = "📍 Location detected: " + lat.toFixed(4) + ", " + lng.toFixed(4);
                        
                        // Send back to Streamlit via URL (only if changed significantly)
                        const params = new URLSearchParams(window.parent.location.search);
                        if (params.get('lat') != lat.toFixed(6)) {
                            params.set('lat', lat.toFixed(6));
                            params.set('lng', lng.toFixed(6));
                            window.parent.location.search = params.toString();
                        }
                    }, function(error) {
                        document.getElementById('location-status').innerHTML = "❌ Error: " + error.message;
                    });
                } else {
                    document.getElementById('location-status').innerHTML = "❌ Geolocation not supported";
                }
            </script>
            """,
            height=30
        )
        
        # Pull coordinates from URL query params
        query_params = st.query_params
        if "lat" in query_params and "lng" in query_params:
            st.session_state.user_lat = query_params["lat"]
            st.session_state.user_lng = query_params["lng"]
            st.success(f"Lokasi terkunci: {st.session_state.user_lat}, {st.session_state.user_lng}")

    start_idx = st.button("Start Extraction", use_container_width=True)

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
                # Pass user location if enabled
                lat = st.session_state.user_lat if use_location else None
                lng = st.session_state.user_lng if use_location else None
                results = scraper.run(
                    search_term, 
                    total_results, 
                    True, 
                    progress_callback=update_progress,
                    user_lat=lat,
                    user_lng=lng
                )
            
            if results:
                # Always enrich with official geographic data
                with st.spinner("Enriching geographic data..."):
                    scraper.enrich_results(progress_callback=update_progress)

                if use_gpt:
                    with st.spinner("AI is analyzing KBLI..."):
                        scraper.process_with_gpt(progress_callback=update_progress)
                
                results = scraper.results
                
                df = pd.DataFrame(results)
                
                # Define logical order: Identity -> Position -> KBLI -> Other
                ordered_cols = [
                    "Name",                                     # Identity
                    "Negara", "Provinsi", "Kabupaten",          # Position
                    "Kecamatan", "Kelurahan", "Keterangan Lingkungan",
                    "Kode Pos", "Address", 
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
