# Quy trình phát hành

## Phân biệt hai thao tác

- **GitHub publish thông thường**: commit/push mã nguồn, không đổi `VERSION`, không tag.
- **Release phiên bản**: đổi phiên bản, cập nhật tài liệu/changelog, kiểm thử đầy đủ,
  commit, push và tạo tag để GitHub Actions phát hành gói.

Không biến một yêu cầu “commit” thành Release nếu người dùng chưa yêu cầu.

## Chuẩn bị phiên bản

1. Xác nhận số phiên bản đích dạng `X.Y.Z` và phạm vi thay đổi.
2. Kiểm tra branch, remote, trạng thái Git và tag hiện có.
3. Cập nhật `VERSION` chỉ chứa `X.Y.Z`.
4. Thêm mục đầu `CHANGELOG.md` cho `vX.Y.Z`.
5. Cập nhật phiên bản ổn định, URL tải và ví dụ phát hành trong `README.md` nếu còn dùng số cụ thể.
6. Cập nhật tài liệu kiến thức nếu kiến trúc/quy trình thay đổi.
7. Chạy kiểm thử trong `TESTING.md`, bao gồm đóng gói tạm và SHA256.
8. Kiểm tra diff và chắc chắn không có secret/dữ liệu runtime.

## Công bố

Chỉ commit/push/tag khi người dùng đã yêu cầu công bố Release:

```bash
git add <các-file-đã-kiểm-tra>
git commit -m "Release vX.Y.Z"
git push origin main
git tag -a vX.Y.Z -m "Release vX.Y.Z"
git push origin vX.Y.Z
```

`.github/workflows/release.yml` yêu cầu tag `vX.Y.Z` khớp nội dung `VERSION`, chạy
`tools/build-release`, tạo GitHub Release và upload:

- `JXNative-vX.Y.Z.tar.gz`
- `JXNative-vX.Y.Z.tar.gz.sha256`

## Xác minh sau phát hành

- Workflow GitHub Actions thành công.
- Release trỏ đúng commit/tag và được đánh dấu phiên bản mới nhất khi phù hợp.
- Hai asset tải được; SHA256 kiểm tra thành công.
- Máy phiên bản cũ nhận diện đúng bản mới.
- Ghi rõ máy cũ có thể cập nhật trực tiếp trên Web hay cần cập nhật thủ công một lần.

Không force hoặc di chuyển tag đã công bố. Nếu Release sai, dừng lại, báo trạng thái
và chọn cách sửa có lịch sử rõ ràng; không tự xóa dấu vết phát hành.

