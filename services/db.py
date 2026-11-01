#services/db.py - everything that talks to the database.
#The database is one SQLite file, sustain.db. It has two tables:
#    users:    id | username | password_hash | salt | onboarding_complete
#              | recovery_question | recovery_hash | recovery_salt
#    profiles: user_id | profile_json | targets_json | targets_manual

import hashlib
import json
import os
import sqlite3

DB_PATH = "sustain.db"


def get_connection():
    # Opens the database file, and creates it if it doesn't exist yet.
    return sqlite3.connect(DB_PATH)


def init_db():
    # Creates the tables the first time the app runs. Safe to call every time.
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
        # Columns for password recovery. Added this way so an older sustain.db
        # (made before these columns existed) gets them too.
        existing = {row[1] for row in conn.execute("PRAGMA table_info(users)")}
        for column in ("recovery_question", "recovery_hash", "recovery_salt"):
            if column not in existing:
                conn.execute(f"ALTER TABLE users ADD COLUMN {column} TEXT")
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS profiles (
                user_id INTEGER PRIMARY KEY REFERENCES users(id),
                profile_json TEXT,
                targets_json TEXT,
                targets_manual INTEGER NOT NULL DEFAULT 0
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


def _normalize_answer(answer):
    # "  Dublin " and "dublin" count as the same recovery answer.
    return answer.strip().lower()


# ---- Sign up and log in ----

def create_user(username, password, recovery_question, recovery_answer):
    """Sign up. Returns True if it worked, False if the username is taken."""
    salt = os.urandom(16).hex()
    recovery_salt = os.urandom(16).hex()
    try:
        with get_connection() as conn:
            conn.execute(
                "INSERT INTO users (username, password_hash, salt, "
                "recovery_question, recovery_hash, recovery_salt) VALUES (?, ?, ?, ?, ?, ?)",
                (
                    username,
                    hash_password(password, salt),
                    salt,
                    recovery_question,
                    hash_password(_normalize_answer(recovery_answer), recovery_salt),
                    recovery_salt,
                ),
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


# ---- Password reset and change (SCRUM-93) ----

def get_recovery_question(username):
    """The user's recovery question, or None if the user doesn't exist or never set one."""
    with get_connection() as conn:
        row = conn.execute(
            "SELECT recovery_question FROM users WHERE username = ?", (username,)
        ).fetchone()
    return row[0] if row else None


def _set_password(conn, user_id, new_password):
    salt = os.urandom(16).hex()
    conn.execute(
        "UPDATE users SET password_hash = ?, salt = ? WHERE id = ?",
        (hash_password(new_password, salt), salt, user_id),
    )


def reset_password(username, recovery_answer, new_password):
    """Forgot password. Returns True if the answer was right and the password changed."""
    with get_connection() as conn:
        row = conn.execute(
            "SELECT id, recovery_hash, recovery_salt FROM users WHERE username = ?",
            (username,),
        ).fetchone()
        if row is None or row[1] is None:
            return False
        user_id, recovery_hash, recovery_salt = row
        if hash_password(_normalize_answer(recovery_answer), recovery_salt) != recovery_hash:
            return False
        _set_password(conn, user_id, new_password)
    return True


def change_password(user_id, current_password, new_password):
    """Logged-in password change. Returns True if the current password was right."""
    with get_connection() as conn:
        row = conn.execute(
            "SELECT password_hash, salt FROM users WHERE id = ?", (user_id,)
        ).fetchone()
        if row is None or hash_password(current_password, row[1]) != row[0]:
            return False
        _set_password(conn, user_id, new_password)
    return True


# ---- Profile and targets (SCRUM-89, 94, 95) ----

def save_profile(user_id, profile):
    """Save the questionnaire answers as a dict (e.g. dataclasses.asdict(user_profile))."""
    with get_connection() as conn:
        conn.execute(
            "INSERT INTO profiles (user_id, profile_json) VALUES (?, ?) "
            "ON CONFLICT(user_id) DO UPDATE SET profile_json = excluded.profile_json",
            (user_id, json.dumps(profile)),
        )


def get_profile(user_id):
    """The saved profile dict, or None if the questionnaire hasn't been saved yet."""
    with get_connection() as conn:
        row = conn.execute(
            "SELECT profile_json FROM profiles WHERE user_id = ?", (user_id,)
        ).fetchone()
    return json.loads(row[0]) if row and row[0] else None


def save_targets(user_id, targets, manual=False):
    """Save daily targets: {"calories", "protein_g", "carbs_g", "fat_g"}.
    manual=True means the user set them by hand, so automatic recalculation leaves them alone."""
    with get_connection() as conn:
        conn.execute(
            "INSERT INTO profiles (user_id, targets_json, targets_manual) VALUES (?, ?, ?) "
            "ON CONFLICT(user_id) DO UPDATE SET targets_json = excluded.targets_json, "
            "targets_manual = excluded.targets_manual",
            (user_id, json.dumps(targets), int(manual)),
        )


def get_targets(user_id):
    """Returns (targets dict or None, manual flag)."""
    with get_connection() as conn:
        row = conn.execute(
            "SELECT targets_json, targets_manual FROM profiles WHERE user_id = ?", (user_id,)
        ).fetchone()
    if not row or not row[0]:
        return None, False
    return json.loads(row[0]), bool(row[1])
