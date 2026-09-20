#!/bin/bash
set -euo pipefail

project_root=/opt/QuanLy_One
compose_file="$project_root/deploy/docker-compose.yml"
admin_root="$project_root/app/web/admin"

if [ "$(id -u)" -ne 0 ]; then
    echo "Hãy chạy: sudo bash /opt/QuanLy_One/update.sh" >&2
    exit 1
fi

if [ ! -f "$project_root/VERSION" ] || [ ! -f "$admin_root/app.py" ] || [ ! -f "$compose_file" ]; then
    echo "Không tìm thấy bộ JXNative hợp lệ tại $project_root" >&2
    exit 1
fi

for unit in jxgame jxs3relay jxbishop jxgoddess jxrelaypay jxpaysys; do
    if systemctl is-active --quiet "$unit"; then
        echo "Hãy Stop All trước khi cập nhật JXNative." >&2
        exit 2
    fi
done

systemctl stop jx-webpanel quanly-public jx-backup-scheduler >/dev/null 2>&1 || true

if ! command -v rsync >/dev/null 2>&1; then
    apt-get update
    apt-get install -y rsync
fi

mkdir -p \
    "$project_root/data/state" \
    "$project_root/data/uploads" \
    "$project_root/data/database/mysql/data" \
    "$project_root/data/database/mssql/data" \
    "$project_root/data/database/backups" \
    "$project_root/JX_Servers/JX_Versions" \
    "$project_root/JX_Servers/MOD"

migrate_directory() {
    source_path=$1
    destination_path=$2
    [ -d "$source_path" ] || return 0
    mkdir -p "$destination_path"
    rsync -a "$source_path/" "$destination_path/"
}

# Di chuyển dữ liệu của cấu trúc v1.1.x nếu đây là lần nâng cấp đầu tiên.
legacy_active_target=""
if [ -L "$project_root/active-server" ]; then
    legacy_active_target=$(readlink -f "$project_root/active-server" || true)
fi
migrate_directory "$project_root/state" "$project_root/data/state"
migrate_directory "$project_root/uploads" "$project_root/data/uploads"
migrate_directory "$project_root/servers" "$project_root/JX_Servers/JX_Versions"
migrate_directory "$project_root/database/mysql/data" "$project_root/data/database/mysql/data"
migrate_directory "$project_root/database/mssql/data" "$project_root/data/database/mssql/data"
migrate_directory "$project_root/database/backups" "$project_root/data/database/backups"

if [ -n "$legacy_active_target" ] && [[ "$legacy_active_target" == "$project_root/servers/"* ]]; then
    relative_target=${legacy_active_target#"$project_root/servers/"}
    if [ -d "$project_root/JX_Servers/JX_Versions/$relative_target" ]; then
        ln -sfn "$project_root/JX_Servers/JX_Versions/$relative_target" "$project_root/JX_Servers/Active"
    fi
fi

if [ -d "$project_root/web-manager/venv" ] && [ ! -d "$admin_root/venv" ]; then
    mv "$project_root/web-manager/venv" "$admin_root/venv"
fi
if [ -d "$project_root/web-public/ModuleWebContent/library/images/uploads" ]; then
    migrate_directory \
        "$project_root/web-public/ModuleWebContent/library/images/uploads" \
        "$project_root/app/web/assets/legacy/library/images/uploads"
fi

# Chỉ xóa đúng các thư mục chương trình v1.1.x sau khi dữ liệu đã được sao chép.
rm -rf \
    "$project_root/active-server" \
    "$project_root/state" \
    "$project_root/uploads" \
    "$project_root/servers" \
    "$project_root/database" \
    "$project_root/web-manager" \
    "$project_root/web-public-python" \
    "$project_root/web-public" \
    "$project_root/shared" \
    "$project_root/runtime" \
    "$project_root/scripts" \
    "$project_root/systemd" \
    "$project_root/nginx-host"
rm -f "$project_root/docker-compose.yml"

if [ ! -x "$admin_root/venv/bin/python" ]; then
    python3 -m venv "$admin_root/venv"
fi
"$admin_root/venv/bin/pip" install --upgrade pip
"$admin_root/venv/bin/pip" install -r "$admin_root/requirements.txt"
"$admin_root/venv/bin/pip" install -r "$project_root/app/web/public/requirements.txt"

if ! command -v git >/dev/null 2>&1; then
    apt-get update
    apt-get install -y git
fi

native_packages=(libsybdb5 libc6:i386 libstdc++6:i386 libgcc-s1:i386 libuuid1:i386)
missing_native_packages=()
if ! dpkg --print-foreign-architectures | grep -x i386 >/dev/null; then
    dpkg --add-architecture i386
fi
for package in "${native_packages[@]}"; do
    if ! dpkg-query -W -f='${Status}' "$package" 2>/dev/null | grep 'install ok installed' >/dev/null; then
        missing_native_packages+=("$package")
    fi
done
if [ "${#missing_native_packages[@]}" -gt 0 ]; then
    apt-get update
    apt-get install -y "${missing_native_packages[@]}"
fi

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
    "$project_root"/tools/apply-update \
    "$project_root"/tools/backup-scheduler \
    "$project_root"/tools/init_databases.py \
    "$project_root"/tools/init_site.py \
    "$project_root"/tools/run-backup-job \
    "$project_root"/tools/build-release

"$admin_root/venv/bin/python" "$project_root/tools/init_site.py"

cp "$project_root"/deploy/systemd/*.service /etc/systemd/system/
install -d -m 0755 /etc/systemd/journald.conf.d
install -m 0644 "$project_root/deploy/systemd/journald-jxnative.conf" /etc/systemd/journald.conf.d/99-jxnative.conf
install -d -m 0755 /etc/systemd/journald@jxnative.conf.d
install -m 0644 "$project_root/deploy/systemd/journald-jxnative-namespace.conf" /etc/systemd/journald@jxnative.conf.d/99-jxnative.conf
cp "$project_root/deploy/nginx/quanly-one.conf" /etc/nginx/sites-available/quanly-one
ln -sfn /etc/nginx/sites-available/quanly-one /etc/nginx/sites-enabled/quanly-one

systemctl daemon-reload
nginx -t
set -a
. "$project_root/.env"
set +a
if [ -n "${MYSQL_ROOT_PASSWORD:-}" ] && [ -n "${MSSQL_SA_PASSWORD:-}" ]; then
    docker compose --env-file "$project_root/.env" -f "$compose_file" up -d --remove-orphans
    installed_version=$(tr -d '\r\n' < "$project_root/VERSION")
    printf '{"complete":true,"source":"update","version":"%s"}\n' "$installed_version" > "$project_root/data/state/installation.json"
    chmod 600 "$project_root/data/state/installation.json"
    systemctl enable jx-backup-scheduler >/dev/null 2>&1 || true
    systemctl restart systemd-journald jx-webpanel quanly-public jx-backup-scheduler
else
    systemctl disable --now jx-backup-scheduler >/dev/null 2>&1 || true
    systemctl restart systemd-journald jx-webpanel quanly-public
    echo "Database chưa có mật khẩu; hãy hoàn tất trình thiết lập lần đầu trên Web Admin."
fi
systemctl reload nginx

echo "Đã cập nhật JXNative lên v$(cat "$project_root/VERSION")."
