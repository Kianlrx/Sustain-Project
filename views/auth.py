# Handles secure login, registration, and user session initialization.
import streamlit as st

from services import db
from services.branding import logo_data_uri


def render_login_page():
    _, middle, _ = st.columns([1, 2, 1])
    with middle:
        st.markdown(
            """
            <style>
            .auth-brand {
                display: flex;
                align-items: center;
                gap: 16px;
                margin: 32px 0 8px;
            }
            .auth-brand img {
                border-radius: 12px;
            }
            .auth-brand h1 {
                margin: 0;
                padding: 0;
                font-size: 2rem;
                font-weight: 500;
            }
            div[data-testid="stHorizontalBlock"]:has(div.st-key-forgot_password) {
                gap: 0;
            }
            div.st-key-forgot_password button {
                background: transparent;
                border: none;
                box-shadow: none;
                color: var(--sustain-secondary);
                padding: 0;
            }
            div.st-key-forgot_password button:hover {
                background: transparent;
                border: none;
                box-shadow: none;
                color: var(--sustain-text);
            }
            </style>
            """,
            unsafe_allow_html=True,
        )
        with st.container(key="auth_title"):
            st.html(
                '<div class="auth-brand">'
                f'<img src="{logo_data_uri()}" alt="Sustain logo" width="48" height="48">'
                "<h1>Sustain</h1></div>"
            )
        login_tab, register_tab = st.tabs(["Log in", "Sign up"])

        with login_tab:
            with st.form("login_form"):
                username = st.text_input("Username", key="login_username")
                password = st.text_input("Password", type="password", key="login_password")
                login_column, forgot_password_column = st.columns([0.6, 3.4])
                with login_column:
                    login_submitted = st.form_submit_button("Log in", type="primary")
                with forgot_password_column:
                    st.form_submit_button("Forgot password?", key="forgot_password")
            if login_submitted:
                user = db.check_login(username, password)
                if user:
                    st.session_state.user = user
                    if user["onboarding_complete"]:
                        st.session_state.main_navigation = "Diary"
                    st.rerun()
                else:
                    st.error("Wrong username or password.")

        with register_tab:
            with st.form("signup_form"):
                username = st.text_input("Choose a username", key="reg_username")
                password = st.text_input(
                    "Choose a password", type="password", key="reg_password"
                )
                signup_submitted = st.form_submit_button("Sign up", type="primary")
            if signup_submitted:
                if not username or len(password) < 6:
                    st.error("Enter a username and a password of at least 6 characters.")
                elif db.create_user(username, password):
                    user = db.check_login(username, password)
                    if user is None:
                        st.error("Your account was created, but automatic sign-in failed. Please log in.")
                    else:
                        st.session_state.user = user
                        if user["onboarding_complete"]:
                            st.session_state.main_navigation = "Diary"
                        st.rerun()
                else:
                    st.error("That username is taken.")


def render_logout_button():
    # Rendered by app.py inside the sidebar footer container, so use st.button
    # (st.sidebar.button would ignore that container).
    if st.button(
        "Log out",
        key="sidebar_logout_button",
        use_container_width=True,
    ):
        st.session_state.user = None
        st.rerun()
