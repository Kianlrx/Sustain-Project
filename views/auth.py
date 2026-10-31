# Handles secure login, registration, and user session initialization.
import streamlit as st

from services import db


def render_login_page():
    _, middle, _ = st.columns([1, 2, 1])
    with middle:
        st.title("SustAIn")
        login_tab, register_tab = st.tabs(["Log in", "Sign up"])

        with login_tab:
            username = st.text_input("Username", key="login_username")
            password = st.text_input("Password", type="password", key="login_password")
            if st.button("Log in"):
                user = db.check_login(username, password)
                if user:
                    st.session_state.user = user
                    st.rerun()
                else:
                    st.error("Wrong username or password.")

        with register_tab:
            username = st.text_input("Choose a username", key="reg_username")
            password = st.text_input("Choose a password", type="password", key="reg_password")
            if st.button("Sign up"):
                if not username or len(password) < 6:
                    st.error("Enter a username and a password of at least 6 characters.")
                elif db.create_user(username, password):
                    st.success("Account created. You can log in now.")
                else:
                    st.error("That username is taken.")


def render_logout_button():
    if st.sidebar.button("Log out"):
        st.session_state.user = None
        st.rerun()