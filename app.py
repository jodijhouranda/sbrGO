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
        font-size: 10rem; /* Balanced size: clear but not overwhelming */
        font-weight: 800;
        margin-bottom: 0px;
        letter-spacing: normal !important; /* Strictly prevent overlapping */
        line-height: 1.2 !important;
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
        font-size: 0.75rem;
        font-weight: 500;
        text-transform: uppercase;
        letter-spacing: 2px;
        margin-top: -5px;
        margin-bottom: 3.5rem;
        opacity: 0.8;
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
    
    /* Progress bar */
    div[data-testid="stProgress"] > div > div > div {
        background: linear-gradient(90deg, #6366f1 0%, #a855f7 100%);
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

# Main UI layout
col1, col2 = st.columns([3, 1])
with col1:
    search_term = st.text_input("Search Query", placeholder="e.g., Coffee in Jakarta")
with col2:
    total_results = st.number_input("Limit", min_value=1, max_value=20, value=10)

if st.button("Start Extraction", use_container_width=True):
    if not search_term:
        st.error("Please enter a search term.")
    elif use_gpt and not api_key:
        st.error("Please enter an OpenAI API Key or disable GPT enhancement.")
    else:
        # Initialize progress
        progress_bar = st.progress(0)
        status_text = st.empty()
        
        try:
            scraper = GoogleMapsScraper(api_key=api_key if use_gpt else None)
            
            def update_progress(current, total, message):
                percent = int((current / total) * 100)
                progress_bar.progress(percent)
                status_text.markdown(f"<p style='color:#64748b; font-size:0.9rem;'>{message}</p>", unsafe_allow_html=True)

            with st.spinner("Initializing browser..."):
                results = scraper.run(search_term, total_results, True, progress_callback=update_progress)
            
            if results:
                if use_gpt:
                    with st.spinner("AI is analyzing data..."):
                        scraper.process_with_gpt(progress_callback=update_progress)
                        results = scraper.results
                
                df = pd.DataFrame(results)
                
                st.markdown("---")
                st.markdown(f"### 📊 Results for '{search_term}'")
                
                # Show data with clickable links
                st.dataframe(
                    df,
                    column_config={
                        "URL": st.column_config.LinkColumn("G-Maps"),
                        "Website": st.column_config.LinkColumn("Website"),
                        "Reviews": st.column_config.NumberColumn("Reviews", format="%d")
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
