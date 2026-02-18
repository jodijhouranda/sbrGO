import streamlit as st
import pandas as pd
from sqlalchemy import text
import io
import time
import os

# --- PAGE CONFIG ---
st.set_page_config(page_title="Business Data Manager", layout="wide")

st.markdown('<p class="subtitle">Search and manage your collected business data.</p>', unsafe_allow_html=True)

# --- DATABASE CONNECTION ---
# Pastikan file sertifikat ada, atau handle errornya
cert_path = "isrgrootx1.pem"
connect_args = {}
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
    """Fetch data filtered by user unless superuser."""
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
    """Delete records with user isolation."""
    try:
        with conn.session as session:
            for rid in ids:
                if st.session_state.get('is_superuser', False):
                    session.execute(text("DELETE FROM scraped_results WHERE id = :id"), {"id": rid})
                else:
                    session.execute(text("DELETE FROM scraped_results WHERE id = :id AND username = :user"), 
                                    {"id": rid, "user": st.session_state.get('username')})
            session.commit()
        st.cache_data.clear() # Clear cache after deletion
        return True
    except Exception as e:
        st.error(f"Error deleting: {e}")
        return False

def deduplicate_db(df):
    """Refined deduplication with user isolation."""
    if df is None or df.empty: return True
    try:
        # User only deduplicates their own data (fetched in df)
        df_unique = df.sort_values('scraped_at', ascending=False).drop_duplicates(
            subset=['Name', 'Latitude', 'Longitude'], keep='first'
        )
        with conn.session as session:
            if st.session_state.get('is_superuser', False):
                session.execute(text("DELETE FROM scraped_results")) # Wipe all if superuser
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
    st.warning(f"⚠️ Anda telah memilih **{len(selected_ids)}** data untuk dihapus.")
    st.write("Tindakan ini tidak dapat dibatalkan. Apakah Anda yakin?")
    
    col_yes, col_no = st.columns(2)
    
    with col_yes:
        if st.button("Ya, Hapus Data", type="primary", use_container_width=True):
            # Progress Bar UI
            progress_text = "Sedang menghapus data dari database..."
            my_bar = st.progress(0, text=progress_text)

            # Simulasi progress (opsional, untuk UX agar tidak kaget tiba-tiba hilang)
            for percent_complete in range(100):
                time.sleep(0.01) # delay sangat kecil
                my_bar.progress(percent_complete + 1, text=progress_text)
            
            # Eksekusi Hapus Database
            if delete_records(selected_ids):
                my_bar.empty()
                st.session_state.refresh_needed = True
                st.success(f"Berhasil menghapus {len(selected_ids)} data!")
                time.sleep(1)
                st.rerun()
            else:
                st.error("Gagal menghapus data.")

    with col_no:
        if st.button("Batal", use_container_width=True):
            st.rerun()

# --- MAIN UI ---

# Mock login session for testing if not exists
if 'username' not in st.session_state:
    st.session_state.username = 'test_user' # Default fallback
if 'is_superuser' not in st.session_state:
    st.session_state.is_superuser = False

# Data Loading Logic
if 'df_db_v5' not in st.session_state or st.session_state.get('refresh_needed', False):
    raw_data = fetch_db_data(st.session_state.get('username'), st.session_state.get('is_superuser', False))
    if raw_data is not None and not raw_data.empty:
        df_init = raw_data.copy()
        df_init.insert(0, "Select", False) # Reset checkbox on reload
        st.session_state.df_db_v5 = df_init
    else:
        st.session_state.df_db_v5 = pd.DataFrame()
    st.session_state.refresh_needed = False

df_db = st.session_state.df_db_v5

if not df_db.empty:
    # Header Metric
    st.markdown(f'<div style="background: linear-gradient(135deg, #6366f1 0%, #a855f7 100%); padding: 20px; border-radius: 15px; margin-bottom: 25px; color: white;"><h3 style="margin:0; color: white; font-size: 1.5rem;">📊 Data Insights Dashboard</h3><p style="margin:0; opacity: 0.8; font-size: 0.9rem;">Filtering data for: {st.session_state.username}</p></div>', unsafe_allow_html=True)
    
    m_col1, m_col2, m_col3, m_col4 = st.columns(4)
    m_col1.metric("Establishments", f"{len(df_db):,}")
    m_col2.metric("Cities", df_db['Kabupaten'].nunique() if 'Kabupaten' in df_db.columns else 0)
    m_col3.metric("Provinces", df_db['Provinsi'].nunique() if 'Provinsi' in df_db.columns else 0)
    kbli_2 = 0
    if 'KBLI' in df_db.columns:
        kb_s = df_db['KBLI'].astype(str).str.strip().str[:2]
        kbli_2 = kb_s[kb_s.str.match(r'^\d{2}$', na=False)].nunique()
    m_col4.metric("KBLI 2-Digit", kbli_2)

    st.markdown("<br>", unsafe_allow_html=True)
    
    # --- TABLE & ACTIONS FORM ---
    # Kita gunakan st.form agar saat checkbox dicentang TIDAK ada reload/loading.
    # Semua aksi baru diproses saat salah satu tombol ditekan.
    
    with st.form("data_management_form", border=False):
        
        # 1. Konfigurasi Tabel
        config = {
            "Select": st.column_config.CheckboxColumn("Select", default=False),
            "scraped_at": st.column_config.DatetimeColumn("Waktu Scrape"),
            "URL": st.column_config.LinkColumn("G-Maps"),
            "WhatsApp Link": st.column_config.LinkColumn("WA"),
            "Rating": st.column_config.NumberColumn("Rating", format="%.1f ⭐"),
        }
        disabled_cols = [c for c in df_db.columns if c != "Select"]

        # 2. Render Tabel
        edited_df = st.data_editor(
            df_db, 
            column_config=config, 
            disabled=disabled_cols, 
            hide_index=True, 
            use_container_width=True, 
            key="db_editor_main"
        )
        
        st.markdown("<br>", unsafe_allow_html=True)

        # 3. Action Buttons (Uniform Layout)
        # Menyiapkan file Excel terlebih dahulu agar bisa dimasukkan ke download_button
        excel_buffer = io.BytesIO()
        with pd.ExcelWriter(excel_buffer, engine='openpyxl') as wr:
            # Export versi bersih (tanpa kolom Select)
            export_df = edited_df.drop(columns=['Select']) if 'Select' in edited_df.columns else edited_df
            export_df.to_excel(wr, index=False)
        excel_data = excel_buffer.getvalue()

        # Layout 3 Kolom Sejajar
        c1, c2, c3 = st.columns(3)
        
        with c1:
            # Tombol Delete (Submit Button)
            delete_pressed = st.form_submit_button("🗑️ Hapus Terpilih", type="primary", use_container_width=True)
        
        with c2:
            # Tombol Deduplicate (Submit Button)
            dedup_pressed = st.form_submit_button("♻️ Hapus Duplikat", use_container_width=True)
            
        with c3:
            # Tombol Export (Download Button - di dalam form ia bertindak sebagai submit juga)
            st.download_button(
                label="📥 Export Excel",
                data=excel_data,
                file_name="data_export.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True
            )

    # --- ACTION LOGIC HANDLERS ---
    # Logika ini berjalan SETELAH form disubmit (salah satu tombol ditekan)
    
    if delete_pressed:
        # Ambil data yang dicentang dari hasil editan terakhir (edited_df)
        selected_rows = edited_df[edited_df["Select"] == True]
        
        if not selected_rows.empty:
            # Panggil dialog konfirmasi
            # Kita gunakan session state atau pemanggilan fungsi dialog langsung
            ids_to_del = selected_rows["id"].tolist() if "id" in selected_rows.columns else []
            confirm_delete_dialog(ids_to_del)
        else:
            st.warning("⚠️ Silakan centang kotak 'Select' pada tabel terlebih dahulu.")

    if dedup_pressed:
        with st.spinner("Sedang membersihkan duplikat..."):
            if deduplicate_db(df_db):
                st.session_state.refresh_needed = True
                st.success("Duplikat berhasil dihapus!")
                time.sleep(1)
                st.rerun()

    st.markdown("---")
    
    # Map Visualization (Tetap sama)
    st.markdown('<p style="font-size:1.3rem; font-weight:600; color:#1e293b;">🗺️ Database Coverage Map</p>', unsafe_allow_html=True)
    import folium
    from streamlit_folium import st_folium
    
    map_df = df_db.copy()
    map_df['lat'] = pd.to_numeric(map_df['Latitude'], errors='coerce')
    map_df['lng'] = pd.to_numeric(map_df['Longitude'], errors='coerce')
    map_df = map_df.dropna(subset=['lat', 'lng'])
    
    if not map_df.empty:
        m = folium.Map(location=[map_df['lat'].mean(), map_df['lng'].mean()], zoom_start=6)
        for _, row in map_df.iterrows():
            wa_link = format_wa_link(row['Phone']) if 'Phone' in row else None
            wa_html = f'<br><a href="{wa_link}" target="_blank">💬 WhatsApp</a>' if wa_link else ""
            gmap_html = f'<br><a href="{row["URL"]}" target="_blank">📍 Google Maps</a>' if 'URL' in row else ""
            popup_html = f"<b>{row['Name']}</b>{wa_html}{gmap_html}"
            folium.Marker([row['lat'], row['lng']], popup=popup_html, icon=folium.Icon(color="indigo")).add_to(m)
        st_folium(m, width="100%", height=500, returned_objects=[], key="db_map_v3")

else:
    st.info("No data found for your user.")