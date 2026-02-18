import streamlit as st
import pandas as pd
from sqlalchemy import text
import io
import time
import os

st.markdown('<p class="subtitle">Search and manage your collected business data.</p>', unsafe_allow_html=True)

# Connection Fix
cert_path = os.path.abspath("isrgrootx1.pem")
try:
    conn = st.connection('tidb', type='sql', connect_args={"ssl": {"ca": cert_path}})
except Exception as e:
    st.error(f"Gagal menghubungkan ke database: {e}")
    st.stop()

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
        st.cache_data.clear() # Clear cache after deduplication
        return True
    except Exception as e:
        st.error(f"Error: {e}")
        return False

def format_wa_link(phone):
    """Konversi nomor telepon Indonesia (08x, +62) ke link WhatsApp wa.me."""
    if pd.isna(phone): return None
    clean_phone = "".join(filter(str.isdigit, str(phone)))
    if not clean_phone: return None
    if clean_phone.startswith('08'):
        return f"https://wa.me/62{clean_phone[1:]}"
    elif clean_phone.startswith('62'):
        return f"https://wa.me/{clean_phone}"
    elif clean_phone.startswith('8'):
        return f"https://wa.me/62{clean_phone}"
    return None

# Main UI
if 'df_db_v5' not in st.session_state or st.session_state.get('refresh_needed', False):
    raw_data = fetch_db_data(st.session_state.get('username'), st.session_state.get('is_superuser', False))
    if raw_data is not None and not raw_data.empty:
        df_init = raw_data.copy()
        df_init.insert(0, "Select", False)
        st.session_state.df_db_v5 = df_init
    else:
        st.session_state.df_db_v5 = pd.DataFrame()
    st.session_state.refresh_needed = False

df_db = st.session_state.df_db_v5

@st.dialog("Confirm Deletion")
def confirm_delete_dialog(selected_ids):
    st.warning(f"Are you sure you want to delete {len(selected_ids)} selected records? This action cannot be undone.")
    c1, c2 = st.columns(2)
    with c1:
        if st.button("Yes, Delete", type="primary", use_container_width=True):
            if delete_records(selected_ids):
                st.session_state.refresh_needed = True
                st.success("Deleted successfully!")
                time.sleep(1)
                st.rerun()
    with c2:
        if st.button("Cancel", use_container_width=True):
            st.rerun()

if not df_db.empty:
    st.markdown('<div style="background: linear-gradient(135deg, #6366f1 0%, #a855f7 100%); padding: 20px; border-radius: 15px; margin-bottom: 25px; color: white;"><h3 style="margin:0; color: white; font-size: 1.5rem;">📊 Data Insights Dashboard</h3><p style="margin:0; opacity: 0.8; font-size: 0.9rem;">Filtering data for: '+str(st.session_state.username)+'</p></div>', unsafe_allow_html=True)
    
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
    
    # Configuration for data editor
    config = {
        "Select": st.column_config.CheckboxColumn("Select", default=False),
        "scraped_at": st.column_config.DatetimeColumn("Waktu Scrape"),
        "URL": st.column_config.LinkColumn("G-Maps"),
        "WhatsApp Link": st.column_config.LinkColumn("WA"),
        "Rating": st.column_config.NumberColumn("Rating", format="%.1f ⭐"),
    }
    
    # Disable all except Select
    disabled_cols = [c for c in df_db.columns if c != "Select"]
    
    # Selection Form: Only the table and delete button are inside to maintain silent selection
    with st.form("delete_form_v3", border=False):
        edited_df = st.data_editor(
            df_db, 
            column_config=config, 
            disabled=disabled_cols, 
            hide_index=True, 
            use_container_width=True, 
            key="db_editor_v8"
        )
        
        # Action button inside the form (Primary Action)
        d1, d2, d3 = st.columns([1, 2, 1])
        with d2:
            if st.form_submit_button("🗑️ Delete Selected Records", type="primary", use_container_width=True):
                # Critical fix: Ensure we are counting correctly from the returned edited_df
                # In st.form, the return value of st.data_editor contains the state at submission
                sel = edited_df[edited_df["Select"] == True]
                if not sel.empty:
                    confirm_delete_dialog(sel["id"].tolist() if "id" in sel.columns else [])
                else:
                    st.warning("No records selected. Please check the 'Select' boxes first.")

    st.markdown("<br>", unsafe_allow_html=True)
    
    # Secondary actions in a clean, consistent row below the form
    st.markdown('<p style="font-size:1.1rem; font-weight:600; color:#475569; margin-bottom:15px;">🛠️ Workspace Management</p>', unsafe_allow_html=True)
    act_col1, act_col2 = st.columns(2)
    with act_col1:
        if st.button("🔄 Remove Duplicates", use_container_width=True):
            if deduplicate_db(df_db): 
                st.session_state.refresh_needed = True
                st.success("Deduplicated!"); time.sleep(1); st.rerun()
    with act_col2:
        buf = io.BytesIO()
        with pd.ExcelWriter(buf, engine='openpyxl') as wr: df_db.to_excel(wr, index=False)
        st.download_button("📥 Export Excel", data=buf.getvalue(), file_name="sbrgo_export.xlsx", use_container_width=True)

    st.markdown("---")
    st.markdown('<p style="font-size:1.3rem; font-weight:600; color:#1e293b;">🗺️ Database Coverage Map</p>', unsafe_allow_html=True)
    import folium
    from streamlit_folium import st_folium
    map_df = df_db.copy(); map_df['lat'] = pd.to_numeric(map_df['Latitude'], errors='coerce'); map_df['lng'] = pd.to_numeric(map_df['Longitude'], errors='coerce')
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
