#!/bin/bash
set -euo pipefail

project_root=/opt/QuanLy_One

if [ "$(id -u)" -ne 0 ]; then
    echo "Hãy chạy: sudo bash install.sh" >&2
    exit 1
fi

if [ ! -f "$project_root/deploy/docker-compose.yml" ]; then
    echo "QuanLy_One phải nằm tại /opt/QuanLy_One" >&2
    exit 1
fi

case "$(uname -m)" in
    x86_64|amd64) ;;
    *) echo "Các binary JX hiện chỉ được chuẩn bị cho x86_64." >&2; exit 1 ;;
esac

export DEBIAN_FRONTEND=noninteractive
dpkg --add-architecture i386
apt-get update
apt-get install -y \
    docker.io python3 python3-venv python3-pip rsync curl iproute2 git \
    libsybdb5 libc6:i386 libstdc++6:i386 libgcc-s1:i386 libuuid1:i386
if ! docker compose version >/dev/null 2>&1; then
    apt-get install -y docker-compose-v2 || apt-get install -y docker-compose-plugin
fi

systemctl enable --now docker

if [ ! -f "$project_root/.env" ]; then
    cp "$project_root/.env.example" "$project_root/.env"
    manager_secret=$(python3 -c 'import secrets; print(secrets.token_urlsafe(48))')
    public_secret=$(python3 -c 'import secrets; print(secrets.token_urlsafe(48))')
    sed -i "s/^MANAGER_SECRET_KEY=.*/MANAGER_SECRET_KEY=${manager_secret}/" "$project_root/.env"
    sed -i "s/^PUBLIC_SECRET_KEY=.*/PUBLIC_SECRET_KEY=${public_secret}/" "$project_root/.env"
    chmod 600 "$project_root/.env"
fi

if ! grep -q '^PUBLIC_SECRET_KEY=' "$project_root/.env"; then
    public_secret=$(python3 -c 'import secrets; print(secrets.token_urlsafe(48))')
    printf '\nPUBLIC_SECRET_KEY=%s\n' "$public_secret" >>"$project_root/.env"
fi

mkdir -p \
    "$project_root/data/state" \
    "$project_root/data/uploads" \
    "$project_root/data/database/mysql/data" \
    "$project_root/data/database/mssql/data" \
    "$project_root/data/database/backups" \
    "$project_root/JX_Servers/JX_Versions" \
    "$project_root/JX_Servers/MOD"

python3 -m venv "$project_root/app/web/admin/venv"
"$project_root/app/web/admin/venv/bin/pip" install --upgrade pip
"$project_root/app/web/admin/venv/bin/pip" install -r "$project_root/app/web/admin/requirements.txt"
"$project_root/app/web/admin/venv/bin/pip" install -r "$project_root/app/web/public/requirements.txt"

chmod 0755 \
    "$project_root"/JX_Servers/Runtime/jx-ensure-running \
    "$project_root"/JX_Servers/Runtime/jx-wait-ip \
    "$project_root"/JX_Servers/Runtime/jx-wait-port \
    "$project_root"/JX_Servers/Runtime/jxgame-wrapper \
    "$project_root"/JX_Servers/Runtime/s3relay-pty-wrapper \
    "$project_root"/JX_Servers/Runtime/s3relayserver \
    "$project_root"/JX_Servers/Runtime/sword3paysys \
    "$project_root"/JX_Servers/Scripts/activate-server \
    "$project_root"/JX_Servers/Scripts/reload-game-stack \
    "$project_root"/JX_Servers/Scripts/start-game-stack \
    "$project_root"/JX_Servers/Scripts/update-server-ip \
    "$project_root"/tools/admin-login-lock \
    "$project_root"/tools/backup-scheduler \
    "$project_root"/tools/init_databases.py \
    "$project_root"/tools/init_site.py \
    "$project_root"/tools/run-backup-job \
    "$project_root"/tools/build-release
chmod +x "$project_root"/JX_Servers/Active/gateway/bishop_y 2>/dev/null || true
chmod +x "$project_root"/JX_Servers/Active/gateway/goddess_y 2>/dev/null || true
chmod +x "$project_root"/JX_Servers/Active/gateway/s3relay/s3relay_y 2>/dev/null || true
chmod +x "$project_root"/JX_Servers/Active/server1/jx_linux_y 2>/dev/null || true

apt-get install -y nginx

# Web public/Admin đi qua Nginx cổng 80. Nếu máy đang bật UFW thì mở đúng
# cổng này; không thay đổi chính sách firewall khi UFW đang tắt.
if command -v ufw >/dev/null 2>&1 && ufw status 2>/dev/null | grep -q '^Status: active'; then
    ufw allow 80/tcp comment 'JXNative Web' >/dev/null
fi

cp "$project_root"/deploy/systemd/*.service /etc/systemd/system/
install -d -m 0755 /etc/systemd/journald.conf.d
install -m 0644 "$project_root/deploy/systemd/journald-jxnative.conf" /etc/systemd/journald.conf.d/99-jxnative.conf
install -d -m 0755 /etc/systemd/journald@jxnative.conf.d
install -m 0644 "$project_root/deploy/systemd/journald-jxnative-namespace.conf" /etc/systemd/journald@jxnative.conf.d/99-jxnative.conf
systemctl restart systemd-journald

# Vô hiệu hóa các override của bộ /opt/jxnative cũ nhưng giữ file để có thể phục hồi.
for legacy_conf in /etc/systemd/system/jx*.service.d/*.conf; do
    [ -f "$legacy_conf" ] || continue
    if grep -Eq '/opt/jxnative|/home/jxser' "$legacy_conf"; then
        disabled="${legacy_conf%.conf}.jxnative-legacy-disabled"
        [ ! -e "$disabled" ] || disabled="$disabled.$(date +%Y%m%d%H%M%S)"
        mv "$legacy_conf" "$disabled"
    fi
done
cp "$project_root/deploy/nginx/quanly-one.conf" /etc/nginx/sites-available/quanly-one
ln -sfn /etc/nginx/sites-available/quanly-one /etc/nginx/sites-enabled/quanly-one
if [ -L /etc/nginx/sites-enabled/default ]; then
    unlink /etc/nginx/sites-enabled/default
fi
systemctl daemon-reload
systemctl disable jxpaysys jxrelaypay jxgoddess jxs3relay jxbishop jxgame >/dev/null 2>&1 || true
systemctl enable jx-webpanel quanly-public nginx

set -a
. "$project_root/.env"
set +a
"$project_root/app/web/admin/venv/bin/python" "$project_root/tools/init_site.py"

nginx -t
systemctl restart jx-webpanel quanly-public nginx

if [ -n "${MYSQL_ROOT_PASSWORD:-}" ] && [ -n "${MSSQL_SA_PASSWORD:-}" ]; then
    # Máy đã cấu hình từ trước: giữ tương thích quy trình update/cài lại.
    docker compose --env-file "$project_root/.env" -f "$project_root/deploy/docker-compose.yml" up -d --remove-orphans
    "$project_root/app/web/admin/venv/bin/python" "$project_root/tools/init_databases.py"
    systemctl enable jx-backup-scheduler
    systemctl restart jx-backup-scheduler
    installed_version=$(tr -d '\r\n' < "$project_root/VERSION")
    printf '{"complete":true,"source":"existing-install","version":"%s"}\n' "$installed_version" > "$project_root/data/state/installation.json"
    chmod 600 "$project_root/data/state/installation.json"
    setup_message="Database cũ đã được nhận diện và khởi động."
else
    # Cài mới chỉ dựng Web. Database sẽ được tạo sau khi Admin đặt mật khẩu.
    systemctl disable --now jx-backup-scheduler >/dev/null 2>&1 || true
    setup_message="Web nền đã sẵn sàng. Hãy hoàn tất trình thiết lập database trên trang Admin."
fi

# Ưu tiên IPv4 nguồn của default route (thường là LAN đang dùng để truy cập
# máy chủ), rồi mới tìm IPv4 global không thuộc bridge/container.
server_ip=$(ip -4 route get 1.1.1.1 2>/dev/null | awk '
    { for (i = 1; i <= NF; i++) if ($i == "src") { print $(i + 1); exit } }
')
if [ -z "$server_ip" ]; then
    server_ip=$(ip -o -4 addr show scope global 2>/dev/null | awk '
        $2 !~ /^(docker|br-|veth)/ { split($4, address, "/"); print address[1]; exit }
    ')
fi
server_ip=${server_ip:-IP-MAY-CHU}

echo
echo "JXNative v$(cat "$project_root/VERSION" 2>/dev/null || echo dev) đã cài xong."
echo "IP máy chủ:      $server_ip"
echo "Trang chủ:       http://$server_ip/"
echo "Quản lý chung:   http://$server_ip/admin/"
echo "Đăng nhập mặc định: admin / admin123"
echo "$setup_message"
echo "Server game không tự khởi động; hãy upload/chọn server trên Web Manager."
