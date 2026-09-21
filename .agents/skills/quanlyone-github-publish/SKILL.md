---
name: quanlyone-github-publish
description: Review, commit, and push ordinary QuanLy One source changes to GitHub. Use when the user asks to update/publish code to GitHub without creating a versioned Release; do not use for release tags.
---

# QuanLyOne GitHub Publish

Tên người dùng: `quanlyone_github_publish`.

## Trước khi thay đổi GitHub

1. Đọc `AGENTS.md`, `docs/knowledge/DATA-SAFETY.md` và `docs/knowledge/TESTING.md`.
2. Xác định lại với ngữ cảnh hiện có: thay đổi nào thuộc commit, branch/remote đích,
   và người dùng chỉ muốn chuẩn bị hay đã yêu cầu push.
3. Chạy `git status --short`, xem diff chưa stage/đã stage, branch và remote. Không
   ghi đè thay đổi không liên quan của người dùng.
4. Nếu yêu cầu thực chất là đổi phiên bản/tag/Release, chuyển sang skill
   `$quanlyone-release`.

## Kiểm tra và commit

- Kiểm tra file mới để loại `.env`, secret, database, backup, log, runtime state,
  server game và MOD riêng.
- Chạy kiểm thử phù hợp với file đã đổi. Dừng nếu kiểm thử bắt buộc thất bại và báo
  lỗi cụ thể; không commit như thể đã đạt.
- Stage đường dẫn đã rà soát theo phạm vi; không dùng `git add .` một cách mù quáng.
- Dùng commit message ngắn, phản ánh đúng thay đổi. Không tự đổi `VERSION` hay tạo tag.

## Push và bàn giao

- Chỉ push khi người dùng yêu cầu đưa lên GitHub. Không force-push.
- Nếu thiếu đăng nhập/quyền GitHub, dừng ở commit an toàn và đưa lệnh đăng nhập hoặc
  push; không yêu cầu người dùng gửi token/mật khẩu vào chat.
- Sau khi hoàn tất, báo commit hash, branch, remote, kiểm thử, kết quả push và mọi
  thay đổi còn chưa commit.
- Đưa lệnh ngắn để máy khác lấy thay đổi, thường là `git pull --ff-only` trên đúng branch.

