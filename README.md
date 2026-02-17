# Google Maps Scraper

A Python script to scrape business data from Google Maps using Playwright.

## Prerequisites

- Python 3.8+
- [Playwright](https://playwright.dev/)

## Installation

1.  Clone the repository or download the files.
2.  Install dependencies:
    ```bash
    pip install -r requirements.txt
    ```
3.  Install Playwright browsers:
    ```bash
    playwright install chromium
    ```

## Usage

Run the Streamlit app:

```bash
streamlit run app.py
```

This will open a web interface in your browser where you can:
1.  Enter a search term (e.g., "Cafe in Bandung").
2.  Set the number of results to scrape.
3.  Choose whether to run in headless mode (background) or show the browser.
4.  **Optional**: Enable GPT Enhancement to automatically categorize businesses (KBLI) and extract detailed address components (Kabupaten, Kecamatan, Kelurahan).
5.  Download the results as CSV or Excel.

### CLI Usage (Optional)

You can still run the script from the command line:

```bash
python scraper.py "SEARCH_TERM" --total NUMBER --headless
```

## Output

The script will generate two files:
- `gmaps_SEARCH_TERM.csv`
- `gmaps_SEARCH_TERM.xlsx`

## Deployment (Streamlit Cloud)

To deploy this app to Streamlit Cloud:

1.  **Repository**: Push your code to a GitHub repository.
2.  **Secrets**: In the Streamlit Cloud dashboard, go to **Settings > Secrets** and add your OpenAI API key:
    ```toml
    OPENAI_API_KEY = "your-api-key-here"
    ```
3.  **Packages**: The `packages.txt` file handles Playwright's system dependencies.
4.  **Install Playwright**: Streamlit Cloud will automatically install dependencies from `requirements.txt`. You might need to add a command to install the browser if it doesn't work out of the box (though `playwright` package usually handles it or you can add `sh install_playwright.sh` if needed).

## Notes

- Google Maps structure changes frequently. If the script fails, selectors in `scraper.py` might need updating.
- Running without headless mode is recommended to reduce detection risk.
