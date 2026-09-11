import html
import os
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path


PROJECT_ROOT = Path(os.environ.get("QUANLY_ONE_ROOT", "/opt/QuanLy_One"))
DATABASE_PATH = PROJECT_ROOT / "data" / "state" / "site.db"
LEGACY_CONTENT = PROJECT_ROOT / "app" / "web" / "seed-content"
THEME_CATALOG = {
    "modern": {
        "label": "JXNative hiện đại",
        "description": "Gọn, hiện đại, tối ưu cho máy tính và điện thoại.",
        "template_dir": "modern",
        "accent": "#c9a45f",
    },
    "thachi": {
        "label": "Thạch Chí cổ điển",
        "description": "Giao diện Võ Lâm cổ điển độc lập, dùng chung dữ liệu website.",
        "template_dir": "thachi",
        "accent": "#9a2724",
    },
}
THEMES = tuple(THEME_CATALOG)
SETTING_DEFAULTS = {
    "title": "JX Server",
    "theme": "thachi",
    "tagline": "Võ Lâm Truyền Kỳ",
    "announcement": "Chào mừng bạn đến với máy chủ Võ Lâm.",
    "download_url": "/article/download",
    "facebook_url": "",
    "facebook_group": "",
    "support_email": "",
    "support_phone": "",
    "support_text": "Hỗ trợ người chơi",
}
SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,79}$")


def connect():
    DATABASE_PATH.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(str(DATABASE_PATH), timeout=15)
    connection.row_factory = sqlite3.Row
    return connection


def initialize():
    with connect() as connection:
        connection.execute("PRAGMA journal_mode=DELETE")
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS site_settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS articles (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                slug TEXT NOT NULL UNIQUE,
                title TEXT NOT NULL,
                category TEXT NOT NULL DEFAULT 'news',
                summary TEXT NOT NULL DEFAULT '',
                body TEXT NOT NULL DEFAULT '',
                image TEXT NOT NULL DEFAULT '',
                published INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            """
        )
        had_settings = bool(
            connection.execute("SELECT COUNT(*) FROM site_settings").fetchone()[0]
        )
        for key, value in SETTING_DEFAULTS.items():
            connection.execute(
                "INSERT OR IGNORE INTO site_settings(key, value) VALUES(?, ?)", (key, value)
            )
        # Trước v1.3, giá trị "thachi" vẫn render giao diện JXNative mới.
        # Chuyển một lần để các máy đang nâng cấp không bất ngờ đổi giao diện.
        renderer_version = connection.execute(
            "SELECT value FROM site_settings WHERE key='theme_renderer_version'"
        ).fetchone()
        if renderer_version is None:
            # Máy cũ giữ giao diện đang quen dùng; máy cài mới dùng Thạch Chí.
            if had_settings:
                connection.execute(
                    "INSERT OR REPLACE INTO site_settings(key,value) VALUES('theme','modern')"
                )
            connection.execute(
                "INSERT INTO site_settings(key,value) VALUES('theme_renderer_version','2')"
            )
        # Luôn bổ sung các bài Web A còn thiếu. INSERT OR IGNORE trong hàm nhập
        # giữ nguyên mọi bài có cùng slug mà quản trị viên đã chỉnh sửa.
        _import_legacy_articles(connection)
        if not connection.execute("SELECT COUNT(*) FROM articles").fetchone()[0]:
            now = _now()
            connection.execute(
                """INSERT INTO articles
                   (slug,title,category,summary,body,image,published,created_at,updated_at)
                   VALUES(?,?,?,?,?,?,?,?,?)""",
                (
                    "chao-mung",
                    "Chào mừng đến với máy chủ",
                    "news",
                    "Website JXNative đã sẵn sàng.",
                    "<p>Hãy đăng nhập khu vực quản lý để cập nhật nội dung website.</p>",
                    "",
                    1,
                    now,
                    now,
                ),
            )
    try:
        os.chmod(DATABASE_PATH, 0o644)
    except OSError:
        pass


def _now():
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _decode_php_value(value):
    return html.unescape(value.replace("\\'", "'").replace("\\\\", "\\"))


def _field(source, slug, name):
    key = re.escape(slug + "_" + name)
    match = re.search(
        r"\$bilContentFile\['" + key + r"'\]\s*=\s*'((?:\\.|[^'])*)'\s*;",
        source,
        re.DOTALL,
    )
    return _decode_php_value(match.group(1)) if match else ""


def _import_legacy_articles(connection):
    if not LEGACY_CONTENT.is_dir():
        return
    now = _now()
    for path in sorted(LEGACY_CONTENT.glob("*.php")):
        slug = path.stem
        if slug in {"index", "__list_content"} or not SLUG_RE.fullmatch(slug):
            continue
        source = path.read_text(encoding="utf-8", errors="ignore")
        title = _field(source, slug, "title")
        body = _field(source, slug, "content")
        if not title or not body:
            continue
        category = _field(source, slug, "platform") or "news"
        summary = _field(source, slug, "priview")
        image = _field(source, slug, "poster")
        hidden = _field(source, slug, "ishidden")
        connection.execute(
            """INSERT OR IGNORE INTO articles
               (slug,title,category,summary,body,image,published,created_at,updated_at)
               VALUES(?,?,?,?,?,?,?,?,?)""",
            (slug, title, category, summary, body, image, 0 if hidden == "hidden" else 1, now, now),
        )


def get_settings():
    with connect() as connection:
        values = dict(connection.execute("SELECT key,value FROM site_settings").fetchall())
    result = dict(SETTING_DEFAULTS)
    result.update(values)
    if result.get("theme") not in THEMES:
        result["theme"] = "thachi"
    return result


def update_settings(values):
    allowed = set(SETTING_DEFAULTS)
    theme = values.get("theme")
    if theme is not None and theme not in THEMES:
        raise ValueError("Giao diện không hợp lệ")
    with connect() as connection:
        for key, value in values.items():
            if key in allowed:
                connection.execute(
                    "INSERT OR REPLACE INTO site_settings(key,value) VALUES(?,?)",
                    (key, str(value).strip()),
                )


def list_articles(published_only=False, category=None, limit=None):
    where = []
    params = []
    if published_only:
        where.append("published=1")
    if category:
        where.append("category=?")
        params.append(category)
    sql = "SELECT * FROM articles"
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY id DESC"
    if limit:
        sql += " LIMIT ?"
        params.append(int(limit))
    with connect() as connection:
        return connection.execute(sql, params).fetchall()


def get_article(slug, published_only=False):
    sql = "SELECT * FROM articles WHERE slug=?"
    if published_only:
        sql += " AND published=1"
    with connect() as connection:
        return connection.execute(sql, (slug,)).fetchone()


def save_article(article_id, values):
    slug = values.get("slug", "").strip().lower()
    if not SLUG_RE.fullmatch(slug):
        raise ValueError("Slug chỉ dùng chữ thường, số, gạch ngang hoặc gạch dưới")
    title = values.get("title", "").strip()
    if not title:
        raise ValueError("Tiêu đề không được để trống")
    data = (
        slug,
        title,
        values.get("category", "news").strip() or "news",
        values.get("summary", "").strip(),
        values.get("body", "").strip(),
        values.get("image", "").strip(),
        1 if values.get("published") else 0,
        _now(),
    )
    with connect() as connection:
        if article_id:
            connection.execute(
                """UPDATE articles SET slug=?,title=?,category=?,summary=?,body=?,image=?,
                   published=?,updated_at=? WHERE id=?""",
                data + (int(article_id),),
            )
            return int(article_id)
        cursor = connection.execute(
            """INSERT INTO articles
               (slug,title,category,summary,body,image,published,created_at,updated_at)
               VALUES(?,?,?,?,?,?,?,?,?)""",
            data[:7] + (data[7], data[7]),
        )
        return cursor.lastrowid


def get_article_by_id(article_id):
    with connect() as connection:
        return connection.execute("SELECT * FROM articles WHERE id=?", (int(article_id),)).fetchone()


def delete_article(article_id):
    with connect() as connection:
        connection.execute("DELETE FROM articles WHERE id=?", (int(article_id),))
