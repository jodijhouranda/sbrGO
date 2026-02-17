import re
import math
import argparse
from playwright.sync_api import sync_playwright
import pandas as pd
import time
import json
from openai import OpenAI

class GoogleMapsScraper:
    def __init__(self, api_key=None):
        self.results = []
        self.api_key = api_key
        self.client = OpenAI(api_key=api_key) if api_key else None

    def run(self, search_term, total_results=10, headless=False, progress_callback=None):
        print(f"Starting scraper for query: '{search_term}' target: {total_results} results")
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=headless)
            context = browser.new_context()
            page = context.new_page()

            # 1. Search and Scroll
            page.goto("https://www.google.com/maps", timeout=60000)
            page.wait_for_timeout(2000)

            # Accept cookies if any
            try:
                page.locator('form[action^="https://consent.google.com"] button').first.click(timeout=3000)
            except:
                pass

            print("Searching...")
            # Try multiple selectors for search box
            try:
                page.wait_for_selector('input#searchboxinput', timeout=10000)
                page.fill('input#searchboxinput', search_term)
            except:
                print("Standard selector failed, trying fallback...")
                page.wait_for_selector('input[name="q"]', timeout=10000)
                page.fill('input[name="q"]', search_term)
            
            page.wait_for_timeout(1000)
            page.keyboard.press("Enter")
            
            # Wait for results to load
            print("Waiting for results...")
            page.wait_for_selector('div[role="feed"]', timeout=10000)
            
            # Scroll to load results
            urls = set()
            previous_count = 0
            
            # Selector for result items
            # Usually results are in 'a' tags with href containing /maps/place/
            # But sometimes they are just in the feed.
            # We want the 'a' tag that links to the place.
            link_selector = 'a[href^="https://www.google.com/maps/place/"]'

            print("Scrolling to load results...")
            while len(urls) < total_results:
                # Scroll the feed
                page.locator('div[role="feed"]').hover()
                page.mouse.wheel(0, 5000)
                page.wait_for_timeout(2000)
                
                # Extract links
                elements = page.locator(link_selector).all()
                current_urls = {el.get_attribute('href') for el in elements}
                urls.update(current_urls)
                
                print(f"Found {len(urls)} unique URLs so far...")
                
                if len(elements) == previous_count:
                    # Try one more time with a bigger scroll or check for end of list
                    page.mouse.wheel(0, 5000)
                    page.wait_for_timeout(3000)
                    # Use a separate check to break if truly stuck?
                    # For now, simplistic break
                    new_elements = page.locator(link_selector).all()
                    if len(new_elements) == previous_count:
                         print("No more results loading.")
                         break
                
                previous_count = len(elements)
                
                if len(urls) >= total_results:
                    break

            # Limit to requested total
            urls = list(urls)[:total_results]
            print(f"Collected {len(urls)} URLs. Starting detail extraction...")

            # 2. Extract Details for each URL
            for i, url in enumerate(urls):
                print(f"[{i+1}/{len(urls)}] Scraping: {url}")
                try:
                    self.extract_details(page, url)
                    if progress_callback:
                        progress_callback(i + 1, len(urls), f"Scraping: {i+1}/{len(urls)}")
                except Exception as e:
                    print(f"Error scraping {url}: {e}")
                
            browser.close()
        
        return self.results

    def process_with_gpt(self, api_key=None, progress_callback=None):
        if api_key:
            self.api_key = api_key
            self.client = OpenAI(api_key=api_key)
        
        if not self.client:
            print("OpenAI client not initialized. Skipping GPT enhancement.")
            return

        print(f"Enhancing {len(self.results)} results with GPT...")
        for i, item in enumerate(self.results):
            print(f"[{i+1}/{len(self.results)}] Processing with GPT: {item['Name']}")
            
            prompt = f"""
            Analyze the following business information from Google Maps and provide structured data in JSON format.
            Business Name: {item['Name']}
            Address: {item['Address']}
            Establishment/Description: {item['Establishment']}
            
            Return the following fields:
            - kbli: Predict the 5-digit KBLI 2020 code (Indonesian Standard Industrial Classification).
            - nama_kbli: The official title (Nama Resmi) for this KBLI code exactly as it appears in the OSS (Online Single Submission) system / KBLI 2020.
            - keterangan_kbli: Brief description/scope of the KBLI category based on OSS regulations.
            - kabupaten: The Regency/City (Kabupaten/Kota) from the address.
            - kecamatan: The District (Kecamatan) from the address.
            - kelurahan: The Sub-district/Village (Kelurahan/Desa) from the address.

            Format the output as a clean JSON object.
            """
            
            try:
                response = self.client.chat.completions.create(
                    model="gpt-4o-mini",
                    messages=[
                        {"role": "system", "content": "You are a helpful assistant that extracts structured business data and identifies official KBLI 2020 categories as defined by the OSS (Online Single Submission) Indonesia system. ALWAYS return a valid JSON object."},
                        {"role": "user", "content": prompt}
                    ],
                    response_format={ "type": "json_object" }
                )
                
                content = response.choices[0].message.content
                if not content:
                    raise ValueError("Empty response from GPT")
                    
                gpt_data = json.loads(content)
                item.update({
                    "KBLI": gpt_data.get("kbli", "N/A"),
                    "Nama Resmi KBLI": gpt_data.get("nama_kbli", "N/A"),
                    "Keterangan KBLI": gpt_data.get("keterangan_kbli", "N/A"),
                    "Kabupaten": gpt_data.get("kabupaten", "N/A"),
                    "Kecamatan": gpt_data.get("kecamatan", "N/A"),
                    "Kelurahan": gpt_data.get("kelurahan", "N/A")
                })
                if progress_callback:
                    progress_callback(i + 1, len(self.results), f"GPT Enhancing: {i+1}/{len(self.results)}")
            except Exception as e:
                error_msg = f"Error processing {item['Name']} with GPT: {str(e)}"
                print(error_msg)
                # Ensure we at least have some info if it fails
                item.update({
                    "KBLI": f"Error: {str(e).split('(')[0]}",
                    "Nama Resmi KBLI": "N/A",
                    "Keterangan KBLI": "N/A",
                    "Kabupaten": "N/A",
                    "Kecamatan": "N/A",
                    "Kelurahan": "N/A"
                })

    def extract_details(self, page, url):
        page.goto(url, timeout=60000)
        page.wait_for_timeout(2000) # Wait for static render

        try:
            # Name
            name_selector = 'h1.DUwDvf' # Common class for the title, might change
            # Fallback usage of aria-label or just h1
            if page.locator(name_selector).count() == 0:
                 # Try finding h1 generically
                 name_selector = 'h1'
            
            name = page.locator(name_selector).first.text_content()
        except:
            name = "N/A"

        # Rating & Reviews
        try:
            # Look for the section with stars
            # usually has aria-label like "4.5 stars 100 reviews"
            rating_selector = 'div.F7nice' 
            request_text = page.locator(rating_selector).first.text_content()
            # Parse simplistic "4.5(200)"
            rating = request_text.split('(')[0].strip() if '(' in request_text else request_text
            review_count = request_text.split('(')[1].replace(')', '').strip() if '(' in request_text else "0"
        except:
            rating = "N/A"
            review_count = "N/A"

        # Address, Website, Phone
        # These are usually in buttons with specific data-item-id or aria-labels
        # We can look for buttons with specific icons or text patterns
        
        address = "N/A"
        website = "N/A"
        phone = "N/A"

        # Helper to find text in buttons
        try:
            # Address usually starts with button that has data-item-id="address"
            address_btn = page.locator('button[data-item-id="address"]')
            if address_btn.count() > 0:
                address = address_btn.first.get_attribute("aria-label").replace("Address: ", "")
        except: pass

        try:
             # Phone usually data-item-id starts with "phone"
             phone_btn = page.locator('button[data-item-id^="phone"]')
             if phone_btn.count() > 0:
                 phone = phone_btn.first.get_attribute("aria-label").replace("Phone: ", "")
        except: pass

        try:
            # Website
            website_btn = page.locator('a[data-item-id="authority"]')
            if website_btn.count() > 0:
                website = website_btn.first.get_attribute("href")
        except: pass

        # Extract Latitude and Longitude from URL
        latitude = "N/A"
        longitude = "N/A"
        try:
            # Wait a bit longer for potential URL updates
            page.wait_for_timeout(1000)
            current_url = page.url
            
            # 1. Try to find coordinates in the URL (@lat,lng)
            match = re.search(r'@(-?\d+\.\d+),(-?\d+\.\d+)', current_url)
            if match:
                latitude = match.group(1)
                longitude = match.group(2)
            
            # 2. If URL doesn't have it, or it seems to be the center (often found in search result pages),
            # try to find it in the page source (common for specific place pages)
            if latitude == "N/A":
                # Look for [null,null,lat,lng] pattern in script tags
                # This is a common pattern in Google Maps initialization data
                html = page.content()
                match = re.search(r'\[null,null,(-?\d+\.\d+),(-?\d+\.\d+)\]', html)
                if match:
                    latitude = match.group(1)
                    longitude = match.group(2)

            # 3. Fallback: Directions link (often has very precise coordinates)
            if latitude == "N/A":
                directions_btn = page.locator('a[href*="/dir/"]').first
                if directions_btn.count() > 0:
                    dir_url = directions_btn.get_attribute("href")
                    # Pattern in directions url is often .../lat,lng/...
                    match = re.search(r'/(-?\d+\.\d+),(-?\d+\.\d+)/', dir_url)
                    if match:
                        latitude = match.group(1)
                        longitude = match.group(2)
            
            # 4. Fallback: Meta image link
            if latitude == "N/A":
                meta_image = page.locator('meta[property="og:image"]').first.get_attribute("content")
                if meta_image:
                     match = re.search(r'center=(-?\d+\.\d+)%2C(-?\d+\.\d+)', meta_image)
                     if match:
                         latitude = match.group(1)
                         longitude = match.group(2)
        except: pass

        # Extract Status (Open, Closed, etc.)
        status = "N/A"
        try:
            # Often in a div with specific indicators or aria-label
            # Try to find text that looks like status
            status_element = page.locator('div[aria-label*="hours"], .Z_C1G, .U66pCc').first
            if status_element.count() > 0:
                status = status_element.text_content().split('·')[0].strip()
        except: pass

        # Extract Establishment / Description
        about_info = "N/A"
        try:
            # Check for a specific "About" summary or description
            # Sometimes it's in the metadata section
            desc_element = page.locator('div.PYvS7b').first # Example class for summary
            if desc_element.count() > 0:
                about_info = desc_element.text_content().strip()
            else:
                # Try finding a button that leads to About or has descriptive aria-label
                about_btn = page.locator('button[aria-label*="About"]').first
                if about_btn.count() > 0:
                     about_info = about_btn.get_attribute("aria-label")
        except: pass

        self.results.append({
            "Name": name,
            "Rating": rating,
            "Reviews": review_count,
            "Status": status,
            "Establishment": about_info,
            "Address": address,
            "Phone": phone,
            "Website": website,
            "Latitude": latitude,
            "Longitude": longitude,
            "URL": url
        })

    def save_data(self, filename="gmaps_data"):
        if not self.results:
            print("No data to save.")
            return

        df = pd.DataFrame(self.results)
        
        # Clean data
        df = df.drop_duplicates()
        
        # Save CSV
        df.to_csv(f"{filename}.csv", index=False)
        print(f"Saved data to {filename}.csv")
        
        # Save Excel
        try:
            df.to_excel(f"{filename}.xlsx", index=False)
            print(f"Saved data to {filename}.xlsx")
        except Exception as e:
            print(f"Could not save Excel: {e}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Google Maps Scraper")
    parser.add_argument("search", type=str, help="Search term (e.g., 'Coffee in Jakarta')")
    parser.add_argument("--total", type=int, default=10, help="Number of results to scrape")
    parser.add_argument("--headless", action="store_true", help="Run in headless mode")

    args = parser.parse_args()
    
    scraper = GoogleMapsScraper()
    scraper.run(args.search, args.total, args.headless)
    scraper.save_data(f"gmaps_{args.search.replace(' ', '_')}")
