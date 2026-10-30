import streamlit as st
#from views.auth import render_login_page
from views.onboarding import render_onboarding_page
#from views.dashboard import render_dashboard_page  # or views/diary.py

st.set_page_config(page_title="Sustain", layout="wide")

render_onboarding_page()