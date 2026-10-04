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

## Khôi phục khi tag đã push nhưng workflow chưa tạo Release

Nếu lỗi thuộc workflow/quyền runner, sửa workflow trên `main` và push commit sửa.
Không xóa hoặc di chuyển tag. Workflow hỗ trợ `workflow_dispatch`: lấy workflow
mới từ `main`, nhưng checkout và đóng gói đúng mã nguồn của tag được chọn.

```bash
gh workflow run release.yml --ref main -f release_tag=v1.3.5
```

Có thể chọn **Actions → Tao goi phat hanh → Run workflow**, branch `main`, nhập
tag cần phát hành. Chỉ bấm Re-run ở lượt lỗi cũ sẽ dùng lại workflow cũ.
Luồng vẫn kiểm tra tag/VERSION, chạy tests và từ chối ghi đè Release đã tồn tại.
Nếu lỗi nằm trong mã nguồn của tag, cần sửa và phát hành tag phiên bản mới.

Kiểm thử dọn log đọc `/proc/*/fd` để kiểm tra file đang mở. Trên Ubuntu runner,
workflow phải chạy tests bằng `sudo` với đúng Python đã cài dependencies, tương
tự quyền của Web service. Không bỏ qua lỗi quyền trong mã dọn log.

Từ v1.3.6, trang cập nhật luôn kiểm tra GitHub mới; cache phiên/server tối đa 5
phút và không giữ kết quả vô hạn trong sessionStorage. Nếu máy cũ bị lỗi nút
cập nhật do JavaScript (v1.3.3–v1.3.5), cần sửa giao diện tại máy đó trước hoặc
dùng hướng dẫn cập nhật thủ công sau Stop All. Gói v1.3.6 chứa bản sửa lâu dài.

## Giữ cấu hình PaySys khi nâng cấp từ v1.3.7

`JX_Servers/Config/mssql.ini` trong Git/gói là cấu hình mẫu cho cài mới. Mật khẩu
trong bản đang chạy phải khớp `MSSQL_SA_PASSWORD` của `.env`. Updater giữ file
trong `JX_Servers/Config` đã tồn tại và chỉ cài thêm file mới. `update.sh` đồng bộ
lại mật khẩu PaySys từ `.env` trước khi báo thành công, vì updater của bản cũ
có thể đã ghi đè cấu hình bằng mẫu trong gói. Việc này không đổi mật khẩu SQL.

Sau cập nhật, kiểm tra đăng nhập MSSQL, cấu hình PaySys và Start All đủ sáu
thành phần; chỉ thấy container healthy chưa đủ xác nhận game kết nối được.
