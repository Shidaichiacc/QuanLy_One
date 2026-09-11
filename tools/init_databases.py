#!/usr/bin/env python3
import os
import time
from pathlib import Path

import pymssql


password = os.environ.get("MSSQL_SA_PASSWORD", "")
if not password:
    raise SystemExit("MSSQL_SA_PASSWORD chưa được cấu hình")
database = os.environ.get("MSSQL_DATABASE", "account_tong")
backup = Path("/opt/QuanLy_One/data/database/seed/account_tong.bak")
sql_backup = "/opt/QuanLy_One/data/database/seed/account_tong.bak"
if not backup.is_file() or backup.stat().st_size == 0:
    raise SystemExit(
        "Thiếu data/database/seed/account_tong.bak; gói cài đặt không đầy đủ. "
        "Hãy cập nhật QuanLy_One rồi thử lại thiết lập database."
    )

connection = None
for attempt in range(60):
    try:
        connection = pymssql.connect(
            server="127.0.0.1",
            port=1433,
            user="sa",
            password=password,
            database="master",
            autocommit=True,
            login_timeout=5,
        )
        break
    except Exception:
        if attempt == 59:
            raise
        time.sleep(2)

with connection:
    cursor = connection.cursor()
    cursor.execute("SELECT DB_ID(%s)", (database,))
    exists = cursor.fetchone()[0] is not None
    if not exists:
        safe_database = database.replace("]", "]]" )
        safe_path = sql_backup.replace("'", "''")
        cursor.execute("RESTORE FILELISTONLY FROM DISK=N'%s'" % safe_path)
        files = cursor.fetchall()
        move_clauses = []
        data_index = 0
        log_index = 0
        for row in files:
            logical_name = str(row[0]).replace("'", "''")
            file_type = str(row[2]).upper()
            if file_type == "L":
                log_index += 1
                filename = "%s%s.ldf" % (database, "_log" if log_index == 1 else "_log%d" % log_index)
            else:
                data_index += 1
                filename = "%s%s.mdf" % (database, "" if data_index == 1 else "_%d" % data_index)
            target = ("/var/opt/mssql/data/" + filename).replace("'", "''")
            move_clauses.append("MOVE N'%s' TO N'%s'" % (logical_name, target))
        cursor.execute(
            "RESTORE DATABASE [%s] FROM DISK=N'%s' WITH REPLACE, %s"
            % (safe_database, safe_path, ", ".join(move_clauses))
        )
        print("Restored MSSQL database:", database)
    elif exists:
        print("MSSQL database already exists:", database)
