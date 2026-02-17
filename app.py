import streamlit as st
import pandas as pd
from scraper import GoogleMapsScraper
import os
import asyncio
import sys

# Fix for Windows asyncio loop policy
if sys.platform == 'win32':
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

st.set_page_config(page_title="Google Maps Scraper", page_icon="🗺️", layout="wide")

st.title("🗺️ Google Maps Scraper")
st.markdown("Scrape business data from Google Maps easily.")

# Sidebar for configuration
st.sidebar.header("Configuration")
search_term = st.sidebar.text_input("Search Term", placeholder="e.g., Coffee in Jakarta")
total_results = st.sidebar.number_input("Total Results", min_value=1, max_value=1000, value=10)
headless = st.sidebar.checkbox("Headless Mode (Hidden Browser)", value=True)

st.sidebar.markdown("---")
st.sidebar.header("OpenAI Enhancement")
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

if st.sidebar.button("Start Scraping"):
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
            
            # Run scraper
            with st.spinner("Browser is running..."):
                results = scraper.run(search_term, total_results, headless)
            
            if results:
                if use_gpt:
                    with st.spinner("Enhancing data with GPT..."):
                        scraper.process_with_gpt()
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
