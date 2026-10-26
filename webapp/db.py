import os
import pymysql
from dotenv import load_dotenv

load_dotenv()

def get_db():
    ca_path = os.getenv("DB_SSL_CA")
    if ca_path and not os.path.isabs(ca_path):
        ca_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ca_path)

    return pymysql.connect(
        host=os.getenv("DB_HOST"),
        port=int(os.getenv("DB_PORT", 3306)),
        user=os.getenv("DB_USER"),
        password=os.getenv("DB_PASSWORD"),
        database=os.getenv("DB_NAME"),
        ssl={"ca": ca_path},
        cursorclass=pymysql.cursors.DictCursor,
        autocommit=True,
    )