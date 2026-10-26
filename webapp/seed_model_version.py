import json
import os
from db import get_db

BASE = os.path.dirname(os.path.abspath(__file__))
with open(os.path.join(BASE, "model", "metrics.json"), encoding="utf-8") as f:
    metrics = json.load(f)

version = "resnet18-v1"
accuracy = metrics["val_accuracy"]   # 0.9975

conn = get_db()
with conn.cursor() as cur:
    cur.execute("SELECT model_id FROM tbl_model_version WHERE model_version = %s", (version,))
    if cur.fetchone():
        cur.execute("UPDATE tbl_model_version SET accuracy = %s WHERE model_version = %s",
                    (accuracy, version))
        print("updated", version)
    else:
        cur.execute("INSERT INTO tbl_model_version (model_version, accuracy) VALUES (%s, %s)",
                    (version, accuracy))
        print("inserted", version)
    cur.execute("SELECT * FROM tbl_model_version")
    for row in cur.fetchall():
        print(row)
conn.close()