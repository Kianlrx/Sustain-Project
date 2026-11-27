# Integration tests (black-box): the whole app run through Streamlit's AppTest,
# clicking through it the way a user would. A temporary SQLite database stands in
# for Supabase, so no keys or passwords are needed.
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from streamlit.testing.v1 import AppTest

import streamlit as st

from services import db
from views.onboarding import _ANSWER_DEFAULTS
from integration_services import PROFILE

APP = str(Path(__file__).resolve().parents[1] / "app.py")


class AppJourneyTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        db_path = patch.object(db, "DB_PATH", Path(folder.name) / "app.db")
        db_path.start()
        self.addCleanup(db_path.stop)
        db.init_db()
        self.app = AppTest.from_file(APP, default_timeout=30)
        self.app.run()
        self.assertFalse(self.app.exception)

    def click(self, label=None, key=None):
        # find a button by its key, or else by its label, click it and check nothing crashed
        if key:
            button = self.app.button(key=key)
        else:
            button = next(b for b in self.app.button if b.label == label)
        button.click().run()
        self.assertFalse(self.app.exception, [e.message for e in self.app.exception])

    def sign_up(self, username, password):
        self.app.text_input(key="reg_username").set_value(username)
        self.app.text_input(key="reg_password").set_value(password)
        self.click("Sign up")

    def log_in(self, username, password):
        self.app.text_input(key="login_username").set_value(username)
        self.app.text_input(key="login_password").set_value(password)
        self.click("Log in")

    def errors(self):
        return [error.value for error in self.app.error]

    def test_new_user_signs_up_and_finishes_onboarding(self):
        self.sign_up("newuser", "secret1")
        self.assertEqual(self.app.session_state["user"]["username"], "newuser")

        # AppTest delivers the submission payload without running the browser component.
        def submit_questionnaire(**kwargs):
            st.session_state.onboarding_questionnaire = SimpleNamespace(submit=dict(_ANSWER_DEFAULTS))
            kwargs["on_submit_change"]()
            st.rerun()

        with patch("views.onboarding._questionnaire", side_effect=submit_questionnaire):
            self.app.run()
            self.assertFalse(self.app.exception)

        user = db.check_login("newuser", "secret1")
        self.assertTrue(user["onboarding_complete"])
        self.assertIsNotNone(db.get_profile(user["id"]))
        self.assertEqual(self.app.session_state["main_navigation"], "Dashboard")

    def test_sign_up_rejects_short_password_and_taken_username(self):
        self.sign_up("newuser", "123")
        self.assertIn("Enter a username and a password of at least 6 characters.", self.errors())
        self.assertIsNone(self.app.session_state["user"])

        db.create_user("taken", "secret1")
        self.sign_up("taken", "secret1")
        self.assertIn("That username is taken.", self.errors())
        self.assertIsNone(self.app.session_state["user"])

    def test_wrong_password_is_rejected(self):
        db.create_user("joe", "secret1")
        self.log_in("joe", "wrong-password")
        self.assertIn("Wrong username or password.", self.errors())
        self.assertIsNone(self.app.session_state["user"])

    def test_returning_user_opens_every_page_and_logs_out(self):
        db.create_user("joe", "secret1")
        user_id = db.check_login("joe", "secret1")["id"]
        db.save_profile(user_id, PROFILE)
        db.mark_onboarding_complete(user_id)

        self.log_in("joe", "secret1")
        self.assertEqual(self.app.session_state["main_navigation"], "Diary")
        for key, page in [("nav_dashboard", "Dashboard"), ("nav_weight", "Weight"),
                          ("nav_settings", "Settings"), ("nav_diary", "Diary")]:
            with self.subTest(page=page):
                self.click(key=key)
                self.assertEqual(self.app.session_state["main_navigation"], page)

        self.click(key="sidebar_logout_button")
        self.assertIsNone(self.app.session_state["user"])
        self.app.text_input(key="login_username")  # the login form is back


if __name__ == "__main__":
    unittest.main()