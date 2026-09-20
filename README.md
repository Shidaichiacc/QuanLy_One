# JXNative / QuanLy_One

Web quản trị JX trên Ubuntu: quản lý nhiều phiên bản server, Start/Stop/Reload,
Console realtime, MySQL, MSSQL, backup/restore, MOD và Website công khai.

Phiên bản ổn định hiện tại: **v1.3.1**
Mã nguồn và bản phát hành: <https://github.com/Shidaichiacc/QuanLy_One>

> Gói JXNative không chứa server game. Sau khi cài Web và database, hãy đưa
> server riêng vào bằng trang **Server & Dữ liệu**.

## 1. Cài đặt lần đầu

### Chuẩn bị Ubuntu

- Ubuntu Server 24.04 LTS x86_64 được khuyến nghị; Ubuntu 22.04 vẫn được hỗ trợ.
- RAM tối thiểu 4 GB, khuyến nghị 8 GB trở lên khi chạy MSSQL và game.
- Ổ trống tối thiểu 20 GB, tài khoản có quyền `sudo` và kết nối Internet.
- Không cần cài Docker trước; `install.sh` sẽ tự cài Docker và Docker Compose.

Tải ISO từ trang chính thức:

- [Ubuntu Server 24.04 LTS](https://ubuntu.com/download/server)
- [ISO Ubuntu Server 24.04.5 amd64](https://releases.ubuntu.com/24.04/ubuntu-24.04.5-live-server-amd64.iso)

Cài Ubuntu theo mặc định, bật **OpenSSH server** để có thể đăng nhập SSH. Sau
khi vào máy chủ, cập nhật hệ thống:

```bash
sudo apt update
sudo apt upgrade -y
```

### Cách khuyến nghị: cài bộ quản lý bằng Git

Các lệnh dưới đây chỉ cài **QuanLy_One**. Server game sẽ được upload hoặc clone
riêng trên Web sau khi hoàn tất thiết lập database.

```bash
sudo apt update
sudo apt install -y git
cd /opt
sudo git clone --depth 1 https://github.com/Shidaichiacc/QuanLy_One.git
cd QuanLy_One
sudo bash install.sh
```

### Cách dự phòng: tải GitHub Release

```bash
cd /opt
sudo wget https://github.com/Shidaichiacc/QuanLy_One/releases/download/v1.3.1/JXNative-v1.3.1.tar.gz
sudo wget https://github.com/Shidaichiacc/QuanLy_One/releases/download/v1.3.1/JXNative-v1.3.1.tar.gz.sha256
sudo sha256sum -c JXNative-v1.3.1.tar.gz.sha256
sudo tar -xzf JXNative-v1.3.1.tar.gz -C /opt
cd /opt/QuanLy_One
sudo bash install.sh
```

Bộ cài tự cài Docker, Docker Compose, Nginx, Python và thư viện 32-bit cần cho
JX. Cuối quá trình, bộ cài tự nhận IPv4 LAN của máy và in đúng hai địa chỉ:

```text
Trang chủ: http://IP-MAY-CHU/
Quản lý:   http://IP-MAY-CHU/admin/
```

Đăng nhập lần đầu: `admin / admin123`.

### Hoàn tất thiết lập trên Web

Lần đăng nhập đầu tiên bắt buộc:

1. Đổi mật khẩu Admin.
2. Đặt mật khẩu riêng cho MySQL và MSSQL hoặc dùng nút tạo tự động.
3. Chờ thanh tiến trình tải image, khởi tạo database và kiểm tra kết nối đạt
   100%. Lần đầu có thể mất vài phút, đặc biệt khi tải MSSQL. Khung nhật ký
   ngay bên dưới cho biết từng bước đang làm và lỗi gần nhất nếu chưa hoàn tất.

Không đóng trang trong khi trạng thái là **Đang xử lý**. Server game chưa tự
chạy sau bước này.

## 2. Thêm server game và chạy lần đầu

Vào **Hệ thống → Server & Dữ liệu → Server game → Thêm phiên bản**:

1. Upload file `.zip`, `.tgz`, `.tar.gz` hoặc nhập repository GitHub công khai.
2. Chờ đủ hai giai đoạn upload và giải nén; Web sẽ báo lỗi cụ thể nếu gói sai.
3. Chọn đúng thư mục chứa đồng thời `gateway/` và `server1/` nếu gói có nhiều
   lớp thư mục.
4. Bấm **Kích hoạt**. Web tự cập nhật IP máy hiện tại và mật khẩu database vào
   các file cấu hình JX cần thiết.
5. Về **Bảng điều khiển**, bấm **Start All** và chờ đủ 6/6 thành phần.

Thứ tự khởi động:

```text
PaySys 5002 → RelayPay 7777 → Goddess 5001 → Bishop 5622
→ S3Relay 5003 → GameServer 6666
```

Một server đầy đủ thường phải có:

```text
gateway/goddess_y
gateway/bishop_y
gateway/s3relay/s3relay_y
server1/jx_linux_y
```

## 3. Các chức năng chính

- **Bảng điều khiển:** trạng thái 6 tiến trình, CPU/RAM từng tiến trình, người
  chơi online, database và thao tác Start All/Stop All/Reload.
- **Console & Nhật ký:** xem realtime riêng PaySys, RelayPay, Goddess, Bishop,
  S3Relay, GameServer, MSSQL hoặc MySQL. Chọn 300/1.000/3.000 dòng.
- **Server & Dữ liệu:** quản lý phiên bản, IP, log đầy đủ, dung lượng, backup,
  restore và mật khẩu database.
- **Tài khoản:** tạo và quản lý tài khoản/người chơi.
- **Thiết lập game:** Kỳ Trân Các, vật phẩm, kinh nghiệm, nhiệm vụ và sự kiện.
- **Quản trị Website:** nội dung, ảnh, cấu hình và lựa chọn giao diện công khai.

Console chỉ tải nguồn đang chọn nên không làm nặng toàn bộ trang. Log đầy đủ
chỉ được đọc khi bấm **Tải log** trong **Server & Dữ liệu**.

## 4. MOD game

Kho MOD dùng chung nằm tại:

```text
/opt/QuanLy_One/JX_Servers/MOD/
```

Bản phát hành có sẵn `vdk.so` trực tiếp trong thư mục này. Web không tạo thư
mục Defaults. Trong **Bảng điều khiển → Cấu hình MOD**, có thể tạo danh sách
tối đa 32 file `.so` và thay đổi thứ tự nạp bằng nút lên/xuống. Mỗi mục có thể
lấy từ **Trong phiên bản active** (`server1/`) hoặc **Kho MOD dùng chung**, nên
một danh sách có thể kết hợp file từ cả hai nguồn.

Ô thêm MOD cho phép chọn file đã quét hoặc nhập đúng tên file rồi bấm **Thêm**.
QuanLy One chỉ nhận file ELF 32-bit thực sự tồn tại trong nguồn đã chọn và
không cho thêm trùng. Thứ tự hiển thị cũng là thứ tự trong `LD_PRELOAD`.
Nếu GameServer đang chạy, lưu thay đổi sẽ yêu cầu xác nhận rồi Reload an toàn
S3Relay + GameServer; nếu đang tắt, cấu hình áp dụng ở lần Start All kế tiếp.
Cấu hình một MOD của bản cũ được tự chuyển sang danh sách mới khi lưu.

## 5. Database, backup và mật khẩu

MySQL và MSSQL mặc định chỉ bind loopback của máy Linux:

```text
127.0.0.1:3306  MySQL
127.0.0.1:1433  MSSQL
```

Vào **Server & Dữ liệu → Sao lưu & Khôi phục** để backup/restore, xem hoặc đổi
mật khẩu. Khi đổi mật khẩu, Web yêu cầu xác nhận, Stop All, backup, đổi mật
khẩu thật trong database, cập nhật `.env` và đồng bộ mã hóa vào cấu hình JX.
Game vẫn tắt sau khi hoàn tất để quản trị viên tự kiểm tra rồi Start All.

Không đưa `.env`, database, backup hoặc log lên GitHub.

## 6. Website công khai

Nginx là cổng vào của cả Web quản trị và Website công khai, vì vậy không nên
gỡ Nginx. Trong **Cấu hình Website** có thể xem thử và áp dụng từng theme:

- **Thạch Chí cổ điển:** giao diện mặc định khi cài mới, dùng khung và tài
  nguyên Võ Lâm cũ.
- **JXNative mới:** hiện đại, responsive; có thể chọn lại trong cấu hình.

Hai theme có HTML/CSS riêng; chỉ dùng chung dữ liệu cần thiết như bài viết,
ảnh, liên kết tải game và tài khoản.

## 7. Kiểm tra và nâng cấp phiên bản

Sau khi đăng nhập, JXNative kiểm tra GitHub Release một lần trong phiên. Kết
quả nằm ngay dưới số phiên bản ở cuối sidebar. Bấm vào trạng thái này để mở
popup xem hoặc tải bản phát hành. Trình kiểm tra không tự chạy mã và không tự
dừng server.

Quy trình nâng cấp an toàn:

```bash
cd /opt
sudo wget https://github.com/Shidaichiacc/QuanLy_One/releases/download/vX.Y.Z/JXNative-vX.Y.Z.tar.gz
sudo wget https://github.com/Shidaichiacc/QuanLy_One/releases/download/vX.Y.Z/JXNative-vX.Y.Z.tar.gz.sha256
sudo sha256sum -c JXNative-vX.Y.Z.tar.gz.sha256
sudo tar -xzf JXNative-vX.Y.Z.tar.gz -C /opt
cd /opt/QuanLy_One
sudo bash update.sh
```

Trước khi nâng cấp, hãy backup database và Stop All. `update.sh` giữ lại `.env`,
database, backup, server game, MOD và trạng thái cần thiết của máy hiện tại.

## 8. Kiểm tra lỗi nhanh

```bash
sudo systemctl status jx-webpanel quanly-public nginx --no-pager
sudo docker compose --env-file /opt/QuanLy_One/.env \
  -f /opt/QuanLy_One/deploy/docker-compose.yml ps
sudo journalctl -u jx-webpanel -n 100 --no-pager
sudo journalctl -u jxbishop -n 100 --no-pager
```

Nếu quên mật khẩu hoặc bị khóa đăng nhập Admin:

```bash
sudo /opt/QuanLy_One/tools/admin-login-lock list
sudo /opt/QuanLy_One/tools/admin-login-lock unlock-all
```

## 9. Tạo GitHub Release

Workflow `.github/workflows/release.yml` tự kiểm tra `VERSION`, đóng gói file
`.tar.gz`, tạo SHA256 và tải cả hai lên GitHub Release khi có tag `v*`.

```bash
cd /duong-dan/QuanLy_One
git init
git add .
git commit -m "Release v1.3.1"
git branch -M main
git remote add origin https://github.com/Shidaichiacc/QuanLy_One.git
git push -u origin main
git tag v1.3.1
git push origin v1.3.1
```

Tag phải đúng bằng chữ `v` cộng nội dung file `VERSION`. Không commit server
game, `.env`, database đang chạy, bản backup, log hoặc môi trường Python.

Để tự đóng gói trên máy:

```bash
cd /opt/QuanLy_One
sudo bash tools/build-release
```

Kết quả gồm `/opt/JXNative-vX.Y.Z.tar.gz` và file `.sha256` tương ứng.
