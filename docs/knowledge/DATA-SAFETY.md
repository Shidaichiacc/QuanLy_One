# An toàn dữ liệu và hệ thống

## Không đưa lên Git

- `.env`, secret Flask, mật khẩu MySQL/MSSQL và thông tin đăng nhập Admin.
- `data/state`, `data/uploads`, dữ liệu Docker, backup và log runtime.
- `JX_Servers/Active`, các server trong `JX_Servers/JX_Versions` và MOD riêng của người dùng.
- Venv, cache Python và gói Release sinh cục bộ.

Ngoại lệ được theo dõi có chủ ý gồm file seed database, `.gitkeep` và MOD chính thức
được khai báo trong `.gitignore`. Trước commit, luôn kiểm tra `git status` và nội
dung file mới, không chỉ tin vào phần mở rộng.

## Database và mật khẩu

- MySQL dùng dữ liệu đăng nhập `server1`; MSSQL dùng dữ liệu nhân vật `account_tong`.
- Mật khẩu nằm trong `.env` và được đồng bộ vào những cấu hình JX cần thiết bằng
  công cụ của dự án. Không in mật khẩu vào log, diff hoặc câu trả lời.
- Trước đổi mật khẩu/restore/cập nhật lớn: Stop All, tạo hoặc xác nhận backup, kiểm
  tra container/database sẵn sàng và có đường quay lui.
- Không xóa volume/database chỉ vì kết nối thất bại. Chẩn đoán credential, container,
  database tồn tại và log trước.

## Dữ liệu server và MOD

- `JX_Servers/Active` là symlink tới phiên bản đang dùng; không thay bằng bản sao thư mục.
- Kích hoạt phiên bản phải xác nhận có `gateway` và `server1` hợp lệ.
- MOD chung nằm trong `JX_Servers/MOD`; cấu hình MOD theo từng server nằm trong
  `data/state/mods`. Không ghi đè MOD người dùng khi cập nhật mà không lưu bản bảo toàn.
- Thay đổi danh sách `LD_PRELOAD` cần kiểm tra ELF 32-bit phù hợp và restart game có chủ đích.

## Thao tác nguy hiểm

- Không dùng `git reset --hard`, force-push, xóa tag/Release hoặc xóa rộng dưới `/opt`.
- Trước thao tác xóa, xác định đường dẫn tuyệt đối cụ thể và kiểm tra nó thuộc đúng phạm vi.
- Dùng backup/di chuyển có thể phục hồi khi phù hợp. Báo rõ thứ đã xóa và khả năng khôi phục.
- Không tự chạy `install.sh`, `update.sh`, đổi mật khẩu, Stop All hoặc restart game khi người dùng chỉ yêu cầu phân tích.

