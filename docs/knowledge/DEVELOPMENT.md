# Quy ước phát triển

## Xác định yêu cầu trước khi sửa

Trước một thay đổi, ghi nhận ngắn gọn:

- Người dùng muốn hành vi nào thay đổi.
- Màn hình, route, service hoặc dữ liệu nào nằm trong phạm vi.
- Điều gì phải được giữ nguyên.
- Cách quan sát để biết thay đổi đã hoàn thành.

Nếu người dùng yêu cầu thảo luận trước, dừng ở phân tích và đề xuất. Khi yêu cầu đã
rõ, không hỏi lại những điều có thể xác nhận từ mã nguồn hoặc máy test.

## Quy ước Web và UI

- Dùng tiếng Việt có dấu và giữ thống nhất các tên: **Server & Dữ liệu**, **Console
  & Nhật ký**, **Cấu hình Website**, **Stop All**, **Start All**.
- Giữ bảng màu/biến CSS hiện có. Ưu tiên class dùng chung và `window.JXDialog` thay
  cho `alert`, `confirm` hoặc popup có phong cách khác.
- Giao diện phải dùng được ở desktop và màn hình hẹp; kiểm tra overflow, popup,
  bảng và thanh công cụ.
- Tác vụ lâu không chạy đồng bộ trong request. Ghi trạng thái ngắn vào `data/state`,
  chạy worker/tiến trình riêng và để giao diện poll tiến độ.
- Chỉ tải log khi người dùng chọn nguồn và bấm tải/xem. Giới hạn số dòng, tránh đọc
  toàn bộ journal hoặc file log khi mở trang.
- Route thay đổi trạng thái phải yêu cầu đăng nhập, CSRF và xác nhận lại mật khẩu
  cho thao tác hệ thống nhạy cảm.

## Website công khai

Website công khai là Flask riêng tại `app/web/public`. Hai theme JXNative và Thạch
Chí có thể dùng chung nội dung, tài khoản, bài viết và cấu hình; CSS/layout/theme
asset cần tách để một theme không làm biến dạng theme còn lại.

Không chạy PHP từ asset legacy. Nginx chặn `.php` trong `/legacy-assets` và `/library`.

## Mã nguồn và máy đang chạy

Thực hiện thay đổi trong repository trước. Nếu người dùng yêu cầu triển khai lên máy
test, chỉ sao chép đúng file đã thay đổi vào `/opt/QuanLy_One`, giữ permission phù
hợp và restart service nhỏ nhất cần thiết.

- Sửa Admin: thường restart `jx-webpanel`.
- Sửa Public: thường restart `quanly-public`.
- Sửa Nginx: chạy `nginx -t` trước khi reload.
- Sửa systemd: `systemctl daemon-reload`, sau đó restart đúng service liên quan.
- Không restart game chỉ vì sửa giao diện Web.

Sau triển khai, kiểm tra HTTP, trạng thái service và journal; không kết luận dựa
trên việc lệnh copy thành công.

## Cập nhật tài liệu

- Thay hành vi người dùng: cập nhật `README.md` nếu cần.
- Thay kiến trúc/quy tắc phát triển: cập nhật `docs/knowledge`.
- Thay đổi sẽ phát hành: thêm vào đầu `CHANGELOG.md` của phiên bản chuẩn bị phát hành.
- Thêm dependency/bản quyền bên thứ ba: cập nhật requirements và `THIRD_PARTY_NOTICES.md` khi áp dụng.

