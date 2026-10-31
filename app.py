import streamlit as st

from services import db
from views.auth import render_login_page, render_logout_button
from views.onboarding import render_onboarding_page
from views.diary import render_diary_page
from views.settings import render_settings_page

st.set_page_config(page_title="Sustain", layout="wide")

db.init_db()
st.session_state.setdefault("user", None)

user = st.session_state.user
if user is None:
    render_login_page()
else:
    render_logout_button()
    if not user["onboarding_complete"]:
        render_onboarding_page()
    else:
        page = st.sidebar.radio("Go to", ["Diary", "Settings"])
        if page == "Diary":
            render_diary_page()
        else:
            render_settings_page()
