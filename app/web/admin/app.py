#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Web quản lý server JX/Kiếm Thế — sidebar dọc, điều khiển qua systemd, xem log CMD,
danh sách người chơi (Online/Offline + mọi thông tin DB)."""
import hashlib
import hmac
import json
import os
import re
import signal
import shutil
import select
import subprocess
import threading
import time
import tempfile
import zipfile
import fcntl
import gzip
import uuid
import unicodedata
import urllib.error
import urllib.request
from collections import Counter, deque
from datetime import datetime, timedelta
from pathlib import Path
from flask import (Flask, Response, has_request_context, jsonify, redirect,
                   render_template_string, request, send_file, session,
                   stream_with_context, url_for)
from flask import flash as _flask_flash
def flash(category, message): _flask_flash(message, category)  # gọi flash(loại, nội_dung)

import pymssql
import pymysql

MSSQL = dict(
    server="127.0.0.1",
    port=1433,
    user="sa",
    password=os.environ.get("MSSQL_SA_PASSWORD", ""),
    database=os.environ.get("MSSQL_DATABASE", "account_tong"),
)
MYSQL = dict(
    host="127.0.0.1",
    port=3306,
    user="root",
    password=os.environ.get("MYSQL_ROOT_PASSWORD", ""),
    database="server1",
)

# (dịch vụ systemd, nhãn hiển thị) — điều khiển qua systemctl, xem log qua journalctl
COMPONENTS = [
    ("jxpaysys",   "sword3paysys (PaySys 5002)"),
    ("jxrelaypay", "s3relayserver (Relay 7777)"),
    ("jxgoddess",  "goddess_y (5001)"),
    ("jxbishop",   "bishop_y (login 5622)"),
    ("jxs3relay",  "s3relay_y (chat/tong)"),
    ("jxgame",     "jx_linux_y (game 6666)"),
]
COMPONENT_SHORT_LABELS = {
    "jxpaysys": "PaySys",
    "jxrelaypay": "Relay",
    "jxgoddess": "Goddess_y",
    "jxbishop": "Bishop_y",
    "jxs3relay": "S3Relay_y",
    "jxgame": "Jx_Linux_y",
}
KEY_PORTS = [(5001,"Goddess"),(5002,"PaySys"),(5622,"Bishop login"),(5003,"S3Relay"),(6666,"GameServer")]
REQUIRED_FOR_GAME = [5001, 5002, 5622, 6666]
PROJECT_ROOT = "/opt/QuanLy_One"
JX_ROOT = os.path.join(PROJECT_ROOT, "JX_Servers")
SERVERS_ROOT = os.path.join(JX_ROOT, "JX_Versions")
ACTIVE_SERVER_PATH = os.path.join(JX_ROOT, "Active")
SHARED_MOD_ROOT = os.path.join(JX_ROOT, "MOD")
GAME_START_SCRIPT = os.path.join(JX_ROOT, "Scripts", "start-game-stack")
GAME_START_STATUS = os.path.join(PROJECT_ROOT, "data", "state", "game-start.status")
GAME_START_LOG = os.path.join(PROJECT_ROOT, "data", "state", "game-start.log")
GAME_START_LOCK = "/run/jxnative-game-start.lock"
GAME_RELOAD_SCRIPT = os.path.join(JX_ROOT, "Scripts", "reload-game-stack")
GAME_RELOAD_STATUS = os.path.join(PROJECT_ROOT, "data", "state", "game-reload.status")
GAME_RELOAD_LOG = os.path.join(PROJECT_ROOT, "data", "state", "game-reload.log")
GAME_RELOAD_LOCK = "/run/jxnative-game-reload.lock"
GAME_MOD_STATE_ROOT = os.path.join(PROJECT_ROOT, "data", "state", "mods")
GAME_MOD_MAX_LIBRARIES = 32
SYSTEM_UPDATE_TOOL = os.path.join(PROJECT_ROOT, "tools", "apply-update")
SYSTEM_UPDATE_STATUS = os.path.join(PROJECT_ROOT, "data", "state", "system-update.json")
SYSTEM_UPDATE_LOG = os.path.join(PROJECT_ROOT, "data", "state", "system-update.log")
SYSTEM_UPDATE_UNIT = "jxnative-update.service"
LOG_SESSION_PATH = os.path.join(PROJECT_ROOT, "data", "state", "log-session.json")
ACTIVITY_LOG_PATH = os.path.join(PROJECT_ROOT, "data", "state", "activity.jsonl")
UPDATE_REPOSITORY = os.environ.get("JXNATIVE_UPDATE_REPOSITORY", "Shidaichiacc/QuanLy_One").strip()
UPDATE_CHECK_INTERVAL = 6 * 60 * 60
_update_cache_lock = threading.Lock()
_update_cache = {"expires": 0.0, "result": None}
ACTIVE_SERVER_BINARIES = (
    "gateway/goddess_y",
    "gateway/bishop_y",
    "gateway/s3relay/s3relay_y",
    "server1/jx_linux_y",
)
LOG_SOURCES = [
    ("session", "Phiên hiện tại"),
    ("jxpaysys", "PaySys"),
    ("jxrelaypay", "RelayPay"),
    ("jxgoddess", "Goddess"),
    ("jxbishop", "Bishop"),
    ("jxs3relay", "S3Relay"),
    ("jxgame", "GameServer"),
    ("mssql", "MSSQL"),
    ("mysql", "MySQL"),
]
LOG_SOURCE_KEYS = {key for key, _label in LOG_SOURCES} | {"all"}
LOG_COLORS = {
    "session": "#4af626",
    "all": "#4af626",
    "jxpaysys": "#18ffff",
    "jxrelaypay": "#ff4081",
    "jxgoddess": "#e040fb",
    "jxbishop": "#448aff",
    "jxs3relay": "#76ff03",
    "jxgame": "#ff9100",
    "mssql": "#ffd54f",
    "mysql": "#00bfa5",
}

BACKUP_DIR = "/opt/QuanLy_One/data/database/backups"
BACKUP_FILES_ROOT = os.path.join(BACKUP_DIR, "files")
BACKUP_STATE_PATH = os.path.join(PROJECT_ROOT, "data", "state", "backup-system.json")
BACKUP_STATE_LOCK_PATH = os.path.join(PROJECT_ROOT, "data", "state", "backup-system.lock")
MYSQL_CONTAINER = "quanlyone_mysql"
MSSQL_CONTAINER = "quanlyone_mssql"
BACKUP_SET_RE = re.compile(r"^(?:jx_backup|before_restore)_\d{8}_\d{6}$")
DATABASE_BACKUP_FILES = {
    "account_tong.bak": "application/octet-stream",
    "server1.sql": "application/sql",
}
ADMIN_ACCOUNT_PATH = "/opt/QuanLy_One/JX_Servers/Active/server1/data/admin_accounts.ini"
GAMESETTING_PATH = "/opt/QuanLy_One/JX_Servers/Active/server1/settings/gamesetting.ini"
KTC_ROOT = "/opt/QuanLy_One/JX_Servers/Active/gateway/s3relay/relaysetting/syncfiles/settings"
KTC_GOODS_PATH = os.path.join(KTC_ROOT, "goods.txt")
KTC_BUYSELL_PATH = os.path.join(KTC_ROOT, "buysell.txt")
KTC_TYPE_PATH = os.path.join(KTC_ROOT, "shop", "type.txt")
KTC_PRICE_COLUMN = 7  # Đồng tiền
KTC_PRICE_MIN = 1
KTC_PRICE_MAX = 2000000000
KTC_CATEGORY_MAX = 10
KTC_GOODS_NAME_OVERRIDES = {
    # Các dòng này tồn tại trong goods.txt nhưng đều bị ghi tên chung
    # "ma bai phi van". Item thật và script mở mã bài đã có đầy đủ.
    2163: "Mã bài - Xích Thố",
    2164: "Mã bài - Đích Lô",
    2165: "Mã bài - Tuyệt Ảnh",
    2166: "Mã bài - Ô Vân Đạp Tuyết",
    2167: "Mã bài - Chiếu Dạ Ngọc Sư Tử",
}
EXP_RATE_MIN = 0
EXP_RATE_MAX = 10000
DROP_RATE_ROOT = "/opt/QuanLy_One/JX_Servers/Active/server1"
DROP_RATE_FILES = [
    f"settings/droprate/npcdroprate{level}.ini"
    for level in (10, 20, 30, 40, 50, 60, 70, 80, 90, 110, 119)
] + [
    "settings/item/npcdroprate.ini",
    "settings/droprate/npcdroprate.ini",
]
DROP_RATE_STATE_PATH = "/opt/QuanLy_One/data/state/drop_rate_baseline.json"
DROP_PERCENT_MIN = 0
DROP_PERCENT_MAX = 100
DROP_MONEY_RATE_MIN = 0
DROP_MONEY_RATE_MAX = 100
DROP_MONEY_MULTIPLIER_MIN = 0.0
DROP_MONEY_MULTIPLIER_MAX = 100.0
DROP_COIN_PERCENT_MIN = 0.0
DROP_COIN_PERCENT_MAX = 100.0
DROP_SPECIAL_PERCENT_MIN = 0.0
DROP_SPECIAL_PERCENT_MAX = 100.0
DROP_SPECIAL_ITEMS = {
    "mystery_map": (6, 1, 196, "Mật Đồ Thần Bí"),
    "mystery_record": (6, 1, 206, "Thần Bí Đồ Chí"),
}
DROP_SPECIAL_RATE_PATHS = {
    "mystery_map": "/opt/QuanLy_One/JX_Servers/Active/server1/settings/droprate/web_mystery_map.ini",
    "mystery_record": "/opt/QuanLy_One/JX_Servers/Active/server1/settings/droprate/web_mystery_record.ini",
}
GROUND_ITEM_LIFETIME_PATHS = (
    "/opt/QuanLy_One/JX_Servers/Active/server1/settings/obj/objdata.txt",
    "/opt/QuanLy_One/JX_Servers/Active/server1/settings/obj/objsetting.txt",
)
GROUND_ITEM_TICKS_PER_SECOND = 18
GROUND_ITEM_LIFETIME_MIN = 1.0
GROUND_ITEM_LIFETIME_MAX = 3600.0
NPC_TEMPLATE_PATH = "/opt/QuanLy_One/JX_Servers/Active/server1/settings/npcs.txt"
MONSTER_RESPAWN_STATE_PATH = "/opt/QuanLy_One/data/state/monster_respawn_state.json"
MONSTER_RESPAWN_TICKS_PER_SECOND = 18
MONSTER_RESPAWN_SECONDS_MIN = 0
MONSTER_RESPAWN_SECONDS_MAX = 3600
DROP_COIN_GENRE = 4
DROP_COIN_DETAIL = 417
DROP_COIN_PARTICULAR = 1
DROP_COIN_CONFIG_PATH = "/opt/QuanLy_One/JX_Servers/Active/server1/script/global/nobitaxd/vdk/coin_drop_webconfig.lua"
SIMCITY_CONFIG_PATH = "/opt/QuanLy_One/JX_Servers/Active/server1/script/global/nobitaxd/vdk/simcity/webconfig.lua"
SIMCITY_BASE_CONFIG_PATH = "/opt/QuanLy_One/JX_Servers/Active/server1/script/global/nobitaxd/vdk/simcity/config.lua"
DA_TAU_CONFIG_PATH = "/opt/QuanLy_One/JX_Servers/Active/server1/script/global/mel/configserver.lua"
EVENT_CONFIG_PATH = "/opt/QuanLy_One/JX_Servers/Active/server1/script/global/pgaming/configserver/configall.lua"
EVENT_FLAGS = [
    ("EventTuDong", "Sự kiện tự động 12 tháng", "Tự chọn sự kiện theo tháng hiện tại."),
    ("BauCua", "Bầu Cua", "NPC và bàn Bầu Cua tại Trung Tâm Tương Dương."),
    ("DoiVatPham", "NPC đổi vật phẩm", "Đổi nguyên liệu và vật phẩm của các hoạt động."),
    ("BanItemHoTro", "NPC bán vật phẩm hỗ trợ", "Bán các vật phẩm hỗ trợ trong game."),
    ("HoatDongTinSu", "Hoạt động Tín Sứ", "Bật chuỗi hoạt động Tín Sứ."),
    ("LoanChienCuuChauCoc", "Loạn Chiến Cửu Châu Cốc", "Mở tại NPC Chưởng Đăng Cung Nữ."),
    ("HoatDongDauNguu", "Hoạt động Đấu Ngưu", "Mở tại NPC Chưởng Đăng Cung Nữ."),
    ("NPCCongThanhQuan3Tru", "Công Thành Chiến 3 Trụ", "Bật NPC và hoạt động Công Thành 3 Trụ."),
    ("ThatThanhDaiChien", "Thất Thành Đại Chiến", "Bật hoạt động Thất Thành Đại Chiến."),
    ("CauCa", "Câu Cá", "Mở tại Thuyền Phu ở các thành."),
]
MONTHLY_EVENTS = [
    "Phúc Lộc Thọ", "Ghép Pháo", "Quốc tế Phụ nữ 8/3", "Mừng ngày 30/4",
    "Nấu bánh tháng 5", "Sinh Nhật Võ Lâm", "Mừng phiên bản mới",
    "Mật đồ thần bí - đại bảo rương", "Quốc Khánh", "Trung Thu",
    "Nhà giáo Việt Nam 20/11", "Giáng Sinh",
]
EVENT_GUIDES = [
    {
        "goal": "Thu thập nguyên liệu, gói Bánh Chưng và dùng Bánh Chưng Thượng Hạng để tích mốc.",
        "npc": "Thợ Bánh (gói bánh), Hàng Rong (mua bí quyết), Cây Mai/Cây Đào (đổi bộ Phúc–Lộc–Thọ) tại thành/thôn.",
        "materials": [
            "Túi Mừng Xuân (ID 1652): mở ra đúng 1 nguyên liệu gói bánh. Tỷ lệ trong script là Lá bánh 60%, Gạo nếp 25%, Đậu xanh 10%, Thịt heo 5%.",
            "Nguyên liệu gói bánh gồm: Lá bánh (1653), Gạo nếp (1654), Đậu xanh (1655), Thịt heo (1656).",
            "Phúc (1657), Lộc (1658), Thọ (1659): là bộ vật phẩm đổi thưởng riêng; ba chữ này không dùng trong công thức Bánh Chưng.",
            "Bí quyết Bánh Chưng Thượng Hạng (1660) và Bí quyết Bánh Chưng Hảo Hạng (1661): mua tại Hàng Rong với giá tương ứng 200.000 và 100.000 Ngân lượng.",
            "Thành phẩm gồm Bánh Chưng Thượng Hạng (1662), Bánh Chưng Hảo Hạng (1663), Bánh Chưng Thường (1664).",
        ],
        "recipes": [
            "Bánh Chưng Thường = 4 Lá bánh + 3 Gạo nếp + 2 Đậu xanh + 1 Thịt heo + 20.000 Ngân lượng.",
            "Bánh Chưng Hảo Hạng = 4 Lá bánh + 3 Gạo nếp + 2 Đậu xanh + 1 Thịt heo + 1 Bí quyết Hảo Hạng.",
            "Bánh Chưng Thượng Hạng = 4 Lá bánh + 3 Gạo nếp + 2 Đậu xanh + 1 Thịt heo + 1 Bí quyết Thượng Hạng.",
            "Bộ Phúc–Lộc–Thọ: nhân vật cấp 50 trở lên đem 1 Phúc + 1 Lộc + 1 Thọ + 9.999 Ngân lượng đến Cây Mai hoặc Cây Đào. Kết quả nhận ngẫu nhiên Phúc Duyên Lộ Tiểu (+10 điểm phúc duyên), Trung (+20) hoặc Đại (+50). Theo mã hiện tại, chỉ 100 lượt đổi đầu của mỗi nhân vật có phần thưởng.",
        ],
        "effect": "Bánh sau khi dùng phát thưởng trực tiếp, nhưng chỉ Bánh Chưng Thượng Hạng cộng tiến độ mốc đặc biệt. Các mốc đang cấu hình là 1.000 / 1.500 / 2.000 lần. Khi dùng bánh, nhân vật phải cấp 50 trở lên và chừa ít nhất 10 ô trống; bánh thường/hảo hạng dùng giới hạn thường, bánh thượng hạng dùng giới hạn đặc biệt.",
        "locations": [
            "Cây Mai — Thành Đô (389,315); Tương Dương (201,202); Lâm An (180,204).",
            "Cây Mai — Long Tuyền Thôn (199,202); Thạch Cổ Trấn (205,198); Đạo Hương Thôn (203,200); Giang Tân Thôn (443,387); Ba Lăng Huyện (198,222); Nam Nhạc Trấn (207,192); Tây Sơn Thôn (201,202).",
            "Cây Đào — Phượng Tường (203,196); Biện Kinh (221,190); Dương Châu (217,187); Đại Lý (198,198).",
            "Cây Đào — Long Môn Trấn (245,280); Vĩnh Lạc Trấn (198,202); Chu Tiên Trấn (201,196); Đào Hoa Nguyên (196,201).",
            "Thợ Bánh — Minh Nguyệt Trấn của Phượng Tường, Thành Đô, Biện Kinh, Tương Dương, Dương Châu, Đại Lý và Lâm An: mỗi bản đồ có 4 vị trí (196,197), (196,204), (205,197), (204,204).",
        ],
        "steps": [
            "Đánh quái hoặc tham gia các hoạt động được event cấu hình để nhận Túi Mừng Xuân; quái còn có thể rơi trực tiếp Phúc, Lộc và Thọ.",
            "Mở Túi Mừng Xuân để gom đủ bộ 4 Lá bánh, 3 Gạo nếp, 2 Đậu xanh và 1 Thịt heo cho mỗi chiếc bánh.",
            "Muốn làm bánh Hảo Hạng hoặc Thượng Hạng, mua đúng loại Bí quyết tại Hàng Rong rồi chọn công thức tương ứng ở Thợ Bánh.",
            "Dùng Bánh Chưng Thượng Hạng để tăng tiến độ, sau đó đến NPC event chọn Nhận Thưởng Đạt Mốc.",
            "Phúc, Lộc, Thọ không cần bấm dùng riêng: gom đủ bộ rồi đổi tại Cây Mai/Cây Đào theo công thức nêu trên.",
        ],
    },
    {
        "goal": "Thu thập và nâng cấp Phong Pháo Tiểu → Trung → Đại, dùng loại đặc biệt để tích mốc.",
        "npc": "Đại Thần Tài — ghép Phong Pháo Trung/Đại Đặc Biệt và nhận thưởng mốc.",
        "materials": [
            "Bao Lì Xì (1350) mở ra đúng 1 vật phẩm: Pháo Tiểu (1351) 60%, Pháo Trung (1352) 30% hoặc Pháo Đại (1353) 10%.",
            "Thành phẩm gồm Phong Pháo Tiểu Đặc Biệt (1354), Phong Pháo Trung Đặc Biệt (1355), Phong Pháo Đại Đặc Biệt (1356).",
        ],
        "recipes": [
            "Phong Pháo Tiểu Đặc Biệt = 10 Pháo Tiểu + 2 Pháo Trung + 1.000 Ngân lượng; tỷ lệ thành công 70%.",
            "Phong Pháo Trung Đặc Biệt = 10 Pháo Trung + 2 Pháo Đại + 3.000 Ngân lượng; tỷ lệ thành công 50%.",
            "Phong Pháo Đại Đặc Biệt = 100 Pháo Đại + 5.000 Ngân lượng; tỷ lệ thành công 20%.",
        ],
        "effect": "Ghép thất bại vẫn tiêu hao nguyên liệu. Chỉ dùng Phong Pháo Đại Đặc Biệt mới cộng tiến độ mốc đặc biệt.",
        "steps": [
            "Nhận nguyên liệu pháo từ quái và các hoạt động trong thời gian event.",
            "Tại Đại Thần Tài, chọn đúng nhánh Hợp Thành Pháo Trung hoặc Hợp Thành Pháo Đại; Pháo Tiểu Đặc Biệt dùng nhánh ghép riêng của vật phẩm.",
            "Dùng Phong Pháo Đại Đặc Biệt để nhận thưởng và cộng số lần sử dụng.",
            "Quay lại NPC event để nhận thưởng khi đạt mốc.",
        ],
        "locations": [
            "Đại Thần Tài — Lâm An (198,185); Phượng Tường (198,200); Biện Kinh (214,195).",
            "Đại Thần Tài — Đại Lý (203,199); Tương Dương (198,201); Thành Đô (392,316).",
            "Script tháng 2 không đặt Đại Thần Tài tại Dương Châu.",
        ],
    },
    {
        "goal": "Gom cánh hoa, bó hoa rồi tặng hoa để nhận thưởng và tích mốc.",
        "npc": "Quản Lý Sự Kiện — gói Bó Hoa Hồng/Bó Hoa Cúc và nhận thưởng mốc.",
        "materials": [
            "Cành Hoa Hồng (1679), Cành Hoa Cúc (1680); thành phẩm là Bó Hoa Hồng (1681), Bó Hoa Cúc (1682).",
        ],
        "recipes": [
            "Bó Hoa Hồng = 10 Cành Hoa Hồng + 300.000 Ngân lượng. Lời thoại cũ có chỗ ghi 100.000 nhưng mã hiện tại thực thu 300.000.",
            "Bó Hoa Cúc = 10 Cành Hoa Cúc + 50.000 Ngân lượng.",
        ],
        "effect": "Bó Hoa Hồng thuộc nhánh đặc biệt và cộng tiến độ mốc; Bó Hoa Cúc thuộc nhánh thưởng thường.",
        "steps": [
            "Đánh quái và tham gia hoạt động để nhận Cánh Hoa Hồng hoặc Cánh Hoa Cúc.",
            "Dùng 10 cánh hoa cùng Ngân lượng để gói thành bó hoa tương ứng.",
            "Đến Quản Lý Sự Kiện, chọn Gói Bó Hoa Hồng hoặc Gói Bó Hoa Cúc; sau đó nhấp dùng bó hoa để nhận thưởng.",
            "Số Bó Hoa Hồng đã sử dụng được tính vào các mốc thưởng.",
        ],
        "locations": [
            "Quản Lý Sự Kiện — Lâm An (198,185); Phượng Tường (198,200); Biện Kinh (214,195).",
            "Quản Lý Sự Kiện — Đại Lý (203,199); Tương Dương (198,201); Thành Đô (392,316).",
            "Script tháng 3 không đặt NPC này tại Dương Châu. Tên NPC và tên bắt sự kiện đã được đồng bộ để menu ghép hoa hoạt động.",
        ],
    },
    {
        "goal": "Thu thập vật phẩm chiến thắng, ghép và sử dụng Lá Cờ Chiến Thắng để tích mốc.",
        "npc": "Lễ Quan — hợp thành Lá Cờ Chiến Thắng và nhận thưởng mốc.",
        "materials": [
            "Hộp Quà May Mắn (1734) mở ra Mảnh Cờ 1 (1735) 60%, Mảnh Cờ 2 (1736) 30%, Mảnh Cờ 3 (1737) 5% hoặc Mảnh Cờ 4 (1738) 5%.",
        ],
        "recipes": [
            "Lá Cờ Chiến Thắng (1739) = 1 Mảnh Cờ 1 + 1 Mảnh Cờ 2 + 1 Mảnh Cờ 3 + 1 Mảnh Cờ 4; tỷ lệ thành công lấy từ TyLeGhepLaCoChienThang.",
        ],
        "effect": "Dùng Lá Cờ Chiến Thắng để nhận thưởng và cộng tiến độ mốc đặc biệt; các mảnh cờ không tự cộng mốc. Tỷ lệ mặc định hiện tại là 100%, có thể chỉnh trên web.",
        "steps": [
            "Tham gia Tống Kim, Vượt Ải và đánh quái/boss để nhận nguyên liệu event.",
            "Mang nguyên liệu đến NPC event để ghép Lá Cờ Chiến Thắng.",
            "Sử dụng Lá Cờ để nhận phần thưởng từng lần và cộng tiến độ.",
            "Nhận thưởng mốc tại NPC khi đủ số lần sử dụng.",
        ],
        "locations": [
            "Lễ Quan — Lâm An (198,185); Phượng Tường (198,200); Biện Kinh (214,195).",
            "Lễ Quan — Đại Lý (203,199); Tương Dương (198,201); Thành Đô (392,316).",
            "Script tháng 4 không đặt Lễ Quan tại Dương Châu. Tên NPC trống trong dữ liệu gốc đã được sửa thành Lễ Quan để khớp menu event.",
        ],
    },
    {
        "goal": "Thu thập Túi Hàng Hóa, chế biến Bánh Chay và dùng Bánh Chay Đặc Biệt để tích mốc.",
        "npc": "Quản Lý Sự Kiện/NPC nấu bánh tháng 5.",
        "materials": [
            "Túi Hàng Hóa (1393); đổi thành Túi/Nguyên Liệu Làm Bánh (1394). Kết quả nấu có bánh đặc biệt (1395), bánh thường (1396) hoặc bánh chưa chín (1397).",
        ],
        "recipes": [
            "Đổi túi: đến NPC Quản Lý Sự Kiện tại một trong sáu thành được liệt kê bên dưới, chọn “Ta muốn đổi túi nguyên liệu”. Nộp 10 Túi Hàng Hóa + 200.000 Ngân lượng để nhận 1 Bao Nguyên Liệu Làm Bánh (1394).",
            "Bắt đầu nấu: lập tổ đội đúng 2 người, một nam và một nữ, cả hai cấp 50 trở lên. Đứng trong một bản đồ hợp lệ rồi nhấp phải Bao Nguyên Liệu Làm Bánh; Bếp Lửa mang tên hai thành viên sẽ xuất hiện ngay cạnh người sử dụng.",
            "Phải tổ đội đúng 2 người, một nam và một nữ, cả hai cấp 50 trở lên. Bốn công đoạn, mỗi công đoạn 20 giây: nữ rửa đậu xanh; nam nhồi bột; cả hai thêm nhân; cả hai thêm củi.",
            "Bản đồ được nấu: 7 thành Phượng Tường, Thành Đô, Biện Kinh, Tương Dương, Dương Châu, Đại Lý, Lâm An; 8 thôn/trấn Long Tuyền, Long Môn, Thạch Cổ, Đạo Hương, Vĩnh Lạc, Chu Tiên, Giang Tân, Ba Lăng; và 4 thắng cảnh Hoa Sơn, Thanh Thành Sơn, Điểm Thương Sơn, Vũ Di Sơn.",
            "Điểm thao tác quyết định bánh đặc biệt, bánh thường hay bánh chưa chín. Hoàn tất bốn công đoạn, tiếp tục nhấp Bếp Lửa và chọn “Lấy bánh ra”; giới hạn 1.000 mẻ/ngày.",
        ],
        "effect": "Bánh đặc biệt mới cộng tiến độ mốc. Thao tác thiếu, sai người hoặc quá chậm có thể chỉ tạo bánh thường/bánh chưa chín.",
        "locations": [
            "Quản Lý Sự Kiện — Lâm An (198,185); Phượng Tường (198,200); Biện Kinh (214,195).",
            "Quản Lý Sự Kiện — Đại Lý (203,199); Tương Dương (198,201); Thành Đô (392,316).",
            "Script tháng 5 hiện không đặt NPC này tại Dương Châu và các tân thủ thôn.",
        ],
        "steps": [
            "Đánh quái và hoàn thành hoạt động để nhận Túi Hàng Hóa.",
            "Đến Quản Lý Sự Kiện, chọn “Ta muốn đổi túi nguyên liệu”; đổi 10 Túi Hàng Hóa + 200.000 lượng lấy 1 Bao Nguyên Liệu.",
            "Tổ đội một nam một nữ, đứng tại bản đồ hợp lệ và nhấp phải Bao Nguyên Liệu để gọi Bếp Lửa; không cần tìm NPC nấu bánh cố định.",
            "Hai người nhấp Bếp Lửa và làm đúng bốn công đoạn theo giới tính/thời điểm; sau công đoạn cuối chọn Lấy bánh ra.",
            "Sử dụng Bánh Chay Đặc Biệt và nhận thưởng các mốc tại NPC.",
        ],
    },
    {
        "goal": "Làm Bánh Kem Cát Tường/Như Ý và sử dụng Bánh Kem Cát Tường để tích mốc sinh nhật.",
        "npc": "Vạn Niên Gia — ghép Bánh Kem Cát Tường và nhận mốc; Hàng Rong — bán Đại Hỷ Lễ Bao giá 300.000 lượng.",
        "materials": [
            "Túi Đại Hỷ Thu (1750) mở ra một chữ: Mừng 60%, VLTK 30%, 3 là 5%, Tuổi 5%; Đại Hỷ Lễ Bao (1760) mua tại Hàng Rong.",
            "Thành phẩm gồm Bánh Kem Như Ý (1761) và Bánh Kem Cát Tường (1762).",
        ],
        "recipes": [
            "Bánh Kem Cát Tường = 3 Mừng + 3 VLTK + 3 chữ 3 + 3 Tuổi + 1 Đại Hỷ Lễ Bao; tỷ lệ theo TyLeBanhKemCatTuong.",
            "Nhánh Bánh Kem Như Ý dùng 3 Mừng + 3 VLTK + 3 chữ 3 + 3 Tuổi + 100.000 Ngân lượng; tỷ lệ theo TyLeBanhKemNhuY.",
        ],
        "effect": "Bánh Kem Cát Tường là vật phẩm cộng tiến độ mốc sinh nhật. Đại Hỷ Lễ Bao là nguyên liệu ghép, không phải Túi Đại Hỷ Thu.",
        "steps": [
            "Nhận túi nguyên liệu từ quái, Tống Kim, Vượt Ải, Thủy Tặc, Viêm Đế hoặc boss.",
            "Mở túi để lấy nguyên liệu làm bánh kem.",
            "Mua Đại Hỷ Lễ Bao ở Hàng Rong nếu ghép nhánh Cát Tường; đến Vạn Niên Gia chọn Nhận phần thưởng 1 để ghép.",
            "Dùng Bánh Kem Cát Tường để cộng tiến độ rồi nhận thưởng mốc.",
        ],
        "locations": [
            "Vạn Niên Gia — Lâm An (198,185); Phượng Tường (198,200); Biện Kinh (214,195).",
            "Vạn Niên Gia — Đại Lý (203,199); Tương Dương (198,201); Thành Đô (392,316).",
            "Script tháng 6 không đặt Vạn Niên Gia tại Dương Châu; Đại Hỷ Lễ Bao mua qua Hàng Rong ở thành.",
        ],
    },
    {
        "goal": "Thu thập hoa và lễ vật, đổi Thúy Tụ Hồ Tiên rồi sử dụng để tích mốc.",
        "npc": "Chưởng Đăng Cung Nữ — đổi Nụ Hoa lấy Cửu Tiên Ngự Yến; Mục Kiều Liên — ghép Thúy Tụ Hồ Tiên, tặng hoa/lễ vật và nhận mốc; Hàng Rong — bán Hải Vị Bồng Lai.",
        "materials": [
            "Nụ Hoa Hồng Đỏ (30132), Hoa Hồng Đỏ (30131), Hải Vị Bồng Lai (30129); vật phẩm trung gian Cửu Tiên Ngự Yến (30128); thành phẩm Thúy Tụ Hồ Tiên (30130).",
        ],
        "recipes": [
            "Tại Chưởng Đăng Cung Nữ: 1 Nụ Hoa Hồng Đỏ đổi 1 Cửu Tiên Ngự Yến.",
            "Tại Mục Kiều Liên: Thúy Tụ Hồ Tiên = 5 Hoa Hồng Đỏ + 1 Cửu Tiên Ngự Yến + 1 Hải Vị Bồng Lai.",
            "Hải Vị Bồng Lai mua tại Hàng Rong với giá 300.000 Ngân lượng.",
        ],
        "effect": "Dùng Thúy Tụ Hồ Tiên để nhận thưởng và cộng tiến độ mốc đặc biệt; Cửu Tiên Ngự Yến chỉ là vật phẩm trung gian.",
        "steps": [
            "Đánh quái hoặc tham gia hoạt động để nhận Nụ Hoa Hồng Đỏ và Hoa Hồng Đỏ.",
            "Đổi Nụ Hoa Hồng Đỏ lấy Cửu Tiên Ngự Yến.",
            "Dùng 5 Hoa Hồng Đỏ, Cửu Tiên Ngự Yến và Hải Vị Bồng Lai để đổi Thúy Tụ Hồ Tiên.",
            "Sử dụng Thúy Tụ Hồ Tiên và đến NPC nhận thưởng mốc.",
        ],
        "locations": [
            "Mục Kiều Liên — Lâm An (180,205). NPC event tháng 7 chỉ tự tạo Mục Kiều Liên tại Lâm An.",
            "Chưởng Đăng Cung Nữ — Lâm An tại (207,204), (197,185), (180,204) và (173,186); đây là các NPC cố định do autoexec tạo.",
            "Hàng Rong — dùng menu Mua Hải Vị Bồng Lai tại NPC Hàng Rong trong thành.",
        ],
    },
    {
        "goal": "Dùng Mật Đồ Thần Bí đổi Rương Bạc hoặc Hoàng Kim Bảo Hạp.",
        "npc": "Mục Lão — đổi Rương Bạc/Hoàng Kim Bảo Hạp và nhận mốc; Hàng Rong — bán Kim Thạch.",
        "materials": [
            "Mật Đồ Thần Bí (196) là nguyên liệu chính; Kim Thạch (1376) là nguyên liệu hiếm để nâng lên nhánh vàng.",
            "Hai thành phẩm: Hoàng Kim Bảo Hạp (1377) và Rương Bạc (1378).",
        ],
        "recipes": [
            "Rương Bạc = 10 Mật Đồ Thần Bí.",
            "Hoàng Kim Bảo Hạp = 10 Mật Đồ Thần Bí + 1 Kim Thạch.",
        ],
        "effect": "Rương Bạc thuộc giới hạn thưởng thường. Hoàng Kim Bảo Hạp thuộc giới hạn đặc biệt và khi mở sẽ cộng tiến độ mốc.",
        "steps": [
            "Thu thập Mật Đồ Thần Bí từ nguồn rơi đồ đang cấu hình trên server.",
            "Đổi 10 Mật Đồ Thần Bí lấy Rương Bạc.",
            "Kim Thạch có thể mua tại Hàng Rong với giá 300.000 lượng; có thêm 1 viên thì đổi 10 Mật Đồ lấy Hoàng Kim Bảo Hạp.",
            "Mở Hoàng Kim Bảo Hạp để nhận thưởng và cộng tiến độ mốc.",
        ],
        "locations": [
            "Mục Lão — Minh Nguyệt Trấn của Phượng Tường, Thành Đô, Biện Kinh, Tương Dương, Dương Châu, Đại Lý và Lâm An: cùng tọa độ (202,201).",
            "Hàng Rong — dùng menu Mua Kim Thạch tại NPC Hàng Rong trong thành.",
        ],
    },
    {
        "goal": "Đổi Quà Quốc Khánh, mở quà lấy Huy Chương Quốc Khánh và tích mốc.",
        "npc": "Sứ Giả Võ Lâm — hợp thành Quà Quốc Khánh và nhận thưởng mốc.",
        "materials": [
            "Ngôi Sao Chiến Thắng (1494), Quà Quốc Khánh (1495), Huy Chương Quốc Khánh (1496) và bộ Mảnh Mật Đồ 1–12.",
        ],
        "recipes": [
            "Quà Quốc Khánh = 10 Ngôi Sao Chiến Thắng + 150.000 Ngân lượng.",
            "Mở quà nhận đúng 1 vật phẩm: mỗi Mảnh Mật Đồ 1–7 có tỷ lệ 10%; mỗi mảnh 8–12 là 5%; Huy Chương Quốc Khánh là 5%.",
        ],
        "effect": "Huy Chương Quốc Khánh là vật phẩm hiếm dùng để cộng tiến độ mốc đặc biệt; các mảnh mật đồ là nhánh thưởng phụ.",
        "steps": [
            "Thu thập Ngôi Sao Chiến Thắng từ quái và các hoạt động.",
            "Dùng 10 Ngôi Sao Chiến Thắng cùng 15 vạn lượng để đổi Quà Quốc Khánh.",
            "Mở Quà Quốc Khánh để nhận Huy Chương Quốc Khánh và vật phẩm khác.",
            "Sử dụng Huy Chương Quốc Khánh rồi nhận thưởng các mốc tại NPC.",
        ],
        "locations": [
            "Sứ Giả Võ Lâm — Minh Nguyệt Trấn của Phượng Tường, Thành Đô, Biện Kinh, Tương Dương, Dương Châu, Đại Lý và Lâm An: cùng tọa độ (195,201).",
        ],
    },
    {
        "goal": "Ghép lồng đèn, nâng thành lồng đèn đặc biệt rồi đổi dần lên Bánh Trung Thu Con Heo.",
        "npc": "Hằng Nga — có đủ ba menu Hợp thành lồng đèn, Đổi lồng đèn đặc biệt và Đổi bánh trung thu.",
        "materials": [
            "Hộp Vật Liệu Lồng Đèn (1220) cho Giấy Kiếng Vàng (1221), Lam (1222), Lục (1223), Đỏ (1224), Cam (1225), Thanh Tre (1226), Dây Cói (1227), Nến (1228).",
            "Sáu lồng đèn đặc biệt ID 1229–1234; chuỗi bánh gồm Bánh Thường (1235), Đậu Xanh (1236), Trứng (1237), Đặc Biệt (1238), Hạt Sen (1239), Con Heo (1240); sáu lồng đèn thường ID 1241–1246.",
        ],
        "recipes": [
            "Lồng Đèn Bướm/Ngôi Sao/Ống/Tròn/Cá Chép lần lượt cần 2 Giấy Kiếng Vàng/Lam/Lục/Đỏ/Cam + 1 Thanh Tre + 1 Dây Cài + 1 Nến; phí lần lượt 50.000 / 100.000 / 200.000 / 300.000 / 400.000 lượng. Lồng Đèn Kéo Quân cần 5 Giấy Kiếng Cam + cùng bộ tre, dây, nến + 500.000 lượng.",
            "Nâng sáu lồng đèn thường thành loại đặc biệt cần thêm 1 Nến và lần lượt 100.000 / 200.000 / 300.000 / 400.000 / 500.000 / 600.000 Ngân lượng.",
            "Bánh Thường = Lồng Đèn Bướm ĐB + 500.000; Bánh Đậu Xanh = Lồng Đèn Sao ĐB + Bánh Thường + 500.000; Bánh Nhân Trứng = Lồng Đèn Ống ĐB + Bánh Thường + 500.000; Bánh Đặc Biệt = Lồng Đèn Cá Chép ĐB + Bánh Thường + 500.000; Bánh Hạt Sen = Lồng Đèn Kéo Quân ĐB + Bánh Thường + 500.000; Bánh Con Heo = Bánh Hạt Sen + Bánh Thường + 500.000 lượng.",
        ],
        "effect": "Bánh Trung Thu Con Heo mới cộng tiến độ mốc đặc biệt; các lồng đèn và cấp bánh trước chỉ là vật phẩm trung gian.",
        "steps": [
            "Đánh quái lấy Hộp Vật Liệu Lồng Đèn; mở hộp lấy giấy kiếng, thanh tre, dây cài và nến.",
            "Ghép các loại lồng đèn thường, sau đó dùng thêm nến và Ngân lượng để đổi loại đặc biệt.",
            "Đổi lồng đèn đặc biệt thành các cấp Bánh Trung Thu theo chuỗi của NPC.",
            "Dùng Bánh Trung Thu Con Heo để cộng tiến độ và nhận thưởng mốc.",
        ],
        "locations": [
            "Hằng Nga — Chu Tiên Trấn (205,197); Thạch Cổ Trấn (205,199); Long Tuyền Thôn (203,200).",
            "NPC tháng 10 chỉ được script đặt tại ba thôn/trấn này, không đặt trực tiếp trong bảy thành.",
        ],
    },
    {
        "goal": "Thu thập nguyên liệu, tạo Bí Kiếp Gia Truyền và sử dụng để tích mốc 20/11.",
        "npc": "Quản Lý Sự Kiện — hợp thành Bí Kiếp Gia Truyền và nhận mốc; Hàng Rong — bán 10 loại Thiệp Chúc Mừng.",
        "materials": [
            "Hộp Quà Ngày Nhà Giáo Việt Nam (1598) mở ra Tôn (1599) 60%, Sư (1600) 30%, Trọng (1601) 6%, Đạo (1602) 2% hoặc Hoa Hồng 2%.",
            "Mười loại Thiệp Chúc Mừng (1588–1597) được bán theo các quan hệ trong menu event, giá 500.000 Ngân lượng mỗi thiệp.",
        ],
        "recipes": [
            "Bí Kíp Gia Truyền (1603) = 1 Tôn + 1 Sư + 1 Trọng + 1 Đạo + 15 Hoa Hồng; tỷ lệ thành công theo TyLeGhepBiKiepGiaTruyen.",
            "Thiệp Chúc Mừng là nhánh tặng quà theo quan hệ; công thức Bí Kíp Gia Truyền trong script không tiêu hao thiệp.",
        ],
        "effect": "Dùng Bí Kíp Gia Truyền để cộng tiến độ mốc đặc biệt. Ghép thất bại vẫn tiêu hao các nguyên liệu đã nộp.",
        "steps": [
            "Tham gia hoạt động và đánh quái để nhận nguyên liệu event.",
            "Mua hoặc nhận thiệp chúc mừng theo các quan hệ sư đồ, hảo hữu hoặc bang hội.",
            "Mang nguyên liệu đến NPC để hoàn thành Bí Kiếp Gia Truyền.",
            "Sử dụng Bí Kiếp Gia Truyền rồi nhận thưởng các mốc tại NPC.",
        ],
        "locations": [
            "Quản Lý Sự Kiện — Lâm An (198,185); Phượng Tường (198,200); Biện Kinh (214,195).",
            "Quản Lý Sự Kiện — Đại Lý (203,199); Tương Dương (198,201); Thành Đô (392,316).",
            "Script tháng 11 không đặt NPC này tại Dương Châu; các loại thiệp mua qua Hàng Rong trong thành.",
        ],
    },
    {
        "goal": "Mở Hộp Quà Giáng Sinh, gom nguyên liệu và chế tạo Người Tuyết để tích mốc.",
        "npc": "Ông già No-en — chế tạo đủ sáu loại Người Tuyết và nhận thưởng mốc.",
        "materials": [
            "Hộp Quà Giáng Sinh (1311) cho đúng 1 vật phẩm: Hoa Tuyết (1312) 60%, Cành Thông (1314) 10%, Cà Rốt (1313) 10%, Nón Noel (1315) 9%, Khăn Xanh (1316) 8%, Khăn Đỏ (1317) 2%, Cây Thông (1318) 1%.",
            "Người Tuyết thường (1324), khăn xanh thường (1322), khăn đỏ thường (1323); ba bản đặc biệt tương ứng ID 1321, 1319, 1320.",
        ],
        "recipes": [
            "Người Tuyết Thường = 5 Hoa Tuyết + 2 Cành Thông + 1 Cà Rốt + 1 Nón Noel.",
            "Bản khăn xanh hoặc khăn đỏ thường = công thức cơ bản + 1 Khăn Xanh hoặc 1 Khăn Đỏ.",
            "Bản đặc biệt = công thức tương ứng + 1 Cây Thông; bản không khăn tốn thêm 10.000 Ngân lượng, bản khăn xanh/đỏ tốn thêm 20.000 Ngân lượng.",
        ],
        "effect": "Người Tuyết Khăn Choàng Đỏ Đặc Biệt mới cộng tiến độ mốc đặc biệt; các loại khác thuộc nhánh thưởng thường hoặc là thành phẩm trung gian.",
        "steps": [
            "Đánh quái và tham gia hoạt động để nhận Hộp Quà Giáng Sinh.",
            "Mở hộp lấy Hoa Tuyết, Cành Thông, Cà Rốt, Nón Giáng Sinh và nguyên liệu hiếm.",
            "Ghép Người Tuyết thường hoặc loại khăn choàng; có Cây Thông để làm loại đặc biệt.",
            "Dùng Người Tuyết Khăn Choàng Đỏ Đặc Biệt để cộng tiến độ và nhận thưởng mốc.",
        ],
        "locations": [
            "Ông già No-en — Minh Nguyệt Trấn của Phượng Tường, Thành Đô, Biện Kinh, Tương Dương, Dương Châu, Đại Lý và Lâm An: cùng tọa độ (198,195).",
        ],
    },
]
EVENT_RATE_ROOT = "/opt/QuanLy_One/JX_Servers/Active/server1/script"
EVENT_RATE_SPECS = [
    {"drop": [(1652, "Túi Mừng Xuân"), (1657, "Phúc"), (1658, "Lộc"), (1659, "Thọ")],
     "box": ("vng_event/eventpgaming/thang1/tuimungxuan.lua", ["Lá bánh", "Gạo nếp", "Đậu xanh", "Thịt heo"])},
    {"drop": [(1350, "Bao Lì Xì")],
     "box": ("vng_event/eventpgaming/thang2/baolixi.lua", ["Pháo Tiểu", "Pháo Trung", "Pháo Đại"]),
     "compose": [("TyLeGhepPhongPhaoTieu", "Ghép Phong Pháo Tiểu đặc biệt"), ("TyLeGhepPhongPhaoTrung", "Ghép Phong Pháo Trung đặc biệt"), ("TyLeGhepPhongPhaoDai", "Ghép Phong Pháo Đại đặc biệt")]},
    {"drop": [(1679, "Cành Hoa Hồng"), (1680, "Cành Hoa Cúc")]},
    {"drop": [(1734, "Hộp Quà May Mắn")],
     "box": ("vng_event/eventpgaming/thang4/hopquamayman.lua", ["Mảnh Cờ 1", "Mảnh Cờ 2", "Mảnh Cờ 3", "Mảnh Cờ 4"]),
     "compose": [("TyLeGhepLaCoChienThang", "Ghép Lá Cờ Chiến Thắng")]},
    {"drop": [(1393, "Túi Hàng Hóa")]},
    {"drop": [(1750, "Túi Đại Hỷ Thu")],
     "box": ("vng_event/eventpgaming/thang6/tuidaihythu.lua", ["Mừng", "VLTK", "Chữ 3", "Tuổi"]),
     "compose": [("TyLeBanhKemCatTuong", "Ghép Bánh Kem Cát Tường"), ("TyLeBanhKemNhuY", "Ghép Bánh Kem Như Ý")]},
    {"drop": [(30131, "Hoa Hồng Đỏ")]},
    {"drop": [(196, "Mật Đồ Thần Bí")]},
    {"drop": [(1494, "Ngôi Sao Chiến Thắng")],
     "box": ("vng_event/eventpgaming/thang9/quaquockhanh.lua", ["Mảnh Mật Đồ 1", "Mảnh Mật Đồ 2", "Mảnh Mật Đồ 3", "Mảnh Mật Đồ 4", "Mảnh Mật Đồ 5", "Mảnh Mật Đồ 6", "Mảnh Mật Đồ 7", "Mảnh Mật Đồ 8", "Mảnh Mật Đồ 9", "Mảnh Mật Đồ 10", "Mảnh Mật Đồ 11", "Mảnh Mật Đồ 12", "Huy Chương Quốc Khánh"]),
     "compose": [("TyLeGhepQuaQuocKhanh", "Ghép Quà Quốc Khánh")]},
    {"drop_special": [(1220, "Hộp Vật Liệu — quái cấp 90", [0, 1]), (1220, "Hộp Vật Liệu — quái cấp 10–80", [2])],
     "weights": ("vng_event/eventpgaming/thang10/hopvatlieulongden.lua", [(1221, "Giấy Kiếng Vàng"), (1224, "Giấy Kiếng Đỏ"), (1223, "Giấy Kiếng Lục"), (1225, "Giấy Kiếng Cam"), (1222, "Giấy Kiếng Lam"), (1226, "Thanh Tre"), (1227, "Dây Cói"), (1228, "Nến")])},
    {"drop": [(1598, "Hộp Quà 20/11")],
     "box": ("vng_event/eventpgaming/thang11/hopqua.lua", ["Tôn", "Sư", "Trọng", "Đạo", "Hoa Hồng"]),
     "compose": [("TyLeGhepBiKiepGiaTruyen", "Ghép Bí Kíp Gia Truyền")]},
    {"drop": [(1311, "Hộp Quà Giáng Sinh")],
     "box": ("vng_event/eventpgaming/thang12/hopquagiangsinh.lua", ["Hoa Tuyết", "Cành Thông", "Cà Rốt", "Nón Giáng Sinh", "Khăn Xanh", "Khăn Đỏ", "Cây Thông"])},
]
DA_TAU_DAILY_LIMIT_MIN = 1
DA_TAU_DAILY_LIMIT_MAX = 255
SIMCITY_TRAINING_MAPS = [
    (20, 19, "Kiếm Các Tây Nam"), (20, 7, "Tần Lăng tầng 1"),
    (20, 179, "La Tiêu Sơn"),
    (30, 193, "Vũ Di Sơn"), (30, 170, "Thổ Phỉ Động"),
    (30, 92, "Thục Cương Sơn"), (30, 22, "Bạch Vân Động"),
    (30, 4, "Kim Quang Động"), (30, 6, "Tỏa Vân Động"),
    (40, 21, "Thanh Thành Sơn"), (40, 167, "Điểm Thương Sơn"),
    (40, 23, "Thần Tiên Động"), (40, 5, "Kinh Hoàng Động"),
    (50, 182, "Nghiệt Long Động"), (50, 164, "Thiên Tầm Tháp"),
    (50, 38, "Thiết Tháp Mê Cung"), (50, 42, "Thiên Tâm Động"),
    (50, 24, "Hướng Thủy Động"),
    (60, 79, "Tương Dương Nha Môn Mật Đạo"), (60, 56, "Hoành Sơn Phái"),
    (60, 166, "Thiên Tầm Tháp tầng 3"), (60, 114, "108 La Hán Trận"),
    (60, 69, "Thanh Loa Động"), (60, 94, "Linh Cốc Động"),
    (70, 319, "Lâm Du Quan"), (70, 123, "Lão Hổ Động"),
    (70, 206, "Tần Lăng tầng 2"), (70, 72, "Đại Tù Động"),
    (70, 169, "Long Nhãn Động"),
    (80, 224, "Sa Mạc Địa Biểu"), (80, 198, "Thanh Khê Động"),
    (80, 320, "Chân Núi Trường Bạch"), (80, 181, "Lưỡng Thủy Động"),
    (80, 201, "Băng Hà Động"), (80, 203, "Vô Danh Động"),
    (80, 202, "Phù Dung Động"),
    (90, 322, "Trường Bạch Sơn Bắc"), (90, 321, "Trường Bạch Sơn Nam"),
    (90, 75, "Khỏa Lang Động"), (90, 225, "Sa Mạc Mê Cung 1"),
    (90, 226, "Sa Mạc Mê Cung 2"), (90, 227, "Sa Mạc Mê Cung 3"),
    (90, 336, "Phong Lăng Độ"), (90, 340, "Mạc Cao Quật"),
    (90, 144, "Dược Vương Động tầng 4"), (90, 93, "Tiến Cúc Động Mật Cung"),
    (90, 124, "Cán Viên Động Mê Cung"), (90, 152, "Tuyết Báo Động tầng 8"),
    (100, 919, "Thực Cốt Nhai"), (100, 920, "Hắc Mộc Nhai"),
    (100, 917, "Tích Huyết Cốc"), (100, 918, "Ác Nhân Cốc"),
    (110, 921, "Thiên Phụ Sơn"), (110, 922, "Bàn Long Sơn"),
    (110, 923, "Địa Mẫu Sơn"), (110, 924, "Uyển Phụng Sơn"),
]
SIMCITY_FACTIONS = [
    ("thieulam", "Thiếu Lâm", [(318, "Đạt Ma Độ Giang"), (319, "Hoành Tảo Thiên Quân"), (321, "Vô Tướng Trảm")]),
    ("thienvuong", "Thiên Vương", [(322, "Phá Thiên Trảm"), (323, "Truy Tinh Trục Nguyệt"), (325, "Truy Phong Quyết")]),
    ("duongmon", "Đường Môn", [(339, "Nhiếp Hồn Nguyệt Ảnh"), (342, "Cửu Cung Phi Tinh"), (302, "Bạo Vũ Lê Hoa")]),
    ("ngudoc", "Ngũ Độc", [(353, "Âm Phong Thực Cốt"), (355, "Huyền Âm Trảm")]),
    ("ngami", "Nga Mi", [(328, "Tam Nga Tề Tuyết"), (380, "Phong Sương Toái Ảnh")]),
    ("thuyyen", "Thúy Yên", [(336, "Băng Tung Vô Ảnh"), (337, "Băng Tâm Tiên Tử")]),
    ("caibang", "Cái Bang", [(357, "Phi Long Tại Thiên"), (359, "Thiên Hạ Vô Cẩu")]),
    ("thiennhan", "Thiên Nhẫn", [(361, "Vân Long Kích"), (362, "Thiên Ngoại Lưu Tinh")]),
    ("vodang", "Võ Đang", [(365, "Thiên Địa Vô Cực"), (368, "Nhân Kiếm Hợp Nhất")]),
    ("conlon", "Côn Lôn", [(372, "Ngạo Tuyết Tiêu Phong"), (375, "Lôi Động Cửu Thiên")]),
]
SIMCITY_DEFAULTS = {
    "hp_min": 60000,
    "hp_max": 120000,
    "attack_speed": 250,
    "cast_delay": 1,
    "normal_cast_delay": 2,
    "skill_level": 20,
    "stall_enabled": 1,
    "stall_city_min": 45,
    "stall_city_max": 65,
    "stall_village_min": 20,
    "stall_village_max": 30,
    "stall_datau_min": 20,
    "stall_datau_max": 30,
    "population_enabled": 1,
    "city_size": 300,
    "village_size": 50,
    "training_enabled": 1,
    "training_size": 10,
    "bot_vs_bot": 1,
    "combat_radius": 20,
    "aggro_player": 0,
    "fight_player_radius": 20,
    "fight_npc_radius": 8,
    "fight_scan_radius": 8,
    "fight_time_min": 6000,
    "fight_time_max": 6000,
    "rest_time_min": 0,
    "rest_time_max": 1,
    "life_restore_percent": 5,
    "ngami_buff": 1,
    "debuff_enabled": 1,
    "faction_buff": 1,
    "city_buff_percent": 30,
    "chat_chance": 10,
    "drop_money_chance": 0,
    "drop_money_min": 1000,
    "drop_money_max": 10000,
    "outfit_enabled": 1,
    "outfit_chance": 100,
    "guild_chance": 50,
    "trade_send_delay": 8,
    "trade_post_delay": 27,
    "trade_wait_delay": 38,
    "trade_greet_delay": 54,
    "trade_bye_delay": 10,
    "tk_enabled": 1,
    "tk_tong_count": 100,
    "tk_kim_count": 100,
    "tk_level_beginner": 0,
    "tk_level_intermediate": 0,
    "tk_level_advanced": 1,
    "tk_bot_level": 95,
    "tk_revive": 1,
    "tk_spawn_stay_min": 0,
    "tk_spawn_stay_max": 1,
    "tk_combat_radius": 40,
    "arena_enabled": 0,
    "arena_bot_level": 95,
    "arena_bot_hp": 120000,
    "arena_wait_seconds": 30,
    "championship_enabled": 0,
    "championship_bot_level": 95,
    "championship_bot_hp": 120000,
    "championship_fight_seconds": 180,
    "duel_enabled": 1,
    "duel_bot_enabled": 1,
    "duel_bot_level": 95,
    "duel_bot_hp": 120000,
    "duel_wait_seconds": 30,
    "duel_ready_seconds": 15,
    "duel_fight_seconds": 300,
    "league_enabled": 1,
    "league_bot_level": 95,
    "league_bot_hp": 120000,
}


def _read_ini_key(path, section_name, key_name, default=None):
    section = None
    key_lower = key_name.lower()
    try:
        with open(path, "r", encoding="latin-1", newline="") as f:
            for raw in f:
                line = raw.strip()
                if line.startswith("[") and "]" in line:
                    section = line[1:line.find("]")].strip().lower()
                    continue
                if section == section_name.lower() and "=" in line and not line.startswith((";", "#")):
                    key, value = line.split("=", 1)
                    if key.strip().lower() == key_lower:
                        return value.strip()
    except FileNotFoundError:
        pass
    return default


def _write_ini_key(path, section_name, key_name, value):
    value = str(value)
    section_lower = section_name.lower()
    key_lower = key_name.lower()
    with open(path, "r", encoding="latin-1", newline="") as f:
        lines = f.readlines()
    section_start = None
    section_end = len(lines)
    for idx, raw in enumerate(lines):
        line = raw.strip()
        if line.startswith("[") and "]" in line:
            current = line[1:line.find("]")].strip().lower()
            if current == section_lower:
                section_start = idx
                section_end = len(lines)
            elif section_start is not None:
                section_end = idx
                break
    if section_start is None:
        if lines and not lines[-1].endswith(("\n", "\r")):
            lines[-1] += "\n"
        lines.extend([f"[{section_name}]\n", f"{key_name}={value}\n"])
    else:
        replaced = False
        for idx in range(section_start + 1, section_end):
            line = lines[idx].strip()
            if not line or line.startswith((";", "#")) or "=" not in line:
                continue
            key, _old_value = line.split("=", 1)
            if key.strip().lower() == key_lower:
                newline = "\r\n" if lines[idx].endswith("\r\n") else "\n"
                lines[idx] = f"{key_name}={value}" + newline
                replaced = True
                break
        if not replaced:
            lines.insert(section_end, f"{key_name}={value}\n")
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="latin-1", newline="") as f:
        f.writelines(lines)
    os.replace(tmp, path)


def _get_exp_rate_raw():
    raw = _read_ini_key(GAMESETTING_PATH, "ServerConfig", "ExpRate", "100")
    try:
        return int(raw)
    except (TypeError, ValueError):
        return 100


def _exp_multiplier_from_raw(raw):
    return raw / 100.0


def _set_exp_rate_raw(raw):
    raw = int(raw)
    if raw < EXP_RATE_MIN or raw > EXP_RATE_MAX:
        raise ValueError(f"Giá trị ExpRate phải từ {EXP_RATE_MIN} đến {EXP_RATE_MAX}")
    stamp = datetime.now().strftime(".bak_exprate_%Y%m%d_%H%M%S")
    backup_path = GAMESETTING_PATH + stamp
    shutil.copy2(GAMESETTING_PATH, backup_path)
    _write_ini_key(GAMESETTING_PATH, "ServerConfig", "ExpRate", raw)
    return backup_path


def _read_npc_template():
    with open(NPC_TEMPLATE_PATH, "r", encoding="latin-1", newline="") as f:
        lines = f.readlines()
    if not lines:
        raise ValueError("Bảng settings/npcs.txt đang trống")
    header = lines[0].rstrip("\r\n").split("\t")
    required = ("Kind", "Treasure", "DropRateFile", "ReviveFrame")
    missing = [name for name in required if name not in header]
    if missing:
        raise ValueError(f"Bảng NPC thiếu cột: {', '.join(missing)}")
    return lines, {name: header.index(name) for name in required}


def _normal_monster_template_ids(lines, columns):
    candidates = []
    for template_id, raw in enumerate(lines[1:], 1):
        fields = raw.rstrip("\r\n").split("\t")
        if len(fields) <= max(columns.values()):
            continue
        if fields[columns["Kind"]].strip() != "0":
            continue
        try:
            treasure = int(fields[columns["Treasure"]].strip() or "0")
            revive_ticks = int(fields[columns["ReviveFrame"]].strip() or "0")
        except ValueError:
            continue
        if not 1 <= treasure <= 4:
            continue
        drop_file = fields[columns["DropRateFile"]].strip().lower().replace("/", "\\")
        is_normal_drop = (
            drop_file.startswith("\\settings\\item\\")
            or drop_file.startswith("\\settings\\droprate\\npcdroprate")
        )
        if not is_normal_drop or "boss" in drop_file or "event" in drop_file:
            continue
        candidates.append((template_id, revive_ticks))
    if not candidates:
        return []
    # Server JX phổ biến dùng 36 tick cho quái thường, không phải 0. Chọn nhịp
    # xuất hiện nhiều nhất trong nhóm bảng rơi luyện công để tránh đụng các mẫu
    # hiếm/boss có thời gian hồi sinh dài, nhưng vẫn tương thích server khác.
    counts = Counter(ticks for _template_id, ticks in candidates)
    normal_ticks = min(counts, key=lambda ticks: (-counts[ticks], ticks))
    return [template_id for template_id, ticks in candidates if ticks == normal_ticks]


def _write_monster_respawn_state(state):
    directory = os.path.dirname(MONSTER_RESPAWN_STATE_PATH)
    os.makedirs(directory, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".monster_respawn_", suffix=".json", dir=directory)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as f:
            json.dump(state, f, ensure_ascii=True, indent=2, sort_keys=True)
            f.write("\n")
        os.replace(tmp, MONSTER_RESPAWN_STATE_PATH)
    except Exception:
        try:
            os.unlink(tmp)
        except FileNotFoundError:
            pass
        raise


def _read_monster_respawn_state():
    lines, columns = _read_npc_template()
    source_server = os.path.realpath(ACTIVE_SERVER_PATH)
    try:
        with open(MONSTER_RESPAWN_STATE_PATH, "r", encoding="utf-8") as f:
            state = json.load(f)
    except (FileNotFoundError, ValueError, TypeError):
        state = {}
    template_ids = state.get("template_ids")
    state_is_current = (
        state.get("version") == 2
        and state.get("source_server") == source_server
        and isinstance(template_ids, list)
        and all(isinstance(value, int) and 1 <= value < len(lines) for value in template_ids)
    )
    if not state_is_current or not template_ids:
        template_ids = _normal_monster_template_ids(lines, columns)
        state = {
            "version": 2,
            "created_at": datetime.now().isoformat(timespec="seconds"),
            "source_server": source_server,
            "template_ids": template_ids,
        }
        _write_monster_respawn_state(state)
    if not template_ids:
        return {
            "available": False,
            "seconds": 0,
            "seconds_values": [],
            "uniform": True,
            "templates": 0,
        }
    values = []
    revive_col = columns["ReviveFrame"]
    for template_id in template_ids:
        if not isinstance(template_id, int) or template_id < 1 or template_id >= len(lines):
            raise ValueError("ID quái thường trong cấu hình hồi sinh không hợp lệ")
        fields = lines[template_id].rstrip("\r\n").split("\t")
        try:
            ticks = int(fields[revive_col].strip() or "0")
        except (IndexError, ValueError):
            raise ValueError(f"ReviveFrame của NPC mẫu {template_id} không hợp lệ")
        values.append(ticks / MONSTER_RESPAWN_TICKS_PER_SECOND)
    rounded_values = sorted({round(value, 4) for value in values})
    return {
        "available": True,
        "seconds": values[0] if len(rounded_values) == 1 else min(values),
        "seconds_values": rounded_values,
        "uniform": len(rounded_values) == 1,
        "templates": len(template_ids),
    }


def _set_monster_respawn_seconds(seconds):
    seconds = float(seconds)
    if seconds < MONSTER_RESPAWN_SECONDS_MIN or seconds > MONSTER_RESPAWN_SECONDS_MAX:
        raise ValueError(
            f"Thời gian hồi sinh phải từ {MONSTER_RESPAWN_SECONDS_MIN} đến "
            f"{MONSTER_RESPAWN_SECONDS_MAX} giây"
        )
    ticks = int(round(seconds * MONSTER_RESPAWN_TICKS_PER_SECOND))
    lines, columns = _read_npc_template()
    current = _read_monster_respawn_state()
    if not current.get("available"):
        raise ValueError("Không tìm thấy mẫu quái thường phù hợp trong settings/npcs.txt")
    with open(MONSTER_RESPAWN_STATE_PATH, "r", encoding="utf-8") as f:
        state = json.load(f)
    template_ids = state.get("template_ids", [])
    revive_col = columns["ReviveFrame"]
    for template_id in template_ids:
        raw = lines[template_id]
        newline = "\r\n" if raw.endswith("\r\n") else "\n" if raw.endswith("\n") else ""
        fields = raw.rstrip("\r\n").split("\t")
        if len(fields) <= revive_col:
            raise ValueError(f"Dòng NPC mẫu {template_id} bị thiếu cột ReviveFrame")
        fields[revive_col] = str(ticks)
        lines[template_id] = "\t".join(fields) + newline
    directory = os.path.dirname(NPC_TEMPLATE_PATH)
    fd, tmp = tempfile.mkstemp(prefix=".npcs_respawn_", suffix=".txt", dir=directory)
    try:
        with os.fdopen(fd, "w", encoding="latin-1", newline="") as f:
            f.writelines(lines)
        os.chmod(tmp, os.stat(NPC_TEMPLATE_PATH).st_mode)
        os.replace(tmp, NPC_TEMPLATE_PATH)
    except Exception:
        try:
            os.unlink(tmp)
        except FileNotFoundError:
            pass
        raise
    state["seconds"] = ticks / MONSTER_RESPAWN_TICKS_PER_SECOND
    state["updated_at"] = datetime.now().isoformat(timespec="seconds")
    _write_monster_respawn_state(state)
    return {"seconds": ticks / MONSTER_RESPAWN_TICKS_PER_SECOND, "templates": len(template_ids)}


def _drop_rate_path(filename):
    if filename not in DROP_RATE_FILES:
        raise ValueError("Bảng rơi đồ không hợp lệ")
    return os.path.join(DROP_RATE_ROOT, filename)


def _parse_drop_rate_file(path):
    with open(path, "r", encoding="latin-1", newline="") as f:
        lines = f.readlines()
    sections = {}
    current = None
    for index, raw in enumerate(lines):
        line = raw.strip()
        match = re.fullmatch(r"\[([^\]]+)\]", line)
        if match:
            current = match.group(1).strip()
            sections[current] = {"header": index, "values": {}}
            continue
        if current is None or not line or line.startswith((";", "#")) or "=" not in line:
            continue
        key, value = line.split("=", 1)
        sections[current]["values"][key.strip().lower()] = (index, value.strip())
    return lines, sections


def _drop_rate_baseline_from_file(filename):
    _lines, sections = _parse_drop_rate_file(_drop_rate_path(filename))
    main = sections.get("Main")
    if not main:
        raise ValueError(f"{filename} thiếu phần Main")
    try:
        rand_range = int(main["values"]["randrange"][1])
        magic_rate = int(main["values"]["magicrate"][1])
    except (KeyError, TypeError, ValueError):
        raise ValueError(f"{filename} có cấu hình Main không hợp lệ")
    equipment = {}
    for section_name, section in sections.items():
        values = section["values"]
        if values.get("genre", (None, None))[1] != "0":
            continue
        try:
            equipment[section_name] = int(values["randrate"][1])
        except (KeyError, TypeError, ValueError):
            raise ValueError(f"{filename} có RandRate trang bị không hợp lệ")
    if not equipment:
        raise ValueError(f"{filename} không có mục trang bị")
    return {
        "rand_range": rand_range,
        "equipment_rates": equipment,
    }, magic_rate


def _build_drop_rate_baseline():
    files = {}
    magic_rates = set()
    for filename in DROP_RATE_FILES:
        baseline, magic_rate = _drop_rate_baseline_from_file(filename)
        files[filename] = baseline
        magic_rates.add(magic_rate)
    first = files[DROP_RATE_FILES[0]]
    drop_percent = (
        sum(first["equipment_rates"].values()) * 100.0 / first["rand_range"]
    )
    return {
        "version": 3,
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "drop_percent": round(drop_percent, 4),
        "magic_rate": min(magic_rates),
        "magic_lines": 1,
        "files": files,
    }


def _write_drop_rate_state(state):
    directory = os.path.dirname(DROP_RATE_STATE_PATH)
    os.makedirs(directory, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".drop_rate_", suffix=".json", dir=directory)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as f:
            json.dump(state, f, ensure_ascii=True, indent=2, sort_keys=True)
            f.write("\n")
        os.replace(tmp, DROP_RATE_STATE_PATH)
    except Exception:
        try:
            os.unlink(tmp)
        except FileNotFoundError:
            pass
        raise


def _read_drop_rate_state():
    try:
        with open(DROP_RATE_STATE_PATH, "r", encoding="utf-8") as f:
            state = json.load(f)
    except FileNotFoundError:
        state = _build_drop_rate_baseline()
        _write_drop_rate_state(state)
    if state.get("version") == 1:
        old_files = state.get("files", {})
        files = {}
        for filename in DROP_RATE_FILES:
            basename = os.path.basename(filename)
            if basename.startswith("npcdroprate") and basename != "npcdroprate.ini":
                baseline = old_files.get(basename)
                if not baseline:
                    raise ValueError(f"Thiếu dữ liệu gốc của {basename}")
            else:
                baseline, _magic_rate = _drop_rate_baseline_from_file(filename)
            files[filename] = baseline
        first = files[DROP_RATE_FILES[0]]
        old_multiplier = float(state.get("multiplier", 1))
        state = {
            "version": 2,
            "created_at": state.get("created_at", datetime.now().isoformat(timespec="seconds")),
            "migrated_at": datetime.now().isoformat(timespec="seconds"),
            "drop_percent": round(
                sum(first["equipment_rates"].values())
                * old_multiplier
                * 100.0
                / first["rand_range"],
                4,
            ),
            "magic_rate": int(state.get("magic_rate", 1)),
            "files": files,
        }
        _write_drop_rate_state(state)
    if state.get("version") == 2:
        magic_lines = set()
        for filename in DROP_RATE_FILES:
            _lines, sections = _parse_drop_rate_file(_drop_rate_path(filename))
            main_values = sections.get("Main", {}).get("values", {})
            min_lines = int(main_values.get("minsocket", (None, "1"))[1])
            max_lines = int(main_values.get("maxsocket", (None, "1"))[1])
            magic_lines.add(min(min_lines, max_lines))
        state["version"] = 3
        state["magic_lines"] = min(magic_lines)
        state["migrated_magic_lines_at"] = datetime.now().isoformat(timespec="seconds")
        _write_drop_rate_state(state)
    if state.get("version") != 3 or set(state.get("files", {})) != set(DROP_RATE_FILES):
        raise ValueError("Dữ liệu gốc của cấu hình rơi đồ không hợp lệ")
    return state


def _replace_ini_value(lines, index, key, value):
    newline = "\r\n" if lines[index].endswith("\r\n") else "\n"
    lines[index] = f"{key}={value}{newline}"


def _equipment_rates_for_percent(baseline, drop_percent):
    base_rates = {
        section: int(rate)
        for section, rate in baseline["equipment_rates"].items()
    }
    base_total = sum(base_rates.values())
    target_total = int(round(int(baseline["rand_range"]) * drop_percent / 100.0))
    exact = {
        section: target_total * rate / base_total
        for section, rate in base_rates.items()
    }
    rates = {section: int(value) for section, value in exact.items()}
    remainder = target_total - sum(rates.values())
    order = sorted(
        rates,
        key=lambda section: (exact[section] - rates[section], section),
        reverse=True,
    )
    for section in order[:remainder]:
        rates[section] += 1
    return rates


def _render_drop_rate_file(
    filename, baseline, drop_percent, money_rate=None, money_scale=None,
    coin_percent=0.0, special_drop_percents=None,
):
    path = _drop_rate_path(filename)
    lines, sections = _parse_drop_rate_file(path)
    main = sections.get("Main")
    if not main or "magicrate" not in main["values"]:
        raise ValueError(f"{filename} thiếu MagicRate")
    magic_index = main["values"]["magicrate"][0]
    _replace_ini_value(lines, magic_index, "MagicRate", 1)
    if money_rate is not None:
        _replace_main_drop_value(lines, sections, "MoneyRate", money_rate)
    if money_scale is not None:
        _replace_main_drop_value(lines, sections, "MoneyScale", money_scale)

    adjusted_rates = _equipment_rates_for_percent(baseline, drop_percent)
    for section_name, rate in adjusted_rates.items():
        section = sections.get(section_name)
        if not section or "randrate" not in section["values"]:
            raise ValueError(f"{filename} thiếu mục trang bị [{section_name}]")
        rate_index = section["values"]["randrate"][0]
        _replace_ini_value(lines, rate_index, "RandRate", rate)
    if special_drop_percents is not None:
        for key in special_drop_percents:
            genre, detail, particular, label = DROP_SPECIAL_ITEMS[key]
            match = _special_drop_section(sections, genre, detail, particular)
            if not match:
                raise ValueError(f"{filename} thiếu mục {label}")
            _section_name, section = match
            rate_index = section["values"]["randrate"][0]
            # Hai mục này được quay qua bảng độc lập để không tranh lượt với trang bị.
            _replace_ini_value(lines, rate_index, "RandRate", 0)
    if sum(adjusted_rates.values()) > int(baseline["rand_range"]):
        raise ValueError(f"Tỷ lệ của {filename} vượt giới hạn")
    return "".join(lines)


def _write_file_preserving_metadata(path, content):
    stat_result = os.stat(path)
    directory = os.path.dirname(path)
    fd, tmp = tempfile.mkstemp(prefix=".drop_rate_", suffix=".ini", dir=directory)
    try:
        with os.fdopen(fd, "w", encoding="latin-1", newline="") as f:
            f.write(content)
        os.chmod(tmp, stat_result.st_mode)
        try:
            os.chown(tmp, stat_result.st_uid, stat_result.st_gid)
        except PermissionError:
            pass
        os.replace(tmp, path)
    except Exception:
        try:
            os.unlink(tmp)
        except FileNotFoundError:
            pass
        raise


def _read_event_flags():
    with open(EVENT_CONFIG_PATH, "r", encoding="latin-1", newline="") as f:
        content = f.read()
    values = {}
    for name, _label, _description in EVENT_FLAGS:
        matches = re.findall(
            rf"(?m)^\s*{re.escape(name)}\s*=\s*([01])(?=\s|$)", content
        )
        if len(matches) != 1:
            raise ValueError(
                f"Cấu hình {name} phải có đúng một dòng, hiện tìm thấy {len(matches)}"
            )
        values[name] = int(matches[0])
    month_matches = re.findall(
        r"(?m)^\s*EventThangLuaChon\s*=\s*(\d+)(?=\s|$)", content
    )
    if len(month_matches) != 1:
        raise ValueError(
            "Cấu hình EventThangLuaChon phải có đúng một dòng, "
            f"hiện tìm thấy {len(month_matches)}"
        )
    selected_month = int(month_matches[0])
    if not 0 <= selected_month <= 12:
        raise ValueError("EventThangLuaChon phải từ 0 đến 12")
    return values, selected_month


def _write_event_flags(values, selected_month):
    selected_month = int(selected_month)
    if not 0 <= selected_month <= 12:
        raise ValueError("Tháng event phải từ 0 đến 12")
    with open(EVENT_CONFIG_PATH, "r", encoding="latin-1", newline="") as f:
        content = f.read()
    for name, _label, _description in EVENT_FLAGS:
        value = values[name]
        pattern = re.compile(
            rf"(?m)^(\s*{re.escape(name)}\s*=\s*)[01](?=\s|$)"
        )
        content, count = pattern.subn(lambda match: match.group(1) + str(value), content)
        if count != 1:
            raise ValueError(
                f"Không thể cập nhật an toàn {name}: tìm thấy {count} dòng"
            )
    month_pattern = re.compile(
        r"(?m)^(\s*EventThangLuaChon\s*=\s*)\d+(?=\s|$)"
    )
    content, count = month_pattern.subn(
        lambda match: match.group(1) + str(selected_month), content
    )
    if count != 1:
        raise ValueError(
            f"Không thể cập nhật an toàn EventThangLuaChon: tìm thấy {count} dòng"
        )
    _write_file_preserving_metadata(EVENT_CONFIG_PATH, content)


def _event_rate_fields():
    rows = []
    for month, spec in enumerate(EVENT_RATE_SPECS, 1):
        fields = []
        drop_path = os.path.join(EVENT_RATE_ROOT, "activitysys", "config", f"20{month:02d}", "config.lua")
        for item_id, label in spec.get("drop", []):
            fields.append({"key": f"m{month}_drop_{item_id}", "kind": "drop", "path": drop_path,
                           "item_id": item_id, "label": label, "group": "Tỷ trọng rơi", "max": 10000})
        for item_id, label, occurrences in spec.get("drop_special", []):
            suffix = "_".join(str(i) for i in occurrences)
            fields.append({"key": f"m{month}_drop_{item_id}_{suffix}", "kind": "drop", "path": drop_path,
                           "item_id": item_id, "occurrences": occurrences, "label": label,
                           "group": "Tỷ trọng rơi", "max": 10000})
        if spec.get("box"):
            rel_path, labels = spec["box"]
            for index, label in enumerate(labels, 1):
                fields.append({"key": f"m{month}_box_{index}", "kind": "box",
                               "path": os.path.join(EVENT_RATE_ROOT, rel_path), "index": index,
                               "label": label, "group": "Tỷ lệ mở hộp (%)", "max": 100,
                               "sum_group": f"m{month}_box", "sum_required": 100})
        if spec.get("weights"):
            rel_path, items = spec["weights"]
            for item_id, label in items:
                fields.append({"key": f"m{month}_weight_{item_id}", "kind": "weight",
                               "path": os.path.join(EVENT_RATE_ROOT, rel_path), "item_id": item_id,
                               "label": label, "group": "Tỷ trọng mở hộp (tổng 10.000)", "max": 10000,
                               "sum_group": f"m{month}_weight", "sum_required": 10000})
        for variable, label in spec.get("compose", []):
            fields.append({"key": f"m{month}_compose_{variable}", "kind": "compose",
                           "path": EVENT_CONFIG_PATH, "variable": variable, "label": label,
                           "group": "Tỷ lệ hợp thành (%)", "max": 100})
        rows.append({"month": month, "name": MONTHLY_EVENTS[month - 1], "fields": fields})
    return rows


def _drop_rate_line_pattern(item_id):
    return re.compile(
        rf"(?m)^.*NpcFunLib:DropSingleItem.*tbProp\s*=\s*\{{\s*6\s*,\s*1\s*,\s*{item_id}\s*,.*$"
    )


def _read_one_event_rate(field, cache):
    content = cache.setdefault(field["path"], open(field["path"], "r", encoding="latin-1", newline="").read())
    if field["kind"] == "compose":
        matches = re.findall(rf"(?m)^\s*{re.escape(field['variable'])}\s*=\s*\{{\s*(\d+)\s*\}}", content)
    elif field["kind"] == "box":
        matches = re.findall(rf"(?m)^\s*\[{field['index']}\]\s*=.*?\bnRate\s*=\s*(\d+)", content)
    elif field["kind"] == "weight":
        matches = re.findall(rf"(?m)^\s*\{{[^\r\n]*,\s*{field['item_id']}\s*,\s*(\d+)\s*\}}", content)
    else:
        lines = _drop_rate_line_pattern(field["item_id"]).findall(content)
        all_values = []
        for line in lines:
            match = re.search(r'\},\s*1\s*,\s*"(\d+)"', line)
            if match:
                all_values.append(match.group(1))
        selected = field.get("occurrences")
        matches = [all_values[i] for i in selected if i < len(all_values)] if selected is not None else all_values
    if not matches:
        raise ValueError(f"Không tìm thấy cấu hình: {field['label']}")
    if len(set(matches)) != 1:
        raise ValueError(f"Các nguồn của {field['label']} đang có giá trị không đồng nhất: {', '.join(matches)}")
    return int(matches[0])


def _read_event_rates():
    cache = {}
    rows = _event_rate_fields()
    for row in rows:
        for field in row["fields"]:
            field["value"] = _read_one_event_rate(field, cache)
    return rows


def _replace_one_event_rate(content, field, value):
    if field["kind"] == "compose":
        pattern = re.compile(rf"(?m)^(\s*{re.escape(field['variable'])}\s*=\s*\{{\s*)\d+(\s*\}})")
        content, count = pattern.subn(lambda m: m.group(1) + str(value) + m.group(2), content)
    elif field["kind"] == "box":
        pattern = re.compile(rf"(?m)^(\s*\[{field['index']}\]\s*=.*?\bnRate\s*=\s*)\d+")
        content, count = pattern.subn(lambda m: m.group(1) + str(value), content)
    elif field["kind"] == "weight":
        pattern = re.compile(rf"(?m)^(\s*\{{[^\r\n]*,\s*{field['item_id']}\s*,\s*)\d+(\s*\}})")
        content, count = pattern.subn(lambda m: m.group(1) + str(value) + m.group(2), content)
    else:
        line_pattern = _drop_rate_line_pattern(field["item_id"])
        selected = field.get("occurrences")
        selected_set = set(selected) if selected is not None else None
        seen = 0
        changed = 0
        def replace_line(match):
            nonlocal seen, changed
            line = match.group(0)
            use = selected_set is None or seen in selected_set
            seen += 1
            if not use:
                return line
            new_line, n = re.subn(r'(\},\s*1\s*,\s*")\d+("\s*\})', lambda m: m.group(1) + str(value) + m.group(2), line, count=1)
            changed += n
            return new_line
        content = line_pattern.sub(replace_line, content)
        count = changed
        expected = len(selected) if selected is not None else seen
        if count != expected:
            raise ValueError(f"Không thể cập nhật an toàn {field['label']}: cần {expected}, sửa được {count}")
        return content
    if count != 1:
        raise ValueError(f"Không thể cập nhật an toàn {field['label']}: tìm thấy {count} vị trí")
    return content


def _write_event_rates(form):
    rows = _event_rate_fields()
    values = {}
    sums = {}
    requirements = {}
    for row in rows:
        for field in row["fields"]:
            raw = (form.get(field["key"]) or "").strip()
            if not re.fullmatch(r"\d{1,5}", raw):
                raise ValueError(f"{field['label']}: phải là số nguyên")
            value = int(raw)
            if not 0 <= value <= field["max"]:
                raise ValueError(f"{field['label']}: phải từ 0 đến {field['max']}")
            values[field["key"]] = value
            if field.get("sum_group"):
                group = field["sum_group"]
                sums[group] = sums.get(group, 0) + value
                requirements[group] = field["sum_required"]
    for group, required in requirements.items():
        if sums.get(group) != required:
            raise ValueError(f"Nhóm {group} phải có tổng đúng {required}, hiện là {sums.get(group, 0)}")
    contents = {}
    for row in rows:
        for field in row["fields"]:
            path = field["path"]
            if path not in contents:
                with open(path, "r", encoding="latin-1", newline="") as f:
                    contents[path] = f.read()
            contents[path] = _replace_one_event_rate(contents[path], field, values[field["key"]])
    for path, content in contents.items():
        _write_file_preserving_metadata(path, content)
    return len(values), len(contents)


def _read_da_tau_daily_limit():
    with open(DA_TAU_CONFIG_PATH, "r", encoding="latin-1", newline="") as f:
        content = f.read()
    match = re.search(
        r"(?m)^\s*So_Lan_Da_Tau_Trong_Ngay\s*=\s*(\d+)\b", content
    )
    if not match:
        raise ValueError("Không tìm thấy So_Lan_Da_Tau_Trong_Ngay trong cấu hình Dã Tẩu")
    return int(match.group(1))


def _set_da_tau_daily_limit(limit):
    limit = int(limit)
    if not DA_TAU_DAILY_LIMIT_MIN <= limit <= DA_TAU_DAILY_LIMIT_MAX:
        raise ValueError(
            f"Số nhiệm vụ Dã Tẩu phải từ {DA_TAU_DAILY_LIMIT_MIN} "
            f"đến {DA_TAU_DAILY_LIMIT_MAX}"
        )
    with open(DA_TAU_CONFIG_PATH, "r", encoding="latin-1", newline="") as f:
        content = f.read()
    pattern = re.compile(
        r"(?m)^(\s*So_Lan_Da_Tau_Trong_Ngay\s*=\s*)\d+(\s*--[^\r\n]*)?$"
    )
    updated, count = pattern.subn(
        lambda match: f"{match.group(1)}{limit}{match.group(2) or ''}", content
    )
    if count != 1:
        raise ValueError(
            "Cấu hình Dã Tẩu không hợp lệ: cần đúng một biến So_Lan_Da_Tau_Trong_Ngay"
        )
    stamp = datetime.now().strftime(".bak_web_%Y%m%d_%H%M%S")
    shutil.copy2(DA_TAU_CONFIG_PATH, DA_TAU_CONFIG_PATH + stamp)
    _write_file_preserving_metadata(DA_TAU_CONFIG_PATH, updated)
    return limit


def _replace_main_drop_value(lines, sections, key, value):
    main = sections.get("Main")
    if not main or key.lower() not in main["values"]:
        raise ValueError(f"Bảng rơi thiếu {key}")
    index = main["values"][key.lower()][0]
    _replace_ini_value(lines, index, key, value)


def _special_drop_section(sections, genre, detail, particular):
    matches = []
    for section_name, section in sections.items():
        values = section["values"]
        try:
            identity = (
                int(values["genre"][1]),
                int(values["detail"][1]),
                int(values["particular"][1]),
            )
        except (KeyError, TypeError, ValueError):
            continue
        if identity == (genre, detail, particular):
            matches.append((section_name, section))
    if len(matches) != 1:
        return None
    return matches[0]


def _global_special_drop_state():
    state = {}
    for key, (genre, detail, particular, label) in DROP_SPECIAL_ITEMS.items():
        path = DROP_SPECIAL_RATE_PATHS[key]
        percent_values = []
        if os.path.isfile(path):
            _lines, sections = _parse_drop_rate_file(path)
            main = sections.get("Main", {}).get("values", {})
            try:
                rand_range = int(main["randrange"][1])
            except (KeyError, TypeError, ValueError):
                raise ValueError(f"Bảng rơi độc lập {label} có RandRange không hợp lệ")
            match = _special_drop_section(sections, genre, detail, particular)
            if not match:
                raise ValueError(f"Bảng rơi độc lập thiếu mục {label}")
            _section_name, section = match
            try:
                rate = int(section["values"]["randrate"][1])
            except (KeyError, TypeError, ValueError):
                raise ValueError(f"Bảng rơi độc lập có RandRate {label} không hợp lệ")
            percent_values = [round(rate * 100.0 / rand_range, 4)]
        else:
            # Server nguyên bản có thể chưa có hai bảng dành cho
            # special_drop_hook.so. Khi đó đọc tỷ lệ đang nằm trong các bảng
            # quái thường để trang vẫn mở được và không tự thay đổi server.
            for filename in DROP_RATE_FILES:
                _lines, sections = _parse_drop_rate_file(_drop_rate_path(filename))
                main = sections.get("Main", {}).get("values", {})
                match = _special_drop_section(sections, genre, detail, particular)
                try:
                    rand_range = int(main["randrange"][1])
                    rate = int(match[1]["values"]["randrate"][1])
                except (KeyError, TypeError, ValueError, IndexError):
                    raise ValueError(f"Bảng rơi quái thường thiếu mục {label}")
                percent_values.append(round(rate * 100.0 / rand_range, 4))
        distinct = sorted(set(percent_values))
        percent = percent_values[0]
        state[key] = {
            "percent": percent,
            "percent_values": distinct,
            "uniform": len(distinct) == 1,
            "independent_file": os.path.isfile(path),
        }
    state["uniform"] = all(item["uniform"] for key, item in state.items() if key != "uniform")
    return state


def _render_special_drop_file(key, percent):
    genre, detail, particular, label = DROP_SPECIAL_ITEMS[key]
    path = DROP_SPECIAL_RATE_PATHS[key]
    if not os.path.isfile(path):
        rand_range = 1000000
        rate = int(round(rand_range * percent / 100.0))
        return (
            "[Main]\n"
            "Count=1\n"
            f"RandRange={rand_range}\n"
            "MagicRate=1\nMoneyRate=0\nMoneyScale=0\n"
            "MinItemLevel=1\nMinItemLevelScale=20\n"
            "MaxItemLevel=10\nMaxItemLevelScale=10\n\n"
            "[1]\n"
            f"Genre={genre}\nDetail={detail}\nParticular={particular}\n"
            f"RandRate={rate}\nMinItemLevel=1\nMaxItemLevel=1\n"
        )
    lines, sections = _parse_drop_rate_file(path)
    main = sections.get("Main", {}).get("values", {})
    try:
        rand_range = int(main["randrange"][1])
    except (KeyError, TypeError, ValueError):
        raise ValueError(f"Bảng rơi độc lập {label} có RandRange không hợp lệ")
    match = _special_drop_section(sections, genre, detail, particular)
    if not match:
        raise ValueError(f"Bảng rơi độc lập thiếu mục {label}")
    _section_name, section = match
    rate_index = section["values"]["randrate"][0]
    rate = int(round(rand_range * percent / 100.0))
    _replace_ini_value(lines, rate_index, "RandRate", rate)
    return "".join(lines)


def _write_special_drop_file(path, content):
    if os.path.isfile(path):
        _write_file_preserving_metadata(path, content)
        return
    directory = os.path.dirname(path)
    os.makedirs(directory, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=".special_drop_", suffix=".ini", dir=directory)
    try:
        with os.fdopen(fd, "w", encoding="latin-1", newline="") as handle:
            handle.write(content)
        os.chmod(temporary, 0o644)
        os.replace(temporary, path)
    except Exception:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass
        raise


def _global_drop_money_state():
    values = []
    for filename in DROP_RATE_FILES[:11]:
        _lines, sections = _parse_drop_rate_file(_drop_rate_path(filename))
        main = sections.get("Main", {}).get("values", {})
        values.append((
            int(main["moneyrate"][1]),
            int(main["moneyscale"][1]),
        ))
    rates = sorted(set(rate for rate, _scale in values))
    scales = sorted(set(scale / 100.0 for _rate, scale in values))
    return {
        "money_rate": values[0][0],
        "money_scale": values[0][1] / 100.0,
        "money_rate_values": rates,
        "money_scale_values": scales,
        "uniform": len(rates) == 1 and len(scales) == 1,
    }


def _global_coin_drop_state():
    basis_points = 0
    enabled = None
    try:
        with open(DROP_COIN_CONFIG_PATH, "r", encoding="ascii", errors="ignore") as f:
            text = f.read()
            match = re.search(r"JX_WEB_COIN_DROP_BP\s*=\s*(\d+)", text)
            enabled_match = re.search(r"JX_WEB_COIN_DROP_ENABLED\s*=\s*([01])", text)
        if match:
            basis_points = int(match.group(1))
        if enabled_match:
            enabled = enabled_match.group(1) == "1"
    except FileNotFoundError:
        pass
    if enabled is None:
        enabled = basis_points > 0
    percent = basis_points / 100.0
    return {
        "enabled": enabled,
        "percent": percent,
        "percent_values": [percent],
        "uniform": True,
    }


def _write_coin_drop_config(coin_percent, coin_enabled=True):
    basis_points = int(round(float(coin_percent) * 100.0))
    content = (
        "-- Webpanel: independent normal-monster coin drop chance (1/10000)\n"
        f"JX_WEB_COIN_DROP_ENABLED = {1 if coin_enabled else 0}\n"
        f"JX_WEB_COIN_DROP_BP = {basis_points}\n"
    )
    directory = os.path.dirname(DROP_COIN_CONFIG_PATH)
    os.makedirs(directory, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".coin_drop_", suffix=".lua", dir=directory)
    try:
        with os.fdopen(fd, "w", encoding="ascii", newline="\n") as f:
            f.write(content)
        os.chmod(tmp, 0o644)
        os.replace(tmp, DROP_COIN_CONFIG_PATH)
    except Exception:
        try:
            os.unlink(tmp)
        except FileNotFoundError:
            pass
        raise


def _set_drop_rate(
    drop_percent, money_rate, money_scale, coin_percent=0.0, coin_enabled=True,
    mystery_map_percent=0.0, mystery_record_percent=0.0,
    ground_item_lifetime_seconds=None,
):
    drop_percent = float(drop_percent)
    money_rate = int(money_rate)
    money_scale = float(money_scale)
    coin_percent = float(coin_percent)
    mystery_map_percent = float(mystery_map_percent)
    mystery_record_percent = float(mystery_record_percent)
    if drop_percent < DROP_PERCENT_MIN or drop_percent > DROP_PERCENT_MAX:
        raise ValueError("Tỷ lệ rơi trang bị phải từ 0% đến 100%")
    if not DROP_MONEY_RATE_MIN <= money_rate <= DROP_MONEY_RATE_MAX:
        raise ValueError("Tỷ lệ quái rơi Ngân lượng phải từ 0% đến 100%")
    if not DROP_MONEY_MULTIPLIER_MIN <= money_scale <= DROP_MONEY_MULTIPLIER_MAX:
        raise ValueError("Hệ số Ngân lượng phải từ x0 đến x100")
    if not DROP_COIN_PERCENT_MIN <= coin_percent <= DROP_COIN_PERCENT_MAX:
        raise ValueError("Tỷ lệ rơi Tiền đồng phải từ 0% đến 100%")
    for label, percent in (
        ("Mật Đồ Thần Bí", mystery_map_percent),
        ("Thần Bí Đồ Chí", mystery_record_percent),
    ):
        if not DROP_SPECIAL_PERCENT_MIN <= percent <= DROP_SPECIAL_PERCENT_MAX:
            raise ValueError(f"Tỷ lệ rơi {label} phải từ 0% đến 100%")

    money_scale_raw = int(round(money_scale * 100))
    special_drop_percents = {
        "mystery_map": mystery_map_percent,
        "mystery_record": mystery_record_percent,
    }
    state = _read_drop_rate_state()
    rendered = {}
    for filename in DROP_RATE_FILES:
        rendered[filename] = _render_drop_rate_file(
            filename, state["files"][filename], drop_percent,
            money_rate, money_scale_raw, coin_percent, special_drop_percents,
        )
    rendered_special = {
        key: _render_special_drop_file(key, percent)
        for key, percent in special_drop_percents.items()
    }
    rendered_ground_lifetime = {}
    if ground_item_lifetime_seconds is not None:
        lifetime_seconds = float(ground_item_lifetime_seconds)
        if not GROUND_ITEM_LIFETIME_MIN <= lifetime_seconds <= GROUND_ITEM_LIFETIME_MAX:
            raise ValueError(
                f"Thời gian tồn tại phải từ {GROUND_ITEM_LIFETIME_MIN:g} đến "
                f"{GROUND_ITEM_LIFETIME_MAX:g} giây"
            )
        lifetime_ticks = int(round(lifetime_seconds * GROUND_ITEM_TICKS_PER_SECOND))
        for path in GROUND_ITEM_LIFETIME_PATHS:
            content, _eligible, _changed = _render_ground_item_lifetime_file(
                path, lifetime_ticks
            )
            rendered_ground_lifetime[path] = content
    stamp = datetime.now().strftime(".bak_droprate_%Y%m%d_%H%M%S")
    backups = {}
    created_paths = set()
    try:
        for filename in DROP_RATE_FILES:
            path = _drop_rate_path(filename)
            backup_path = path + stamp
            shutil.copy2(path, backup_path)
            backups[path] = backup_path
        coin_backup_path = DROP_COIN_CONFIG_PATH + stamp
        shutil.copy2(DROP_COIN_CONFIG_PATH, coin_backup_path)
        backups[DROP_COIN_CONFIG_PATH] = coin_backup_path
        for key, path in DROP_SPECIAL_RATE_PATHS.items():
            if os.path.isfile(path):
                backup_path = path + stamp
                shutil.copy2(path, backup_path)
                backups[path] = backup_path
            else:
                created_paths.add(path)
        for path in rendered_ground_lifetime:
            backup_path = path + stamp
            shutil.copy2(path, backup_path)
            backups[path] = backup_path
        for filename, content in rendered.items():
            _write_file_preserving_metadata(_drop_rate_path(filename), content)
        for key, content in rendered_special.items():
            _write_special_drop_file(DROP_SPECIAL_RATE_PATHS[key], content)
        for path, content in rendered_ground_lifetime.items():
            _write_bytes_preserving_metadata(path, content)
        _write_coin_drop_config(coin_percent, coin_enabled)
        state["drop_percent"] = drop_percent
        state["magic_rate"] = 1
        state["updated_at"] = datetime.now().isoformat(timespec="seconds")
        _write_drop_rate_state(state)
    except Exception:
        for path, backup_path in backups.items():
            if os.path.exists(backup_path):
                shutil.copy2(backup_path, path)
        for path in created_paths:
            try:
                os.unlink(path)
            except FileNotFoundError:
                pass
        raise
    return len(rendered)


def _read_simcity_config():
    values = dict(SIMCITY_DEFAULTS)
    values["skills"] = {key: 0 for key, _label, _options in SIMCITY_FACTIONS}
    values["training_maps"] = {
        map_id: values["training_size"] for _level, map_id, _name in SIMCITY_TRAINING_MAPS
    }
    try:
        with open(SIMCITY_CONFIG_PATH, "r", encoding="ascii", errors="ignore") as f:
            text = f.read()
    except FileNotFoundError:
        return values

    scalar_keys = {
        "hp_min": "SIMBOT_HP_MIN",
        "hp_max": "SIMBOT_HP_MAX",
        "attack_speed": "SIMBOT_ATTACK_SPEED",
        "cast_delay": "SIMBOT_CAST_DELAY",
        "normal_cast_delay": "SIMBOT_NORMAL_CAST_DELAY",
        "skill_level": "SIMCITY_SKILL_LEVEL",
        "stall_enabled": "SIMCITY_STALL_ENABLED",
        "stall_city_min": "SIMCITY_STALL_CITY_MIN",
        "stall_city_max": "SIMCITY_STALL_CITY_MAX",
        "stall_village_min": "SIMCITY_STALL_VILLAGE_MIN",
        "stall_village_max": "SIMCITY_STALL_VILLAGE_MAX",
        "stall_datau_min": "SIMCITY_STALL_DATAU_MIN",
        "stall_datau_max": "SIMCITY_STALL_DATAU_MAX",
        "population_enabled": "STARTUP_AUTOADD_THANHTHI",
        "city_size": "THANHTHI_SIZE",
        "village_size": "THON_SIZE",
        "training_enabled": "LUYENCONG_AUTOADD",
        "training_size": "SIMCITY_TRAIN_SIZE",
        "bot_vs_bot": "BOT_VS_BOT",
        "combat_radius": "BOT_COMBAT_RADIUS",
        "aggro_player": "SIMBOT_AGGRO_PLAYER",
        "fight_player_radius": "RADIUS_FIGHT_PLAYER",
        "fight_npc_radius": "RADIUS_FIGHT_NPC",
        "fight_scan_radius": "RADIUS_FIGHT_SCAN",
        "fight_time_min": "SIMCITY_FIGHT_TIME_MIN",
        "fight_time_max": "SIMCITY_FIGHT_TIME_MAX",
        "rest_time_min": "SIMCITY_REST_TIME_MIN",
        "rest_time_max": "SIMCITY_REST_TIME_MAX",
        "life_restore_percent": "LIFE_RESTORE_PERCENT",
        "ngami_buff": "SIMBOT_NGAMI_BUFF",
        "debuff_enabled": "SIMBOT_DEBUFF",
        "faction_buff": "SIMBOT_TRANPHAI",
        "city_buff_percent": "SIMBOT_CITY_BUFF_PCT",
        "chat_chance": "CHANCE_CHAT",
        "drop_money_chance": "CHANCE_DROP_MONEY",
        "drop_money_min": "SIMCITY_DROP_MONEY_MIN",
        "drop_money_max": "SIMCITY_DROP_MONEY_MAX",
        "outfit_enabled": "SIMCITY_OUTFIT_ENABLED",
        "outfit_chance": "SIMCITY_OUTFIT_CHANCE",
        "guild_chance": "SIMCITY_GUILD_CHANCE",
        "trade_send_delay": "SIMCITY_TRADE_SEND_DELAY",
        "trade_post_delay": "SIMCITY_TRADE_POST_DELAY",
        "trade_wait_delay": "SIMCITY_TRADE_WAIT_DELAY",
        "trade_greet_delay": "SIMCITY_TRADE_GREET_DELAY",
        "trade_bye_delay": "SIMCITY_TRADE_BYE_DELAY",
        "tk_enabled": "SIMCITY_TK_ENABLED",
        "tk_tong_count": "SIMCITY_TK_TONG_COUNT",
        "tk_kim_count": "SIMCITY_TK_KIM_COUNT",
        "tk_level_beginner": "SIMCITY_TK_LEVEL_BEGINNER",
        "tk_level_intermediate": "SIMCITY_TK_LEVEL_INTERMEDIATE",
        "tk_level_advanced": "SIMCITY_TK_LEVEL_ADVANCED",
        "tk_bot_level": "SIMCITY_TK_BOT_LEVEL",
        "tk_revive": "SIMCITY_TK_REVIVE",
        "tk_spawn_stay_min": "TONGKIM_SPAWN_MINSTAY",
        "tk_spawn_stay_max": "TONGKIM_SPAWN_MAXSTAY",
        "tk_combat_radius": "SIMCITY_TK_COMBAT_RADIUS",
        "arena_enabled": "SIMCITY_ARENA_ENABLED",
        "arena_bot_level": "SIMCITY_ARENA_BOT_LEVEL",
        "arena_bot_hp": "SIMCITY_ARENA_BOT_HP",
        "arena_wait_seconds": "SIMCITY_ARENA_WAIT_SECONDS",
        "championship_enabled": "SIMCITY_CHAMPIONSHIP_ENABLED",
        "championship_bot_level": "SIMCITY_CHAMPIONSHIP_BOT_LEVEL",
        "championship_bot_hp": "SIMCITY_CHAMPIONSHIP_BOT_HP",
        "championship_fight_seconds": "SIMCITY_CHAMPIONSHIP_FIGHT_SECONDS",
        "duel_enabled": "SIMCITY_DUEL_ENABLED",
        "duel_bot_enabled": "SIMCITY_DUEL_BOT_ENABLED",
        "duel_bot_level": "SIMCITY_DUEL_BOT_LEVEL",
        "duel_bot_hp": "SIMCITY_DUEL_BOT_HP",
        "duel_wait_seconds": "SIMCITY_DUEL_WAIT_SECONDS",
        "duel_ready_seconds": "SIMCITY_DUEL_READY_SECONDS",
        "duel_fight_seconds": "SIMCITY_DUEL_FIGHT_SECONDS",
        "league_enabled": "SIMCITY_LEAGUE_ENABLED",
        "league_bot_level": "SIMCITY_LEAGUE_BOT_LEVEL",
        "league_bot_hp": "SIMCITY_LEAGUE_BOT_HP",
    }
    for field, lua_name in scalar_keys.items():
        match = re.search(rf"(?m)^\s*{lua_name}\s*=\s*(\d+)\s*$", text)
        if match:
            values[field] = int(match.group(1))

    # Runtime SimCity uses these namespaced values.  Read them last so the
    # web form always shows the effective population, while retaining the
    # legacy THANHTHI_SIZE/THON_SIZE fallback for older configuration files.
    runtime_population_keys = {
        "city_size": "SIMCITY_WEB_CITY_SIZE",
        "village_size": "SIMCITY_WEB_VILLAGE_SIZE",
    }
    for field, lua_name in runtime_population_keys.items():
        match = re.search(rf"(?m)^\s*{lua_name}\s*=\s*(\d+)\s*$", text)
        if match:
            values[field] = int(match.group(1))

    values["training_maps"] = {
        map_id: values["training_size"] for _level, map_id, _name in SIMCITY_TRAINING_MAPS
    }
    map_table = re.search(
        r"SIMCITY_TRAIN_SIZE_BY_MAP\s*=\s*\{(.*?)\}", text, re.DOTALL
    )
    if map_table:
        known_map_ids = set(values["training_maps"])
        for map_id_text, count_text in re.findall(
            r"\[(\d+)\]\s*=\s*(\d+)", map_table.group(1)
        ):
            map_id = int(map_id_text)
            if map_id in known_map_ids:
                values["training_maps"][map_id] = int(count_text)

    for key, _label, _options in SIMCITY_FACTIONS:
        match = re.search(rf"(?m)^\s*{key}\s*=\s*(\d+)\s*,?\s*$", text)
        if match:
            values["skills"][key] = int(match.group(1))
    return values


def _sync_simcity_training_to_base_config(values):
    """Embed training-map values in config.lua for JX Include contexts.

    JX caches Include(webconfig.lua) across script packages, although globals
    are package-local.  Consequently the main SimCity package can miss the
    web table completely.  config.lua is always executed by that package.
    """
    begin = "-- BEGIN WEBADMIN TRAINING MAP CONFIG"
    end = "-- END WEBADMIN TRAINING MAP CONFIG"
    with open(SIMCITY_BASE_CONFIG_PATH, "r", encoding="latin-1", newline="") as f:
        content = f.read()
    newline = "\r\n" if "\r\n" in content else "\n"
    lines = [
        begin,
        "-- Generated from the SimCity web form. Do not edit this block manually.",
        f"SIMCITY_TRAIN_SIZE = {values['training_size']}",
        "SIMCITY_TRAIN_SIZE_BY_MAP = {",
    ]
    for _level, map_id, _name in SIMCITY_TRAINING_MAPS:
        lines.append(f"    [{map_id}] = {values['training_maps'][map_id]},")
    lines.extend(["}", "SIMCITY_TRAIN_LEVEL_BY_MAP = {"])
    for map_level, map_id, _name in SIMCITY_TRAINING_MAPS:
        lines.append(f"    [{map_id}] = {map_level},")
    lines.extend([
        "}",
        'if WriteLog then WriteLog("SIMCITY_TRAIN_CONFIG\\tMap224:"..tostring(SIMCITY_TRAIN_SIZE_BY_MAP[224])) end',
        end,
    ])
    block = newline.join(lines)
    pattern = rf"(?ms)^{re.escape(begin)}\r?$.*?^{re.escape(end)}\r?$"
    if re.search(pattern, content):
        rendered = re.sub(pattern, block, content, count=1)
    else:
        rendered = content.rstrip("\r\n") + newline + newline + block + newline
    stamp = datetime.now().strftime(".bak_webtraining_%Y%m%d_%H%M%S")
    shutil.copy2(SIMCITY_BASE_CONFIG_PATH, SIMCITY_BASE_CONFIG_PATH + stamp)
    _write_file_preserving_metadata(SIMCITY_BASE_CONFIG_PATH, rendered)


def _write_simcity_config(values):
    lines = [
        "-- Cau hinh SimCity do webadmin quan ly. Chi dung ky tu ASCII trong file nay.",
        f"SIMBOT_HP_MIN = {values['hp_min']}",
        f"SIMBOT_HP_MAX = {values['hp_max']}",
        f"SIMBOT_ATTACK_SPEED = {values['attack_speed']}",
        f"SIMBOT_CAST_DELAY = {values['cast_delay']}",
        f"SIMBOT_NORMAL_CAST_DELAY = {values['normal_cast_delay']}",
        f"SIMCITY_SKILL_LEVEL = {values['skill_level']}",
        f"SIMCITY_STALL_ENABLED = {values['stall_enabled']}",
        f"SIMCITY_STALL_CITY_MIN = {values['stall_city_min']}",
        f"SIMCITY_STALL_CITY_MAX = {values['stall_city_max']}",
        f"SIMCITY_STALL_VILLAGE_MIN = {values['stall_village_min']}",
        f"SIMCITY_STALL_VILLAGE_MAX = {values['stall_village_max']}",
        f"SIMCITY_STALL_DATAU_MIN = {values['stall_datau_min']}",
        f"SIMCITY_STALL_DATAU_MAX = {values['stall_datau_max']}",
        f"STARTUP_AUTOADD_THANHTHI = {values['population_enabled']}",
        f"THANHTHI_SIZE = {values['city_size']}",
        f"THON_SIZE = {values['village_size']}",
        f"SIMCITY_WEB_CITY_SIZE = {values['city_size']}",
        f"SIMCITY_WEB_VILLAGE_SIZE = {values['village_size']}",
        f"LUYENCONG_AUTOADD = {values['training_enabled']}",
        f"SIMCITY_TRAIN_SIZE = {values['training_size']}",
        f"BOT_VS_BOT = {values['bot_vs_bot']}",
        f"BOT_COMBAT_RADIUS = {values['combat_radius']}",
        f"SIMBOT_AGGRO_PLAYER = {values['aggro_player']}",
        f"RADIUS_FIGHT_PLAYER = {values['fight_player_radius']}",
        f"RADIUS_FIGHT_NPC = {values['fight_npc_radius']}",
        f"RADIUS_FIGHT_SCAN = {values['fight_scan_radius']}",
        f"SIMCITY_FIGHT_TIME_MIN = {values['fight_time_min']}",
        f"SIMCITY_FIGHT_TIME_MAX = {values['fight_time_max']}",
        f"SIMCITY_REST_TIME_MIN = {values['rest_time_min']}",
        f"SIMCITY_REST_TIME_MAX = {values['rest_time_max']}",
        "TIME_FIGHTING = { minTs = SIMCITY_FIGHT_TIME_MIN, maxTs = SIMCITY_FIGHT_TIME_MAX }",
        "TIME_RESTING = { minTs = SIMCITY_REST_TIME_MIN, maxTs = SIMCITY_REST_TIME_MAX }",
        f"LIFE_RESTORE_PERCENT = {values['life_restore_percent']}",
        f"SIMBOT_NGAMI_BUFF = {values['ngami_buff']}",
        f"SIMBOT_DEBUFF = {values['debuff_enabled']}",
        f"SIMBOT_TRANPHAI = {values['faction_buff']}",
        f"SIMBOT_CITY_BUFF_PCT = {values['city_buff_percent']}",
        f"CHANCE_CHAT = {values['chat_chance']}",
        f"CHANCE_DROP_MONEY = {values['drop_money_chance']}",
        f"SIMCITY_DROP_MONEY_MIN = {values['drop_money_min']}",
        f"SIMCITY_DROP_MONEY_MAX = {values['drop_money_max']}",
        f"SIMCITY_OUTFIT_ENABLED = {values['outfit_enabled']}",
        f"SIMCITY_OUTFIT_CHANCE = {values['outfit_chance']}",
        f"SIMCITY_GUILD_CHANCE = {values['guild_chance']}",
        f"SIMCITY_TRADE_SEND_DELAY = {values['trade_send_delay']}",
        f"SIMCITY_TRADE_POST_DELAY = {values['trade_post_delay']}",
        f"SIMCITY_TRADE_WAIT_DELAY = {values['trade_wait_delay']}",
        f"SIMCITY_TRADE_GREET_DELAY = {values['trade_greet_delay']}",
        f"SIMCITY_TRADE_BYE_DELAY = {values['trade_bye_delay']}",
        f"SIMCITY_TK_ENABLED = {values['tk_enabled']}",
        f"SIMCITY_TK_TONG_COUNT = {values['tk_tong_count']}",
        f"SIMCITY_TK_KIM_COUNT = {values['tk_kim_count']}",
        f"SIMCITY_TK_LEVEL_BEGINNER = {values['tk_level_beginner']}",
        f"SIMCITY_TK_LEVEL_INTERMEDIATE = {values['tk_level_intermediate']}",
        f"SIMCITY_TK_LEVEL_ADVANCED = {values['tk_level_advanced']}",
        f"SIMCITY_TK_BOT_LEVEL = {values['tk_bot_level']}",
        f"SIMCITY_TK_REVIVE = {values['tk_revive']}",
        f"TONGKIM_SPAWN_MINSTAY = {values['tk_spawn_stay_min']}",
        f"TONGKIM_SPAWN_MAXSTAY = {values['tk_spawn_stay_max']}",
        f"SIMCITY_TK_COMBAT_RADIUS = {values['tk_combat_radius']}",
        f"SIMCITY_ARENA_ENABLED = {values['arena_enabled']}",
        f"SIMCITY_ARENA_BOT_LEVEL = {values['arena_bot_level']}",
        f"SIMCITY_ARENA_BOT_HP = {values['arena_bot_hp']}",
        f"SIMCITY_ARENA_WAIT_SECONDS = {values['arena_wait_seconds']}",
        f"SIMCITY_CHAMPIONSHIP_ENABLED = {values['championship_enabled']}",
        f"SIMCITY_CHAMPIONSHIP_BOT_LEVEL = {values['championship_bot_level']}",
        f"SIMCITY_CHAMPIONSHIP_BOT_HP = {values['championship_bot_hp']}",
        f"SIMCITY_CHAMPIONSHIP_FIGHT_SECONDS = {values['championship_fight_seconds']}",
        f"SIMCITY_DUEL_ENABLED = {values['duel_enabled']}",
        f"SIMCITY_DUEL_BOT_ENABLED = {values['duel_bot_enabled']}",
        f"SIMCITY_DUEL_BOT_LEVEL = {values['duel_bot_level']}",
        f"SIMCITY_DUEL_BOT_HP = {values['duel_bot_hp']}",
        f"SIMCITY_DUEL_WAIT_SECONDS = {values['duel_wait_seconds']}",
        f"SIMCITY_DUEL_READY_SECONDS = {values['duel_ready_seconds']}",
        f"SIMCITY_DUEL_FIGHT_SECONDS = {values['duel_fight_seconds']}",
        f"SIMCITY_LEAGUE_ENABLED = {values['league_enabled']}",
        f"SIMCITY_LEAGUE_BOT_LEVEL = {values['league_bot_level']}",
        f"SIMCITY_LEAGUE_BOT_HP = {values['league_bot_hp']}",
        "",
        "-- Gia tri 0 giu cach chon skill ngau nhien/mau NPC nhu ban goc.",
        "SIMCITY_WEB_SKILLS = {",
    ]
    train_map_lines = ["SIMCITY_TRAIN_SIZE_BY_MAP = {"]
    for _level, map_id, _name in SIMCITY_TRAINING_MAPS:
        train_map_lines.append(f"    [{map_id}] = {values['training_maps'][map_id]},")
    train_map_lines.append("}")
    train_map_lines.append("SIMCITY_TRAIN_LEVEL_BY_MAP = {")
    for map_level, map_id, _name in SIMCITY_TRAINING_MAPS:
        train_map_lines.append(f"    [{map_id}] = {map_level},")
    train_map_lines.append("}")
    train_map_index = lines.index(f"BOT_VS_BOT = {values['bot_vs_bot']}")
    lines[train_map_index:train_map_index] = train_map_lines
    faction_keys = [key for key, _label, _options in SIMCITY_FACTIONS]
    for index, key in enumerate(faction_keys):
        comma = "," if index < len(faction_keys) - 1 else ""
        lines.append(f"    {key} = {values['skills'][key]}{comma}")
    lines.extend(["}", ""])

    if os.path.exists(SIMCITY_CONFIG_PATH):
        stamp = datetime.now().strftime(".bak_simcity_%Y%m%d_%H%M%S")
        shutil.copy2(SIMCITY_CONFIG_PATH, SIMCITY_CONFIG_PATH + stamp)
    tmp = SIMCITY_CONFIG_PATH + ".tmp"
    with open(tmp, "w", encoding="ascii", newline="\n") as f:
        f.write("\n".join(lines))
    os.replace(tmp, SIMCITY_CONFIG_PATH)
    _sync_simcity_training_to_base_config(values)


def _simcity_values_from_form():
    def number(name, low, high, label):
        raw = (request.form.get(name) or "").strip()
        if not re.fullmatch(r"\d+", raw):
            raise ValueError(f"{label} phải là số nguyên")
        value = int(raw)
        if value < low or value > high:
            raise ValueError(f"{label} phải từ {low} đến {high}")
        return value

    def checkbox(name):
        return 1 if "1" in request.form.getlist(name) else 0

    values = {
        "hp_min": number("sim_hp_min", 1000, 10000000, "Sinh lực tối thiểu"),
        "hp_max": number("sim_hp_max", 1000, 10000000, "Sinh lực tối đa"),
        "attack_speed": number("sim_attack_speed", 50, 500, "Tốc độ đánh"),
        "cast_delay": number("sim_cast_delay", 1, 10, "Nhịp đánh trực tiếp"),
        "normal_cast_delay": number("sim_normal_cast_delay", 1, 10, "Nhịp AI đánh thường"),
        "skill_level": number("sim_skill_level", 1, 20, "Cấp skill"),
        "stall_enabled": 1 if "1" in request.form.getlist("sim_stall_enabled") else 0,
        "stall_city_min": number("sim_stall_city_min", 0, 200, "Số người bán trong thành tối thiểu"),
        "stall_city_max": number("sim_stall_city_max", 0, 200, "Số người bán trong thành tối đa"),
        "stall_village_min": number("sim_stall_village_min", 0, 100, "Số người bán trong thôn tối thiểu"),
        "stall_village_max": number("sim_stall_village_max", 0, 100, "Số người bán trong thôn tối đa"),
        "stall_datau_min": number("sim_stall_datau_min", 0, 100, "Số người bán quanh Dã Tẩu tối thiểu"),
        "stall_datau_max": number("sim_stall_datau_max", 0, 100, "Số người bán quanh Dã Tẩu tối đa"),
        "population_enabled": checkbox("sim_population_enabled"),
        "city_size": number("sim_city_size", 0, 1000, "Số bot mỗi thành"),
        "village_size": number("sim_village_size", 0, 500, "Số bot mỗi thôn"),
        "training_enabled": checkbox("sim_training_enabled"),
        "training_size": number("sim_training_size", 0, 500, "Số nhóm bot luyện công"),
        "bot_vs_bot": checkbox("sim_bot_vs_bot"),
        "combat_radius": number("sim_combat_radius", 1, 50, "Bán kính tìm bot đối thủ"),
        "aggro_player": checkbox("sim_aggro_player"),
        "fight_player_radius": number("sim_fight_player_radius", 1, 50, "Bán kính phát hiện người chơi"),
        "fight_npc_radius": number("sim_fight_npc_radius", 1, 50, "Bán kính phát hiện NPC"),
        "fight_scan_radius": number("sim_fight_scan_radius", 1, 50, "Bán kính tham gia chiến đấu"),
        "fight_time_min": number("sim_fight_time_min", 0, 86400, "Thời gian chiến đấu tối thiểu"),
        "fight_time_max": number("sim_fight_time_max", 0, 86400, "Thời gian chiến đấu tối đa"),
        "rest_time_min": number("sim_rest_time_min", 0, 3600, "Thời gian nghỉ tối thiểu"),
        "rest_time_max": number("sim_rest_time_max", 0, 3600, "Thời gian nghỉ tối đa"),
        "life_restore_percent": number("sim_life_restore_percent", 0, 100, "Tỷ lệ tự hồi sinh lực"),
        "ngami_buff": checkbox("sim_ngami_buff"),
        "debuff_enabled": checkbox("sim_debuff_enabled"),
        "faction_buff": checkbox("sim_faction_buff"),
        "city_buff_percent": number("sim_city_buff_percent", 0, 100, "Tỷ lệ bot thành thị dùng buff"),
        "chat_chance": number("sim_chat_chance", 0, 1000, "Tần suất trò chuyện"),
        "drop_money_chance": number("sim_drop_money_chance", 0, 10000, "Tỷ lệ rơi tiền"),
        "drop_money_min": number("sim_drop_money_min", 1, 100000000, "Tiền rơi tối thiểu"),
        "drop_money_max": number("sim_drop_money_max", 1, 100000000, "Tiền rơi tối đa"),
        "outfit_enabled": checkbox("sim_outfit_enabled"),
        "outfit_chance": number("sim_outfit_chance", 0, 100, "Tỷ lệ ngoại trang"),
        "guild_chance": number("sim_guild_chance", 0, 100, "Tỷ lệ có tên bang"),
        "trade_send_delay": number("sim_trade_send_delay", 0, 300, "Thời gian gửi vật phẩm giao dịch"),
        "trade_post_delay": number("sim_trade_post_delay", 0, 300, "Thời gian chờ hoàn tất giao dịch"),
        "trade_wait_delay": number("sim_trade_wait_delay", 0, 300, "Thời gian chờ người chơi chọn giao dịch"),
        "trade_greet_delay": number("sim_trade_greet_delay", 0, 300, "Thời gian chào hỏi"),
        "trade_bye_delay": number("sim_trade_bye_delay", 0, 300, "Thời gian chờ rời đi"),
        "tk_enabled": checkbox("sim_tk_enabled"),
        "tk_tong_count": number("sim_tk_tong_count", 0, 500, "Số bot phe Tống"),
        "tk_kim_count": number("sim_tk_kim_count", 0, 500, "Số bot phe Kim"),
        "tk_level_beginner": checkbox("sim_tk_level_beginner"),
        "tk_level_intermediate": checkbox("sim_tk_level_intermediate"),
        "tk_level_advanced": checkbox("sim_tk_level_advanced"),
        "tk_bot_level": number("sim_tk_bot_level", 1, 255, "Cấp bot Tống Kim"),
        "tk_revive": checkbox("sim_tk_revive"),
        "tk_spawn_stay_min": number("sim_tk_spawn_stay_min", 0, 600, "Thời gian ở hậu doanh tối thiểu"),
        "tk_spawn_stay_max": number("sim_tk_spawn_stay_max", 0, 600, "Thời gian ở hậu doanh tối đa"),
        "tk_combat_radius": number("sim_tk_combat_radius", 1, 100, "Bán kính chiến đấu Tống Kim"),
        "arena_enabled": checkbox("sim_arena_enabled"),
        "arena_bot_level": number("sim_arena_bot_level", 1, 255, "Cấp bot Bách Nhân"),
        "arena_bot_hp": number("sim_arena_bot_hp", 1000, 10000000, "Sinh lực bot Bách Nhân"),
        "arena_wait_seconds": number("sim_arena_wait_seconds", 5, 300, "Thời gian chờ Bách Nhân"),
        "championship_enabled": checkbox("sim_championship_enabled"),
        "championship_bot_level": number("sim_championship_bot_level", 1, 255, "Cấp bot Tỉ Võ"),
        "championship_bot_hp": number("sim_championship_bot_hp", 1000, 10000000, "Sinh lực bot Tỉ Võ"),
        "championship_fight_seconds": number("sim_championship_fight_seconds", 30, 600, "Thời gian trận Tỉ Võ"),
        "duel_enabled": checkbox("sim_duel_enabled"),
        "duel_bot_enabled": checkbox("sim_duel_bot_enabled"),
        "duel_bot_level": number("sim_duel_bot_level", 1, 255, "Cấp bot Cạnh Kỹ Trường"),
        "duel_bot_hp": number("sim_duel_bot_hp", 1000, 10000000, "Sinh lực bot Cạnh Kỹ Trường"),
        "duel_wait_seconds": number("sim_duel_wait_seconds", 5, 300, "Thời gian chờ ghép bot Cạnh Kỹ Trường"),
        "duel_ready_seconds": number("sim_duel_ready_seconds", 5, 120, "Thời gian chuẩn bị Cạnh Kỹ Trường"),
        "duel_fight_seconds": number("sim_duel_fight_seconds", 30, 900, "Thời gian trận Cạnh Kỹ Trường"),
        "league_enabled": checkbox("sim_league_enabled"),
        "league_bot_level": number("sim_league_bot_level", 1, 255, "Cấp bot Liên Đấu"),
        "league_bot_hp": number("sim_league_bot_hp", 1000, 10000000, "Sinh lực bot Liên Đấu"),
        "skills": {},
    }
    values["training_maps"] = {}
    for _level, map_id, map_name in SIMCITY_TRAINING_MAPS:
        values["training_maps"][map_id] = number(
            f"sim_training_map_{map_id}", 0, 500,
            f"Số nhóm luyện công tại {map_name}",
        )
    if values["hp_min"] > values["hp_max"]:
        raise ValueError("Sinh lực tối thiểu không được lớn hơn sinh lực tối đa")
    if values["city_size"] % 5 != 0 or values["village_size"] % 5 != 0:
        raise ValueError("Số bot mỗi thành và mỗi thôn phải là bội số của 5")
    stall_ranges = (
        ("trong thành", "stall_city_min", "stall_city_max"),
        ("trong thôn", "stall_village_min", "stall_village_max"),
        ("quanh Dã Tẩu", "stall_datau_min", "stall_datau_max"),
    )
    for label, minimum, maximum in stall_ranges:
        if values[minimum] > values[maximum]:
            raise ValueError(f"Số người bán tối thiểu {label} không được lớn hơn tối đa")
    ordered_ranges = (
        ("Thời gian chiến đấu", "fight_time_min", "fight_time_max"),
        ("Thời gian nghỉ", "rest_time_min", "rest_time_max"),
        ("Lượng tiền rơi", "drop_money_min", "drop_money_max"),
    )
    for label, minimum, maximum in ordered_ranges:
        if values[minimum] > values[maximum]:
            raise ValueError(f"{label} tối thiểu không được lớn hơn tối đa")
    if values["tk_spawn_stay_min"] > values["tk_spawn_stay_max"]:
        raise ValueError("Thời gian ở hậu doanh tối thiểu không được lớn hơn tối đa")

    for key, label, options in SIMCITY_FACTIONS:
        skill_id = number(f"sim_skill_{key}", 0, 10000, f"Skill {label}")
        allowed = {0}
        allowed.update(skill for skill, _name in options)
        if skill_id not in allowed:
            raise ValueError(f"Skill đã chọn cho {label} không hợp lệ")
        values["skills"][key] = skill_id
    return values


ITEM_BRAND_ROOT = "/opt/QuanLy_One/JX_Servers/Active/server1/settings/item"
ITEM_BRAND_CONFIG = "/opt/QuanLy_One/data/state/item_brand_current.txt"
ITEM_BRAND_DOWNLOAD_DIR = "/opt/QuanLy_One/JX_Servers/Active"
ITEM_BRAND_DEFAULT_TEXT = "Võ Lâm Offline"
ITEM_BRAND_DEFAULT_BYTES = b"V\xe2 L\xa9m Offline"
ITEM_BRAND_TARGET_FILES = {
    "amulet.txt", "armor.txt", "belt.txt", "boot.txt", "cuff.txt", "goldequip.txt",
    "helm.txt", "horse.txt", "magicscript.txt", "mantle.txt", "mask.txt",
    "meleeweapon.txt", "pendant.txt", "potion.txt", "questkey.txt",
    "rangeweapon.txt", "ring.txt", "shipin.txt", "signet.txt",
}

ITEM_STACK_SERVER_ROOT = "/opt/QuanLy_One/JX_Servers/Active/server1/settings/item"
ITEM_STACK_DIRS = ("", "000", "001", "002", "003", "004")
ITEM_STACK_FILES = (
    "potion.txt",
    "magicscript.txt", "magicscript_stack.txt",
    "questkey.txt", "questkey_stack.txt",
)
ITEM_STACK_MIN = 2
ITEM_STACK_MAX = 999
ITEM_STACK_SERVER_BINARY = "/opt/QuanLy_One/JX_Servers/Active/server1/jx_linux_y"
# Kept only so previously generated download links remain valid.  Saving the
# setting no longer reads or writes these client paths.
ITEM_STACK_DOWNLOAD_DIR = "/opt/QuanLy_One/JX_Servers/Active"
ITEM_STACK_CLIENT_ROOT = "/home/client/settings/item"
ITEM_STACK_CLIENT_BINARY = "/home/client/game.exe"
ITEM_STACK_BINARY_LAYOUTS = {
    ITEM_STACK_SERVER_BINARY: (0x1B00AC, 3, 16, bytes.fromhex("81c2bc000000")),
}
# Medicines reuse the same genre/detail/particular IDs for several strength
# levels. Enable m_bStackCmpLevel so small/medium/large medicines never merge
# into one another.
ITEM_STACK_MEDICINE_COMPARE_PATCHES = {
    ITEM_STACK_SERVER_BINARY: (
        0x1B00A6,
        bytes.fromhex(
            "8d041a83c101c740740100000081c2bc000000c7407864000000"
            "394e087fe15b5e5dc3908db600000000"
        ),
        bytes.fromhex(
            "8d041a416690c740740100000081c2bc000000c7407864000000"
            "c7407c01000000394e087fda5b5e5dc3"
        ),
    ),
}
ITEM_STACK_MEDICINE_EMPTY_BRANCH_PATCHES = {
    ITEM_STACK_SERVER_BINARY: (0x1B009E, bytes.fromhex("26"), bytes.fromhex("2d")),
}

# UTF-8 -> TCVN3/ABC, đủ cho chuỗi tiếng Việt nhập từ web.
TCVN3_MAP = {
    "à":"µ","á":"¸","ả":"¶","ã":"·","ạ":"¹",
    "ă":"¨","ằ":"»","ắ":"¾","ẳ":"¼","ẵ":"½","ặ":"Æ",
    "â":"©","ầ":"Ç","ấ":"Ê","ẩ":"È","ẫ":"É","ậ":"Ë",
    "đ":"®",
    "è":"Ì","é":"Ð","ẻ":"Î","ẽ":"Ï","ẹ":"Ñ",
    "ê":"ª","ề":"Ò","ế":"Õ","ể":"Ó","ễ":"Ô","ệ":"Ö",
    "ì":"×","í":"Ý","ỉ":"Ø","ĩ":"Ü","ị":"Þ",
    "ò":"ß","ó":"ã","ỏ":"á","õ":"â","ọ":"ä",
    "ô":"«","ồ":"å","ố":"è","ổ":"æ","ỗ":"ç","ộ":"é",
    "ơ":"¬","ờ":"ê","ớ":"í","ở":"ë","ỡ":"ì","ợ":"î",
    "ù":"ï","ú":"ó","ủ":"ñ","ũ":"ò","ụ":"ô",
    "ư":"­","ừ":"õ","ứ":"ø","ử":"ö","ữ":"÷","ự":"ù",
    "ỳ":"ú","ý":"ý","ỷ":"û","ỹ":"ü","ỵ":"þ",
    "À":"µ","Á":"¸","Ả":"¶","Ã":"·","Ạ":"¹",
    "Ă":"¡","Ằ":"¡»","Ắ":"¡¾","Ẳ":"¡¼","Ẵ":"¡½","Ặ":"¡Æ",
    "Â":"¢","Ầ":"¢Ç","Ấ":"¢Ê","Ẩ":"¢È","Ẫ":"¢É","Ậ":"¢Ë",
    "Đ":"§",
    "È":"Ì","É":"Ð","Ẻ":"Î","Ẽ":"Ï","Ẹ":"Ñ",
    "Ê":"£","Ề":"£Ò","Ế":"£Õ","Ể":"£Ó","Ễ":"£Ô","Ệ":"£Ö",
    "Ì":"×","Í":"Ý","Ỉ":"Ø","Ĩ":"Ü","Ị":"Þ",
    "Ò":"ß","Ó":"ã","Ỏ":"á","Õ":"â","Ọ":"ä",
    "Ô":"¤","Ồ":"¤å","Ố":"¤è","Ổ":"¤æ","Ỗ":"¤ç","Ộ":"¤é",
    "Ơ":"¥","Ờ":"¥ê","Ớ":"¥í","Ở":"¥ë","Ỡ":"¥ì","Ợ":"¥î",
    "Ù":"ï","Ú":"ó","Ủ":"ñ","Ũ":"ò","Ụ":"ô",
    "Ư":"¦","Ừ":"¦õ","Ứ":"¦ø","Ử":"¦ö","Ữ":"¦÷","Ự":"¦ù",
    "Ỳ":"ú","Ý":"ý","Ỷ":"û","Ỹ":"ü","Ỵ":"þ",
}

def _to_tcvn3_bytes(text):
    converted = "".join(TCVN3_MAP.get(ch, ch) for ch in text)
    return converted.encode("latin-1")


def _from_tcvn3_bytes(data):
    reverse = {}
    # Tên vật phẩm dùng kiểu ABC cũ: ưu tiên chữ thường có dấu khi một byte
    # có nhiều cách biểu diễn để khôi phục đúng các tên như "Tín Vật".
    ordered = sorted(
        TCVN3_MAP.items(), key=lambda item: (not item[0].islower(), -len(item[1]))
    )
    for char, encoded in ordered:
        reverse.setdefault(encoded.encode("latin-1"), char)
    signatures = sorted(reverse, key=len, reverse=True)
    result = []
    index = 0
    while index < len(data):
        for signature in signatures:
            if data.startswith(signature, index):
                result.append(reverse[signature])
                index += len(signature)
                break
        else:
            result.append(chr(data[index]))
            index += 1
    return "".join(result).strip()


def _ktc_read_table(path):
    with open(path, "rb") as f:
        lines = f.readlines()
    if not lines:
        raise ValueError(f"Bảng Kỳ Trân Các rỗng: {path}")
    return lines


def _ktc_goods(lines=None):
    lines = lines or _ktc_read_table(KTC_GOODS_PATH)
    goods = {}
    for goods_id, line in enumerate(lines[1:], 1):
        fields, _newline = _split_tsv_line(line)
        if len(fields) < 8:
            continue
        try:
            genre = int(fields[0].strip())
            detail = int(fields[1].strip())
            particular = int(fields[2].strip())
            level = int(fields[4].strip() or b"1")
            price = int(fields[KTC_PRICE_COLUMN].strip() or b"0")
        except ValueError:
            continue
        name = KTC_GOODS_NAME_OVERRIDES.get(goods_id)
        if not name:
            name = _from_tcvn3_bytes(fields[-1].strip()) if fields[-1].strip() else ""
        goods[goods_id] = {
            "id": goods_id,
            "genre": genre,
            "detail": detail,
            "particular": particular,
            "level": level,
            "price": price,
            "name": name or f"Vật phẩm ({genre},{detail},{particular})",
        }
    return goods


def _ktc_categories(buysell_lines=None):
    buysell_lines = buysell_lines or _ktc_read_table(KTC_BUYSELL_PATH)
    categories = []
    for line in _ktc_read_table(KTC_TYPE_PATH)[1:]:
        fields, _newline = _split_tsv_line(line)
        if len(fields) < 2:
            continue
        try:
            sell_id = int(fields[1].strip())
        except ValueError:
            continue
        if sell_id <= 0 or sell_id >= len(buysell_lines):
            raise ValueError(f"SellID {sell_id} không tồn tại trong buysell.txt")
        item_fields, _item_newline = _split_tsv_line(buysell_lines[sell_id])
        item_ids = []
        for value in item_fields:
            value = value.strip()
            if not value:
                continue
            try:
                item_ids.append(int(value))
            except ValueError:
                raise ValueError(f"Mã hàng không hợp lệ tại SellID {sell_id}")
        categories.append({
            "name": _from_tcvn3_bytes(fields[0].strip()) or f"Nhóm {sell_id}",
            "sell_id": sell_id,
            "item_ids": item_ids,
        })
    if not categories:
        raise ValueError("Không tìm thấy nhóm Kỳ Trân Các")
    return categories


def _ktc_state(query=""):
    goods = _ktc_goods()
    categories = _ktc_categories()
    current_ids = set()
    for category in categories:
        category["items"] = []
        for goods_id in category["item_ids"]:
            item = goods.get(goods_id)
            if not item:
                item = {
                    "id": goods_id, "genre": "?", "detail": "?",
                    "particular": "?", "level": "?", "price": 0,
                    "name": f"Mã hàng thiếu #{goods_id}",
                }
            category["items"].append(item)
            current_ids.add(goods_id)

    candidates = []
    query = (query or "").strip()
    if query:
        needle = query.casefold()
        for item in goods.values():
            identity = f"{item['genre']},{item['detail']},{item['particular']}"
            if (needle in item["name"].casefold() or needle == str(item["id"])
                    or needle in identity.casefold()):
                candidate = dict(item)
                candidate["in_shop"] = item["id"] in current_ids
                candidates.append(candidate)
                if len(candidates) >= 100:
                    break
    return {
        "categories": categories,
        "category_count": len(categories),
        "item_count": len(current_ids),
        "catalog_count": len(goods),
        "candidates": candidates,
        "query": query,
    }


def _ktc_render_price(lines, goods_id, price):
    if goods_id <= 0 or goods_id >= len(lines):
        raise ValueError("Mã hàng không tồn tại")
    fields, newline = _split_tsv_line(lines[goods_id])
    if len(fields) <= KTC_PRICE_COLUMN:
        raise ValueError("Dòng hàng hóa thiếu cột giá Đồng tiền")
    fields[KTC_PRICE_COLUMN] = str(price).encode("ascii")
    rendered = list(lines)
    rendered[goods_id] = b"\t".join(fields) + newline
    return rendered


def _ktc_render_category(lines, sell_id, item_ids):
    if sell_id <= 0 or sell_id >= len(lines):
        raise ValueError("Nhóm Kỳ Trân Các không tồn tại")
    fields, newline = _split_tsv_line(lines[sell_id])
    if len(item_ids) > len(fields):
        raise ValueError(f"Nhóm chỉ chứa tối đa {len(fields)} vật phẩm")
    values = [str(item_id).encode("ascii") for item_id in item_ids]
    fields = values + [b""] * (len(fields) - len(values))
    rendered = list(lines)
    rendered[sell_id] = b"\t".join(fields) + newline
    return rendered


def _ktc_update(action, goods_id, sell_id=None, price=None):
    action = (action or "").strip().lower()
    goods_id = int(goods_id)
    goods_lines = _ktc_read_table(KTC_GOODS_PATH)
    buysell_lines = _ktc_read_table(KTC_BUYSELL_PATH)
    goods = _ktc_goods(goods_lines)
    categories = _ktc_categories(buysell_lines)
    category_map = {category["sell_id"]: category for category in categories}
    if goods_id not in goods:
        raise ValueError(f"Mã hàng #{goods_id} không tồn tại trong catalog")
    current_categories = [
        category for category in categories if goods_id in category["item_ids"]
    ]

    if action == "edit_price":
        if not current_categories:
            raise ValueError("Vật phẩm này không nằm trong Kỳ Trân Các")
        price = int(price)
        if not KTC_PRICE_MIN <= price <= KTC_PRICE_MAX:
            raise ValueError("Giá Đồng tiền phải từ 1 đến 2.000.000.000")
        goods_lines = _ktc_render_price(goods_lines, goods_id, price)
        message = f"Đã đổi giá {goods[goods_id]['name']} thành {price:,} Đồng tiền"
    elif action == "add":
        sell_id = int(sell_id)
        if sell_id not in category_map:
            raise ValueError("Nhóm Kỳ Trân Các không hợp lệ")
        if current_categories:
            raise ValueError(
                f"Vật phẩm đã có trong nhóm {current_categories[0]['name']}; hãy gỡ trước khi chuyển nhóm"
            )
        price = int(price)
        if not KTC_PRICE_MIN <= price <= KTC_PRICE_MAX:
            raise ValueError("Giá Đồng tiền phải từ 1 đến 2.000.000.000")
        item_ids = list(category_map[sell_id]["item_ids"])
        item_ids.append(goods_id)
        buysell_lines = _ktc_render_category(buysell_lines, sell_id, item_ids)
        goods_lines = _ktc_render_price(goods_lines, goods_id, price)
        message = (
            f"Đã thêm {goods[goods_id]['name']} vào {category_map[sell_id]['name']} "
            f"với giá {price:,} Đồng tiền"
        )
    elif action == "remove":
        sell_id = int(sell_id)
        if sell_id not in category_map or goods_id not in category_map[sell_id]["item_ids"]:
            raise ValueError("Vật phẩm không nằm trong nhóm đã chọn")
        item_ids = [item_id for item_id in category_map[sell_id]["item_ids"] if item_id != goods_id]
        buysell_lines = _ktc_render_category(buysell_lines, sell_id, item_ids)
        message = f"Đã gỡ {goods[goods_id]['name']} khỏi {category_map[sell_id]['name']}"
    else:
        raise ValueError("Thao tác Kỳ Trân Các không hợp lệ")

    rendered = {
        KTC_GOODS_PATH: b"".join(goods_lines),
        KTC_BUYSELL_PATH: b"".join(buysell_lines),
    }
    stamp = datetime.now().strftime(".bak_ktc_web_%Y%m%d_%H%M%S")
    backups = {}
    try:
        for path in rendered:
            backup_path = path + stamp
            shutil.copy2(path, backup_path)
            backups[path] = backup_path
        for path, content in rendered.items():
            _write_bytes_preserving_metadata(path, content)
    except Exception:
        for path, backup_path in backups.items():
            if os.path.exists(backup_path):
                shutil.copy2(backup_path, path)
        raise
    return message


def _ktc_update_category(action, sell_id=None, name=None):
    action = (action or "").strip().lower()
    type_lines = _ktc_read_table(KTC_TYPE_PATH)
    buysell_lines = _ktc_read_table(KTC_BUYSELL_PATH)
    categories = _ktc_categories(buysell_lines)
    category_map = {category["sell_id"]: category for category in categories}

    if action in ("create_category", "rename_category"):
        name = (name or "").strip()
        if not name or len(name) > 24 or any(ch in name for ch in "\t\r\n"):
            raise ValueError("Tên tab phải từ 1 đến 24 ký tự và không chứa ký tự xuống dòng")
        if any(category["name"].casefold() == name.casefold() for category in categories):
            raise ValueError("Tên tab này đã tồn tại")
        encoded_name = _to_tcvn3_bytes(name)

    if action == "create_category":
        if len(categories) >= KTC_CATEGORY_MAX:
            raise ValueError(f"Kỳ Trân Các chỉ cho phép tối đa {KTC_CATEGORY_MAX} tab trên web")
        used_ids = set(category_map)
        sell_id = None
        # Ưu tiên các dòng trống liền sau cụm Kỳ Trân Các hiện tại; không ghi đè
        # dòng buysell đang được một cửa hàng khác sử dụng.
        start_id = max(used_ids) + 1
        candidates = list(range(start_id, len(buysell_lines))) + list(range(1, start_id))
        for candidate in candidates:
            if candidate in used_ids:
                continue
            fields, _newline = _split_tsv_line(buysell_lines[candidate])
            if not any(field.strip() for field in fields):
                sell_id = candidate
                break
        if sell_id is None:
            raise ValueError("Không còn dòng SellID trống trong buysell.txt để tạo tab mới")
        newline = b"\r\n" if type_lines[0].endswith(b"\r\n") else b"\n"
        if type_lines[-1] and not type_lines[-1].endswith((b"\r\n", b"\n")):
            type_lines[-1] += newline
        type_lines.append(encoded_name + b"\t" + str(sell_id).encode("ascii") + newline)
        message = f"Đã tạo tab {name} (SellID {sell_id})"
    elif action == "rename_category":
        sell_id = int(sell_id)
        if sell_id not in category_map:
            raise ValueError("Tab Kỳ Trân Các không tồn tại")
        found = False
        for index, line in enumerate(type_lines[1:], 1):
            fields, newline = _split_tsv_line(line)
            if len(fields) < 2:
                continue
            try:
                row_sell_id = int(fields[1].strip())
            except ValueError:
                continue
            if row_sell_id == sell_id:
                fields[0] = encoded_name
                type_lines[index] = b"\t".join(fields) + newline
                found = True
                break
        if not found:
            raise ValueError("Không tìm thấy dòng cấu hình của tab")
        message = f"Đã đổi tên tab thành {name}"
    elif action == "delete_category":
        sell_id = int(sell_id)
        if sell_id not in category_map:
            raise ValueError("Tab Kỳ Trân Các không tồn tại")
        if len(categories) <= 1:
            raise ValueError("Phải giữ lại ít nhất một tab Kỳ Trân Các")
        if category_map[sell_id]["item_ids"]:
            raise ValueError("Chỉ xóa được tab rỗng; hãy gỡ hết vật phẩm trong tab trước")
        kept = [type_lines[0]]
        removed = False
        for line in type_lines[1:]:
            fields, _newline = _split_tsv_line(line)
            try:
                row_sell_id = int(fields[1].strip()) if len(fields) >= 2 else None
            except ValueError:
                row_sell_id = None
            if row_sell_id == sell_id:
                removed = True
                continue
            kept.append(line)
        if not removed:
            raise ValueError("Không tìm thấy dòng cấu hình của tab")
        type_lines = kept
        message = f"Đã xóa tab {category_map[sell_id]['name']}"
    else:
        raise ValueError("Thao tác tab Kỳ Trân Các không hợp lệ")

    rendered = {KTC_TYPE_PATH: b"".join(type_lines)}
    stamp = datetime.now().strftime(".bak_ktc_web_%Y%m%d_%H%M%S")
    backup_path = KTC_TYPE_PATH + stamp
    shutil.copy2(KTC_TYPE_PATH, backup_path)
    try:
        _write_bytes_preserving_metadata(KTC_TYPE_PATH, rendered[KTC_TYPE_PATH])
    except Exception:
        shutil.copy2(backup_path, KTC_TYPE_PATH)
        raise
    return message

def _item_brand_current_text():
    try:
        with open(ITEM_BRAND_CONFIG, "r", encoding="utf-8") as f:
            text = f.read().strip()
            return text or ITEM_BRAND_DEFAULT_TEXT
    except FileNotFoundError:
        return ITEM_BRAND_DEFAULT_TEXT

def _write_item_brand_current_text(text):
    tmp = ITEM_BRAND_CONFIG + ".tmp"
    with open(tmp, "w", encoding="utf-8", newline="") as f:
        f.write(text.strip() + "\n")
    os.replace(tmp, ITEM_BRAND_CONFIG)

def _item_brand_files():
    result = []
    for root, _dirs, files in os.walk(ITEM_BRAND_ROOT):
        for filename in files:
            if not filename.endswith(".txt") or ".bak" in filename:
                continue
            result.append(os.path.join(root, filename))
    return sorted(result)

def _item_brand_patterns(brand_bytes):
    patterns = [
        b"<enter><enter><enter><enter><color=white><enter><enter><color=white><bclr=pink>" + brand_bytes + b"<bclr><color><color><color>",
        b"<enter><enter><color=white><enter><enter><color=white><bclr=pink>" + brand_bytes + b"<bclr><color><color>",
        b"<enter><enter><color=white><bclr=pink>" + brand_bytes + b"<bclr><color>",
        b"<color=white><bclr=pink>" + brand_bytes + b"<bclr><color>",
        b"<bclr=pink>" + brand_bytes + b"<bclr>",
    ]
    for n in range(1, 8):
        patterns.append((b"<enter>" * n) + b"<bclr=pink>" + brand_bytes + b"<bclr>")
        patterns.append((b"<enter>" * n) + b"<color=white><bclr=pink>" + brand_bytes + b"<bclr><color>")
    return sorted(set(patterns), key=len, reverse=True)

def _item_brand_replacement(text, remove=False):
    if remove:
        return b""
    return b"<enter><enter><bclr=pink>" + _to_tcvn3_bytes(text) + b"<bclr>"

def _item_brand_count(brand_text=None):
    brand_text = brand_text if brand_text is not None else _item_brand_current_text()
    try:
        brand_bytes = _to_tcvn3_bytes(brand_text)
    except UnicodeEncodeError:
        brand_bytes = ITEM_BRAND_DEFAULT_BYTES
    patterns = sorted(_item_brand_patterns(brand_bytes), key=len, reverse=True)
    count = 0
    files = 0
    for path in _item_brand_files():
        data = open(path, "rb").read()
        n = 0
        for pattern in patterns:
            found = data.count(pattern)
            if found:
                data = data.replace(pattern, b"")
                n += found
        if n:
            files += 1
            count += n
    return {"files": files, "count": count}

def _backup_item_file(path, stamp):
    backup = path + stamp
    if not os.path.exists(backup):
        shutil.copy2(path, backup)


def _insert_item_brand(new_text, stamp):
    """Chen brand vao cot mo ta khi dong brand da bi xoa sach, khong con chuoi cu de replace."""
    replacement = _item_brand_replacement(new_text, remove=False)
    brand_patterns = []
    for text in (_item_brand_current_text(), ITEM_BRAND_DEFAULT_TEXT, new_text):
        try:
            brand_patterns.extend(_item_brand_patterns(_to_tcvn3_bytes(text)))
        except UnicodeEncodeError:
            pass
    changed_files = 0
    inserted = 0
    for path in _item_brand_files():
        if os.path.basename(path) not in ITEM_BRAND_TARGET_FILES:
            continue
        data = open(path, "rb").read()
        lines = data.splitlines(keepends=True)
        if len(lines) <= 1:
            continue
        new_lines = []
        file_count = 0
        for index, line in enumerate(lines):
            if index == 0 or b"\t" not in line:
                new_lines.append(line)
                continue
            ending = b""
            body = line
            if body.endswith(b"\r\n"):
                body, ending = body[:-2], b"\r\n"
            elif body.endswith(b"\n"):
                body, ending = body[:-1], b"\n"
            fields = body.split(b"\t")
            if len(fields) > 8 and fields[8] and not any(pattern in fields[8] for pattern in brand_patterns):
                fields[8] = fields[8] + replacement
                body = b"\t".join(fields)
                file_count += 1
            new_lines.append(body + ending)
        if file_count:
            _backup_item_file(path, stamp)
            with open(path, "wb") as f:
                f.write(b"".join(new_lines))
            changed_files += 1
            inserted += file_count
    return changed_files, inserted


def _strip_item_brand_from_desc(desc, brand_texts):
    patterns = []
    for text in brand_texts:
        if not text:
            continue
        try:
            brand_bytes = _to_tcvn3_bytes(text)
        except UnicodeEncodeError:
            continue
        patterns.extend(_item_brand_patterns(brand_bytes))
        patterns.append(brand_bytes)
    for pattern in sorted(set(patterns), key=len, reverse=True):
        desc = desc.replace(pattern, b"")
    # Xoa cac token trang tri con sot lai o cuoi mo ta sau khi bo brand.
    trailing_tokens = [b"<enter>", b"<color=white>", b"<color>", b"<bclr=pink>", b"<bclr>"]
    changed = True
    while changed:
        changed = False
        for token in trailing_tokens:
            if desc.endswith(token):
                desc = desc[:-len(token)]
                changed = True
                break
    return desc


def _replace_item_brand(new_text, remove=False):
    old_text = _item_brand_current_text()
    brand_texts = {old_text, ITEM_BRAND_DEFAULT_TEXT, new_text, "Võ Lâm TK Offline", "Võ Lâm TK  Offline"}
    replacement = _item_brand_replacement(new_text, remove=False)
    stamp = datetime.now().strftime(".bak_item_brand_%Y%m%d_%H%M%S")
    changed_files = 0
    replacements = 0
    for path in _item_brand_files():
        if os.path.basename(path) not in ITEM_BRAND_TARGET_FILES:
            continue
        data = open(path, "rb").read()
        lines = data.splitlines(keepends=True)
        if len(lines) <= 1:
            continue
        new_lines = []
        file_count = 0
        for index, line in enumerate(lines):
            if index == 0 or b"\t" not in line:
                new_lines.append(line)
                continue
            ending = b""
            body = line
            if body.endswith(b"\r\n"):
                body, ending = body[:-2], b"\r\n"
            elif body.endswith(b"\n"):
                body, ending = body[:-1], b"\n"
            fields = body.split(b"\t")
            if len(fields) > 8 and fields[8]:
                cleaned = _strip_item_brand_from_desc(fields[8], brand_texts)
                normalized = cleaned if remove else cleaned + replacement
                if normalized != fields[8]:
                    fields[8] = normalized
                    body = b"\t".join(fields)
                    file_count += 1
            new_lines.append(body + ending)
        if file_count:
            _backup_item_file(path, stamp)
            with open(path, "wb") as f:
                f.write(b"".join(new_lines))
            changed_files += 1
            replacements += file_count
    if not remove:
        _write_item_brand_current_text(new_text)
    return {"files": changed_files, "count": replacements, "backup_suffix": stamp}

# Dung s3relay truoc, sau do game, cac gateway va cuoi cung he thong thanh toan.
# systemctl stop cho tung service se doi tien trinh thoat (SIGTERM) de no kip luu du lieu.
STOP_SEQUENCE = [
    ("jxs3relay", 5),
    ("jxgame", 3),
    ("jxbishop", 2),
    ("jxgoddess", 2),
    ("jxpaysys", 2),
    ("jxrelaypay", 0),
]
STOP_DISPLAY_NAMES = {
    "jxs3relay": "s3relay",
    "jxgame": "jxgame",
    "jxbishop": "bishop",
    "jxgoddess": "goddess",
    "jxrelaypay": "relay",
    "jxpaysys": "paysys",
}

app = Flask(__name__)
app.secret_key = os.environ.get("MANAGER_SECRET_KEY", "quanly-one-change-this-secret")
app.config.update(
    SESSION_COOKIE_NAME="quanly_one_manager",
    SESSION_COOKIE_PATH="/",
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
)

try:
    APP_VERSION = open("/opt/QuanLy_One/VERSION", encoding="utf-8").read().strip() or "dev"
except OSError:
    APP_VERSION = "dev"
app.jinja_env.globals["app_version"] = APP_VERSION

from werkzeug.middleware.proxy_fix import ProxyFix
from manager_extension import register_manager_extensions, verify_manager_password
from site_admin import register_site_admin

app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_prefix=1)
app.extensions["database_credentials"] = {"mysql": MYSQL, "mssql": MSSQL}
register_manager_extensions(app)
register_site_admin(app)

def md5_upper(s): return hashlib.md5(s.encode("utf-8")).hexdigest().upper()
def mssql_conn(): return pymssql.connect(**MSSQL, charset="utf8", autocommit=True)
def mysql_conn(): return pymysql.connect(**MYSQL, charset="utf8mb4", autocommit=True)

def _read_game_account_flag_section(section_name):
    accounts = set()
    section = ""
    try:
        with open(ADMIN_ACCOUNT_PATH, "r", encoding="utf-8", errors="ignore") as f:
            for raw in f:
                line = raw.strip()
                if not line or line.startswith("#"):
                    continue
                if line.startswith("[") and "]" in line:
                    section = line[1:line.find("]")].strip().lower()
                    continue
                if section == section_name and "=" in line:
                    key, value = line.split("=", 1)
                    if value.strip() == "1":
                        accounts.add(key.strip().lower())
    except FileNotFoundError:
        pass
    return accounts

def _read_game_admin_accounts():
    return _read_game_account_flag_section("admin")

def _write_game_admin_accounts(admins):
    admins = sorted({a.strip().lower() for a in admins if re.fullmatch(r"[A-Za-z0-9_.-]{1,32}", a.strip())})
    text = "[admin]\n# tai khoan game co quyen Lenh Bai Admin; tai khoan thuong tu nhan Cam Nang Tan Thu\n"
    for acc in admins:
        text += f"{acc}=1\n"
    text += "\n[granted]\n# he thong game co the bo qua muc nay; giu lai de tuong thich\n"
    tmp = ADMIN_ACCOUNT_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8", newline="") as f:
        f.write(text)
    os.replace(tmp, ADMIN_ACCOUNT_PATH)
    return admins

def _set_game_admin_account(acc, enabled):
    acc = (acc or "").strip().lower()
    if not re.fullmatch(r"[A-Za-z0-9_.-]{1,32}", acc):
        raise ValueError("Tên tài khoản game không hợp lệ")
    admins = _read_game_admin_accounts()
    if enabled:
        admins.add(acc)
    else:
        admins.discard(acc)
    return _write_game_admin_accounts(admins)

def sctl(*args, timeout=8):
    return subprocess.run(["systemctl", *args], capture_output=True, text=True, timeout=timeout)
def unit_active(unit): return sctl("is-active", unit).stdout.strip() == "active"
def port_listening(port):
    try:
        out = subprocess.run(["ss","-ltn"],capture_output=True,text=True,timeout=2).stdout
        return any(len(p:=l.split())>=4 and p[3].rsplit(":",1)[-1]==str(port) for l in out.splitlines())
    except Exception: return False

def active_server_info():
    """Thông tin phiên bản mà JX_Servers/Active trỏ tới, không tin đường dẫn ngoài JX_Versions/."""
    if not os.path.islink(ACTIVE_SERVER_PATH):
        return None
    resolved = os.path.realpath(ACTIVE_SERVER_PATH)
    try:
        relative = os.path.relpath(resolved, SERVERS_ROOT)
    except ValueError:
        return None
    if relative == os.pardir or relative.startswith(os.pardir + os.sep):
        return None
    parts = Path(relative).parts
    return {
        "name": parts[0] if parts else os.path.basename(resolved),
        "path": resolved,
        "relative": relative,
    }


def available_server_versions():
    try:
        return sorted(
            entry.name for entry in Path(SERVERS_ROOT).iterdir()
            if entry.is_dir() and not entry.is_symlink()
            and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}", entry.name)
        )
    except OSError:
        return []

def _operation_status(path, states=("starting", "success", "error"), lock_path=None):
    try:
        with open(path, encoding="utf-8") as status_file:
            lines = [line.rstrip("\n") for line in status_file.readlines()[:3]]
        if len(lines) != 3 or lines[0] not in states:
            return None
        updated = int(lines[2])
        age = max(0, int(time.time()) - updated)
        if lines[0] == "starting" and lock_path and age >= 10 and not os.path.exists(lock_path):
            return {
                "state": "error",
                "message": "Tiến trình nền đã dừng bất thường; điều khiển đã được mở khóa. Hãy xem log hoặc dùng !!! để dọn toàn bộ.",
                "age": age,
                "updated": updated,
                "stale": True,
            }
        if age > (300 if lines[0] == "success" else 1800):
            return None
        return {"state": lines[0], "message": lines[1], "age": age, "updated": updated}
    except (OSError, ValueError):
        return None

def game_reload_status():
    return _operation_status(GAME_RELOAD_STATUS, ("starting", "success", "error"), GAME_RELOAD_LOCK)

def latest_game_operation():
    operations = []
    started = game_start_status()
    reloaded = game_reload_status()
    if started:
        operations.append({**started, "kind": "start"})
    if reloaded:
        operations.append({**reloaded, "kind": "reload"})
    return max(operations, key=lambda item: item["updated"]) if operations else None


def _version_key(value):
    match = re.fullmatch(r"v?(\d+)\.(\d+)\.(\d+)(?:-([0-9A-Za-z.-]+))?", str(value or "").strip())
    if not match:
        return None
    suffix = match.group(4)
    suffix_parts = tuple(
        (0, int(part)) if part.isdigit() else (1, part.lower())
        for part in re.split(r"[.-]", suffix or "") if part
    )
    return (int(match.group(1)), int(match.group(2)), int(match.group(3)), 1 if not suffix else 0, suffix_parts)


def _github_release_status(current_version, force=False):
    """Đọc GitHub Release công khai; chỉ cung cấp thông tin, không tự chạy mã tải về."""
    now = time.time()
    with _update_cache_lock:
        if not force and _update_cache["result"] is not None and now < _update_cache["expires"]:
            return dict(_update_cache["result"])
    if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", UPDATE_REPOSITORY):
        result = {"status": "error", "message": "Nguồn cập nhật GitHub không hợp lệ."}
    else:
        api_url = f"https://api.github.com/repos/{UPDATE_REPOSITORY}/releases/latest"
        request_headers = {
            "Accept": "application/vnd.github+json",
            "User-Agent": "JXNative-Update-Checker",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        try:
            req = urllib.request.Request(api_url, headers=request_headers)
            with urllib.request.urlopen(req, timeout=8) as response:
                release = json.loads(response.read(1024 * 1024).decode("utf-8"))
            tag = str(release.get("tag_name") or "").strip()
            latest_key = _version_key(tag)
            current_key = _version_key(current_version)
            assets = release.get("assets") if isinstance(release.get("assets"), list) else []
            archive = next((asset for asset in assets if str(asset.get("name", "")).endswith(".tar.gz")), None)
            checksum = next((asset for asset in assets if str(asset.get("name", "")).endswith(".sha256")), None)
            result = {
                "status": "ok",
                "repository": UPDATE_REPOSITORY,
                "current": str(current_version),
                "latest": tag.lstrip("v"),
                "available": bool(current_key and latest_key and latest_key > current_key),
                "name": str(release.get("name") or tag),
                "notes": str(release.get("body") or "")[:12000],
                "published_at": str(release.get("published_at") or ""),
                "url": str(release.get("html_url") or f"https://github.com/{UPDATE_REPOSITORY}/releases"),
                "download_url": str(archive.get("browser_download_url") or "") if archive else "",
                "download_name": str(archive.get("name") or "") if archive else "",
                "checksum_url": str(checksum.get("browser_download_url") or "") if checksum else "",
                "checksum_name": str(checksum.get("name") or "") if checksum else "",
            }
            if not latest_key:
                result = {"status": "error", "message": f"Tag Release '{tag}' không đúng dạng vX.Y.Z."}
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                result = {"status": "no_release", "repository": UPDATE_REPOSITORY,
                          "message": "Repository chưa có GitHub Release chính thức."}
            elif exc.code == 403:
                result = {"status": "error", "message": "GitHub đang giới hạn lượt kiểm tra; hãy thử lại sau."}
            else:
                result = {"status": "error", "message": f"GitHub trả về HTTP {exc.code}."}
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            result = {"status": "error", "message": "Không kết nối được GitHub: " + str(exc)}
    ttl = UPDATE_CHECK_INTERVAL if result.get("status") in ("ok", "no_release") else 10 * 60
    result["checked_at"] = int(now)
    with _update_cache_lock:
        _update_cache.update(expires=now + ttl, result=dict(result))
    return result

def _scan_mod_libraries(root, recursive=False):
    libraries = []
    if not root or not os.path.isdir(root):
        return libraries
    root_path = Path(root).resolve()
    candidates = list(root_path.glob("*.so"))
    if recursive:
        candidates.extend(root_path.glob("*/*.so"))
    for path in sorted(candidates, key=lambda item: str(item).lower()):
        try:
            relative = path.relative_to(root_path).as_posix()
            if (not re.fullmatch(r"(?:[A-Za-z0-9_.-]+/)?[A-Za-z0-9_.-]+\.so", relative)
                    or path.is_symlink() or not path.is_file()):
                continue
            with path.open("rb") as library_file:
                if library_file.read(5) == b"\x7fELF\x01":
                    libraries.append(relative)
        except (OSError, ValueError):
            continue
    return libraries


def _mod_companion(selected, libraries):
    parent = os.path.dirname(selected)
    local = (parent + "/" if parent else "") + "special_drop_hook.so"
    if local in libraries:
        return local
    return "special_drop_hook.so" if "special_drop_hook.so" in libraries else ""


def _detected_game_mods():
    info = active_server_info()
    server_root = os.path.join(info["path"], "server1") if info else ""
    version_libraries = _scan_mod_libraries(server_root)
    shared_libraries = _scan_mod_libraries(SHARED_MOD_ROOT, recursive=True)
    return {"version": version_libraries, "shared": shared_libraries}


def _game_mod_state_path():
    info = active_server_info()
    version = info["name"] if info else "no-active-server"
    return os.path.join(GAME_MOD_STATE_ROOT, version + ".json")


def _read_game_mod_state():
    for state_path in (_game_mod_state_path(), os.path.join(PROJECT_ROOT, "data", "state", "game-mod.json")):
        try:
            with open(state_path, encoding="utf-8") as state_file:
                candidate = json.load(state_file)
                if isinstance(candidate, dict):
                    return candidate
        except (OSError, ValueError):
            continue
    return {}


def _legacy_game_mod_entries(saved, detected):
    """Chuyển cấu hình một MOD cũ sang danh sách có thứ tự mà không làm mất hook."""
    source = saved.get("source", "version")
    if source not in ("version", "shared"):
        source = "version"
    available = detected[source]
    cores = [name for name in available if os.path.basename(name) != "special_drop_hook.so"]
    selected = saved.get("core_library", "")
    if selected not in cores:
        selected = "vdk.so" if "vdk.so" in cores else (cores[0] if len(cores) == 1 else "")
    entries = [{"source": source, "name": selected}] if selected else []
    companion = _mod_companion(selected, available) if selected else ""
    if bool(saved.get("hook_enabled", bool(companion))) and companion:
        entries.append({"source": source, "name": companion})
    return entries


def _game_mod_entries(saved, detected):
    raw_entries = saved.get("libraries")
    if not isinstance(raw_entries, list):
        return _legacy_game_mod_entries(saved, detected), True
    entries = []
    seen = set()
    for item in raw_entries[:GAME_MOD_MAX_LIBRARIES]:
        if not isinstance(item, dict):
            continue
        source = str(item.get("source") or "").strip()
        name = str(item.get("name") or "").strip()
        key = (source, name)
        if source not in ("version", "shared") or not name or key in seen:
            continue
        seen.add(key)
        entries.append({"source": source, "name": name})
    return entries, False


def game_mod_settings():
    detected = _detected_game_mods()
    saved = _read_game_mod_state()
    entries, legacy = _game_mod_entries(saved, detected)
    labels = {"version": "Trong phiên bản", "shared": "Kho MOD"}
    display_entries = [
        {
            "source": item["source"],
            "source_label": labels[item["source"]],
            "name": item["name"],
            "available": item["name"] in detected[item["source"]],
        }
        for item in entries
    ]
    source_labels = []
    for item in display_entries:
        if item["source_label"] not in source_labels:
            source_labels.append(item["source_label"])
    return {
        "enabled": bool(saved.get("enabled", bool(entries))),
        "libraries": entries,
        "display_entries": display_entries,
        "available": detected,
        "legacy": legacy,
        "summary": " → ".join(item["name"] for item in entries) if entries else "Không nạp",
        "source_labels": source_labels,
        "invalid_count": sum(not item["available"] for item in display_entries),
        "max_libraries": GAME_MOD_MAX_LIBRARIES,
    }

def _online_player_count():
    try:
        conn = mssql_conn(); cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM Account_Info WHERE ISNULL(iClientID, 0) <> 0")
        value = int(cursor.fetchone()[0]); conn.close()
        return value
    except Exception:
        return None

def game_start_preflight(check_databases=True):
    """Trả về lỗi dễ hiểu trước khi cho phép chạy chuỗi server."""
    if not os.path.islink(ACTIVE_SERVER_PATH):
        return "Chưa kích hoạt phiên bản server. Vào Server & Dữ liệu → Phiên bản & IP, chọn đường dẫn rồi bấm Kích hoạt."
    if not os.path.isdir(os.path.join(ACTIVE_SERVER_PATH, "gateway")) or not os.path.isdir(os.path.join(ACTIVE_SERVER_PATH, "server1")):
        return "Đường dẫn server đang kích hoạt không còn hợp lệ; cần chọn lại phiên bản có đủ gateway/ và server1/."
    missing = [relative for relative in ACTIVE_SERVER_BINARIES
               if not os.path.isfile(os.path.join(ACTIVE_SERVER_PATH, relative))]
    if missing:
        return "Phiên bản server đang chọn thiếu: " + ", ".join(missing)
    if check_databases:
        closed = [name for port, name in ((1433, "MSSQL"), (3306, "MySQL")) if not port_listening(port)]
        if closed:
            return "Database chưa sẵn sàng: " + ", ".join(closed) + ". Hãy kiểm tra Docker trước khi khởi động game."
    if not os.path.isfile(GAME_START_SCRIPT):
        return "Thiếu script khởi động JXNative. Hãy chạy lại update.sh."
    return None

def game_start_status():
    return _operation_status(GAME_START_STATUS, lock_path=GAME_START_LOCK)


def _default_log_session(now=None):
    now = float(now or time.time())
    sources = [unit for unit, _label in COMPONENTS]
    return {
        "started_at": now,
        "label": "Phiên hiện tại",
        "scope": sources,
        "selected": "session",
        "markers": {source: now for source in sources + ["mssql", "mysql"]},
    }


def _load_log_session():
    try:
        with open(LOG_SESSION_PATH, encoding="utf-8") as session_file:
            state = json.load(session_file)
        if not isinstance(state, dict) or not isinstance(state.get("markers"), dict):
            raise ValueError("invalid log session")
        allowed = {unit for unit, _label in COMPONENTS} | {"mssql", "mysql"}
        scope = [source for source in state.get("scope", []) if source in allowed]
        if not scope:
            scope = [unit for unit, _label in COMPONENTS]
        started_at = float(state.get("started_at") or time.time())
        markers = {}
        for source in allowed:
            try:
                markers[source] = float(state["markers"].get(source, started_at))
            except (TypeError, ValueError):
                markers[source] = started_at
        selected = state.get("selected", "session")
        if selected not in {key for key, _label in LOG_SOURCES}:
            selected = "session"
        return {"started_at": started_at, "label": str(state.get("label") or "Phiên hiện tại")[:120],
                "scope": scope, "selected": selected, "markers": markers}
    except (OSError, ValueError, TypeError):
        state = _default_log_session()
        _save_log_session(state)
        return state


def _save_log_session(state):
    os.makedirs(os.path.dirname(LOG_SESSION_PATH), mode=0o750, exist_ok=True)
    temporary = LOG_SESSION_PATH + ".tmp"
    with open(temporary, "w", encoding="utf-8") as session_file:
        json.dump(state, session_file, ensure_ascii=False, indent=2, sort_keys=True)
        session_file.write("\n")
    os.chmod(temporary, 0o600)
    os.replace(temporary, LOG_SESSION_PATH)


def _begin_log_session(label, sources, selected="session"):
    allowed = {unit for unit, _label in COMPONENTS} | {"mssql", "mysql"}
    scope = [source for source in sources if source in allowed]
    if not scope:
        return _load_log_session()
    state = _load_log_session()
    started_at = time.time() - 0.25
    for source in scope:
        state["markers"][source] = started_at
    state.update(started_at=started_at, label=str(label)[:120], scope=scope,
                 selected=selected if selected in {key for key, _label in LOG_SOURCES} else "session")
    _save_log_session(state)
    _record_activity(label, "Thành phần: " + ", ".join(LOG_UNIT_LABELS.get(item, item) for item in scope))
    return state


def _log_session_view(state=None):
    state = state or _load_log_session()
    return {
        "started_at": state["started_at"],
        "started_label": datetime.fromtimestamp(state["started_at"]).astimezone().strftime("%I:%M:%S %p %d/%m/%Y"),
        "label": state["label"],
        "scope": state["scope"],
        "selected": state["selected"],
    }


def _record_activity(action, detail="", result="info"):
    """Append one small, structured admin activity record (never game output)."""
    try:
        os.makedirs(os.path.dirname(ACTIVITY_LOG_PATH), mode=0o750, exist_ok=True)
        if os.path.isfile(ACTIVITY_LOG_PATH) and os.path.getsize(ACTIVITY_LOG_PATH) > 2 * 1024 * 1024:
            with open(ACTIVITY_LOG_PATH, "rb") as old_file:
                recent = deque(old_file, maxlen=1000)
            temporary = ACTIVITY_LOG_PATH + ".tmp"
            with open(temporary, "wb") as new_file:
                new_file.writelines(recent)
            os.chmod(temporary, 0o600)
            os.replace(temporary, ACTIVITY_LOG_PATH)
        row = {
            "time": datetime.now().astimezone().isoformat(timespec="seconds"),
            "action": str(action)[:160],
            "detail": str(detail)[:1000],
            "result": result if result in ("ok", "error", "info") else "info",
            "user": str(session.get("manager_username") or session.get("username") or "admin")[:64]
                    if has_request_context() else "system",
            "ip": str(request.remote_addr or "")[:64] if has_request_context() else "",
        }
        with open(ACTIVITY_LOG_PATH, "a", encoding="utf-8") as activity_file:
            fcntl.flock(activity_file.fileno(), fcntl.LOCK_EX)
            activity_file.write(json.dumps(row, ensure_ascii=False) + "\n")
            activity_file.flush()
            fcntl.flock(activity_file.fileno(), fcntl.LOCK_UN)
    except OSError:
        pass


def _read_activity(limit=200):
    try:
        with open(ACTIVITY_LOG_PATH, "rb") as activity_file:
            raw_rows = deque(activity_file, maxlen=max(20, min(int(limit), 1000)))
    except (OSError, TypeError, ValueError):
        return []
    rows = []
    for raw in reversed(raw_rows):
        try:
            row = json.loads(raw.decode("utf-8", errors="replace"))
            if isinstance(row, dict):
                rows.append(row)
        except (TypeError, ValueError):
            continue
    return rows


def _operation_log_tail(path, limit):
    try:
        with open(path, "rb") as log_file:
            rows = deque(log_file, maxlen=limit)
    except OSError:
        return []
    return [_decode_mixed_log(row).rstrip("\r\n") for row in rows]


def _read_jxnative_operation_log(source, tail):
    try:
        limit = 50000 if str(tail).lower() == "all" else max(10, min(int(tail), 50000))
    except (TypeError, ValueError):
        limit = 1000

    def web_rows(row_limit):
        try:
            result = subprocess.run(
                ["journalctl", "-u", "jx-webpanel", "-n", str(row_limit),
                 "--no-pager", "-o", "short-iso"],
                capture_output=True, timeout=15, check=False,
            )
            return _decode_mixed_log(result.stdout or result.stderr).splitlines()
        except (OSError, subprocess.TimeoutExpired):
            return ["Không đọc được journal của Web quản trị."]

    if source == "start":
        rows = _operation_log_tail(GAME_START_LOG, limit)
    elif source == "reload":
        rows = _operation_log_tail(GAME_RELOAD_LOG, limit)
    elif source == "web":
        rows = web_rows(limit)
    else:
        share = max(20, limit // 3)
        rows = ["===== START ALL ====="]
        rows.extend(_operation_log_tail(GAME_START_LOG, share))
        rows.extend(["", "===== RELOAD ====="])
        rows.extend(_operation_log_tail(GAME_RELOAD_LOG, share))
        rows.extend(["", "===== WEB QUẢN TRỊ ====="])
        rows.extend(web_rows(share))
        rows = rows[-limit:]
    return "\n".join(rows) if rows else "(chưa có log)"


_process_metrics_lock = threading.Lock()
_process_metrics_previous = {}


def _unit_control_group(unit):
    try:
        result = sctl("show", unit, "--property=ControlGroup", "--value", timeout=3)
        return result.stdout.strip() if result.returncode == 0 else ""
    except (OSError, subprocess.TimeoutExpired):
        return ""


def _unit_pids(unit):
    group = _unit_control_group(unit)
    if not group:
        return []
    root = Path("/sys/fs/cgroup") / group.lstrip("/")
    if not root.is_dir():
        return []
    pids = set()
    try:
        files = [root / "cgroup.procs"] + list(root.glob("*/cgroup.procs"))
        for path in files:
            try:
                pids.update(int(value) for value in path.read_text(encoding="ascii").split())
            except (OSError, ValueError):
                continue
    except OSError:
        pass
    return sorted(pids)


def _service_resource_snapshot(running=None):
    """CPU/RAM for the complete systemd cgroup of each game component."""
    now = time.monotonic()
    clock_ticks = max(1, os.sysconf("SC_CLK_TCK"))
    page_size = max(1, os.sysconf("SC_PAGE_SIZE"))
    snapshot = {}
    with _process_metrics_lock:
        for unit, _label in COMPONENTS:
            is_running = running.get(unit, False) if running is not None else unit_active(unit)
            ticks = 0
            rss_bytes = 0
            pids = _unit_pids(unit) if is_running else []
            for pid in pids:
                try:
                    stat = Path(f"/proc/{pid}/stat").read_text(encoding="ascii")
                    fields = stat[stat.rfind(")") + 2:].split()
                    ticks += int(fields[11]) + int(fields[12])
                    rss_pages = int(Path(f"/proc/{pid}/statm").read_text(encoding="ascii").split()[1])
                    rss_bytes += max(0, rss_pages) * page_size
                except (OSError, ValueError, IndexError):
                    continue
            previous = _process_metrics_previous.get(unit)
            cpu = 0.0
            if previous and now > previous[0] and ticks >= previous[1]:
                cpu = (ticks - previous[1]) / clock_ticks / (now - previous[0]) * 100
            _process_metrics_previous[unit] = (now, ticks)
            snapshot[unit] = {
                "cpu": round(max(0.0, cpu), 1),
                "ram_mb": round(rss_bytes / 1024 / 1024, 1),
                "pids": len(pids),
            }
    return snapshot

# ---------------- Template chung (sidebar dọc bên trái) ----------------
BASE = """
<!doctype html><html lang="vi"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>JXNative</title>
<style>
:root{--bg:#edf1f5;--card:#fff;--line:#dce3ea;--fg:#293f54;--mut:#6f8091;--acc:#3b89d4;--ok:#14bda0;--err:#d9534f;--warn:#e8a23b}
*{box-sizing:border-box}body{margin:0;font-family:system-ui,Segoe UI,Roboto,sans-serif;background:var(--bg);color:var(--fg);display:flex;min-height:100vh}
.sidebar{width:260px;flex:0 0 260px;background:#293f54;border-right:1px solid #203449;position:sticky;top:0;height:100vh;overflow-x:hidden;overflow-y:auto;transition:width .22s ease,flex-basis .22s ease;z-index:30;display:flex;flex-direction:column}
.brand{height:64px;padding:0 14px;display:flex;align-items:center;gap:9px;color:#fff;border-bottom:1px solid rgba(255,255,255,.08);white-space:nowrap}.brand-mark{font-size:20px}.brand-name{font-weight:800;letter-spacing:.03em;flex:1}.sidebar-toggle{width:32px;height:32px;padding:0;border-radius:7px;background:rgba(255,255,255,.1);font-size:18px}.sidebar-nav{padding:10px;flex:1}.sidebar-power{padding:9px 12px;border-top:1px solid rgba(255,255,255,.09);display:flex;gap:8px}.sidebar-power form{flex:1}.sidebar-power button{width:100%;height:36px;padding:0;font-size:16px;background:#1e3a5f}.sidebar-power .power-off{background:#7f1d1d}.sidebar-version{border-top:1px solid rgba(255,255,255,.09);padding:11px 15px;color:#91a7ba;font-size:10px;letter-spacing:.04em;white-space:nowrap}.sidebar-version b{display:block;color:#dbe7f0;font-size:12px;margin-top:2px}
.nav-group{margin:4px 0}.nav-group-toggle{width:100%;display:flex;align-items:center;gap:9px;padding:10px 11px;background:transparent;color:#aebfce;border-radius:7px;text-align:left}.nav-group-toggle:hover{background:#284765;opacity:1}.nav-group-title{flex:1;font-size:11px;font-weight:800;text-transform:uppercase;letter-spacing:.055em;white-space:nowrap}.nav-chevron{font-size:12px;transition:transform .18s}.nav-group.open .nav-chevron{transform:rotate(90deg)}
.nav-items{display:none;padding:2px 0 5px}.nav-group.open .nav-items{display:block}.sidebar a{display:flex;align-items:center;gap:10px;color:#cbd9e4;text-decoration:none;padding:10px 12px;border-radius:5px;font-size:13px;margin-bottom:3px;white-space:nowrap}.sidebar a:hover{background:#284765;color:#fff}.sidebar a.active{background:#3b89d4;color:#fff;font-weight:700}.nav-icon{width:20px;min-width:20px;text-align:center;font-size:15px}.nav-label{overflow:hidden;text-overflow:ellipsis}
.app{flex:1;min-width:0}.topbar{min-height:64px;background:#fff;border-bottom:1px solid var(--line);padding:9px 20px;display:flex;align-items:center;gap:12px;position:sticky;top:0;z-index:20}.mobile-toggle{display:none;width:36px;height:36px;padding:0;background:#293f54}.system-status{margin-left:auto;display:flex;gap:7px;align-items:center;flex-wrap:nowrap;justify-content:flex-end;overflow:hidden}.status-chip{background:#f4f7fa;border:1px solid var(--line);border-radius:8px;padding:6px 8px;font-size:11px;line-height:1.2;white-space:nowrap;height:32px;display:inline-flex;align-items:center;justify-content:center;flex:0 0 auto;font-variant-numeric:tabular-nums}.status-chip b{font-size:12px;color:#293f54;min-width:0;overflow:hidden;text-overflow:ellipsis}.status-chip.status-ip{width:190px}.status-chip.status-cpu{width:160px}.status-chip.status-ram{width:220px}.status-chip.status-disk{width:220px}.status-chip.status-time{width:205px}.status-chip.status-ip b{color:#1772b9}.status-chip.status-cpu b{color:#b56b00}.status-chip.status-ram b{color:#07866f}.status-chip.status-disk b{color:#7657bd}
body.sidebar-collapsed .sidebar{width:68px;flex-basis:68px}body.sidebar-collapsed .brand{padding:0;justify-content:center}body.sidebar-collapsed .brand-mark,body.sidebar-collapsed .brand-name,body.sidebar-collapsed .nav-group-title,body.sidebar-collapsed .nav-chevron,body.sidebar-collapsed .nav-label,body.sidebar-collapsed .version-label{display:none}body.sidebar-collapsed .sidebar-toggle{position:static;background:rgba(255,255,255,.1)}body.sidebar-collapsed .nav-group-toggle{justify-content:center;padding:10px}body.sidebar-collapsed .sidebar a{justify-content:center;padding:10px}body.sidebar-collapsed .sidebar-power{padding:8px 6px;display:block}body.sidebar-collapsed .sidebar-power form+form{margin-top:6px}body.sidebar-collapsed .sidebar-version{padding:10px 7px;text-align:center}body.sidebar-collapsed .sidebar-version b{font-size:10px}
main{padding:20px 22px;max-width:none;overflow-x:auto}
.card{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:18px 20px;margin-bottom:18px}
.card h2{margin:0 0 14px;font-size:16px}
label{display:block;font-size:13px;color:var(--mut);margin:10px 0 4px}
input,select,textarea{width:100%;padding:10px 12px;background:#fff;border:1px solid #b9c6d2;border-radius:5px;color:var(--fg);font-size:14px}
textarea{min-height:90px;resize:vertical;line-height:1.45}
button,.btn{cursor:pointer;border:0;border-radius:9px;padding:8px 15px;font-size:13px;font-weight:600;color:#fff;background:var(--acc);text-decoration:none;display:inline-block}
button.ok,.btn.ok{background:var(--ok);color:#04231a}button.err,.btn.err{background:var(--err)}button.mut,.btn.mut{background:#2a3346}
button:hover,.btn:hover{opacity:.9}button:disabled{opacity:.45;cursor:not-allowed}.row{display:flex;gap:12px;flex-wrap:wrap}.row>*{flex:1;min-width:170px}
table{width:100%;border-collapse:collapse;font-size:13px}th,td{text-align:left;padding:8px 10px;border-bottom:1px solid var(--line);white-space:nowrap}
th{color:var(--mut);font-weight:600}.pill{display:inline-block;padding:3px 10px;border-radius:20px;font-size:12px;font-weight:600}
.pill.on{background:rgba(57,217,138,.15);color:var(--ok)}.pill.off{background:rgba(255,92,114,.15);color:var(--err)}
.flash{padding:11px 14px;border-radius:9px;margin-bottom:14px;font-size:14px}
.flash.ok{background:rgba(57,217,138,.12);color:var(--ok);border:1px solid rgba(57,217,138,.3)}
.flash.err{background:rgba(255,92,114,.12);color:var(--err);border:1px solid rgba(255,92,114,.3)}
.muted{color:var(--mut);font-size:13px}.scroll{overflow-x:auto}
pre.log{background:#05080f;border:1px solid var(--line);border-radius:9px;padding:14px;font-size:12px;line-height:1.5;max-height:70vh;overflow:auto;white-space:pre-wrap;color:#cdd6e6}
.settings-tabs{display:flex;gap:4px;border-bottom:1px solid var(--line);margin-bottom:18px}
.settings-tab{background:transparent;color:var(--mut);border-radius:8px 8px 0 0;padding:11px 16px;border-bottom:2px solid transparent}
.settings-tab:hover{background:#1a2130;color:var(--fg);opacity:1}.settings-tab.active{background:#1a2130;color:#fff;border-bottom-color:var(--acc)}
.game-center-heading,.account-heading{display:flex;align-items:center;justify-content:space-between;gap:12px;margin-bottom:12px}.game-center-heading h1,.account-heading h1{margin:0;font-size:25px}.game-center-tabs{display:flex;gap:5px;border-bottom:1px solid var(--line);margin-bottom:18px;position:sticky;top:64px;background:var(--bg);padding-top:4px;z-index:12}.game-center-tab{padding:10px 15px;border-radius:9px 9px 0 0;text-decoration:none;color:var(--mut);font-weight:700}.game-center-tab:hover{background:#1a2130;color:var(--fg)}.game-center-tab.active{background:var(--acc);color:#fff}.account-create-dialog{width:min(560px,calc(100% - 28px));padding:0;border:1px solid var(--line);border-radius:14px;background:var(--card);color:var(--fg);box-shadow:0 20px 70px rgba(0,0,0,.48)}.account-create-dialog::backdrop{background:rgba(8,15,25,.72)}.account-dialog-head,.account-dialog-foot{padding:14px 17px;display:flex;align-items:center;gap:9px}.account-dialog-head{border-bottom:1px solid var(--line)}.account-dialog-head h2{margin:0;flex:1}.account-dialog-body{padding:14px 17px}.account-dialog-foot{border-top:1px solid var(--line);justify-content:flex-end}
.jx-dialog-overlay[hidden]{display:none}.jx-dialog-overlay{position:fixed;inset:0;z-index:1000;background:rgba(5,12,20,.76);display:grid;place-items:center;padding:18px}.jx-dialog{width:min(520px,100%);background:var(--card);color:var(--fg);border:1px solid var(--line);border-radius:16px;box-shadow:0 24px 80px rgba(0,0,0,.55);overflow:hidden}.jx-dialog-head{display:flex;align-items:center;gap:10px;padding:16px 18px;border-bottom:1px solid var(--line)}.jx-dialog-icon{width:36px;height:36px;border-radius:50%;display:grid;place-items:center;background:rgba(59,137,212,.14);font-size:18px}.jx-dialog.danger .jx-dialog-icon{background:rgba(217,83,79,.16);color:var(--err)}.jx-dialog-head h2{margin:0;font-size:18px;flex:1}.jx-dialog-body{padding:18px}.jx-dialog-message{margin:0;line-height:1.55;white-space:pre-line}.jx-dialog-input{margin-top:14px}.jx-dialog-error{min-height:20px;margin-top:7px;color:var(--err);font-size:12px}.jx-dialog-foot{padding:13px 18px;border-top:1px solid var(--line);display:flex;justify-content:flex-end;gap:8px}.jx-dialog-confirm.danger{background:var(--err)}
.settings-panel{display:none}.settings-panel.active{display:block}
.simcity-tabs{display:flex;gap:6px;flex-wrap:wrap;margin:4px 0 20px;padding-bottom:12px;border-bottom:1px solid var(--line)}
.simcity-tab{background:#232c3d;color:var(--mut);padding:8px 13px}
.simcity-tab:hover{color:#fff}.simcity-tab.active{background:var(--acc);color:#fff}
.simcity-panel{display:none}.simcity-panel.active{display:block}
.toggle-line{display:flex;align-items:center;gap:10px;margin:16px 0 6px;color:var(--fg);font-size:14px}
.toggle-line input{width:18px;height:18px;margin:0;accent-color:var(--acc)}
.grid{display:grid;grid-template-columns:1fr 1fr;gap:14px}.tools{display:flex;gap:10px;flex-wrap:wrap;margin:15px 0}form.inline{display:inline}button.danger,.btn.danger{background:var(--err)}textarea.body{min-height:430px;font-family:ui-monospace,monospace}.page-heading{margin:0 0 18px;font-size:25px}.media-thumb{width:90px;max-height:70px;object-fit:cover;border-radius:6px}
.header-server{display:flex;align-items:center;gap:5px;min-width:150px;max-width:330px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;font-size:13px}.header-server b{color:var(--acc);overflow:hidden;text-overflow:ellipsis}.dashboard-grid{display:grid;grid-template-columns:minmax(360px,32%) minmax(620px,68%);gap:16px;align-items:start}.dashboard-grid .card{margin-bottom:0}.dashboard-actionbar{display:flex;align-items:center;justify-content:space-between;gap:12px;padding:12px 16px;margin-bottom:14px}.dashboard-actionbar h2{margin:0}.server-main-actions{display:flex;gap:7px;align-items:center;flex-wrap:wrap}.server-main-actions form{margin:0}.service-table{table-layout:fixed}.service-table td,.service-table th{padding:8px 5px}.service-table th:nth-child(1){width:auto}.service-table th:nth-child(2){width:54px;text-align:center}.service-table th:nth-child(3){width:72px;text-align:right}.service-source{font-weight:750;border:0;background:transparent;padding:0;text-align:left;white-space:normal}.service-state{text-align:center}.state-dot{display:inline-block;width:13px;height:13px;border-radius:50%;background:var(--err);box-shadow:0 0 0 3px rgba(217,83,79,.12)}.state-dot.on{background:var(--ok);box-shadow:0 0 0 3px rgba(20,189,160,.14)}.state-dot.busy{background:var(--warn);animation:statePulse 1s infinite}.service-action{text-align:right}.service-action button{min-width:54px;padding:7px 9px}.database-source{border:0;background:transparent;padding:0;font-weight:750;text-align:left}.session-meta{display:flex;gap:8px;align-items:center;flex-wrap:wrap;margin:-6px 0 10px;color:var(--mut);font-size:12px}.log-toolbar,.log-options{display:flex;gap:7px;align-items:center;flex-wrap:wrap}.log-source{padding:6px 9px;background:#293f54;color:var(--source-color,#dce7f1);border:1px solid var(--source-color,#51677b)}.log-source.active{background:var(--source-color,var(--acc));color:#071018}.log-options select{width:auto;padding:7px 9px}.log-options label{display:flex;align-items:center;gap:5px;margin:0}.log-options input{width:16px;height:16px;margin:0}.dashboard-log{height:calc(100vh - 285px);min-height:610px;max-height:none;margin:10px 0 0;background:#03060b;border:1px solid var(--line);border-radius:9px;padding:12px;overflow:auto;font:12px/1.5 ui-monospace,SFMono-Regular,Consolas,monospace;white-space:pre-wrap}.log-line{margin-bottom:2px;word-break:break-word}.log-time{opacity:.48;margin-right:7px}.log-service{font-weight:800;margin-right:7px}.log-error{color:#ff5c72!important}.log-warning{color:#ffb02e!important}.log-success{color:#39d98a!important}.mod-summary{border-top:1px solid var(--line);margin-top:15px;padding-top:12px;display:flex;align-items:center;gap:10px}.mod-summary-info{min-width:0;flex:1}.mod-summary-title{font-weight:750;display:block;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.mod-summary-meta{display:flex;gap:5px;flex-wrap:wrap;margin-top:5px}.mod-summary .pill{padding:2px 7px;font-size:10px}.mod-config-button{padding:7px 10px;white-space:nowrap}.mod-modal[hidden]{display:none}.mod-modal{position:fixed;inset:0;z-index:900;background:rgba(5,12,20,.78);display:grid;place-items:center;padding:18px}.mod-dialog{width:min(680px,100%);max-height:calc(100vh - 36px);overflow:auto;background:var(--card);border:1px solid var(--line);border-radius:16px;box-shadow:0 24px 80px rgba(0,0,0,.58)}.mod-dialog-head,.mod-dialog-foot{display:flex;align-items:center;gap:9px;padding:15px 18px}.mod-dialog-head{border-bottom:1px solid var(--line)}.mod-dialog-head h2{margin:0;flex:1;font-size:18px}.mod-dialog-body{padding:17px 18px}.mod-server-note{padding:10px 12px;border:1px solid var(--line);border-radius:9px;background:rgba(59,137,212,.06);margin-bottom:15px}.mod-enable-line{display:flex;align-items:center;gap:9px;color:var(--fg);font-weight:700;margin:0 0 15px}.mod-enable-line input,.mod-hook-line input{width:18px;height:18px;margin:0}.mod-source-grid{display:grid;grid-template-columns:1fr 1fr;gap:10px;margin:7px 0 15px}.mod-source-card{margin:0;padding:12px;border:1px solid var(--line);border-radius:10px;cursor:pointer;color:var(--fg);display:grid;grid-template-columns:auto 1fr;gap:4px 9px;align-items:start}.mod-source-card input{width:17px;height:17px;margin:2px 0 0;grid-row:1/3}.mod-source-card b{font-size:13px}.mod-source-card small{color:var(--mut);line-height:1.35}.mod-source-card.selected{border-color:var(--acc);box-shadow:0 0 0 2px rgba(59,137,212,.13);background:rgba(59,137,212,.07)}.mod-library-label{margin-top:0}.mod-hook-line{display:flex;align-items:center;gap:9px;color:var(--fg);margin:14px 0 0}.mod-hook-line.disabled{opacity:.5}.mod-empty{color:var(--warn);font-size:12px;margin:7px 0 0}.mod-dialog-foot{border-top:1px solid var(--line);justify-content:flex-end}.operation-notice{padding:11px 14px;margin-bottom:14px;border:1px solid var(--line);border-radius:10px}.operation-notice.starting{border-color:var(--warn);color:var(--warn)}.operation-notice.success{border-color:var(--ok);color:var(--ok)}.operation-notice.error{border-color:var(--err);color:var(--err)}.compact-status td{padding:8px 5px}.server-center-tabs{display:flex;gap:5px;border-bottom:1px solid var(--line);margin-bottom:18px;position:sticky;top:64px;background:var(--bg);padding-top:4px;z-index:12}.server-center-tab{padding:10px 15px;border-radius:9px 9px 0 0;text-decoration:none;color:var(--mut);font-weight:700}.server-center-tab.active{background:var(--acc);color:#fff}@keyframes statePulse{50%{opacity:.35;transform:scale(.8)}}
.mod-dialog{width:min(760px,100%)}.mod-add-row{display:grid;grid-template-columns:minmax(0,1fr) auto;gap:9px;align-items:end}.mod-add-row label{margin:0}.mod-add-row button{height:40px;min-width:84px}.mod-add-help{margin:7px 0 0;color:var(--mut);font-size:12px}.mod-list-heading{display:flex;align-items:center;justify-content:space-between;gap:10px;margin:18px 0 8px}.mod-list-heading b{font-size:13px}.mod-list-heading span{font-size:11px;color:var(--mut)}.mod-list{display:grid;gap:7px;min-height:48px}.mod-entry{display:grid;grid-template-columns:28px minmax(0,1fr) auto;gap:9px;align-items:center;padding:9px 10px;border:1px solid var(--line);border-radius:9px;background:rgba(255,255,255,.025)}.mod-entry-index{width:25px;height:25px;display:grid;place-items:center;border-radius:50%;background:rgba(59,137,212,.14);color:var(--acc);font-size:11px;font-weight:800}.mod-entry-main{min-width:0}.mod-entry-name{display:block;font:700 13px ui-monospace,SFMono-Regular,Consolas,monospace;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.mod-entry-source{display:inline-block;margin-top:4px;padding:2px 7px;border-radius:10px;background:rgba(59,137,212,.12);color:var(--mut);font-size:10px}.mod-entry-source.shared{background:rgba(57,217,138,.12);color:var(--ok)}.mod-entry-source.missing{background:rgba(255,92,114,.14);color:var(--err)}.mod-entry-actions{display:flex;gap:5px}.mod-entry-actions button{width:30px;height:30px;padding:0;border-radius:7px;background:#2a3346}.mod-entry-actions .remove{background:rgba(217,83,79,.82)}.mod-empty-list{padding:13px;border:1px dashed var(--line);border-radius:9px;text-align:center;color:var(--mut);font-size:12px}.mod-form-error{min-height:18px;margin:7px 0 0;color:var(--err);font-size:12px}.dashboard-grid{grid-template-columns:320px minmax(620px,1fr);gap:14px}.server-main-actions{margin:0 0 12px;flex-wrap:nowrap}.server-main-actions form{flex:1}.server-main-actions button{width:100%;padding:8px 5px;white-space:nowrap}.server-main-actions .emergency-stop-form{flex:0 0 auto}.server-main-actions .emergency-stop-button{width:38px;min-width:38px;padding:8px 4px;background:#b42318;color:#fff;border-color:#e05247;font-weight:900;letter-spacing:-1px}.server-main-actions .emergency-stop-button:hover{background:#d92d20}.service-table td,.service-table th{padding:7px 5px}.service-table th:nth-child(2){width:36px}.service-table th:nth-child(3){width:64px}.service-row,.database-row{cursor:pointer;transition:background .14s}.service-row:hover,.database-row:hover,.service-row.active,.database-row.active{background:rgba(59,137,212,.11)}.service-row:focus-visible,.database-row:focus-visible{outline:2px solid var(--acc);outline-offset:-2px}.service-source,.database-source{pointer-events:none}.dashboard-log{height:calc(100vh - 220px);min-height:650px}
@media(max-width:1100px){.dashboard-grid{grid-template-columns:1fr}.dashboard-log{height:600px;min-height:450px}}
@media(max-width:1250px){.status-chip.status-disk{display:none}}@media(max-width:1050px){.status-chip.status-ram{display:none}}@media(max-width:900px){.status-chip.status-cpu,.status-chip.status-ram,.status-chip.status-disk{display:none}.sidebar{position:fixed;left:0;transform:translateX(-100%);width:260px!important;transition:transform .22s ease}.sidebar.mobile-open{transform:translateX(0)}.mobile-toggle{display:inline-block}body.sidebar-collapsed .sidebar{width:260px;flex-basis:260px}body.sidebar-collapsed .brand-mark,body.sidebar-collapsed .brand-name,body.sidebar-collapsed .nav-group-title,body.sidebar-collapsed .nav-chevron,body.sidebar-collapsed .nav-label,body.sidebar-collapsed .version-label{display:block}body.sidebar-collapsed .brand{padding:0 14px;justify-content:flex-start}body.sidebar-collapsed .sidebar-toggle{position:static;background:rgba(255,255,255,.1)}body.sidebar-collapsed .nav-group-toggle,body.sidebar-collapsed .sidebar a{justify-content:flex-start}body.sidebar-collapsed .sidebar-version{padding:11px 15px;text-align:left}body.sidebar-collapsed .sidebar-version b{font-size:12px}.sidebar-backdrop{display:none;position:fixed;inset:0;background:rgba(10,25,40,.5);z-index:25}.sidebar-backdrop.show{display:block}main{padding:18px 14px}.topbar{padding:8px 12px}.grid{grid-template-columns:1fr}}
@media(max-width:560px){.status-chip.status-ip{max-width:150px;overflow:hidden;text-overflow:ellipsis}.status-chip.status-time{display:none}.mod-source-grid,.mod-add-row{grid-template-columns:1fr}.mod-add-row button{width:100%}.mod-entry{grid-template-columns:25px minmax(0,1fr)}.mod-entry-actions{grid-column:2;justify-content:flex-end}.dashboard-log{height:380px}}
</style></head><body>
<aside class="sidebar" id="sidebar"><div class="brand"><span class="brand-mark">🗡️</span><span class="brand-name">JXNative</span><button type="button" class="sidebar-toggle" id="sidebarToggle" title="Thu gọn menu">☰</button></div><nav class="sidebar-nav">
<section class="nav-group {{'open' if page in ('dash','console','accounts','ky_tran_cac','item_brand','game_settings','events') else ''}}" data-group="server"><button type="button" class="nav-group-toggle"><span class="nav-icon">🖥️</span><span class="nav-group-title">Quản lý Server</span><span class="nav-chevron">▶</span></button><div class="nav-items">
<a href="{{ url_for('dashboard') }}" class="{{'active' if page=='dash' else ''}}"><span class="nav-icon">📊</span><span class="nav-label">Bảng điều khiển</span></a>
<a href="{{ url_for('console_page') }}" class="{{'active' if page=='console' else ''}}"><span class="nav-icon">⌨️</span><span class="nav-label">Console & Nhật ký</span></a>
<a href="{{ url_for('players') }}" class="{{'active' if page=='accounts' else ''}}"><span class="nav-icon">👥</span><span class="nav-label">Tài khoản</span></a>
<a href="{{ url_for('game_settings') }}" class="{{'active' if page in ('ky_tran_cac','item_brand','game_settings','events') else ''}}"><span class="nav-icon">⚙️</span><span class="nav-label">Thiết lập game</span></a></div></section>
<section class="nav-group {{'open' if page in ('site_settings','site_articles','site_article') else ''}}" data-group="website"><button type="button" class="nav-group-toggle"><span class="nav-icon">🌐</span><span class="nav-group-title">Quản trị Website</span><span class="nav-chevron">▶</span></button><div class="nav-items">
<a href="{{ site_admin_url() }}" class="{{'active' if page=='site_settings' else ''}}"><span class="nav-icon">⚙️</span><span class="nav-label">Cấu hình Website</span></a>
<a href="{{ site_articles_url() }}" class="{{'active' if page=='site_articles' else ''}}"><span class="nav-icon">📝</span><span class="nav-label">Quản lý bài viết</span></a></div></section>
<section class="nav-group {{'open' if page in ('server_setup','database','account_settings') else ''}}" data-group="system"><button type="button" class="nav-group-toggle"><span class="nav-icon">🔧</span><span class="nav-group-title">Hệ thống</span><span class="nav-chevron">▶</span></button><div class="nav-items">
<a href="{{ manager_setup_url() }}" class="{{'active' if page in ('server_setup','database') else ''}}"><span class="nav-icon">🗄️</span><span class="nav-label">Server & Dữ liệu</span></a>
<a href="{{ manager_account_url() }}" class="{{'active' if page=='account_settings' else ''}}"><span class="nav-icon">🔐</span><span class="nav-label">Đổi tài khoản Admin</span></a>
<a href="{{ url_for('manager_ext.logout') }}"><span class="nav-icon">🚪</span><span class="nav-label">Đăng xuất</span></a></div></section>
</nav><div class="sidebar-power">
<form method="post" action="{{ url_for('shutdown_host') }}" data-confirm="{{ 'Server còn chạy. Hệ thống sẽ Stop All an toàn rồi TẮT MÁY. Tiếp tục?' if host_locked else 'TẮT MÁY CHỦ? Máy sẽ tắt hoàn toàn.' }}" data-dialog-danger="1"><button class="power-off" title="Tắt máy chủ">⏻</button></form>
<form method="post" action="{{ url_for('reboot_host') }}" data-confirm="{{ 'Server còn chạy. Hệ thống sẽ Stop All an toàn rồi KHỞI ĐỘNG LẠI máy. Tiếp tục?' if host_locked else 'KHỞI ĐỘNG LẠI MÁY CHỦ?' }}" data-dialog-danger="1"><button title="Khởi động lại máy chủ">↻</button></form>
</div><div class="sidebar-version"><span class="version-label">PHIÊN BẢN</span><b>v{{ app_version }}</b><button type="button" id="sidebarUpdate" class="sidebar-update" data-check-url="{{url_for('update_check')}}" data-cache-key="{{update_session_key}}" title="Kiểm tra bản cập nhật"><span class="sidebar-update-icon">↻</span><span class="sidebar-update-label">Đang kiểm tra…</span></button></div></aside><div class="sidebar-backdrop" id="sidebarBackdrop"></div>
<div class="app"><header class="topbar"><button type="button" class="mobile-toggle" id="mobileToggle">☰</button>{% if server_versions|length > 1 %}<details class="header-server-picker"><summary title="Đổi server active">Server: <b>{{ header_server.name if header_server else 'Chưa chọn' }}</b><span>▾</span></summary><div class="server-picker-menu"><div class="server-picker-title">Chọn server active<small>{{'Cần Stop All trước khi đổi' if host_locked else 'Chọn phiên bản muốn sử dụng'}}</small></div>{% for server_name in server_versions %}{% if header_server and server_name == header_server.name %}<div class="server-picker-current"><b>{{server_name}}</b><span>Đang dùng</span></div>{% else %}<form method="post" action="{{url_for('manager_ext.activate')}}" data-confirm="Kích hoạt server {{server_name}}? IP của máy hiện tại sẽ được áp dụng vào phiên bản này."><input type="hidden" name="csrf_token" value="{{manager_csrf}}"><input type="hidden" name="server_name" value="{{server_name}}"><input type="hidden" name="next" value="{{url_for('dashboard')}}"><button type="submit" class="server-picker-option" {{'disabled' if host_locked else ''}}>{{server_name}}</button></form>{% endif %}{% endfor %}<a href="{{manager_setup_url()}}">Quản lý phiên bản…</a></div></details>{% else %}<div class="header-server" title="{{ header_server.path if header_server else 'Chưa kích hoạt phiên bản' }}">Server: <b>{{ header_server.name if header_server else 'Chưa chọn' }}</b></div>{% endif %}<div class="system-status" id="systemStatus" data-url="{{ url_for('system_status') }}"><span class="status-chip status-ip">IP&nbsp;<b data-field="ip">--</b></span><span class="status-chip status-cpu">CPU&nbsp;<b data-field="cpu">--</b></span><span class="status-chip status-ram">RAM&nbsp;<b data-field="ram">--</b></span><span class="status-chip status-disk">Ổ đĩa&nbsp;<b data-field="disk">--</b></span><span class="status-chip status-time">🕒&nbsp;<b data-field="time">--</b></span></div></header><main>
{% with msgs = get_flashed_messages(with_categories=true) %}{% for cat,m in msgs %}
<div class="flash {{cat}}">{{m}}</div>{% endfor %}{% endwith %}
{{ body|safe }}
</main></div>
<div class="jx-dialog-overlay" id="jxDialogOverlay" hidden aria-hidden="true"><section class="jx-dialog" id="jxDialog" role="dialog" aria-modal="true" aria-labelledby="jxDialogTitle"><div class="jx-dialog-head"><span class="jx-dialog-icon" id="jxDialogIcon">?</span><h2 id="jxDialogTitle">Xác nhận thao tác</h2></div><div class="jx-dialog-body"><p class="jx-dialog-message" id="jxDialogMessage"></p><input class="jx-dialog-input" id="jxDialogInput" autocomplete="off" hidden><div class="jx-dialog-error" id="jxDialogError"></div></div><div class="jx-dialog-foot"><button type="button" class="mut" id="jxDialogCancel">Hủy</button><button type="button" class="jx-dialog-confirm" id="jxDialogConfirm">Xác nhận</button></div></section></div>
<dialog class="update-dialog" id="updateDialog"><div class="update-dialog-head"><span class="update-dialog-icon" id="updateDialogIcon">↻</span><div><small>CẬP NHẬT JXNATIVE</small><h2 id="updateDialogTitle">Đang kiểm tra…</h2></div><button type="button" class="mut update-dialog-close" aria-label="Đóng">✕</button></div><div class="update-dialog-body"><p id="updateDialogMessage">Đang đọc bản phát hành mới nhất từ GitHub.</p><p class="update-dialog-note" id="updateDialogNote" hidden>Có thể xem Release, tải gói hoặc cập nhật trực tiếp trên máy chủ.</p></div><div class="update-dialog-actions"><button type="button" class="mut" id="updateRetry">Kiểm tra lại</button><a class="btn mut" id="updateRelease" target="_blank" rel="noopener" hidden>Xem Release</a><a class="btn mut" id="updateDownload" target="_blank" rel="noopener" hidden>Tải về</a><a class="btn ok" id="updateCenter" href="{{url_for('update_center')}}" hidden>Cập nhật ngay</a><button type="button" class="update-dialog-close">Đóng</button></div></dialog>
<script>
(function(){
  const overlay=document.getElementById('jxDialogOverlay'),dialog=document.getElementById('jxDialog'),title=document.getElementById('jxDialogTitle'),icon=document.getElementById('jxDialogIcon'),message=document.getElementById('jxDialogMessage'),input=document.getElementById('jxDialogInput'),error=document.getElementById('jxDialogError'),cancel=document.getElementById('jxDialogCancel'),accept=document.getElementById('jxDialogConfirm');let finish=null,mode='confirm',options={};
  function close(value){if(!finish)return;overlay.hidden=true;overlay.setAttribute('aria-hidden','true');document.body.style.overflow=document.querySelector('.mod-modal:not([hidden])')?'hidden':'';const done=finish;finish=null;done(value)}
  function open(kind,text,opts={}){if(finish)close(kind==='prompt'?null:false);mode=kind;options=opts;title.textContent=opts.title||(kind==='prompt'?'Nhập thông tin':'Xác nhận thao tác');message.textContent=text||'';error.textContent='';dialog.classList.toggle('danger',!!opts.danger);accept.classList.toggle('danger',!!opts.danger);icon.textContent=opts.danger?'!':(kind==='prompt'?'✎':'?');accept.textContent=opts.confirmText||(kind==='prompt'?'Tiếp tục':'Xác nhận');input.hidden=kind!=='prompt';input.type=opts.inputType||'text';input.value=opts.initial||'';input.placeholder=opts.placeholder||'';overlay.hidden=false;overlay.setAttribute('aria-hidden','false');document.body.style.overflow='hidden';setTimeout(()=>kind==='prompt'?input.focus():accept.focus(),0);return new Promise(resolve=>{finish=resolve})}
  accept.addEventListener('click',()=>{if(mode==='prompt'){const value=input.value;if(options.exact!==undefined&&value.trim()!==String(options.exact)){error.textContent=options.mismatch||'Giá trị xác nhận chưa chính xác.';input.focus();input.select();return}close(value)}else close(true)});cancel.addEventListener('click',()=>close(mode==='prompt'?null:false));overlay.addEventListener('click',event=>{if(event.target===overlay)close(mode==='prompt'?null:false)});document.addEventListener('keydown',event=>{if(overlay.hidden)return;if(event.key==='Escape')close(mode==='prompt'?null:false);else if(event.key==='Enter'&&mode==='prompt'){event.preventDefault();accept.click()}});
  window.JXDialog={confirm:(text,opts={})=>open('confirm',text,opts),prompt:(text,opts={})=>open('prompt',text,opts)};
  document.addEventListener('submit',async event=>{const form=event.target;if(!(form instanceof HTMLFormElement)||form.dataset.dialogBypass==='1'){if(form?.dataset)delete form.dataset.dialogBypass;return}const confirmText=form.dataset.confirm,promptText=form.dataset.prompt;if(!confirmText&&!promptText)return;event.preventDefault();event.stopImmediatePropagation();const submitter=event.submitter,danger=form.dataset.dialogDanger==='1'||!!submitter?.matches('.err,.danger,.power-off');if(promptText){const target=form.dataset.promptTarget,value=await window.JXDialog.prompt(promptText,{title:form.dataset.promptTitle||'Nhập thông tin',initial:form.dataset.promptInitial||'',placeholder:form.dataset.promptPlaceholder||'',exact:form.dataset.promptExact,mismatch:form.dataset.promptMismatch,danger});if(value===null)return;if(target&&form.elements[target])form.elements[target].value=value.trim()}if(confirmText&&!await window.JXDialog.confirm(confirmText,{danger,confirmText:form.dataset.confirmButton||'Xác nhận'}))return;form.dataset.dialogBypass='1';form.requestSubmit(submitter||undefined)},true);
})();
(function(){
  const body=document.body, sidebar=document.getElementById('sidebar'), backdrop=document.getElementById('sidebarBackdrop');
  if(localStorage.getItem('jx-sidebar-collapsed')==='1') body.classList.add('sidebar-collapsed');
  document.getElementById('sidebarToggle').addEventListener('click',()=>{if(innerWidth<=900){sidebar.classList.remove('mobile-open');backdrop.classList.remove('show')}else{body.classList.toggle('sidebar-collapsed');localStorage.setItem('jx-sidebar-collapsed',body.classList.contains('sidebar-collapsed')?'1':'0')}});
  document.getElementById('mobileToggle').addEventListener('click',()=>{sidebar.classList.add('mobile-open');backdrop.classList.add('show')});
  backdrop.addEventListener('click',()=>{sidebar.classList.remove('mobile-open');backdrop.classList.remove('show')});
  document.querySelectorAll('.sidebar a').forEach(link=>{const label=link.querySelector('.nav-label');if(label)link.title=label.textContent.trim()});
  document.querySelectorAll('.nav-group-toggle').forEach(button=>{const title=button.querySelector('.nav-group-title');if(title)button.title=title.textContent.trim()});
  document.querySelectorAll('.nav-group').forEach(group=>{const key='jx-nav-'+group.dataset.group;const active=!!group.querySelector('a.active');if(!active&&localStorage.getItem(key)==='1')group.classList.add('open');group.querySelector('.nav-group-toggle').addEventListener('click',()=>{group.classList.toggle('open');localStorage.setItem(key,group.classList.contains('open')?'1':'0')})});
  const status=document.getElementById('systemStatus'), fields={};status.querySelectorAll('[data-field]').forEach(el=>fields[el.dataset.field]=el);
  function fixed(value,digits){const number=Number(value);return Number.isFinite(number)?number.toFixed(digits):'0'}
  let serverClock=null;
  function renderClock(){if(!serverClock)return;const elapsed=Math.floor((Date.now()-serverClock.received)/1000),value=new Date((serverClock.epoch+elapsed+serverClock.offset)*1000),rawHour=value.getUTCHours(),suffix=rawHour>=12?'PM':'AM',hour=rawHour%12||12,pad=number=>String(number).padStart(2,'0');fields.time.textContent=hour+':'+pad(value.getUTCMinutes())+':'+pad(value.getUTCSeconds())+' '+suffix+' '+pad(value.getUTCDate())+'/'+pad(value.getUTCMonth()+1)+'/'+value.getUTCFullYear()}
  function update(data){fields.ip.textContent=(data.interface?data.interface+' · ':'')+(data.ip||'Chưa xác định');fields.cpu.textContent=fixed(data.cpu_percent,1)+'% · '+fixed(data.cpu_ghz,2)+' GHz';fields.ram.textContent=fixed(data.ram_used_gb,1)+' / '+fixed(data.ram_total_gb,1)+' GB · '+fixed(data.ram_percent,1)+'%';fields.disk.textContent=fixed(data.disk_used_gb,1)+' / '+fixed(data.disk_total_gb,1)+' GB · '+fixed(data.disk_percent,1)+'%';if(Number.isFinite(Number(data.time_epoch))&&Number.isFinite(Number(data.time_offset))){serverClock={epoch:Number(data.time_epoch),offset:Number(data.time_offset),received:Date.now()};renderClock()}else fields.time.textContent=data.time||'--'}
  let refreshing=false;async function refresh(){if(refreshing)return;refreshing=true;try{const response=await fetch(status.dataset.url,{headers:{Accept:'application/json'},cache:'no-store'});if(response.ok)update(await response.json())}catch(e){}finally{refreshing=false}}
  refresh();setInterval(refresh,5000);setInterval(renderClock,1000);
})();
(function(){
  const link=document.getElementById('sidebarUpdate'),dialog=document.getElementById('updateDialog');if(!link||!dialog)return;
  const label=link.querySelector('.sidebar-update-label'),icon=link.querySelector('.sidebar-update-icon'),title=document.getElementById('updateDialogTitle'),message=document.getElementById('updateDialogMessage'),note=document.getElementById('updateDialogNote'),release=document.getElementById('updateRelease'),download=document.getElementById('updateDownload'),center=document.getElementById('updateCenter'),retry=document.getElementById('updateRetry'),dialogIcon=document.getElementById('updateDialogIcon');
  const cacheKey='jx-update:'+link.dataset.cacheKey;let current=null;
  function render(data){current=data;link.classList.remove('available','checked','failed');release.hidden=true;download.hidden=true;center.hidden=true;note.hidden=true;if(data.status==='ok'&&data.available){link.classList.add('available');icon.textContent='↑';label.textContent='Có bản v'+data.latest;link.title='Có bản JXNative v'+data.latest;dialogIcon.textContent='↑';title.textContent='Có bản mới v'+data.latest;message.textContent='Máy đang dùng v'+data.current+'. Chọn cách cập nhật bên dưới.';note.hidden=false;center.hidden=false}else if(data.status==='ok'){link.classList.add('checked');icon.textContent='✓';label.textContent='Đã là bản mới nhất';link.title='JXNative đang ở bản mới nhất';dialogIcon.textContent='✓';title.textContent='Đã là bản mới nhất';message.textContent='Máy đang dùng JXNative v'+data.current+'.';}else if(data.status==='no_release'){link.classList.add('checked');icon.textContent='•';label.textContent='Chưa có bản phát hành';link.title=data.message||'Repository chưa có Release';dialogIcon.textContent='•';title.textContent='Chưa có bản phát hành';message.textContent=data.message||'GitHub chưa có Release chính thức.'}else{link.classList.add('failed');icon.textContent='!';label.textContent='Không kiểm tra được';link.title=data.message||'Không kiểm tra được GitHub';dialogIcon.textContent='!';title.textContent='Không kiểm tra được';message.textContent=data.message||'Không thể kết nối GitHub lúc này.'}if(data.url){release.href=data.url;release.hidden=false}if(data.available&&data.download_url){download.href=data.download_url;download.hidden=false}}
  async function check(force=false){retry.disabled=true;try{const response=await fetch(link.dataset.checkUrl+(force?'?refresh=1':''),{headers:{Accept:'application/json'},cache:'no-store'});if(!response.ok)throw new Error('HTTP '+response.status);const data=await response.json();render(data);try{sessionStorage.setItem(cacheKey,JSON.stringify(data))}catch(error){}}catch(error){render({status:'error',message:'Lỗi kết nối GitHub: '+(error.message||'không xác định')})}finally{retry.disabled=false}}
  link.addEventListener('click',()=>{if(typeof dialog.showModal==='function')dialog.showModal();else dialog.setAttribute('open','')});
  dialog.querySelectorAll('.update-dialog-close').forEach(button=>button.addEventListener('click',()=>dialog.close()));dialog.addEventListener('click',event=>{if(event.target===dialog)dialog.close()});retry.addEventListener('click',()=>check(true));
  try{const cached=JSON.parse(sessionStorage.getItem(cacheKey)||'null');if(cached&&cached.status)render(cached);else check()}catch(error){check()}
})();
</script></body></html>
"""
_ADMIN_POLISH_CSS = (Path(__file__).with_name("polish.css")).read_text(encoding="utf-8")
BASE = BASE.replace("</head>", "<style>" + _ADMIN_POLISH_CSS + "</style></head>", 1)
_ADMIN_DATABASE_JS = (Path(__file__).with_name("database_tools.js")).read_text(encoding="utf-8")
BASE = BASE.replace("</body>", "<script>" + _ADMIN_DATABASE_JS + "</script></body>", 1)

def page(body, **kw):
    kw.setdefault("host_locked", _host_action_blocked("thực hiện thao tác máy chủ") is not None)
    kw.setdefault("header_server", active_server_info())
    kw.setdefault("server_versions", available_server_versions())
    kw.setdefault("manager_csrf", session.get("csrf_token", ""))
    kw.setdefault("update_session_key", f"{APP_VERSION}:{session.get('manager_login_at', '')}")
    return render_template_string(BASE, body=render_template_string(body, **kw), **kw)

app.extensions["render_manager_page"] = page

GAME_SETTINGS_NAV = """
<div class="game-center-heading"><h1>Thiết lập game</h1></div>
<nav class="game-center-tabs" aria-label="Nhóm thiết lập game">
  <a class="game-center-tab {{'active' if game_center_section=='game_settings' else ''}}" href="{{url_for('game_settings')}}">Tổng quát</a>
  <a class="game-center-tab {{'active' if game_center_section=='ky_tran_cac' else ''}}" href="{{url_for('ky_tran_cac')}}">Kỳ Trân Các</a>
  <a class="game-center-tab {{'active' if game_center_section=='item_brand' else ''}}" href="{{url_for('item_brand')}}">Vật phẩm</a>
  <a class="game-center-tab {{'active' if game_center_section=='events' else ''}}" href="{{url_for('events')}}">Sự kiện</a>
</nav>
"""


def game_settings_page(body, section, **context):
    return page(
        GAME_SETTINGS_NAV + body,
        page=section,
        game_center_section=section,
        **context,
    )

_cpu_sampler_lock = threading.Lock()
_cpu_sampler_started = False
_cpu_samples = deque(maxlen=5)
_cpu_average = None
_status_static_cache = {
    "updated": 0.0,
    "interface": "",
    "ip": "",
    "online": None,
    "uptime": "--",
    "disk_percent": 0.0,
    "disk_used_gb": 0.0,
    "disk_total_gb": 0.0,
}

def _read_cpu_totals():
    values = [int(value) for value in open("/proc/stat", encoding="ascii").readline().split()[1:]]
    idle = values[3] + (values[4] if len(values) > 4 else 0)
    return idle, sum(values)


def _cpu_sample_loop():
    global _cpu_average
    try:
        previous_idle, previous_total = _read_cpu_totals()
    except Exception:
        previous_idle, previous_total = 0, 0
    while True:
        time.sleep(1)
        try:
            idle, total = _read_cpu_totals()
            if total > previous_total:
                percent = 100 * (1 - (idle - previous_idle) / (total - previous_total))
                with _cpu_sampler_lock:
                    _cpu_samples.append(max(0.0, min(100.0, percent)))
                    if len(_cpu_samples) == _cpu_samples.maxlen:
                        _cpu_average = round(sum(_cpu_samples) / len(_cpu_samples), 1)
            previous_idle, previous_total = idle, total
        except Exception:
            continue


def _ensure_cpu_sampler():
    global _cpu_sampler_started
    with _cpu_sampler_lock:
        if _cpu_sampler_started:
            return
        _cpu_sampler_started = True
        threading.Thread(target=_cpu_sample_loop, name="jx-cpu-sampler", daemon=True).start()


def _read_cpu_percent():
    _ensure_cpu_sampler()
    with _cpu_sampler_lock:
        average = _cpu_average
    if average is not None:
        return average
    try:
        return round(min(100, os.getloadavg()[0] * 100 / max(1, os.cpu_count() or 1)), 1)
    except Exception:
        return 0.0


def _read_cpu_ghz():
    try:
        frequencies = []
        for path in Path("/sys/devices/system/cpu").glob("cpu[0-9]*/cpufreq/scaling_cur_freq"):
            frequencies.append(float(path.read_text(encoding="ascii").strip()) / 1_000_000)
        if frequencies:
            return round(sum(frequencies) / len(frequencies), 2)
        with open("/proc/cpuinfo", encoding="ascii", errors="ignore") as handle:
            for line in handle:
                if line.lower().startswith("cpu mhz"):
                    frequencies.append(float(line.split(":", 1)[1].strip()) / 1000)
        return round(sum(frequencies) / len(frequencies), 2) if frequencies else 0.0
    except Exception:
        return 0.0


def _read_memory_status():
    try:
        values = {}
        with open("/proc/meminfo", encoding="ascii") as handle:
            for line in handle:
                key, value = line.split(":", 1)
                values[key] = int(value.strip().split()[0])
        total = values["MemTotal"]
        available = values.get("MemAvailable", values.get("MemFree", 0))
        used = total - available
        return {
            "percent": round(100 * used / total, 1) if total else 0.0,
            "used_gb": round(used / 1024 / 1024, 1),
            "total_gb": round(total / 1024 / 1024, 1),
        }
    except Exception:
        return {"percent": 0.0, "used_gb": 0.0, "total_gb": 0.0}

def _read_uptime_label():
    try:
        seconds = int(float(Path("/proc/uptime").read_text(encoding="ascii").split()[0]))
        days, seconds = divmod(seconds, 86400)
        hours, _seconds = divmod(seconds, 3600)
        return (f"{days} ngày " if days else "") + f"{hours} giờ"
    except Exception:
        return "--"

def _primary_network_address():
    try:
        result = subprocess.run(["ip", "-j", "-4", "addr", "show"], capture_output=True, text=True, timeout=3, check=True)
        candidates = []
        for interface in json.loads(result.stdout):
            name = interface.get("ifname", "")
            if name == "lo" or name.startswith(("docker", "br-", "veth", "virbr")):
                continue
            for info in interface.get("addr_info", []):
                address = info.get("local")
                if address:
                    vpn = name.startswith(("zt", "tailscale", "wg", "tun", "tap"))
                    candidates.append((0 if vpn else 1, name, address))
        configured_ip = ""
        config_path = "/opt/QuanLy_One/JX_Servers/Active/server1/servercfg.ini"
        try:
            with open(config_path, "r", encoding="latin-1") as handle:
                match = re.search(r"^\s*InternetIp\s*=\s*([^\s;#]+)", handle.read(), re.IGNORECASE | re.MULTILINE)
                configured_ip = match.group(1).strip() if match else ""
        except OSError:
            pass
        if configured_ip:
            for _priority, name, address in candidates:
                if address == configured_ip:
                    return name, address
            return "Game", configured_ip
        if candidates:
            _priority, name, address = sorted(candidates)[0]
            return name, address
    except Exception:
        pass
    return "", ""

@app.route("/api/system-status")
def system_status():
    now = time.monotonic()
    if now - _status_static_cache["updated"] >= 10:
        interface, address = _primary_network_address()
        disk = shutil.disk_usage("/opt/QuanLy_One")
        _status_static_cache.update(
            updated=now,
            interface=interface,
            ip=address,
            online=_online_player_count(),
            uptime=_read_uptime_label(),
            disk_percent=round(100 * disk.used / disk.total, 1) if disk.total else 0,
            disk_used_gb=round(disk.used / 1024 / 1024 / 1024, 1),
            disk_total_gb=round(disk.total / 1024 / 1024 / 1024, 1),
        )
    memory = _read_memory_status()
    local_time = datetime.now().astimezone()
    return jsonify(
        ip=_status_static_cache["ip"],
        interface=_status_static_cache["interface"],
        online=_status_static_cache["online"],
        uptime=_status_static_cache["uptime"],
        cpu_percent=_read_cpu_percent(),
        cpu_ghz=_read_cpu_ghz(),
        ram_percent=memory["percent"],
        ram_used_gb=memory["used_gb"],
        ram_total_gb=memory["total_gb"],
        disk_percent=_status_static_cache["disk_percent"],
        disk_used_gb=_status_static_cache["disk_used_gb"],
        disk_total_gb=_status_static_cache["disk_total_gb"],
        time=local_time.strftime("%I:%M:%S %p %d/%m/%Y").lstrip("0"),
        time_epoch=time.time(),
        time_offset=int((local_time.utcoffset() or timedelta()).total_seconds()),
    )


@app.route("/api/update-check")
def update_check():
    force = request.args.get("refresh") == "1"
    cache_id = f"{APP_VERSION}:{UPDATE_REPOSITORY}"
    cached = session.get("jx_update_status")
    if not force and isinstance(cached, dict) and cached.get("cache_id") == cache_id:
        return jsonify(cached)
    result = _github_release_status(APP_VERSION, force=force)
    # Chỉ giữ dữ liệu cần cho popup để cookie phiên luôn nhỏ và không chứa release notes.
    compact = {
        key: result.get(key)
        for key in (
            "status", "current", "latest", "available", "message", "url",
            "download_url", "download_name", "checked_at",
        )
        if result.get(key) is not None
    }
    compact["cache_id"] = cache_id
    session["jx_update_status"] = compact
    return jsonify(compact)


def _system_update_status():
    try:
        with open(SYSTEM_UPDATE_STATUS, encoding="utf-8") as status_file:
            value = json.load(status_file)
        if not isinstance(value, dict):
            raise ValueError("invalid status")
    except (OSError, ValueError, json.JSONDecodeError):
        value = {"state": "idle", "percent": 0, "phase": "Chưa cập nhật", "message": "", "logs": []}
    logs = value.get("logs", [])
    value["logs"] = logs[-12:] if isinstance(logs, list) else []
    value["installed_version"] = APP_VERSION
    return value


def _write_system_update_status(state, percent, phase, message):
    os.makedirs(os.path.dirname(SYSTEM_UPDATE_STATUS), mode=0o750, exist_ok=True)
    payload = {
        "state": state, "percent": max(0, min(100, int(percent))),
        "phase": phase, "message": message, "updated": int(time.time()), "logs": [],
    }
    temporary = SYSTEM_UPDATE_STATUS + ".tmp"
    with open(temporary, "w", encoding="utf-8") as status_file:
        json.dump(payload, status_file, ensure_ascii=False, indent=2)
        status_file.write("\n")
    os.chmod(temporary, 0o600)
    os.replace(temporary, SYSTEM_UPDATE_STATUS)


def _start_system_update(release):
    if not os.path.isfile(SYSTEM_UPDATE_TOOL):
        raise RuntimeError("Thiếu tools/apply-update; hãy cập nhật thủ công lần này.")
    if sctl("is-active", "--quiet", SYSTEM_UPDATE_UNIT, timeout=5).returncode == 0:
        raise RuntimeError("Một tiến trình cập nhật đang chạy.")
    latest = str(release.get("latest") or "").strip()
    archive_url = str(release.get("download_url") or "").strip()
    checksum_url = str(release.get("checksum_url") or "").strip()
    expected = f"https://github.com/{UPDATE_REPOSITORY}/releases/download/v{latest}/JXNative-v{latest}.tar.gz"
    if archive_url != expected or checksum_url != expected + ".sha256":
        raise RuntimeError("Release chưa có đủ gói .tar.gz và SHA256 chính thức.")
    os.chmod(SYSTEM_UPDATE_TOOL, 0o755)
    sctl("reset-failed", SYSTEM_UPDATE_UNIT, timeout=10)
    _write_system_update_status("queued", 1, "Đã nhận yêu cầu", f"Chuẩn bị cập nhật lên v{latest}")
    result = subprocess.run([
        "systemd-run", "--unit=jxnative-update", "--collect", "--property=Type=exec",
        SYSTEM_UPDATE_TOOL, latest, UPDATE_REPOSITORY, archive_url, checksum_url,
    ], capture_output=True, text=True, timeout=20, check=False)
    if result.returncode != 0:
        raise RuntimeError((result.stderr or result.stdout or "Không tạo được tiến trình cập nhật").strip())


def _system_update_conflict():
    """Không cập nhật giữa lúc database đang được cài, đổi mật khẩu hoặc backup."""
    database_job = os.path.join(PROJECT_ROOT, "data", "state", "database-job.json")
    try:
        with open(database_job, encoding="utf-8") as job_file:
            job = json.load(job_file)
        if (isinstance(job, dict) and job.get("state") == "working"
                and time.time() - int(job.get("updated", 0)) < 3600):
            return "Tác vụ database đang chạy; hãy chờ tác vụ hoàn tất rồi cập nhật."
    except (OSError, TypeError, ValueError, json.JSONDecodeError):
        pass
    now = datetime.now().astimezone()
    for run in _backup_state().get("runs", []):
        if run.get("status") not in ("queued", "running"):
            continue
        stamp = run.get("started_at") or run.get("scheduled_at")
        try:
            started = datetime.fromisoformat(stamp)
            if started.tzinfo is None:
                started = started.astimezone()
            if (now - started).total_seconds() < 6 * 3600:
                return "Một lượt backup database đang chạy; hãy chờ backup hoàn tất rồi cập nhật."
        except (TypeError, ValueError):
            continue
    return ""


@app.route("/system/update")
def update_center():
    release = _github_release_status(APP_VERSION, force=request.args.get("refresh") == "1")
    latest = str(release.get("latest") or "").strip()
    archive_name = str(release.get("download_name") or f"JXNative-v{latest}.tar.gz")
    manual_commands = ""
    if latest and release.get("download_url") and release.get("checksum_url"):
        manual_commands = "\n".join((
            "cd /opt",
            f"sudo wget -O {archive_name} {release['download_url']}",
            f"sudo wget -O {archive_name}.sha256 {release['checksum_url']}",
            f"sudo sha256sum -c {archive_name}.sha256",
            f"sudo tar -xzf {archive_name} -C /opt",
            "cd /opt/QuanLy_One",
            "sudo bash update.sh",
        ))
    status = _system_update_status()
    body = """
    <style>
    .update-center{max-width:860px;margin:0 auto}.update-compact{padding:18px 20px}.update-head{display:flex;align-items:center;gap:14px}.update-head>div{min-width:0;flex:1}.update-head h1{margin:0 0 4px;font-size:23px}.update-version{font-size:13px;color:var(--mut)}.update-version b{color:var(--fg)}.update-actions{display:flex;gap:8px;flex-wrap:wrap;margin-top:16px}.update-actions .btn,.update-actions button{min-width:130px;text-align:center}.update-state{margin-top:16px;padding:13px;border:1px solid var(--line);border-radius:10px;background:rgba(255,255,255,.025)}.update-state[hidden]{display:none}.update-state-head{display:flex;justify-content:space-between;gap:12px;margin-bottom:8px}.update-state progress{width:100%;height:10px}.update-state p{margin:7px 0 0;color:var(--mut);font-size:12px}.update-log{margin:10px 0 0;max-height:150px;overflow:auto;font:11px/1.5 ui-monospace,Consolas,monospace;color:#b8c5d2}.update-manual{margin-top:12px;border:1px solid var(--line);border-radius:10px}.update-manual summary{cursor:pointer;padding:12px 14px;font-weight:700}.update-manual pre{margin:0 12px 12px;max-height:none}.update-error{min-height:18px;color:var(--err);font-size:12px;margin:9px 0 0}@media(max-width:560px){.update-head{align-items:flex-start}.update-actions>*{width:100%}}
    </style>
    <div class="update-center"><section class="card update-compact">
      <div class="update-head"><span class="update-dialog-icon">{{'↑' if release.status=='ok' and release.available else '✓'}}</span><div><h1>Cập nhật JXNative</h1><div class="update-version">Đang dùng <b>v{{app_version}}</b>{% if release.status=='ok' %} · Mới nhất <b>v{{release.latest}}</b>{% endif %}</div></div></div>
      {% if release.status=='ok' and release.available %}<p>Có bản mới sẵn sàng. Hãy backup dữ liệu quan trọng trước khi cập nhật.</p>{% elif release.status=='ok' %}<p>Máy đang dùng phiên bản mới nhất.</p>{% else %}<p class="update-error">{{release.message or 'Không kiểm tra được GitHub Release.'}}</p>{% endif %}
      <div class="update-actions">
        {% if release.url %}<a class="btn mut" href="{{release.url}}" target="_blank" rel="noopener">Xem Release</a>{% endif %}
        {% if release.download_url %}<a class="btn mut" href="{{release.download_url}}">Tải về</a>{% endif %}
        {% if release.status=='ok' and release.available and release.download_url and release.checksum_url %}<button class="ok" id="startWebUpdate">Cập nhật ngay</button>{% endif %}
      </div><p class="update-error" id="updateError"></p>
      <div class="update-state" id="updateState" {% if status.state=='idle' %}hidden{% endif %}><div class="update-state-head"><b id="updatePhase">{{status.phase}}</b><span id="updatePercent">{{status.percent}}%</span></div><progress id="updateProgress" max="100" value="{{status.percent}}"></progress><p id="updateMessage">{{status.message}}</p><div class="update-log" id="updateLog"></div></div>
      {% if manual_commands %}<details class="update-manual"><summary>Tự cập nhật bằng lệnh</summary><pre class="log">{{manual_commands}}</pre></details>{% endif %}
    </section></div>
    <script>
    (function(){const start=document.getElementById('startWebUpdate'),stateBox=document.getElementById('updateState'),phase=document.getElementById('updatePhase'),percent=document.getElementById('updatePercent'),bar=document.getElementById('updateProgress'),message=document.getElementById('updateMessage'),log=document.getElementById('updateLog'),error=document.getElementById('updateError');let polling=false,finished=false;
      function render(data){stateBox.hidden=false;phase.textContent=data.phase||'Đang cập nhật';percent.textContent=Number(data.percent||0)+'%';bar.value=Number(data.percent||0);message.textContent=data.message||'';const rows=Array.isArray(data.logs)?data.logs:[];log.textContent=rows.map(row=>`[${row.time||''}] ${row.phase||''}${row.message?' — '+row.message:''}`).join('\n');log.scrollTop=log.scrollHeight;if(data.state==='error'){error.textContent=data.message||'Cập nhật thất bại';if(start)start.disabled=false;finished=true}else if(data.state==='success'){error.textContent='';if(start)start.disabled=true;finished=true;setTimeout(()=>location.href={{url_for('update_center')|tojson}},1800)}else if(start){start.disabled=true}}
      async function poll(){if(polling||finished)return;polling=true;try{const response=await fetch({{url_for('system_update_status')|tojson}},{cache:'no-store',headers:{Accept:'application/json'}});if(response.ok)render(await response.json())}catch(e){stateBox.hidden=false;phase.textContent='Web đang khởi động lại';message.textContent='Đang chờ Web hoạt động trở lại…'}finally{polling=false;if(!finished)setTimeout(poll,1800)}}
      async function launch(password,stopServer){error.textContent='';start.disabled=true;const body=new FormData();body.set('csrf_token',{{manager_csrf|tojson}});body.set('admin_password',password);body.set('stop_server',stopServer?'1':'0');try{const response=await fetch({{url_for('system_update_start')|tojson}},{method:'POST',body,headers:{Accept:'application/json'}}),data=await response.json();if(response.status===409&&data.requires_stop){const approved=await window.JXDialog.confirm('Server game đang chạy. QuanLy One sẽ Stop All an toàn rồi cập nhật. Tiếp tục?',{danger:true,confirmText:'Stop All và cập nhật'});if(approved)return launch(password,true)}if(!response.ok)throw new Error(data.error||'Không bắt đầu được cập nhật');stateBox.hidden=false;finished=false;render({state:'queued',percent:1,phase:'Đã nhận yêu cầu',message:'Tiến trình cập nhật đang bắt đầu',logs:[]});poll()}catch(e){error.textContent=e.message||String(e);start.disabled=false}}
      if(start)start.addEventListener('click',async()=>{const password=await window.JXDialog.prompt('Nhập mật khẩu Admin hiện tại để xác nhận cập nhật hệ thống.',{title:'Xác nhận cập nhật',inputType:'password',confirmText:'Tiếp tục'});if(password!==null&&password!=='')launch(password,false)});{% if status.state in ('queued','working') %}poll();{% endif %}
    })();
    </script>
    """
    return page(body, page="update", release=release, status=status, manual_commands=manual_commands)


@app.post("/system/update/start")
def system_update_start():
    supplied = request.form.get("csrf_token", "")
    expected = session.get("csrf_token", "")
    if not supplied or not expected or not hmac.compare_digest(supplied, expected):
        return jsonify(error="Phiên biểu mẫu không hợp lệ."), 400
    if not verify_manager_password(request.form.get("admin_password", "")):
        return jsonify(error="Mật khẩu Admin hiện tại không đúng."), 403
    conflict = _system_update_conflict()
    if conflict:
        return jsonify(error=conflict), 409
    release = _github_release_status(APP_VERSION, force=True)
    if release.get("status") != "ok" or not release.get("available"):
        return jsonify(error="Không còn bản cập nhật mới hơn phiên bản đang dùng."), 409
    running = [unit for unit, _label in COMPONENTS if unit_active(unit)]
    if running and request.form.get("stop_server") != "1":
        return jsonify(error="Server đang chạy; cần Stop All trước khi cập nhật.",
                       requires_stop=True, running=running), 409
    if running:
        stopped, errors = stop_all_gracefully()
        if errors:
            return jsonify(error="Không Stop All an toàn được: " + "; ".join(errors)), 500
        still_running = [unit for unit, _label in COMPONENTS if unit_active(unit)]
        if still_running:
            return jsonify(error="Một số dịch vụ chưa dừng: " + ", ".join(still_running)), 500
    try:
        _start_system_update(release)
    except (OSError, RuntimeError, subprocess.TimeoutExpired) as exc:
        return jsonify(error=str(exc)), 500
    return jsonify(ok=True, latest=release.get("latest")), 202


@app.get("/api/system-update/status")
def system_update_status():
    response = jsonify(_system_update_status())
    response.headers["Cache-Control"] = "no-store, max-age=0"
    return response


@app.route("/events", methods=["GET", "POST"])
def events():
    if request.method == "POST":
        try:
            if request.form.get("event_action") == "rates":
                field_count, file_count = _write_event_rates(request.form)
                restart = sctl("restart", "jxgame", timeout=90)
                if restart.returncode != 0:
                    detail = (restart.stderr or restart.stdout or "systemctl restart jxgame thất bại").strip()
                    flash("err", f"Đã lưu {field_count} tỷ lệ trong {file_count} file, nhưng restart thất bại: {detail}")
                else:
                    flash("ok", f"Đã lưu {field_count} tỷ lệ của 12 event và restart jxgame để áp dụng.")
                return redirect(url_for("events"))
            values = {
                name: 1 if request.form.get(f"event_{name}") == "1" else 0
                for name, _label, _description in EVENT_FLAGS
            }
            selected_month_text = (request.form.get("event_month") or "").strip()
            if not re.fullmatch(r"(?:[0-9]|1[0-2])", selected_month_text):
                raise ValueError("Lựa chọn event tháng không hợp lệ")
            selected_month = int(selected_month_text)
            _write_event_flags(values, selected_month)
            restart = sctl("restart", "jxgame", timeout=90)
            enabled_count = sum(values.values())
            if restart.returncode != 0:
                detail = (
                    restart.stderr or restart.stdout or "systemctl restart jxgame thất bại"
                ).strip()
                flash(
                    "err",
                    f"Đã lưu {enabled_count} mục đang bật, nhưng restart jxgame thất bại: {detail}",
                )
            else:
                flash(
                    "ok",
                    f"Đã lưu cấu hình event ({enabled_count}/{len(EVENT_FLAGS)} mục đang bật) "
                    "và restart jxgame để áp dụng.",
                )
        except Exception as e:
            flash("err", f"Không lưu được cấu hình event: {e}")
        return redirect(url_for("events"))

    try:
        values, selected_month = _read_event_flags()
        config_error = ""
    except Exception as e:
        values = {name: 0 for name, _label, _description in EVENT_FLAGS}
        selected_month = 0
        config_error = str(e)
    try:
        rate_rows = _read_event_rates()
        rate_error = ""
    except Exception as e:
        rate_rows = _event_rate_fields()
        rate_error = str(e)
    event_rows = [
        {
            "name": name,
            "label": label,
            "description": description,
            "enabled": bool(values[name]),
        }
        for name, label, description in EVENT_FLAGS
    ]
    current_month = datetime.now().month
    active_month = selected_month if selected_month else current_month
    monthly_rows = [
        {
            "month": month,
            "name": name,
            "calendar_month": month == current_month,
            "active": month == active_month,
            "guide": EVENT_GUIDES[month - 1],
        }
        for month, name in enumerate(MONTHLY_EVENTS, 1)
    ]
    annual_enabled = bool(values.get("EventTuDong"))
    body = """
    {% if config_error %}
    <div class="card" style="border-color:var(--err);background:rgba(255,92,114,.08)">
      <h2 style="color:var(--err)">Không đọc được cấu hình event</h2>
      <p>{{config_error}}</p>
    </div>
    {% endif %}
    <div class="card"><h2>Trạng thái event</h2>
      <table>
        <tr><td>Game server</td><td>{% if game_running %}<span class="pill on">jxgame đang chạy</span>{% else %}<span class="pill off">jxgame đang tắt</span>{% endif %}</td></tr>
        <tr><td>Chế độ event tháng</td><td>{% if selected_month == 0 %}<b>Tự động theo tháng thực tế</b>{% else %}<b>Cố định tháng {{selected_month}}</b>{% endif %}</td></tr>
        <tr><td>Event được chọn</td><td>{% if annual_enabled %}<span class="pill on">Đang bật — {{active_event}}</span>{% else %}<span class="pill off">Event 12 tháng đang tắt</span>{% endif %}</td></tr>
        <tr><td>File cấu hình</td><td><span class="muted">{{config_path}}</span></td></tr>
      </table>
      <p class="muted">Web chỉ sửa các khóa bật/tắt đã xác định trong cấu hình gốc. Sau khi lưu, jxgame được restart để nạp lại NPC, lịch và script event.</p>
    </div>
    <div class="card"><h2>Bật / tắt event</h2>
      <form method="post" data-confirm="Lưu cấu hình event và restart jxgame để áp dụng? Người chơi đang online sẽ bị ngắt kết nối.">
        <label>Chế độ chọn event tháng</label>
        <select name="event_month" {% if config_error %}disabled{% endif %} style="margin-bottom:16px">
          <option value="0" {% if selected_month == 0 %}selected{% endif %}>Tự động — chạy event theo tháng thực tế</option>
          {% for item in monthly_rows %}<option value="{{item.month}}" {% if selected_month == item.month %}selected{% endif %}>Cố định tháng {{item.month}} — {{item.name}}</option>{% endfor %}
        </select>
        <p class="muted">Chế độ cố định chỉ kích hoạt đúng một event đã chọn; các event tháng còn lại sẽ đóng.</p>
        <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(320px,1fr));gap:10px 18px">
        {% for item in event_rows %}
          <label class="toggle-line" style="margin:0;padding:12px;border:1px solid var(--line);border-radius:10px">
            <input type="checkbox" name="event_{{item.name}}" value="1" {% if item.enabled %}checked{% endif %} {% if config_error %}disabled{% endif %}>
            <span><b>{{item.label}}</b><br><span class="muted">{{item.description}}</span></span>
          </label>
        {% endfor %}
        </div>
        <button class="ok" style="margin-top:18px" {% if config_error %}disabled{% endif %}>💾 Lưu và restart game</button>
      </form>
    </div>
    <div class="card"><h2>Lịch sự kiện tự động 12 tháng</h2>
      <div class="scroll"><table><tr><th>Tháng</th><th>Sự kiện</th><th>Trạng thái</th></tr>
      {% for item in monthly_rows %}<tr {% if item.active %}style="background:rgba(79,140,255,.08)"{% endif %}>
        <td>Tháng {{item.month}}</td><td>{{item.name}}</td>
        <td>{% if item.active and annual_enabled %}<span class="pill on">Đang áp dụng duy nhất</span>{% elif item.active %}<span class="pill off">Đã chọn nhưng đang tắt</span>{% elif item.calendar_month %}<span class="muted">Tháng hiện tại</span>{% else %}<span class="muted">Không hoạt động</span>{% endif %}</td>
      </tr>{% endfor %}</table></div>
    </div>
    <div class="card"><h2>Tỷ lệ rơi, mở hộp và hợp thành</h2>
      {% if rate_error %}
      <p style="color:var(--err)">Không đọc được tỷ lệ: {{rate_error}}</p>
      {% else %}
      <p class="muted">Tỷ trọng rơi là tham số gốc của hàm DropSingleItem: số lớn hơn làm vật phẩm dễ rơi hơn, không phải phần trăm tuyệt đối. Tỷ lệ mở hộp của từng hộp phải cộng đủ 100%; riêng Hộp Vật Liệu Lồng Đèn dùng tổng trọng số 10.000.</p>
      <form method="post" data-confirm="Lưu toàn bộ tỷ lệ event và restart jxgame? Người chơi đang online sẽ bị ngắt kết nối.">
        <input type="hidden" name="event_action" value="rates">
        {% for event in rate_rows %}
        <details {% if event.month == active_month %}open{% endif %} style="border:1px solid {% if event.month == active_month %}var(--acc){% else %}var(--line){% endif %};border-radius:10px;margin:10px 0;background:#131a27">
          <summary style="cursor:pointer;padding:12px 14px;font-weight:650">Tháng {{event.month}} — {{event.name}}</summary>
          <div style="padding:4px 14px 14px;border-top:1px solid var(--line)">
            {% for group in event.fields|groupby('group') %}
            <p style="margin:12px 0 5px"><b>{{group.grouper}}</b></p>
            <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(210px,1fr));gap:8px 14px">
              {% for field in group.list %}
              <label style="margin:0">{{field.label}}
                <input type="number" name="{{field.key}}" value="{{field.value}}" min="0" max="{{field.max}}" required style="margin-top:4px">
              </label>
              {% endfor %}
            </div>
            {% endfor %}
            {% if not event.fields %}<p class="muted">Event này dùng công thức cố định, không có phép quay hoặc tỷ lệ hợp thành riêng trong script.</p>{% endif %}
          </div>
        </details>
        {% endfor %}
        <button class="ok" style="margin-top:12px">💾 Lưu toàn bộ tỷ lệ và restart game</button>
      </form>
      {% endif %}
    </div>
    <div class="card"><h2>Hướng dẫn tham gia từng event</h2>
      <p class="muted">Nội dung được tổng hợp từ script đang chạy trên server này. Nguồn nguyên liệu phổ biến gồm đánh quái cấp 10–90, Tống Kim, Vượt Ải, Thủy Tặc, Viêm Đế, Võ Lâm Minh Chủ, Boss Thế Giới và nhiệm vụ Sát Thủ; từng event có thể chỉ dùng một phần các nguồn này.</p>
      {% for item in monthly_rows %}
      <details {% if item.active %}open{% endif %} style="border:1px solid {% if item.active %}var(--acc){% else %}var(--line){% endif %};border-radius:10px;margin:10px 0;background:#131a27">
        <summary style="cursor:pointer;padding:13px 15px;font-weight:650;list-style-position:inside">
          Tháng {{item.month}} — {{item.name}}
          {% if item.active and annual_enabled %}<span class="pill on" style="margin-left:8px">Đang chạy</span>{% endif %}
        </summary>
        <div style="padding:0 16px 15px;border-top:1px solid var(--line)">
          <p><b>Mục tiêu:</b> {{item.guide.goal}}</p>
          <p><b>NPC thực hiện:</b> {{item.guide.npc}}</p>
          {% if item.guide.materials %}
          <p style="margin-bottom:6px"><b>Vật phẩm và nguyên liệu cụ thể:</b></p>
          <ul style="margin-top:0;padding-left:22px;line-height:1.65">
            {% for material in item.guide.materials %}<li>{{material}}</li>{% endfor %}
          </ul>
          <p style="margin-bottom:6px"><b>Công thức và cách đổi:</b></p>
          <ul style="margin-top:0;padding-left:22px;line-height:1.65">
            {% for recipe in item.guide.recipes %}<li>{{recipe}}</li>{% endfor %}
          </ul>
          <p><b>Tác dụng và cách tính mốc:</b> {{item.guide.effect}}</p>
          {% endif %}
          {% if item.guide.locations %}
          <p style="margin-bottom:6px"><b>Vị trí NPC (tọa độ hiển thị trong game):</b></p>
          <ul style="margin-top:0;padding-left:22px;line-height:1.65">
            {% for location in item.guide.locations %}<li>{{location}}</li>{% endfor %}
          </ul>
          {% endif %}
          <p style="margin-bottom:6px"><b>Cách thực hiện:</b></p>
          <ol style="margin-top:0;padding-left:22px;line-height:1.65">
            {% for step in item.guide.steps %}<li>{{step}}</li>{% endfor %}
          </ol>
          <p class="muted">Vật phẩm đích sau khi sử dụng sẽ cộng tiến độ. Đến NPC event chọn “Nhận Thưởng Đạt Mốc”; các mốc hiện do cấu hình chung của server quyết định.</p>
        </div>
      </details>
      {% endfor %}
    </div>
    """
    return game_settings_page(
        body,
        "events",
        event_rows=event_rows,
        rate_rows=rate_rows,
        rate_error=rate_error,
        monthly_rows=monthly_rows,
        current_month=current_month,
        selected_month=selected_month,
        active_event=MONTHLY_EVENTS[active_month - 1],
        annual_enabled=annual_enabled,
        game_running=unit_active("jxgame"),
        config_path=EVENT_CONFIG_PATH,
        config_error=config_error,
    )

# ---------------- Bảng điều khiển ----------------
@app.route("/")
def dashboard():
    running = {unit: unit_active(unit) for unit, _label in COMPONENTS}
    resources = _service_resource_snapshot(running)
    comps = [(unit, label, running[unit], resources[unit]) for unit, label in COMPONENTS]
    dbst = [("mssql", "MSSQL account_tong", port_listening(1433)),
            ("mysql", "MySQL server1", port_listening(3306))]
    health = {"online": _online_player_count(), "uptime": _read_uptime_label()}
    operation = latest_game_operation()
    mod = game_mod_settings()
    body = r"""
    <div class="dashboard-operations">
    <div class="card component-card">
      <div class="operations-heading"><div><h2>Tổng quan vận hành</h2><span class="muted">Điều khiển, trạng thái và tài nguyên tiến trình trong một bảng.</span></div><a class="btn mut" href="{{url_for('console_page')}}">Console & Nhật ký →</a></div>
      <div id="operationNotice" class="operation-notice {{ operation.state if operation else '' }}" {% if not operation or (operation.state == 'success' and operation.age >= 5) %}hidden{% endif %}>
        <b id="operationText">{% if operation %}{{ '⏳' if operation.state == 'starting' else ('✅' if operation.state == 'success' else '❌') }} {{operation.message}}{% endif %}</b>
        <a id="operationLog" class="operation-log-link" style="{{ '' if operation and operation.state == 'error' else 'display:none' }}" href="{{ url_for('reload_log') if operation and operation.kind == 'reload' else url_for('startup_log') }}">Xem log →</a>
      </div>
      <div class="operations-summary">
        <div><small>Thành phần game</small><b id="healthServices" class="{{'health-good' if all_running else 'health-warn'}}">{{running_count}} / 6 đang chạy</b></div>
        <div><small>Người chơi online</small><b id="healthOnline">{{health.online if health.online is not none else '--'}}</b></div>
        <div><small>Uptime Linux</small><b id="healthUptime">{{health.uptime}}</b></div>
        <div><small>Database</small><b id="healthDatabase" class="{{'health-good' if dbst[0][2] and dbst[1][2] else 'health-warn'}}">{{'Ổn định' if dbst[0][2] and dbst[1][2] else 'Cần kiểm tra'}}</b></div>
      </div>
      <div class="server-main-actions">
        <form method="post" action="/control"><button class="ok" id="startAllButton" name="action" value="start_all" {{'disabled' if all_running else ''}}>▶ Start All</button></form>
        <form method="post" action="{{ url_for('reload_game') }}" data-confirm="Reload an toàn: dừng S3Relay → dừng GameServer → bật S3Relay → bật GameServer. Tiếp tục?"><button id="reloadButton" {% if not (comps[4][2] and comps[5][2]) %}disabled{% endif %}>↻ Reload</button></form>
        <form method="post" action="/control" data-confirm="Stop All và chờ toàn bộ server lưu dữ liệu?"><button class="err" id="stopAllButton" name="action" value="stop_all" {{'disabled' if not any_running else ''}}>■ Stop All</button></form>
        <form class="emergency-stop-form" method="post" action="{{url_for('emergency_stop_game')}}" data-confirm="DỪNG KHẨN CẤP sẽ cưỡng bức tắt cả 6 thành phần game và xóa trạng thái đang bị kẹt. Chỉ dùng khi các nút điều khiển bị khóa hoặc Stop All không hoàn tất. Tiếp tục?" data-confirm-button="Dừng khẩn cấp" data-dialog-danger="1"><input type="hidden" name="csrf_token" value="{{manager_csrf}}"><button type="submit" class="emergency-stop-button danger" title="Dừng khẩn cấp và mở khóa điều khiển" aria-label="Dừng khẩn cấp">!!!</button></form>
      </div>
      <table class="service-table resource-service-table"><tr><th>Thành phần</th><th title="Trạng thái">●</th><th>CPU</th><th>RAM</th><th>Thao tác</th></tr>
      {% for unit,label,run,resource in comps %}<tr class="service-row" data-console-url="{{url_for('console_page', source=unit)}}" tabindex="0" title="{{label}} — bấm cả dòng để mở console">
        <td><button type="button" class="service-source" style="color:{{log_colors[unit]}}">{{short_labels[unit]}}</button></td>
        <td class="service-state"><span id="state-{{unit}}" class="state-dot {{'on' if run else ''}}" title="{{'Đang chạy' if run else 'Đang tắt'}}"></span></td>
        <td class="service-metric"><span id="cpu-{{unit}}">{{'%.1f'|format(resource.cpu)}}%</span></td>
        <td class="service-metric"><span id="ram-{{unit}}">{{'%.1f'|format(resource.ram_mb)}} MB</span></td>
        <td class="service-action"><form method="post" action="/control" style="margin:0">
          <input type="hidden" name="unit" value="{{unit}}">
          <button id="action-{{unit}}" class="{{'err' if run else 'ok'}}" name="action" value="{{'stop' if run else 'start'}}">{{'Tắt' if run else 'Bật'}}</button>
        </form></td></tr>{% endfor %}
      </table>
      <h2 style="margin-top:18px">Database</h2><table class="compact-status">
      {% for key,label,ok in dbst %}<tr class="database-row" data-console-url="{{url_for('console_page', source=key)}}" tabindex="0" title="{{label}} — bấm để mở console"><td><button type="button" class="database-source" style="color:{{log_colors[key]}}">{{label}}</button></td><td class="service-state"><span id="db-state-{{key}}" class="state-dot {{'on' if ok else ''}}" title="{{'Kết nối OK' if ok else 'Mất kết nối'}}"></span></td></tr>{% endfor %}
      </table>
      <div class="mod-summary"><div class="mod-summary-info"><span class="mod-summary-title" title="{{mod.summary}}">🧩 MOD game — {{mod.summary}}</span><div class="mod-summary-meta"><span class="pill {{'on' if mod.enabled else 'off'}}">{{'Đang bật' if mod.enabled else 'Đang tắt'}}</span><span class="pill">{{mod.libraries|length}} file</span>{% for label in mod.source_labels %}<span class="pill">{{label}}</span>{% endfor %}{% if mod.invalid_count %}<span class="pill off">{{mod.invalid_count}} file bị thiếu</span>{% endif %}</div></div><button type="button" class="mut mod-config-button" id="openModSettings">Cấu hình</button></div>
      <div class="mod-modal" id="modSettingsModal" hidden aria-hidden="true"><section class="mod-dialog" role="dialog" aria-modal="true" aria-labelledby="modDialogTitle"><div class="mod-dialog-head"><h2 id="modDialogTitle">🧩 Cấu hình MOD game</h2><button type="button" class="mut" data-close-mod>✕</button></div>
        <form id="modSettingsForm" method="post" action="{{ url_for('mod_settings') }}" data-libraries='{{mod.available|tojson}}' data-initial='{{ {"enabled":mod.enabled,"libraries":mod.libraries}|tojson }}' data-max-libraries="{{mod.max_libraries}}">
          <div class="mod-dialog-body"><input type="hidden" name="libraries" id="modLibrariesValue" value="[]"><div class="mod-server-note">Server đang chọn: <b>{{header_server.name if header_server else 'Chưa chọn'}}</b><br><span class="muted">Mỗi phiên bản lưu danh sách MOD và thứ tự nạp riêng. Nếu GameServer đang chạy, cấu hình mới chỉ có hiệu lực sau khi khởi động lại.</span></div>
          <label class="mod-enable-line"><input type="checkbox" name="enabled" {% if mod.enabled %}checked{% endif %}> Nạp MOD khi chạy GameServer</label>
          <label style="margin-top:0">Nguồn của file muốn thêm</label><div class="mod-source-grid"><label class="mod-source-card"><input type="radio" name="source" value="version" checked><b>Trong phiên bản active</b><small>File `.so` trong thư mục `server1` đang sử dụng.</small></label><label class="mod-source-card"><input type="radio" name="source" value="shared"><b>Kho MOD dùng chung</b><small>File trong `JX_Servers/MOD`, có thể dùng cho nhiều phiên bản.</small></label></div>
          <div class="mod-add-row"><label><span id="modLibraryLabel">File trong phiên bản active</span><input type="text" id="modLibraryInput" list="modLibraryChoices" autocomplete="off" spellcheck="false" placeholder="Chọn hoặc nhập tên file .so"><datalist id="modLibraryChoices"></datalist></label><button type="button" class="ok" id="addModLibrary">＋ Thêm</button></div>
          <p class="mod-add-help" id="modSourceHelp"></p><p class="mod-form-error" id="modFormError" role="alert"></p>
          <div class="mod-list-heading"><b>Danh sách sẽ nạp theo thứ tự</b><span>Dùng ↑ ↓ để đổi thứ tự LD_PRELOAD</span></div><div class="mod-list" id="modLibraryList"></div></div>
          <div class="mod-dialog-foot"><button type="button" class="mut" data-close-mod>Hủy</button><button type="submit">Lưu cấu hình</button></div>
        </form></section></div>
    </div></div>
    <script>
    (function(){
      document.querySelectorAll('[data-console-url]').forEach(row=>{const open=()=>location.href=row.dataset.consoleUrl;row.addEventListener('click',event=>{if(!event.target.closest('button,form'))open()});row.addEventListener('keydown',event=>{if(event.key==='Enter'||event.key===' '){event.preventDefault();open()}})});
      const modForm=document.getElementById('modSettingsForm');if(modForm){
        const modal=document.getElementById('modSettingsModal'),openButton=document.getElementById('openModSettings'),libraryInput=document.getElementById('modLibraryInput'),choicesList=document.getElementById('modLibraryChoices'),libraryLabel=document.getElementById('modLibraryLabel'),sourceHelp=document.getElementById('modSourceHelp'),list=document.getElementById('modLibraryList'),hidden=document.getElementById('modLibrariesValue'),error=document.getElementById('modFormError'),addButton=document.getElementById('addModLibrary'),sourceInputs=Array.from(modForm.querySelectorAll('input[name="source"]')),maxLibraries=Number(modForm.dataset.maxLibraries||32);let available={version:[],shared:[]},initial={enabled:false,libraries:[]},draft=[];try{available=JSON.parse(modForm.dataset.libraries||'{}')}catch(e){}try{initial=JSON.parse(modForm.dataset.initial||'{}')}catch(e){};
        function currentSource(){return sourceInputs.find(input=>input.checked)?.value||'version'}
        function sourceLabel(source){return source==='shared'?'Kho MOD':'Trong phiên bản'}
        function setError(message){error.textContent=message||''}
        function entryAvailable(item){return Array.isArray(available[item.source])&&available[item.source].includes(item.name)}
        function syncSource(){const source=currentSource(),choices=Array.isArray(available[source])?available[source]:[];sourceInputs.forEach(input=>input.closest('.mod-source-card').classList.toggle('selected',input.checked));choicesList.replaceChildren();for(const name of choices){const option=document.createElement('option');option.value=name;choicesList.appendChild(option)}libraryLabel.textContent=source==='shared'?'File trong kho MOD dùng chung':'File trong phiên bản active';sourceHelp.textContent=choices.length?`Đã tìm thấy ${choices.length} file ELF 32-bit. Có thể chọn trong danh sách hoặc tự nhập đúng tên file.`:'Nguồn này chưa có file .so ELF 32-bit hợp lệ.';libraryInput.value='';setError('')}
        function renderMods(){hidden.value=JSON.stringify(draft);list.replaceChildren();if(!draft.length){const empty=document.createElement('div');empty.className='mod-empty-list';empty.textContent='Chưa có file .so nào trong danh sách.';list.appendChild(empty);return}draft.forEach((item,index)=>{const row=document.createElement('div');row.className='mod-entry';const number=document.createElement('span');number.className='mod-entry-index';number.textContent=String(index+1);const main=document.createElement('div');main.className='mod-entry-main';const name=document.createElement('span');name.className='mod-entry-name';name.textContent=item.name;const badge=document.createElement('span');const exists=entryAvailable(item);badge.className='mod-entry-source '+(exists?(item.source==='shared'?'shared':''):'missing');badge.textContent=exists?sourceLabel(item.source):sourceLabel(item.source)+' · Thiếu file';main.append(name,badge);const actions=document.createElement('div');actions.className='mod-entry-actions';[['↑','Lên',-1],['↓','Xuống',1],['✕','Xóa',0]].forEach(([textValue,title,move])=>{const button=document.createElement('button');button.type='button';button.textContent=textValue;button.title=title;if(move===0)button.className='remove';button.disabled=(move<0&&index===0)||(move>0&&index===draft.length-1);button.addEventListener('click',()=>{if(move===0)draft.splice(index,1);else{const target=index+move;[draft[index],draft[target]]=[draft[target],draft[index]]}setError('');renderMods()});actions.appendChild(button)});row.append(number,main,actions);list.appendChild(row)})}
        function resetDraft(){modForm.reset();sourceInputs[0].checked=true;draft=Array.isArray(initial.libraries)?initial.libraries.map(item=>({source:item.source,name:item.name})):[];syncSource();renderMods()}
        function addLibrary(){const source=currentSource(),name=libraryInput.value.trim(),choices=Array.isArray(available[source])?available[source]:[];if(!name){setError('Hãy chọn hoặc nhập tên file .so.');libraryInput.focus();return}if(!choices.includes(name)){setError(`Không tìm thấy “${name}” trong ${sourceLabel(source).toLowerCase()}.`);libraryInput.focus();return}if(draft.some(item=>item.source===source&&item.name===name)){setError(`File ${name} đã có trong danh sách.`);return}if(draft.length>=maxLibraries){setError(`Chỉ được nạp tối đa ${maxLibraries} file .so.`);return}draft.push({source,name});libraryInput.value='';setError('');renderMods();libraryInput.focus()}
        function closeMod(reset){modal.hidden=true;modal.setAttribute('aria-hidden','true');document.body.style.overflow='';if(reset)resetDraft()}
        function openMod(){resetDraft();modal.hidden=false;modal.setAttribute('aria-hidden','false');document.body.style.overflow='hidden';setTimeout(()=>libraryInput.focus(),0)}
        openButton.addEventListener('click',openMod);modal.querySelectorAll('[data-close-mod]').forEach(button=>button.addEventListener('click',()=>closeMod(true)));modal.addEventListener('click',event=>{if(event.target===modal)closeMod(true)});document.addEventListener('keydown',event=>{const dialogOverlay=document.getElementById('jxDialogOverlay'),dialogIsOpen=dialogOverlay&&!dialogOverlay.hidden;if(event.key==='Escape'&&!modal.hidden&&!dialogIsOpen)closeMod(true)});sourceInputs.forEach(input=>input.addEventListener('change',syncSource));addButton.addEventListener('click',addLibrary);libraryInput.addEventListener('keydown',event=>{if(event.key==='Enter'){event.preventDefault();addLibrary()}});resetDraft();
        modForm.addEventListener('submit',event=>{setError('');if(modForm.elements.enabled.checked&&!draft.length){event.preventDefault();setError('Đã bật MOD nhưng danh sách file .so đang trống.');return}const missing=draft.find(item=>!entryAvailable(item));if(missing){event.preventDefault();setError(`Không còn tìm thấy file ${missing.name}. Hãy xóa mục này hoặc chép lại file.`);return}hidden.value=JSON.stringify(draft)})
      }
      let statusLoading=false;async function refreshDashboard(){if(statusLoading)return;statusLoading=true;try{const response=await fetch({{ url_for('dashboard_status')|tojson }},{cache:'no-store',headers:{Accept:'application/json'}});if(!response.ok)return;const data=await response.json(),values=Object.values(data.components),runningCount=values.filter(Boolean).length,busy=!!(data.operation&&data.operation.state==='starting'),busyScope=new Set((data.session&&data.session.scope)||[]);for(const [unit,running] of Object.entries(data.components)){const dot=document.getElementById('state-'+unit),button=document.getElementById('action-'+unit),unitBusy=busy&&busyScope.has(unit),metric=data.resources?.[unit]||{};if(dot){dot.className='state-dot '+(unitBusy?'busy':running?'on':'');dot.title=unitBusy?'Đang xử lý':running?'Đang chạy':'Đang tắt'}if(button){button.value=running?'stop':'start';button.textContent=running?'Tắt':'Bật';button.className=running?'err':'ok';button.disabled=busy}const cpu=document.getElementById('cpu-'+unit),ram=document.getElementById('ram-'+unit);if(cpu)cpu.textContent=Number(metric.cpu||0).toFixed(1)+'%';if(ram)ram.textContent=Number(metric.ram_mb||0).toFixed(1)+' MB'}for(const [kind,running] of Object.entries(data.databases)){const dot=document.getElementById('db-state-'+kind);if(dot){dot.className='state-dot '+(running?'on':'');dot.title=running?'Kết nối OK':'Mất kết nối'}}document.getElementById('startAllButton').disabled=busy||runningCount===6;document.getElementById('reloadButton').disabled=busy||!(data.components.jxs3relay&&data.components.jxgame);document.getElementById('stopAllButton').disabled=busy||runningCount===0;if(modForm)modForm.dataset.gameRunning=data.components.jxgame?'1':'0';const serviceHealth=document.getElementById('healthServices'),databaseHealth=document.getElementById('healthDatabase'),databasesOK=data.databases.mssql&&data.databases.mysql;serviceHealth.textContent=runningCount+' / 6 đang chạy';serviceHealth.className=runningCount===6?'health-good':'health-warn';document.getElementById('healthOnline').textContent=data.health.online??'--';document.getElementById('healthUptime').textContent=data.health.uptime||'--';databaseHealth.textContent=databasesOK?'Ổn định':'Cần kiểm tra';databaseHealth.className=databasesOK?'health-good':'health-warn';const notice=document.getElementById('operationNotice'),text=document.getElementById('operationText'),link=document.getElementById('operationLog'),showOperation=data.operation&&!(data.operation.state==='success'&&data.operation.age>=5);if(showOperation){notice.hidden=false;notice.className='operation-notice '+data.operation.state;text.textContent=(data.operation.state==='starting'?'⏳ ':data.operation.state==='success'?'✅ ':'❌ ')+data.operation.message;link.style.display=data.operation.state==='error'?'inline-block':'none';link.href=data.operation.kind==='reload'?{{ url_for('reload_log')|tojson }}:{{ url_for('startup_log')|tojson }}}else notice.hidden=true}catch(e){}finally{statusLoading=false}}
      refreshDashboard();setInterval(refreshDashboard,2000);
    })();
    </script>
    """
    return page(body, page="dash", comps=comps, dbst=dbst, operation=operation, mod=mod,
                log_colors=LOG_COLORS, short_labels=COMPONENT_SHORT_LABELS,
                game_running=running["jxgame"], all_running=all(running.values()),
                any_running=any(running.values()), running_count=sum(running.values()), health=health)

@app.route("/dashboard/status")
def dashboard_status():
    components = {unit: unit_active(unit) for unit, _label in COMPONENTS}
    return jsonify({
        "components": components,
        "resources": _service_resource_snapshot(components),
        "databases": {"mssql": port_listening(1433), "mysql": port_listening(3306)},
        "health": {"online": _online_player_count(), "uptime": _read_uptime_label()},
        "operation": latest_game_operation(),
        "session": _log_session_view(),
    })


def _write_game_operation_status(path, state, message):
    """Ghi trạng thái nguyên tử để dashboard không đọc trúng file dở dang."""
    os.makedirs(os.path.dirname(path), mode=0o750, exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as status_file:
        status_file.write(f"{state}\n{message}\n{int(time.time())}\n")
    os.replace(tmp, path)


def _game_operation_helper_pids():
    """Chỉ tìm đúng helper Start/Reload của QuanLy One trong /proc."""
    scripts = {GAME_START_SCRIPT, GAME_RELOAD_SCRIPT}
    found = []
    for proc_entry in Path("/proc").glob("[0-9]*"):
        try:
            pid = int(proc_entry.name)
            if pid == os.getpid():
                continue
            args = proc_entry.joinpath("cmdline").read_bytes().split(b"\0")
            decoded = {arg.decode("utf-8", "surrogateescape") for arg in args if arg}
            if scripts.intersection(decoded):
                found.append(pid)
        except (OSError, ValueError):
            continue
    return found


def _terminate_game_operation_helpers():
    errors = []
    targets = []
    for pid in _game_operation_helper_pids():
        try:
            pgid = os.getpgid(pid)
            targets.append((pid, pgid))
            if pgid == pid:
                os.killpg(pgid, signal.SIGTERM)
            else:
                os.kill(pid, signal.SIGTERM)
        except ProcessLookupError:
            continue
        except OSError as exc:
            errors.append(f"helper PID {pid}: {exc}")
    if targets:
        time.sleep(0.5)
    for pid, pgid in targets:
        if not os.path.exists(f"/proc/{pid}"):
            continue
        try:
            if pgid == pid:
                os.killpg(pgid, signal.SIGKILL)
            else:
                os.kill(pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        except OSError as exc:
            errors.append(f"helper PID {pid}: {exc}")
    return errors


def force_stop_game_stack():
    """Cứu hộ khi Start/Reload kẹt: bỏ qua thời gian chờ lưu và cưỡng bức dừng."""
    labels = dict(COMPONENTS)
    units = [unit for unit, _pause in STOP_SEQUENCE]
    active_before = {unit: unit_active(unit) for unit in units}
    errors = _terminate_game_operation_helpers()

    for unit in units:
        try:
            # Stop không chờ trước, sau đó kill toàn bộ process còn nằm trong cgroup.
            sctl("stop", "--no-block", unit, timeout=8)
            sctl("kill", "--kill-whom=all", "--signal=SIGKILL", unit, timeout=8)
            result = sctl("stop", unit, timeout=15)
            if result.returncode != 0:
                detail = (result.stderr or result.stdout or "systemctl stop thất bại").strip()
                errors.append(f"{unit}: {detail}")
            sctl("reset-failed", unit, timeout=8)
        except (OSError, subprocess.TimeoutExpired) as exc:
            errors.append(f"{unit}: {exc}")

    for lock_path in (GAME_START_LOCK, GAME_RELOAD_LOCK):
        shutil.rmtree(lock_path, ignore_errors=True)
    for runtime_path in ("/tmp/s3relay_canclose", "/tmp/s3relay_tty"):
        try:
            os.unlink(runtime_path)
        except FileNotFoundError:
            pass
        except OSError as exc:
            errors.append(f"{runtime_path}: {exc}")

    remaining = [unit for unit in units if unit_active(unit)]
    if remaining:
        errors.append("còn chạy: " + ", ".join(remaining))
    message = ("Đã dừng khẩn cấp và mở khóa điều khiển."
               if not errors else "Dừng khẩn cấp chưa hoàn tất: " + "; ".join(errors))
    for status_path in (GAME_START_STATUS, GAME_RELOAD_STATUS):
        try:
            _write_game_operation_status(status_path, "error", message)
        except OSError as exc:
            errors.append(f"trạng thái: {exc}")
    try:
        Path("/run/jx-ready.status").write_text(
            f"STOPPED EMERGENCY {datetime.now():%F %T}\n", encoding="ascii")
    except OSError:
        pass
    stopped = [labels.get(unit, unit) for unit in units if active_before[unit] and unit not in remaining]
    return stopped, errors


@app.post("/control/emergency-stop")
def emergency_stop_game():
    supplied = request.form.get("csrf_token", "")
    expected = session.get("csrf_token", "")
    if not expected or not hmac.compare_digest(supplied, expected):
        flash("err", "Phiên xác nhận đã hết hạn. Hãy tải lại trang rồi thử lại.")
        return redirect(url_for("dashboard"))
    stopped, errors = force_stop_game_stack()
    detail = "Đã dừng khẩn cấp: " + (", ".join(stopped) or "không có dịch vụ đang chạy")
    if errors:
        detail += ". Lỗi: " + "; ".join(errors)
    _record_activity("Dừng khẩn cấp", detail, "error" if errors else "ok")
    if errors:
        flash("err", detail)
    else:
        flash("ok", "Đã cưỡng bức dừng toàn bộ game và mở khóa điều khiển. Bây giờ có thể dùng Start All.")
    return redirect(url_for("dashboard"))


@app.route("/control", methods=["POST"])
def control():
    action = request.form.get("action"); unit = request.form.get("unit")
    units = [u for u, _ in COMPONENTS]
    if action == "start_all":
        problem = game_start_preflight()
        if problem:
            flash("err", problem)
        else:
            try:
                _begin_log_session("Start All", units, "session")
                log_handle = open(GAME_START_LOG, "ab", buffering=0)
                subprocess.Popen(
                    [GAME_START_SCRIPT],
                    stdout=log_handle,
                    stderr=subprocess.STDOUT,
                    start_new_session=True,
                    close_fds=True,
                )
                log_handle.close()
                # Tiến độ đã được hiển thị trực tiếp trong khung Tổng quan vận hành.
            except OSError as exc:
                flash("err", "Không chạy được quy trình khởi động: " + str(exc))
    elif action == "stop_all":
        stopped, errors = stop_all_gracefully()
        detail = "Đã dừng: " + (", ".join(stopped) or "không có dịch vụ đang chạy")
        if errors:
            detail += ". Lỗi: " + "; ".join(errors)
        _record_activity("Stop All", detail, "error" if errors else "ok")
        if errors:
            flash("err", "Đã dừng: " + (", ".join(stopped) or "không có")
                  + ". Lỗi: " + "; ".join(errors))
        else:
            flash("ok", "Đã tắt tuần tự và an toàn: " + (", ".join(stopped) or "mọi service vốn đã tắt") + ".")
    elif action in ("start","stop") and unit in units:
        if action == "start" and unit in ("jxgoddess", "jxbishop", "jxs3relay", "jxgame"):
            problem = game_start_preflight(check_databases=False)
            if problem:
                flash("err", problem)
                return redirect(url_for("dashboard"))
        try:
            display_name = LOG_UNIT_LABELS.get(unit, dict(COMPONENTS).get(unit, unit).split(" (")[0])
            if action == "start":
                _begin_log_session("Bật " + display_name, [unit], unit)
            result = sctl(action, unit)
            if action == "stop":
                detail = (result.stderr or result.stdout or "systemctl đã hoàn tất").strip()
                _record_activity("Tắt " + display_name, detail,
                                 "ok" if result.returncode == 0 else "error")
            if result.returncode == 0:
                flash("ok", f"Đã {'bật' if action=='start' else 'tắt'} {unit}.")
            else:
                detail = (result.stderr or result.stdout or "systemctl trả về lỗi").strip()
                flash("err", f"Không thể {'bật' if action=='start' else 'tắt'} {unit}: {detail}")
        except subprocess.TimeoutExpired:
            state = "đang khởi động" if action == "start" else "đang dừng"
            flash("err", f"{unit} {state} quá 8 giây. Lệnh vẫn có thể đang được systemd xử lý; hãy chờ rồi tải lại trang.")
    return redirect(url_for("dashboard"))

@app.route("/reload-game", methods=["POST"])
def reload_game():
    try:
        _launch_game_reload()
        flash("ok", "Đã bắt đầu Reload Game an toàn; trang sẽ tự cập nhật trạng thái.")
    except (OSError, RuntimeError) as exc:
        flash("err", str(exc))
    return redirect(url_for("dashboard"))


def _launch_game_reload():
    if not unit_active("jxs3relay") or not unit_active("jxgame"):
        raise RuntimeError("Reload Game chỉ dùng khi S3Relay và GameServer đang chạy. Nếu server đang tắt, hãy dùng Start All.")
    current = game_reload_status()
    if current and current["state"] == "starting":
        raise RuntimeError("Một lần Reload Game đang chạy; hãy chờ hoàn tất.")
    if not os.path.isfile(GAME_RELOAD_SCRIPT):
        raise RuntimeError("Thiếu script Reload Game. Hãy chạy lại update.sh.")
    _begin_log_session("Reload S3Relay + GameServer", ["jxs3relay", "jxgame"], "session")
    log_handle = open(GAME_RELOAD_LOG, "ab", buffering=0)
    try:
        subprocess.Popen([GAME_RELOAD_SCRIPT], stdout=log_handle, stderr=subprocess.STDOUT,
                         start_new_session=True, close_fds=True)
    finally:
        log_handle.close()

@app.route("/logs/reload")
def reload_log():
    try:
        with open(GAME_RELOAD_LOG, encoding="utf-8", errors="replace") as log_file:
            content = log_file.read()[-50000:]
    except OSError:
        content = "Chưa có log Reload Game."
    return page('<h1 class="page-heading">Log Reload Game</h1><pre class="log">{{ content }}</pre>',
                page="dash", content=content)

@app.route("/mod-settings", methods=["POST"])
def mod_settings():
    detected = _detected_game_mods()
    enabled = request.form.get("enabled") == "on"
    try:
        submitted = json.loads(request.form.get("libraries") or "[]")
    except (TypeError, ValueError, json.JSONDecodeError):
        submitted = None
    if not isinstance(submitted, list):
        flash("err", "Danh sách MOD gửi lên không hợp lệ.")
        return redirect(url_for("dashboard"))
    if len(submitted) > GAME_MOD_MAX_LIBRARIES:
        flash("err", f"Chỉ được nạp tối đa {GAME_MOD_MAX_LIBRARIES} file .so.")
        return redirect(url_for("dashboard"))
    entries = []
    seen = set()
    for position, item in enumerate(submitted, 1):
        if not isinstance(item, dict):
            flash("err", f"MOD thứ {position} không hợp lệ.")
            return redirect(url_for("dashboard"))
        source = str(item.get("source") or "").strip()
        name = str(item.get("name") or "").strip()
        if source not in ("version", "shared"):
            flash("err", f"Nguồn của MOD thứ {position} không hợp lệ.")
            return redirect(url_for("dashboard"))
        if name not in detected[source]:
            flash("err", f"Không tìm thấy file MOD hợp lệ: {name or '(trống)'}. Hãy kiểm tra lại nguồn đã chọn.")
            return redirect(url_for("dashboard"))
        key = (source, name)
        if key in seen:
            flash("err", f"File MOD bị thêm trùng: {name}.")
            return redirect(url_for("dashboard"))
        seen.add(key)
        entries.append({"source": source, "name": name})
    if enabled and not entries:
        flash("err", "Đã bật MOD nhưng danh sách file .so đang trống.")
        return redirect(url_for("dashboard"))
    state = {"schema_version": 2, "enabled": enabled, "libraries": entries}
    current = game_mod_settings()
    previous = {"schema_version": 2, "enabled": current["enabled"], "libraries": current["libraries"]}
    changed = state != previous
    game_running = unit_active("jxgame")
    state_path = _game_mod_state_path()
    os.makedirs(os.path.dirname(state_path), mode=0o750, exist_ok=True)
    tmp = state_path + ".tmp"
    try:
        with open(tmp, "w", encoding="utf-8") as state_file:
            json.dump(state, state_file, ensure_ascii=True, sort_keys=True)
            state_file.write("\n")
        os.chmod(tmp, 0o600)
        os.replace(tmp, state_path)
        if changed and game_running:
            flash("ok", f"Đã lưu {len(entries)} file MOD. GameServer vẫn đang chạy; hãy khởi động lại GameServer để cấu hình mới có hiệu lực.")
        elif changed:
            flash("ok", f"Đã lưu {len(entries)} file MOD. Cấu hình sẽ áp dụng khi bật GameServer.")
        elif current["legacy"]:
            flash("ok", "Đã chuyển cấu hình MOD cũ sang danh sách mới.")
        else:
            flash("ok", "Cấu hình MOD không thay đổi.")
    except OSError as exc:
        try: os.unlink(tmp)
        except OSError: pass
        flash("err", "Không lưu được cấu hình MOD: " + str(exc))
    return redirect(url_for("dashboard"))

@app.route("/logs/startup")
def startup_log():
    try:
        with open(GAME_START_LOG, encoding="utf-8", errors="replace") as log_file:
            content = log_file.read()[-30000:]
    except OSError:
        content = "Chưa có log khởi động."
    return page('<h1 class="page-heading">Log khởi động JXNative</h1><pre class="log">{{ content }}</pre>',
                page="dash", content=content)

def stop_all_gracefully():
    """Dung tung tang theo chieu nguoc luong game, cho moi tien trinh tu thoat."""
    labels = dict(COMPONENTS)
    stopped, errors = [], []
    total = len(STOP_SEQUENCE)
    _console_status("\n========================================================\n"
                    "  BAT DAU TAT SERVER AN TOAN - DANG LUU DU LIEU\n"
                    "========================================================")
    for step, (unit, pause_seconds) in enumerate(STOP_SEQUENCE, 1):
        display = STOP_DISPLAY_NAMES.get(unit, unit)
        if not unit_active(unit):
            _console_status(f"  [{step}/{total}] {display:<10} - DA TAT, BO QUA")
            continue
        _console_status(f"  [{step}/{total}] DANG TAT {display} ...")
        try:
            if unit == "jxs3relay":
                _stop_s3relay_like_jxsh()
            result = sctl("stop", unit, timeout=90)
            if result.returncode != 0:
                detail = (result.stderr or result.stdout or "systemctl stop thất bại").strip()
                errors.append(f"{unit}: {detail}")
                _console_status(f"  [{step}/{total}] LOI - KHONG TAT DUOC {display}")
                continue
            deadline = time.time() + 20
            while unit_active(unit) and time.time() < deadline:
                time.sleep(1)
            if unit_active(unit):
                errors.append(f"{unit}: tiến trình chưa dừng sau thời gian chờ")
                _console_status(f"  [{step}/{total}] LOI - {display} CHUA DUNG")
                continue
            stopped.append(labels.get(unit, unit))
            _console_status(f"  [{step}/{total}] OK  - {display} DA DUNG")
            if pause_seconds:
                time.sleep(pause_seconds)
        except Exception as e:
            errors.append(f"{unit}: {e}")
            _console_status(f"  [{step}/{total}] LOI - {display}: {e}")
    if errors:
        _console_status("========================================================\n"
                        "  TAT SERVER CHUA HOAN TAT - KIEM TRA LOI TREN WEB\n"
                        "========================================================\n")
    else:
        _console_status("========================================================\n"
                        "  SERVER DA TAT AN TOAN - DU LIEU DA DUOC LUU\n"
                        "  WEB QUAN LY VAN DANG HOAT DONG\n"
                        "========================================================\n")
        try:
            with open("/run/jx-ready.status", "w", encoding="ascii") as status_file:
                status_file.write(f"STOPPED {datetime.now():%F %T}\n")
        except Exception:
            pass
    return stopped, errors

app.extensions["stop_game_stack"] = stop_all_gracefully

def _stop_s3relay_like_jxsh():
    """Gui exit + y vao PTY cua s3relay_y, sau do cho binary tu thoat."""
    import fcntl, termios

    def current_pid():
        result = subprocess.run(["pgrep", "-x", "s3relay_y"], capture_output=True, text=True)
        return result.stdout.splitlines()[0].strip() if result.returncode == 0 and result.stdout.strip() else None

    pid = current_pid()
    if not pid:
        return
    tty = ""
    try:
        with open("/tmp/s3relay_tty", "r", encoding="ascii") as tty_file:
            tty = tty_file.read().strip()
    except Exception:
        pass
    if not tty or not os.path.exists(tty):
        ps = subprocess.run(["ps", "-o", "tty=", "-p", pid], capture_output=True, text=True)
        tty_name = ps.stdout.strip()
        if tty_name and tty_name != "?":
            tty = "/dev/" + tty_name.lstrip("/dev/")
    if not tty or not os.path.exists(tty):
        raise RuntimeError("Không tìm thấy PTY của s3relay_y; chưa gửi được exit")

    def inject(text):
        fd = os.open(tty, os.O_WRONLY | os.O_NOCTTY)
        try:
            for char in text:
                try:
                    fcntl.ioctl(fd, termios.TIOCSTI, char.encode())
                except PermissionError:
                    subprocess.run(["sysctl", "-w", "dev.tty.legacy_tiocsti=1"],
                                   capture_output=True, check=False)
                    fcntl.ioctl(fd, termios.TIOCSTI, char.encode())
        finally:
            os.close(fd)

    inject("exit\n")
    time.sleep(2)
    inject("y\n")
    deadline = time.time() + 60
    while current_pid() and time.time() < deadline:
        time.sleep(2)
    if current_pid():
        subprocess.run(["pkill", "-TERM", "-x", "s3relay_y"], check=False)
        time.sleep(5)
    if current_pid():
        subprocess.run(["pkill", "-KILL", "-x", "s3relay_y"], check=False)
    try:
        open("/tmp/s3relay_canclose", "a").close()
    except Exception:
        pass

def _console_status(message):
    """Ghi mot lan ra console vat ly; tranh ghi trung tty1 va /dev/console."""
    for target in ("/dev/tty1", "/dev/console"):
        try:
            if os.path.exists(target) and os.access(target, os.W_OK):
                with open(target, "w", encoding="ascii", errors="replace", buffering=1) as console:
                    console.write(message + "\n")
                break
        except Exception:
            continue
    print("[SAFE STOP] " + message.replace("\n", " | "), flush=True)

def _host_action_blocked(verb):
    """Tra ve thong bao loi neu CHUA duoc phep tat/reset may, None neu OK."""
    still_on = [label for unit, label in COMPONENTS if unit_active(unit)]
    if still_on:
        return ("KHÔNG thể " + verb + ": còn " + str(len(still_on))
                + " thành phần đang chạy — " + ", ".join(still_on)
                + ". Hãy bấm “Tắt TẤT CẢ” trước.")
    host_ports = sorted({port for port, _label in KEY_PORTS} | {7777})
    busy = [str(p) for p in host_ports if port_listening(p)]
    if busy:
        return ("KHÔNG thể " + verb + ": cổng còn mở (" + ", ".join(busy)
                + "). Đợi vài giây rồi thử lại.")
    return None

@app.route("/shutdown", methods=["POST"])
def shutdown_host():
    err = _host_action_blocked("tắt máy")
    if err:
        _stopped, errors = stop_all_gracefully()
        if errors:
            flash("err", "Đã hủy tắt máy vì Stop All chưa hoàn tất: " + "; ".join(errors))
            return redirect(url_for("dashboard"))
        deadline = time.time() + 30
        while _host_action_blocked("tắt máy") and time.time() < deadline:
            time.sleep(1)
        err = _host_action_blocked("tắt máy")
        if err:
            flash("err", "Đã hủy tắt máy: " + err)
            return redirect(url_for("dashboard"))
    try:
        subprocess.Popen(["shutdown", "-h", "now"])
        flash("ok", "Đã gửi lệnh TẮT MÁY CHỦ. Máy sẽ tắt trong giây lát.")
    except Exception as e:
        flash("err", f"Lỗi khi tắt máy: {e}")
    return redirect(url_for("dashboard"))

@app.route("/reboot", methods=["POST"])
def reboot_host():
    err = _host_action_blocked("khởi động lại")
    if err:
        _stopped, errors = stop_all_gracefully()
        if errors:
            flash("err", "Đã hủy khởi động lại máy vì Stop All chưa hoàn tất: " + "; ".join(errors))
            return redirect(url_for("dashboard"))
        deadline = time.time() + 30
        while _host_action_blocked("khởi động lại") and time.time() < deadline:
            time.sleep(1)
        err = _host_action_blocked("khởi động lại")
        if err:
            flash("err", "Đã hủy khởi động lại máy: " + err)
            return redirect(url_for("dashboard"))
    try:
        subprocess.Popen(["shutdown", "-r", "now"])
        flash("ok", "Đã gửi lệnh KHỞI ĐỘNG LẠI. Máy sẽ tự bật lại và khởi động server tự động (~1-2 phút).")
    except Exception as e:
        flash("err", f"Lỗi khi khởi động lại: {e}")
    return redirect(url_for("dashboard"))

def _db_action_blocked():
    running = [label for unit, label in COMPONENTS if unit_active(unit)]
    if running:
        return "Cần tắt toàn bộ server game trước: " + ", ".join(running)
    return None

def _run_checked(cmd, **kwargs):
    result = subprocess.run(cmd, capture_output=True, timeout=600, **kwargs)
    if result.returncode != 0:
        err = result.stderr
        if isinstance(err, bytes):
            err = err.decode("utf-8", errors="replace")
        raise RuntimeError((err or "Lệnh hệ thống thất bại").strip())
    return result

def _create_backup_set(prefix="jx_backup"):
    os.makedirs(BACKUP_DIR, exist_ok=True)
    set_name = f"{prefix}_{datetime.now():%Y%m%d_%H%M%S}"
    set_dir = os.path.join(BACKUP_DIR, set_name)
    os.makedirs(set_dir, mode=0o777)
    os.chmod(set_dir, 0o777)  # user mssql trong container can ghi file .bak
    bak_path = os.path.join(set_dir, "account_tong.bak")
    sql_path = os.path.join(set_dir, "server1.sql")
    try:
        c = pymssql.connect(**{**MSSQL, "database": "master"}, charset="utf8", autocommit=True)
        cur = c.cursor()
        sql_bak_path = bak_path.replace("'", "''")
        cur.execute("BACKUP DATABASE [account_tong] TO DISK=%s WITH INIT, COPY_ONLY, CHECKSUM", (sql_bak_path,))
        c.close()

        with open(sql_path, "wb") as dump_file:
            result = subprocess.run([
                "docker", "exec", MYSQL_CONTAINER, "mysqldump",
                "-uroot", "-p" + MYSQL["password"], "--single-transaction",
                "--routines", "--events", "--triggers", "--set-gtid-purged=OFF",
                "--default-character-set=utf8mb4", MYSQL["database"],
            ], stdout=dump_file, stderr=subprocess.PIPE, timeout=600)
        if result.returncode != 0:
            raise RuntimeError(result.stderr.decode("utf-8", errors="replace").strip())
        if not os.path.getsize(bak_path) or not os.path.getsize(sql_path):
            raise RuntimeError("File backup rỗng")
        return set_name
    except Exception:
        shutil.rmtree(set_dir, ignore_errors=True)
        raise

app.extensions["create_database_backup"] = _create_backup_set

def _backup_sets():
    sets = []
    if not os.path.isdir(BACKUP_DIR):
        return sets
    for name in os.listdir(BACKUP_DIR):
        if not BACKUP_SET_RE.fullmatch(name):
            continue
        folder = os.path.join(BACKUP_DIR, name)
        bak = os.path.join(folder, "account_tong.bak")
        sql = os.path.join(folder, "server1.sql")
        if os.path.isfile(bak) and os.path.isfile(sql):
            mtime = max(os.path.getmtime(bak), os.path.getmtime(sql))
            sets.append({"name": name, "time": datetime.fromtimestamp(mtime),
                         "mssql_size": os.path.getsize(bak), "mysql_size": os.path.getsize(sql)})
    return sorted(sets, key=lambda item: item["time"], reverse=True)

def _backup_default_state():
    return {
        "retention": {"mysql": 14, "mssql": 14},
        "metadata": {},
        "schedules": [],
        "runs": [],
    }

def _normalize_backup_state(value):
    state = _backup_default_state()
    if isinstance(value, dict):
        for key in state:
            if key in value and isinstance(value[key], type(state[key])):
                state[key] = value[key]
    for kind in ("mysql", "mssql"):
        try: state["retention"][kind] = max(1, min(int(state["retention"].get(kind, 14)), 3650))
        except (TypeError, ValueError): state["retention"][kind] = 14
    state["schedules"] = [job for job in state["schedules"] if isinstance(job, dict)][-100:]
    state["runs"] = [run for run in state["runs"] if isinstance(run, dict)][-300:]
    return state

def _read_backup_state_unlocked():
    try:
        with open(BACKUP_STATE_PATH, encoding="utf-8") as state_file:
            return _normalize_backup_state(json.load(state_file))
    except (OSError, ValueError):
        return _backup_default_state()

def _backup_state(mutator=None):
    os.makedirs(os.path.dirname(BACKUP_STATE_PATH), mode=0o750, exist_ok=True)
    with open(BACKUP_STATE_LOCK_PATH, "a+", encoding="ascii") as lock_file:
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX if mutator else fcntl.LOCK_SH)
        state = _read_backup_state_unlocked()
        if mutator:
            mutator(state)
            state = _normalize_backup_state(state)
            temporary = BACKUP_STATE_PATH + ".tmp"
            with open(temporary, "w", encoding="utf-8") as state_file:
                json.dump(state, state_file, ensure_ascii=False, indent=2)
                state_file.write("\n")
            os.chmod(temporary, 0o600)
            os.replace(temporary, BACKUP_STATE_PATH)
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)
    return state

def _backup_kind_label(kind):
    return "Dữ liệu Đăng nhập (MySQL)" if kind == "mysql" else "Dữ liệu Nhân vật (MSSQL)"

def _record_backup_metadata(relative, **values):
    def mutate(state):
        current = state["metadata"].get(relative, {})
        current.update({key: value for key, value in values.items() if value is not None})
        state["metadata"][relative] = current
    _backup_state(mutate)

def _create_backup_artifact(kind, source="manual", note="", job_id=""):
    if kind not in ("mysql", "mssql"):
        raise ValueError("Loại database không hợp lệ")
    folder = os.path.join(BACKUP_FILES_ROOT, kind)
    os.makedirs(folder, mode=0o777, exist_ok=True)
    os.chmod(folder, 0o777)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    if kind == "mssql":
        filename = f"mssql-{stamp}.bak"
        path = os.path.join(folder, filename)
        conn = pymssql.connect(**{**MSSQL, "database": "master"}, charset="utf8", autocommit=True)
        try:
            cursor = conn.cursor(); sql_path = path.replace("'", "''")
            cursor.execute("BACKUP DATABASE [account_tong] TO DISK=%s WITH INIT, COPY_ONLY, CHECKSUM", (sql_path,))
        finally:
            conn.close()
    else:
        filename = f"mysql-{stamp}.sql.gz"
        path = os.path.join(folder, filename)
        with gzip.open(path, "wb", compresslevel=6) as dump_file:
            result = subprocess.run([
                "docker", "exec", MYSQL_CONTAINER, "mysqldump", "-uroot", "-p" + MYSQL["password"],
                "--single-transaction", "--routines", "--events", "--triggers", "--set-gtid-purged=OFF",
                "--default-character-set=utf8mb4", MYSQL["database"],
            ], stdout=dump_file, stderr=subprocess.PIPE, timeout=900)
        if result.returncode != 0:
            try: os.unlink(path)
            except OSError: pass
            raise RuntimeError(result.stderr.decode("utf-8", errors="replace").strip())
    if not os.path.isfile(path) or os.path.getsize(path) == 0:
        raise RuntimeError("File backup rỗng")
    os.chmod(path, 0o660)
    relative = os.path.relpath(path, BACKUP_DIR)
    _record_backup_metadata(relative, note=note.strip()[:500], source=source,
                            created_at=datetime.now().astimezone().isoformat(timespec="seconds"), job_id=job_id)
    _cleanup_backup_retention(kind)
    return path

def _backup_artifacts():
    state = _backup_state()
    rows = []
    candidates = []
    for kind in ("mysql", "mssql"):
        folder = os.path.join(BACKUP_FILES_ROOT, kind)
        if os.path.isdir(folder):
            for name in os.listdir(folder):
                path = os.path.join(folder, name)
                if os.path.isfile(path) and not os.path.islink(path):
                    candidates.append((kind, path))
    # Đọc cả các bộ backup cũ để nâng cấp không làm mất lịch sử.
    for item in _backup_sets():
        folder = os.path.join(BACKUP_DIR, item["name"])
        candidates += [("mssql", os.path.join(folder, "account_tong.bak")),
                       ("mysql", os.path.join(folder, "server1.sql"))]
    for kind, path in candidates:
        try:
            relative = os.path.relpath(path, BACKUP_DIR)
            if relative.startswith(os.pardir + os.sep):
                continue
            stat = os.stat(path); meta = state["metadata"].get(relative, {})
            rows.append({
                "id": hashlib.sha256(relative.encode()).hexdigest()[:20], "kind": kind,
                "label": _backup_kind_label(kind), "filename": os.path.basename(path),
                "relative": relative, "path": path, "size": stat.st_size,
                "time": datetime.fromtimestamp(stat.st_mtime), "note": meta.get("note", ""),
                "source": meta.get("source", "legacy" if not relative.startswith("files/") else "manual"),
            })
        except OSError:
            continue
    rows.sort(key=lambda item: item["time"], reverse=True)
    latest = {}
    for row in rows:
        if row["kind"] not in latest:
            latest[row["kind"]] = row["id"]
        row["is_latest"] = latest[row["kind"]] == row["id"]
    return rows

def _backup_artifact(artifact_id):
    for row in _backup_artifacts():
        if row["id"] == artifact_id:
            resolved = os.path.realpath(row["path"])
            if os.path.commonpath((os.path.realpath(BACKUP_DIR), resolved)) != os.path.realpath(BACKUP_DIR):
                break
            return row
    raise FileNotFoundError("Không tìm thấy file backup")

def _restore_backup_artifact(row):
    path = row["path"]
    if row["kind"] == "mssql":
        sql_path = path.replace("'", "''")
        conn = pymssql.connect(**{**MSSQL, "database": "master"}, charset="utf8", autocommit=True)
        cursor = conn.cursor()
        cursor.execute("RESTORE VERIFYONLY FROM DISK=%s WITH CHECKSUM", (sql_path,))
        try:
            cursor.execute("ALTER DATABASE [account_tong] SET SINGLE_USER WITH ROLLBACK IMMEDIATE")
            cursor.execute("RESTORE DATABASE [account_tong] FROM DISK=%s WITH REPLACE, CHECKSUM", (sql_path,))
        finally:
            try: cursor.execute("ALTER DATABASE [account_tong] SET MULTI_USER")
            except Exception: pass
            conn.close()
    else:
        _run_checked(["docker", "exec", MYSQL_CONTAINER, "mysql", "-uroot", "-p" + MYSQL["password"],
                      "-e", "DROP DATABASE IF EXISTS `server1`; CREATE DATABASE `server1` CHARACTER SET utf8mb4;"])
        opener = gzip.open if path.lower().endswith(".gz") else open
        with opener(path, "rb") as sql_file:
            result = subprocess.run(["docker", "exec", "-i", MYSQL_CONTAINER, "mysql", "-uroot",
                                     "-p" + MYSQL["password"], "--default-character-set=utf8mb4", "server1"],
                                    stdin=sql_file, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=900)
        if result.returncode != 0:
            raise RuntimeError(result.stderr.decode("utf-8", errors="replace").strip())

def _cleanup_backup_retention(kind):
    retention = _backup_state()["retention"][kind]
    cutoff = time.time() - retention * 86400
    rows = [row for row in _backup_artifacts() if row["kind"] == kind and row["source"] == "schedule"]
    for row in rows:
        if not row["is_latest"] and os.path.getmtime(row["path"]) < cutoff:
            try: os.unlink(row["path"])
            except OSError: pass

def _schedule_matches(schedule, moment):
    kind = schedule.get("type")
    if kind == "hourly":
        every = max(1, min(int(schedule.get("every_hours", 1)), 23))
        return moment.minute == int(schedule.get("minute", 0)) and moment.hour % every == 0
    hour, minute = [int(value) for value in str(schedule.get("time", "03:00")).split(":", 1)]
    if moment.hour != hour or moment.minute != minute:
        return False
    return kind == "daily" or (kind == "weekly" and moment.weekday() in schedule.get("days", []))

def _next_schedule_time(job):
    cursor = datetime.now().replace(second=0, microsecond=0) + timedelta(minutes=1)
    for _ in range(8 * 24 * 60):
        try:
            if _schedule_matches(job.get("schedule", {}), cursor):
                return cursor
        except (TypeError, ValueError):
            return None
        cursor += timedelta(minutes=1)
    return None

def _schedule_summary(schedule):
    kind = schedule.get("type")
    if kind == "hourly":
        return f"Mỗi {schedule.get('every_hours', 1)} giờ, phút {int(schedule.get('minute', 0)):02d}"
    if kind == "daily":
        return "Hàng ngày lúc " + str(schedule.get("time", "03:00"))
    labels = ["T2", "T3", "T4", "T5", "T6", "T7", "CN"]
    days = ", ".join(labels[value] for value in schedule.get("days", []) if isinstance(value, int) and 0 <= value < 7)
    return f"{days or 'Chưa chọn ngày'} lúc {schedule.get('time', '03:00')}"

def _queue_backup_job(job_id, trigger="manual"):
    run_id = "run_" + uuid.uuid4().hex[:16]
    selected = {}
    def mutate(state):
        job = next((item for item in state["schedules"] if item.get("id") == job_id), None)
        if not job:
            raise ValueError("Không tìm thấy lịch backup")
        selected.update(job)
        now = datetime.now().astimezone().isoformat(timespec="seconds")
        job["last_run"] = now
        state["runs"].append({"id": run_id, "job_id": job_id, "database": job["database"],
                              "trigger": trigger, "status": "queued", "scheduled_at": now,
                              "file": "", "error": ""})
    _backup_state(mutate)
    python = os.path.join(PROJECT_ROOT, "app", "web", "admin", "venv", "bin", "python")
    runner = os.path.join(PROJECT_ROOT, "tools", "run-backup-job")
    subprocess.Popen([python, runner, run_id], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                     start_new_session=True, close_fds=True)
    return run_id

def _execute_backup_run(run_id):
    selected = {}
    def mark_running(state):
        run = next((item for item in state["runs"] if item.get("id") == run_id), None)
        if not run: raise ValueError("Không tìm thấy lượt backup")
        run["status"] = "running"; run["started_at"] = datetime.now().astimezone().isoformat(timespec="seconds")
        selected.update(run)
    _backup_state(mark_running)
    try:
        path = _create_backup_artifact(selected["database"], source="schedule", job_id=selected["job_id"])
        def success(state):
            run = next(item for item in state["runs"] if item.get("id") == run_id)
            run.update(status="succeeded", file=os.path.basename(path), finished_at=datetime.now().astimezone().isoformat(timespec="seconds"))
        _backup_state(success)
    except Exception as exc:
        def failed(state):
            run = next(item for item in state["runs"] if item.get("id") == run_id)
            run.update(status="failed", error=str(exc)[:1000], finished_at=datetime.now().astimezone().isoformat(timespec="seconds"))
        _backup_state(failed)
        raise

def _queue_due_backup_jobs():
    state = _backup_state(); now = datetime.now(); queued = []
    for job in state["schedules"]:
        if not job.get("enabled", True):
            continue
        try:
            if not _schedule_matches(job.get("schedule", {}), now):
                continue
            last = datetime.fromisoformat(job.get("last_run", "")) if job.get("last_run") else None
            if last and last.strftime("%Y%m%d%H%M") == now.strftime("%Y%m%d%H%M"):
                continue
            queued.append(_queue_backup_job(job["id"], "schedule"))
        except (TypeError, ValueError, OSError):
            continue
    return queued

def _selected_backup_dir(set_name):
    if not BACKUP_SET_RE.fullmatch(set_name or ""):
        raise ValueError("Tên bộ backup không hợp lệ")
    folder = os.path.abspath(os.path.join(BACKUP_DIR, set_name))
    if os.path.dirname(folder) != os.path.abspath(BACKUP_DIR):
        raise ValueError("Đường dẫn backup không hợp lệ")
    for filename in ("account_tong.bak", "server1.sql"):
        if not os.path.isfile(os.path.join(folder, filename)):
            raise FileNotFoundError(f"Thiếu {filename}")
    return folder

def _restore_backup_set(set_name):
    folder = _selected_backup_dir(set_name)
    bak_path = os.path.join(folder, "account_tong.bak").replace("'", "''")
    sql_path = os.path.join(folder, "server1.sql")

    c = pymssql.connect(**{**MSSQL, "database": "master"}, charset="utf8", autocommit=True)
    cur = c.cursor()
    cur.execute("RESTORE VERIFYONLY FROM DISK=%s WITH CHECKSUM", (bak_path,))
    try:
        cur.execute("ALTER DATABASE [account_tong] SET SINGLE_USER WITH ROLLBACK IMMEDIATE")
        cur.execute("RESTORE DATABASE [account_tong] FROM DISK=%s WITH REPLACE, CHECKSUM", (bak_path,))
    finally:
        try: cur.execute("ALTER DATABASE [account_tong] SET MULTI_USER")
        except Exception: pass
        c.close()

    _run_checked(["docker", "exec", MYSQL_CONTAINER, "mysql",
                  "-uroot", "-p" + MYSQL["password"], "-e",
                  "DROP DATABASE IF EXISTS `server1`; CREATE DATABASE `server1` CHARACTER SET utf8mb4;"])
    with open(sql_path, "rb") as sql_file:
        result = subprocess.run([
            "docker", "exec", "-i", MYSQL_CONTAINER, "mysql",
            "-uroot", "-p" + MYSQL["password"], "--default-character-set=utf8mb4", "server1",
        ], stdin=sql_file, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=600)
    if result.returncode != 0:
        raise RuntimeError(result.stderr.decode("utf-8", errors="replace").strip())

def _item_stack_paths(root):
    return [
        os.path.join(root, directory, filename) if directory else os.path.join(root, filename)
        for directory in ITEM_STACK_DIRS
        for filename in ITEM_STACK_FILES
    ]


def _split_tsv_line(line):
    if line.endswith(b"\r\n"):
        return line[:-2].split(b"\t"), b"\r\n"
    if line.endswith(b"\n"):
        return line[:-1].split(b"\t"), b"\n"
    return line.split(b"\t"), b""


def _ground_item_lifetime_state():
    values = []
    per_file = {}
    for path in GROUND_ITEM_LIFETIME_PATHS:
        path_values = []
        with open(path, "rb") as f:
            for line in f.readlines()[1:]:
                fields, _newline = _split_tsv_line(line)
                if len(fields) < 7 or fields[2].strip().lower() != b"item":
                    continue
                try:
                    ticks = int(fields[6].strip())
                except ValueError:
                    raise ValueError(f"LifeTime vật phẩm không hợp lệ trong {path}")
                if ticks < 0:
                    raise ValueError(f"LifeTime vật phẩm âm trong {path}")
                path_values.append(ticks)
                values.append(ticks)
        if not path_values:
            raise ValueError(f"Không tìm thấy dòng Kind=Item trong {path}")
        per_file[path] = path_values

    counts = {}
    for ticks in values:
        counts[ticks] = counts.get(ticks, 0) + 1
    selected_ticks = max(counts, key=lambda ticks: (counts[ticks], ticks))
    seconds_values = sorted({round(ticks / GROUND_ITEM_TICKS_PER_SECOND, 3) for ticks in values})
    return {
        "seconds": round(selected_ticks / GROUND_ITEM_TICKS_PER_SECOND, 3),
        "seconds_values": seconds_values,
        "uniform": len(counts) == 1,
        "items": len(values),
        "files": len(per_file),
    }


def _render_ground_item_lifetime_file(path, ticks):
    with open(path, "rb") as f:
        lines = f.readlines()
    if not lines:
        raise ValueError(f"Bảng object rỗng: {path}")
    rendered = [lines[0]]
    changed = 0
    eligible = 0
    value = str(ticks).encode("ascii")
    for line in lines[1:]:
        fields, newline = _split_tsv_line(line)
        if len(fields) >= 7 and fields[2].strip().lower() == b"item":
            eligible += 1
            if fields[6] != value:
                fields[6] = value
                changed += 1
                line = b"\t".join(fields) + newline
        rendered.append(line)
    if not eligible:
        raise ValueError(f"Không tìm thấy dòng Kind=Item trong {path}")
    return b"".join(rendered), eligible, changed


def _render_item_stack_file(path, stack_limit):
    filename = os.path.basename(path)
    with open(path, "rb") as f:
        lines = f.readlines()
    if not lines:
        raise ValueError(f"Bảng vật phẩm rỗng: {path}")
    changed = 0
    eligible = 0
    rendered = [lines[0]]
    for line in lines[1:]:
        fields, newline = _split_tsv_line(line)
        target_column = None
        if filename == "magicscript.txt":
            if len(fields) >= 21 and fields[12].strip() == b"1":
                target_column = 20
        elif filename == "potion.txt":
            if len(fields) >= 13:
                target_column = 12
        elif filename == "questkey.txt":
            if len(fields) >= 10:
                try:
                    if int(fields[9].strip() or b"0") > 0:
                        target_column = 9
                except ValueError:
                    pass
        elif filename in ("magicscript_stack.txt", "questkey_stack.txt"):
            if len(fields) >= 2:
                try:
                    int(fields[0].strip())
                    int(fields[1].strip())
                    target_column = 1
                except ValueError:
                    pass
        else:
            raise ValueError(f"Bảng xếp chồng không được hỗ trợ: {filename}")

        if target_column is not None:
            eligible += 1
            value = b"1" if filename == "potion.txt" else str(stack_limit).encode("ascii")
            if fields[target_column] != value:
                fields[target_column] = value
                changed += 1
                line = b"\t".join(fields) + newline
        rendered.append(line)
    return b"".join(rendered), eligible, changed


def _write_bytes_preserving_metadata(path, content):
    stat_result = os.stat(path)
    directory = os.path.dirname(path)
    fd, tmp = tempfile.mkstemp(prefix=".item_stack_", suffix=".txt", dir=directory)
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(content)
        os.chmod(tmp, stat_result.st_mode)
        try:
            os.chown(tmp, stat_result.st_uid, stat_result.st_gid)
        except PermissionError:
            pass
        os.replace(tmp, path)
    except Exception:
        try:
            os.unlink(tmp)
        except FileNotFoundError:
            pass
        raise


def _set_ground_item_lifetime(seconds):
    seconds = float(seconds)
    if not GROUND_ITEM_LIFETIME_MIN <= seconds <= GROUND_ITEM_LIFETIME_MAX:
        raise ValueError(
            f"Thời gian tồn tại phải từ {GROUND_ITEM_LIFETIME_MIN:g} đến "
            f"{GROUND_ITEM_LIFETIME_MAX:g} giây"
        )
    ticks = int(round(seconds * GROUND_ITEM_TICKS_PER_SECOND))
    rendered = {}
    eligible = 0
    changed = 0
    for path in GROUND_ITEM_LIFETIME_PATHS:
        data, path_eligible, path_changed = _render_ground_item_lifetime_file(path, ticks)
        rendered[path] = data
        eligible += path_eligible
        changed += path_changed

    stamp = datetime.now().strftime(".bak_ground_lifetime_%Y%m%d_%H%M%S")
    backups = {}
    try:
        for path in rendered:
            backup_path = path + stamp
            shutil.copy2(path, backup_path)
            backups[path] = backup_path
        for path, data in rendered.items():
            _write_bytes_preserving_metadata(path, data)
    except Exception:
        for path, backup_path in backups.items():
            if os.path.exists(backup_path):
                shutil.copy2(backup_path, path)
        raise
    return {
        "seconds": ticks / GROUND_ITEM_TICKS_PER_SECOND,
        "ticks": ticks,
        "eligible": eligible,
        "changed": changed,
        "files": len(rendered),
    }


def _render_potion_stack_binary(path, stack_limit):
    data = bytearray(open(path, "rb").read())
    try:
        offset, flag_immediate, max_immediate, stride = ITEM_STACK_BINARY_LAYOUTS[path]
    except KeyError:
        raise ValueError(f"Không có sơ đồ sửa xếp chồng thuốc cho {path}")
    if data[offset:offset + 3] != bytes.fromhex("c74074"):
        raise ValueError(f"Sai chữ ký cờ xếp chồng thuốc trong {path}")
    if path == ITEM_STACK_SERVER_BINARY:
        if data[offset + 7:offset + 13] != stride or data[offset + 13:offset + 16] != bytes.fromhex("c74078"):
            raise ValueError(f"Sai chữ ký giới hạn thuốc trong {path}")
    else:
        if data[offset + 7:offset + 10] != bytes.fromhex("c74078") or data[offset + 14:offset + 20] != stride:
            raise ValueError(f"Sai chữ ký giới hạn thuốc trong {path}")
    data[offset + flag_immediate:offset + flag_immediate + 4] = (1).to_bytes(4, "little")
    data[offset + max_immediate:offset + max_immediate + 4] = int(stack_limit).to_bytes(4, "little")
    try:
        patch_offset, original, replacement = ITEM_STACK_MEDICINE_COMPARE_PATCHES[path]
    except KeyError:
        raise ValueError(f"Thiếu bản vá nhận diện cấp thuốc cho {path}")
    current = bytearray(data[patch_offset:patch_offset + len(replacement)])
    original_cmp = bytearray(original)
    replacement_cmp = bytearray(replacement)
    max_field = offset + max_immediate - patch_offset
    for signature in (current, original_cmp, replacement_cmp):
        signature[max_field:max_field + 4] = b"\0" * 4
    if bytes(current) not in (bytes(original_cmp), bytes(replacement_cmp)):
        raise ValueError(f"Sai chữ ký nhận diện cấp thuốc trong {path}")
    rendered_compare = bytearray(replacement)
    rendered_compare[max_field:max_field + 4] = int(stack_limit).to_bytes(4, "little")
    data[patch_offset:patch_offset + len(rendered_compare)] = rendered_compare
    try:
        branch_offset, original, replacement = ITEM_STACK_MEDICINE_EMPTY_BRANCH_PATCHES[path]
    except KeyError:
        raise ValueError(f"Thiếu bản vá nhánh bảng thuốc rỗng cho {path}")
    current = bytes(data[branch_offset:branch_offset + len(replacement)])
    originals = original if isinstance(original, tuple) else (original,)
    if current not in originals + (replacement,):
        raise ValueError(f"Sai chữ ký nhánh bảng thuốc rỗng trong {path}")
    data[branch_offset:branch_offset + len(replacement)] = replacement
    return bytes(data)


def _potion_stack_binary_limit():
    path = ITEM_STACK_SERVER_BINARY
    data = open(path, "rb").read()
    offset, _flag_immediate, max_immediate, _stride = ITEM_STACK_BINARY_LAYOUTS[path]
    return int.from_bytes(data[offset + max_immediate:offset + max_immediate + 4], "little")


def _item_stack_state():
    values = set()
    eligible = 0
    files = 0
    potion_limit = _potion_stack_binary_limit()
    for path in _item_stack_paths(ITEM_STACK_SERVER_ROOT):
        if not os.path.isfile(path):
            raise ValueError(f"Thiếu bảng vật phẩm: {path}")
        filename = os.path.basename(path)
        with open(path, "rb") as f:
            lines = f.readlines()
        files += 1
        for line in lines[1:]:
            fields, _newline = _split_tsv_line(line)
            value = None
            if filename == "magicscript.txt" and len(fields) >= 21 and fields[12].strip() == b"1":
                value = fields[20].strip()
            elif filename == "potion.txt" and len(fields) >= 13:
                if int(fields[12].strip() or b"0") > 0:
                    value = str(potion_limit).encode("ascii")
            elif filename == "questkey.txt" and len(fields) >= 10:
                try:
                    if int(fields[9].strip() or b"0") > 0:
                        value = fields[9].strip()
                except ValueError:
                    pass
            elif filename in ("magicscript_stack.txt", "questkey_stack.txt") and len(fields) >= 2:
                try:
                    int(fields[0].strip())
                    value = fields[1].strip()
                except ValueError:
                    pass
            if value is not None:
                eligible += 1
                try:
                    values.add(int(value or b"0"))
                except ValueError:
                    values.add(0)
    positive = sorted(value for value in values if value > 0)
    return {
        "limit": positive[0] if len(positive) == 1 else 100,
        "limits": positive,
        "uniform": len(positive) == 1 and 0 not in values,
        "eligible": eligible,
        "files": files,
    }


def _set_item_stack_limit(stack_limit):
    stack_limit = int(stack_limit)
    if not ITEM_STACK_MIN <= stack_limit <= ITEM_STACK_MAX:
        raise ValueError(
            f"Số lượng mỗi chồng phải từ {ITEM_STACK_MIN} đến {ITEM_STACK_MAX}"
        )
    # The server is authoritative for stack counts.  Do not rewrite the
    # reference client tree or require players to download a new executable.
    paths = _item_stack_paths(ITEM_STACK_SERVER_ROOT)
    missing = [path for path in paths if not os.path.isfile(path)]
    if missing:
        raise ValueError(f"Thiếu bảng vật phẩm: {missing[0]}")
    rendered = {}
    eligible = 0
    changed = 0
    for path in paths:
        data, path_eligible, path_changed = _render_item_stack_file(path, stack_limit)
        rendered[path] = data
        eligible += path_eligible
        changed += path_changed
    for path in ITEM_STACK_BINARY_LAYOUTS:
        if not os.path.isfile(path):
            raise ValueError(f"Thiếu engine xếp chồng thuốc: {path}")
        rendered[path] = _render_potion_stack_binary(path, stack_limit)

    stamp = datetime.now().strftime(".bak_item_stack_%Y%m%d_%H%M%S")
    backups = {}
    try:
        for path in rendered:
            backup_path = path + stamp
            shutil.copy2(path, backup_path)
            backups[path] = backup_path
        for path, data in rendered.items():
            _write_bytes_preserving_metadata(path, data)
    except Exception:
        for path, backup_path in backups.items():
            if os.path.exists(backup_path):
                shutil.copy2(backup_path, path)
        raise
    return {"files": len(paths), "eligible": eligible, "changed": changed}


def _create_item_stack_client_zip():
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"jx_item_stack_client_update_{stamp}.zip"
    zip_path = os.path.join(ITEM_STACK_DOWNLOAD_DIR, filename)
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for path in _item_stack_paths(ITEM_STACK_CLIENT_ROOT):
            rel = os.path.relpath(path, ITEM_STACK_CLIENT_ROOT).replace(os.sep, "/")
            zf.write(path, "settings/item/" + rel)
        if not os.path.isfile(ITEM_STACK_CLIENT_BINARY):
            raise ValueError(f"Thiếu chương trình client: {ITEM_STACK_CLIENT_BINARY}")
        zf.write(ITEM_STACK_CLIENT_BINARY, "game.exe")
    os.chmod(zip_path, 0o644)
    return filename, zip_path


def _valid_item_stack_pack(filename):
    if not re.fullmatch(r"jx_item_stack_client_update_\d{8}_\d{6}\.zip", filename or ""):
        return None
    path = os.path.abspath(os.path.join(ITEM_STACK_DOWNLOAD_DIR, filename))
    if os.path.dirname(path) != os.path.abspath(ITEM_STACK_DOWNLOAD_DIR) or not os.path.isfile(path):
        return None
    return path


def _create_item_brand_client_zip():
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"jx_item_brand_client_update_{stamp}.zip"
    zip_path = os.path.join(ITEM_BRAND_DOWNLOAD_DIR, filename)
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for path in _item_brand_files():
            if os.path.basename(path) not in ITEM_BRAND_TARGET_FILES:
                continue
            rel = os.path.relpath(path, ITEM_BRAND_ROOT).replace(os.sep, "/")
            zf.write(path, "settings/item/" + rel)
    os.chmod(zip_path, 0o644)
    return filename, zip_path


def _valid_item_brand_pack(filename):
    if not re.fullmatch(r"jx_item_brand_client_update_\d{8}_\d{6}\.zip", filename or ""):
        return None
    path = os.path.abspath(os.path.join(ITEM_BRAND_DOWNLOAD_DIR, filename))
    if os.path.dirname(path) != os.path.abspath(ITEM_BRAND_DOWNLOAD_DIR) or not os.path.isfile(path):
        return None
    return path


def _item_brand_client_packs():
    packs = []
    try:
        for filename in os.listdir(ITEM_BRAND_DOWNLOAD_DIR):
            path = _valid_item_brand_pack(filename)
            if not path:
                continue
            packs.append({
                "name": filename,
                "size": os.path.getsize(path),
                "time": datetime.fromtimestamp(os.path.getmtime(path)),
            })
    except FileNotFoundError:
        pass
    return sorted(packs, key=lambda item: item["time"], reverse=True)


def _delete_item_brand_client_packs():
    deleted = 0
    total_size = 0
    for item in _item_brand_client_packs():
        path = _valid_item_brand_pack(item["name"])
        if not path:
            continue
        total_size += os.path.getsize(path)
        os.unlink(path)
        deleted += 1
    return deleted, total_size


@app.route("/item-brand/delete-packs", methods=["POST"])
def item_brand_delete_packs():
    if (request.form.get("confirm") or "").strip().upper() != "XOAZIP":
        flash("err", "Hãy nhập XOAZIP để xác nhận xoá các gói client update.")
        return redirect(url_for("item_brand"))
    try:
        deleted, total_size = _delete_item_brand_client_packs()
        flash("ok", f"Đã xoá {deleted} file zip client update, giải phóng {total_size / 1048576:.2f} MB.")
    except Exception as e:
        flash("err", f"Không xoá được file zip: {e}")
    return redirect(url_for("item_brand"))


@app.route("/item-brand/download/<filename>")
def item_brand_download(filename):
    path = _valid_item_brand_pack(filename)
    if not path:
        flash("err", "Gói client update không tồn tại hoặc tên file không hợp lệ.")
        return redirect(url_for("item_brand"))
    return send_file(path, as_attachment=True, download_name=os.path.basename(path), mimetype="application/zip")


@app.route("/item-brand", methods=["GET", "POST"])
def item_brand():
    current_text = _item_brand_current_text()
    brand_files = _item_brand_files()
    brand_error = "" if brand_files else (
        "Chưa thấy bảng vật phẩm phù hợp trong " + _game_setting_path_label(ITEM_BRAND_ROOT)
    )
    if request.method == "POST":
        if brand_error:
            flash("err", brand_error)
            return redirect(url_for("item_brand"))
        action = request.form.get("action") or "save"
        confirm = (request.form.get("confirm") or "").strip().upper()
        if confirm != "SUAITEM":
            flash("err", "Hãy nhập SUAITEM để xác nhận sửa toàn bộ mô tả vật phẩm.")
            return redirect(url_for("item_brand"))
        try:
            new_text = (request.form.get("brand_text") or "").strip()
            if not new_text:
                raise ValueError("Cần nhập nội dung dòng tuỳ chỉnh")
            if len(new_text) > 80:
                raise ValueError("Nội dung tối đa 80 ký tự")
            # Bảo đảm chỉ nhận ký tự có thể chuyển sang TCVN3/latin-1.
            _to_tcvn3_bytes(new_text)
            result = _replace_item_brand(new_text, remove=False)
            pack_name, pack_path = _create_item_brand_client_zip()
            flash("ok", f"Đã đổi dòng tuỳ chỉnh thành '{new_text}' trong {result['files']} file, {result['count']} vị trí. Đã tạo gói client: /opt/QuanLy_One/JX_Servers/Active/{pack_name}.")
            return redirect(url_for("item_brand", pack=pack_name))
        except Exception as e:
            flash("err", f"Không sửa được dòng vật phẩm: {e}")
        return redirect(url_for("item_brand"))

    stats = _item_brand_count(current_text)
    default_stats = _item_brand_count(ITEM_BRAND_DEFAULT_TEXT)
    pack_name = request.args.get("pack") or ""
    pack_path = _valid_item_brand_pack(pack_name)
    if not pack_path:
        pack_name = ""
    packs = _item_brand_client_packs()
    body = """
    {% if brand_error %}<div class="card" style="border-color:var(--warn);background:rgba(255,176,46,.07)"><h2>⚠️ Vật phẩm — Chưa thấy</h2><p>{{brand_error}}</p><p class="muted">Tính năng này được khóa để không ghi nhầm dữ liệu. Các trang Thiết lập game khác vẫn dùng bình thường.</p></div>{% endif %}
    <div {% if brand_error %}hidden{% endif %}>
    <div class="card"><h2>Dòng tuỳ chỉnh vật phẩm</h2>
      <p class="muted">Công cụ này sửa trực tiếp cột mô tả trong các file</p>
      <table>
        <tr><td>Dòng hiện tại web đang quản lý</td><td><b>{{current_text}}</b></td></tr>
        <tr><td>Vị trí khớp dòng hiện tại</td><td>{{stats.count}} vị trí trong {{stats.files}} file</td></tr>
        <tr><td>Vị trí còn dòng mặc định</td><td>{{default_stats.count}} vị trí trong {{default_stats.files}} file</td></tr>
      </table>
    </div>
    {% if pack_name %}
    <div class="card" style="border-color:var(--ok);background:rgba(57,217,138,.08)"><h2>Gói đồng bộ client vừa tạo</h2>
      <p class="muted">File đã được tạo tại <b>/opt/QuanLy_One/JX_Servers/Active/{{pack_name}}</b>. Tải về rồi giải nén đè vào client theo đúng thư mục <b>settings/item</b>.</p>
      <a class="btn ok" href="/item-brand/download/{{pack_name}}">⬇️ Tải {{pack_name}}</a>
    </div>
    {% endif %}
    <div class="card"><h2>Quản lý gói client update</h2>
      {% if packs %}
      <p class="muted">Đang có {{packs|length}} file zip trong <b>/opt/QuanLy_One/JX_Servers/Active</b>. File mới nhất nằm trên cùng.</p>
      <div class="scroll"><table><tr><th>Tên file</th><th>Dung lượng</th><th>Thời gian</th><th>Tải</th></tr>
      {% for item in packs[:8] %}<tr>
        <td>{{item.name}}</td>
        <td>{{'%.2f MB'|format(item.size/1048576)}}</td>
        <td>{{item.time.strftime('%d/%m/%Y %H:%M:%S')}}</td>
        <td><a class="btn mut" href="/item-brand/download/{{item.name}}">Tải</a></td>
      </tr>{% endfor %}</table></div>
      <form method="post" action="/item-brand/delete-packs" style="margin-top:12px"
            data-confirm="Xoá tất cả file zip client update trong /opt/QuanLy_One/JX_Servers/Active?">
        <input name="confirm" placeholder="Nhập XOAZIP" required style="max-width:220px;display:inline-block">
        <button class="err" style="background:#991b1b;border-color:#b91c1c">🗑️ Xoá các file zip</button>
      </form>
      {% else %}<p class="muted">Chưa có file zip client update nào trong /opt/QuanLy_One/JX_Servers/Active.</p>{% endif %}
    </div>
    <div class="card"><h2>Đổi nội dung</h2>
      <form method="post" data-confirm="Sửa dòng mô tả cho toàn bộ vật phẩm? Web sẽ backup trước khi ghi.">
        <label>Nội dung mới</label>
        <input name="brand_text" value="{{current_text}}" maxlength="80" required>
        <label>Xác nhận</label>
        <input name="confirm" placeholder="Nhập SUAITEM" required style="max-width:240px">
        <button class="ok" name="action" value="save" style="margin-top:12px">💾 Lưu thay đổi</button>
      </form>
    </div>
    </div>
    """
    return game_settings_page(body, "item_brand", current_text=current_text, stats=stats,
                              default_stats=default_stats, pack_name=pack_name, packs=packs,
                              brand_error=brand_error)


@app.route("/item-stack/download/<filename>")
def item_stack_download(filename):
    path = _valid_item_stack_pack(filename)
    if not path:
        flash("err", "Gói đồng bộ xếp chồng không tồn tại hoặc tên file không hợp lệ.")
        return redirect(url_for("game_settings", tab="item_stack"))
    return send_file(path, as_attachment=True, download_name=os.path.basename(path), mimetype="application/zip")


def _game_setting_path_label(path):
    try:
        relative = os.path.relpath(path, ACTIVE_SERVER_PATH)
        if relative != os.pardir and not relative.startswith(os.pardir + os.sep):
            return relative.replace(os.sep, "/")
    except (TypeError, ValueError):
        pass
    return str(path)


def _default_simcity_state():
    values = dict(SIMCITY_DEFAULTS)
    values["skills"] = {key: 0 for key, _label, _options in SIMCITY_FACTIONS}
    values["training_maps"] = {
        map_id: values["training_size"] for _level, map_id, _name in SIMCITY_TRAINING_MAPS
    }
    return values


def _load_experience_state():
    raw = _read_ini_key(GAMESETTING_PATH, "ServerConfig", "ExpRate")
    if raw is None:
        raise ValueError("không tìm thấy [ServerConfig] ExpRate")
    try:
        return _exp_multiplier_from_raw(int(raw))
    except (TypeError, ValueError):
        raise ValueError("ExpRate không phải số nguyên")


def _load_drop_settings_state():
    return {
        "drop_rate": _read_drop_rate_state(),
        "drop_money": _global_drop_money_state(),
        "drop_coin": _global_coin_drop_state(),
        "special_drop": _global_special_drop_state(),
        "ground_item_lifetime": _ground_item_lifetime_state(),
    }


def _safe_game_setting_feature(key, label, required_paths, loader, fallback):
    active = active_server_info()
    missing = [_game_setting_path_label(path) for path in required_paths if not os.path.isfile(path)]
    if active is None:
        return fallback, {
            "key": key, "label": label, "available": False,
            "message": "Chưa chọn server đang sử dụng hợp lệ", "missing": missing,
        }
    if missing:
        return fallback, {
            "key": key, "label": label, "available": False,
            "message": "Chưa thấy file cần thiết", "missing": missing,
        }
    try:
        value = loader()
        if key == "monster_respawn" and not value.get("available"):
            raise ValueError("không tìm thấy mẫu quái thường phù hợp")
        return value, {
            "key": key, "label": label, "available": True,
            "message": "Đã đọc từ server đang sử dụng", "missing": [],
        }
    except Exception as exc:
        app.logger.warning("Game setting %s unavailable: %s", key, exc)
        return fallback, {
            "key": key, "label": label, "available": False,
            "message": "Không đọc được cấu hình: " + str(exc), "missing": [],
        }


@app.route("/game-settings", methods=["GET", "POST"])
def game_settings():
    if request.method == "POST":
        settings_type = (request.form.get("settings_type") or "experience").strip()
        stack_pack_name = ""
        sim_active_tab = (request.form.get("sim_active_tab") or "basic").strip()
        if sim_active_tab not in ("basic", "combat", "interaction", "stall", "skills", "tongkim", "competition"):
            sim_active_tab = "basic"
        try:
            if settings_type == "simcity":
                simcity = _simcity_values_from_form()
                _write_simcity_config(simcity)
                saved_message = "Đã lưu cấu hình SimCity"
            elif settings_type == "experience":
                multiplier_text = (request.form.get("exp_multiplier") or "").strip().replace(",", ".")
                multiplier = float(multiplier_text)
                if multiplier < 0 or multiplier > 100:
                    raise ValueError("Hệ số kinh nghiệm phải từ x0 đến x100")
                raw = int(round(multiplier * 100))
                _set_exp_rate_raw(raw)
                saved_message = f"Đã lưu kinh nghiệm đánh quái x{_exp_multiplier_from_raw(raw):g}"
            elif settings_type == "da_tau":
                limit_text = (request.form.get("da_tau_daily_limit") or "").strip()
                if not re.fullmatch(r"\d+", limit_text):
                    raise ValueError("Số nhiệm vụ Dã Tẩu phải là số nguyên")
                limit = _set_da_tau_daily_limit(int(limit_text))
                saved_message = (
                    f"Đã đặt giới hạn Dã Tẩu là {limit} nhiệm vụ "
                    "cho mỗi nhân vật trong một ngày"
                )
            elif settings_type == "monster_respawn":
                seconds_text = (
                    request.form.get("monster_respawn_seconds") or ""
                ).strip().replace(",", ".")
                result = _set_monster_respawn_seconds(float(seconds_text))
                saved_message = (
                    f"Đã đặt thời gian hồi sinh quái thường là "
                    f"{result['seconds']:g} giây cho {result['templates']} mẫu quái"
                )
            elif settings_type == "drop_rate":
                drop_percent_text = (
                    request.form.get("drop_percent") or ""
                ).strip().replace(",", ".")
                drop_percent = float(drop_percent_text)
                money_rate = int((request.form.get("money_rate") or "").strip())
                money_scale_text = (
                    request.form.get("money_scale") or ""
                ).strip().replace(",", ".")
                money_scale = float(money_scale_text)
                coin_percent_text = (
                    request.form.get("coin_percent") or "0"
                ).strip().replace(",", ".")
                coin_percent = float(coin_percent_text)
                coin_enabled = request.form.get("coin_enabled") == "1"
                mystery_map_percent = float(
                    (request.form.get("mystery_map_percent") or "0")
                    .strip().replace(",", ".")
                )
                mystery_record_percent = float(
                    (request.form.get("mystery_record_percent") or "0")
                    .strip().replace(",", ".")
                )
                ground_item_lifetime_seconds = float(
                    (request.form.get("ground_item_lifetime_seconds") or "")
                    .strip().replace(",", ".")
                )
                file_count = _set_drop_rate(
                    drop_percent, money_rate, money_scale, coin_percent, coin_enabled,
                    mystery_map_percent, mystery_record_percent,
                    ground_item_lifetime_seconds,
                )
                saved_message = (
                    f"Đã lưu cấu hình chung: rơi đồ {drop_percent:g}%, "
                    f"rơi Ngân lượng {money_rate}%, lượng Ngân lượng x{money_scale:g} "
                    f"và Tiền đồng {'bật' if coin_enabled else 'tắt'} ({coin_percent:g}%) "
                    f"Mật Đồ Thần Bí {mystery_map_percent:g}%, "
                    f"Thần Bí Đồ Chí {mystery_record_percent:g}% "
                    f"và vật phẩm tồn tại {ground_item_lifetime_seconds:g} giây "
                    f"cho {file_count} nhóm quái thường"
                )
            elif settings_type == "item_stack":
                stack_limit = int((request.form.get("stack_limit") or "").strip())
                result = _set_item_stack_limit(stack_limit)
                saved_message = (
                    f"Đã đặt tối đa {stack_limit} vật phẩm mỗi chồng; "
                    f"đồng bộ {result['files']} bảng server, "
                    f"thay đổi {result['changed']} bản ghi"
                )
            elif settings_type == "ground_item_lifetime":
                lifetime_text = (
                    request.form.get("ground_item_lifetime_seconds") or ""
                ).strip().replace(",", ".")
                result = _set_ground_item_lifetime(float(lifetime_text))
                saved_message = (
                    f"Đã đặt thời gian tồn tại vật phẩm rơi dưới đất "
                    f"{result['seconds']:g} giây cho {result['eligible']} bản ghi "
                    f"trong {result['files']} bảng object"
                )
            else:
                raise ValueError("Nhóm cấu hình không hợp lệ")

            if unit_active("jxgame"):
                restart = sctl("restart", "jxgame", timeout=90)
                if restart.returncode != 0:
                    detail = (restart.stderr or restart.stdout or "systemctl restart jxgame thất bại").strip()
                    flash("err", f"{saved_message}, nhưng restart jxgame thất bại: {detail}")
                else:
                    flash("ok", f"{saved_message} và restart jxgame để áp dụng.")
            else:
                flash("ok", f"{saved_message}; jxgame đang tắt nên cấu hình sẽ áp dụng ở lần bật tiếp theo.")
        except Exception as e:
            flash("err", f"Không lưu được cấu hình: {e}")
        if settings_type == "simcity":
            return redirect(url_for("game_settings", tab=settings_type, simtab=sim_active_tab))
        if settings_type == "ground_item_lifetime":
            return redirect(url_for("game_settings", tab="drop_rate"))
        return redirect(url_for("game_settings", tab=settings_type))

    active_tab = request.args.get("tab", "experience")
    if active_tab not in ("experience", "da_tau", "monster_respawn", "drop_rate", "simcity", "item_stack"):
        active_tab = "experience"
    sim_active_tab = request.args.get("simtab", "basic")
    if sim_active_tab not in ("basic", "combat", "interaction", "stall", "skills", "tongkim", "competition"):
        sim_active_tab = "basic"
    feature_status = {}
    multiplier, feature_status["experience"] = _safe_game_setting_feature(
        "experience", "Kinh nghiệm", [GAMESETTING_PATH], _load_experience_state, 1.0
    )
    da_tau_daily_limit, feature_status["da_tau"] = _safe_game_setting_feature(
        "da_tau", "Nhiệm vụ", [DA_TAU_CONFIG_PATH], _read_da_tau_daily_limit, 0
    )
    monster_fallback = {
        "available": False, "seconds": 0, "seconds_values": [],
        "uniform": True, "templates": 0,
    }
    monster_respawn, feature_status["monster_respawn"] = _safe_game_setting_feature(
        "monster_respawn", "Hồi sinh quái", [NPC_TEMPLATE_PATH],
        _read_monster_respawn_state, monster_fallback,
    )
    simcity, feature_status["simcity"] = _safe_game_setting_feature(
        "simcity", "SimCity", [SIMCITY_BASE_CONFIG_PATH],
        _read_simcity_config, _default_simcity_state(),
    )
    drop_fallback = {
        "drop_rate": {"drop_percent": 0},
        "drop_money": {"money_rate": 0, "money_scale": 0, "money_rate_values": [],
                       "money_scale_values": [], "uniform": True},
        "drop_coin": {"enabled": False, "percent": 0, "percent_values": [0], "uniform": True},
        "special_drop": {
            "mystery_map": {"percent": 0, "percent_values": [0], "uniform": True},
            "mystery_record": {"percent": 0, "percent_values": [0], "uniform": True},
            "uniform": True,
        },
        "ground_item_lifetime": {
            "seconds": 0, "seconds_values": [], "uniform": True, "items": 0, "files": 0,
        },
    }
    drop_required = [
        *[_drop_rate_path(filename) for filename in DROP_RATE_FILES],
        *GROUND_ITEM_LIFETIME_PATHS,
    ]
    drop_bundle, feature_status["drop_rate"] = _safe_game_setting_feature(
        "drop_rate", "Rơi đồ", drop_required, _load_drop_settings_state, drop_fallback,
    )
    drop_rate = drop_bundle["drop_rate"]
    drop_money = drop_bundle["drop_money"]
    drop_coin = drop_bundle["drop_coin"]
    special_drop = drop_bundle["special_drop"]
    ground_item_lifetime = drop_bundle["ground_item_lifetime"]
    item_stack_fallback = {
        "limit": 0, "limits": [], "uniform": True, "eligible": 0, "files": 0,
    }
    item_stack_required = [
        ITEM_STACK_SERVER_BINARY,
        *_item_stack_paths(ITEM_STACK_SERVER_ROOT),
    ]
    item_stack, feature_status["item_stack"] = _safe_game_setting_feature(
        "item_stack", "Xếp chồng vật phẩm", item_stack_required,
        _item_stack_state, item_stack_fallback,
    )
    stack_pack_name = ""
    skill_rows = []
    for key, label, options in SIMCITY_FACTIONS:
        skill_rows.append({
            "key": key,
            "label": label,
            "options": options,
            "selected": simcity["skills"][key],
        })
    game_running = unit_active("jxgame")
    body = """
    <style>.setting-scan{display:flex;align-items:center;justify-content:space-between;gap:12px;flex-wrap:wrap}.setting-scan-list{display:flex;gap:7px;flex-wrap:wrap}.setting-scan-item{border:1px solid var(--line);border-radius:999px;padding:6px 9px;font-size:12px}.setting-scan-item.ok{color:var(--ok);border-color:rgba(57,217,138,.45)}.setting-scan-item.missing{color:var(--warn);border-color:rgba(255,176,46,.55)}.feature-unavailable{border-color:var(--warn)!important;background:rgba(255,176,46,.07)!important}.feature-unavailable code{display:block;margin-top:5px;overflow-wrap:anywhere}</style>
    <div class="card setting-scan"><div><h2 style="margin:0 0 4px">🔎 Cấu hình của server active</h2><span class="muted">{{settings_server.name if settings_server else 'Chưa chọn server'}}{% if settings_server %} · {{settings_server.path}}{% endif %}</span></div><div class="setting-scan-list">{% for item in feature_status.values() %}<span class="setting-scan-item {{'ok' if item.available else 'missing'}}">{{'●' if item.available else '○'}} {{item.label}}: {{'Có' if item.available else 'Chưa thấy'}}</span>{% endfor %}</div></div>
    <div class="settings-tabs" role="tablist" aria-label="Nhóm cấu hình game">
      <button type="button" class="settings-tab {% if active_tab == 'experience' %}active{% endif %}"
              data-settings-tab="experience" role="tab"
              aria-selected="{{'true' if active_tab == 'experience' else 'false'}}">Kinh nghiệm</button>
      <button type="button" class="settings-tab {% if active_tab == 'da_tau' %}active{% endif %}"
              data-settings-tab="da_tau" role="tab"
              aria-selected="{{'true' if active_tab == 'da_tau' else 'false'}}">Nhiệm vụ</button>
      <button type="button" class="settings-tab {% if active_tab == 'monster_respawn' %}active{% endif %}"
              data-settings-tab="monster_respawn" role="tab"
              aria-selected="{{'true' if active_tab == 'monster_respawn' else 'false'}}">Hồi sinh quái</button>
      <button type="button" class="settings-tab {% if active_tab == 'simcity' %}active{% endif %}"
              data-settings-tab="simcity" role="tab"
              aria-selected="{{'true' if active_tab == 'simcity' else 'false'}}">SimCity</button>
      <button type="button" class="settings-tab {% if active_tab == 'drop_rate' %}active{% endif %}"
              data-settings-tab="drop_rate" role="tab"
              aria-selected="{{'true' if active_tab == 'drop_rate' else 'false'}}">Rơi đồ</button>
      <button type="button" class="settings-tab {% if active_tab == 'item_stack' %}active{% endif %}"
              data-settings-tab="item_stack" role="tab"
              aria-selected="{{'true' if active_tab == 'item_stack' else 'false'}}">Xếp chồng vật phẩm</button>
    </div>
    <section class="settings-panel {% if active_tab == 'experience' %}active{% endif %}"
             data-settings-panel="experience" role="tabpanel">
    <div class="card"><h2>Cấu hình kinh nghiệm đánh quái</h2>
      <table>
        <tr><td>Hệ số hiện tại</td><td><b>x{{'%g'|format(multiplier)}}</b></td></tr>
        <tr><td>Trạng thái game</td><td>{% if game_running %}<span class="pill on">jxgame đang chạy</span>{% else %}<span class="pill off">jxgame đang tắt</span>{% endif %}</td></tr>
      </table>
      <p class="muted">Sau khi lưu, webadmin sẽ tự restart <b>jxgame</b> để áp dụng cấu hình.</p>
    </div>
    <div class="card"><h2>Đổi hệ số</h2>
      <form method="post" data-confirm="Lưu hệ số kinh nghiệm mới và restart jxgame để áp dụng?">
        <input type="hidden" name="settings_type" value="experience">
        <label>Hệ số kinh nghiệm</label>
        <input name="exp_multiplier" type="number" min="0" max="100" step="0.01" value="{{'%g'|format(multiplier)}}" required>
        <p class="muted">Ví dụ: nhập <b>1</b> = x1, <b>10</b> = x10, <b>20</b> = x20.</p>
        <button class="ok" style="margin-top:12px">💾 Lưu và restart game</button>
      </form>
    </div>
    </section>
    <section class="settings-panel {% if active_tab == 'da_tau' %}active{% endif %}"
             data-settings-panel="da_tau" role="tabpanel">
      <div class="card"><h2>Nhiệm vụ Dã Tẩu</h2>
        <table>
          <tr><td>Giới hạn hiện tại</td><td><b>{{da_tau_daily_limit}} nhiệm vụ/nhân vật/ngày</b></td></tr>
          <tr><td>Khoảng cho phép</td><td>{{da_tau_min}}–{{da_tau_max}} nhiệm vụ</td></tr>
          <tr><td>Trạng thái game</td><td>{% if game_running %}<span class="pill on">jxgame đang chạy</span>{% else %}<span class="pill off">jxgame đang tắt</span>{% endif %}</td></tr>
        </table>
        <form method="post" style="margin-top:18px"
              data-confirm="Lưu giới hạn nhiệm vụ Dã Tẩu và restart jxgame để áp dụng?">
          <input type="hidden" name="settings_type" value="da_tau">
          <label>Số nhiệm vụ tối đa cho mỗi nhân vật trong một ngày</label>
          <input name="da_tau_daily_limit" type="number" min="{{da_tau_min}}"
                 max="{{da_tau_max}}" step="1" value="{{da_tau_daily_limit}}" required>
          <p class="muted">Giá trị này sửa trực tiếp giới hạn Dã Tẩu gốc. Tính năng hoàn thành nhanh bằng Ngân lượng cũng dùng cùng mức giới hạn, không còn khóa cứng 40 lần.</p>
          <button class="ok" style="margin-top:12px">💾 Lưu và restart game</button>
        </form>
      </div>
    </section>
    <section class="settings-panel {% if active_tab == 'monster_respawn' %}active{% endif %}"
             data-settings-panel="monster_respawn" role="tabpanel">
      <div class="card"><h2>Thời gian hồi sinh quái thường</h2>
        <table>
          <tr><td>Phạm vi</td><td><b>{{monster_respawn.templates}} mẫu quái thường trên bản đồ luyện công</b></td></tr>
          <tr><td>Thời gian hiện tại</td><td>
            {% if not monster_respawn.available %}<b>Không có dữ liệu phù hợp</b>
            {% elif monster_respawn.uniform %}<b>{{'%g'|format(monster_respawn.seconds)}} giây</b>
            {% else %}<b>Đang có nhiều mức thời gian</b>{% endif %}
          </td></tr>
          <tr><td>Trạng thái game</td><td>{% if game_running %}<span class="pill on">jxgame đang chạy</span>{% else %}<span class="pill off">jxgame đang tắt</span>{% endif %}</td></tr>
        </table>
        {% if monster_respawn.available and not monster_respawn.uniform %}
        <p class="muted">Các mẫu quái hiện có nhiều mức: {{monster_respawn.seconds_values|join(', ')}} giây. Sau khi lưu, toàn bộ quái thường sẽ dùng chung giá trị mới.</p>
        {% endif %}
        {% if monster_respawn.available %}
        <form method="post" style="margin-top:18px"
              data-confirm="Lưu thời gian hồi sinh quái thường và restart jxgame để áp dụng?">
          <input type="hidden" name="settings_type" value="monster_respawn">
          <label>Thời gian hồi sinh sau khi quái chết (giây)</label>
          <input name="monster_respawn_seconds" type="number"
                 min="{{monster_respawn_min}}" max="{{monster_respawn_max}}" step="0.1"
                 value="{{'%g'|format(monster_respawn.seconds)}}" required>
          <p class="muted">Web tự quy đổi sang nhịp server 18 tick/giây. Nhập <b>0</b> để quái xuất hiện lại ngay; tối đa 3.600 giây.</p>
          <p class="muted">Chỉ đổi quái thường dùng bảng rơi của bản đồ luyện công. Không thay đổi Boss, quái nhiệm vụ, Tống Kim, quái sự kiện, NPC hỗ trợ hoặc SimCity.</p>
          <button class="ok" style="margin-top:12px">💾 Lưu thời gian hồi sinh</button>
        </form>
        {% else %}<div class="flash err" style="margin-top:16px">Server này không có mẫu quái thường phù hợp để chỉnh tự động. Các nhóm thiết lập khác vẫn sử dụng bình thường.</div>{% endif %}
      </div>
    </section>
    <section class="settings-panel {% if active_tab == 'drop_rate' %}active{% endif %}"
             data-settings-panel="drop_rate" role="tabpanel">
      <div class="card"><h2>Cấu hình rơi trang bị, tiền và vật phẩm đặc biệt</h2>
        <table>
          <tr><td>Phạm vi</td><td><b>Toàn bộ bản đồ quái thường</b></td></tr>
          <tr><td>Tỷ lệ rơi trang bị hiện tại</td><td><b>{{'%g'|format(drop_rate.drop_percent)}}%</b></td></tr>
          <tr><td>Ngân lượng — xác suất rơi</td><td><b>{{drop_money.money_rate_values|join(', ')}}%</b></td></tr>
          <tr><td>Ngân lượng — hệ số số lượng theo cấp quái</td><td><b>x{{drop_money.money_scale_values|join(', x')}}</b></td></tr>
          <tr><td>Tiền đồng — trạng thái</td><td>{% if drop_coin.enabled %}<span class="pill on">Đang bật</span>{% else %}<span class="pill off">Đang tắt</span>{% endif %}</td></tr>
          <tr><td>Tiền đồng — xác suất rơi</td><td><b>{{drop_coin.percent_values|join(', ')}}%</b></td></tr>
          <tr><td>Mật Đồ Thần Bí — xác suất rơi</td><td><b>{{special_drop.mystery_map.percent_values|join(', ')}}%</b></td></tr>
          <tr><td>Thần Bí Đồ Chí — xác suất rơi</td><td><b>{{special_drop.mystery_record.percent_values|join(', ')}}%</b></td></tr>
          <tr><td>Vật phẩm dưới đất — thời gian tồn tại</td><td>
            {% if ground_item_lifetime.uniform %}<b>{{'%g'|format(ground_item_lifetime.seconds)}} giây</b>
            {% else %}<b>Đang có nhiều mức thời gian</b>{% endif %}
          </td></tr>
          <tr><td>Trạng thái game</td><td>{% if game_running %}<span class="pill on">jxgame đang chạy</span>{% else %}<span class="pill off">jxgame đang tắt</span>{% endif %}</td></tr>
        </table>
        {% if not drop_money.uniform %}
        <p class="muted">Các nhóm cấp quái hiện đang có mức tiền khác nhau. Sau lần lưu tiếp theo, tất cả sẽ dùng chung giá trị trong form bên dưới.</p>
        {% endif %}
        {% if not special_drop.uniform %}
        <p class="muted">Các nhóm cấp quái hiện có tỷ lệ Mật Đồ/Đồ Chí khác nhau. Form đang lấy mức của nhóm cấp 10; sau lần lưu tiếp theo, toàn bộ nhóm quái thường sẽ dùng chung hai tỷ lệ đã nhập.</p>
        {% endif %}
        <form method="post" style="margin-top:18px"
              data-confirm="Lưu cấu hình chung cho toàn bộ bản đồ quái thường và restart jxgame?">
          <input type="hidden" name="settings_type" value="drop_rate">
          <h3>Trang bị</h3>
          <div class="row">
            <div>
              <label>Tỷ lệ rơi trang bị mỗi lượt (%)</label>
              <input name="drop_percent" type="number" min="0" max="100" step="0.1"
                     value="{{'%g'|format(drop_rate.drop_percent)}}" required>
            </div>
          </div>
          <h3 style="margin-top:18px">Ngân lượng</h3>
          <div class="row">
            <div>
              <label>Xác suất mỗi quái rơi Ngân lượng (%)</label>
              <input name="money_rate" type="number" min="0" max="100" step="1"
                     value="{{drop_money.money_rate}}" required>
            </div>
            <div>
              <label>Hệ số Ngân lượng theo cấp quái (lần)</label>
              <input name="money_scale" type="number" min="0" max="100" step="0.01"
                     value="{{'%g'|format(drop_money.money_scale)}}" required>
            </div>
          </div>
          <h3 style="margin-top:18px">Vật phẩm đặc biệt</h3>
          <div class="row">
            <div>
              <label>Tỷ lệ rơi Mật Đồ Thần Bí (%)</label>
              <input name="mystery_map_percent" type="number" min="0" max="100" step="0.0001"
                     value="{{'%g'|format(special_drop.mystery_map.percent)}}" required>
            </div>
            <div>
              <label>Tỷ lệ rơi Thần Bí Đồ Chí (%)</label>
              <input name="mystery_record_percent" type="number" min="0" max="100" step="0.0001"
                     value="{{'%g'|format(special_drop.mystery_record.percent)}}" required>
            </div>
          </div>
          <h3 style="margin-top:18px">Tiền đồng</h3>
          <label class="toggle-line">
            <input name="coin_enabled" type="checkbox" value="1" {% if drop_coin.enabled %}checked{% endif %}>
            <span>Bật rơi Tiền đồng khi đánh quái thường</span>
          </label>
          <div class="row">
            <div>
              <label>Xác suất mỗi quái rơi Tiền đồng (%)</label>
              <input name="coin_percent" type="number" min="0" max="100" step="0.01"
                     value="{{'%g'|format(drop_coin.percent)}}" required>
            </div>
          </div>
          <h3 style="margin-top:18px">Thời gian vật phẩm tồn tại dưới đất</h3>
          <div class="row">
            <div>
              <label>Thời gian trước khi vật phẩm biến mất (giây)</label>
              <input name="ground_item_lifetime_seconds" type="number"
                     min="{{ground_lifetime_min}}" max="{{ground_lifetime_max}}" step="0.1"
                     value="{{'%g'|format(ground_item_lifetime.seconds)}}" required>
            </div>
          </div>
          {% if not ground_item_lifetime.uniform %}
          <p class="muted">Dữ liệu cũ đang có nhiều mức: {{ground_item_lifetime.seconds_values|join(', ')}} giây. Giá trị trong ô là mức phổ biến nhất; sau khi lưu, toàn bộ vật phẩm sẽ dùng chung thời gian đã nhập.</p>
          {% endif %}
          <p class="muted">Thời gian áp dụng cho mọi object <b>Kind=Item</b>, gồm trang bị, thuốc và vật phẩm đặc biệt rơi dưới đất. Không đổi thời gian Ngân lượng, NPC, vật phẩm trong túi hoặc hạn sử dụng. Tối đa 3.600 giây để hạn chế vật phẩm tồn đọng gây lag.</p>
          <p class="muted">Tỷ lệ rơi trang bị chỉ áp dụng cho trang bị thường trong bảng rơi của bản đồ; cấp trang bị và thuộc tính vẫn theo cấp quái. 100% bảo đảm lượt quay bảng rơi chọn một trang bị.</p>
          <p class="muted">Ngân lượng có xác suất và số lượng riêng: xác suất <b>100%</b> nghĩa là mọi quái đều rơi; hệ số <b>1</b> giữ nguyên mức tiền mặc định, <b>2</b> là 200% (gấp đôi), <b>100</b> là 10.000% (gấp 100 lần).</p>
          <p class="muted">Mật Đồ Thần Bí và Thần Bí Đồ Chí được quay rơi riêng cho mỗi quái thường, độc lập với trang bị và độc lập với nhau. Ví dụ <b>0,05%</b> tương đương trung bình 1 vật phẩm trên 2.000 lượt hạ quái; <b>100%</b> thì mỗi quái rơi 1 vật phẩm của loại đó.</p>
          <p class="muted">Mỗi lần thành công rơi <b>1 Tiền đồng</b>. Khi tắt, web vẫn giữ tỷ lệ để dùng lại vào lần bật sau.</p>
          <p class="muted">Không thay đổi boss, sự kiện, Tống Kim, thuốc hoặc vật phẩm nhiệm vụ.</p>
          <button class="ok" style="margin-top:12px">💾 Lưu toàn bộ cấu hình rơi</button>
        </form>
      </div>
    </section>
    <section class="settings-panel {% if active_tab == 'item_stack' %}active{% endif %}"
             data-settings-panel="item_stack" role="tabpanel">
      <div class="card"><h2>Xếp chồng vật phẩm cùng loại</h2>
        <table>
          <tr><td>Giới hạn đang có trong dữ liệu</td><td>
            {% if item_stack.uniform %}<b>{{item_stack.limit}} vật phẩm/chồng</b>
            {% else %}<b>Nhiều mức: {{item_stack.limits|join(', ')}}</b>{% endif %}
          </td></tr>
          <tr><td>Trạng thái game</td><td>{% if game_running %}<span class="pill on">jxgame đang chạy</span>{% else %}<span class="pill off">jxgame đang tắt</span>{% endif %}</td></tr>
        </table>
        <form method="post" style="margin-top:18px"
              data-confirm="Đổi giới hạn xếp chồng trên server và restart jxgame?">
          <input type="hidden" name="settings_type" value="item_stack">
          <label>Số lượng tối đa trong một chồng</label>
          <input name="stack_limit" type="number" min="{{stack_min}}" max="{{stack_max}}" step="1"
                 value="{{item_stack.limit}}" required>
          <p class="muted">Áp dụng cho thuốc (gồm Ngũ Hoa Ngọc Lộ Hoàn), vật phẩm script/phụ trợ và vật phẩm nhiệm vụ đã được engine đánh dấu có thể xếp chồng. Không ép trang bị hoặc vật phẩm có thuộc tính riêng vào cùng một chồng.</p>
          <button class="ok" style="margin-top:12px">💾 Lưu giới hạn trên server</button>
        </form>
      </div>
    </section>
    <section class="settings-panel {% if active_tab == 'simcity' %}active{% endif %}"
             data-settings-panel="simcity" role="tabpanel">
	    <div class="card"><h2>Cấu hình SimCity</h2>
	      <form method="post" data-confirm="Lưu cấu hình SimCity và restart jxgame để áp dụng cho toàn bộ bot?">
	        <input type="hidden" name="settings_type" value="simcity">
	        <input type="hidden" name="sim_active_tab" value="{{sim_active_tab}}" data-sim-active-input>
	        <div class="simcity-tabs" role="tablist" aria-label="Nhóm cấu hình SimCity">
	          <button type="button" class="simcity-tab {% if sim_active_tab == 'basic' %}active{% endif %}" data-simcity-tab="basic">Cơ bản</button>
	          <button type="button" class="simcity-tab {% if sim_active_tab == 'combat' %}active{% endif %}" data-simcity-tab="combat">Chiến đấu</button>
	          <button type="button" class="simcity-tab {% if sim_active_tab == 'interaction' %}active{% endif %}" data-simcity-tab="interaction">Tương tác</button>
	          <button type="button" class="simcity-tab {% if sim_active_tab == 'stall' %}active{% endif %}" data-simcity-tab="stall">Bán hàng</button>
	          <button type="button" class="simcity-tab {% if sim_active_tab == 'skills' %}active{% endif %}" data-simcity-tab="skills">Kỹ năng</button>
	          <button type="button" class="simcity-tab {% if sim_active_tab == 'tongkim' %}active{% endif %}" data-simcity-tab="tongkim">Tống Kim</button>
	          <button type="button" class="simcity-tab {% if sim_active_tab == 'competition' %}active{% endif %}" data-simcity-tab="competition">Thi đấu</button>
	        </div>
	        <div class="simcity-panel {% if sim_active_tab == 'basic' %}active{% endif %}" data-simcity-panel="basic">
	        <h2>Dân số</h2>
	        <label class="toggle-line">
	          <input name="sim_population_enabled" type="checkbox" value="1" {% if simcity.population_enabled == 1 %}checked{% endif %}>
	          <span>Tự động tạo SimCity khi có người vào bản đồ</span>
	        </label>
	        <div class="row">
	          <div><label>Số bot mỗi thành</label>
	            <input name="sim_city_size" type="number" min="0" max="1000" step="5" value="{{simcity.city_size}}" required>
	          </div>
	          <div><label>Số bot mỗi thôn</label>
	            <input name="sim_village_size" type="number" min="0" max="500" step="5" value="{{simcity.village_size}}" required>
	          </div>
	        </div>
	        <label class="toggle-line">
	          <input name="sim_training_enabled" type="checkbox" value="1" {% if simcity.training_enabled == 1 %}checked{% endif %}>
	          <span>Tạo bot tại các bản đồ luyện công cấp 20–110</span>
	        </label>
	        <div class="row">
	          <div><label>Số nhóm bot luyện công</label>
	            <input name="sim_training_size" type="number" min="0" max="500" value="{{simcity.training_size}}" required>
	            <p class="muted">Giá trị mặc định dùng cho bản đồ chưa có cấu hình riêng. Mỗi nhóm gồm 1 trưởng nhóm và 6–7 NPC con, tương đương khoảng <b>7–8 NPC/nhóm</b>.</p>
	          </div>
	        </div>
	        <h2 style="margin-top:22px">Số nhóm theo từng bản đồ luyện công</h2>
	        <p class="muted">Nhập 0 để không tạo bot luyện công trên bản đồ đó. Ví dụ nhập 2 tương đương khoảng 14–16 NPC trên map.</p>
	        <div class="scroll"><table><thead><tr><th>Cấp</th><th>Map ID</th><th>Bản đồ</th><th>Số nhóm</th><th>NPC dự kiến</th></tr></thead><tbody>
	        {% for map_level, map_id, map_name in sim_training_maps %}<tr>
	          <td>{{map_level}}</td><td>{{map_id}}</td><td>{{map_name}}</td><td>
	            <input name="sim_training_map_{{map_id}}" type="number" min="0" max="500"
	                   value="{{simcity.training_maps[map_id]}}" style="width:120px;padding:7px" required>
	          </td><td>khoảng {{simcity.training_maps[map_id] * 7}}–{{simcity.training_maps[map_id] * 8}} NPC</td>
	        </tr>{% endfor %}
	        </tbody></table></div>
	        </div>
	        <div class="simcity-panel {% if sim_active_tab == 'combat' %}active{% endif %}" data-simcity-panel="combat">
	        <h2 style="margin-top:22px">Chiến đấu</h2>
	        <div class="row">
          <div><label>Sinh lực tối thiểu</label>
            <input name="sim_hp_min" type="number" min="1000" max="10000000" step="1000" value="{{simcity.hp_min}}" required>
          </div>
          <div><label>Sinh lực tối đa</label>
            <input name="sim_hp_max" type="number" min="1000" max="10000000" step="1000" value="{{simcity.hp_max}}" required>
          </div>
          <div><label>Tốc độ đánh NPC</label>
            <input name="sim_attack_speed" type="number" min="50" max="500" value="{{simcity.attack_speed}}" required>
          </div>
        </div>
        <div class="row">
          <div><label>Nhịp đánh trực tiếp (giây)</label>
            <input name="sim_cast_delay" type="number" min="1" max="10" value="{{simcity.cast_delay}}" required>
          </div>
          <div><label>Nhịp AI đánh thường (giây)</label>
            <input name="sim_normal_cast_delay" type="number" min="1" max="10" value="{{simcity.normal_cast_delay}}" required>
          </div>
          <div><label>Cấp skill tấn công</label>
	            <input name="sim_skill_level" type="number" min="1" max="20" value="{{simcity.skill_level}}" required>
	          </div>
	        </div>
	        <label class="toggle-line">
	          <input name="sim_bot_vs_bot" type="checkbox" value="1" {% if simcity.bot_vs_bot == 1 %}checked{% endif %}>
	          <span>Cho phép bot đánh nhau với bot</span>
	        </label>
	        <label class="toggle-line">
	          <input name="sim_aggro_player" type="checkbox" value="1" {% if simcity.aggro_player == 1 %}checked{% endif %}>
	          <span>Cho phép bot chủ động tấn công người chơi</span>
	        </label>
	        <div class="row">
	          <div><label>Bán kính tìm bot đối thủ</label>
	            <input name="sim_combat_radius" type="number" min="1" max="50" value="{{simcity.combat_radius}}" required>
	          </div>
	          <div><label>Bán kính phát hiện người chơi</label>
	            <input name="sim_fight_player_radius" type="number" min="1" max="50" value="{{simcity.fight_player_radius}}" required>
	          </div>
	          <div><label>Bán kính phát hiện NPC</label>
	            <input name="sim_fight_npc_radius" type="number" min="1" max="50" value="{{simcity.fight_npc_radius}}" required>
	          </div>
	          <div><label>Bán kính tham gia trận đánh</label>
	            <input name="sim_fight_scan_radius" type="number" min="1" max="50" value="{{simcity.fight_scan_radius}}" required>
	          </div>
	        </div>
	        <div class="row">
	          <div><label>Thời gian chiến đấu tối thiểu (giây)</label>
	            <input name="sim_fight_time_min" type="number" min="0" max="86400" value="{{simcity.fight_time_min}}" required>
	          </div>
	          <div><label>Thời gian chiến đấu tối đa (giây)</label>
	            <input name="sim_fight_time_max" type="number" min="0" max="86400" value="{{simcity.fight_time_max}}" required>
	          </div>
	          <div><label>Thời gian nghỉ tối thiểu (giây)</label>
	            <input name="sim_rest_time_min" type="number" min="0" max="3600" value="{{simcity.rest_time_min}}" required>
	          </div>
	          <div><label>Thời gian nghỉ tối đa (giây)</label>
	            <input name="sim_rest_time_max" type="number" min="0" max="3600" value="{{simcity.rest_time_max}}" required>
	          </div>
	        </div>
	        <div class="row">
	          <div><label>Tự hồi sinh lực (%)</label>
	            <input name="sim_life_restore_percent" type="number" min="0" max="100" value="{{simcity.life_restore_percent}}" required>
	          </div>
	          <div><label>Tỷ lệ bot thành thị dùng buff (%)</label>
	            <input name="sim_city_buff_percent" type="number" min="0" max="100" value="{{simcity.city_buff_percent}}" required>
	          </div>
	        </div>
	        <div class="row">
	          <label class="toggle-line"><input name="sim_ngami_buff" type="checkbox" value="1" {% if simcity.ngami_buff == 1 %}checked{% endif %}><span>Buff Nga Mi</span></label>
	          <label class="toggle-line"><input name="sim_debuff_enabled" type="checkbox" value="1" {% if simcity.debuff_enabled == 1 %}checked{% endif %}><span>Debuff Ngũ Độc</span></label>
	          <label class="toggle-line"><input name="sim_faction_buff" type="checkbox" value="1" {% if simcity.faction_buff == 1 %}checked{% endif %}><span>Buff trấn phái</span></label>
	        </div>
	        </div>
	        <div class="simcity-panel {% if sim_active_tab == 'interaction' %}active{% endif %}" data-simcity-panel="interaction">
	        <h2 style="margin-top:22px">Tương tác</h2>
	        <div class="row">
	          <div><label>Tần suất trò chuyện (/1.000)</label>
	            <input name="sim_chat_chance" type="number" min="0" max="1000" value="{{simcity.chat_chance}}" required>
	          </div>
	          <div><label>Tỷ lệ rơi tiền (/10.000)</label>
	            <input name="sim_drop_money_chance" type="number" min="0" max="10000" value="{{simcity.drop_money_chance}}" required>
	          </div>
	          <div><label>Tiền rơi tối thiểu</label>
	            <input name="sim_drop_money_min" type="number" min="1" max="100000000" value="{{simcity.drop_money_min}}" required>
	          </div>
	          <div><label>Tiền rơi tối đa</label>
	            <input name="sim_drop_money_max" type="number" min="1" max="100000000" value="{{simcity.drop_money_max}}" required>
	          </div>
	        </div>
	        <label class="toggle-line">
	          <input name="sim_outfit_enabled" type="checkbox" value="1" {% if simcity.outfit_enabled == 1 %}checked{% endif %}>
	          <span>Bật ngoại trang ngẫu nhiên</span>
	        </label>
	        <div class="row">
	          <div><label>Tỷ lệ có ngoại trang (%)</label>
	            <input name="sim_outfit_chance" type="number" min="0" max="100" value="{{simcity.outfit_chance}}" required>
	          </div>
	          <div><label>Tỷ lệ có tên bang (%)</label>
	            <input name="sim_guild_chance" type="number" min="0" max="100" value="{{simcity.guild_chance}}" required>
	          </div>
	        </div>
	        <div class="row">
	          <div><label>Gửi vật phẩm giao dịch (giây)</label>
	            <input name="sim_trade_send_delay" type="number" min="0" max="300" value="{{simcity.trade_send_delay}}" required>
	          </div>
	          <div><label>Chờ hoàn tất giao dịch (giây)</label>
	            <input name="sim_trade_post_delay" type="number" min="0" max="300" value="{{simcity.trade_post_delay}}" required>
	          </div>
	          <div><label>Chờ người chơi chọn giao dịch (giây)</label>
	            <input name="sim_trade_wait_delay" type="number" min="0" max="300" value="{{simcity.trade_wait_delay}}" required>
	          </div>
	          <div><label>Thời gian chào hỏi (giây)</label>
	            <input name="sim_trade_greet_delay" type="number" min="0" max="300" value="{{simcity.trade_greet_delay}}" required>
	          </div>
	          <div><label>Thời gian chờ rời đi (giây)</label>
	            <input name="sim_trade_bye_delay" type="number" min="0" max="300" value="{{simcity.trade_bye_delay}}" required>
	          </div>
	        </div>
	        </div>
	        <div class="simcity-panel {% if sim_active_tab == 'stall' %}active{% endif %}" data-simcity-panel="stall">
	        <h2 style="margin-top:22px">Bot bán hàng</h2>
        <label class="toggle-line">
          <input name="sim_stall_enabled" type="checkbox" value="1" {% if simcity.stall_enabled == 1 %}checked{% endif %}>
          <span>Bật bot bày bán trong thành và thôn</span>
        </label>
        <div class="row">
          <div><label>Trong thành - tối thiểu</label>
            <input name="sim_stall_city_min" type="number" min="0" max="200" value="{{simcity.stall_city_min}}" required>
          </div>
          <div><label>Trong thành - tối đa</label>
            <input name="sim_stall_city_max" type="number" min="0" max="200" value="{{simcity.stall_city_max}}" required>
          </div>
        </div>
        <div class="row">
          <div><label>Trong thôn - tối thiểu</label>
            <input name="sim_stall_village_min" type="number" min="0" max="100" value="{{simcity.stall_village_min}}" required>
          </div>
          <div><label>Trong thôn - tối đa</label>
            <input name="sim_stall_village_max" type="number" min="0" max="100" value="{{simcity.stall_village_max}}" required>
          </div>
          <div><label>Quanh Dã Tẩu - tối thiểu</label>
            <input name="sim_stall_datau_min" type="number" min="0" max="100" value="{{simcity.stall_datau_min}}" required>
          </div>
          <div><label>Quanh Dã Tẩu - tối đa</label>
            <input name="sim_stall_datau_max" type="number" min="0" max="100" value="{{simcity.stall_datau_max}}" required>
          </div>
        </div>
        </div>
        <div class="simcity-panel {% if sim_active_tab == 'skills' %}active{% endif %}" data-simcity-panel="skills">
        <h2 style="margin-top:22px">Skill tấn công theo môn phái</h2>
        <div class="scroll" style="margin-top:16px">
          <table>
            <thead><tr><th>Môn phái</th><th>Skill tấn công</th></tr></thead>
            <tbody>{% for row in skill_rows %}
              <tr><td><b>{{row.label}}</b></td><td>
                <select name="sim_skill_{{row.key}}">
                  <option value="0" {% if row.selected == 0 %}selected{% endif %}>Tự động như cấu hình gốc</option>
                  {% for skill_id, skill_name in row.options %}
                    <option value="{{skill_id}}" {% if row.selected == skill_id %}selected{% endif %}>{{skill_id}} - {{skill_name}}</option>
                  {% endfor %}
                </select>
              </td></tr>
            {% endfor %}</tbody>
          </table>
        </div>
        <p class="muted">Chỉ các skill đã có sẵn trong server và client hiện tại được phép chọn.</p>
        </div>
        <div class="simcity-panel {% if sim_active_tab == 'tongkim' %}active{% endif %}" data-simcity-panel="tongkim">
          <h2>Tống Kim</h2>
          <label class="toggle-line">
            <input name="sim_tk_enabled" type="checkbox" value="1" {% if simcity.tk_enabled == 1 %}checked{% endif %}>
            <span>Cho phép bot SimCity tham gia Tống Kim</span>
          </label>
          <div class="row">
            <div><label>Số bot phe Tống</label>
              <input name="sim_tk_tong_count" type="number" min="0" max="500" value="{{simcity.tk_tong_count}}" required>
            </div>
            <div><label>Số bot phe Kim</label>
              <input name="sim_tk_kim_count" type="number" min="0" max="500" value="{{simcity.tk_kim_count}}" required>
            </div>
            <div><label>Cấp độ bot</label>
              <input name="sim_tk_bot_level" type="number" min="1" max="255" value="{{simcity.tk_bot_level}}" required>
            </div>
          </div>
          <h2 style="margin-top:22px">Cấp chiến trường tham gia</h2>
          <div class="row">
            <label class="toggle-line"><input name="sim_tk_level_beginner" type="checkbox" value="1" {% if simcity.tk_level_beginner == 1 %}checked{% endif %}><span>Sơ cấp</span></label>
            <label class="toggle-line"><input name="sim_tk_level_intermediate" type="checkbox" value="1" {% if simcity.tk_level_intermediate == 1 %}checked{% endif %}><span>Trung cấp</span></label>
            <label class="toggle-line"><input name="sim_tk_level_advanced" type="checkbox" value="1" {% if simcity.tk_level_advanced == 1 %}checked{% endif %}><span>Cao cấp</span></label>
          </div>
          <h2 style="margin-top:22px">Hành vi chiến đấu</h2>
          <label class="toggle-line">
            <input name="sim_tk_revive" type="checkbox" value="1" {% if simcity.tk_revive == 1 %}checked{% endif %}>
            <span>Bot hồi sinh sau khi bị hạ</span>
          </label>
          <div class="row">
            <div><label>Ở hậu doanh tối thiểu (giây)</label>
              <input name="sim_tk_spawn_stay_min" type="number" min="0" max="600" value="{{simcity.tk_spawn_stay_min}}" required>
            </div>
            <div><label>Ở hậu doanh tối đa (giây)</label>
              <input name="sim_tk_spawn_stay_max" type="number" min="0" max="600" value="{{simcity.tk_spawn_stay_max}}" required>
            </div>
            <div><label>Bán kính chiến đấu</label>
              <input name="sim_tk_combat_radius" type="number" min="1" max="100" value="{{simcity.tk_combat_radius}}" required>
            </div>
          </div>
          <p class="muted">Số bot được tính riêng cho từng phe. Mặc định hiện tại là 100 phe Tống và 100 phe Kim.</p>
        </div>
        <div class="simcity-panel {% if sim_active_tab == 'competition' %}active{% endif %}" data-simcity-panel="competition">
          <h2>Võ Lâm Liên Đấu — Đơn đấu tự do</h2>
          <label class="toggle-line">
            <input name="sim_league_enabled" type="checkbox" value="1" {% if simcity.league_enabled == 1 %}checked{% endif %} disabled>
            <span>Ghép đối thủ SimCity khi chỉ còn một chiến đội, thay cho thắng miễn phí</span>
          </label>
          <div class="row">
            <div><label>Cấp bot</label>
              <input name="sim_league_bot_level" type="number" min="1" max="255" value="{{simcity.league_bot_level}}" required disabled>
            </div>
            <div><label>Sinh lực bot</label>
              <input name="sim_league_bot_hp" type="number" min="1000" max="10000000" step="1000" value="{{simcity.league_bot_hp}}" required disabled>
            </div>
          </div>
          <p class="muted">Chỉ áp dụng cho loại “Đơn đấu tự do”. Người chơi báo danh bình thường; nếu không có đối thủ thật sẽ vào đấu trường gặp một SIM. Kết quả thắng, thua hoặc hòa được tính như một trận Liên Đấu.</p>

          <h2>Đấu trường 1 đấu 1 với SIM</h2>
          <label class="toggle-line">
            <input name="sim_duel_enabled" type="checkbox" value="1" {% if simcity.duel_enabled == 1 %}checked{% endif %}>
            <span>Mở đăng ký tại Công Bình Tử ở Thành Đô</span>
          </label>
          <label class="toggle-line">
            <input name="sim_duel_bot_enabled" type="checkbox" value="1" {% if simcity.duel_bot_enabled == 1 %}checked{% endif %} disabled>
            <span>Ghép đối thủ SimCity nếu không tìm thấy người chơi thật</span>
          </label>
          <div class="row">
            <div><label>Cấp bot</label>
              <input name="sim_duel_bot_level" type="number" min="1" max="255" value="{{simcity.duel_bot_level}}" required disabled>
            </div>
            <div><label>Sinh lực bot</label>
              <input name="sim_duel_bot_hp" type="number" min="1000" max="10000000" step="1000" value="{{simcity.duel_bot_hp}}" required disabled>
            </div>
            <div><label>Chờ người thật (giây)</label>
              <input name="sim_duel_wait_seconds" type="number" min="5" max="300" value="{{simcity.duel_wait_seconds}}" required disabled>
            </div>
            <div><label>Chuẩn bị (giây)</label>
              <input name="sim_duel_ready_seconds" type="number" min="5" max="120" value="{{simcity.duel_ready_seconds}}" required disabled>
            </div>
            <div><label>Thời gian đấu (giây)</label>
              <input name="sim_duel_fight_seconds" type="number" min="30" max="900" value="{{simcity.duel_fight_seconds}}" required disabled>
            </div>
          </div>
          <p class="muted">Tại Công Bình Tử: tổ đội với một SIM, chọn “Được thôi”, xác nhận rồi cả hai sẽ vào Diễn Võ Trường để đấu 1v1. SIM dùng đúng cấp, sinh lực và kỹ năng hiện có của nó.</p>

          <h2 style="margin-top:26px">Bách Nhân Lôi Đài</h2>
          <label class="toggle-line">
            <input name="sim_arena_enabled" type="checkbox" value="1" {% if simcity.arena_enabled == 1 %}checked{% endif %} disabled>
            <span>Dùng cấu hình SimCity cho NPC thách đấu khi lôi chủ không có người khiêu chiến</span>
          </label>
          <div class="row">
            <div><label>Cấp bot</label>
              <input name="sim_arena_bot_level" type="number" min="1" max="255" value="{{simcity.arena_bot_level}}" required disabled>
            </div>
            <div><label>Sinh lực bot</label>
              <input name="sim_arena_bot_hp" type="number" min="1000" max="10000000" step="1000" value="{{simcity.arena_bot_hp}}" required disabled>
            </div>
            <div><label>Chờ người khiêu chiến (giây)</label>
              <input name="sim_arena_wait_seconds" type="number" min="5" max="300" value="{{simcity.arena_wait_seconds}}" required disabled>
            </div>
          </div>
          <p class="muted">Nếu tắt, Bách Nhân giữ nguyên NPC và thời gian chờ mặc định của game.</p>

          <h2 style="margin-top:26px">Tỉ Võ môn phái</h2>
          <label class="toggle-line">
            <input name="sim_championship_enabled" type="checkbox" value="1" {% if simcity.championship_enabled == 1 %}checked{% endif %} disabled>
            <span>Ghép bot SimCity khi vòng đấu chỉ còn một người, thay cho thắng miễn phí</span>
          </label>
          <div class="row">
            <div><label>Cấp bot</label>
              <input name="sim_championship_bot_level" type="number" min="1" max="255" value="{{simcity.championship_bot_level}}" required disabled>
            </div>
            <div><label>Sinh lực bot</label>
              <input name="sim_championship_bot_hp" type="number" min="1000" max="10000000" step="1000" value="{{simcity.championship_bot_hp}}" required disabled>
            </div>
            <div><label>Thời gian tối đa (giây)</label>
              <input name="sim_championship_fight_seconds" type="number" min="30" max="600" value="{{simcity.championship_fight_seconds}}" required disabled>
            </div>
          </div>
          <p class="muted">Người chơi thắng/thua/hòa và nhận điểm như trận thường; bot không được ghi bảng xếp hạng hay nhận phần thưởng.</p>
        </div>
        <button class="ok" style="margin-top:12px">💾 Lưu SimCity và restart game</button>
      </form>
    </div>
    </section>
    <script>
    const gameFeatureStatus={{feature_status|tojson}};
    document.querySelectorAll('[data-settings-panel]').forEach(function(panel){
      const state=gameFeatureStatus[panel.dataset.settingsPanel];
      if(!state||state.available)return;
      const notice=document.createElement('div');notice.className='card feature-unavailable';
      const title=document.createElement('h2');title.textContent='⚠️ '+state.label+' — Chưa thấy';notice.appendChild(title);
      const message=document.createElement('p');message.textContent=state.message;notice.appendChild(message);
      if(state.missing&&state.missing.length){const intro=document.createElement('p');intro.className='muted';intro.textContent='File còn thiếu trong server active:';notice.appendChild(intro);state.missing.forEach(function(path){const code=document.createElement('code');code.textContent=path;notice.appendChild(code)})}
      const help=document.createElement('p');help.className='muted';help.textContent='Nhóm này được khóa để không ghi nhầm dữ liệu. Các nhóm có trạng thái “Có” vẫn dùng bình thường.';notice.appendChild(help);
      panel.replaceChildren(notice);
      const tab=document.querySelector('[data-settings-tab="'+panel.dataset.settingsPanel+'"]');if(tab){tab.classList.add('feature-missing');tab.title=state.message}
    });
    document.querySelectorAll('[data-settings-tab]').forEach(function(tab) {
      tab.addEventListener('click', function() {
        var name = tab.dataset.settingsTab;
        document.querySelectorAll('[data-settings-tab]').forEach(function(item) {
          var selected = item.dataset.settingsTab === name;
          item.classList.toggle('active', selected);
          item.setAttribute('aria-selected', selected ? 'true' : 'false');
        });
        document.querySelectorAll('[data-settings-panel]').forEach(function(panel) {
          panel.classList.toggle('active', panel.dataset.settingsPanel === name);
        });
        var url = '?tab=' + encodeURIComponent(name);
        if (name === 'simcity') {
          var simInput = document.querySelector('[data-sim-active-input]');
          url += '&simtab=' + encodeURIComponent(simInput ? simInput.value : 'basic');
        }
        history.replaceState(null, '', url);
      });
    });
    document.querySelectorAll('[data-simcity-tab]').forEach(function(tab) {
      tab.addEventListener('click', function() {
        var name = tab.dataset.simcityTab;
        document.querySelectorAll('[data-simcity-tab]').forEach(function(item) {
          item.classList.toggle('active', item.dataset.simcityTab === name);
        });
        document.querySelectorAll('[data-simcity-panel]').forEach(function(panel) {
          panel.classList.toggle('active', panel.dataset.simcityPanel === name);
        });
        var input = document.querySelector('[data-sim-active-input]');
        if (input) input.value = name;
        history.replaceState(null, '', '?tab=simcity&simtab=' + encodeURIComponent(name));
      });
    });
    var competitionPanel = document.querySelector('[data-simcity-panel="competition"]');
    if (competitionPanel) {
      var simcityForm = competitionPanel.closest('form');
      if (simcityForm) {
        simcityForm.addEventListener('submit', function() {
          competitionPanel.querySelectorAll('input[disabled]').forEach(function(input) {
            input.disabled = false;
          });
        });
      }
    }
    </script>
    """
    return game_settings_page(body, "game_settings", multiplier=multiplier, simcity=simcity,
                drop_rate=drop_rate, drop_money=drop_money, drop_coin=drop_coin,
                special_drop=special_drop, ground_item_lifetime=ground_item_lifetime,
                skill_rows=skill_rows, game_running=game_running, active_tab=active_tab,
                sim_active_tab=sim_active_tab, item_stack=item_stack,
                stack_pack_name=stack_pack_name, stack_min=ITEM_STACK_MIN,
                stack_max=ITEM_STACK_MAX,
                ground_lifetime_min=GROUND_ITEM_LIFETIME_MIN,
                ground_lifetime_max=GROUND_ITEM_LIFETIME_MAX,
                da_tau_daily_limit=da_tau_daily_limit,
                da_tau_min=DA_TAU_DAILY_LIMIT_MIN,
                da_tau_max=DA_TAU_DAILY_LIMIT_MAX,
                monster_respawn=monster_respawn,
                monster_respawn_min=MONSTER_RESPAWN_SECONDS_MIN,
                monster_respawn_max=MONSTER_RESPAWN_SECONDS_MAX,
                sim_training_maps=SIMCITY_TRAINING_MAPS,
                feature_status=feature_status, settings_server=active_server_info())

@app.route("/ky-tran-cac", methods=["GET", "POST"])
def ky_tran_cac():
    query = (request.values.get("q") or "").strip()
    if request.method == "POST":
        try:
            action = (request.form.get("action") or "").strip().lower()
            if action == "reload_ktc":
                relay_was_active = unit_active("jxs3relay")
                game_was_active = unit_active("jxgame")
                if not relay_was_active and not game_was_active:
                    raise RuntimeError("Server đang tắt; cấu hình sẽ tự được nạp khi bật server")
                relay = sctl("restart", "jxs3relay", timeout=90)
                if relay.returncode != 0:
                    detail = (relay.stderr or relay.stdout).strip()
                    raise RuntimeError(f"Không khởi động lại được S3Relay: {detail}")
                if game_was_active:
                    game = sctl("restart", "jxgame", timeout=90)
                    if game.returncode != 0:
                        detail = (game.stderr or game.stdout).strip()
                        raise RuntimeError(f"Không khởi động lại được GameServer: {detail}")
                message = "Đã nạp lại cấu hình Kỳ Trân Các qua S3Relay"
                if game_was_active:
                    message += "/GameServer"
            elif action in ("create_category", "rename_category", "delete_category"):
                message = _ktc_update_category(
                    action, request.form.get("sell_id"), request.form.get("name")
                )
                message += "; chưa restart server"
            else:
                message = _ktc_update(
                    action,
                    request.form.get("goods_id"),
                    request.form.get("sell_id"),
                    request.form.get("price"),
                )
                message += "; chưa restart server"
            flash("ok", message)
        except (TypeError, ValueError) as exc:
            flash("err", str(exc) or "Dữ liệu Kỳ Trân Các không hợp lệ")
        except Exception as exc:
            flash("err", f"Lỗi cập nhật Kỳ Trân Các: {exc}")
        return redirect(url_for("ky_tran_cac", q=query))

    try:
        state = _ktc_state(query)
        ktc_error = ""
    except Exception as exc:
        ktc_error = "Chưa thấy hoặc không đọc được dữ liệu Kỳ Trân Các: " + str(exc)
        flash("err", ktc_error)
        state = {
            "categories": [], "category_count": 0, "item_count": 0,
            "catalog_count": 0, "candidates": [], "query": query,
        }
    body = """
    {% if ktc_error %}<div class="card" style="border-color:var(--warn);background:rgba(255,176,46,.07)"><h2>⚠️ Kỳ Trân Các — Chưa thấy</h2><p>{{ktc_error}}</p><p class="muted">Cần đủ goods.txt, buysell.txt và shop/type.txt trong server active. Các trang Thiết lập game khác vẫn dùng bình thường.</p></div>{% endif %}
    <div {% if ktc_error %}hidden{% endif %}>
    <div class="card">
      <h2>🛒 Quản lý Kỳ Trân Các</h2>
      <p class="muted">Hiện có <b>{{ktc.item_count}}</b> vật phẩm trong
      <b>{{ktc.category_count}}</b> nhóm; catalog có <b>{{ktc.catalog_count}}</b> mã hàng.
      Giá bên dưới là giá <b>Đồng tiền</b>. Mỗi lần lưu sẽ tự tạo bản sao lưu của
      <code>goods.txt</code>, <code>buysell.txt</code> hoặc <code>shop/type.txt</code> tương ứng.</p>
      <form method="get" action="/ky-tran-cac" class="row" style="align-items:flex-end">
        <div style="flex:4"><label>Tìm vật phẩm trong catalog</label>
          <input name="q" value="{{ktc.query}}"
                 placeholder="Tên, Goods ID hoặc Genre,Detail,Particular"></div>
        <div style="flex:0;min-width:105px"><button>🔎 Tìm</button></div>
        {% if ktc.query %}<div style="flex:0;min-width:105px"><a class="btn mut" href="/ky-tran-cac">Xóa lọc</a></div>{% endif %}
      </form>
    </div>

    <div class="card" style="border-color:var(--warn);background:rgba(255,176,46,.06)">
      <h2>Áp dụng thay đổi vào game</h2>
      <p class="muted">Bạn có thể thêm, gỡ, sửa giá và tab liên tục mà server không restart.
      Khi chỉnh xong toàn bộ, bấm nút dưới đây một lần để nạp cấu hình mới. Người chơi đang online sẽ bị ngắt kết nối.</p>
      <form method="post" data-confirm="Restart S3Relay và GameServer để áp dụng toàn bộ thay đổi Kỳ Trân Các?">
        <input type="hidden" name="action" value="reload_ktc"><input type="hidden" name="q" value="{{ktc.query}}">
        <button style="background:var(--warn);color:#241500">🔄 Nạp lại Kỳ Trân Các (restart server)</button>
      </form>
    </div>

    <div class="card">
      <h2>Quản lý tab ({{ktc.category_count}}/{{category_max}})</h2>
      <form method="post" class="row" style="align-items:flex-end;margin-bottom:16px"
            data-confirm="Tạo tab Kỳ Trân Các mới?">
        <input type="hidden" name="action" value="create_category"><input type="hidden" name="q" value="{{ktc.query}}">
        <div style="flex:3"><label>Tên tab mới</label><input name="name" maxlength="24" placeholder="Ví dụ: Trang Bị" required></div>
        <div style="flex:0;min-width:130px"><button class="ok" {% if ktc.category_count >= category_max %}disabled{% endif %}>＋ Thêm tab</button></div>
      </form>
      <div class="scroll"><table><thead><tr><th>SellID</th><th>Tên tab</th><th>Số vật phẩm</th><th>Đổi tên</th><th>Xóa tab</th></tr></thead><tbody>
      {% for group in ktc.categories %}<tr><td>{{group.sell_id}}</td><td>{{group.name}}</td><td>{{group['items']|length}}</td><td>
        <form method="post" style="display:flex;gap:6px;align-items:center">
          <input type="hidden" name="action" value="rename_category"><input type="hidden" name="sell_id" value="{{group.sell_id}}"><input type="hidden" name="q" value="{{ktc.query}}">
          <input name="name" maxlength="24" value="{{group.name}}" style="width:180px;padding:7px" required><button>Lưu tên</button>
        </form></td><td>
        <form method="post" data-confirm="Xóa tab {{group.name}}?">
          <input type="hidden" name="action" value="delete_category"><input type="hidden" name="sell_id" value="{{group.sell_id}}"><input type="hidden" name="q" value="{{ktc.query}}">
          <button class="err" {% if group['items'] %}disabled title="Hãy gỡ hết vật phẩm trước"{% endif %}>Xóa</button>
        </form></td></tr>{% endfor %}
      </tbody></table></div>
      <p class="muted">Tab mới tự dùng một SellID trống, không đè dữ liệu cửa hàng khác. Chỉ xóa được tab không còn vật phẩm.</p>
    </div>

    <div class="card">
      <h2>Thêm nhanh bằng Goods ID</h2>
      <form method="post" class="row" style="align-items:flex-end"
            data-confirm="Thêm vật phẩm này vào Kỳ Trân Các?">
        <input type="hidden" name="action" value="add"><input type="hidden" name="q" value="{{ktc.query}}">
        <div><label>Goods ID</label><input type="number" name="goods_id" min="1" required></div>
        <div><label>Nhóm</label><select name="sell_id" required>
          {% for group in ktc.categories %}<option value="{{group.sell_id}}">{{group.name}} (SellID {{group.sell_id}})</option>{% endfor %}
        </select></div>
        <div><label>Giá Đồng tiền</label><input type="number" name="price" min="{{price_min}}" max="{{price_max}}" value="1" required></div>
        <div style="flex:0;min-width:105px"><button class="ok">＋ Thêm</button></div>
      </form>
      <p class="muted">Vật phẩm phải có sẵn trong catalog. Nếu chưa biết Goods ID, hãy tìm theo tên ở ô phía trên.</p>
    </div>

    {% if ktc.query %}
    <div class="card"><h2>Kết quả tìm “{{ktc.query}}” (tối đa 100)</h2>
      {% if ktc.candidates %}<div class="scroll"><table><thead><tr>
        <th>Goods ID</th><th>Tên</th><th>Genre,Detail,Particular</th><th>Cấp</th><th>Giá hiện tại</th><th>Thêm</th>
      </tr></thead><tbody>{% for item in ktc.candidates %}<tr>
        <td>#{{item.id}}</td><td>{{item.name}}</td>
        <td>{{item.genre}},{{item.detail}},{{item.particular}}</td><td>{{item.level}}</td>
        <td>{{'{:,}'.format(item.price)}}</td><td>
        {% if item.in_shop %}<span class="pill on">Đang bán</span>{% else %}
          <form method="post" style="display:flex;gap:6px;align-items:center"
                data-confirm="Thêm {{item.name}} vào Kỳ Trân Các?">
            <input type="hidden" name="action" value="add"><input type="hidden" name="goods_id" value="{{item.id}}"><input type="hidden" name="q" value="{{ktc.query}}">
            <select name="sell_id" style="width:130px;padding:7px" required>{% for group in ktc.categories %}<option value="{{group.sell_id}}">{{group.name}}</option>{% endfor %}</select>
            <input type="number" name="price" min="{{price_min}}" max="{{price_max}}" value="{{item.price if item.price > 0 else 1}}" style="width:115px;padding:7px" required>
            <button class="ok">Thêm</button>
          </form>{% endif %}</td>
      </tr>{% endfor %}</tbody></table></div>
      {% else %}<p class="muted">Không tìm thấy vật phẩm phù hợp.</p>{% endif %}
    </div>{% endif %}

    {% for group in ktc.categories %}
    <div class="card"><h2>{{group.name}} — {{group['items']|length}} vật phẩm <span class="muted">(SellID {{group.sell_id}})</span></h2>
      {% if group['items'] %}<div class="scroll"><table><thead><tr>
        <th>Goods ID</th><th>Tên</th><th>Genre,Detail,Particular</th><th>Cấp</th><th>Giá Đồng tiền</th><th>Gỡ</th>
      </tr></thead><tbody>{% for item in group['items'] %}<tr>
        <td>#{{item.id}}</td><td>{{item.name}}</td>
        <td>{{item.genre}},{{item.detail}},{{item.particular}}</td><td>{{item.level}}</td><td>
          <form method="post" style="display:flex;gap:6px;align-items:center">
            <input type="hidden" name="action" value="edit_price"><input type="hidden" name="goods_id" value="{{item.id}}"><input type="hidden" name="q" value="{{ktc.query}}">
            <input type="number" name="price" min="{{price_min}}" max="{{price_max}}" value="{{item.price}}" style="width:145px;padding:7px" required>
            <button>Lưu giá</button>
          </form></td><td>
          <form method="post" data-confirm="Gỡ {{item.name}} khỏi nhóm {{group.name}}?">
            <input type="hidden" name="action" value="remove"><input type="hidden" name="goods_id" value="{{item.id}}"><input type="hidden" name="sell_id" value="{{group.sell_id}}"><input type="hidden" name="q" value="{{ktc.query}}">
            <button class="err">Gỡ</button>
          </form></td>
      </tr>{% endfor %}</tbody></table></div>
      {% else %}<p class="muted">Nhóm này chưa có vật phẩm.</p>{% endif %}
    </div>{% endfor %}
    </div>
    """
    return game_settings_page(body, "ky_tran_cac", ktc=state,
                price_min=KTC_PRICE_MIN, price_max=KTC_PRICE_MAX,
                category_max=KTC_CATEGORY_MAX, ktc_error=ktc_error)

BACKUP_PAGE_V116 = r"""
<style>
.backup-summary{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:1px;background:var(--line);border:1px solid var(--line);border-radius:11px;overflow:hidden;margin-bottom:16px}.backup-stat{background:var(--card);padding:11px 13px;min-width:0}.backup-stat small{display:block;color:var(--mut);margin-bottom:3px}.backup-stat b,.backup-stat span{display:block;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.backup-subnav{display:flex;gap:6px;align-items:center;margin-bottom:16px}.backup-subnav .settings-tab{margin:0}.backup-subnav .gear{margin-left:auto}.backup-head{display:flex;align-items:center;justify-content:space-between;gap:12px;margin-bottom:13px}.backup-head h2{margin:0}.backup-actions{display:flex;gap:7px;align-items:center;flex-wrap:wrap}.backup-filter{display:flex;gap:7px;align-items:center;flex-wrap:wrap}.filter-chip{padding:7px 12px;border-radius:20px;background:#293f54;color:#cbd9e4;text-decoration:none;font-size:13px}.filter-chip.active{background:var(--acc);color:#fff}.backup-table td{vertical-align:middle}.backup-file{display:block;max-width:410px;overflow:hidden;text-overflow:ellipsis}.backup-direct-actions{display:flex;gap:5px;align-items:center;flex-wrap:wrap;min-width:390px}.backup-direct-actions form{margin:0}.backup-direct-actions button,.backup-direct-actions .btn{padding:7px 10px;white-space:nowrap}.backup-modal{display:none;position:fixed;inset:0;background:rgba(0,0,0,.65);z-index:100;align-items:center;justify-content:center;padding:18px}.backup-modal.open{display:flex}.backup-dialog{width:min(700px,100%);max-height:86vh;background:var(--card);border:1px solid var(--line);border-radius:14px;box-shadow:0 18px 60px rgba(0,0,0,.4);display:flex;flex-direction:column}.backup-dialog.wide{width:min(900px,100%)}.backup-modal-head,.backup-modal-foot{padding:14px 16px;display:flex;align-items:center;gap:9px}.backup-modal-head{border-bottom:1px solid var(--line)}.backup-modal-head h2{margin:0;flex:1}.backup-modal-body{padding:16px;overflow:auto}.backup-modal-foot{border-top:1px solid var(--line);justify-content:flex-end}.schedule-grid{display:grid;grid-template-columns:minmax(480px,1fr) minmax(420px,1fr);gap:16px;align-items:start}.compact-history{max-height:560px;overflow:auto}.schedule-days{display:flex;gap:8px;flex-wrap:wrap;margin:12px 0}.schedule-days label{display:flex;align-items:center;gap:5px;margin:0}.schedule-days input{width:17px}.danger-box{border-color:var(--err)!important}.status-good{color:var(--ok)}.status-bad{color:var(--err)}
@media(max-width:1100px){.backup-summary{grid-template-columns:1fr 1fr}.schedule-grid{grid-template-columns:1fr}}@media(max-width:700px){.backup-summary{grid-template-columns:1fr}.backup-head{align-items:flex-start;flex-direction:column}.backup-table th:nth-child(4),.backup-table td:nth-child(4){display:none}}
</style>
<h1 class="page-heading">Server & Dữ liệu</h1>
<div class="server-center-tabs"><a class="server-center-tab" href="{{manager_setup_url()}}?tab=versions">Server game</a><a class="server-center-tab" href="{{manager_setup_url()}}?tab=logs">Log & Dung lượng</a><a class="server-center-tab active" href="{{url_for('database_tools')}}">Sao lưu & Khôi phục</a></div>
<style>.db-access{display:grid;grid-template-columns:minmax(0,1fr) auto;gap:18px;align-items:center}.db-access-title{display:flex;align-items:center;gap:9px;margin-bottom:11px}.db-access-title h2{margin:0}.db-credentials{display:grid;grid-template-columns:1fr 1fr;gap:10px}.db-credential{padding:11px 13px;border:1px solid var(--line);border-radius:9px;background:rgba(201,164,95,.035)}.db-credential small,.db-credential span{display:block;color:var(--mut)}.db-credential code{display:block;margin:5px 0;color:var(--fg);font-size:14px;overflow-wrap:anywhere}.db-access-actions{display:flex;gap:7px;flex-wrap:wrap;justify-content:flex-end}.db-grid{display:grid;grid-template-columns:1fr 1fr;gap:12px}.db-warning{padding:10px 12px;border-left:3px solid var(--warn);background:rgba(232,162,59,.08);color:var(--mut)}.db-progress{margin-top:14px;padding:13px;border:1px solid var(--line);border-radius:9px}.db-progress progress{width:100%}.db-progress-head{display:flex;justify-content:space-between;gap:10px}.db-reveal-countdown{color:var(--warn);font-variant-numeric:tabular-nums}@media(max-width:700px){.db-credentials,.db-grid{grid-template-columns:1fr}.db-access{grid-template-columns:1fr}.db-access-actions{justify-content:flex-start}}</style>
<section class="card db-access"><div><div class="db-access-title"><h2>🔐 Kết nối database</h2><span class="pill on">Chỉ máy chủ</span></div><div class="db-credentials"><div class="db-credential"><small>MySQL server1</small><b>root · 127.0.0.1:3306</b><code id="mysqlSecret">••••••••••••</code><span>Mật khẩu dùng bởi Web, backup và Goddess</span></div><div class="db-credential"><small>MSSQL account_tong</small><b>sa · 127.0.0.1:1433</b><code id="mssqlSecret">••••••••••••</code><span>Mật khẩu dùng bởi Web, backup và PaySys</span></div></div><small class="db-reveal-countdown" id="secretCountdown"></small></div><div class="db-access-actions"><button type="button" class="mut" data-backup-modal="databaseRevealModal">👁 Xem mật khẩu</button><button type="button" data-backup-modal="databasePasswordModal">🔁 Đổi mật khẩu</button></div></section>
<div class="backup-modal" id="databaseRevealModal"><div class="backup-dialog"><div class="backup-modal-head"><h2>👁 Xem mật khẩu database</h2><button type="button" class="mut backup-modal-close">✕</button></div><form id="databaseRevealForm" method="post" action="{{url_for('manager_ext.reveal_database_passwords')}}"><input type="hidden" name="csrf_token" value="{{manager_csrf}}"><div class="backup-modal-body"><p class="muted">Xác minh lại để tránh người đang dùng phiên đăng nhập xem được mật khẩu. Sau khi hiện, mật khẩu tự ẩn sau 30 giây.</p><label>Mật khẩu Admin hiện tại<input type="password" name="admin_password" autocomplete="current-password" required autofocus></label><p class="status-bad" id="databaseRevealError"></p></div><div class="backup-modal-foot"><button type="button" class="mut backup-modal-close">Hủy</button><button>Xác minh và xem</button></div></form></div></div>
<div class="backup-modal" id="databasePasswordModal"><div class="backup-dialog wide"><div class="backup-modal-head"><h2>🔁 Đổi mật khẩu database</h2><button type="button" class="mut backup-modal-close">✕</button></div><form id="databasePasswordForm" method="post" action="{{url_for('manager_ext.rotate_database_passwords')}}"><input type="hidden" name="csrf_token" value="{{manager_csrf}}"><input type="hidden" name="stop_server" value="0"><div class="backup-modal-body"><div class="db-warning">Nếu game đang chạy, hệ thống sẽ hỏi xác nhận rồi Stop All an toàn. Sau đó hệ thống sao lưu, đổi mật khẩu thật, đồng bộ file JX và kiểm tra kết nối. Game được giữ ở trạng thái tắt sau khi hoàn tất.</div><label>Mật khẩu Admin hiện tại<input type="password" name="admin_password" autocomplete="current-password" required></label><div class="db-grid"><label>Mật khẩu MySQL mới<input type="password" name="mysql_password" autocomplete="new-password" minlength="12" maxlength="20" required></label><label>Nhập lại MySQL<input type="password" name="mysql_confirm" autocomplete="new-password" minlength="12" maxlength="20" required></label><label>Mật khẩu MSSQL mới<input type="password" name="mssql_password" autocomplete="new-password" minlength="12" maxlength="20" required></label><label>Nhập lại MSSQL<input type="password" name="mssql_confirm" autocomplete="new-password" minlength="12" maxlength="20" required></label></div><p class="muted">12–20 ký tự; có chữ hoa, chữ thường, số và @ _ ! . hoặc -.</p><button type="button" class="mut" id="generateDatabasePasswords">Tạo hai mật khẩu mạnh</button><div class="db-progress" id="databasePasswordProgress" hidden><div class="db-progress-head"><b id="databasePasswordPhase">Đang chuẩn bị</b><span id="databasePasswordPercent">0%</span></div><progress id="databasePasswordBar" max="100" value="0"></progress><p class="muted" id="databasePasswordMessage"></p></div></div><div class="backup-modal-foot"><button type="button" class="mut backup-modal-close">Hủy</button><button id="databasePasswordSubmit">Sao lưu và đổi mật khẩu</button></div></form></div></div>
<div class="backup-summary"><div class="backup-stat"><small>MySQL server1</small><b class="{{'status-good' if backup_summary.mysql.ok else 'status-bad'}}">{{'Kết nối OK' if backup_summary.mysql.ok else 'Mất kết nối'}}</b><span class="muted">{{backup_summary.mysql.latest}}</span></div><div class="backup-stat"><small>MSSQL account_tong</small><b class="{{'status-good' if backup_summary.mssql.ok else 'status-bad'}}">{{'Kết nối OK' if backup_summary.mssql.ok else 'Mất kết nối'}}</b><span class="muted">{{backup_summary.mssql.latest}}</span></div><div class="backup-stat"><small>Lịch kế tiếp</small><b>{{backup_summary.next_schedule}}</b><span class="muted">Backup không cần tắt game</span></div><div class="backup-stat"><small>Dung lượng kho</small><b>{{'%.1f MB'|format(backup_summary.total_size/1048576)}}</b><span class="muted">{{backup_summary.total_files}} file</span></div></div>
<div class="backup-subnav"><a class="settings-tab {{'active' if tab=='files' else ''}}" href="?tab=files">Kho backup</a><a class="settings-tab {{'active' if tab=='automation' else ''}}" href="?tab=automation">Lịch tự động & Lịch sử</a><button type="button" class="mut gear" data-backup-modal="backupSettingsModal">⚙ Cài đặt</button></div>
{% if tab == 'files' %}
<section class="card"><div class="backup-head"><div><h2>Kho backup</h2><span class="muted">Restore cần Stop All; hệ thống tự tạo bản an toàn trước khi ghi đè.</span></div><div class="backup-actions"><form method="post" action="{{url_for('database_backup')}}"><input type="hidden" name="kind" value="all"><button class="ok">💾 Sao lưu tất cả</button></form><form method="post" action="{{url_for('database_backup')}}"><input type="hidden" name="kind" value="mysql"><button>MySQL</button></form><form method="post" action="{{url_for('database_backup')}}"><input type="hidden" name="kind" value="mssql"><button>MSSQL</button></form><button type="button" class="mut" data-backup-modal="backupUploadModal">＋ Tải file lên</button></div></div>
<form method="get" class="backup-filter"><input type="hidden" name="tab" value="files"><a class="filter-chip {{'active' if kind_filter=='all' else ''}}" href="?tab=files&kind=all">Tất cả</a><a class="filter-chip {{'active' if kind_filter=='mysql' else ''}}" href="?tab=files&kind=mysql">MySQL</a><a class="filter-chip {{'active' if kind_filter=='mssql' else ''}}" href="?tab=files&kind=mssql">MSSQL</a><input name="q" value="{{query}}" placeholder="Tìm tên file hoặc ghi chú" style="max-width:330px"><button>Lọc</button></form></section>
<section class="card scroll"><table class="backup-table"><thead><tr><th>Database</th><th>File / Ghi chú</th><th>Dung lượng</th><th>Thời gian</th><th>Nguồn</th><th>Thao tác</th></tr></thead><tbody>{% for item in artifacts %}<tr><td><span class="pill {{'on' if item.kind=='mysql' else 'off'}}">{{item.kind|upper}}</span></td><td><b class="backup-file" title="{{item.filename}}">{{item.filename}}</b><span class="muted">{{item.note or 'Không có ghi chú'}}</span>{% if item.is_latest %} <span class="pill on">Mới nhất</span>{% endif %}</td><td>{{'%.2f MB'|format(item.size/1048576)}}</td><td>{{item.time.strftime('%d/%m/%Y %H:%M')}}</td><td>{{'Tải lên' if item.source=='uploaded' else ('Tự động' if item.source=='schedule' else ('An toàn' if item.source=='safety' else 'Thủ công'))}}</td><td><div class="backup-direct-actions"><form method="post" action="{{url_for('database_artifact_restore',artifact_id=item.id)}}" data-prompt="Restore sẽ ghi đè {{item.label}}. Nhập đúng tên file để xác nhận:" data-prompt-title="Xác nhận Restore" data-prompt-target="confirm_filename" data-prompt-exact="{{item.filename}}" data-prompt-mismatch="Tên file chưa chính xác." data-dialog-danger="1"><input type="hidden" name="confirm_filename"><button class="err">↩ Restore</button></form><a class="btn mut" href="{{url_for('database_artifact_download',artifact_id=item.id)}}">⬇ Tải xuống</a><form method="post" action="{{url_for('database_artifact_note',artifact_id=item.id)}}" data-prompt="Nhập ghi chú cho file backup:" data-prompt-title="Sửa ghi chú" data-prompt-target="note" data-prompt-initial="{{item.note}}"><input type="hidden" name="note"><button class="mut">✎ Ghi chú</button></form><form method="post" action="{{url_for('database_artifact_delete',artifact_id=item.id)}}" data-confirm="Xóa vĩnh viễn {{item.filename}}?"><button class="err" {{'disabled' if item.is_latest else ''}}>🗑 Xóa</button></form></div></td></tr>{% else %}<tr><td colspan="6" class="muted">Chưa có file backup phù hợp.</td></tr>{% endfor %}</tbody></table></section>
<details class="card danger-box"><summary style="cursor:pointer;font-weight:700;color:var(--err)">Tác vụ nguy hiểm — xóa toàn bộ nhân vật</summary><p class="muted">Xóa nhân vật MySQL server1 nhưng giữ tài khoản MSSQL. Hệ thống tự tạo backup an toàn.</p><form method="post" action="/database/delete-all-characters" data-confirm="XÓA SẠCH TẤT CẢ NHÂN VẬT?"><input name="confirm" placeholder="Nhập XOANHANVAT" required style="max-width:240px;display:inline-block"><button class="err">Xóa tất cả nhân vật</button></form></details>
{% else %}
<div class="schedule-grid"><section class="card"><div class="backup-head"><div><h2>Lịch backup</h2><span class="muted">Tự chạy theo giờ server.</span></div><button type="button" class="ok" data-backup-modal="scheduleModal">＋ Thêm lịch</button></div><div class="scroll"><table><thead><tr><th>Database</th><th>Tần suất</th><th>Lần kế tiếp</th><th>Trạng thái</th><th>Thao tác</th></tr></thead><tbody>{% for job in schedules %}<tr><td>{{job.label}}</td><td>{{schedule_summary(job.schedule)}}</td><td>{{job.next_run.strftime('%d/%m/%Y %H:%M') if job.next_run else 'Không có'}}</td><td><span class="pill {{'on' if job.enabled else 'off'}}">{{'Bật' if job.enabled else 'Tắt'}}</span></td><td><div class="backup-actions"><form method="post" action="{{url_for('database_schedule_run',job_id=job.id)}}"><button class="ok" title="Chạy ngay">▶</button></form><a class="btn mut" href="?tab=automation&edit_job={{job.id}}">✎</a><form method="post" action="{{url_for('database_schedule_toggle',job_id=job.id)}}"><button class="mut">{{'Tắt' if job.enabled else 'Bật'}}</button></form><form method="post" action="{{url_for('database_schedule_delete',job_id=job.id)}}" data-confirm="Xóa lịch backup này?"><button class="err">🗑</button></form></div></td></tr>{% else %}<tr><td colspan="5" class="muted">Chưa có lịch tự động.</td></tr>{% endfor %}</tbody></table></div></section>
<section class="card"><h2>Lịch sử gần đây</h2><div class="scroll compact-history"><table><thead><tr><th>Database</th><th>Thời gian</th><th>Trạng thái</th><th>File / Lỗi</th></tr></thead><tbody>{% for run in runs %}<tr><td>{{run.database|upper}}</td><td>{{run.scheduled_at|replace('T',' ')}}</td><td><span class="pill {{'on' if run.status=='succeeded' else 'off'}}">{{'Thành công' if run.status=='succeeded' else 'Lỗi'}}</span></td><td>{{run.file or run.error or '—'}}{% if run.status=='failed' %}<form method="post" action="{{url_for('database_schedule_run',job_id=run.job_id)}}"><button>Chạy lại</button></form>{% endif %}</td></tr>{% else %}<tr><td colspan="4" class="muted">Chưa có lịch sử.</td></tr>{% endfor %}</tbody></table></div></section></div>
{% endif %}
<div class="backup-modal" id="backupUploadModal"><div class="backup-dialog"><div class="backup-modal-head"><h2>＋ Tải file backup lên kho</h2><button type="button" class="mut backup-modal-close">✕</button></div><form method="post" action="{{url_for('database_backup_upload')}}" enctype="multipart/form-data"><div class="backup-modal-body"><label>Database<select name="kind"><option value="mysql">MySQL (.sql/.sql.gz)</option><option value="mssql">MSSQL (.bak)</option></select></label><label>File<input type="file" name="backup_file" accept=".sql,.gz,.bak" required></label><label>Ghi chú<input name="note" maxlength="500"></label></div><div class="backup-modal-foot"><button type="button" class="mut backup-modal-close">Hủy</button><button>Tải lên</button></div></form></div></div>
<div class="backup-modal" id="scheduleModal"><div class="backup-dialog wide"><div class="backup-modal-head"><h2>{{'Sửa lịch backup' if edit_job.id else 'Thêm lịch backup'}}</h2><button type="button" class="mut backup-modal-close">✕</button></div><form method="post" action="{{url_for('database_schedule_save')}}" id="scheduleForm"><input type="hidden" name="job_id" value="{{edit_job.id}}"><div class="backup-modal-body"><div class="row"><label>Database<select name="database" {{'disabled' if edit_job.id else ''}}><option value="mysql" {{'selected' if edit_job.database=='mysql' else ''}}>MySQL</option><option value="mssql" {{'selected' if edit_job.database=='mssql' else ''}}>MSSQL</option></select>{% if edit_job.id %}<input type="hidden" name="database" value="{{edit_job.database}}">{% endif %}</label><label>Kiểu lịch<select name="schedule_type" id="scheduleType"><option value="hourly" {{'selected' if edit_job.schedule.type=='hourly' else ''}}>Hàng giờ</option><option value="daily" {{'selected' if edit_job.schedule.type=='daily' else ''}}>Hàng ngày</option><option value="weekly" {{'selected' if edit_job.schedule.type=='weekly' else ''}}>Hàng tuần</option></select></label><label id="hourEvery">Mỗi bao nhiêu giờ<input type="number" name="every_hours" min="1" max="23" value="{{edit_job.schedule.get('every_hours',2)}}"></label><label id="hourMinute">Vào phút thứ<input type="number" name="minute" min="0" max="59" value="{{edit_job.schedule.get('minute',0)}}"></label><label id="scheduleTime">Giờ server<input type="time" name="time" value="{{edit_job.schedule.get('time','03:00')}}"></label></div><div id="weekDays" class="schedule-days">{% for value,label in day_options %}<label><input type="checkbox" name="days" value="{{value}}" {{'checked' if value in edit_job.schedule.get('days',[]) else ''}}> {{label}}</label>{% endfor %}</div><label class="toggle-line"><input type="checkbox" name="enabled" {{'checked' if edit_job.enabled else ''}}> Bật lịch này</label></div><div class="backup-modal-foot"><button type="button" class="mut backup-modal-close">Hủy</button><button>{{'Cập nhật' if edit_job.id else 'Tạo lịch'}}</button></div></form></div></div>
<div class="backup-modal" id="backupSettingsModal"><div class="backup-dialog"><div class="backup-modal-head"><h2>⚙ Thời gian giữ backup tự động</h2><button type="button" class="mut backup-modal-close">✕</button></div><form method="post" action="{{url_for('database_backup_settings')}}"><div class="backup-modal-body"><p class="muted">Chỉ tự dọn file do lịch tạo; backup thủ công và file tải lên được giữ nguyên.</p><label>MySQL — số ngày<input type="number" name="mysql_days" min="1" max="3650" value="{{state.retention.mysql}}"></label><label>MSSQL — số ngày<input type="number" name="mssql_days" min="1" max="3650" value="{{state.retention.mssql}}"></label></div><div class="backup-modal-foot"><button type="button" class="mut backup-modal-close">Hủy</button><button>Lưu cài đặt</button></div></form></div></div>
<script>(function(){function open(modal){modal.classList.add('open')}function close(modal){modal.classList.remove('open')}document.querySelectorAll('[data-backup-modal]').forEach(button=>button.addEventListener('click',()=>open(document.getElementById(button.dataset.backupModal))));document.querySelectorAll('.backup-modal-close').forEach(button=>button.addEventListener('click',()=>close(button.closest('.backup-modal'))));document.querySelectorAll('.backup-modal').forEach(modal=>modal.addEventListener('click',event=>{if(event.target===modal)close(modal)}));document.addEventListener('keydown',event=>{if(event.key==='Escape')document.querySelectorAll('.backup-modal.open').forEach(close)});const type=document.getElementById('scheduleType'),hourEvery=document.getElementById('hourEvery'),hourMinute=document.getElementById('hourMinute'),scheduleTime=document.getElementById('scheduleTime'),weekDays=document.getElementById('weekDays');if(type){function update(){const value=type.value;hourEvery.style.display=hourMinute.style.display=value==='hourly'?'block':'none';scheduleTime.style.display=value==='hourly'?'none':'block';weekDays.style.display=value==='weekly'?'flex':'none'}type.addEventListener('change',update);update()}{% if edit_job.id %}open(document.getElementById('scheduleModal'));{% endif %}{% if open_backup_settings %}open(document.getElementById('backupSettingsModal'));{% endif %}})();</script>
"""

@app.route("/database")
def database_tools():
    requested_tab = request.args.get("tab", "files")
    open_backup_settings = requested_tab == "settings"
    tab = "automation" if requested_tab in ("automation", "schedule", "history") else "files"
    kind_filter = request.args.get("kind", "all")
    if kind_filter not in ("all", "mysql", "mssql"):
        kind_filter = "all"
    query = (request.args.get("q") or "").strip().lower()
    all_artifacts = _backup_artifacts()
    artifacts = [row for row in all_artifacts
                 if (kind_filter == "all" or row["kind"] == kind_filter)
                 and (not query or query in row["filename"].lower() or query in row["note"].lower())]
    state = _backup_state()
    schedules = []
    for job in state["schedules"]:
        next_run = _next_schedule_time(job) if job.get("enabled", True) else None
        schedules.append({**job, "next_run": next_run, "label": _backup_kind_label(job.get("database"))})
    edit_id = request.args.get("edit_job", "")
    edit_job = next((job for job in schedules if job.get("id") == edit_id), None)
    if not edit_job:
        edit_job = {"id": "", "database": "mysql", "enabled": True,
                    "schedule": {"type": "daily", "every_hours": 2, "minute": 0,
                                 "time": "03:00", "days": []}}
    runs = list(reversed(state["runs"][-200:]))
    body = """
    <h1 class="page-heading">Server & Dữ liệu</h1>
    <div class="server-center-tabs">
      <a class="server-center-tab" href="{{ manager_setup_url() }}?tab=versions">Phiên bản & IP</a>
      <a class="server-center-tab" href="{{ manager_setup_url() }}?tab=logs">Log & Dung lượng</a>
      <a class="server-center-tab active" href="{{ url_for('database_tools') }}">Sao lưu & Khôi phục</a>
    </div>
    <div class="settings-tabs">
      <a class="settings-tab {{'active' if tab=='files' else ''}}" href="?tab=files">File backup</a>
      <a class="settings-tab {{'active' if tab=='schedule' else ''}}" href="?tab=schedule">Lịch tự động</a>
      <a class="settings-tab {{'active' if tab=='history' else ''}}" href="?tab=history">Lịch sử</a>
      <a class="settings-tab {{'active' if tab=='settings' else ''}}" href="?tab=settings">Cài đặt</a>
    </div>

    {% if tab == 'files' %}
    <div class="card">
      <div class="tools">
        <form method="post" action="{{url_for('database_backup')}}"><input type="hidden" name="kind" value="all"><button class="ok">💾 Sao lưu tất cả</button></form>
        <form method="post" action="{{url_for('database_backup')}}"><input type="hidden" name="kind" value="mysql"><button>MySQL</button></form>
        <form method="post" action="{{url_for('database_backup')}}"><input type="hidden" name="kind" value="mssql"><button>MSSQL</button></form>
      </div>
      <details><summary style="cursor:pointer;font-weight:700">⬆️ Tải một file backup lên kho</summary>
        <form method="post" action="{{url_for('database_backup_upload')}}" enctype="multipart/form-data" class="row" style="align-items:flex-end;margin-top:10px">
          <label>Database<select name="kind"><option value="mysql">MySQL (.sql/.sql.gz)</option><option value="mssql">MSSQL (.bak)</option></select></label>
          <label>File<input type="file" name="backup_file" accept=".sql,.gz,.bak" required></label>
          <label>Ghi chú<input name="note" maxlength="500" placeholder="Nguồn hoặc nội dung bản backup"></label>
          <div style="flex:0;min-width:100px"><button>Tải lên</button></div>
        </form>
      </details>
      <form method="get" class="row" style="align-items:flex-end;margin-top:14px"><input type="hidden" name="tab" value="files">
        <label>Database<select name="kind"><option value="all">Tất cả</option><option value="mysql" {{'selected' if kind_filter=='mysql' else ''}}>MySQL</option><option value="mssql" {{'selected' if kind_filter=='mssql' else ''}}>MSSQL</option></select></label>
        <label>Tìm kiếm<input name="q" value="{{query}}" placeholder="Tên file hoặc ghi chú"></label>
        <div style="flex:0;min-width:100px"><button>Lọc</button></div>
      </form>
    </div>
    <div class="card scroll"><table><thead><tr><th>Database</th><th>Tên file</th><th>Dung lượng</th><th>Cập nhật</th><th>Ghi chú / Nguồn</th><th>Thao tác</th></tr></thead><tbody>
      {% for item in artifacts %}<tr>
        <td><span class="pill {{'on' if item.kind=='mysql' else 'off'}}">{{item.kind|upper}}</span></td>
        <td><b>{{item.filename}}</b>{% if item.is_latest %} <span class="pill on">Mới nhất</span>{% endif %}</td>
        <td>{{'%.2f MB'|format(item.size/1048576)}}</td><td>{{item.time.strftime('%d/%m/%Y %H:%M:%S')}}</td>
        <td>{{item.note or '—'}}<br><span class="muted">{{'Tải lên' if item.source=='uploaded' else ('Tự động' if item.source=='schedule' else ('Bản an toàn' if item.source=='safety' else 'Thủ công'))}}</span></td>
        <td><div style="display:flex;gap:5px;flex-wrap:wrap">
          <form method="post" action="{{url_for('database_artifact_restore', artifact_id=item.id)}}" data-prompt="Restore sẽ ghi đè {{item.label}}. Nhập đúng tên file để xác nhận:" data-prompt-title="Xác nhận Restore" data-prompt-target="confirm_filename" data-prompt-exact="{{item.filename}}" data-prompt-mismatch="Tên file chưa chính xác." data-dialog-danger="1"><input type="hidden" name="confirm_filename"><button class="err" title="Khôi phục">↩</button></form>
          <a class="btn mut" href="{{url_for('database_artifact_download', artifact_id=item.id)}}" title="Tải xuống">⬇</a>
          <form method="post" action="{{url_for('database_artifact_note', artifact_id=item.id)}}" data-prompt="Nhập ghi chú cho file backup:" data-prompt-title="Sửa ghi chú" data-prompt-target="note" data-prompt-initial="{{item.note}}"><input type="hidden" name="note"><button class="mut" title="Sửa ghi chú">✎</button></form>
          <form method="post" action="{{url_for('database_artifact_delete', artifact_id=item.id)}}" data-confirm="Xóa vĩnh viễn {{item.filename}}?"><button class="err" title="{{'Không xóa file mới nhất' if item.is_latest else 'Xóa'}}" {% if item.is_latest %}disabled{% endif %}>🗑</button></form>
        </div></td>
      </tr>{% else %}<tr><td colspan="6" class="muted">Chưa có file backup phù hợp.</td></tr>{% endfor %}
    </tbody></table></div>
    <details class="card" style="border-color:var(--err)"><summary style="cursor:pointer;font-weight:700;color:var(--err)">Vùng nguy hiểm — xóa toàn bộ nhân vật</summary>
      <p class="muted">Xóa nhân vật MySQL server1 nhưng vẫn giữ tài khoản MSSQL. Hệ thống tự tạo backup an toàn trước khi xóa.</p>
      <form method="post" action="/database/delete-all-characters" data-confirm="XÓA SẠCH TẤT CẢ NHÂN VẬT?"><input name="confirm" placeholder="Nhập XOANHANVAT" required style="max-width:240px;display:inline-block"><button class="err">Xóa tất cả nhân vật</button></form>
    </details>
    {% elif tab == 'schedule' %}
    <div class="card"><h2>{{'Sửa lịch tự động' if edit_job.id else 'Thêm lịch tự động'}}</h2>
      <form method="post" action="{{url_for('database_schedule_save')}}" id="scheduleForm"><input type="hidden" name="job_id" value="{{edit_job.id}}"><div class="row">
        <label>Database<select name="database" {{'disabled' if edit_job.id else ''}}><option value="mysql" {{'selected' if edit_job.database=='mysql' else ''}}>MySQL</option><option value="mssql" {{'selected' if edit_job.database=='mssql' else ''}}>MSSQL</option></select>{% if edit_job.id %}<input type="hidden" name="database" value="{{edit_job.database}}">{% endif %}</label>
        <label>Kiểu lịch<select name="schedule_type" id="scheduleType"><option value="hourly" {{'selected' if edit_job.schedule.type=='hourly' else ''}}>Hàng giờ</option><option value="daily" {{'selected' if edit_job.schedule.type=='daily' else ''}}>Hàng ngày</option><option value="weekly" {{'selected' if edit_job.schedule.type=='weekly' else ''}}>Hàng tuần</option></select></label>
        <label id="hourEvery">Mỗi bao nhiêu giờ<input type="number" name="every_hours" min="1" max="23" value="{{edit_job.schedule.get('every_hours',2)}}"></label>
        <label id="hourMinute">Vào phút thứ<input type="number" name="minute" min="0" max="59" value="{{edit_job.schedule.get('minute',0)}}"></label>
        <label id="scheduleTime">Giờ server<input type="time" name="time" value="{{edit_job.schedule.get('time','03:00')}}"></label>
      </div><div id="weekDays" class="tools">{% for value,label in day_options %}<label style="display:flex;align-items:center;gap:5px;margin:0"><input type="checkbox" name="days" value="{{value}}" style="width:17px" {{'checked' if value in edit_job.schedule.get('days',[]) else ''}}> {{label}}</label>{% endfor %}</div>
      <label class="toggle-line"><input type="checkbox" name="enabled" {{'checked' if edit_job.enabled else ''}}> Bật lịch này</label><button>{{'Cập nhật' if edit_job.id else 'Tạo lịch'}}</button>{% if edit_job.id %} <a class="btn mut" href="?tab=schedule">Hủy sửa</a>{% endif %}</form>
    </div>
    <div class="card scroll"><table><thead><tr><th>Database</th><th>Tần suất</th><th>Lần kế tiếp</th><th>Trạng thái</th><th>Thao tác</th></tr></thead><tbody>{% for job in schedules %}<tr>
      <td>{{job.label}}</td><td>{{schedule_summary(job.schedule)}}</td><td>{{job.next_run.strftime('%d/%m/%Y %H:%M') if job.next_run else 'Không có'}}</td><td><span class="pill {{'on' if job.enabled else 'off'}}">{{'ĐANG BẬT' if job.enabled else 'ĐANG TẮT'}}</span></td>
      <td><div style="display:flex;gap:5px"><form method="post" action="{{url_for('database_schedule_run', job_id=job.id)}}"><button class="ok" title="Chạy ngay">▶</button></form><a class="btn mut" href="?tab=schedule&edit_job={{job.id}}">✎</a><form method="post" action="{{url_for('database_schedule_toggle', job_id=job.id)}}"><button class="mut">{{'Tắt' if job.enabled else 'Bật'}}</button></form><form method="post" action="{{url_for('database_schedule_delete', job_id=job.id)}}" data-confirm="Xóa lịch backup này?"><button class="err">🗑</button></form></div></td>
    </tr>{% else %}<tr><td colspan="5" class="muted">Chưa có lịch tự động.</td></tr>{% endfor %}</tbody></table></div>
    <script>(function(){const type=document.getElementById('scheduleType'),hourEvery=document.getElementById('hourEvery'),hourMinute=document.getElementById('hourMinute'),scheduleTime=document.getElementById('scheduleTime'),weekDays=document.getElementById('weekDays');function update(){const value=type.value;hourEvery.style.display=hourMinute.style.display=value==='hourly'?'block':'none';scheduleTime.style.display=value==='hourly'?'none':'block';weekDays.style.display=value==='weekly'?'flex':'none'}type.addEventListener('change',update);update()})()</script>
    {% elif tab == 'history' %}
    <div class="card scroll"><table><thead><tr><th>Lượt chạy</th><th>Database</th><th>Nguồn</th><th>Thời gian</th><th>Trạng thái</th><th>File / Lỗi</th><th>Thao tác</th></tr></thead><tbody>{% for run in runs %}<tr>
      <td>{{run.id}}</td><td>{{run.database|upper}}</td><td>{{'Theo lịch' if run.trigger=='schedule' else 'Thủ công'}}</td><td>{{run.scheduled_at|replace('T',' ')}}</td><td><span class="pill {{'on' if run.status=='succeeded' else 'off'}}">{{run.status}}</span></td><td>{{run.file or run.error or '—'}}</td><td>{% if run.status=='failed' %}<form method="post" action="{{url_for('database_schedule_run', job_id=run.job_id)}}"><button>Chạy lại</button></form>{% endif %}</td>
    </tr>{% else %}<tr><td colspan="7" class="muted">Chưa có lịch sử backup tự động.</td></tr>{% endfor %}</tbody></table></div>
    {% else %}
    <div class="card" style="max-width:720px"><h2>Thời gian giữ backup tự động</h2><form method="post" action="{{url_for('database_backup_settings')}}"><label>MySQL — số ngày<input type="number" name="mysql_days" min="1" max="3650" value="{{state.retention.mysql}}"></label><label>MSSQL — số ngày<input type="number" name="mssql_days" min="1" max="3650" value="{{state.retention.mssql}}"></label><button style="margin-top:14px">Lưu cài đặt</button></form><p class="muted">Chỉ tự dọn file do lịch tự động tạo; file tải lên và backup thủ công không bị xóa.</p></div>
    {% endif %}
    """
    latest = {}
    for kind in ("mysql", "mssql"):
        matches = [row for row in all_artifacts if row["kind"] == kind]
        latest[kind] = max(matches, key=lambda row: row["time"]) if matches else None
    next_runs = [job["next_run"] for job in schedules if job.get("next_run")]
    backup_summary = {
        "mysql": {"ok": port_listening(3306), "latest": ("Mới nhất " + latest["mysql"]["time"].strftime("%d/%m %H:%M")) if latest["mysql"] else "Chưa có backup"},
        "mssql": {"ok": port_listening(1433), "latest": ("Mới nhất " + latest["mssql"]["time"].strftime("%d/%m %H:%M")) if latest["mssql"] else "Chưa có backup"},
        "next_schedule": min(next_runs).strftime("%d/%m %H:%M") if next_runs else "Chưa đặt lịch",
        "total_size": sum(row["size"] for row in all_artifacts),
        "total_files": len(all_artifacts),
    }
    body = BACKUP_PAGE_V116
    return page(body, page="database", tab=tab, artifacts=artifacts, kind_filter=kind_filter,
                query=query, state=state, schedules=schedules, edit_job=edit_job, runs=runs,
                day_options=[(0,"Thứ 2"),(1,"Thứ 3"),(2,"Thứ 4"),(3,"Thứ 5"),(4,"Thứ 6"),(5,"Thứ 7"),(6,"Chủ Nhật")],
                schedule_summary=_schedule_summary, backup_summary=backup_summary,
                open_backup_settings=open_backup_settings)

@app.route("/database/artifact/<artifact_id>/download")
def database_artifact_download(artifact_id):
    try:
        row = _backup_artifact(artifact_id)
        return send_file(row["path"], as_attachment=True, download_name=row["filename"], conditional=True)
    except Exception as exc:
        flash("err", "Không tải được file backup: " + str(exc))
        return redirect(url_for("database_tools", tab="files"))

@app.route("/database/artifact/<artifact_id>/restore", methods=["POST"])
def database_artifact_restore(artifact_id):
    try:
        row = _backup_artifact(artifact_id)
        if request.form.get("confirm_filename") != row["filename"]:
            raise ValueError("Tên file xác nhận không đúng")
        blocked = _db_action_blocked()
        if blocked: raise RuntimeError(blocked)
        safety = _create_backup_artifact(row["kind"], source="safety", note="Tự tạo trước khi restore " + row["filename"])
        _restore_backup_artifact(row)
        flash("ok", f"Đã khôi phục {row['label']} từ {row['filename']}. Bản an toàn: {os.path.basename(safety)}.")
    except Exception as exc:
        flash("err", "Restore thất bại: " + str(exc))
    return redirect(url_for("database_tools", tab="files"))

@app.route("/database/artifact/<artifact_id>/note", methods=["POST"])
def database_artifact_note(artifact_id):
    try:
        row = _backup_artifact(artifact_id); note = (request.form.get("note") or "").strip()[:500]
        _record_backup_metadata(row["relative"], note=note)
        flash("ok", "Đã cập nhật ghi chú.")
    except Exception as exc:
        flash("err", "Không cập nhật được ghi chú: " + str(exc))
    return redirect(url_for("database_tools", tab="files"))

@app.route("/database/artifact/<artifact_id>/delete", methods=["POST"])
def database_artifact_delete(artifact_id):
    try:
        row = _backup_artifact(artifact_id)
        if row["is_latest"]:
            raise ValueError("Không thể xóa backup mới nhất của database này")
        os.unlink(row["path"])
        def mutate(state): state["metadata"].pop(row["relative"], None)
        _backup_state(mutate)
        flash("ok", "Đã xóa file backup " + row["filename"] + ".")
    except Exception as exc:
        flash("err", "Không xóa được file backup: " + str(exc))
    return redirect(url_for("database_tools", tab="files"))

@app.route("/database/upload", methods=["POST"])
def database_backup_upload():
    kind = request.form.get("kind")
    uploaded = request.files.get("backup_file")
    try:
        if kind not in ("mysql", "mssql") or not uploaded or not uploaded.filename:
            raise ValueError("Thiếu loại database hoặc file")
        lower = uploaded.filename.lower()
        if kind == "mysql" and not (lower.endswith(".sql") or lower.endswith(".sql.gz")):
            raise ValueError("MySQL chỉ nhận .sql hoặc .sql.gz")
        if kind == "mssql" and not lower.endswith(".bak"):
            raise ValueError("MSSQL chỉ nhận .bak")
        suffix = ".sql.gz" if lower.endswith(".sql.gz") else (".sql" if kind == "mysql" else ".bak")
        folder = os.path.join(BACKUP_FILES_ROOT, kind); os.makedirs(folder, mode=0o777, exist_ok=True)
        filename = f"uploaded-{datetime.now():%Y%m%d-%H%M%S-%f}{suffix}"
        path = os.path.join(folder, filename); uploaded.save(path)
        if os.path.getsize(path) == 0: raise ValueError("File upload rỗng")
        relative = os.path.relpath(path, BACKUP_DIR)
        _record_backup_metadata(relative, source="uploaded", note=(request.form.get("note") or "").strip()[:500],
                                original_name=os.path.basename(uploaded.filename))
        flash("ok", "Đã tải file vào kho. Upload chưa tự Restore dữ liệu.")
    except Exception as exc:
        flash("err", "Upload backup thất bại: " + str(exc))
    return redirect(url_for("database_tools", tab="files"))

@app.route("/database/schedule/save", methods=["POST"])
def database_schedule_save():
    try:
        job_id = (request.form.get("job_id") or "").strip()
        database = request.form.get("database")
        schedule_type = request.form.get("schedule_type")
        if database not in ("mysql", "mssql") or schedule_type not in ("hourly", "daily", "weekly"):
            raise ValueError("Cấu hình lịch không hợp lệ")
        schedule = {"type": schedule_type}
        if schedule_type == "hourly":
            every = int(request.form.get("every_hours", 1)); minute = int(request.form.get("minute", 0))
            if not 1 <= every <= 23 or not 0 <= minute <= 59: raise ValueError("Giờ/phút không hợp lệ")
            schedule.update(every_hours=every, minute=minute)
        else:
            clock = request.form.get("time", "")
            if not re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", clock): raise ValueError("Giờ chạy không hợp lệ")
            schedule["time"] = clock
            if schedule_type == "weekly":
                days = sorted({int(value) for value in request.form.getlist("days")})
                if not days or any(value < 0 or value > 6 for value in days): raise ValueError("Cần chọn ngày trong tuần")
                schedule["days"] = days
        def mutate(state):
            existing = next((item for item in state["schedules"] if item.get("id") == job_id), None) if job_id else None
            if job_id and not existing: raise ValueError("Không tìm thấy lịch cần sửa")
            if existing:
                existing.update(database=database, schedule=schedule, enabled=request.form.get("enabled") == "on")
            else:
                state["schedules"].append({"id": "job_" + uuid.uuid4().hex[:16], "database": database,
                                           "schedule": schedule, "enabled": request.form.get("enabled") == "on",
                                           "created_at": datetime.now().astimezone().isoformat(timespec="seconds"), "last_run": ""})
        _backup_state(mutate)
        flash("ok", "Đã lưu lịch backup tự động.")
    except Exception as exc:
        flash("err", "Không lưu được lịch: " + str(exc))
    return redirect(url_for("database_tools", tab="schedule"))

@app.route("/database/schedule/<job_id>/run", methods=["POST"])
def database_schedule_run(job_id):
    try:
        state = _backup_state(); job = next((item for item in state["schedules"] if item.get("id") == job_id), None)
        if not job: raise ValueError("Không tìm thấy lịch")
        port = 3306 if job["database"] == "mysql" else 1433
        if not port_listening(port): raise RuntimeError(job["database"].upper() + " chưa sẵn sàng")
        _queue_backup_job(job_id, "manual")
        flash("ok", "Đã đưa lượt backup vào hàng đợi.")
    except Exception as exc:
        flash("err", "Không chạy được lịch: " + str(exc))
    return redirect(url_for("database_tools", tab="history"))

@app.route("/database/schedule/<job_id>/toggle", methods=["POST"])
def database_schedule_toggle(job_id):
    try:
        def mutate(state):
            job = next((item for item in state["schedules"] if item.get("id") == job_id), None)
            if not job: raise ValueError("Không tìm thấy lịch")
            job["enabled"] = not job.get("enabled", True)
        _backup_state(mutate); flash("ok", "Đã đổi trạng thái lịch.")
    except Exception as exc: flash("err", str(exc))
    return redirect(url_for("database_tools", tab="schedule"))

@app.route("/database/schedule/<job_id>/delete", methods=["POST"])
def database_schedule_delete(job_id):
    def mutate(state): state["schedules"] = [job for job in state["schedules"] if job.get("id") != job_id]
    _backup_state(mutate); flash("ok", "Đã xóa lịch backup.")
    return redirect(url_for("database_tools", tab="schedule"))

@app.route("/database/settings", methods=["POST"])
def database_backup_settings():
    try:
        mysql_days = int(request.form.get("mysql_days", 14)); mssql_days = int(request.form.get("mssql_days", 14))
        if not 1 <= mysql_days <= 3650 or not 1 <= mssql_days <= 3650: raise ValueError("Số ngày phải từ 1 đến 3650")
        def mutate(state): state["retention"].update(mysql=mysql_days, mssql=mssql_days)
        _backup_state(mutate); flash("ok", "Đã lưu thời gian giữ backup tự động.")
    except Exception as exc: flash("err", "Không lưu được cài đặt: " + str(exc))
    return redirect(url_for("database_tools", tab="files"))

@app.route("/database/download/<set_name>/<filename>")
def database_backup_download(set_name, filename):
    try:
        mimetype = DATABASE_BACKUP_FILES.get(filename)
        if not mimetype:
            raise ValueError("Tên file backup không hợp lệ")
        folder = _selected_backup_dir(set_name)
        path = os.path.join(folder, filename)
    except (ValueError, FileNotFoundError) as e:
        flash("err", f"Không tải được file backup: {e}")
        return redirect(url_for("database_tools"))

    download_name = f"{set_name}_{filename}"
    return send_file(path, as_attachment=True, download_name=download_name,
                     mimetype=mimetype, conditional=True)

@app.route("/database/backup", methods=["POST"])
def database_backup():
    kind = request.form.get("kind", "all")
    try:
        if kind not in ("all", "mysql", "mssql"):
            raise ValueError("Loại database không hợp lệ")
        selected = ("mysql", "mssql") if kind == "all" else (kind,)
        paths = []
        for current in selected:
            port = 3306 if current == "mysql" else 1433
            if not port_listening(port):
                raise RuntimeError(current.upper() + " chưa sẵn sàng")
            paths.append(_create_backup_artifact(current, source="manual"))
        flash("ok", "Backup thành công: " + ", ".join(os.path.basename(path) for path in paths) + ".")
    except Exception as e:
        flash("err", f"Backup thất bại: {e}")
    return redirect(url_for("database_tools", tab="files"))

@app.route("/database/restore/<set_name>", methods=["POST"])
def database_restore(set_name):
    if (request.form.get("confirm") or "").strip().upper() != "RESTORE":
        flash("err", "Hãy nhập RESTORE để xác nhận (không phân biệt hoa/thường).")
        return redirect(url_for("database_tools"))
    blocked = _db_action_blocked()
    if blocked:
        flash("err", blocked); return redirect(url_for("database_tools"))
    try:
        safety = _create_backup_set(prefix="before_restore")
        _restore_backup_set(set_name)
        flash("ok", f"Restore thành công từ {set_name}. Bản an toàn trước restore: {safety}.")
    except Exception as e:
        flash("err", f"Restore thất bại: {e}")
    return redirect(url_for("database_tools"))

@app.route("/database/delete-backup/<set_name>", methods=["POST"])
def database_delete_backup(set_name):
    confirm_delete = (request.form.get("confirm_delete") or "").strip().upper()
    if confirm_delete not in ("XOA", "XÓA"):
        flash("err", "Hãy nhập XOA hoặc XÓA để xác nhận xóa bộ backup.")
        return redirect(url_for("database_tools"))
    try:
        folder = _selected_backup_dir(set_name)
        shutil.rmtree(folder)
        flash("ok", f"Đã xóa bộ backup: {set_name}.")
    except Exception as e:
        flash("err", f"Không xóa được bộ backup {set_name}: {e}")
    return redirect(url_for("database_tools"))

@app.route("/database/restore-upload", methods=["POST"])
def database_restore_upload():
    if (request.form.get("confirm") or "").strip().upper() != "RESTORE":
        flash("err", "Hãy nhập RESTORE để xác nhận (không phân biệt hoa/thường).")
        return redirect(url_for("database_tools"))
    blocked = _db_action_blocked()
    if blocked:
        flash("err", blocked); return redirect(url_for("database_tools"))

    mssql_file = request.files.get("mssql_backup")
    mysql_file = request.files.get("mysql_backup")
    if not mssql_file or not mysql_file or not mssql_file.filename or not mysql_file.filename:
        flash("err", "Cần chọn đủ account_tong.bak và server1.sql từ máy Windows.")
        return redirect(url_for("database_tools"))
    if not mssql_file.filename.lower().endswith(".bak") or not mysql_file.filename.lower().endswith(".sql"):
        flash("err", "Sai định dạng: MSSQL phải là .bak và MySQL phải là .sql.")
        return redirect(url_for("database_tools"))

    os.makedirs(BACKUP_DIR, exist_ok=True)
    set_name = f"jx_backup_{datetime.now():%Y%m%d_%H%M%S}"
    set_dir = os.path.join(BACKUP_DIR, set_name)
    try:
        os.makedirs(set_dir, mode=0o777)
        os.chmod(set_dir, 0o777)
        bak_path = os.path.join(set_dir, "account_tong.bak")
        sql_path = os.path.join(set_dir, "server1.sql")
        mssql_file.save(bak_path)
        mysql_file.save(sql_path)
        os.chmod(bak_path, 0o666)
        os.chmod(sql_path, 0o666)
        if not os.path.getsize(bak_path) or not os.path.getsize(sql_path):
            raise ValueError("File upload rỗng")

        safety = _create_backup_set(prefix="before_restore")
        _restore_backup_set(set_name)
        flash("ok", f"Upload và restore thành công từ máy Windows. Bộ đã tải: {set_name}. Bản an toàn: {safety}.")
    except Exception as e:
        flash("err", f"Upload/restore thất bại: {e}. Bộ file đã tải được giữ lại để kiểm tra.")
    return redirect(url_for("database_tools"))

@app.route("/database/delete-server1", methods=["POST"])
def database_delete_server1():
    if request.form.get("confirm") != "DELETE SERVER1":
        flash("err", "Phải nhập chính xác DELETE SERVER1 để xác nhận.")
        return redirect(url_for("database_tools"))
    blocked = _db_action_blocked()
    if blocked:
        flash("err", blocked); return redirect(url_for("database_tools"))
    try:
        safety = _create_backup_set(prefix="before_restore")
        c = mysql_conn(); cur = c.cursor()
        cur.execute("SET FOREIGN_KEY_CHECKS=0")
        cur.execute("SHOW FULL TABLES WHERE Table_type='BASE TABLE'")
        tables = [row[0] for row in cur.fetchall()]
        for table in tables:
            cur.execute("DROP TABLE `" + table.replace("`", "``") + "`")
        cur.execute("SET FOREIGN_KEY_CHECKS=1"); c.close()
        flash("ok", f"Đã xóa {len(tables)} bảng trong server1. Bản an toàn: {safety}.")
    except Exception as e:
        flash("err", f"Xóa database thất bại: {e}")
    return redirect(url_for("database_tools"))

# ---------------- Xem log CMD (tự động realtime) ----------------
_TCVN_HIGH_CHARS = (
    "ÀẢÃÁẠẶẬÈẺẼÉẸỆÌỈĨÍỊÒỎÕÓỌỘỜỞỠỚỢÙỦŨ "
    "ĂÂÊÔƠƯĐăâêôơưđẶ̀̀̉̃́àảãáạẲằẳẵắẴẮẦẨẪẤỀặầẩẫấậèỂẻẽéẹềểễếệìỉỄẾỒĩíịòỔỏõóọồổỗốộờởỡớợùỖủũúụừửữứựỳỷỹýỵỐ"
)
_TCVN_CONTROL_CHARS = {
    0x01: "Ú", 0x02: "Ụ", 0x04: "Ừ", 0x05: "Ử", 0x06: "Ữ",
    0x11: "Ứ", 0x12: "Ự", 0x13: "Ỳ", 0x14: "Ỷ", 0x15: "Ỹ",
    0x16: "Ý", 0x17: "Ỵ",
}
_EMBEDDED_LOG_TIMESTAMP = re.compile(
    r"^\s*\[\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}:\d{2}"
    r"(?:[.,]\d+)?(?:Z|[+-]\d{2}:?\d{2})?\]\s*"
)

def _decode_tcvn5712(raw):
    chars = []
    for value in raw:
        if value >= 0x80:
            chars.append(_TCVN_HIGH_CHARS[value - 0x80])
        elif value in _TCVN_CONTROL_CHARS:
            chars.append(_TCVN_CONTROL_CHARS[value])
        else:
            chars.append(chr(value))
    return unicodedata.normalize("NFC", "".join(chars))

def _decode_mixed_log(raw):
    if not raw:
        return "(chưa có log)"
    # Log JX cũ chủ yếu là UTF-8 hoặc TCVN-5712; một số bản dùng GBK/Big5.
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        pass
    tcvn = _decode_tcvn5712(raw)
    if any("\u00c0" <= char <= "\u1ef9" for char in tcvn):
        return tcvn
    for encoding in ("gbk", "big5"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")

def _strip_embedded_log_timestamp(message):
    return _EMBEDDED_LOG_TIMESTAMP.sub("", str(message), count=1)

LOG_UNIT_LABELS = {
    "jxpaysys": "PaySys",
    "jxrelaypay": "RelayPay",
    "jxgoddess": "Goddess",
    "jxbishop": "Bishop",
    "jxs3relay": "S3Relay",
    "jxgame": "GameServer",
}

def _journal_log_entries(units, tail, since=None):
    # Đọc cả journal mặc định (phiên cũ) và namespace JXNative
    # giới hạn trong RAM (phiên mới).
    command = ["journalctl", "--namespace=*", "--merge"]
    for unit in units:
        command += ["-u", unit]
    if since is not None:
        command += ["--since", "@%.6f" % float(since)]
    command += ["-n", str(tail), "--no-pager", "-o", "json"]
    result = subprocess.run(command, capture_output=True, timeout=10)
    entries = []
    for raw_line in (result.stdout or b"").splitlines():
        try:
            row = json.loads(raw_line.decode("utf-8", errors="replace"))
            unit = str(row.get("_SYSTEMD_UNIT") or "").removesuffix(".service")
            label = LOG_UNIT_LABELS.get(unit, unit or "System")
            message = row.get("MESSAGE", "")
            if isinstance(message, list):
                message = _decode_mixed_log(bytes(value for value in message if isinstance(value, int)))
            timestamp = int(row.get("__REALTIME_TIMESTAMP", 0) or 0) / 1_000_000
            stamp = datetime.fromtimestamp(timestamp).astimezone().isoformat(timespec="microseconds") if timestamp else ""
            for line in str(message).splitlines() or [""]:
                entries.append((timestamp, label, stamp, _strip_embedded_log_timestamp(line)))
        except (ValueError, TypeError, OSError):
            continue
    if result.returncode != 0 and result.stderr:
        entries.append((time.time(), "System", datetime.now().astimezone().isoformat(timespec="seconds"),
                        _decode_mixed_log(result.stderr).strip()))
    return entries

def _docker_log_entries(kind, tail, since=None):
    container = MSSQL_CONTAINER if kind == "mssql" else MYSQL_CONTAINER
    label = "MSSQL" if kind == "mssql" else "MySQL"
    command = ["docker", "logs", "--timestamps", "--tail", str(tail)]
    if since is not None:
        command += ["--since", "%.6f" % float(since)]
    command.append(container)
    result = subprocess.run(command,
                            capture_output=True, timeout=10)
    entries = []
    raw = (result.stdout or b"") + (result.stderr or b"")
    for line in _decode_mixed_log(raw).splitlines():
        first, separator, content = line.partition(" ")
        stamp = first if separator and re.match(r"^\d{4}-\d{2}-\d{2}T", first) else ""
        if not stamp:
            content = line
        try:
            sort_time = datetime.fromisoformat(stamp.replace("Z", "+00:00")).timestamp() if stamp else time.time()
        except ValueError:
            sort_time = time.time()
        entries.append((sort_time, label, stamp, _strip_embedded_log_timestamp(content)))
    return entries

def _read_log(source, tail=300, timestamps=True, history=False, requested_since=None):
    try:
        tail = 50000 if str(tail).lower() == "all" else max(10, min(int(tail), 50000))
    except (TypeError, ValueError):
        tail = 300
    try:
        session = _load_log_session()
        requested_since = float(requested_since) if requested_since not in (None, "") else None
        if history:
            since = requested_since
        elif source == "session":
            since = max(session["started_at"], requested_since or 0)
        else:
            since = max(session["markers"].get(source, session["started_at"]), requested_since or 0)
        if source in ("mssql", "mysql"):
            entries = _docker_log_entries(source, tail, since)
        elif source in ("all", "session"):
            units = [unit for unit, _label in COMPONENTS] if source == "all" else [unit for unit in session["scope"] if unit not in ("mssql", "mysql")]
            entries = _journal_log_entries(units, tail, since) if units else []
            database_sources = ("mssql", "mysql") if source == "all" else [item for item in session["scope"] if item in ("mssql", "mysql")]
            for database_source in database_sources:
                entries += _docker_log_entries(database_source, tail, since)
            entries.sort(key=lambda item: item[0])
            entries = entries[-tail:]
        else:
            entries = _journal_log_entries([source], tail, since)
        lines = []
        for _sort_time, label, stamp, content in entries:
            middle = (stamp + " ") if timestamps and stamp else ""
            lines.append(f"{label} | {middle}{content}")
        return "\n".join(lines) if lines else "(chưa có log)"
    except Exception as exc:
        return f"(không đọc được log: {exc})"


def _sse_message(event, payload):
    return "event: " + event + "\ndata: " + json.dumps(payload, ensure_ascii=False) + "\n\n"


def _console_marker(source):
    state = _load_log_session()
    return float(state["markers"].get(source, state["started_at"])), state


def _console_follow_command(source):
    if source in ("mssql", "mysql"):
        container = MSSQL_CONTAINER if source == "mssql" else MYSQL_CONTAINER
        return ["docker", "logs", "--follow", "--tail", "0", "--timestamps", container]
    return ["journalctl", "--namespace=*", "--merge", "--follow", "--lines", "0",
            "--no-pager", "--output=json", "-u", source]


def _console_follow_lines(source, raw):
    label = dict(LOG_SOURCES).get(source, source)
    if source in ("mssql", "mysql"):
        line = _decode_mixed_log(raw).rstrip("\r\n")
        first, separator, content = line.partition(" ")
        stamp = first if separator and re.match(r"^\d{4}-\d{2}-\d{2}T", first) else ""
        if not stamp:
            content = line
        return [f"{label} | {(stamp + ' ') if stamp else ''}{content}"] if line else []
    try:
        row = json.loads(raw.decode("utf-8", errors="replace"))
        message = row.get("MESSAGE", "")
        if isinstance(message, list):
            message = _decode_mixed_log(bytes(value for value in message if isinstance(value, int)))
        timestamp = int(row.get("__REALTIME_TIMESTAMP", 0) or 0) / 1_000_000
        stamp = datetime.fromtimestamp(timestamp).astimezone().isoformat(timespec="microseconds") if timestamp else ""
        return [f"{label} | {(stamp + ' ') if stamp else ''}{_strip_embedded_log_timestamp(line)}" for line in str(message).splitlines() or [""]]
    except (TypeError, ValueError, OSError):
        text = _decode_mixed_log(raw).rstrip("\r\n")
        return [f"{label} | {text}"] if text else []


def _console_event_stream(source, initial_tail=None):
    marker, state = _console_marker(source)
    default_tail = 300
    try:
        initial_tail = default_tail if initial_tail in (None, "", "default") else int(initial_tail)
    except (TypeError, ValueError):
        initial_tail = default_tail
    initial_tail = max(10, min(initial_tail, 3000))
    initial = _read_log(source, initial_tail, timestamps=True)
    yield _sse_message("snapshot", {
        "text": "" if initial == "(chưa có log)" else initial,
        "marker": marker,
        "session": _log_session_view(state),
    })
    while True:
        process = None
        try:
            process = subprocess.Popen(
                _console_follow_command(source), stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT, bufsize=0, close_fds=True,
            )
            while True:
                next_marker, next_state = _console_marker(source)
                if next_marker != marker:
                    marker = next_marker
                    yield _sse_message("reset", {"marker": marker, "session": _log_session_view(next_state)})
                if process.poll() is not None:
                    break
                ready, _write, _errors = select.select([process.stdout], [], [], 1.0)
                if not ready:
                    yield ": keep-alive\n\n"
                    continue
                raw = process.stdout.readline()
                if not raw:
                    break
                for line in _console_follow_lines(source, raw):
                    yield _sse_message("log", {"line": line})
        except (GeneratorExit, BrokenPipeError, ConnectionError):
            return
        except (OSError, ValueError) as exc:
            yield _sse_message("status", {"state": "retry", "message": str(exc)[:240]})
        finally:
            if process is not None and process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=1)
                except subprocess.TimeoutExpired:
                    process.kill()
        time.sleep(1)


@app.route("/console")
def console_page():
    allowed_sources = [key for key, _label in LOG_SOURCES if key != "session"]
    selected = request.args.get("source", "jxgame")
    if selected not in allowed_sources:
        selected = "jxgame"
    view = request.args.get("view", "console")
    if view not in ("console", "activity"):
        view = "console"
    activity_tab = request.args.get("activity_tab", "admin")
    if activity_tab not in ("admin", "operation"):
        activity_tab = "admin"
    body = r"""
    <div class="console-heading"><div><h1 class="page-heading">Console & Nhật ký</h1><p>Theo dõi trực tiếp từng thành phần; log đầy đủ vẫn nằm trong Server & Dữ liệu.</p></div>{% if view == 'console' %}<span class="console-live pill on" id="consoleState">● ĐANG KẾT NỐI</span>{% endif %}</div>
    <nav class="console-view-tabs"><a class="{{'active' if view=='console' else ''}}" href="{{url_for('console_page', source=selected)}}">Console máy chủ</a><a class="{{'active' if view=='activity' else ''}}" href="{{url_for('console_page', view='activity')}}">Nhật ký hoạt động</a></nav>
    {% if view == 'activity' %}
      <nav class="activity-subtabs" aria-label="Loại nhật ký"><a class="{{'active' if activity_tab=='admin' else ''}}" href="{{url_for('console_page', view='activity', activity_tab='admin')}}">Thao tác quản trị</a><a class="{{'active' if activity_tab=='operation' else ''}}" href="{{url_for('console_page', view='activity', activity_tab='operation')}}">Log vận hành JXNative</a></nav>
      {% if activity_tab == 'admin' %}
      <section class="card activity-card"><div class="section-head"><div><h2>Nhật ký thao tác quản trị</h2><span class="muted">Ghi thao tác Start All, Stop All, Reload và Bật/Tắt từng thành phần; không chứa output game.</span></div><a class="btn mut" href="{{url_for('console_page', view='activity')}}">Làm mới</a></div>
      <div class="activity-table-wrap"><table class="activity-table"><thead><tr><th>Thời gian</th><th>Thao tác</th><th>Chi tiết</th><th>Người dùng</th><th>IP</th></tr></thead><tbody>{% for row in activity_rows %}<tr><td>{{row.time}}</td><td><span class="activity-result {{row.result}}">{{row.action}}</span></td><td>{{row.detail or '—'}}</td><td>{{row.user}}</td><td><code>{{row.ip or '—'}}</code></td></tr>{% else %}<tr><td colspan="5" class="muted">Chưa có thao tác mới. Nhật ký sẽ bắt đầu ghi từ phiên bản này.</td></tr>{% endfor %}</tbody></table></div></section>
      {% else %}
      <section class="card operation-log-card"><div class="section-head"><div><h2>Log vận hành JXNative</h2><span class="muted">Log Start All, Reload và Web quản trị; chỉ đọc khi bấm Tải log.</span></div></div><div class="operation-log-tools"><label>Nguồn<select id="operationLogSource"><option value="all">Tất cả vận hành</option><option value="start">Start All</option><option value="reload">Reload</option><option value="web">Web quản trị</option></select></label><label>Số dòng<select id="operationLogTail"><option value="1000">1.000</option><option value="3000">3.000</option><option value="all">Tất cả</option></select></label><button type="button" id="operationLogLoad">Tải log</button><button type="button" class="mut" id="operationLogBottom">↓ Cuối log</button></div><p class="muted">Tất cả được giới hạn tối đa 50.000 dòng.</p><pre class="operation-log-view" id="operationLogView">Chưa tải log.</pre></section>
      <script>(function(){const source=document.getElementById('operationLogSource'),tail=document.getElementById('operationLogTail'),load=document.getElementById('operationLogLoad'),box=document.getElementById('operationLogView');async function read(){load.disabled=true;box.textContent='Đang tải log...';try{const query=new URLSearchParams({source:source.value,tail:tail.value}),response=await fetch({{url_for('jxnative_operation_log_raw')|tojson}}+'?'+query,{cache:'no-store'});if(!response.ok)throw new Error('HTTP '+response.status);box.textContent=await response.text();box.scrollTop=box.scrollHeight}catch(error){box.textContent='Không đọc được log: '+error.message}finally{load.disabled=false}}function reset(){box.textContent='Chưa tải log. Bấm “Tải log” khi cần xem.'}load.addEventListener('click',read);source.addEventListener('change',reset);tail.addEventListener('change',reset);document.getElementById('operationLogBottom').addEventListener('click',()=>box.scrollTop=box.scrollHeight)})();</script>
      {% endif %}
    {% else %}
      <section class="card console-card" id="consoleCard" style="--console-color:{{log_colors[selected]}}">
        <div class="console-source-groups"><div><small>GAME SERVER</small><div class="console-sources">{% for key,label in console_sources if key not in ('mssql','mysql') %}<button type="button" class="console-source {{'active' if key==selected else ''}}" data-source="{{key}}" style="--source-color:{{log_colors[key]}}">{{label}}</button>{% endfor %}</div></div><div><small>DATABASE</small><div class="console-sources">{% for key,label in console_sources if key in ('mssql','mysql') %}<button type="button" class="console-source {{'active' if key==selected else ''}}" data-source="{{key}}" style="--source-color:{{log_colors[key]}}">{{label}}</button>{% endfor %}</div></div></div>
        <div class="console-meta"><b id="consoleSession">Phiên hiện tại</b><span id="consoleSourceLabel">{{dict(console_sources)[selected]}}</span><span class="muted">Chỉ tải và theo dõi tab đang chọn</span></div>
        <div class="console-tools"><label>Số dòng <select id="consoleTail"><option value="300">300</option><option value="1000">1.000</option><option value="3000">3.000</option></select></label><label><input type="checkbox" id="consoleTimestamps"> Hiện thời gian</label><label><input type="checkbox" id="consoleAutoscroll" checked> Tự cuộn</label><button type="button" class="mut" id="consoleBottom">↓ Cuối log</button><button type="button" class="mut" id="consoleFullscreen">⛶ Toàn màn hình</button></div>
        <div class="server-console" id="serverConsole" tabindex="0" aria-live="off"><div id="consoleText"></div></div>
      </section>
      <script>
      (function(){
        const card=document.getElementById('consoleCard'),box=document.getElementById('serverConsole'),node=document.getElementById('consoleText'),state=document.getElementById('consoleState'),sessionLabel=document.getElementById('consoleSession'),sourceLabel=document.getElementById('consoleSourceLabel'),tail=document.getElementById('consoleTail'),timestamps=document.getElementById('consoleTimestamps'),autoscroll=document.getElementById('consoleAutoscroll');
        const labels={{dict(console_sources)|tojson}},colors={{log_colors|tojson}},streamPattern={{url_for('logs_stream', unit='__SOURCE__')|tojson}};let source={{selected|tojson}},stream=null,buffer=[],pending=[],flushTimer=0,renderedDay='',renderedCount=0;const maxBuffer=3000,maxDom=3000;
        try{const saved=JSON.parse(localStorage.getItem('jxnative.console.v3')||'{}');if(typeof saved.timestamps==='boolean')timestamps.checked=saved.timestamps;if(typeof saved.autoscroll==='boolean')autoscroll.checked=saved.autoscroll;if(['300','1000','3000'].includes(saved.tail))tail.value=saved.tail}catch(e){}
        function save(){try{localStorage.setItem('jxnative.console.v3',JSON.stringify({timestamps:timestamps.checked,autoscroll:autoscroll.checked,tail:tail.value}))}catch(e){}}
        function stripAnsi(value){return String(value||'').replace(/[\u001b\u009b][[\]()#;?]*(?:(?:(?:[a-zA-Z\d]*(?:;[-a-zA-Z\d\/#&.:=?%@~_]+)*)?\u0007)|(?:(?:\d{1,4}(?:[;:]\d{0,4})*)?[\dA-PR-TZcf-nq-uy=><~]))/g,'').replace(/\r(?!\n)/g,'')}
        function severity(message){const value=message.toLowerCase();if(/error|failed|fatal|exception|segv|core-dump|exit-code|không mở được|thất bại/.test(value))return'error';if(/warn|warning|cảnh báo|timeout|retry/.test(value))return'warning';if(/success|successful|started|listening|kết nối ok|thành công/.test(value))return'success';if(/\bdebug\b|\bhex:|\bascii:/.test(value))return'debug';return''}
        function parsedLine(raw){const line=stripAnsi(raw),match=line.match(/^([^|]+)\s*\|\s*(?:(\d{4}-\d{2}-\d{2}T\S+)\s+)?(.*)$/);if(!match)return{source:'System',message:line,time:'',date:'',severity:severity(line)};let day='',clock='';if(match[2]){const date=new Date(match[2]);if(!Number.isNaN(date.getTime())){day=new Intl.DateTimeFormat('vi-VN',{day:'2-digit',month:'2-digit',year:'numeric'}).format(date);clock=new Intl.DateTimeFormat('vi-VN',{hour:'2-digit',minute:'2-digit',second:'2-digit',hour12:false}).format(date)}}return{source:match[1].trim(),message:match[3],time:clock,date:day,severity:severity(match[3])}}
        function dateDivider(day){const divider=document.createElement('div');divider.className='log-date-divider';divider.textContent=day;return divider}
        function lineNode(row){const line=document.createElement('div');line.className='log-line';const sourceNode=document.createElement('span');sourceNode.className='console-log-source';sourceNode.style.color=colors[source]||'#d6c09a';sourceNode.textContent=row.source;const separator=document.createElement('span');separator.className='log-separator';separator.textContent='|';line.append(sourceNode,separator);if(timestamps.checked&&row.time){const timeNode=document.createElement('span');timeNode.className='log-time';timeNode.textContent='['+row.time+']';line.appendChild(timeNode)}const message=document.createElement('span');message.className='log-message'+(row.severity?' is-'+row.severity:'');message.textContent=row.message;line.appendChild(message);return line}
        function appendRows(rows,resetDay){const fragment=document.createDocumentFragment();if(resetDay)renderedDay='';for(const raw of rows){const row=parsedLine(raw);if(timestamps.checked&&row.date&&row.date!==renderedDay){renderedDay=row.date;fragment.appendChild(dateDivider(renderedDay))}fragment.appendChild(lineNode(row))}node.appendChild(fragment)}
        function rebuild(){node.replaceChildren();const rows=buffer.slice(-maxDom);appendRows(rows,true);renderedCount=rows.length;if(autoscroll.checked)box.scrollTop=box.scrollHeight}
        function flush(){flushTimer=0;if(!pending.length)return;const rows=pending.splice(0);appendRows(rows,false);renderedCount+=rows.length;if(renderedCount>maxDom+250)rebuild();else if(autoscroll.checked)box.scrollTop=box.scrollHeight}
        function schedule(){if(flushTimer)return;flushTimer=setTimeout(flush,100)}
        function append(raw){const line=stripAnsi(raw);if(!line)return;buffer.push(line);if(buffer.length>maxBuffer)buffer.splice(0,buffer.length-maxBuffer);pending.push(line);if(pending.length>2000)pending.splice(0,pending.length-2000);schedule()}
        function setState(text,ok){state.textContent=text;state.className='console-live pill '+(ok?'on':'off')}
        function clearView(){buffer=[];pending=[];renderedDay='';renderedCount=0;node.textContent=''}
        function connect(){if(stream)stream.close();pending=[];setState('● ĐANG KẾT NỐI',true);const url=streamPattern.replace('__SOURCE__',encodeURIComponent(source))+'?tail='+encodeURIComponent(tail.value);stream=new EventSource(url);stream.addEventListener('snapshot',event=>{const data=JSON.parse(event.data);buffer=stripAnsi(data.text||'').split(/\r?\n/).filter(Boolean).slice(-maxBuffer);pending=[];sessionLabel.textContent=data.session?.label||'Phiên hiện tại';rebuild();setState('● REALTIME',true)});stream.addEventListener('reset',event=>{const data=JSON.parse(event.data);clearView();sessionLabel.textContent=data.session?.label||'Phiên mới'});stream.addEventListener('log',event=>append(JSON.parse(event.data).line));stream.addEventListener('status',()=>setState('● ĐANG THỬ LẠI',false));stream.onopen=()=>setState('● REALTIME',true);stream.onerror=()=>setState('● MẤT KẾT NỐI — TỰ THỬ LẠI',false)}
        function choose(next){source=next;clearView();card.style.setProperty('--console-color',colors[source]||'#cdd6e6');sourceLabel.textContent=labels[source]||source;document.querySelectorAll('.console-source').forEach(button=>button.classList.toggle('active',button.dataset.source===source));history.replaceState(null,'',{{url_for('console_page')|tojson}}+'?source='+encodeURIComponent(source));connect()}
        async function refreshStates(){try{const response=await fetch({{url_for('dashboard_status')|tojson}},{cache:'no-store',headers:{Accept:'application/json'}});if(!response.ok)return;const data=await response.json();document.querySelectorAll('.console-source').forEach(button=>{const key=button.dataset.source,running=key==='mssql'||key==='mysql'?data.databases?.[key]:data.components?.[key];button.classList.toggle('running',!!running);button.classList.toggle('stopped',!running)})}catch(e){}}
        document.querySelectorAll('.console-source').forEach(button=>button.addEventListener('click',()=>choose(button.dataset.source)));tail.addEventListener('change',()=>{save();clearView();connect()});timestamps.addEventListener('change',()=>{save();rebuild()});autoscroll.addEventListener('change',save);document.getElementById('consoleBottom').addEventListener('click',()=>box.scrollTop=box.scrollHeight);document.getElementById('consoleFullscreen').addEventListener('click',()=>box.requestFullscreen?.());window.addEventListener('beforeunload',()=>stream?.close());refreshStates();setInterval(refreshStates,5000);connect();
      })();
      </script>
    {% endif %}
    """
    return page(body, page="console", view=view, activity_tab=activity_tab, selected=selected,
                console_sources=LOG_SOURCES[1:], log_colors=LOG_COLORS,
                activity_rows=_read_activity() if view == "activity" and activity_tab == "admin" else [])


@app.route("/logs/jxnative/raw")
def jxnative_operation_log_raw():
    source = request.args.get("source", "all")
    if source not in ("all", "start", "reload", "web"):
        return "Nguồn log không hợp lệ", 400
    return Response(_read_jxnative_operation_log(source, request.args.get("tail", "1000")),
                    mimetype="text/plain; charset=utf-8")


@app.route("/logs/<unit>/stream")
def logs_stream(unit):
    allowed = {key for key, _label in LOG_SOURCES if key != "session"}
    if unit not in allowed:
        return "invalid", 404
    response = Response(stream_with_context(_console_event_stream(unit, request.args.get("tail"))), mimetype="text/event-stream")
    response.headers["Cache-Control"] = "no-cache, no-transform"
    response.headers["X-Accel-Buffering"] = "no"
    response.headers["Connection"] = "keep-alive"
    return response

@app.route("/logs/<unit>/raw")
def logs_raw(unit):
    if unit not in LOG_SOURCE_KEYS:
        return "invalid", 404
    read_started = time.time()
    response = Response(_read_log(unit, request.args.get("tail", 300), request.args.get("timestamps", "1") == "1",
                                  request.args.get("mode") == "history", request.args.get("since")),
                        mimetype="text/plain; charset=utf-8")
    response.headers["X-Log-Now"] = "%.6f" % read_started
    return response

@app.route("/logs/<unit>")
def logs(unit):
    if unit not in [u for u, _ in COMPONENTS]:
        flash("err", "Thành phần không hợp lệ."); return redirect(url_for("dashboard"))
    return redirect(url_for("console_page", source=unit))

# ---------------- Đăng ký tài khoản ----------------
@app.route("/register", methods=["GET","POST"])
def register():
    if request.method == "POST":
        acc = (request.form.get("account") or "").strip()
        p1 = request.form.get("password1") or ""; p2 = request.form.get("password2") or ""
        if not acc:
            flash("err","Cần nhập tên tài khoản."); return redirect(url_for("players", create=1))
        if len(acc) > 32:
            flash("err","Tên tài khoản tối đa 32 ký tự theo cấu trúc database của game."); return redirect(url_for("players", create=1))
        if not p1 or not p2:
            flash("err","Cần nhập mật khẩu cấp 1 và cấp 2."); return redirect(url_for("players", create=1))
        try:
            c = mssql_conn(); cur = c.cursor()
            cur.execute("SELECT COUNT(*) FROM Account_Info WHERE cAccName=%s",(acc,))
            if cur.fetchone()[0] > 0:
                c.close(); flash("err",f"Tài khoản '{acc}' đã tồn tại."); return redirect(url_for("players", create=1))
            cur.execute("INSERT INTO Account_Info (cAccName,cPassWord,cSecPassWord,"
                "nExtPoint,nExtPoint1,nExtPoint2,nExtPoint3,nExtPoint4,nExtPoint5,nExtPoint6,nExtPoint7,nFeeType,iOTPSessionLifeTime) "
                "VALUES (%s,%s,%s,1,0,0,0,0,0,0,0,0,0)",(acc,md5_upper(p1),md5_upper(p2)))
            cur.execute("IF NOT EXISTS(SELECT 1 FROM account_Habitus WHERE cAccName=%s) "
                "INSERT INTO account_Habitus (cAccName,iLeftSecond,dEndDate) VALUES (%s,360000,'2035-12-31')",(acc,acc))
            c.close(); flash("ok",f"Đăng ký thành công tài khoản '{acc}'.")
        except Exception as e:
            flash("err",f"Lỗi DB: {e}")
            return redirect(url_for("players", create=1))
        return redirect(url_for("players", q=acc))
    return redirect(url_for("players", create=1))

# ---------------- Danh sách người chơi (lọc cột, việt hóa, phân trang 20/trang) ----------------
PER_PAGE = 20
@app.route("/players")
def players():
    q = (request.args.get("q") or "").strip()
    open_create = request.args.get("create") == "1"
    try: pg = max(1, int(request.args.get("pg", 1)))
    except Exception: pg = 1
    rows, total = [], 0
    where = "WHERE a.cAccName LIKE %s" if q else ""
    args = ((f"%{q}%",) if q else ())
    try:
        c = mssql_conn(); cur = c.cursor()
        cur.execute(f"SELECT COUNT(*) FROM Account_Info a {where}", args)
        total = cur.fetchone()[0]
        cur.execute(
            "SELECT a.cAccName, a.iClientID, a.nExtPoint, a.nExtPoint1, "
            "ISNULL(h.iLeftSecond,0), a.bIsBanned, a.dLoginDate "
            "FROM Account_Info a LEFT JOIN account_Habitus h ON a.cAccName=h.cAccName "
            f"{where} ORDER BY CASE WHEN ISNULL(a.iClientID,0)<>0 THEN 0 ELSE 1 END, a.dLoginDate DESC, a.cAccName OFFSET %s ROWS FETCH NEXT %s ROWS ONLY",
            args + ((pg-1)*PER_PAGE, PER_PAGE))
        rows = cur.fetchall(); c.close()
    except Exception as e:
        flash("err", f"Lỗi: {e}")
    pages = max(1, (total + PER_PAGE - 1)//PER_PAGE)
    admin_accounts = _read_game_admin_accounts()
    body = """
    <div class="account-heading"><h1>Tài khoản</h1><button type="button" class="ok" id="openCreateAccount">＋ Tạo tài khoản</button></div>
    <div class="card"><h2>Danh sách — {{total}} tài khoản</h2>
    <form method="get"><div class="row"><div><input name="q" value="{{q}}" placeholder="Lọc theo tên tài khoản (bỏ trống = tất cả)"></div>
    <div style="flex:0"><button>Tìm</button></div></div></form></div>
    <div class="card scroll">
    {% if rows %}<table>
      <tr><th>Tài khoản</th><th>Quyền</th><th>Trạng thái</th><th>Xu</th><th>KNB</th><th>Giờ còn lại</th><th>Khóa</th><th>Đăng nhập lúc</th><th>Thao tác</th></tr>
    {% for r in rows %}<tr>
      <td><b>{{r[0]}}</b></td>
      <td>{% if r[0]|lower in admin_accounts %}<span class="pill on">Admin</span>{% else %}<span class="pill off">Thường</span>{% endif %}</td>
      <td>{% if r[1] and r[1]!=0 %}<span class="pill on">ONLINE</span>{% else %}<span class="pill off">Offline</span>{% endif %}</td>
      <td>{{ r[2] or 0 }}</td>
      <td>{{ r[3] or 0 }}</td>
      <td>{{ '%.1f giờ'|format((r[4] or 0)/3600) }}</td>
      <td>{% if r[5] %}<span class="pill off">Khóa</span>{% else %}<span class="pill on">Bình thường</span>{% endif %}</td>
      <td>{{ r[6] if r[6] else '—' }}</td>
      <td><a class="btn mut" href="/player/{{r[0]}}">Quản lý</a>
        <form method="post" action="{{url_for('player_renew_300_hours', acc=r[0])}}"
              style="display:inline-block;margin-left:6px"
              data-confirm="Gia hạn thêm 300 giờ cho tài khoản {{r[0]}}?">
          <input type="hidden" name="q" value="{{q}}">
          <input type="hidden" name="pg" value="{{pg}}">
          <button class="ok" type="submit">⏱ +300 giờ</button>
        </form>
        <form method="post" action="{{url_for('player_toggle_game_admin', acc=r[0])}}"
              style="display:inline-block;margin-left:6px"
              data-confirm="Xác nhận chuyển quyền tài khoản này? Nhân vật cần đăng nhập lại để áp dụng.">
          <input type="hidden" name="enabled" value="{{0 if r[0]|lower in admin_accounts else 1}}">
          <input type="hidden" name="q" value="{{q}}">
          <input type="hidden" name="pg" value="{{pg}}">
          {% if r[0]|lower in admin_accounts %}
            <button class="mut" type="submit">👤 → User</button>
          {% else %}
            <button type="submit">👑 → Admin</button>
          {% endif %}
        </form>
        <form method="post" action="{{url_for('player_delete', acc=r[0])}}" style="display:inline-block;margin-left:6px"
              data-prompt="Xóa tài khoản {{r[0]}} và toàn bộ nhân vật khỏi account_tong + server1. Nhập đúng tên tài khoản để xác nhận:" data-prompt-title="Xóa vĩnh viễn tài khoản" data-prompt-target="confirm_account" data-prompt-exact="{{r[0]}}" data-prompt-mismatch="Tên tài khoản chưa chính xác." data-dialog-danger="1">
          <input type="hidden" name="confirm_account">
          <button class="err" type="submit">🗑️ Xóa</button>
        </form>
      </td>
    </tr>{% endfor %}</table>
    {% else %}<p class="muted">Chưa có người chơi nào{% if q %} khớp "{{q}}"{% endif %}.</p>{% endif %}
    </div>
    {% if pages > 1 %}<div class="card" style="display:flex;gap:8px;align-items:center;flex-wrap:wrap">
      {% if pg>1 %}<a class="btn mut" href="?q={{q}}&pg={{pg-1}}">← Trước</a>{% endif %}
      <span class="muted">Trang {{pg}}/{{pages}}</span>
      {% if pg<pages %}<a class="btn mut" href="?q={{q}}&pg={{pg+1}}">Sau →</a>{% endif %}
    </div>{% endif %}
    <dialog class="account-create-dialog" id="createAccountDialog">
      <form method="post" action="{{url_for('register')}}">
        <div class="account-dialog-head"><h2>Tạo tài khoản game</h2><button type="button" class="mut" id="closeCreateAccount" aria-label="Đóng">✕</button></div>
        <div class="account-dialog-body">
          <label>Tên tài khoản</label><input name="account" maxlength="32" autocomplete="off" required autofocus>
          <div class="row"><div><label>Mật khẩu cấp 1</label><input name="password1" type="password" autocomplete="new-password" required></div>
          <div><label>Mật khẩu cấp 2</label><input name="password2" type="password" autocomplete="new-password" required></div></div>
          <p class="muted">Mật khẩu được lưu MD5 hoa theo chuẩn game. Tài khoản mới có sẵn 100 giờ chơi.</p>
        </div>
        <div class="account-dialog-foot"><button type="button" class="mut" id="cancelCreateAccount">Hủy</button><button type="submit" class="ok">Tạo tài khoản</button></div>
      </form>
    </dialog>
    <script>
    (function(){const dialog=document.getElementById('createAccountDialog'),openButton=document.getElementById('openCreateAccount'),closeButtons=[document.getElementById('closeCreateAccount'),document.getElementById('cancelCreateAccount')];function open(){if(typeof dialog.showModal==='function')dialog.showModal();else dialog.setAttribute('open','')}function close(){if(typeof dialog.close==='function')dialog.close();else dialog.removeAttribute('open')}openButton.addEventListener('click',open);closeButtons.forEach(button=>button.addEventListener('click',close));dialog.addEventListener('click',event=>{if(event.target===dialog)close()});if({{open_create|tojson}})open()})();
    </script>
    """
    return page(body, page="accounts", q=q, rows=rows, total=total, pg=pg,
                pages=pages, admin_accounts=admin_accounts, open_create=open_create)

# ---------------- Chi tiết 1 người chơi (nút Xem — nơi mở rộng tác vụ sau) ----------------
@app.route("/player/<acc>")
def player_detail(acc):
    info = None
    try:
        c = mssql_conn(); cur = c.cursor(as_dict=True)
        cur.execute("SELECT a.*, h.iLeftSecond, h.dEndDate FROM Account_Info a "
                    "LEFT JOIN account_Habitus h ON a.cAccName=h.cAccName WHERE a.cAccName=%s",(acc,))
        info = cur.fetchone(); c.close()
    except Exception as e:
        flash("err", f"Lỗi: {e}")
    account_key = acc.strip().lower()
    is_game_admin = account_key in _read_game_admin_accounts()
    body = """
    <div class="card"><h2>Người chơi: {{acc}}</h2>
    <a class="btn mut" href="/players">← Danh sách</a>
    {% if info %}
    <div class="card" style="margin-top:14px;background:#121a28">
      <h2>Phân quyền tài khoản game</h2>
      <p class="muted">Trạng thái hiện tại: {% if is_game_admin %}<span class="pill on">Admin</span> — sẽ nhận Lệnh Bài Admin và thu hồi Cẩm Nang Tân Thủ{% else %}<span class="pill off">Tài khoản thường</span> — sẽ nhận Cẩm Nang Tân Thủ và thu hồi Lệnh Bài Admin{% endif %}</p>
      <form method="post" action="{{url_for('player_set_game_admin', acc=acc)}}"
            data-confirm="Cập nhật quyền tài khoản {{acc}}? Nhân vật cần đăng nhập lại để tự cấp/thu hồi vật phẩm.">
        <button class="ok" name="enabled" value="1" {% if is_game_admin %}disabled{% endif %}>Đặt làm Admin</button>
        <button class="err" name="enabled" value="0" {% if not is_game_admin %}disabled{% endif %}>Chuyển về tài khoản thường</button>
      </form>
    </div>
    <div class="card" style="margin-top:14px;background:#121a28">
      <h2>+ Ngày chơi</h2>
      <p class="muted">Cộng ngày chơi vào tài khoản này.</p>
      <form method="post" action="{{url_for('player_add_days', acc=acc)}}"
            data-confirm="Cộng ngày chơi cho tài khoản {{acc}}?">
        <div class="row"><div><label>Số ngày cần cộng</label><input name="days" type="number" min="1" max="3650" value="30" required></div>
        <div style="flex:0;align-self:end"><button class="ok" type="submit">➕ Cộng ngày</button></div></div>
      </form>
    </div>
    <div class="card" style="margin-top:14px;background:#121a28">
      <h2>Thông tin người chơi</h2>
      <table>
        {% for k,v in info.items() %}<tr><th style="width:220px">{{k}}</th><td>{{ '' if v is none else v }}</td></tr>{% endfor %}
      </table>
    </div>
    {% else %}<p class="muted">Không tìm thấy.</p>{% endif %}
    </div>
    """
    return page(body, page="accounts", acc=acc, info=info, is_game_admin=is_game_admin)

def _delete_player_account(acc):
    # Lấy toàn bộ ID/tên nhân vật trước khi xóa Role để dọn các bảng phụ.
    my = mysql_conn()
    my_deleted = 0
    try:
        cur = my.cursor()
        cur.execute("SELECT ID, RoleName FROM Role WHERE Account=%s", (acc,))
        roles = cur.fetchall()
        cur.execute("SELECT RoleName FROM RoleBack WHERE Account=%s", (acc,))
        back_names = [row[0] for row in cur.fetchall()]
        role_ids = [row[0] for row in roles]
        role_names = list(dict.fromkeys([row[1] for row in roles] + back_names))

        def placeholders(values): return ",".join(["%s"] * len(values))
        if role_ids:
            cur.execute(f"DELETE FROM TongMember WHERE MemberID IN ({placeholders(role_ids)})", role_ids)
            my_deleted += cur.rowcount
        if role_names:
            marks = placeholders(role_names)
            cur.execute(f"DELETE FROM OfflineMsg WHERE Receiver IN ({marks}) OR Sender IN ({marks})", role_names + role_names)
            my_deleted += cur.rowcount
            cur.execute(f"DELETE FROM Relation WHERE RoleName IN ({marks})", role_names)
            my_deleted += cur.rowcount
            text_names = []
            for name in role_names:
                if isinstance(name, bytes):
                    for encoding in ("utf-8", "gbk", "latin1"):
                        try:
                            text_names.append(name.decode(encoding)); break
                        except UnicodeDecodeError: pass
                else:
                    text_names.append(str(name))
            if text_names:
                cur.execute(f"DELETE FROM PlayerTag WHERE rolename IN ({placeholders(text_names)})", text_names)
                my_deleted += cur.rowcount
        cur.execute("DELETE FROM RoleBack WHERE Account=%s", (acc,)); my_deleted += cur.rowcount
        cur.execute("DELETE FROM Role WHERE Account=%s", (acc,)); my_deleted += cur.rowcount
        my.commit()
    except Exception:
        my.rollback()
        raise
    finally:
        my.close()

    # Xóa khỏi mọi bảng MSSQL thật có cột cAccName; Account_Info luôn xóa cuối.
    ms = mssql_conn()
    ms_deleted = 0
    try:
        cur = ms.cursor()
        cur.execute("""
            SELECT c.TABLE_SCHEMA,c.TABLE_NAME
            FROM INFORMATION_SCHEMA.COLUMNS c
            JOIN INFORMATION_SCHEMA.TABLES t ON t.TABLE_SCHEMA=c.TABLE_SCHEMA AND t.TABLE_NAME=c.TABLE_NAME
            WHERE c.COLUMN_NAME='cAccName' AND t.TABLE_TYPE='BASE TABLE'
        """)
        tables = cur.fetchall()
        tables.sort(key=lambda row: row[1].lower() == "account_info")
        for schema, table in tables:
            safe_schema = schema.replace("]", "]]" )
            safe_table = table.replace("]", "]]" )
            cur.execute(f"DELETE FROM [{safe_schema}].[{safe_table}] WHERE cAccName=%s", (acc,))
            ms_deleted += cur.rowcount
        ms.commit()
    except Exception:
        ms.rollback()
        raise
    finally:
        ms.close()
    return len(roles), my_deleted, ms_deleted


def _add_account_hours(acc, hours):
    hours = int(hours)
    seconds = hours * 3600
    ms = mssql_conn()
    try:
        cur = ms.cursor()
        cur.execute("SELECT COUNT(*) FROM Account_Info WHERE cAccName=%s", (acc,))
        if cur.fetchone()[0] <= 0:
            raise ValueError("Tài khoản không tồn tại")
        cur.execute("""
            IF EXISTS(SELECT 1 FROM account_Habitus WHERE cAccName=%s)
                UPDATE account_Habitus
                SET iLeftSecond = ISNULL(iLeftSecond,0) + %s,
                    dEndDate = CASE
                        WHEN dEndDate IS NULL OR dEndDate < GETDATE() THEN DATEADD(hour, %s, GETDATE())
                        ELSE DATEADD(hour, %s, dEndDate)
                    END
                WHERE cAccName=%s
            ELSE
                INSERT INTO account_Habitus (cAccName,iLeftSecond,dEndDate,iUseSecond)
                VALUES (%s,%s,DATEADD(hour, %s, GETDATE()),0)
        """, (acc, seconds, hours, hours, acc, acc, seconds, hours))
        cur.execute("SELECT ISNULL(iLeftSecond,0), dEndDate FROM account_Habitus WHERE cAccName=%s", (acc,))
        row = cur.fetchone()
        ms.commit()
        return row
    except Exception:
        ms.rollback()
        raise
    finally:
        ms.close()


def _add_account_days(acc, days):
    return _add_account_hours(acc, int(days) * 24)


@app.route("/player/<acc>/set-game-admin", methods=["POST"])
def player_set_game_admin(acc):
    try:
        enabled = (request.form.get("enabled") or "0") == "1"
        c = mssql_conn(); cur = c.cursor()
        cur.execute("SELECT COUNT(*) FROM Account_Info WHERE cAccName=%s", (acc,))
        exists = cur.fetchone()[0] > 0
        c.close()
        if not exists:
            raise ValueError("Tài khoản không tồn tại")
        _set_game_admin_account(acc, enabled)
        flash("ok", f"Đã {'đặt' if enabled else 'chuyển'} {acc} {'làm Admin' if enabled else 'về tài khoản thường'}. Nhân vật cần đăng nhập lại để áp dụng.")
    except Exception as e:
        flash("err", f"Cập nhật quyền game thất bại: {e}")
    return redirect(url_for("player_detail", acc=acc))


@app.route("/player/<acc>/toggle-game-admin", methods=["POST"])
def player_toggle_game_admin(acc):
    q = (request.form.get("q") or "").strip()
    try:
        pg = max(1, int(request.form.get("pg") or "1"))
    except (TypeError, ValueError):
        pg = 1
    try:
        enabled = (request.form.get("enabled") or "0") == "1"
        c = mssql_conn()
        cur = c.cursor()
        cur.execute("SELECT COUNT(*) FROM Account_Info WHERE cAccName=%s", (acc,))
        exists = cur.fetchone()[0] > 0
        c.close()
        if not exists:
            raise ValueError("Tài khoản không tồn tại")
        _set_game_admin_account(acc, enabled)
        target = "Admin" if enabled else "User"
        flash(
            "ok",
            f"Đã chuyển {acc} thành {target}. "
            "Nhân vật cần đăng nhập lại để áp dụng quyền và vật phẩm.",
        )
    except Exception as e:
        flash("err", f"Chuyển quyền tài khoản {acc} thất bại: {e}")
    return redirect(url_for("players", q=q, pg=pg))


@app.route("/player/<acc>/add-days", methods=["POST"])
def player_add_days(acc):
    try:
        days = int(request.form.get("days") or "0")
        if days < 1 or days > 3650:
            raise ValueError("Số ngày phải từ 1 đến 3650")
        left_seconds, end_date = _add_account_days(acc, days)
        flash("ok", f"Đã cộng {days} ngày chơi cho {acc}. Giờ còn lại: {left_seconds/3600:.1f} giờ. Hạn: {end_date}.")
    except Exception as e:
        flash("err", f"Cộng ngày chơi thất bại: {e}")
    return redirect(url_for("player_detail", acc=acc))


@app.route("/player/<acc>/renew-300-hours", methods=["POST"])
def player_renew_300_hours(acc):
    q = (request.form.get("q") or "").strip()
    try:
        pg = max(1, int(request.form.get("pg") or "1"))
    except (TypeError, ValueError):
        pg = 1
    try:
        left_seconds, end_date = _add_account_hours(acc, 300)
        flash(
            "ok",
            f"Đã gia hạn 300 giờ cho {acc}. "
            f"Giờ còn lại: {left_seconds / 3600:.1f} giờ. Hạn: {end_date}.",
        )
    except Exception as e:
        flash("err", f"Gia hạn 300 giờ cho {acc} thất bại: {e}")
    return redirect(url_for("players", q=q, pg=pg))


ROLE_DATA_TABLES = [
    "OfflineMsg", "PlayerTag", "Relation", "Role", "RoleBack",
    "TongMember", "Tong", "TongUnion", "TongZhaoMu",
]

RANK_RESET_FILES = {
    "/opt/QuanLy_One/JX_Servers/Active/server1/data/rankexp.txt": "Ten              Cap   KinhNghiem ThoiGian             LastTick    Trans FNo Faction   \n",
    "/opt/QuanLy_One/JX_Servers/Active/server1/data/rankexp.tmp": "Ten              Cap   KinhNghiem ThoiGian             LastTick    Trans FNo Faction   \n",
    "/opt/QuanLy_One/JX_Servers/Active/server1/data/rankphuhao.txt": "Ten              Tien          FNo Faction   \n",
    "/opt/QuanLy_One/JX_Servers/Active/server1/data/rankphuhao.tmp": "Ten              Tien          FNo Faction   \n",
    "/opt/QuanLy_One/JX_Servers/Active/server1/data/worldrank_temp_new.txt": "NamePlayer\tLevelPlayer\n",
    "/opt/QuanLy_One/JX_Servers/Active/server1/data/worldrank_temp_old.txt": "NamePlayer\tLevelPlayer\n",
    "/opt/QuanLy_One/JX_Servers/Active/server1/data/worldrank_compared.txt": "NamePlayer\tLevelPlayer\n",
    "/opt/QuanLy_One/JX_Servers/Active/server1/script/global/pgaming/xephang/xephang_log/worldrank_sorted.lua": "nRankingData = {\n\t[71774849] = {RankNum = 0, NamePlayer = 'GM01'},\n}\n",
}

def _reset_rank_files():
    changed = []
    for path, content in RANK_RESET_FILES.items():
        try:
            folder = os.path.dirname(path)
            if folder:
                os.makedirs(folder, exist_ok=True)
            with open(path, "w", encoding="utf-8", newline="") as f:
                f.write(content)
            changed.append(path)
        except Exception as e:
            raise RuntimeError(f"Không ghi được file rank {path}: {e}")
    return changed

def _delete_all_characters():
    my = mysql_conn()
    counts = {}
    try:
        cur = my.cursor()
        cur.execute("SET FOREIGN_KEY_CHECKS=0")
        for table in ROLE_DATA_TABLES:
            cur.execute("SHOW TABLES LIKE %s", (table,))
            if not cur.fetchone():
                continue
            safe_table = "`" + table.replace("`", "``") + "`"
            cur.execute(f"SELECT COUNT(*) FROM {safe_table}")
            counts[table] = cur.fetchone()[0]
        for table in ROLE_DATA_TABLES:
            if table not in counts:
                continue
            safe_table = "`" + table.replace("`", "``") + "`"
            cur.execute(f"TRUNCATE TABLE {safe_table}")
        cur.execute("SET FOREIGN_KEY_CHECKS=1")
        return counts
    except Exception:
        try:
            cur.execute("SET FOREIGN_KEY_CHECKS=1")
        except Exception:
            pass
        raise
    finally:
        my.close()

@app.route("/database/delete-all-characters", methods=["POST"])
def database_delete_all_characters():
    if (request.form.get("confirm") or "").strip().upper() != "XOANHANVAT":
        flash("err", "Phải nhập chính xác XOANHANVAT để xác nhận.")
        return redirect(url_for("database_tools"))
    blocked = _db_action_blocked()
    if blocked:
        flash("err", blocked); return redirect(url_for("database_tools"))
    try:
        safety = _create_backup_set(prefix="before_restore")
        counts = _delete_all_characters()
        rank_files = _reset_rank_files()
        role_count = counts.get("Role", 0)
        roleback_count = counts.get("RoleBack", 0)
        total = sum(counts.values())
        flash("ok", f"Đã xóa sạch nhân vật và làm trống bảng xếp hạng: Role={role_count}, RoleBack={roleback_count}, tổng {total} dòng DB, {len(rank_files)} file rank. Bản an toàn: {safety}.")
    except Exception as e:
        flash("err", f"Xóa tất cả nhân vật thất bại: {e}")
    return redirect(url_for("database_tools"))

@app.route("/player/<acc>/delete", methods=["POST"])
def player_delete(acc):
    confirm_account = (request.form.get("confirm_account") or "").strip()
    if confirm_account.casefold() != acc.casefold():
        flash("err", f"Tên xác nhận không đúng. Chưa xóa tài khoản {acc}.")
        return redirect(url_for("players"))
    blocked = _db_action_blocked()
    if blocked:
        flash("err", blocked); return redirect(url_for("players"))
    try:
        c = mssql_conn(); cur = c.cursor()
        cur.execute("SELECT ISNULL(iClientID,0) FROM Account_Info WHERE cAccName=%s", (acc,))
        row = cur.fetchone(); c.close()
        if not row:
            raise ValueError("Tài khoản không tồn tại")
        if row[0] != 0:
            raise RuntimeError("Tài khoản vẫn đang online, không thể xóa")
        safety = _create_backup_set(prefix="before_restore")
        role_count, my_count, ms_count = _delete_player_account(acc)
        flash("ok", f"Đã xóa {acc}: {role_count} nhân vật, {my_count} dòng server1, {ms_count} dòng account_tong. Bản an toàn: {safety}.")
    except Exception as e:
        flash("err", f"Xóa tài khoản {acc} thất bại: {e}")
    return redirect(url_for("players"))

if __name__ == "__main__":
    app.run(
        host=os.environ.get("MANAGER_BIND", "127.0.0.1"),
        port=int(os.environ.get("MANAGER_PORT", "8080")),
    )
