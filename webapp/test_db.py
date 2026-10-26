# webapp/test_db.py
from db import get_db

conn = get_db()
with conn.cursor() as cur:
    cur.execute("SELECT 1 AS ok")
    print(cur.fetchone())
conn.close()