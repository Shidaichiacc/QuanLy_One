# Kiến trúc QuanLy One

## Tổng quan

QuanLy One là bộ quản lý máy chủ JX chạy trên Ubuntu x86_64. Nginx nhận HTTP cổng
80, chuyển `/admin/` tới Web quản trị và `/` tới Website công khai. Game chạy bằng
các service systemd; MySQL và MSSQL chạy trong Docker.

```text
Trình duyệt
  └─ Nginx :80
      ├─ /admin/ → jx-webpanel → Flask Admin :8080
      ├─ /       → quanly-public → Flask Public :8000
      └─ asset giao diện cũ → app/web/assets/legacy

Flask Admin
  ├─ systemd → 6 thành phần game
  ├─ Docker  → MySQL 5.7 + MSSQL 2019
  ├─ data/   → trạng thái, nội dung, upload và backup
  └─ JX_Servers/ → phiên bản server, Active, Runtime, Scripts và MOD
```

## Mã nguồn chính

- `app/web/admin/app.py`: Flask Admin, dashboard, console, game settings, database, backup và updater.
- `app/web/admin/manager_extension.py`: đăng nhập Admin, thiết lập lần đầu, đổi mật khẩu và quản lý phiên bản server.
- `app/web/admin/site_admin.py`: quản trị cấu hình/nội dung Website công khai.
- `app/web/admin/database_tools.js`: tương tác giao diện database/backup.
- `app/web/admin/polish.css`: lớp giao diện bổ sung của Admin.
- `app/web/public/app.py`: Website công khai và chọn theme.
- `app/shared/`: mã dùng chung cho đăng nhập, mật khẩu database, mã hóa JX và kho nội dung.
- `tools/`: thiết lập database/site, backup, khóa đăng nhập, đóng gói và tự cập nhật.

Admin hiện chủ yếu dùng template chuỗi phía server trong các module Flask. Hãy
mở rộng thành phần hiện có trước khi cân nhắc tách framework hoặc viết lại lớn.

## Runtime chuẩn

- Mã cài: `/opt/QuanLy_One`
- Bí mật: `/opt/QuanLy_One/.env`
- Phiên bản server: `JX_Servers/JX_Versions/<tên>`
- Server active: symlink `JX_Servers/Active`
- MOD chung: `JX_Servers/MOD`
- Trạng thái: `data/state`
- Dữ liệu database: `data/database/mysql/data` và `data/database/mssql/data`
- Backup: `data/database/backups`
- Upload: `data/uploads`

Các đường dẫn trên là dữ liệu vận hành, không phải dữ liệu để đồng bộ ngược vào Git.

## Dịch vụ

- Web: `jx-webpanel`, `quanly-public`, `nginx`
- Nền: `jx-backup-scheduler`, transient `jxnative-update`
- Game: `jxpaysys`, `jxrelaypay`, `jxgoddess`, `jxbishop`, `jxs3relay`, `jxgame`
- Container: `quanlyone_mysql`, `quanlyone_mssql`

Thứ tự Start All do `JX_Servers/Scripts/start-game-stack` điều phối và chờ cổng
sẵn sàng. Không thay bằng việc bật đồng thời sáu service nếu đang sửa luồng khởi động.

## Cài đặt và cập nhật

- `install.sh` cài dependency, venv, systemd, Nginx và dựng Web trước. Máy mới hoàn
  tất mật khẩu/database bằng trình thiết lập lần đầu.
- `update.sh` yêu cầu game đã Stop All, giữ dữ liệu runtime, cập nhật dependency/cấu
  hình dịch vụ rồi khởi động lại Web và database cần thiết.
- `tools/apply-update` tải GitHub Release, kiểm tra SHA256 và cấu trúc tar, sau đó
  chạy `update.sh` trong tiến trình systemd riêng.
- `.github/workflows/release.yml` đóng gói và tải asset Release khi push tag `v*`.

