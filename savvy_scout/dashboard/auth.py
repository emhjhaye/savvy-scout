"""Individual logins, no shared accounts (SPEC.md B1)."""

import sqlite3

from flask import Blueprint, current_app, g, redirect, render_template, request, url_for
from flask_login import LoginManager, UserMixin, login_required, login_user, logout_user
from werkzeug.security import check_password_hash

from savvy_scout.db.connection import get_connection

login_manager = LoginManager()
login_manager.login_view = "auth.login"
# Suppress Flask-Login's default "Please log in to access this page" flash.
# login.html doesn't render flashed messages (it has its own `error` slot for
# failed submissions), so that flash was going unread until the next
# authenticated page render, leaking a stale message onto the queues view
# right after a successful login.
login_manager.login_message = None

auth_bp = Blueprint("auth", __name__)


class User(UserMixin):
    def __init__(self, row: sqlite3.Row):
        self.id = str(row["id"])
        self.username = row["username"]
        self.display_name = row["display_name"]
        self.is_victoria = bool(row["is_victoria"])


def get_db() -> sqlite3.Connection:
    if "db" not in g:
        g.db = get_connection(current_app.config["SAVVY_SCOUT_DB_PATH"])
    return g.db


@login_manager.user_loader
def load_user(user_id: str):
    row = get_db().execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    return User(row) if row else None


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    error = None
    if request.method == "POST":
        row = get_db().execute(
            "SELECT * FROM users WHERE username = ?", (request.form.get("username", ""),)
        ).fetchone()
        if row and check_password_hash(row["password_hash"], request.form.get("password", "")):
            login_user(User(row))
            return redirect(url_for("queues.index"))
        error = "Invalid username or password"
    
    return render_template("login.html", error=error)


@auth_bp.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for("auth.login"))
