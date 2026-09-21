# Kiểm thử thay đổi

Chọn kiểm thử theo file và rủi ro. Không cần chạy tác vụ phá hủy dữ liệu để chứng
minh một thay đổi giao diện.

## Kiểm tra cơ bản cho mọi thay đổi

```bash
git diff --check
git status --short
```

Đọc lại diff, đặc biệt là đường dẫn, lệnh shell, URL, quyền file và dữ liệu nhạy cảm.

## Python

Khi sửa Web, công cụ Python hoặc wrapper:

```bash
python3 -m py_compile \
  app/shared/*.py \
  app/web/admin/*.py \
  app/web/public/*.py \
  tools/*.py \
  tools/admin-login-lock tools/apply-update tools/backup-scheduler tools/run-backup-job \
  JX_Servers/Runtime/jxgame-wrapper \
  JX_Servers/Scripts/reload-game-stack
```

Với route/UI, thêm smoke test Flask hoặc render template cho nhánh thành công, lỗi
và quyền truy cập. Không gọi thao tác thật nếu có thể mock ranh giới systemd/Docker.

## Shell

Chạy `bash -n` trên đúng script shell đã sửa. Với nhóm script hiện tại:

```bash
bash -n install.sh update.sh tools/build-release \
  JX_Servers/Runtime/jx-ensure-running \
  JX_Servers/Runtime/jx-wait-ip \
  JX_Servers/Runtime/jx-wait-port \
  JX_Servers/Runtime/s3relay-pty-wrapper \
  JX_Servers/Scripts/activate-server \
  JX_Servers/Scripts/start-game-stack \
  JX_Servers/Scripts/update-server-ip
```

## Cấu hình dịch vụ

- Nginx: `sudo nginx -t` trước reload.
- Docker Compose: `docker compose --env-file .env -f deploy/docker-compose.yml config`
  chỉ trên máy có `.env` hợp lệ; không in kết quả chứa secret.
- systemd: kiểm tra diff unit, chạy `systemctl daemon-reload` khi triển khai và xem
  journal service sau restart.

## Kiểm tra gói Release

```bash
release_tmp=$(mktemp -d /tmp/quanlyone-release-check.XXXXXX)
release_version=$(tr -d '\r\n' < VERSION)
bash tools/build-release "$release_tmp/JXNative-v${release_version}.tar.gz"
(cd "$release_tmp" && sha256sum -c "JXNative-v${release_version}.tar.gz.sha256")
tar -tzf "$release_tmp/JXNative-v${release_version}.tar.gz" | less
```

Xác nhận gói có `QuanLy_One/VERSION`, `install.sh`, `update.sh`, mã Web và tool cần
thiết; không có `.env`, `.git`, venv, runtime database, backup hoặc server người dùng.

Sau kiểm tra có thể dọn thư mục tạm đã xác định:

```bash
find "$release_tmp" -type f -delete
rmdir "$release_tmp"
```

## Sau triển khai máy test

```bash
systemctl is-active jx-webpanel quanly-public nginx
journalctl -u jx-webpanel -n 50 --no-pager
journalctl -u quanly-public -n 50 --no-pager
```

Kiểm tra HTTP và chức năng đã sửa. Nếu không chủ ý tác động game, xác nhận sáu
service game vẫn giữ trạng thái trước triển khai.

