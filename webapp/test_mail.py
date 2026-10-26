import os
import smtplib
from email.message import EmailMessage
from dotenv import load_dotenv

load_dotenv()

msg = EmailMessage()
msg["Subject"] = "LeafLens mail test"
msg["From"] = os.getenv("MAIL_FROM", os.getenv("MAIL_USER"))
msg["To"] = os.getenv("MAIL_USER")        # sends to yourself
msg.set_content("If you can read this, email works.")

with smtplib.SMTP_SSL(os.getenv("MAIL_HOST"), int(os.getenv("MAIL_PORT", 465))) as s:
    s.login(os.getenv("MAIL_USER"), os.getenv("MAIL_PASSWORD"))
    s.send_message(msg)
print("sent")