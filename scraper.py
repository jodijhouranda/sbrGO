import re
import math
import argparse
from playwright.sync_api import sync_playwright
import pandas as pd
import time
import json
import requests
from openai import OpenAI

class GoogleMapsScraper:
    def __init__(self, api_key=None):
        self.results = []
        self.api_key = api_key
        self.client = OpenAI(api_key=api_key) if api_key else None

    def reverse_geocode(self, lat, lng):
        """Fetch administrative data from Nominatim (OpenStreetMap)."""
        if lat == "N/A" or lng == "N/A":
            return {}
        
        try:
            # Respect OSM usage policy: Custom User-Agent and delay
            headers = {'User-Agent': 'sbrGO-Scraper/1.0 (contact@example.com)'}
            url = f"https://nominatim.openstreetmap.org/reverse?format=json&lat={lat}&lon={lng}&zoom=18&addressdetails=1"
            response = requests.get(url, headers=headers, timeout=10)
            if response.status_code == 200:
                data = response.json()
                address = data.get('address', {})
                return {
                    "Kabupaten": address.get('city') or address.get('regency') or address.get('county') or "N/A",
                    "Kecamatan": address.get('district') or address.get('subdistrict') or address.get('city_district') or "N/A",
                    "Kelurahan": address.get('village') or address.get('suburb') or address.get('neighbourhood') or "N/A"
                }
        except Exception as e:
            print(f"Geocoding error: {e}")
        return {}

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

    def enrich_results(self, progress_callback=None):
        """Perform reverse geocoding for all results."""
        print(f"Enriching {len(self.results)} results with Geocoding...")
        for i, item in enumerate(self.results):
            if progress_callback:
                progress_callback(i + 1, len(self.results), f"Geocoding: {i+1}/{len(self.results)}")
            
            geo_data = self.reverse_geocode(item.get('Latitude'), item.get('Longitude'))
            if geo_data:
                item.update(geo_data)
            
            # Rate limit protection for OSM
            time.sleep(1)

    def process_with_gpt(self, api_key=None, progress_callback=None):
        if api_key:
            self.api_key = api_key
            self.client = OpenAI(api_key=api_key)
        
        if not self.client:
            print("OpenAI client not initialized. Skipping GPT enhancement.")
            return

        print(f"Enhancing {len(self.results)} results with GPT...")
        for i, item in enumerate(self.results):
            print(f"[{i+1}/{len(self.results)}] Processing: {item['Name']}")

            # GPT for KBLI and fallback for missing geo fields
            prompt = f"""
            Analyze the following business information from Google Maps and provide structured data in JSON format.
            Business Name: {item['Name']}
            Address: {item['Address']}
            Position: {item.get('Provinsi')}/{item.get('Kabupaten')}/{item.get('Kecamatan')}/{item.get('Kelurahan')}
            
            Return the following fields:
            - kbli: Predict the 5-digit KBLI 2020 code (Indonesian Standard Industrial Classification).
            - nama_kbli: The official title (Nama Resmi) for this KBLI code exactly as it appears in the OSS (Online Single Submission) system / KBLI 2020.
            - keterangan_kbli: Brief description/scope of the KBLI category based on OSS regulations.
            - provinsi: Use provided Geo Data if available, otherwise extract from address.
            - kabupaten: The Regency/City (Kabupaten/Kota). Use provided Geo Data if available, otherwise extract from address.
            - kecamatan: The District (Kecamatan). Use provided Geo Data if available, otherwise extract from address.
            - kelurahan: The Sub-district/Village (Kelurahan/Desa). Use provided Geo Data if available, otherwise extract from address.
            - kode_pos: The Postal Code. Use provided Geo Data if available, otherwise extract from address.

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
                
                # Update with GPT data, prioritizing Geocoding data for position
                item.update({
                    "KBLI": gpt_data.get("kbli", "N/A"),
                    "Nama Resmi KBLI": gpt_data.get("nama_kbli", "N/A"),
                    "Keterangan KBLI": gpt_data.get("keterangan_kbli", "N/A"),
                    "Provinsi": gpt_data.get("provinsi", item.get("Provinsi", "N/A")),
                    "Kabupaten": gpt_data.get("kabupaten", item.get("Kabupaten", "N/A")),
                    "Kecamatan": gpt_data.get("kecamatan", item.get("Kecamatan", "N/A")),
                    "Kelurahan": gpt_data.get("kelurahan", item.get("Kelurahan", "N/A")),
                    "Kode Pos": gpt_data.get("kode_pos", item.get("Kode Pos", "N/A"))
                })
                
                if progress_callback:
                    progress_callback(i + 1, len(self.results), f"AI Analysis: {i+1}/{len(self.results)}")
            except Exception as e:
                error_msg = f"Error processing {item['Name']}: {str(e)}"
                print(error_msg)
                item.update({
                    "KBLI": f"Error: {str(e).split('(')[0]}",
                    "Nama Resmi KBLI": "N/A",
                    "Keterangan KBLI": "N/A"
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
            # More robust selector for rating and review count
            # Often in a div with role="img" and aria-label containing rating/reviews
            # Or in div.F7nice
            rating_element = page.locator('div.F7nice').first
            if rating_element.count() > 0:
                request_text = rating_element.text_content()
                # Parse "4.5 (200)"
                if '(' in request_text:
                    rating = request_text.split('(')[0].strip()
                    review_count = request_text.split('(')[1].replace(')', '').replace(',', '').strip()
                else:
                    rating = request_text.strip()
                    review_count = "0"
            else:
                # Try aria-label fallback for hidden elements
                stars_label = page.locator('span[aria-label*="stars"]').first
                if stars_label.count() > 0:
                    label = stars_label.get_attribute("aria-label")
                    # "4.5 stars 100 reviews"
                    rating = label.split(' ')[0]
                    review_count = label.split('stars ')[1].split(' ')[0] if 'stars ' in label else "0"
                else:
                    rating = "N/A"
                    review_count = "N/A"
        except:
            rating = "N/A"
            review_count = "N/A"

        # Address, Website, Phone
        address = "N/A"
        website = "N/A"
        phone = "N/A"

        try:
            address_btn = page.locator('button[data-item-id="address"]')
            if address_btn.count() > 0:
                address = address_btn.first.get_attribute("aria-label").replace("Address: ", "")
        except: pass

        try:
             phone_btn = page.locator('button[data-item-id^="phone"]')
             if phone_btn.count() > 0:
                 phone = phone_btn.first.get_attribute("aria-label").replace("Phone: ", "")
        except: pass

        try:
            website_btn = page.locator('a[data-item-id="authority"]')
            if website_btn.count() > 0:
                website = website_btn.first.get_attribute("href")
        except: pass

        # Extract Operation Hours (New)
        operation_hours = "N/A"
        try:
            # Look for hours button/section
            hours_btn = page.locator('div[aria-label*="hours"], button[aria-label*="hours"]').first
            if hours_btn.count() > 0:
                # Try to get the raw text first (often says "Open now · 08.00–17.00")
                operation_hours = hours_btn.text_content().strip()
                # If it's just a summary, we could potentially click to get more, 
                # but let's start with the visible text which is usually what users want.
        except: pass

        # Extract Latest Review Time (New)
        latest_review_time = "N/A"
        try:
            # Look for review snippets usually shown on the main page
            # These are often in div.wiUu6 or aria-labels
            review_snippet = page.locator('div[role="region"] div.jftiEf').first
            if review_snippet.count() > 0:
                # The relative time is usually in a span or specific class like .rS69Wb
                time_el = review_snippet.locator('span.rS69Wb').first
                if time_el.count() > 0:
                    latest_review_time = time_el.text_content().strip()
        except: pass

        # Extract Latitude and Longitude from URL
        latitude = "N/A"
        longitude = "N/A"
        try:
            page.wait_for_timeout(1000)
            current_url = page.url
            match = re.search(r'@(-?\d+\.\d+),(-?\d+\.\d+)', current_url)
            if match:
                latitude = match.group(1)
                longitude = match.group(2)
            
            if latitude == "N/A":
                html = page.content()
                match = re.search(r'\[null,null,(-?\d+\.\d+),(-?\d+\.\d+)\]', html)
                if match:
                    latitude = match.group(1)
                    longitude = match.group(2)

            if latitude == "N/A":
                directions_btn = page.locator('a[href*="/dir/"]').first
                if directions_btn.count() > 0:
                    dir_url = directions_btn.get_attribute("href")
                    match = re.search(r'/(-?\d+\.\d+),(-?\d+\.\d+)/', dir_url)
                    if match:
                        latitude = match.group(1)
                        longitude = match.group(2)
        except: pass

        self.results.append({
            "Name": name,
            "Rating": rating,
            "Reviews": review_count,
            "Operation Hours": operation_hours,
            "Latest Review": latest_review_time,
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
