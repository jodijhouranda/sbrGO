import streamlit as st
import pandas as pd
from sqlalchemy import text
import io
import time
import os
from streamlit_folium import st_folium
import folium

# --- CUSTOM CSS (Mengembalikan Desain Tombol yang Bagus) ---
st.markdown("""
<style>
    /* Styling Container Utama agar lebih rapi */
    .block-container {
        padding-top: 2rem;
    }
    
    /* Styling Judul */
    .subtitle {
        font-size: 1.2rem;
        color: #64748b;
        margin-bottom: 20px;
    }

    /* Styling Metric Cards */
    div[data-testid="stMetric"] {
        background-color: #f8fafc;
        padding: 15px;
        border-radius: 10px;
        border: 1px solid #e2e8f0;
        box-shadow: 0 1px 3px rgba(0,0,0,0.05);
    }

    /* Styling Tombol agar Seragam dan Full Width */
    div.stButton > button, div.stDownloadButton > button {
        width: 100%;
        border-radius: 8px;
        font-weight: 600;
        padding: 0.5rem 1rem;
        transition: all 0.3s ease;
        border: none;
    }

    /* Warna Tombol Delete (Merah) - Kita akan target via key/urutan nanti, 
       tapi ini default hover effect */
    div.stButton > button:hover {
        transform: translateY(-2px);
        box-shadow: 0 4px 6px rgba(0,0,0,0.1);
    }
    
    /* Header Dashboard */
    .dashboard-header {
        background: linear-gradient(135deg, #4f46e5 0%, #7c3aed 100%);
        padding: 20px;
        border-radius: 15px;
        margin-bottom: 25px;
        color: white;
        box-shadow: 0 10px 15px -3px rgba(0, 0, 0, 0.1);
    }
</style>
""", unsafe_allow_html=True)

st.markdown('<p class="subtitle">Search and manage your collected business data.</p>', unsafe_allow_html=True)

# --- DATABASE CONNECTION ---
cert_path = "isrgrootx1.pem"
connect_args = {}
# Cek sertifikat jika ada (untuk local/deploy flexibility)
if os.path.exists(cert_path):
    connect_args = {"ssl": {"ca": os.path.abspath(cert_path)}}

try:
    conn = st.connection('tidb', type='sql', connect_args=connect_args)
except Exception as e:
    st.error(f"Gagal menghubungkan ke database: {e}")
    st.stop()

# --- HELPER FUNCTIONS ---
@st.cache_data(ttl=0)
def fetch_db_data(username, is_superuser):
    try:
        query = "SELECT * FROM scraped_results"
        params = {}
        if not is_superuser:
            query += " WHERE username = :user"
            params['user'] = username
        return conn.query(query, params=params, ttl=0)
    except Exception as e:
        st.warning(f"Error fetching data: {e}")
        return None

def delete_records(ids):
    try:
        with conn.session as session:
            for rid in ids:
                if st.session_state.get('is_superuser', False):
                    session.execute(text("DELETE FROM scraped_results WHERE id = :id"), {"id": rid})
                else:
                    session.execute(text("DELETE FROM scraped_results WHERE id = :id AND username = :user"), 
                                    {"id": rid, "user": st.session_state.get('username')})
            session.commit()
        st.cache_data.clear()
        return True
    except Exception as e:
        st.error(f"Error deleting: {e}")
        return False

def deduplicate_db(df):
    if df is None or df.empty: return True
    try:
        df_unique = df.sort_values('scraped_at', ascending=False).drop_duplicates(
            subset=['Name', 'Latitude', 'Longitude'], keep='first'
        )
        with conn.session as session:
            if st.session_state.get('is_superuser', False):
                session.execute(text("DELETE FROM scraped_results"))
            else:
                session.execute(text("DELETE FROM scraped_results WHERE username = :user"), 
                                {"user": st.session_state.get('username')})
            session.commit()
        df_unique.to_sql('scraped_results', con=conn.engine, if_exists='append', index=False)
        st.cache_data.clear()
        return True
    except Exception as e:
        st.error(f"Error: {e}")
        return False

def format_wa_link(phone):
    if pd.isna(phone): return None
    clean_phone = "".join(filter(str.isdigit, str(phone)))
    if not clean_phone: return None
    if clean_phone.startswith('08'): return f"https://wa.me/62{clean_phone[1:]}"
    elif clean_phone.startswith('62'): return f"https://wa.me/{clean_phone}"
    elif clean_phone.startswith('8'): return f"https://wa.me/62{clean_phone}"
    return None

# --- DIALOGS ---
@st.dialog("Konfirmasi Penghapusan")
def confirm_delete_dialog(selected_ids):
    st.markdown(f"### ⚠️ Hapus Data?")
    st.write(f"Anda akan menghapus **{len(selected_ids)}** data terpilih secara permanen.")
    
    col_yes, col_no = st.columns(2)
    with col_yes:
        if st.button("Ya, Hapus", type="primary", use_container_width=True):
            # Progress Bar UI
            progress_bar = st.progress(0, text="Menghubungkan ke database...")
            for i in range(100):
                time.sleep(0.005) # Animasi cepat
                progress_bar.progress(i + 1, text="Menghapus data...")
            
            if delete_records(selected_ids):
                progress_bar.progress(100, text="Selesai!")
                st.session_state.refresh_needed = True
                st.success("Data berhasil dihapus.")
                time.sleep(0.5)
                st.rerun()
            else:
                st.error("Gagal menghapus.")
    with col_no:
        if st.button("Batal", use_container_width=True):
            st.rerun()

# --- MAIN APP LOGIC ---

# Setup Session State Default
if 'username' not in st.session_state: st.session_state.username = 'demo_user' 
if 'is_superuser' not in st.session_state: st.session_state.is_superuser = False
if 'refresh_needed' not in st.session_state: st.session_state.refresh_needed = False

# Load Data
if 'df_db_v5' not in st.session_state or st.session_state.refresh_needed:
    raw_data = fetch_db_data(st.session_state.username, st.session_state.is_superuser)
    if raw_data is not None and not raw_data.empty:
        df_init = raw_data.copy()
        # Ensure Select column exists
        if "Select" not in df_init.columns:
            df_init.insert(0, "Select", False)
        else:
            df_init["Select"] = False # Reset selection on reload
        st.session_state.df_db_v5 = df_init
    else:
        st.session_state.df_db_v5 = pd.DataFrame()
    st.session_state.refresh_needed = False

df_db = st.session_state.df_db_v5

# --- UI RENDER ---

if not df_db.empty:
    # Header Dashboard
    st.markdown(f"""
    <div class="dashboard-header">
        <h3 style="margin:0; font-size: 1.5rem;">📊 Data Insights Dashboard</h3>
        <p style="margin:0; opacity: 0.9; font-size: 0.9rem;">Workspace: {st.session_state.username}</p>
    </div>
    """, unsafe_allow_html=True)
    
    # Metrics
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Total Data", f"{len(df_db):,}")
    m2.metric("Kota/Kab", df_db['Kabupaten'].nunique() if 'Kabupaten' in df_db.columns else 0)
    m3.metric("Provinsi", df_db['Provinsi'].nunique() if 'Provinsi' in df_db.columns else 0)
    kbli_count = df_db['KBLI'].astype(str).str[:2].nunique() if 'KBLI' in df_db.columns else 0
    m4.metric("Kategori (KBLI)", kbli_count)

    st.write("") # Spacer

    # --- TABLE EDITOR ---
    # Catatan: Kita menaruh ini DI LUAR form agar download button bisa sejajar.
    # Namun data_editor cukup efisien. 
    
    config = {
        "Select": st.column_config.CheckboxColumn("✅", width="small", default=False),
        "scraped_at": st.column_config.DatetimeColumn("Waktu Scrape", format="D MMM, HH:mm"),
        "URL": st.column_config.LinkColumn("Maps"),
        "Phone": st.column_config.TextColumn("Telepon"),
        "Rating": st.column_config.NumberColumn("⭐", format="%.1f"),
    }
    
    # Hide technical columns if needed
    cols_to_show = ["Select", "Name", "Phone", "Rating", "Alamat", "Kabupaten", "KBLI", "URL", "scraped_at"]
    # Filter columns that actually exist
    cols_to_show = [c for c in cols_to_show if c in df_db.columns]
    
    # Tampilkan tabel
    edited_df = st.data_editor(
        df_db,
        column_config=config,
        column_order=cols_to_show,
        disabled=[c for c in df_db.columns if c != "Select"],
        hide_index=True,
        use_container_width=True,
        height=400,
        key="main_editor"
    )

    st.write("") # Spacer

    # --- ACTION BUTTONS (LAYOUT SERAGAM) ---
    # 3 Kolom sejajar: Delete | Deduplicate | Export
    
    # Persiapan Data Excel
    excel_buffer = io.BytesIO()
    with pd.ExcelWriter(excel_buffer, engine='openpyxl') as wr:
        output_df = edited_df.drop(columns=['Select']) if 'Select' in edited_df.columns else edited_df
        output_df.to_excel(wr, index=False)
    excel_data = excel_buffer.getvalue()

    c_act1, c_act2, c_act3 = st.columns(3)

    # 1. Tombol Delete
    with c_act1:
        # Kita pakai session state trigger manual untuk cek seleksi
        if st.button("🗑️ Delete Selected", type="primary", use_container_width=True):
            selected = edited_df[edited_df["Select"] == True]
            if not selected.empty:
                confirm_delete_dialog(selected["id"].tolist())
            else:
                st.warning("Pilih data dulu!")

    # 2. Tombol Deduplicate
    with c_act2:
        if st.button("♻️ Remove Duplicates", use_container_width=True):
            with st.spinner("Membersihkan duplikat..."):
                if deduplicate_db(df_db):
                    st.session_state.refresh_needed = True
                    st.success("Duplikat dihapus!")
                    time.sleep(1)
                    st.rerun()

    # 3. Tombol Export (Penyebab error sebelumnya, sekarang aman di luar form)
    with c_act3:
        st.download_button(
            label="📥 Export Excel",
            data=excel_data,
            file_name=f"data_export_{int(time.time())}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True
        )

    st.markdown("---")

    # --- MAP SECTION ---
    st.markdown("### 🗺️ Peta Sebaran")
    map_df = df_db.copy()
    map_df['lat'] = pd.to_numeric(map_df['Latitude'], errors='coerce')
    map_df['lng'] = pd.to_numeric(map_df['Longitude'], errors='coerce')
    map_df = map_df.dropna(subset=['lat', 'lng'])

    if not map_df.empty:
        # Center map
        avg_lat = map_df['lat'].mean()
        avg_lng = map_df['lng'].mean()
        m = folium.Map(location=[avg_lat, avg_lng], zoom_start=10, tiles='CartoDB positron')
        
        # Cluster marker agar tidak berat jika data banyak
        from folium.plugins import MarkerCluster
        marker_cluster = MarkerCluster().add_to(m)

        for _, row in map_df.iterrows():
            wa = format_wa_link(row.get('Phone', ''))
            wa_btn = f'<a href="{wa}" target="_blank" style="text-decoration:none; color:white; background:#25D366; padding:5px 10px; border-radius:5px;">Chat WA</a>' if wa else ""
            popup_html = f"""
            <div style="font-family:sans-serif; width:200px;">
                <b>{row['Name']}</b><br>
                <span style="color:gray; font-size:0.8em;">{row.get('Alamat', '')}</span><br><br>
                {wa_btn}
            </div>
            """
            folium.Marker(
                [row['lat'], row['lng']],
                popup=popup_html,
                icon=folium.Icon(color="blue", icon="info-sign")
            ).add_to(marker_cluster)
            
        st_folium(m, width="100%", height=500, returned_objects=[])

else:
    st.info("Belum ada data yang tersimpan.")