import streamlit as st
import pandas as pd
from sqlalchemy import text
import io
import time

st.set_page_config(page_title="NoSBRGo - Database Explorer", page_icon="📦", layout="wide")

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

try:
    conn = st.connection('tidb', type='sql')
except Exception as e:
    st.error(f"Gagal menghubungkan ke database: {e}")
    st.info("Pastikan [connections.tidb] sudah terkonfigurasi di secrets.toml")
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

st.markdown('<p style="font-size:2rem; font-weight:800; color:#1e293b;">📦 Database Explorer</p>', unsafe_allow_html=True)
st.markdown('<p class="subtitle">Manage and Analyze your saved business data.</p>', unsafe_allow_html=True)

df_db = fetch_db_data()

if df_db is not None and not df_db.empty:
    act_col1, act_col2, act_col3 = st.columns(3)
    
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
        st.metric("Total Records", len(df_db))

    st.markdown("---")
    
    df_display = df_db.copy()
    df_display.insert(0, "Select", False)
    
    edited_df = st.data_editor(
        df_display,
        column_config={
            "Select": st.column_config.CheckboxColumn("Select", default=False),
            "scraped_at": st.column_config.DatetimeColumn("Waktu Scrape"),
            "URL": st.column_config.LinkColumn("G-Maps")
        },
        disabled=[c for c in df_display.columns if c != "Select"],
        hide_index=True,
        use_container_width=True,
        key="db_editor"
    )
    
    selected_rows = edited_df[edited_df["Select"] == True]
    
    if not selected_rows.empty:
        st.warning(f"Terpilih {len(selected_rows)} data untuk dihapus.")
        if st.button("🗑️ Delete Selected", type="primary", use_container_width=True):
            to_delete = []
            for _, row in selected_rows.iterrows():
                to_delete.append((row["Name"], row["Latitude"], row["Longitude"]))
            
            if delete_records(to_delete):
                st.success(f"Berhasil menghapus {len(to_delete)} data.")
                time.sleep(1)
                st.rerun()
else:
    st.info("Database kosong atau belum terhubung. Silakan gunakan Scraper terlebih dahulu.")
