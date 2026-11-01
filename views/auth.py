# Handles secure login, registration, and user session initialization.
from pathlib import Path

import streamlit as st

from services import db


def render_login_page():
    _, middle, _ = st.columns([1, 2, 1])
    with middle:
        st.markdown(
            """
            <style>
            div.st-key-auth_title [data-testid="stHorizontalBlock"] {
            }
            div.st-key-auth_title img {
                transform: translateY(8px);
            }
            div[data-testid="stHorizontalBlock"]:has(div.st-key-forgot_password) {
                gap: 0;
            }
            div.st-key-forgot_password button {
                background: transparent;
                border: none;
                box-shadow: none;
                color: inherit;
                padding: 0;
            }
            div.st-key-forgot_password button:hover {
                background: transparent;
                border: none;
                box-shadow: none;
                color: #808080;
            }
            </style>
            """,
            unsafe_allow_html=True,
        )
        with st.container(key="auth_title"):
            title_logo_column, title_text_column = st.columns(
                [0.7, 5], vertical_alignment="center"
            )
            with title_logo_column:
                st.image(
                    Path(__file__).resolve().parents[1] / "assets" / "sustain_logo.png",
                    width=56,
                )
            with title_text_column:
                st.title("SustAIn")
        login_tab, register_tab = st.tabs(["Log in", "Sign up"])

        with login_tab:
            with st.form("login_form"):
                username = st.text_input("Username", key="login_username")
                password = st.text_input("Password", type="password", key="login_password")
                login_column, forgot_password_column = st.columns([0.6, 3.4])
                with login_column:
                    login_submitted = st.form_submit_button("Log in")
                with forgot_password_column:
                    st.form_submit_button("Forgot password?", key="forgot_password")
            if login_submitted:
                user = db.check_login(username, password)
                if user:
                    st.session_state.user = user
                    st.rerun()
                else:
                    st.error("Wrong username or password.")

        with register_tab:
            with st.form("signup_form"):
                username = st.text_input("Choose a Username", key="reg_username")
                password = st.text_input(
                    "Choose a Password", type="password", key="reg_password"
                )
                signup_submitted = st.form_submit_button("Sign up")
            if signup_submitted:
                if not username or len(password) < 6:
                    st.error("Enter a username and a password of at least 6 characters.")
                elif db.create_user(username, password):
                    user = db.check_login(username, password)
                    if user is None:
                        st.error("Your account was created, but automatic sign-in failed. Please log in.")
                    else:
                        st.session_state.user = user
                        st.rerun()
                else:
                    st.error("That username is taken.")


def render_logout_button():
    if st.sidebar.button("Log out"):
        st.session_state.user = None
        st.rerun()
