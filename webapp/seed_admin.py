from werkzeug.security import generate_password_hash
from db import get_db

FIRST_NAME = "Vincent"
LAST_NAME = "Ofoka"
EMAIL = "vincentofoka@gmail.com"
PASSWORD = "project"

conn = get_db()
with conn.cursor() as cur:
    cur.execute("SELECT admin_id FROM tbl_administrators WHERE email = %s", (EMAIL,))
    if cur.fetchone():
        print("Admin already exists, nothing inserted.")
    else:
        cur.execute(
            "INSERT INTO tbl_administrators (first_name, last_name, email, password_hash) "
            "VALUES (%s, %s, %s, %s)",
            (FIRST_NAME, LAST_NAME, EMAIL, generate_password_hash(PASSWORD)),
        )
        print("Admin created.")
    cur.execute("SELECT admin_id, first_name, last_name, email, date_added FROM tbl_administrators")
    for row in cur.fetchall():
        print(row)
conn.close()