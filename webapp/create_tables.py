from db import get_db

conn = get_db()
with conn.cursor() as cur:
    for stmt in open("schema.sql", encoding="utf-8").read().split(";"):
        if stmt.strip():
            cur.execute(stmt)
    cur.execute("SHOW TABLES")
    for row in cur.fetchall():
        print(list(row.values())[0])
conn.close()
print("done")