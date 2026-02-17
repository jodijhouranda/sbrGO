import streamlit as st
import pandas as pd
from sqlalchemy import text
import io
import time
import os

# Premium UI Styling
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;600&display=swap');
    html, body, [data-testid="stStandardType"] { font-family: 'Outfit', sans-serif; }
    .stApp { background: radial-gradient(circle at top right, #f8f9ff 0%, #ffffff 100%); }
    .subtitle { color: #94a3b8; font-size: 0.65rem !important; font-weight: 500; text-transform: uppercase; letter-spacing: 1px; margin-top: -10px; margin-bottom: 3rem; opacity: 0.6; }
    .stButton > button { background: linear-gradient(90deg, #6366f1 0%, #a855f7 100%); color: white !important; border: none; padding: 0.6rem 2rem; border-radius: 8px; font-weight: 600; transition: all 0.3s ease; box-shadow: 0 4px 15px rgba(99, 102, 241, 0.2); }
</style>
""", unsafe_allow_html=True)

# Connection Fix
cert_path = os.path.abspath("isrgrootx1.pem")
try:
    conn = st.connection('tidb', type='sql', connect_args={"ssl": {"ca": cert_path}})
except Exception as e:
    st.error(f"Gagal menghubungkan ke database: {e}")
    st.stop()

def fetch_db_data():
    """Fetch data filtered by user unless superuser."""
    try:
        query = "SELECT * FROM scraped_results"
        params = {}
        if not st.session_state.get('is_superuser', False):
            query += " WHERE username = :user"
            params['user'] = st.session_state.get('username')
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
        return True
    except Exception as e:
        st.error(f"Error: {e}")
        return False

# Main UI
df_db = fetch_db_data()

if df_db is not None and not df_db.empty:
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
    df_display = df_db.copy()
    df_display.insert(0, "Select", False)
    
    # Configuration for data editor
    config = {
        "Select": st.column_config.CheckboxColumn("Select", default=False),
        "scraped_at": st.column_config.DatetimeColumn("Waktu Scrape"),
        "URL": st.column_config.LinkColumn("G-Maps"),
        "WhatsApp Link": st.column_config.LinkColumn("WA"),
        "Rating": st.column_config.NumberColumn("Rating", format="%.1f ⭐"),
    }
    
    # Disable all except Select
    disabled_cols = [c for c in df_display.columns if c != "Select"]
    
    edited_df = st.data_editor(df_display, column_config=config, disabled=disabled_cols, hide_index=True, use_container_width=True, key="db_editor_v3")
    
    act_col1, act_col2, act_col3 = st.columns(3)
    with act_col1:
        if st.button("🔄 Remove Duplicates", use_container_width=True):
            if deduplicate_db(df_db): st.success("Deduplicated!"); time.sleep(1); st.rerun()
    with act_col2:
        buf = io.BytesIO()
        with pd.ExcelWriter(buf, engine='openpyxl') as wr: df_db.to_excel(wr, index=False)
        st.download_button("📥 Export Excel", data=buf.getvalue(), file_name="sbrgo_export.xlsx", use_container_width=True)
    with act_col3:
        sel = edited_df[edited_df["Select"] == True]
        if not sel.empty:
            if st.button(f"🗑️ Delete ({len(sel)})", type="primary", use_container_width=True):
                if delete_records(sel["id"].tolist() if "id" in sel.columns else []):
                    st.success("Deleted!"); time.sleep(1); st.rerun()

    st.markdown("---")
    st.markdown('<p style="font-size:1.3rem; font-weight:600; color:#1e293b;">🗺️ Database Coverage Map</p>', unsafe_allow_html=True)
    import folium
    from streamlit_folium import st_folium
    map_df = df_db.copy(); map_df['lat'] = pd.to_numeric(map_df['Latitude'], errors='coerce'); map_df['lng'] = pd.to_numeric(map_df['Longitude'], errors='coerce')
    map_df = map_df.dropna(subset=['lat', 'lng'])
    if not map_df.empty:
        m = folium.Map(location=[map_df['lat'].mean(), map_df['lng'].mean()], zoom_start=6)
        for _, row in map_df.iterrows():
            folium.Marker([row['lat'], row['lng']], popup=row['Name'], icon=folium.Icon(color="indigo")).add_to(m)
        st_folium(m, width="100%", height=500, returned_objects=[], key="db_map_v3")
else:
    st.info("No data found for your user.")
