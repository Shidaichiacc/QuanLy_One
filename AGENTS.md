# Hướng dẫn phát triển QuanLy One

Tệp này là điểm vào bắt buộc cho AI và người phát triển làm việc trong repository.

## Cách bắt đầu một yêu cầu

1. Nhắc lại ngắn gọn mục tiêu, phạm vi và tiêu chí hoàn thành dựa trên yêu cầu mới nhất.
2. Đọc mã nguồn và tài liệu liên quan trước khi đề xuất hoặc sửa.
3. Nếu người dùng nói đang **thảo luận**, **phân tích** hoặc **đề xuất trước**, chỉ kiểm tra và tư vấn; không sửa file hay triển khai.
4. Chỉ hỏi lại khi thiếu thông tin có thể làm thay đổi đáng kể kết quả. Nếu có thể suy luận an toàn, nêu giả định và tiếp tục.
5. Sửa tối thiểu trong đúng phạm vi, kiểm thử tương xứng với rủi ro rồi mới bàn giao.

## Tài liệu phải đọc theo công việc

- Bản đồ tài liệu: `docs/knowledge/INDEX.md`
- Kiến trúc và luồng chạy: `docs/knowledge/ARCHITECTURE.md`
- Quy ước phát triển và giao diện: `docs/knowledge/DEVELOPMENT.md`
- Dữ liệu, mật khẩu và thao tác nguy hiểm: `docs/knowledge/DATA-SAFETY.md`
- Ma trận kiểm thử: `docs/knowledge/TESTING.md`
- Chuẩn bị và phát hành phiên bản: `docs/knowledge/RELEASE.md`

Không cần đọc mọi tài liệu cho một thay đổi nhỏ; chọn đúng tài liệu liên quan.

## Nguyên tắc của repository

- Repository Git là mã nguồn. Bản cài vận hành chuẩn nằm tại `/opt/QuanLy_One`.
- Luôn sửa mã nguồn trước. Chỉ đồng bộ sang bản đang chạy khi người dùng yêu cầu triển khai hoặc kiểm thử trực tiếp.
- Không commit `.env`, mật khẩu, secret, dữ liệu database đang chạy, backup, log, phiên bản server do người dùng tải lên hoặc trạng thái runtime.
- Không ghi đè thay đổi không liên quan. Không xóa dữ liệu, reset Git, force-push, di chuyển tag hay thay Release đã công bố nếu chưa có yêu cầu rõ ràng.
- Trước cập nhật hệ thống, đổi mật khẩu database hoặc thay đổi cần restart game, phải kiểm tra trạng thái và dùng luồng Stop All an toàn.
- Giữ tương thích Ubuntu x86_64, Python/Flask, Nginx, systemd, Docker MySQL 5.7 và MSSQL 2019 hiện tại trừ khi yêu cầu thay đổi kiến trúc.

## Phong cách sản phẩm hiện tại

- Nội dung giao diện và hướng dẫn dùng tiếng Việt có dấu, ngắn, rõ và thống nhất thuật ngữ.
- Giữ giao diện tối màu vàng/nâu hiện có, khoảng cách gọn, responsive và không thêm framework chỉ để sửa một phần nhỏ.
- Tác vụ lâu phải có trạng thái, phần trăm, thông báo lỗi rõ và không khóa request Web.
- Log lớn chỉ tải theo yêu cầu; không đưa toàn bộ log vào lần mở trang đầu tiên.
- Ưu tiên dùng hộp thoại, biến CSS và thành phần sẵn có thay vì tạo một kiểu giao diện khác biệt.

## Hoàn thành và bàn giao

- Báo kết quả trước, sau đó nêu file chính đã đổi và kiểm thử đã chạy.
- Nếu đã triển khai, báo dịch vụ nào được restart và dịch vụ game có bị tác động hay không.
- Luôn đưa lệnh hoặc các bước sử dụng tiếp theo khi thay đổi tạo ra chức năng, quy trình Git hoặc Release mới.
- Không nói đã hoàn tất nếu mới chỉ sửa mã mà chưa chạy các kiểm tra phù hợp.

## Skill của repository

- `$quanlyone-github-publish`: rà soát, commit và push thay đổi thông thường lên GitHub.
- `$quanlyone-release`: chuẩn bị, kiểm thử và phát hành một phiên bản mới.

