import streamlit as st
import pandas as pd
from sqlalchemy import text
import io
import time
import os
from streamlit_folium import st_folium
import folium

# --- CUSTOM CSS ---
st.markdown("""
<style>
    div[data-testid="stMetric"] {
        background-color: #f8fafc;
        padding: 15px;
        border-radius: 10px;
        border: 1px solid #e2e8f0;
        box-shadow: 0 1px 3px rgba(0,0,0,0.05);
    }
    div.stButton > button, div.stDownloadButton > button {
        width: 100%;
        border-radius: 8px;
        font-weight: 600;
        padding: 0.6rem 1rem;
        transition: all 0.3s ease;
        border: none;
    }
    div.stButton > button:hover, div.stDownloadButton > button:hover {
        transform: translateY(-2px);
        box-shadow: 0 4px 6px rgba(0,0,0,0.1);
    }
    .dashboard-header {
        background: linear-gradient(135deg, #4f46e5 0%, #7c3aed 100%);
        padding: 20px;
        border-radius: 15px;
        margin-bottom: 25px;
        color: white;
        box-shadow: 0 10px 15px -3px rgba(0, 0, 0, 0.1);
    }
    .subtitle {
        font-size: 1.2rem;
        color: #64748b;
        margin-bottom: 20px;
    }
</style>
""", unsafe_allow_html=True)

st.markdown('<p class="subtitle">Search and manage your collected business data.</p>', unsafe_allow_html=True)

# --- DATABASE CONNECTION ---
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

def delete_records(values, column_name="id"):
    try:
        with conn.session as session:
            for val in values:
                # Query dinamis berdasarkan kolom target (id atau URL)
                query_str = f"DELETE FROM scraped_results WHERE `{column_name}` = :val"
                params = {"val": val}
                
                if not st.session_state.get('is_superuser', False):
                    query_str += " AND username = :user"
                    params["user"] = st.session_state.get('username')
                
                session.execute(text(query_str), params)
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
        if 'Select' in df_unique.columns:
            df_unique = df_unique.drop(columns=['Select'])
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
def confirm_delete_dialog(selected_values, target_col):
    st.warning(f"⚠️ Anda akan menghapus **{len(selected_values)}** data.")
    st.caption(f"Penghapusan berdasarkan kolom: {target_col}")
    
    col_yes, col_no = st.columns(2)
    with col_yes:
        if st.button("Ya, Hapus", type="primary", use_container_width=True):
            progress_bar = st.progress(0, text="Memproses...")
            for i in range(100):
                time.sleep(0.005) 
                progress_bar.progress(i + 1, text="Menghapus data...")
            
            if delete_records(selected_values, column_name=target_col):
                progress_bar.progress(100, text="Selesai!")
                st.session_state.refresh_needed = True
                st.success("Berhasil dihapus!")
                time.sleep(0.5)
                st.rerun()
            else:
                st.error("Gagal menghapus.")
    with col_no:
        if st.button("Batal", use_container_width=True):
            st.rerun()

@st.dialog("Detail Data")
def show_row_details(row):
    st.markdown(f"### 🏢 {row['Name']}")
    st.markdown("---")
    
    col_a, col_b = st.columns(2)
    with col_a:
        st.write("**📍 Alamat**")
        st.write(row.get('Address', row.get('Alamat', '-')))
        st.write("**🗺️ Lokasi**")
        st.write(f"- **Provinsi:** {row.get('Provinsi', '-')}")
        st.write(f"- **Kabupaten:** {row.get('Kabupaten', '-')}")
        st.write(f"- **Kecamatan:** {row.get('Kecamatan', '-')}")
        st.write(f"- **Kelurahan:** {row.get('Kelurahan', '-')}")
    
    with col_b:
        st.write("**🌐 Koordinat**")
        st.write(f"- **Latitude:** `{row.get('Latitude', '-')}`")
        st.write(f"- **Longitude:** `{row.get('Longitude', '-')}`")
        
        gmap_url = row.get('URL', '')
        if gmap_url:
            st.link_button("🚀 Buka di Google Maps", gmap_url, use_container_width=True)
            
    st.markdown("---")
    if st.button("Tutup", use_container_width=True):
        st.rerun()

# --- MAIN APP LOGIC ---

if 'username' not in st.session_state: st.session_state.username = 'demo_user' 
if 'is_superuser' not in st.session_state: st.session_state.is_superuser = False
if 'refresh_needed' not in st.session_state: st.session_state.refresh_needed = False

# Load Data
if 'df_db_v5' not in st.session_state or st.session_state.refresh_needed:
    raw_data = fetch_db_data(st.session_state.username, st.session_state.is_superuser)
    if raw_data is not None and not raw_data.empty:
        df_init = raw_data.copy()
        if "Select" not in df_init.columns:
            df_init.insert(0, "Select", False)
        else:
            df_init["Select"] = False
        st.session_state.df_db_v5 = df_init
    else:
        st.session_state.df_db_v5 = pd.DataFrame()
    st.session_state.refresh_needed = False

df_db = st.session_state.df_db_v5

if not df_db.empty:
    # 1. Header
    st.markdown(f"""
    <div class="dashboard-header">
        <h3 style="margin:0; font-size: 1.5rem;">📊 Data Insights Dashboard</h3>
        <p style="margin:0; opacity: 0.9; font-size: 0.9rem;">Workspace: {st.session_state.username}</p>
    </div>
    """, unsafe_allow_html=True)
    
    # 2. Metrics
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Total Data", f"{len(df_db):,}")
    m2.metric("Kota/Kab", df_db['Kabupaten'].nunique() if 'Kabupaten' in df_db.columns else 0)
    m3.metric("Provinsi", df_db['Provinsi'].nunique() if 'Provinsi' in df_db.columns else 0)
    kbli_count = df_db['KBLI'].astype(str).str[:2].nunique() if 'KBLI' in df_db.columns else 0
    m4.metric("Kategori (KBLI)", kbli_count)

    st.write("") 

    # 3. Table Editor (FIXED: No Hidden Param)
    
    # Deteksi kolom unik
    target_delete_col = "id"
    if "id" not in df_db.columns:
        if "URL" in df_db.columns:
            target_delete_col = "URL"
        elif "Name" in df_db.columns:
            target_delete_col = "Name"

    config = {
        "Select": st.column_config.CheckboxColumn("✅", width="small", default=False),
        "scraped_at": st.column_config.DatetimeColumn("Waktu Scrape", format="D MMM, HH:mm"),
        "URL": st.column_config.LinkColumn("Maps"),
        "Phone": st.column_config.TextColumn("Telepon"),
        "Rating": st.column_config.NumberColumn("⭐", format="%.1f"),
    }
    
    # ATUR VISIBILITAS VIA COLUMN_ORDER
    # Kita buat list kolom yang akan DITAMPILKAN.
    all_cols = df_db.columns.tolist()
    if "Select" in all_cols:
        all_cols.remove("Select")
        all_cols.insert(0, "Select") # Pindah Select ke depan
    
    display_cols = all_cols.copy()
    
    # Jika targetnya 'id' (teknis), kita sembunyikan dari tampilan agar rapi.
    # TAPI jika targetnya 'URL' atau 'Name', kita TETAP TAMPILKAN karena itu informasi berguna.
    if target_delete_col == "id" and "id" in display_cols:
        display_cols.remove("id")
    
    edited_df = st.data_editor(
        df_db,
        column_config=config,
        column_order=display_cols, # Hanya kolom di list ini yang tampil
        disabled=[c for c in df_db.columns if c != "Select"],
        hide_index=True,
        use_container_width=True,
        height=400,
        key="main_editor_fixed_v2",
        selection_mode="single_row"
    )

    # Deteksi Klik Baris
    if "selection" in st.session_state.main_editor_fixed_v2 and st.session_state.main_editor_fixed_v2["selection"]["rows"]:
        selected_row_idx = st.session_state.main_editor_fixed_v2["selection"]["rows"][0]
        
        # BERSIHKAN SELEKSI SEGERA untuk memutus loop rerun
        st.session_state.main_editor_fixed_v2["selection"]["rows"] = []
        
        selected_row_data = df_db.iloc[selected_row_idx]
        show_row_details(selected_row_data)

    st.write("") 

    # 4. Action Buttons
    excel_buffer = io.BytesIO()
    with pd.ExcelWriter(excel_buffer, engine='openpyxl') as wr:
        output_df = edited_df.drop(columns=['Select']) if 'Select' in edited_df.columns else edited_df
        output_df.to_excel(wr, index=False)
    excel_data = excel_buffer.getvalue()

    c_act1, c_act2, c_act3 = st.columns(3)

    # TOMBOL DELETE
    with c_act1:
        if st.button("🗑️ Delete Selected", type="primary", use_container_width=True):
            selected = edited_df[edited_df["Select"] == True]
            if not selected.empty:
                # Pastikan kolom target ada di dataframe yang diedit
                if target_delete_col in selected.columns:
                    vals_to_delete = selected[target_delete_col].tolist()
                    confirm_delete_dialog(vals_to_delete, target_delete_col)
                else:
                    st.error(f"❌ Kolom kunci '{target_delete_col}' hilang. Mohon refresh.")
            else:
                st.warning("⚠️ Pilih data terlebih dahulu.")

    # TOMBOL DEDUPLICATE
    with c_act2:
        if st.button("♻️ Remove Duplicates", use_container_width=True):
            with st.spinner("Membersihkan duplikat..."):
                if deduplicate_db(df_db):
                    st.session_state.refresh_needed = True
                    st.success("Selesai!")
                    time.sleep(1)
                    st.rerun()

    # TOMBOL EXPORT
    with c_act3:
        st.download_button(
            label="📥 Export Excel",
            data=excel_data,
            file_name=f"data_export_{int(time.time())}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True
        )

    st.markdown("---")

    # 5. Map Section
    st.markdown("### 🗺️ Peta Sebaran")
    map_df = df_db.copy()
    map_df['lat'] = pd.to_numeric(map_df['Latitude'], errors='coerce')
    map_df['lng'] = pd.to_numeric(map_df['Longitude'], errors='coerce')
    map_df = map_df.dropna(subset=['lat', 'lng'])

    if not map_df.empty:
        avg_lat = map_df['lat'].mean()
        avg_lng = map_df['lng'].mean()
        m = folium.Map(location=[avg_lat, avg_lng], zoom_start=10, tiles='CartoDB positron')
        
        from folium.plugins import MarkerCluster
        marker_cluster = MarkerCluster().add_to(m)

        for _, row in map_df.iterrows():
            name = row.get('Name', 'Tanpa Nama')
            alamat = row.get('Address', row.get('Alamat', '-'))
            if pd.isna(alamat): alamat = "-"
            
            wa_link = row.get('WhatsApp Link')
            if pd.isna(wa_link): 
                wa_link = format_wa_link(row.get('Phone', ''))
                
            gmap_link = row.get('URL', '')

            # Tombol HTML
            wa_btn = ""
            if wa_link:
                wa_btn = f'<a href="{wa_link}" target="_blank" style="display:inline-block; margin-top:5px; text-decoration:none; color:white; background:#25D366; padding:4px 8px; border-radius:4px; font-size:0.8em;">💬 WhatsApp</a>'
            
            map_btn = ""
            if gmap_link:
                 map_btn = f'<a href="{gmap_link}" target="_blank" style="display:inline-block; margin-top:5px; margin-left:5px; text-decoration:none; color:white; background:#4285F4; padding:4px 8px; border-radius:4px; font-size:0.8em;">📍 G-Maps</a>'

            popup_content = f"""
            <div style="font-family:sans-serif; min-width:200px;">
                <b style="font-size:1.1em; color:#333;">{name}</b><br>
                <div style="color:#666; font-size:0.85em; margin: 4px 0 8px 0; line-height:1.2;">{alamat}</div>
                <div>{wa_btn} {map_btn}</div>
            </div>
            """
            
            folium.Marker(
                [row['lat'], row['lng']],
                popup=folium.Popup(popup_content, max_width=300),
                icon=folium.Icon(color="blue", icon="info-sign")
            ).add_to(marker_cluster)
            
        st_folium(m, width="100%", height=500, returned_objects=[])

else:
    st.info("Belum ada data yang tersimpan.")