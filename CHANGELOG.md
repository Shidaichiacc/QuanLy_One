# Lịch sử phiên bản

## v1.3.1

- Sửa bản cài bằng `git clone` thiếu `data/database/seed/account_tong.bak` do quy tắc bỏ qua `*.bak`, khiến thiết lập MSSQL đứng ở 76% và báo `Login failed ... account_tong` (State 38).
- Đưa backup mẫu MSSQL vào Git và kiểm tra file ngay đầu quy trình; nếu gói cài không đầy đủ, Web báo lỗi rõ ràng thay vì chờ database không tồn tại.
- Tinh gọn màn thiết lập database lần đầu: bỏ nút chép đồng thời hai mật khẩu, đặt nút hiện/ẩn mật khẩu riêng ở góc phải và thêm nhật ký ngắn theo từng mốc giờ, phần trăm, kết quả hoặc lỗi.
- Đặt Thạch Chí cổ điển làm giao diện mặc định cho máy cài mới; không tự đổi theme mà máy đang sử dụng khi nâng cấp.
- Bỏ mục Cập nhật phiên bản khỏi menu Hệ thống; tự kiểm tra một lần mỗi phiên và hiển thị trạng thái dưới số phiên bản, kèm popup cập nhật tối giản khi bấm vào.

## v1.3.0

- Phát hành ổn định giao diện quản trị polish, Console realtime theo từng tiến trình, nhật ký thao tác, tài nguyên CPU/RAM riêng và quản lý log theo yêu cầu.
- Hoàn thiện trình thiết lập lần đầu cho Admin, MySQL và MSSQL; tự mã hóa và đồng bộ mật khẩu vào cấu hình JX, có tiến trình và rollback khi lỗi.
- Quản lý nhiều phiên bản server, tự nhận IP máy, upload/GitHub có tiến độ, lựa chọn MOD theo đúng nguồn và kèm sẵn `JX_Servers/MOD/vdk.so`.
- Tách giao diện Website JXNative mới và Thạch Chí cổ điển; hai theme chỉ dùng chung nội dung, ảnh, liên kết và dữ liệu tài khoản cần thiết.
- Thêm kiểm tra GitHub Release trong Web, tài liệu cài đặt mới, `.gitignore`, SHA256 và workflow tự tạo Release khi đẩy tag phiên bản.

## v1.3.0-test.16

- Đặt trực tiếp `vdk.so` trong `JX_Servers/MOD` của gói phát hành; sau khi tải và giải nén đã có sẵn MOD dùng chung, không còn thư mục trung gian `JX_Servers/Defaults/MOD` hoặc bước tạo MOD mặc định.
- Bỏ nhãn `(mặc định)` cạnh `vdk.so` trong giao diện chọn MOD; file được hiển thị như mọi MOD dùng chung khác.
- Bộ đóng gói giữ file MOD chính thức trong `JX_Servers/MOD` nhưng vẫn loại các bản sao `.bak` và `.user-*`.

## v1.3.0-test.15

- Phục hồi đúng cấu trúc giao diện Thạch Chí từ JXNative 1.2.1: dùng lại khung sprite `Frame_All`, menu, cột trái, vùng nội dung và biểu mẫu tài khoản nguyên bản; vẫn chạy Flask và dùng chung dữ liệu CMS hiện tại, không cần PHP.
- Loại bỏ hero và hệ card hiện đại từng làm theme Thạch Chí xuất hiện hai banner và sai tỷ lệ; giữ khung cổ điển 1.024px đúng với kích thước tài nguyên gốc.
- Đưa trạng thái Start All/Reload vào trong khung `Tổng quan vận hành`, thu nhỏ chiều cao và cỡ chữ; bỏ thông báo Start All trùng phía trên và tự ẩn thông báo hoàn tất sau 5 giây.

## v1.3.0-test.14

- Căn thanh tab con của Nhật ký hoạt động theo đúng container nội dung, không còn lệch sang vùng sidebar trên màn hình rộng.
- Đưa `vdk.so` ELF 32-bit vào bộ MOD mặc định của QuanLy_One; cài mới và cập nhật đều triển khai vào kho MOD chung, đồng thời backup bản người dùng nếu checksum khác.
- Bỏ mục `Xem Website` trùng lặp khỏi sidebar; xem thử theme được thực hiện ngay trong Cấu hình Website.
- Nới Web Thạch Chí lên tối đa 1.360px, dùng nền đầu trang liền mạch từ tài nguyên Web cổ điển và nền nội dung nâu đồng nhất; toàn bộ vẫn chạy bằng Flask, không cần PHP.

## v1.3.0-test.13

- Tinh gọn Console máy chủ: bỏ Tạm dừng và Xóa màn hình; chỉ giữ 300, 1.000 hoặc 3.000 dòng cho đúng mục tiêu theo dõi realtime, không đưa toàn bộ journal vào DOM trình duyệt.
- Tách Nhật ký hoạt động thành hai tab con `Thao tác quản trị` và `Log vận hành JXNative`; chỉ dựng và tải nội dung của tab đang mở.
- Đổi cấu hình giao diện Website sang danh sách theme có mô tả, nút Xem thử và nút Áp dụng riêng, phù hợp khi bổ sung nhiều theme sau này.
- Tách hoàn toàn hai bộ template public `Modern` và `Thạch Chí` cho trang chủ, tin tức, bài viết và tài khoản; chỉ dùng chung dữ liệu CMS, ảnh, tài khoản và nghiệp vụ database.
- Làm lại Web Thạch Chí bằng HTML/CSS độc lập, responsive, không còn bị bó khung hoặc kế thừa bố cục của giao diện JXNative hiện đại.

## v1.3.0-test.9

- Sửa hiện tượng dấu tiếng Việt bị tách như “Thiế t” trên một số trình duyệt Windows bằng font UI hiện đại; chỉ giữ font trang trí cho logo JXNative.
- Website công khai có hai giao diện thật: `JXNative mới` và `Thạch Chi cổ điển`; đổi giao diện không thay bài viết, thư viện ảnh hay tài khoản game.
- Chuyển quản lý mật khẩu MySQL/MSSQL lên đầu trang `Sao lưu & Khôi phục`; mật khẩu mặc định bị che và chỉ hiện 30 giây sau khi xác minh lại mật khẩu Admin.
- Thêm sao chép riêng an toàn cho hai mật khẩu database; phản hồi chứa mật khẩu đặt `Cache-Control: no-store` và không đưa bí mật vào URL, log hoặc HTML ban đầu.
- Đổi mật khẩu database khi game đang chạy sẽ hỏi xác nhận, Stop All an toàn, chờ đủ sáu thành phần dừng rồi mới backup và thay đổi; nếu dừng lỗi thì database hoàn toàn chưa bị chạm tới.
- Trình thiết lập database lần đầu có nút hiện/ẩn và chép cả hai mật khẩu được tạo tự động để quản trị viên lưu lại ngay.

## v1.3.0-test.8

- Sửa cài mới đặt mật khẩu MySQL thành công nhưng Start All dừng tại S3Relay: đồng bộ thêm mật khẩu mã hóa vào `s3relay/relay_config.ini` và `backupdaemon.ini` của từng phiên bản server.
- Server đã upload trước hoặc kích hoạt về sau đều được cập nhật đủ cấu hình Goddess, S3Relay, backup daemon và MSSQL trước khi chạy.

## v1.3.0-test.7

- Sửa máy mới cài xong không truy cập được Web khi UFW đang bật: bộ cài tự mở cổng Nginx `80/tcp` nhưng không thay đổi chính sách firewall khác.
- Tự nhận IPv4 LAN từ default route và in đúng liên kết Web public/Admin sau khi cài, thay cho chuỗi giữ chỗ `IP-MAY-CHU`.

## v1.3.0-test.6

- Thêm trình thiết lập lần đầu theo ba bước: đăng nhập Admin mặc định, bắt buộc đổi mật khẩu Admin, rồi tự đặt mật khẩu riêng cho MySQL và MSSQL.
- `install.sh` cài Web nền trước; trình thiết lập mới khởi tạo Docker/database sau, hiển thị phần trăm tổng, bước đang chạy, thời gian chờ, lỗi và trạng thái hoàn tất.
- Bỏ hoàn toàn mật khẩu database mặc định khỏi `.env.example`, Docker Compose, Web Admin/Public, công cụ nạp database và cấu hình MSSQL dùng chung.
- Tích hợp mã hóa mật khẩu tương thích JX từ dự án MIT `jxoffline/jxtools`; khi setup hoặc kích hoạt phiên bản sẽ tự đồng bộ đúng `goddess.cfg` và `database.ini`.
- Thêm công cụ đổi mật khẩu MySQL/MSSQL về sau: bắt buộc Stop All và xác nhận mật khẩu Admin, backup trước, cập nhật database thật + Docker + cấu hình JX, kiểm tra kết nối và rollback khi lỗi.
- Sửa menu ba chấm của phiên bản server không bị khung cuộn cắt; thêm popup đổi mật khẩu database và tiến trình trực quan.

## v1.3.0-test.5

- Sửa menu ba chấm của từng phiên bản server không còn bị vùng cuộn của bảng cắt thành một khung nhỏ.
- Menu thao tác rộng và rõ hơn, tự đóng menu khác hoặc khi bấm ra ngoài; trên màn hình nhỏ hiển thị giữa màn hình để luôn dùng được nút đổi tên, chọn đường dẫn và xóa.

## v1.3.0-test.4

- Danh sách MOD chỉ dựng file `.so` thuộc đúng nguồn đang chọn; bỏ nhóm nguồn khác và lựa chọn “Không chọn MOD” gây rối.
- Nếu nguồn có MOD, tự chọn `vdk.so` hoặc file hợp lệ đầu tiên; nếu nguồn trống, hiển thị rõ chưa có file ELF 32-bit.
- Popup thêm phiên bản hiển thị phần trăm upload thật từ trình duyệt và phần trăm giải nén theo tiến độ xử lý archive.
- Hiển thị riêng các bước nhận file, kiểm tra an toàn, giải nén, dò `gateway/` + `server1/`, hoàn tất hoặc thông báo lỗi; tự tải lại danh sách sau khi thành công.

## v1.3.0-test.3

- Thêm menu chọn nhanh server active ngay trên header khi đã có từ hai phiên bản; vẫn bắt buộc Stop All và vẫn chạy đủ bước kiểm tra binary, cập nhật IP trước khi kích hoạt.
- Gộp các khối thông tin trùng trên Bảng điều khiển thành một bảng `Tổng quan vận hành`: trạng thái tổng, điều khiển, CPU/RAM từng tiến trình, database và MOD.
- Giữ log realtime ở trang `Console & Nhật ký`; Bảng điều khiển chỉ còn nút mở console để dành không gian cho thông tin vận hành.
- Sửa lỗi JavaScript khai báo trùng làm nút `Cấu hình MOD` và cập nhật trạng thái dashboard không hoạt động.

## v1.3.0-test.2

- Tách khung log lớn khỏi Bảng điều khiển; Dashboard mới tập trung vào trạng thái sáu thành phần, người chơi, uptime, database và đường dẫn server đang chạy.
- Hiển thị CPU và RAM riêng cho từng systemd cgroup của PaySys, RelayPay, Goddess, Bishop, S3Relay và GameServer, bao gồm cả tiến trình con của service.
- Thêm trang `Console & Nhật ký` với console riêng cho sáu thành phần game và hai database; chỉ duy trì một kết nối cho tab đang xem.
- Chuyển console realtime sang Server-Sent Events: tải 300 dòng đầu của phiên hiện tại rồi chỉ nối thêm dòng mới, không đọc và dựng lại toàn bộ DOM mỗi hai giây.
- Giữ tối đa 40.000 dòng trong bộ đệm trình duyệt và 30.000 dòng hiển thị; hỗ trợ tạm dừng, tự cuộn, ẩn thời gian, xóa màn hình và toàn màn hình.
- Mỗi Start All, Stop All, Reload hoặc Bật/Tắt riêng tự mở đúng phiên console liên quan; Reload chỉ làm mới S3Relay và GameServer.
- Thêm Nhật ký hoạt động quản trị riêng; log lịch sử đầy đủ và công cụ dọn dung lượng vẫn nằm tại `Server & Dữ liệu → Log & Dung lượng`.
- Chuyển Web quản trị sang Gunicorn `gthread` và tắt proxy buffering của Nginx để luồng SSE không chặn thao tác Web khác.

## v1.3.0-test.1

- Làm mới giao diện quản trị theo phong cách JX tối hiện đại: nền đen nâu phân lớp rõ, điểm nhấn vàng tiết chế, nút phẳng, bảng gọn và terminal vẫn giữ nền đen.
- Giữ nguyên bố cục vận hành đã ổn định của v1.2.1, không thay đổi quy trình Start All, Reload, Stop All, service, MOD, backup/restore hoặc database.
- Thêm dải tổng quan gọn trên dashboard gồm phiên bản server active, số thành phần đang chạy, người chơi online, uptime Linux và trạng thái hai database.
- Đồng bộ giao diện đăng nhập và đổi mật khẩu lần đầu; vẫn hiển thị tài khoản mặc định ở lần cài mới rồi bắt buộc đổi mật khẩu riêng.
- Thiết kế lại Web public bằng dữ liệu CMS hiện có, tái sử dụng hình ảnh JX của Web cũ nhưng không đưa trở lại mã PHP, thanh toán, SimCity Bot hoặc mật khẩu hard-code.
- Khu vực tài khoản public hiển thị nhanh Xu, KNB và thời gian còn lại khi người chơi đã đăng nhập; lỗi đọc database không làm hỏng trang Web.
- Bổ sung responsive cho sidebar, dashboard, danh sách bài viết, trang tin, biểu mẫu đăng ký/đăng nhập và khu vực tài khoản.

## v1.2.1

- Làm lại cấu hình MOD bằng popup rộng, hiển thị rõ server active, trạng thái nạp MOD, nguồn trong phiên bản/kho dùng chung, MOD chính và hook phụ.
- Tự lọc danh sách MOD theo nguồn; ưu tiên `vdk.so` khi có và cảnh báo rõ khi nguồn chưa có file ELF 32-bit hợp lệ.
- Khi GameServer đang chạy, lưu thay đổi MOD bằng popup xác nhận `Lưu và Reload`; khi server tắt chỉ lưu để áp dụng ở lần chạy sau.
- Thay toàn bộ hộp `confirm`, `prompt` và `alert` mặc định của trình duyệt bằng popup Web đồng bộ giao diện; các thao tác nguy hiểm vẫn yêu cầu xác nhận hoặc nhập đúng giá trị.
- Ở lần đăng nhập đầu tiên, hiển thị rõ tài khoản/mật khẩu mặc định ngay trên trang đăng nhập và vẫn bắt buộc đổi mật khẩu trước khi vào trang quản trị.

## v1.2.0

- Tổ chức lại bản phát hành sạch thành `app`, `JX_Servers`, `data`, `deploy` và `tools`; loại bỏ ứng dụng PHP cũ, cache, log, file backup thử nghiệm và đường dẫn lịch sử khỏi gói cài mới.
- Tách nhiều phiên bản game vào `JX_Servers/JX_Versions`, symlink đang chạy thành `JX_Servers/Active`, runtime/config/script dùng chung vào đúng nhóm riêng.
- Tách Web quản trị, Web public, tài nguyên Thạch Chi và nội dung mẫu nhưng giữ nguyên giao diện, ảnh, đăng ký tài khoản và công cụ quản trị hiện có.
- Bổ sung kho `JX_Servers/MOD`: mỗi phiên bản lưu cấu hình MOD riêng, có thể chọn MOD nằm trong server active hoặc kho dùng chung; chỉ nhận ELF 32-bit hợp lệ.
- Chuyển dữ liệu vận hành, upload, database, backup và trạng thái sang `data/`; gói phát hành không chứa mật khẩu thật, phiên đăng nhập, log, database đang chạy, server game hay MOD của máy đóng gói.
- Chuyển Docker Compose, Nginx và systemd vào `deploy/`; cập nhật toàn bộ service, script cài mới/nâng cấp và đường dẫn trong Web theo cấu trúc mới.
- Viết lại README cho quy trình cài mới Ubuntu, upload/kích hoạt server, MOD, backup/restore, log, bảo mật database và mở khóa Admin qua SSH.
- Không thêm chức năng “Dọn file tạm phiên bản”; quản trị viên chỉ quản lý phiên bản server và log thật đã được xác định rõ.

## v1.1.23

- Khi kích hoạt phiên bản server, tự áp dụng IP LAN/ZeroTier đã chọn gần nhất; nếu IP cũ không còn trên máy thì tự chọn IP LAN hiện tại.
- Mỗi lần Start All chuẩn hóa lại cấu hình mạng của server active để phiên bản mới không giữ IP từ máy cũ.
- Đồng bộ `InternetIp`, `IntranetIp` của Goddess/Bishop và đặt kết nối PaySys/Role của Bishop về `127.0.0.1`, tương đương cơ chế cấu hình lúc khởi động của QuanLy2.
- Giữ nguyên `MacAddress`, `Guid`, tài khoản và mật khẩu của từng phiên bản.

## v1.1.22

- Kiểm tra độc lập toàn bộ sáu nhóm Tổng quát theo đúng server active: Kinh nghiệm, Nhiệm vụ, Hồi sinh quái, SimCity, Rơi đồ và Xếp chồng vật phẩm.
- Nhóm đủ file hiển thị dữ liệu thật và cho thao tác; nhóm thiếu hoặc sai cấu trúc hiển thị `Chưa thấy`, liệt kê file thiếu và tự khóa form mà không làm lỗi các nhóm khác.
- Hiển thị thanh tổng quan tên/đường dẫn server active cùng trạng thái Có/Chưa thấy của từng nhóm ngay đầu trang.
- Trang vẫn trả HTTP 200 khi chưa chọn server, server không có tính năng mở rộng hoặc chỉ có một phần cấu hình; không dùng giá trị giả để ghi vào server.
- Bổ sung trạng thái Chưa thấy rõ ràng cho Kỳ Trân Các và Vật phẩm; Sự kiện tiếp tục tách riêng lỗi cấu hình chính và lỗi bảng tỷ lệ.

## v1.1.21

- Sửa lỗi 500 của Thiết lập game khi server active không có `web_mystery_map.ini` hoặc `web_mystery_record.ini` dành cho hook rơi vật phẩm đặc biệt.
- Khi hai file mở rộng chưa tồn tại, trang chỉ đọc tỷ lệ hiện có từ các bảng rơi quái thường và không tự sửa dữ liệu lúc mở trang.
- Khi Admin chủ động lưu cấu hình rơi đồ, tự tạo an toàn file mở rộng còn thiếu; hỗ trợ rollback cả file mới nếu một bước lưu khác thất bại.

## v1.1.20

- Sửa lỗi 500 khi mở Thiết lập game trên server mới do bộ lọc hồi sinh chỉ nhận `ReviveFrame=0` trong khi server JXNative dùng `ReviveFrame=36` cho quái thường.
- Tự phục hồi file `monster_respawn_state.json` rỗng/sai phiên bản đã sinh bởi bản cũ và tạo lại danh sách theo server active hiện tại.
- Nhận diện an toàn nhóm quái thường theo nhịp hồi sinh phổ biến nhất, tách khỏi các mẫu hiếm/boss có thời gian dài; nếu server không có dữ liệu phù hợp, chỉ vô hiệu hóa phần Hồi sinh quái thay vì làm lỗi toàn trang.

## v1.1.19

- Bảo vệ đăng nhập Admin theo từng IP: mỗi 3 lần sai sẽ khóa lần lượt 5 phút, 1 giờ và 24 giờ; đăng nhập đúng sẽ đặt lại cấp khóa của IP đó.
- Hiển thị IP phiên hiện tại, lần đăng nhập thành công gần nhất, IP đang bị khóa và 50 sự kiện bảo mật gần nhất trong trang Tài khoản Admin.
- Cho mở khóa riêng từng IP trên Web và bổ sung lệnh SSH `admin-login-lock` để xem, mở khóa một IP hoặc mở khóa tất cả khi Admin tự khóa mình.
- Không kiểm tra mật khẩu và không kéo dài thời hạn khi IP còn bị khóa; lỗi CSRF chỉ được ghi nhật ký, không tính là một lần sai mật khẩu.
- Giới hạn nhật ký bảo mật ở 1.000 bản ghi, không lưu mật khẩu và loại toàn bộ trạng thái/nhật ký đăng nhập khỏi GitHub cùng gói phát hành.

## v1.1.18

- Tính CPU tổng toàn máy bằng bộ lấy mẫu nền độc lập, lấy trung bình trượt 5 giây nên nhiều tab hoặc nhiều Admin không còn làm số liệu dao động sai.
- Cập nhật CPU/RAM/ổ đĩa mỗi 5 giây nhưng giữ đồng hồ Linux chạy mượt mỗi giây ngay trên trình duyệt.
- Gộp Đăng ký tài khoản và Danh sách người chơi thành một mục Tài khoản; tạo tài khoản mới bằng popup ngay trên danh sách.
- Gộp Kỳ Trân Các, Dòng vật phẩm, Cấu hình game và Quản lý event thành một mục Thiết lập game với bốn tab nội bộ; giữ nguyên các URL cũ.

## v1.1.17

- Hiển thị trực tiếp bốn nút Restore, Tải xuống, Ghi chú và Xóa trên từng file backup; bỏ menu ba chấm để thao tác nhanh hơn.

## v1.1.16

- Đồng bộ ba khu vực Server game, Log & Dung lượng và Backup & Restore theo bố cục tóm tắt → thao tác chính → danh sách.
- Thu gọn Server game thành một thanh trạng thái và danh sách phiên bản; chuyển đổi IP cùng Upload/GitHub sang popup, gom đổi tên/chọn đường dẫn/xóa vào menu từng dòng.
- Tách Log & Dung lượng thành Xem log và Quản lý dung lượng; bổ sung tổng log game, journal, ổ đĩa trống và chế độ xem log toàn màn hình.
- Làm lại quản lý dung lượng thành danh sách thống nhất cho log game, journal, Start/Reload và Docker; giữ chọn thư mục log an toàn.
- Thu gọn Backup & Restore còn Kho backup và Lịch tự động & Lịch sử; thêm thanh tình trạng database, backup mới nhất, lịch kế tiếp và tổng dung lượng kho.
- Chuyển Upload backup, tạo/sửa lịch và thời gian lưu backup sang popup; gom Restore, tải xuống, ghi chú và xóa vào menu từng file.
- Xóa hoàn toàn chức năng backup từ server khác qua SSH, route xử lý, mã Paramiko và phụ thuộc Paramiko.

## v1.1.15

- Đưa Start All, Reload và Stop All vào ngay khung Thành phần game; bỏ thanh điều khiển và nhãn 6/6 dư thừa.
- Thu hẹp cột thành phần để dành diện tích cho log, rút gọn tên hiển thị và cho phép bấm toàn bộ dòng để chuyển nguồn log.
- Chuyển Server & Dữ liệu sang nhóm Hệ thống trong sidebar.
- Sửa sidebar thu gọn: nút ba gạch luôn nằm trong sidebar, chỉ hiện icon con của nhóm đang mở và vẫn giữ mục hiện tại.
- Thêm hộp duyệt thư mục trực quan cho đường dẫn chạy server và thư mục log, tham khảo cách trình bày của QuảnLy2.
- Giới hạn trình duyệt thư mục trong đúng phiên bản hoặc server active, chặn symbolic link/đường dẫn vượt gốc và chỉ cho chọn server có đủ gateway + server1.

## v1.1.14

- Mỗi thao tác mở một phiên log mới mà không xóa log thật: Start/Stop All áp dụng 6 service, Reload chỉ S3Relay + GameServer, bật/tắt riêng chỉ service được chọn.
- Dashboard chỉ xem phiên hiện tại, mặc định 300 dòng; có 100, 1.000 và Toàn bộ phiên với cơ chế chỉ lấy thêm dòng mới thay vì tải lại toàn bộ.
- Đưa Start All, Reload và Stop All lên thanh điều khiển ngang; luôn giữ ba nút, khóa tạm khi không phù hợp hoặc đang xử lý.
- Thu gọn bảng service: chấm xanh/đỏ/vàng biểu thị chạy/tắt/đang xử lý, chỉ hiện một nút Bật hoặc Tắt và bấm tên để chọn log; database dùng cùng cách trình bày.
- Đổi khung dashboard thành `Log server`, bỏ nút Xóa hiển thị và hiển thị tên, giờ bắt đầu cùng phạm vi phiên log hiện tại.
- Gom Phiên bản/IP, Log/Dung lượng và Backup/Restore vào `Server & Dữ liệu` với ba tab riêng; không còn trang dài phải cuộn qua các khu vực khác.
- Tab Log/Dung lượng đặt trình xem toàn bộ lịch sử cạnh công cụ dọn; tách Dọn journal xuống 100 MB khỏi Làm trống log Start/Reload và khóa dọn journal khi chưa vượt 100 MB.
- Hiển thị tiến trình Start All theo bước 1/6 đến 6/6 và sửa chuyển hướng đăng nhập trực tiếp về dashboard.

## v1.1.13

- Khi thay đổi cấu hình mod lúc GameServer đang chạy, yêu cầu xác nhận và tự chạy Reload Game an toàn; khi server tắt chỉ lưu để áp dụng ở lần khởi động sau.
- Đồng bộ màu tên service, tab nguồn và nội dung log; đổi S3Relay sang xanh sáng, GameServer sang cam và ghi nhớ số dòng/thời gian/tự cuộn trong trình duyệt.
- Chuyển toàn bộ thao tác dọn file log khỏi dashboard sang trang Phiên bản Server / IP; bỏ chế độ xóa theo 7 ngày.
- Sắp xếp lại trang Phiên bản/IP theo server active, IP, danh sách phiên bản, Upload/GitHub và quản lý dung lượng log.
- Quản lý từng thư mục log của server active, hiển thị số file/dung lượng, xóa riêng hoặc tất cả và cho thêm đường dẫn con an toàn; không đi theo symbolic link và không xóa thư mục.
- Thêm thống kê journal, log Docker và log thao tác JXNative; nút Xóa log hệ thống dọn journal bằng `journalctl` và làm rỗng log Start/Reload.
- Giới hạn journal lưu trên ổ ở 500 MB, journal RAM ở 100 MB; tự xoay log Docker MSSQL/MySQL ở 20 MB × 5 file/container.

## v1.1.12

- Header chỉ cập nhật IP/CPU/RAM/ổ đĩa/đồng hồ mỗi 2 giây bằng API; dashboard không còn tự tải lại toàn trang.
- Đưa tên phiên bản server sang góc trái header; bỏ banner sẵn sàng, đường dẫn server và năm dòng cổng khỏi dashboard.
- Gom điều khiển thành `Start All`, `Reload`, `Stop All`; thu gọn cấu hình mod xuống cuối danh sách 6 service và 2 database.
- Tắt/reset máy luôn bấm được; nếu server đang chạy, hệ thống Stop All an toàn và chỉ thực hiện thao tác máy khi service cùng cổng đã dừng hết.
- Mở rộng log theo toàn màn hình, thêm nhãn và màu riêng cho tám nguồn; thời gian, lỗi, cảnh báo và thành công có màu trực quan như QuảnLy2.
- Làm lại Backup/Restore thành bốn tab: file backup, lịch tự động, lịch sử và cài đặt lưu trữ; hỗ trợ backup riêng MySQL/MSSQL, upload, ghi chú, tải xuống, restore và xóa.
- Thêm service `jx-backup-scheduler` chạy lịch backup theo giờ, ngày hoặc tuần; lưu lịch sử, chạy lại khi lỗi và tự dọn backup theo số ngày cấu hình.

## v1.1.11

- Đổi bảng điều khiển thành bố cục service 30% và log realtime 70%, có nguồn log riêng, số dòng, thời gian, tự cuộn, làm mới và xóa phần đang hiển thị.
- Bổ sung dọn file log của phiên bản đang chọn theo hai mức: cũ hơn 7 ngày hoặc toàn bộ; không tác động journal hệ thống.
- Hiển thị tên và đường dẫn phiên bản server đang chạy ngay trên bảng điều khiển.
- Thêm Reload Game an toàn theo thứ tự: yêu cầu S3Relay lưu và thoát, dừng GameServer, bật lại S3Relay rồi GameServer và chờ đúng cổng.
- Thêm cấu hình mod động: mặc định `vdk.so`, tự nhận mod ELF 32-bit tên khác, bắt chọn khi có nhiều file và tách công tắc `special_drop_hook.so`.
- Chuyển nút tắt máy và khởi động lại xuống cuối sidebar; khóa cả giao diện lẫn máy chủ khi còn service hoặc cổng game đang hoạt động.

## v1.1.10

- Bật kiến trúc `i386` và cài runtime 32-bit cho `goddess_y`, `bishop_y`, `s3relay_y` và `jx_linux_y` trên Ubuntu mới.
- Bổ sung `libc6:i386`, `libstdc++6:i386`, `libgcc-s1:i386` và `libuuid1:i386` vào cả cài mới lẫn cập nhật.
- Kiểm tra `/lib/ld-linux.so.2` trước khi khởi động để báo rõ khi máy thiếu môi trường chạy game 32-bit.

## v1.1.9

- Cài tự động `libsybdb5` trên Ubuntu mới để cung cấp `libsybdb.so.5` cho PaySys và Relay.
- Kiểm tra thư viện FreeTDS trước khi khởi động, hiển thị hướng dẫn cụ thể thay vì để PaySys lặp lại `status=127`.

## v1.1.8

- Đổi tên hiển thị chính thức của bộ quản lý thành JXNative; giữ đường dẫn nội bộ `/opt/QuanLy_One` để cập nhật an toàn.
- Sửa file `jxs3relay.service` bị dính lệnh giải nén không hợp lệ trong v1.1.7.
- Khởi động server tuần tự theo đúng phụ thuộc và chỉ sang bước kế tiếp khi cổng trước đã mở: 5002, 7777, 5001, 5622, 5003, 6666.
- Kiểm tra phiên bản server đang kích hoạt, đủ `gateway/`, `server1/`, binary và database trước khi chạy.
- Hiển thị trực tiếp tiến độ hoặc bước bị lỗi trên bảng điều khiển, kèm log khởi động riêng.
- Dùng PTY cho S3Relay và tự nạp `vdk.so`/`special_drop_hook.so` theo phiên bản server đang chọn.
- Khi cài/cập nhật, vô hiệu hóa có sao lưu các systemd override cũ còn trỏ về `/opt/jxnative` hoặc `/home/jxser`.

## v1.1.7

- Header hiển thị CPU theo phần trăm và xung nhịp GHz hiện tại.
- RAM và ổ đĩa hiển thị dung lượng đã dùng, tổng dung lượng và phần trăm.
- Đồng hồ chuyển sang 12 giờ AM/PM và bỏ nhãn Giờ Linux (24h).
- Cố định kích thước các khung trạng thái và dùng chữ số đều cột để tránh giao diện co giãn.

## v1.1.6

- Đưa nút Viết bài mới lên cùng hàng với Bài viết và Thư viện ảnh.
- Bỏ nút Cấu hình website bị trùng trong trang quản lý bài viết.
- Sửa bộ chọn ảnh trong trình soạn để lọc chính xác ảnh theo thư mục.

## v1.1.5

- Gom thư viện ảnh vào khu vực Quản lý bài viết và lọc gọn theo từng thư mục hoặc tất cả ảnh.
- Lọc bài theo Tin tức, Tính năng, Sự kiện; tìm theo tiêu đề/slug và hiện hoặc ẩn ngay trong danh sách.
- Trình soạn bài chọn ảnh từ thư viện theo thư mục hoặc tải ảnh trực tiếp từ máy tính; dùng được cho nội dung và ảnh đại diện.
- Kiểm tra đúng định dạng ảnh và giới hạn file tải lên tối đa 10 MB.

## v1.1.4

- Thư viện ảnh quản trị hiển thị toàn bộ ảnh hiện có của Web A, gồm cả ảnh đang dùng trong bài viết.
- Trang viết và sửa bài chia hai bên: nhập nội dung bên trái, xem trước trực tiếp bên phải; danh sách có nút xem riêng cho từng bài.
- Đồng hồ Linux trên header dùng định dạng 24 giờ và làm mới mỗi giây.
- Cho tải phiên bản server từ repository GitHub công khai, tự dò thư mục có `gateway/` và `server1/`.

## v1.1.3

- Bấm trực tiếp các mục lớn trên menu Thạch Chi sẽ mở nội dung phù hợp.
- Vẫn giữ menu con khi rê chuột như Web A gốc.
- Tự bổ sung các bài Web A còn thiếu vào `site.db` khi cập nhật, không ghi đè bài đã sửa.

## v1.1.2

- Chỉ giữ giao diện public Thạch Chi.
- Thống nhất trang chủ, tin tức, bài viết, đăng ký, đăng nhập và tài khoản vào cùng bố cục Thạch Chi.
- Sửa khung nội dung dài, ảnh tràn, menu lớp trên và slideshow trang chủ.
- Thêm đổi tên phiên bản server.
- Giữ nguyên cấu trúc file sau giải nén và cho chọn đúng thư mục có `gateway/` cùng `server1/`.
- Header quản trị cập nhật giờ, CPU và RAM mỗi giây; IP và ổ đĩa được làm mới nền mỗi 10 giây.
- Thêm `update.sh` để dọn file giao diện cũ và nạp lại cả Web Admin lẫn Web Public.

## v1.1.1

- Thêm số phiên bản ở góc dưới sidebar quản trị.
- Thêm sidebar drawer, nhóm menu thu gọn và header trạng thái hệ thống.
