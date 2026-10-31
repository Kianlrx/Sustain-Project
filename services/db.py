#services/db.py - everything that talks to the database.
#The database is one SQLite file, sustain.db. It has one table, users:
#    id | username | password_hash | salt | onboarding_complete

import hashlib
import os
import sqlite3

DB_PATH = "sustain.db"


def get_connection():
    # Opens the database file, and creates it if it doesn't exist yet.
    return sqlite3.connect(DB_PATH)


def init_db():
    # Creates the users table the first time the app runs. Safe to call every time.
    with get_connection() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                salt TEXT NOT NULL,
                onboarding_complete INTEGER NOT NULL DEFAULT 0
            )
            """
        )


def hash_password(password, salt):
    # We never store the real password. We store a scrambled version (a hash).
    # The salt is random text mixed in, so two people with the same password
    # still get different hashes.
    return hashlib.pbkdf2_hmac(
        "sha256", password.encode(), bytes.fromhex(salt), 100_000
    ).hex()


def create_user(username, password):
    """Sign up. Returns True if it worked, False if the username is taken."""
    salt = os.urandom(16).hex()
    try:
        with get_connection() as conn:
            conn.execute(
                "INSERT INTO users (username, password_hash, salt) VALUES (?, ?, ?)",
                (username, hash_password(password, salt), salt),
            )
        return True
    except sqlite3.IntegrityError:  # UNIQUE rule broken: username already exists
        return False


def check_login(username, password):
    """Log in. Returns the user as a dict if the password is right, else None."""
    with get_connection() as conn:
        row = conn.execute(
            "SELECT id, username, password_hash, salt, onboarding_complete "
            "FROM users WHERE username = ?",
            (username,),
        ).fetchone()
    if row is None:
        return None  # no such user
    user_id, name, stored_hash, salt, onboarding_complete = row
    if hash_password(password, salt) != stored_hash:
        return None  # wrong password
    return {"id": user_id, "username": name, "onboarding_complete": bool(onboarding_complete)}


def mark_onboarding_complete(user_id):
    # Kian's questionnaire calls this when the user submits it.
    with get_connection() as conn:
        conn.execute("UPDATE users SET onboarding_complete = 1 WHERE id = ?", (user_id,))
