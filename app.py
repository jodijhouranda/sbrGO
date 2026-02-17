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
    """Install Playwright browsers if they are missing."""
    with st.spinner("Installing Playwright browsers..."):
        try:
            # Only install chromium to save time/space
            os.system("playwright install chromium")
            return True
        except Exception as e:
            st.error(f"Failed to install Playwright: {e}")
            return False

# Ensure browsers are installed
install_playwright()

st.set_page_config(page_title="Google Maps Scraper", page_icon="🗺️", layout="wide")

st.title("🗺️ Google Maps Scraper")
st.markdown("Scrape business data from Google Maps easily.")

st.sidebar.markdown("---")
st.sidebar.header("Advanced Settings")
headless = st.sidebar.checkbox("Show Browser (Disable Headless)", value=False)
use_gpt = st.sidebar.checkbox("Enable GPT Enhancement", value=True)

# Try to get API key from secrets
secret_api_key = st.secrets.get("OPENAI_API_KEY")

if secret_api_key:
    st.sidebar.success("✅ API Key loaded from secrets")
    api_key = secret_api_key
else:
    api_key = st.sidebar.text_input(
        "OpenAI API Key", 
        type="password", 
        help="Enter your OpenAI API key here if not configured in secrets.toml"
    )

st.sidebar.markdown("---")
with st.sidebar.expander("ℹ️ Usage Tips & Safety"):
    st.markdown("""
    **Best Practices:**
    - **Total Results**: Start with 10-20 to test. Large numbers take time.
    - **Show Browser**: Recommended for local use to see progress.
    - **GPT**: Provides better KBLI and addressing data.
    
    **Safety:**
    - Avoid frequent large scrapes to prevent IP blocks.
    - The tool includes random delays to behave naturally.
    """)

# Main UI layout
col1, col2 = st.columns([2, 1])
with col1:
    search_term = st.text_input("What are you looking for?", placeholder="e.g., Coffee in Jakarta")
with col2:
    total_results = st.number_input("Results Count", min_value=1, max_value=1000, value=10)

if st.button("🚀 Start Scraping", use_container_width=True):
    if not search_term:
        st.error("Please enter a search term.")
    elif use_gpt and not api_key:
        st.error("Please enter an OpenAI API Key or disable GPT enhancement.")
    else:
        st.info(f"Scraping {total_results} results for '{search_term}'... Please wait.")
        
        # Initialize progress
        progress_bar = st.progress(0)
        status_text = st.empty()
        
        try:
            scraper = GoogleMapsScraper(api_key=api_key if use_gpt else None)
            
            # Progress callback for the UI
            def update_progress(current, total, message):
                percent = int((current / total) * 100)
                progress_bar.progress(percent)
                status_text.text(f"Processing... {message}")

            # Run scraper
            with st.spinner("Browser is running..."):
                # On Streamlit Cloud, headless is usually required. 
                # Locally, the user choice matters.
                # However, the user requested "default headless tidak dicentang"
                # which means headless=False (show browser).
                results = scraper.run(search_term, total_results, not headless, progress_callback=update_progress)
            
            if results:
                if use_gpt:
                    with st.spinner("Enhancing data with GPT..."):
                        scraper.process_with_gpt(progress_callback=update_progress)
                        results = scraper.results # Get updated results
                
                df = pd.DataFrame(results)
                st.success(f"Successfully scraped {len(df)} results!")
                
                # Show data with clickable links
                st.dataframe(
                    df,
                    column_config={
                        "URL": st.column_config.LinkColumn("Google Maps Link"),
                        "Website": st.column_config.LinkColumn("Website")
                    },
                    use_container_width=True
                )
                
                # Download buttons
                csv = df.to_csv(index=False).encode('utf-8')
                st.download_button(
                    label="Download CSV",
                    data=csv,
                    file_name=f"gmaps_{search_term.replace(' ', '_')}.csv",
                    mime="text/csv",
                )
                
                # Excel download
                # Requires openpyxl
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
                    )
                except ImportError:
                    st.warning("Install 'openpyxl' to enable Excel download.")
                
            else:
                st.warning("No results found. Try a different search term or check your internet connection.")
                
        except Exception as e:
            st.error(f"An error occurred: {e}")
            import traceback
            st.expander("Show detailed error").code(traceback.format_exc())

st.markdown("---")
st.markdown("Created with ❤️ using Playwright and Streamlit")
