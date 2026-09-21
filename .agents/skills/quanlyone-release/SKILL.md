---
name: quanlyone-release
description: Prepare, validate, tag, and publish a versioned QuanLy One GitHub Release. Use when the user asks to bump VERSION, create a release/tag, or verify release assets; do not use for an ordinary commit or push.
---

# QuanLyOne Release

Tên người dùng: `quanlyone_release`.

## Xác định Release

1. Đọc `AGENTS.md`, `docs/knowledge/RELEASE.md`, `docs/knowledge/TESTING.md` và
   `docs/knowledge/DATA-SAFETY.md`.
2. Xác định lại phiên bản đích, nội dung thuộc Release và người dùng muốn **chuẩn bị**
   hay **công bố**. Nếu chưa có số phiên bản, kiểm tra phiên bản/tag hiện tại và đề
   xuất bước SemVer phù hợp; không âm thầm chọn phiên bản khi phạm vi còn mơ hồ.
3. Kiểm tra branch, remote, working tree, tag local/remote và GitHub Release hiện có.
   Không tái sử dụng hoặc di chuyển một tag đã công bố.

## Chuẩn bị và xác minh

- Cập nhật nhất quán `VERSION`, mục đầu `CHANGELOG.md`, phiên bản/URL cụ thể trong
  `README.md` và tài liệu kiến thức bị ảnh hưởng.
- Chạy toàn bộ kiểm tra liên quan trong `docs/knowledge/TESTING.md`.
- Dùng `tools/build-release` để tạo gói trong thư mục tạm, kiểm tra SHA256 và nội
  dung gói. Không đưa gói sinh cục bộ vào commit.
- Rà soát diff và dữ liệu nhạy cảm trước khi commit.

## Công bố và kiểm tra sau phát hành

- Nếu người dùng chỉ yêu cầu chuẩn bị, dừng trước commit/push/tag và đưa diff cùng
  lệnh tiếp theo.
- Nếu người dùng yêu cầu công bố, commit Release, push branch, tạo annotated tag
  `vX.Y.Z` trên đúng commit rồi push tag. Không force-push.
- Theo dõi `.github/workflows/release.yml`; xác minh GitHub Release có đúng tag và
  đủ `.tar.gz` cùng `.sha256`, sau đó tải/kiểm tra checksum khi có thể.
- Nếu workflow hoặc asset lỗi, báo đúng điểm lỗi và giữ lịch sử nguyên vẹn; không tự
  xóa Release/tag hoặc che lỗi bằng cách di chuyển tag.
- Bàn giao phiên bản, commit, tag, URL Release, kết quả kiểm thử và hướng dẫn nâng
  máy cũ (Web một nút hay lệnh thủ công tùy phiên bản nguồn).

