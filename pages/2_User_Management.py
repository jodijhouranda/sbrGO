import streamlit as st
import pandas as pd
from sqlalchemy import text
import os
import time

# --- ACCESS CONTROL ---
if not st.session_state.get('is_superuser', False):
    st.error("🚫 Access Denied. Only superusers can access this page.")
    st.stop()

# Premium UI Styling
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;600&display=swap');
    html, body, [data-testid="stStandardType"] { font-family: 'Outfit', sans-serif; }
    .stApp { background: radial-gradient(circle at top right, #f8f9ff 0%, #ffffff 100%); }
    .stButton > button { border-radius: 8px; font-weight: 600; }
    .user-card { background: white; padding: 20px; border-radius: 12px; box-shadow: 0 4px 10px rgba(0,0,0,0.05); margin-bottom: 15px; border-left: 5px solid #6366f1; }
</style>
""", unsafe_allow_html=True)

# Connection Fix
cert_path = os.path.abspath("isrgrootx1.pem")
try:
    conn = st.connection('tidb', type='sql', connect_args={"ssl": {"ca": cert_path}})
except Exception as e:
    st.error(f"Database error: {e}")
    st.stop()

def get_users():
    return conn.query("SELECT username, is_superuser, created_at FROM users", ttl=0)

def add_user(u, p, is_admin):
    try:
        with conn.session as session:
            session.execute(
                text("INSERT INTO users (username, password, is_superuser) VALUES (:u, :p, :is_a)"),
                {"u": u, "p": p, "is_a": is_admin}
            )
            session.commit()
        return True
    except Exception as e:
        st.error(f"Error adding user: {e}")
        return False

def delete_user(u):
    if u == st.session_state.username:
        st.error("You cannot delete yourself!")
        return False
    try:
        with conn.session as session:
            session.execute(text("DELETE FROM users WHERE username = :u"), {"u": u})
            session.commit()
        return True
    except Exception as e:
        st.error(f"Error deleting user: {e}")
        return False

# UI Layout
st.markdown('<div class="logo-container"><p class="main-title"><span class="title-no">User</span><span class="title-sbr">Management</span></p></div>', unsafe_allow_html=True)
st.markdown('<p class="subtitle">Admin Dashboard for managing system access.</p>', unsafe_allow_html=True)

with st.expander("➕ Add New User", expanded=True):
    with st.form("add_user_form"):
        new_u = st.text_input("Username")
        new_p = st.text_input("Password", type="password")
        is_a = st.toggle("Superuser Access")
        if st.form_submit_button("Create User", use_container_width=True):
            if new_u and new_p:
                if add_user(new_u, new_p, is_a):
                    st.success(f"User '{new_u}' created!")
                    time.sleep(1); st.rerun()
            else:
                st.warning("Please fill all fields.")

st.markdown("### 📋 System Users")
users_df = get_users()
if not users_df.empty:
    for _, row in users_df.iterrows():
        cols = st.columns([3, 2, 1])
        with cols[0]:
            st.markdown(f"**{row['username']}**")
        with cols[1]:
            role = "👑 Admin" if row['is_superuser'] else "👤 User"
            st.markdown(f"Role: {role}")
        with cols[2]:
            if st.button("🗑️", key=f"del_{row['username']}", help=f"Delete {row['username']}"):
                if delete_user(row['username']):
                    st.success("Deleted!"); time.sleep(1); st.rerun()
else:
    st.info("No users found.")
