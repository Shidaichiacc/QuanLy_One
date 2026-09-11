import hmac
import html
import os
import secrets
import sqlite3
import sys
import time
from pathlib import Path

from flask import Blueprint, current_app, flash, jsonify, redirect, request, session, url_for
from werkzeug.utils import secure_filename


PROJECT_ROOT = Path(os.environ.get("QUANLY_ONE_ROOT", "/opt/QuanLy_One"))
sys.path.insert(0, str(PROJECT_ROOT / "app" / "shared"))
from site_store import (  # noqa: E402
    THEME_CATALOG,
    THEMES,
    delete_article,
    get_article_by_id,
    get_settings,
    list_articles,
    save_article,
    update_settings,
)

IMAGE_ROOT = PROJECT_ROOT / "app" / "web" / "assets" / "legacy" / "library" / "images"
MEDIA_ROOT = IMAGE_ROOT / "uploads"
MEDIA_SUFFIXES = {".jpg", ".jpeg", ".png", ".gif", ".webp"}
MEDIA_MAX_BYTES = 10 * 1024 * 1024
CATEGORY_LABELS = {"news": "Tin tức", "t_nag": "Tính năng", "event": "Sự kiện"}


STYLE = """
<style>
body{font:15px system-ui;background:#edf1f5;color:#293f54;margin:0;padding:24px}main{max-width:1080px;margin:auto}
a{color:#3b89d4}.top{display:flex;justify-content:space-between;align-items:center;gap:12px;flex-wrap:wrap;background:#293f54;color:#fff;padding:15px 18px;margin:-24px -24px 24px}.top a{color:#d5e5f4}.card{background:#fff;border:1px solid #dce3ea;padding:20px;margin:16px 0;border-radius:6px;box-shadow:0 2px 9px rgba(41,63,84,.08)}
input,select,textarea{box-sizing:border-box;width:100%;padding:10px;border-radius:4px;border:1px solid #b9c6d2;background:#fff;color:#293f54;margin:5px 0 12px}textarea{min-height:120px}textarea.body{min-height:430px;font-family:ui-monospace,monospace}
button,.btn{display:inline-block;padding:10px 14px;border:0;border-radius:4px;background:#3b89d4;color:#fff;text-decoration:none;font-weight:700;cursor:pointer}.danger{background:#d9534f}.muted{color:#718294}.ok{color:#07866f}.err{color:#c4322e}
table{width:100%;border-collapse:collapse}th,td{padding:10px;border-bottom:1px solid #dce3ea;text-align:left}th{background:#f4f7f9}form.inline{display:inline}.grid{display:grid;grid-template-columns:1fr 1fr;gap:14px}.tools{display:flex;gap:10px;flex-wrap:wrap;margin:15px 0}@media(max-width:700px){.grid{grid-template-columns:1fr}}
</style>
"""


def _csrf():
    token = session.get("csrf_token")
    if not token:
        token = secrets.token_urlsafe(32)
        session["csrf_token"] = token
    return token


def _valid_csrf():
    supplied = request.form.get("csrf_token", "")
    expected = session.get("csrf_token", "")
    return bool(supplied and expected and hmac.compare_digest(supplied, expected))


def _header(title):
    return '<h1 class="page-heading">' + title + '</h1>'


def _manager_page(body, page, **context):
    return current_app.extensions["render_manager_page"](body, page=page, **context)


def _media_catalog():
    IMAGE_ROOT.mkdir(parents=True, exist_ok=True)
    files = sorted(
        (path for path in IMAGE_ROOT.rglob("*") if path.is_file() and path.suffix.lower() in MEDIA_SUFFIXES and ".trash" not in path.parts),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    images = []
    for path in files:
        relative = path.relative_to(IMAGE_ROOT).as_posix()
        parts = Path(relative).parts
        images.append(
            {
                "relative": relative,
                "url": "/library/images/" + relative,
                "folder": parts[0] if len(parts) > 1 else "__root__",
                "size_kb": round(path.stat().st_size / 1024, 1),
            }
        )
    folders = sorted({image["folder"] for image in images}, key=lambda value: (value != "__root__", value.lower()))
    return images, folders


def _store_uploaded_image(uploaded):
    original = secure_filename(uploaded.filename if uploaded else "")
    suffix = Path(original).suffix.lower()
    if not uploaded or not original or suffix not in MEDIA_SUFFIXES:
        raise ValueError("Chỉ nhận ảnh JPG, PNG, GIF hoặc WEBP")
    uploaded.stream.seek(0, os.SEEK_END)
    size = uploaded.stream.tell()
    uploaded.stream.seek(0)
    if size <= 0 or size > MEDIA_MAX_BYTES:
        raise ValueError("Ảnh phải có dung lượng từ 1 byte đến 10 MB")
    header = uploaded.stream.read(16)
    uploaded.stream.seek(0)
    signatures = {
        ".jpg": header.startswith(b"\xff\xd8\xff"),
        ".jpeg": header.startswith(b"\xff\xd8\xff"),
        ".png": header.startswith(b"\x89PNG\r\n\x1a\n"),
        ".gif": header.startswith((b"GIF87a", b"GIF89a")),
        ".webp": header.startswith(b"RIFF") and header[8:12] == b"WEBP",
    }
    if not signatures.get(suffix):
        raise ValueError("Nội dung file không đúng định dạng ảnh")
    MEDIA_ROOT.mkdir(parents=True, exist_ok=True)
    name = str(time.time_ns()) + "-" + secrets.token_hex(3) + "-" + original
    uploaded.save(MEDIA_ROOT / name)
    return "/library/images/uploads/" + name


def register_site_admin(app):
    blueprint = Blueprint("site_admin", __name__)

    @blueprint.route("/website", methods=["GET", "POST"])
    def settings():
        if request.method == "POST":
            if not _valid_csrf():
                flash("Phiên biểu mẫu không hợp lệ", "err")
            else:
                try:
                    update_settings(
                        {
                            "title": request.form.get("title", ""),
                            "theme": request.form.get("theme", "modern"),
                            "tagline": request.form.get("tagline", ""),
                            "announcement": request.form.get("announcement", ""),
                            "download_url": request.form.get("download_url", ""),
                            "facebook_url": request.form.get("facebook_url", ""),
                            "facebook_group": request.form.get("facebook_group", ""),
                            "support_email": request.form.get("support_email", ""),
                            "support_phone": request.form.get("support_phone", ""),
                            "support_text": request.form.get("support_text", ""),
                        }
                    )
                    flash("Đã lưu cấu hình website", "ok")
                    return redirect(url_for("site_admin.settings"))
                except Exception as exc:
                    flash("Không lưu được: " + str(exc), "err")
        values = get_settings()
        body = _header("Cấu hình Website") + """
        <style>.theme-picker{display:grid;grid-template-columns:minmax(220px,380px) minmax(280px,1fr);gap:12px;align-items:stretch;margin:7px 0 18px}.theme-picker select{margin:0}.theme-summary{display:flex;align-items:center;justify-content:space-between;gap:14px;padding:12px 14px;border:1px solid var(--line);border-radius:9px;background:rgba(201,164,95,.035)}.theme-summary b,.theme-summary small{display:block}.theme-summary small{margin-top:3px;color:var(--mut)}.theme-preview-link{white-space:nowrap}@media(max-width:760px){.theme-picker{grid-template-columns:1fr}.theme-summary{align-items:flex-start;flex-direction:column}}</style>
        <form method="post" class="card"><input type="hidden" name="csrf_token" value="{{ csrf }}">
          <div class="grid"><label>Tên website<input name="title" value="{{ s.title }}" required></label>
          <label>Dòng giới thiệu<input name="tagline" value="{{ s.tagline }}"></label></div>
          <label for="websiteTheme">Giao diện website công khai</label><div class="theme-picker"><select id="websiteTheme" name="theme">{% for key,meta in theme_catalog.items() %}<option value="{{key}}" data-label="{{meta.label}}" data-description="{{meta.description}}" {{'selected' if s.theme==key else ''}}>{{meta.label}}</option>{% endfor %}</select><div class="theme-summary"><span><b id="themeLabel"></b><small id="themeDescription"></small></span><a class="btn mut theme-preview-link" id="themePreview" href="/?theme_preview={{s.theme}}" target="_blank" rel="noopener">Xem thử</a></div></div>
          <label>Thông báo chạy trên trang chủ<input name="announcement" value="{{ s.announcement }}"></label>
          <div class="grid"><label>Đường dẫn tải game<input name="download_url" value="{{ s.download_url }}"></label>
          <label>Facebook hỗ trợ<input name="facebook_url" value="{{ s.facebook_url }}"></label></div>
          <div class="grid"><label>Nhóm Facebook<input name="facebook_group" value="{{ s.facebook_group }}"></label>
          <label>Email hỗ trợ<input name="support_email" value="{{ s.support_email }}"></label></div>
          <label>Số điện thoại hỗ trợ<input name="support_phone" value="{{ s.support_phone }}"></label>
          <label>Nội dung nút hỗ trợ<input name="support_text" value="{{ s.support_text }}"></label>
          <button>Áp dụng và lưu cấu hình</button>
        </form><script>(function(){const select=document.getElementById('websiteTheme'),label=document.getElementById('themeLabel'),description=document.getElementById('themeDescription'),preview=document.getElementById('themePreview');function update(){const option=select.options[select.selectedIndex];label.textContent=option.dataset.label||option.textContent;description.textContent=option.dataset.description||'';preview.href='/?theme_preview='+encodeURIComponent(option.value)}select.addEventListener('change',update);update()})();</script>"""
        return _manager_page(body, "site_settings", s=values, themes=THEMES,
                             theme_catalog=THEME_CATALOG, csrf=_csrf())

    @blueprint.route("/website/articles")
    def articles():
        selected_category = request.args.get("category", "all")
        if selected_category not in {"all", *CATEGORY_LABELS}:
            selected_category = "all"
        search = request.args.get("q", "").strip()[:100]
        all_rows = list_articles()
        rows = all_rows if selected_category == "all" else [row for row in all_rows if row["category"] == selected_category]
        if search:
            needle = search.casefold()
            rows = [row for row in rows if needle in row["title"].casefold() or needle in row["slug"].casefold()]
        category_counts = {key: sum(1 for row in all_rows if row["category"] == key) for key in CATEGORY_LABELS}
        body = _header("Quản lý bài viết") + """
        <style>.content-tabs,.filter-tabs{display:flex;gap:7px;flex-wrap:wrap}.content-tabs{border-bottom:1px solid var(--line);margin-bottom:17px}.content-tabs .btn{border-radius:8px 8px 0 0}.filter-tabs{margin:13px 0}.filter-tabs .btn.active{background:var(--acc);color:#fff}.article-search{display:flex;gap:6px;align-items:center;margin-left:auto;min-width:min(360px,100%)}.article-search input{margin:0}.article-actions{display:flex;gap:5px;align-items:center;flex-wrap:wrap}.article-actions button,.article-actions .btn{padding:7px 10px}.status-visible{color:#07866f;font-weight:700}.status-hidden{color:#a64642;font-weight:700}</style>
        <div class="content-tabs"><a class="btn" href="{{ url_for('site_admin.articles') }}">📝 Bài viết</a><a class="btn mut" href="{{ url_for('site_admin.media') }}">🖼️ Thư viện ảnh</a><a class="btn mut" href="{{ url_for('site_admin.article_new') }}">＋ Viết bài mới</a></div>
        <div class="tools"><form class="article-search" method="get"><input type="hidden" name="category" value="{{ selected_category }}"><input name="q" value="{{ search }}" placeholder="Tìm theo tiêu đề hoặc slug"><button>Tìm</button></form></div>
        <div class="filter-tabs"><a class="btn {{ 'active' if selected_category == 'all' else 'mut' }}" href="{{ url_for('site_admin.articles', category='all', q=search) }}">Tất cả ({{ total }})</a>{% for key,label in category_labels.items() %}<a class="btn {{ 'active' if selected_category == key else 'mut' }}" href="{{ url_for('site_admin.articles', category=key, q=search) }}">{{ label }} ({{ category_counts[key] }})</a>{% endfor %}</div>
        <div class="card scroll"><table><tr><th>Tiêu đề</th><th>Nhóm</th><th>Trạng thái</th><th>Thao tác</th></tr>
        {% for a in articles %}<tr><td>{{ a.title }}<br><small class="muted">{{ a.slug }}</small></td><td>{{ category_labels.get(a.category, a.category) }}</td><td><span class="{{ 'status-visible' if a.published else 'status-hidden' }}">{{ 'Đang hiện' if a.published else 'Đang ẩn' }}</span></td><td><div class="article-actions"><a class="btn mut" href="{{ url_for('site_admin.article_preview', article_id=a.id) }}">Xem</a><a class="btn" href="{{ url_for('site_admin.article_edit', article_id=a.id) }}">Sửa</a><form class="inline" method="post" action="{{ url_for('site_admin.article_toggle', article_id=a.id) }}"><input type="hidden" name="csrf_token" value="{{ csrf }}"><input type="hidden" name="category" value="{{ selected_category }}"><input type="hidden" name="q" value="{{ search }}"><button class="{{ 'danger' if a.published else 'ok' }}">{{ 'Ẩn' if a.published else 'Hiện' }}</button></form><form class="inline" method="post" action="{{ url_for('site_admin.article_delete', article_id=a.id) }}" data-confirm="Xóa bài viết này?"><input type="hidden" name="csrf_token" value="{{ csrf }}"><button class="danger">Xóa</button></form></div></td></tr>{% else %}<tr><td colspan="4">Không có bài viết trong nhóm này.</td></tr>{% endfor %}
        </table></div>"""
        return _manager_page(
            body,
            "site_articles",
            articles=rows,
            total=len(all_rows),
            selected_category=selected_category,
            search=search,
            category_labels=CATEGORY_LABELS,
            category_counts=category_counts,
            csrf=_csrf(),
        )

    def article_form(article=None):
        item = dict(article) if article else {"id": "", "slug": "", "title": "", "category": "news", "summary": "", "body": "", "image": "", "published": 1}
        picker_images, picker_folders = _media_catalog()
        body = _header("Sửa bài viết" if article else "Viết bài mới") + """
        <style>.article-workspace{display:grid;grid-template-columns:minmax(440px,1fr) minmax(390px,1fr);gap:18px;align-items:start}.article-editor{margin:0}.article-preview{position:sticky;top:82px;margin:0;padding:0;overflow:hidden}.article-preview-head{padding:12px 15px;background:#293f54;color:#fff;font-weight:700}.article-preview iframe{display:block;width:100%;height:720px;border:0;background:#f9f0e1}.editor-toolbar{display:flex;gap:5px;flex-wrap:wrap;margin:5px 0 8px}.editor-toolbar button{padding:6px 9px;background:#5d6e7e}.image-chooser{background:#07866f;margin:5px 0 8px}.image-field{display:flex;gap:6px;align-items:center}.image-field input{margin:5px 0 12px}.image-field button{white-space:nowrap}.article-editor textarea.body{min-height:390px}.preview-note{font-size:12px;color:var(--mut);font-weight:400;margin-left:8px}.image-picker-modal[hidden]{display:none}.image-picker-modal{position:fixed;inset:0;z-index:200;background:rgba(12,24,36,.72);display:grid;place-items:center;padding:24px}.image-picker-dialog{width:min(980px,96vw);max-height:90vh;background:#fff;border-radius:13px;box-shadow:0 18px 60px rgba(0,0,0,.35);display:flex;flex-direction:column;overflow:hidden}.image-picker-head{display:flex;align-items:center;justify-content:space-between;padding:14px 18px;background:#293f54;color:#fff}.image-picker-head h2{margin:0;font-size:18px}.picker-close{padding:6px 10px;background:#5d6e7e}.picker-tabs{display:flex;gap:6px;padding:12px 16px 0;border-bottom:1px solid #dce3ea}.picker-tab{border-radius:8px 8px 0 0;background:#5d6e7e}.picker-tab.active{background:#3b89d4}.picker-pane{display:none;padding:15px 18px;overflow:auto}.picker-pane.active{display:block}.picker-filter{display:flex;gap:10px;align-items:center;margin-bottom:13px}.picker-filter label{margin:0;white-space:nowrap}.picker-filter select{margin:0;max-width:330px}.picker-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(145px,1fr));gap:10px}.picker-image{padding:7px;background:#f4f7f9;color:#293f54;border:1px solid #dce3ea;text-align:left;overflow:hidden}.picker-image:hover{border-color:#3b89d4;opacity:1}.picker-image img{display:block;width:100%;height:105px;object-fit:contain;background:#fff;margin-bottom:6px}.picker-image span{display:block;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;font-size:11px}.upload-panel{max-width:620px}.upload-status{min-height:22px;margin-top:8px}@media(max-width:1050px){.article-workspace{grid-template-columns:1fr}.article-preview{position:static}.article-preview iframe{height:600px}}@media(max-width:600px){.image-picker-modal{padding:8px}.picker-grid{grid-template-columns:repeat(2,minmax(0,1fr))}.image-field{display:block}}</style>
        <style>.content-tabs{display:flex;gap:7px;flex-wrap:wrap;border-bottom:1px solid var(--line);margin-bottom:17px}.content-tabs .btn{border-radius:8px 8px 0 0}.picker-image[hidden]{display:none!important}</style><div class="content-tabs"><a class="btn mut" href="{{ url_for('site_admin.articles') }}">📝 Bài viết</a><a class="btn mut" href="{{ url_for('site_admin.media') }}">🖼️ Thư viện ảnh</a><a class="btn {{ 'mut' if a.id else '' }}" href="{{ url_for('site_admin.article_new') }}">＋ Viết bài mới</a></div>
        <div class="article-workspace"><form method="post" class="card article-editor" id="articleEditor"><input type="hidden" name="csrf_token" value="{{ csrf }}">
          <div class="grid"><label>Tiêu đề<input id="articleTitle" name="title" value="{{ a.title }}" required></label><label>Slug<input name="slug" value="{{ a.slug }}" required></label></div>
          <div class="grid"><label>Nhóm<select id="articleCategory" name="category">{% for key,label in category_labels.items() %}<option value="{{ key }}" {{ 'selected' if key == a.category else '' }}>{{ label }}</option>{% endfor %}</select></label><label>Ảnh đại diện<div class="image-field"><input id="articleImage" name="image" value="{{ a.image }}" placeholder="/library/images/poster/default.jpg"><button type="button" class="mut" data-open-image="cover">Chọn ảnh</button></div></label></div>
          <label>Tóm tắt<textarea id="articleSummary" name="summary">{{ a.summary }}</textarea></label>
          <label>Nội dung HTML</label><button type="button" class="image-chooser" data-open-image="body">🖼 Chèn ảnh từ thư viện hoặc máy tính</button><div class="editor-toolbar"><button type="button" data-tag="h2">Tiêu đề</button><button type="button" data-tag="strong">In đậm</button><button type="button" data-tag="p">Đoạn văn</button><button type="button" data-action="link">Liên kết</button><button type="button" data-action="image">Nhập đường dẫn ảnh</button></div>
          <textarea id="articleBody" class="body" name="body">{{ a.body }}</textarea>
          <label><input style="width:auto" type="checkbox" name="published" value="1" {{ 'checked' if a.published else '' }}> Hiển thị bài viết</label><br>
          <button>Lưu bài viết</button> <a class="btn mut" href="{{ url_for('site_admin.articles') }}">Quay lại</a>
        </form><section class="card article-preview"><div class="article-preview-head">Xem trước trực tiếp <span class="preview-note">Không cần lưu bài</span></div><iframe id="articlePreview" sandbox=""></iframe></section></div>
        <div class="image-picker-modal" id="imagePicker" hidden><div class="image-picker-dialog"><div class="image-picker-head"><h2>Chọn ảnh cho bài viết</h2><button type="button" class="picker-close" id="pickerClose">✕ Đóng</button></div><div class="picker-tabs"><button type="button" class="picker-tab active" data-picker-tab="library">Từ thư viện</button><button type="button" class="picker-tab" data-picker-tab="upload">Từ máy tính</button></div>
          <div class="picker-pane active" data-picker-pane="library"><div class="picker-filter"><label>Thư mục</label><select id="pickerFolder"><option value="all">Tất cả ảnh ({{ picker_images|length }})</option>{% for folder in picker_folders %}<option value="{{ folder }}">{{ 'Thư mục gốc' if folder == '__root__' else folder }}</option>{% endfor %}</select></div><div class="picker-grid" id="pickerGrid">{% for item in picker_images %}<button type="button" class="picker-image" data-folder="{{ item.folder }}" data-image-url="{{ item.url }}" title="{{ item.relative }}"><img src="{{ item.url }}" loading="lazy" alt=""><span>{{ item.relative }}</span></button>{% endfor %}</div><p class="muted" id="pickerEmpty" hidden>Thư mục này chưa có ảnh.</p></div>
          <div class="picker-pane" data-picker-pane="upload"><div class="upload-panel"><p class="muted">Chọn JPG, PNG, GIF hoặc WEBP, tối đa 10 MB. Ảnh sẽ được lưu vào <code>uploads</code> và chèn ngay vào bài.</p><input type="file" id="pickerUpload" accept="image/jpeg,image/png,image/gif,image/webp"><button type="button" id="pickerUploadButton">Tải lên và chèn ảnh</button><p class="upload-status muted" id="pickerUploadStatus"></p></div></div>
        </div></div>
        <script>(function(){const folder=document.getElementById('pickerFolder');function applyFolder(){const selected=folder.value;document.querySelectorAll('#pickerGrid .picker-image').forEach(item=>{item.style.display=selected==='all'||item.dataset.folder===selected?'':'none'})}folder.addEventListener('change',applyFolder);applyFolder()})();</script>
        <script>(function(){const modal=document.getElementById('imagePicker'),folder=document.getElementById('pickerFolder'),empty=document.getElementById('pickerEmpty'),upload=document.getElementById('pickerUpload'),uploadButton=document.getElementById('pickerUploadButton'),uploadStatus=document.getElementById('pickerUploadStatus'),body=document.getElementById('articleBody'),cover=document.getElementById('articleImage');let imageTarget='body';function openPicker(target){imageTarget=target;modal.hidden=false;document.body.style.overflow='hidden'}function closePicker(){modal.hidden=true;document.body.style.overflow=''}function applyImage(url){if(imageTarget==='cover'){cover.value=url;cover.dispatchEvent(new Event('input'))}else{const start=body.selectionStart,end=body.selectionEnd;body.setRangeText('<img src="'+url+'" alt="">',start,end,'end');body.dispatchEvent(new Event('input'));body.focus()}closePicker()}document.querySelectorAll('[data-open-image]').forEach(button=>button.addEventListener('click',()=>openPicker(button.dataset.openImage)));document.getElementById('pickerClose').addEventListener('click',closePicker);modal.addEventListener('click',event=>{if(event.target===modal)closePicker()});document.addEventListener('keydown',event=>{if(event.key==='Escape'&&!modal.hidden)closePicker()});document.querySelectorAll('[data-picker-tab]').forEach(button=>button.addEventListener('click',()=>{document.querySelectorAll('[data-picker-tab]').forEach(item=>item.classList.toggle('active',item===button));document.querySelectorAll('[data-picker-pane]').forEach(item=>item.classList.toggle('active',item.dataset.pickerPane===button.dataset.pickerTab))}));function filterImages(){let visible=0;document.querySelectorAll('.picker-image').forEach(item=>{const show=folder.value==='all'||item.dataset.folder===folder.value;item.hidden=!show;if(show)visible++});empty.hidden=visible!==0}folder.addEventListener('change',filterImages);document.querySelectorAll('.picker-image').forEach(item=>item.addEventListener('click',()=>applyImage(item.dataset.imageUrl)));uploadButton.addEventListener('click',async()=>{const file=upload.files[0];if(!file){uploadStatus.textContent='Hãy chọn một file ảnh.';uploadStatus.className='upload-status err';return}uploadButton.disabled=true;uploadStatus.textContent='Đang tải ảnh lên...';uploadStatus.className='upload-status muted';const data=new FormData();data.append('csrf_token',{{ csrf|tojson }});data.append('image',file);try{const response=await fetch({{ url_for('site_admin.media_upload_json')|tojson }},{method:'POST',body:data,headers:{Accept:'application/json'}});const result=await response.json();if(!response.ok||!result.ok)throw new Error(result.error||'Không tải được ảnh');applyImage(result.url)}catch(error){uploadStatus.textContent=error.message;uploadStatus.className='upload-status err'}finally{uploadButton.disabled=false}})})();</script>
        <script>(function(){const title=document.getElementById('articleTitle'),summary=document.getElementById('articleSummary'),image=document.getElementById('articleImage'),body=document.getElementById('articleBody'),preview=document.getElementById('articlePreview');const escapeHtml=value=>value.replace(/[&<>\"]/g,char=>({'&':'&amp;','<':'&lt;','>':'&gt;','\"':'&quot;'}[char]));function render(){const imageHtml=image.value.trim()?'<img class="cover" src="'+escapeHtml(image.value.trim())+'">':'';preview.srcdoc='<!doctype html><html><head><meta charset="utf-8"><style>body{margin:0;padding:26px 30px;background:#f9f0e1;color:#2e241c;font:14px/1.7 Tahoma,Arial,sans-serif}h1{margin:0 0 8px;color:#8d351d;font-size:25px;border-bottom:2px solid #a54100;padding-bottom:10px}.summary{color:#745d4c;font-style:italic;margin:10px 0 18px}.cover{display:block;max-width:100%;max-height:260px;object-fit:cover;margin:0 auto 18px;border:1px solid #c9ad91;padding:3px}img,video,iframe{max-width:100%;height:auto}table{width:100%;border-collapse:collapse}td,th{border:1px solid #906946;padding:7px}a{color:#a54100}</style></head><body><h1>'+escapeHtml(title.value||'Tiêu đề bài viết')+'</h1>'+imageHtml+'<div class="summary">'+escapeHtml(summary.value||'Tóm tắt bài viết sẽ hiển thị tại đây.')+'</div><article>'+body.value+'</article></body></html>'}let timer;[title,summary,image,body].forEach(input=>input.addEventListener('input',()=>{clearTimeout(timer);timer=setTimeout(render,120)}));document.querySelectorAll('.editor-toolbar button').forEach(button=>button.addEventListener('click',async()=>{const start=body.selectionStart,end=body.selectionEnd,text=body.value.slice(start,end);let before='',after='';if(button.dataset.tag){before='<'+button.dataset.tag+'>';after='</'+button.dataset.tag+'>'}else if(button.dataset.action==='link'){const url=await window.JXDialog.prompt('Đường dẫn liên kết:',{title:'Chèn liên kết',initial:'https://'});if(!url)return;before='<a href="'+url+'">';after='</a>'}else{const url=await window.JXDialog.prompt('Đường dẫn ảnh, ví dụ /library/images/...:',{title:'Chèn ảnh bằng đường dẫn',initial:'/library/images/'});if(!url)return;before='<img src="'+url+'" alt="">'}body.setRangeText(before+text+after,start,end,'end');body.dispatchEvent(new Event('input'));body.focus()}));render()})();</script>"""
        return _manager_page(
            body,
            "site_article",
            a=item,
            picker_images=picker_images,
            picker_folders=picker_folders,
            category_labels=CATEGORY_LABELS,
            csrf=_csrf(),
        )

    def persist(article_id=None):
        if not _valid_csrf():
            flash("Phiên biểu mẫu không hợp lệ", "err")
            return None
        try:
            return save_article(
                article_id,
                {
                    "slug": request.form.get("slug", ""),
                    "title": request.form.get("title", ""),
                    "category": request.form.get("category", "news"),
                    "summary": request.form.get("summary", ""),
                    "body": request.form.get("body", ""),
                    "image": request.form.get("image", ""),
                    "published": bool(request.form.get("published")),
                },
            )
        except (ValueError, sqlite3.Error) as exc:
            flash("Không lưu được: " + str(exc), "err")
            return None

    @blueprint.route("/website/articles/new", methods=["GET", "POST"])
    def article_new():
        if request.method == "POST" and persist():
            flash("Đã thêm bài viết", "ok")
            return redirect(url_for("site_admin.articles"))
        return article_form()

    @blueprint.route("/website/articles/<int:article_id>", methods=["GET", "POST"])
    def article_edit(article_id):
        article = get_article_by_id(article_id)
        if not article:
            return redirect(url_for("site_admin.articles"))
        if request.method == "POST" and persist(article_id):
            flash("Đã cập nhật bài viết", "ok")
            return redirect(url_for("site_admin.articles"))
        return article_form(article)

    @blueprint.route("/website/articles/<int:article_id>/preview")
    def article_preview(article_id):
        article = get_article_by_id(article_id)
        if not article:
            flash("Không tìm thấy bài viết", "err")
            return redirect(url_for("site_admin.articles"))
        title = html.escape(article["title"] or "Bài viết chưa có tiêu đề")
        summary = html.escape(article["summary"] or "")
        image = html.escape(article["image"] or "", quote=True)
        cover = '<img class="cover" src="' + image + '" alt="">' if image else ""
        preview_doc = """<!doctype html><html lang="vi"><head><meta charset="utf-8"><style>
        body{margin:0;padding:28px 34px;background:#f9f0e1;color:#2e241c;font:14px/1.7 Tahoma,Arial,sans-serif}
        h1{margin:0 0 9px;color:#8d351d;font-size:27px;border-bottom:2px solid #a54100;padding-bottom:10px}
        .summary{color:#745d4c;font-style:italic;margin:10px 0 18px}.cover{display:block;max-width:100%;max-height:360px;object-fit:contain;margin:0 auto 18px;border:1px solid #c9ad91;padding:3px}
        article img,article video,article iframe{max-width:100%;height:auto}table{width:100%;border-collapse:collapse}td,th{border:1px solid #906946;padding:7px}a{color:#a54100}
        </style></head><body><h1>""" + title + "</h1>" + cover + '<div class="summary">' + summary + "</div><article>" + (article["body"] or "") + "</article></body></html>"
        body = _header("Xem bài viết") + """
        <div class="tools"><a class="btn" href="{{ url_for('site_admin.article_edit', article_id=article.id) }}">Sửa bài viết</a><a class="btn mut" href="{{ url_for('site_admin.articles') }}">Quay lại danh sách</a></div>
        <section class="card" style="padding:0;overflow:hidden"><iframe id="savedArticlePreview" title="Xem trước bài viết" sandbox="" style="display:block;width:100%;height:760px;border:0;background:#f9f0e1"></iframe></section>
        <script>document.getElementById('savedArticlePreview').srcdoc={{ preview_doc|tojson }};</script>"""
        return _manager_page(body, "site_article", article=article, preview_doc=preview_doc)

    @blueprint.route("/website/articles/<int:article_id>/delete", methods=["POST"])
    def article_delete(article_id):
        if _valid_csrf():
            delete_article(article_id)
            flash("Đã xóa bài viết", "ok")
        else:
            flash("Phiên biểu mẫu không hợp lệ", "err")
        return redirect(url_for("site_admin.articles"))

    @blueprint.route("/website/articles/<int:article_id>/toggle", methods=["POST"])
    def article_toggle(article_id):
        selected_category = request.form.get("category", "all")
        search = request.form.get("q", "").strip()[:100]
        if selected_category not in {"all", *CATEGORY_LABELS}:
            selected_category = "all"
        if not _valid_csrf():
            flash("Phiên biểu mẫu không hợp lệ", "err")
        else:
            article = get_article_by_id(article_id)
            if not article:
                flash("Không tìm thấy bài viết", "err")
            else:
                values = dict(article)
                values["published"] = not bool(article["published"])
                try:
                    save_article(article_id, values)
                    flash("Đã hiện bài viết" if values["published"] else "Đã ẩn bài viết", "ok")
                except (ValueError, sqlite3.Error) as exc:
                    flash("Không đổi được trạng thái: " + str(exc), "err")
        return redirect(url_for("site_admin.articles", category=selected_category, q=search))

    @blueprint.route("/website/media", methods=["GET", "POST"])
    def media():
        if request.method == "POST":
            if not _valid_csrf():
                flash("Phiên biểu mẫu không hợp lệ", "err")
            else:
                try:
                    image_url = _store_uploaded_image(request.files.get("image"))
                    flash("Đã tải ảnh lên: " + image_url, "ok")
                    return redirect(url_for("site_admin.media", folder="uploads"))
                except ValueError as exc:
                    flash(str(exc), "err")
        all_images, folders = _media_catalog()
        selected_folder = request.args.get("folder", "all")
        if selected_folder != "all" and selected_folder not in folders:
            selected_folder = "all"
        images = all_images if selected_folder == "all" else [image for image in all_images if image["folder"] == selected_folder]
        body = _header("Thư viện ảnh Website") + """
        <style>.content-tabs{display:flex;gap:7px;flex-wrap:wrap;border-bottom:1px solid var(--line);margin-bottom:17px}.content-tabs .btn{border-radius:8px 8px 0 0}.folder-filter{display:flex;gap:10px;align-items:center;margin:12px 0;max-width:460px}.folder-filter label{margin:0;white-space:nowrap}.folder-filter select{margin:0}.media-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(180px,1fr));gap:12px}.media-card{border:1px solid var(--line);border-radius:9px;padding:8px;background:#f7f9fb;min-width:0}.media-card img{display:block;width:100%;height:125px;object-fit:contain;background:#fff;border-radius:6px}.media-path{font-size:11px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;margin:7px 0}.media-card .row-actions{display:flex;gap:5px;justify-content:space-between;align-items:center}.media-card button{padding:6px 9px}@media(max-width:520px){.media-grid{grid-template-columns:repeat(2,minmax(0,1fr))}}</style>
        <div class="content-tabs"><a class="btn mut" href="{{ url_for('site_admin.articles') }}">📝 Bài viết</a><a class="btn" href="{{ url_for('site_admin.media') }}">🖼️ Thư viện ảnh</a><a class="btn mut" href="{{ url_for('site_admin.article_new') }}">＋ Viết bài mới</a></div>
        <form method="post" enctype="multipart/form-data" class="card"><input type="hidden" name="csrf_token" value="{{ csrf }}"><h2>Tải ảnh từ máy tính</h2><p class="muted">JPG, PNG, GIF hoặc WEBP; tối đa 10 MB.</p><label>Chọn ảnh<input type="file" name="image" accept="image/jpeg,image/png,image/gif,image/webp" required></label><button>Tải ảnh lên</button></form>
        <form method="get" class="folder-filter"><label>Lọc thư mục</label><select name="folder" onchange="this.form.submit()"><option value="all">Tất cả ảnh ({{ all_images|length }})</option>{% for folder in folders %}<option value="{{ folder }}" {{ 'selected' if selected_folder == folder else '' }}>{{ 'Thư mục gốc' if folder == '__root__' else folder }}</option>{% endfor %}</select></form>
        <div class="card"><p class="muted">Đang hiển thị {{ images|length }} ảnh. Bấm đường dẫn để sao chép; file ảnh không bị di chuyển khi lọc thư mục.</p><div class="media-grid">{% for image in images %}<article class="media-card"><img src="{{ image.url }}" loading="lazy" alt=""><input class="media-path" readonly value="{{ image.url }}" title="Bấm để sao chép" onclick="this.select();navigator.clipboard&&navigator.clipboard.writeText(this.value)"><div class="row-actions"><small class="muted">{{ image.size_kb }} KB</small><form method="post" action="{{ url_for('site_admin.media_delete', filename=image.relative) }}" data-confirm="Chuyển ảnh này vào thùng rác? Bài viết đang dùng ảnh có thể bị mất hình."><input type="hidden" name="csrf_token" value="{{ csrf }}"><input type="hidden" name="folder" value="{{ selected_folder }}"><button class="danger">Xóa</button></form></div></article>{% else %}<p>Thư mục này chưa có ảnh.</p>{% endfor %}</div></div>"""
        return _manager_page(
            body,
            "site_articles",
            images=images,
            all_images=all_images,
            folders=folders,
            selected_folder=selected_folder,
            csrf=_csrf(),
        )

    @blueprint.route("/website/media/upload-json", methods=["POST"])
    def media_upload_json():
        if not _valid_csrf():
            return jsonify(ok=False, error="Phiên biểu mẫu không hợp lệ"), 400
        try:
            image_url = _store_uploaded_image(request.files.get("image"))
            return jsonify(ok=True, url=image_url)
        except ValueError as exc:
            return jsonify(ok=False, error=str(exc)), 400

    @blueprint.route("/website/media/<path:filename>/delete", methods=["POST"])
    def media_delete(filename):
        selected_folder = request.form.get("folder", "all")
        if not _valid_csrf():
            flash("Phiên biểu mẫu không hợp lệ", "err")
            return redirect(url_for("site_admin.media", folder=selected_folder))
        image_path = (IMAGE_ROOT / filename).resolve()
        try:
            image_path.relative_to(IMAGE_ROOT.resolve())
        except ValueError:
            image_path = Path("/")
        if not image_path.is_file() or image_path.suffix.lower() not in MEDIA_SUFFIXES or ".trash" in image_path.parts:
            flash("Không tìm thấy ảnh hợp lệ", "err")
            return redirect(url_for("site_admin.media", folder=selected_folder))
        trash = IMAGE_ROOT / ".trash"
        trash.mkdir(exist_ok=True)
        destination = trash / (str(int(time.time())) + "-" + filename.replace("/", "__"))
        image_path.replace(destination)
        flash("Đã chuyển ảnh vào thùng rác", "ok")
        return redirect(url_for("site_admin.media", folder=selected_folder))

    app.jinja_env.globals["site_admin_url"] = lambda: url_for("site_admin.settings")
    app.jinja_env.globals["site_articles_url"] = lambda: url_for("site_admin.articles")
    app.jinja_env.globals["site_article_new_url"] = lambda: url_for("site_admin.article_new")
    app.jinja_env.globals["site_media_url"] = lambda: url_for("site_admin.media")
    app.register_blueprint(blueprint)
