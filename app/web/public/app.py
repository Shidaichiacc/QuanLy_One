#!/usr/bin/env python3
import hashlib
import os
import re
import secrets
import sys
from pathlib import Path

import pymssql
from flask import Flask, abort, flash, redirect, render_template, request, send_from_directory, session, url_for
from markupsafe import Markup


PROJECT_ROOT = Path(os.environ.get("QUANLY_ONE_ROOT", "/opt/QuanLy_One"))
sys.path.insert(0, str(PROJECT_ROOT / "app" / "shared"))
from site_store import THEME_CATALOG, THEMES, get_article, get_settings, list_articles  # noqa: E402


LEGACY_ROOT = PROJECT_ROOT / "app" / "web" / "assets" / "legacy"
USERNAME_RE = re.compile(r"^[A-Za-z0-9_]{4,24}$")
app = Flask(__name__)
app.secret_key = os.environ.get("PUBLIC_SECRET_KEY") or os.environ.get(
    "MANAGER_SECRET_KEY", "quanly-one-change-this-secret"
)
app.config.update(
    SESSION_COOKIE_NAME="quanly_one_public",
    SESSION_COOKIE_PATH="/",
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    MAX_CONTENT_LENGTH=2 * 1024 * 1024,
)


def mssql_connection():
    return pymssql.connect(
        server=os.environ.get("MSSQL_HOST", "127.0.0.1"),
        port=int(os.environ.get("MSSQL_PORT", "1433")),
        user=os.environ.get("MSSQL_USER", "sa"),
        password=os.environ.get("MSSQL_SA_PASSWORD", ""),
        database=os.environ.get("MSSQL_DATABASE", "account_tong"),
        charset="utf8",
        autocommit=False,
        login_timeout=5,
    )


def password_digest(value):
    return hashlib.md5(value.encode("utf-8")).hexdigest().upper()


def csrf_token():
    token = session.get("public_csrf")
    if not token:
        token = secrets.token_urlsafe(32)
        session["public_csrf"] = token
    return token


def valid_csrf():
    supplied = request.form.get("csrf_token", "")
    expected = session.get("public_csrf", "")
    return bool(supplied and expected and secrets.compare_digest(supplied, expected))


def current_account_info():
    """Return the small account summary used by the public JX dashboard."""
    username = session.get("game_user")
    if not username:
        return None
    try:
        with mssql_connection() as connection:
            cursor = connection.cursor()
            cursor.execute(
                """SELECT ISNULL(a.nExtPoint,0), ISNULL(a.nExtPoint1,0),
                          ISNULL(h.iLeftSecond,0)
                   FROM Account_Info a
                   LEFT JOIN Account_Habitus h ON h.cAccName=a.cAccName
                   WHERE a.cAccName=%s""",
                (username,),
            )
            row = cursor.fetchone()
        if not row:
            return None
        return {"xu": int(row[0] or 0), "knb": int(row[1] or 0), "hours": round(float(row[2] or 0) / 3600, 1)}
    except Exception:
        app.logger.warning("Unable to load public account summary", exc_info=True)
        return None


def page_context(**extra):
    settings = get_settings()
    preview_theme = request.args.get("theme_preview", "")
    theme = preview_theme if preview_theme in THEMES else settings["theme"]
    if theme not in THEMES:
        theme = "modern"
    context = {
        "settings": settings,
        "theme": theme,
        "theme_meta": THEME_CATALOG[theme],
        "theme_preview": bool(preview_theme in THEMES),
        "game_user": session.get("game_user"),
        "account_info": current_account_info(),
        "csrf_token": csrf_token(),
    }
    context.update(extra)
    return context


def render_theme(page_name, **context):
    theme = context.get("theme", "modern")
    template_dir = THEME_CATALOG.get(theme, THEME_CATALOG["modern"])["template_dir"]
    return render_template(f"themes/{template_dir}/{page_name}.html", **context)


@app.after_request
def security_headers(response):
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
    response.headers.setdefault("Referrer-Policy", "same-origin")
    return response


@app.route("/")
def home():
    articles = list_articles(published_only=True, limit=45)
    context = page_context(
        articles=articles,
        latest=articles[:15],
        events=[row for row in articles if row["category"] == "event"][:15],
        features=[row for row in articles if row["category"] == "t_nag"][:15],
    )
    return render_theme("home", **context)


@app.route("/news")
def news():
    category = request.args.get("category") or None
    articles = list_articles(published_only=True, category=category)
    try:
        current_page = max(1, int(request.args.get("page", request.args.get("p", "1"))))
    except ValueError:
        current_page = 1
    page_size = 8
    start = (current_page - 1) * page_size
    context = page_context(
        articles=articles[start:start + page_size],
        category=category,
        current_page=current_page,
        has_previous=current_page > 1,
        has_next=start + page_size < len(articles),
    )
    return render_theme("news", **context)


@app.route("/article/<slug>")
def article(slug):
    item = get_article(slug, published_only=True)
    if not item:
        abort(404)
    context = page_context(article=item, article_body=Markup(item["body"]))
    return render_theme("article", **context)


@app.route("/news.php")
def legacy_news():
    return redirect(url_for("news", category=request.args.get("g"), page=request.args.get("p", 1)))


@app.route("/content.php")
def legacy_content():
    slug = request.args.get("i", "")
    return redirect(url_for("article", slug=slug)) if slug else redirect(url_for("home"))


@app.route("/acc.php")
def legacy_account():
    if request.args.get("i") == "register":
        return redirect(url_for("register"))
    return redirect(url_for("account"))


@app.route("/admin.php")
def legacy_admin():
    return redirect("/admin/")


@app.route("/account")
def account():
    context = page_context()
    return render_theme("account", **context)


@app.route("/account/register", methods=["GET", "POST"])
def register():
    if "register_captcha" not in session:
        session["register_captcha"] = "%04d" % secrets.randbelow(10000)
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        confirm = request.form.get("confirm", "")
        captcha = request.form.get("captcha", "").strip()
        error = None
        if not valid_csrf():
            error = "Phiên biểu mẫu không hợp lệ, hãy thử lại."
        elif not USERNAME_RE.fullmatch(username):
            error = "Tài khoản cần 4–24 ký tự, chỉ gồm chữ, số hoặc gạch dưới."
        elif not 6 <= len(password) <= 24:
            error = "Mật khẩu cần từ 6 đến 24 ký tự."
        elif password != confirm:
            error = "Hai mật khẩu không giống nhau."
        elif not secrets.compare_digest(captcha, session.get("register_captcha", "")):
            error = "Mã xác nhận không đúng."
        if not error:
            connection = None
            try:
                connection = mssql_connection()
                cursor = connection.cursor()
                cursor.execute("SELECT 1 FROM Account_Info WHERE cAccName=%s", (username,))
                if cursor.fetchone():
                    error = "Tài khoản đã tồn tại."
                else:
                    cursor.execute(
                        """INSERT INTO Account_Info
                           (cAccName,cPassWord,cSecPassWord,nExtPoint,nExtPoint1,nExtPoint2,
                            nExtPoint3,nExtPoint4,nExtPoint5,nExtPoint6,nExtPoint7,nFeeType,
                            iOTPSessionLifeTime)
                           VALUES(%s,%s,%s,1,0,0,0,0,0,0,0,0,0)""",
                        (username, password_digest(password), password_digest(password)),
                    )
                    cursor.execute(
                        """IF NOT EXISTS(SELECT 1 FROM Account_Habitus WHERE cAccName=%s)
                           INSERT INTO Account_Habitus(cAccName,iLeftSecond,dEndDate)
                           VALUES(%s,360000,'2035-12-31')""",
                        (username, username),
                    )
                    connection.commit()
                    flash("Đăng ký tài khoản thành công.", "ok")
                    session.pop("register_captcha", None)
                    return redirect(url_for("login"))
            except Exception as exc:
                if connection:
                    connection.rollback()
                app.logger.exception("Register failed")
                error = "Không kết nối được database tài khoản."
            finally:
                if connection:
                    connection.close()
        if error:
            flash(error, "err")
            session["register_captcha"] = "%04d" % secrets.randbelow(10000)
    context = page_context(register_captcha=session["register_captcha"])
    return render_theme("register", **context)


@app.route("/account/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        if not valid_csrf():
            flash("Phiên biểu mẫu không hợp lệ.", "err")
        else:
            try:
                with mssql_connection() as connection:
                    cursor = connection.cursor()
                    cursor.execute(
                        "SELECT cAccName FROM Account_Info WHERE cAccName=%s AND cPassWord=%s",
                        (username, password_digest(password)),
                    )
                    row = cursor.fetchone()
                if row:
                    session.clear()
                    session["game_user"] = row[0]
                    session["public_csrf"] = secrets.token_urlsafe(32)
                    flash("Đăng nhập thành công.", "ok")
                    return redirect(url_for("account"))
                flash("Sai tài khoản hoặc mật khẩu.", "err")
            except Exception:
                app.logger.exception("Login failed")
                flash("Không kết nối được database tài khoản.", "err")
    context = page_context()
    return render_theme("login", **context)


@app.route("/account/change-password", methods=["GET", "POST"])
def change_password():
    username = session.get("game_user")
    if not username:
        return redirect(url_for("login"))
    if request.method == "POST":
        current = request.form.get("current_password", "")
        new = request.form.get("new_password", "")
        confirm = request.form.get("confirm", "")
        if not valid_csrf():
            flash("Phiên biểu mẫu không hợp lệ.", "err")
        elif not 6 <= len(new) <= 24:
            flash("Mật khẩu mới cần từ 6 đến 24 ký tự.", "err")
        elif new != confirm:
            flash("Hai mật khẩu mới không giống nhau.", "err")
        else:
            try:
                with mssql_connection() as connection:
                    cursor = connection.cursor()
                    cursor.execute(
                        """UPDATE Account_Info SET cPassWord=%s
                           WHERE cAccName=%s AND cPassWord=%s""",
                        (password_digest(new), username, password_digest(current)),
                    )
                    if cursor.rowcount != 1:
                        connection.rollback()
                        flash("Mật khẩu hiện tại không đúng.", "err")
                    else:
                        connection.commit()
                        flash("Đã đổi mật khẩu.", "ok")
                        return redirect(url_for("account"))
            except Exception:
                app.logger.exception("Password change failed")
                flash("Không kết nối được database tài khoản.", "err")
    context = page_context()
    return render_theme("change_password", **context)


@app.route("/account/logout", methods=["POST"])
def logout():
    if valid_csrf():
        session.clear()
    return redirect(url_for("home"))


@app.route("/legacy-assets/<theme>/<path:filename>")
def legacy_assets(theme, filename):
    if theme not in THEMES:
        abort(404)
    return send_from_directory(str(LEGACY_ROOT / "themes" / theme), filename)


@app.route("/library/<path:filename>")
def legacy_library(filename):
    return send_from_directory(str(LEGACY_ROOT / "library"), filename)


@app.errorhandler(404)
def not_found(_error):
    context = page_context(message="Không tìm thấy nội dung.")
    return render_theme("message", **context), 404


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=int(os.environ.get("PUBLIC_PORT", "8000")))
