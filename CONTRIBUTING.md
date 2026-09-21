# Phát triển QuanLy One

Repository này chứa cả mã nguồn Web quản trị, Website công khai, công cụ vận hành,
cấu hình Docker, Nginx và systemd. Trước khi sửa, hãy đọc `AGENTS.md` và
`docs/knowledge/INDEX.md`.

## Luồng làm việc

1. Xác định lại mục tiêu, phần được phép thay đổi và tiêu chí hoàn thành.
2. Kiểm tra trạng thái Git và đọc mã liên quan.
3. Sửa trong repository; không sửa trực tiếp dữ liệu runtime.
4. Chạy kiểm thử theo `docs/knowledge/TESTING.md`.
5. Kiểm tra diff, sau đó mới commit, triển khai hoặc phát hành.
6. Bàn giao kèm hướng dẫn sử dụng và lệnh cần chạy.

## Dùng với Codex

Mở Codex từ thư mục gốc repository. `AGENTS.md` và các skill trong
`.agents/skills` sẽ được phát hiện từ repository.

Đưa thay đổi thông thường lên GitHub:

```text
$quanlyone-github-publish kiểm tra, commit và push các thay đổi hiện tại
```

Chuẩn bị hoặc phát hành phiên bản:

```text
$quanlyone-release chuẩn bị và phát hành phiên bản vX.Y.Z
```

Nếu vừa clone mà skill chưa xuất hiện, hãy mở lại phiên Codex tại thư mục gốc.

## Ranh giới quan trọng

- Commit/push thông thường không tự động đổi `VERSION` hoặc tạo tag.
- Release là quy trình riêng và phải dùng phiên bản được xác định rõ.
- Không đưa `.env`, database runtime, backup, log và server game của người dùng
  lên GitHub. Xem đầy đủ tại `docs/knowledge/DATA-SAFETY.md`.

