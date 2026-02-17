import streamlit as st
import pandas as pd
from sqlalchemy import text
import io
import time

# Premium UI Styling (Shared)
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;600&display=swap');
    
    html, body, [data-testid="stStandardType"] {
        font-family: 'Outfit', sans-serif;
    }
    
    .stApp {
        background: radial-gradient(circle at top right, #f8f9ff 0%, #ffffff 100%);
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
</style>
""", unsafe_allow_html=True)

import os

# Resolve absolute path for SSL CA
cert_path = os.path.abspath("isrgrootx1.pem")

try:
    # We pass connect_args to ensure SSL is used correctly on Windows
    conn = st.connection('tidb', type='sql', connect_args={
        "ssl": {"ca": cert_path}
    })
except Exception as e:
    st.error(f"Gagal menghubungkan ke database: {e}")
    st.info("Pastikan [connections.tidb] sudah terkonfigurasi di secrets.toml dan isrgrootx1.pem tersedia.")
    st.stop()

def fetch_db_data():
    """Fetch all data from TiDB using st.connection."""
    try:
        # st.connection object has query() method
        return conn.query("SELECT * FROM scraped_results", ttl=0)
    except Exception as e:
        st.warning("Database table mungkin belum ada atau kosong.")
        return None

def delete_records(names_locations):
    """Delete selected records from TiDB."""
    try:
        with conn.session as session:
            for name, lat, lng in names_locations:
                query = text("DELETE FROM scraped_results WHERE Name = :name AND Latitude = :lat AND Longitude = :lng")
                session.execute(query, {"name": name, "lat": lat, "lng": lng})
            session.commit()
        return True
    except Exception as e:
        st.error(f"Error deleting records: {e}")
        return False

def deduplicate_db():
    """Remove duplicates based on Name and Location (Lat/Lng)."""
    try:
        with conn.session as session:
            # Modern SQL deduplication using CTE or Temporary Table
            session.execute(text("CREATE TEMPORARY TABLE temp_unique_results AS SELECT * FROM (SELECT *, ROW_NUMBER() OVER (PARTITION BY Name, Latitude, Longitude ORDER BY scraped_at DESC) as rn FROM scraped_results) t WHERE rn = 1"))
            session.execute(text("DELETE FROM scraped_results"))
            # We need to list columns explicitly if the table has auto-increment or extra cols, 
            # but since we matched it previously, it should work. 
            # Listing them is safer.
            cols = ["Name", "Rating", "Reviews", "`Operation Hours`", "`Latest Review`", "Address", "Phone", "Website", "Latitude", "Longitude", "URL", "Negara", "Provinsi", "Kabupaten", "Kecamatan", "Kelurahan", "`Hamlet/Quarter`", "Jalan", "Nomor", "`Kode Pos`", "`Kategori OSM`", "KBLI", "`Nama Resmi KBLI`", "`Keterangan KBLI`", "`WhatsApp Link`", "scraped_at"]
            col_str = ", ".join(cols)
            session.execute(text(f"INSERT INTO scraped_results ({col_str}) SELECT {col_str} FROM temp_unique_results"))
            session.execute(text("DROP TEMPORARY TABLE temp_unique_results"))
            session.commit()
        return True
    except Exception as e:
        st.error(f"Error deduplicating: {e}")
        return False

df_db = fetch_db_data()

if df_db is not None and not df_db.empty:
    # --- PREMIUM DASHBOARD METRICS ---
    st.markdown("""
    <div style="background: linear-gradient(135deg, #6366f1 0%, #a855f7 100%); 
                padding: 20px; border-radius: 15px; margin-bottom: 25px; color: white;">
        <h3 style="margin:0; color: white; font-size: 1.5rem;">📊 Data Insights Dashboard</h3>
        <p style="margin:0; opacity: 0.8; font-size: 0.9rem;">Real-time analytics from your database</p>
    </div>
    """, unsafe_allow_html=True)
    
    m_col1, m_col2, m_col3, m_col4 = st.columns(4)
    
    with m_col1:
        st.metric("Total Establishments", f"{len(df_db):,}")
    
    with m_col2:
        cities = df_db['Kabupaten'].nunique() if 'Kabupaten' in df_db.columns else 0
        st.metric("Total Cities", f"{cities}")
        
    with m_col3:
        provinces = df_db['Provinsi'].nunique() if 'Provinsi' in df_db.columns else 0
        st.metric("Total Provinces", f"{provinces}")
        
    with m_col4:
        # Calculate Unique 2-Digit KBLI
        kbli_2digit = 0
        if 'KBLI' in df_db.columns:
            # Safe conversion to string and slicing first 2 digits
            kbli_series = df_db['KBLI'].astype(str).str.strip().str[:2]
            # Filter out 'na', 'No', 'N/', or empty
            kbli_series = kbli_series[kbli_series.str.match(r'^\d{2}$', na=False)]
            kbli_2digit = kbli_series.nunique()
        st.metric("Unique KBLI 2-Digit", f"{kbli_2digit}")

    st.markdown("<br>", unsafe_allow_html=True)

    # --- TABLE SECTION ---
    st.markdown('<p style="color:#64748b; font-size:0.8rem; text-transform:uppercase; letter-spacing:1px; margin-bottom:-10px;">Master Data Storage</p>', unsafe_allow_html=True)
    st.markdown('<p style="font-size:1.5rem; font-weight:600; color:#1e293b;">📋 Scraped Results Table</p>', unsafe_allow_html=True)

    df_display = df_db.copy()
    df_display.insert(0, "Select", False)
    
    edited_df = st.data_editor(
        df_display,
        column_config={
            "Select": st.column_config.CheckboxColumn("Select", default=False),
            "scraped_at": st.column_config.DatetimeColumn("Waktu Scrape"),
            "URL": st.column_config.LinkColumn("G-Maps"),
            "WhatsApp Link": st.column_config.LinkColumn("WA", width="small"),
            "Rating": st.column_config.NumberColumn("Rating", format="%.1f ⭐"),
            "Reviews": st.column_config.NumberColumn("Reviews", format="%d")
        },
        disabled=[c for c in df_display.columns if c != "Select"],
        hide_index=True,
        use_container_width=True,
        key="db_editor"
    )
    
    # --- ACTION BUTTONS ---
    st.markdown("<br>", unsafe_allow_html=True)
    act_col1, act_col2, act_col3 = st.columns([1, 1, 1])
    
    with act_col1:
        if st.button("🔄 Remove Duplicates", use_container_width=True):
            if deduplicate_db():
                st.success("Duplicates removed!")
                time.sleep(1)
                st.rerun()
    
    with act_col2:
        buffer = io.BytesIO()
        with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
            df_db.to_excel(writer, index=False)
        st.download_button(
            label="📥 Export Excel (All)",
            data=buffer.getvalue(),
            file_name="sbrgo_database_export.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True
        )

    with act_col3:
        selected_rows = edited_df[edited_df["Select"] == True]
        if not selected_rows.empty:
            if st.button(f"🗑️ Delete ({len(selected_rows)})", type="primary", use_container_width=True):
                to_delete = []
                for _, row in selected_rows.iterrows():
                    to_delete.append((row["Name"], row["Latitude"], row["Longitude"]))
                
                if delete_records(to_delete):
                    st.success("Records deleted!")
                    time.sleep(1)
                    st.rerun()
    
    # --- MAP AT THE BOTTOM ---
    st.markdown("---")
    st.markdown('<p style="color:#64748b; font-size:0.8rem; text-transform:uppercase; letter-spacing:1px; margin-bottom:5px;">Spatial Distribution</p>', unsafe_allow_html=True)
    st.markdown('<p style="font-size:1.5rem; font-weight:600; color:#1e293b; margin-top:0;">🗺️ Database Coverage Map</p>', unsafe_allow_html=True)
    
    import folium
    from streamlit_folium import st_folium
    
    map_df = df_db.copy()
    map_df['latitude'] = pd.to_numeric(map_df['Latitude'], errors='coerce')
    map_df['longitude'] = pd.to_numeric(map_df['Longitude'], errors='coerce')
    map_df = map_df.dropna(subset=['latitude', 'longitude'])
    
    if not map_df.empty:
        avg_lat = map_df['latitude'].mean()
        avg_lng = map_df['longitude'].mean()
        m = folium.Map(location=[avg_lat, avg_lng], zoom_start=6, control_scale=True)
        for _, row in map_df.iterrows():
            folium.Marker(
                [row['latitude'], row['longitude']],
                popup=f"{row['Name']}<br>⭐ {row.get('Rating', 'N/A')}",
                tooltip=row['Name'],
                icon=folium.Icon(color="indigo", icon="info-sign")
            ).add_to(m)
        st_folium(m, width="100%", height=500, returned_objects=[], key="db_explorer_map")
    else:
        st.info("Tidak ada data koordinat untuk ditampilkan di peta.")

else:
    st.info("Database kosong atau belum terhubung. Silakan gunakan Scraper terlebih dahulu.")
