# Handles secure login, registration, and user session initialization.
import streamlit as st

from services import db

RECOVERY_QUESTIONS = [
    "What was the name of your first pet?",
    "What city were you born in?",
    "What was the name of your primary school?",
    "What is your favourite food?",
]


def render_login_page():
    _, middle, _ = st.columns([1, 2, 1])
    with middle:
        st.title("SustAIn")
        login_tab, register_tab, reset_tab = st.tabs(["Log in", "Sign up", "Forgot password"])

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
            question = st.selectbox("Recovery question", RECOVERY_QUESTIONS, key="reg_question")
            answer = st.text_input(
                "Answer (used if you forget your password)", type="password", key="reg_answer"
            )
            if st.button("Sign up"):
                if not username or len(password) < 6:
                    st.error("Enter a username and a password of at least 6 characters.")
                elif not answer.strip():
                    st.error("Enter an answer to the recovery question.")
                elif db.create_user(username, password, question, answer):
                    st.success("Account created. You can log in now.")
                else:
                    st.error("That username is taken.")

        with reset_tab:
            render_password_reset()


def render_password_reset():
    username = st.text_input("Username", key="reset_username")
    if not username:
        return
    question = db.get_recovery_question(username)
    if question is None:
        st.info("No recovery question is set for that username.")
        return
    answer = st.text_input(question, type="password", key="reset_answer")
    new_password = st.text_input("New password", type="password", key="reset_new_password")
    if st.button("Reset password"):
        if len(new_password) < 6:
            st.error("The new password must be at least 6 characters.")
        elif db.reset_password(username, answer, new_password):
            st.success("Password changed. You can log in now.")
        else:
            st.error("That answer doesn't match.")


def render_logout_button():
    if st.sidebar.button("Log out"):
        st.session_state.user = None
        st.rerun()
