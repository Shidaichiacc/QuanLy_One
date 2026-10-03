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
`unittest`, dùng `tools/build-release` xác minh cấu trúc gói, tạo GitHub Release
nháp, upload đủ hai asset rồi công bố:

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


## Kiểm tra cơ chế cập nhật từ v1.3.5

- Chọn đúng `JXNative-vX.Y.Z.tar.gz` và `.sha256` theo tag; thiếu/sai asset phải
  báo lỗi trước khi đề nghị Stop All. Không dùng archive source tự sinh của GitHub.
- Worker xác minh checksum theo đúng tên file, VERSION và file bắt buộc trong gói;
  từ chối đường dẫn nguy hiểm, secret và dữ liệu runtime trước khi giải nén.
- Kiểm tra lại sáu dịch vụ game đã dừng sau khi tải. Kiểm tra này không thay thế
  Stop All an toàn từ Web; không bật game trong khi cập nhật.
- Nếu cài lỗi sau giải nén, giữ số VERSION cũ để có thể thử lại. Mã/cấu hình đã
  giải nén chưa được rollback; cần đọc log lỗi trước khi thử lại.
- Bản cài v1.3.3/v1.3.4 đã có updater nên nhận được gói v1.3.5 qua Web. Các kiểm
  tra mới của worker chỉ có hiệu lực từ lần cập nhật tiếp theo sau khi đã cài v1.3.5.
- Build từ repository nguồn; gói không chứa `data/backups-code`, `.env` hay các
  biến thể `.env.*` riêng (vẫn có `.env.example`).
- Workflow không ghi đè Release đã tồn tại. Nếu upload/công bố lỗi để lại bản nháp,
  kiểm tra asset và checksum trong bản nháp trước khi quyết định công bố thủ công.
