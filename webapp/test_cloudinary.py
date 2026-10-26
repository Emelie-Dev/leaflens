import io
import os

import cloudinary
import cloudinary.uploader
from dotenv import load_dotenv
from PIL import Image

load_dotenv()

cloudinary.config(
    cloud_name=os.getenv("CLOUDINARY_CLOUD_NAME"),
    api_key=os.getenv("CLOUDINARY_API_KEY"),
    api_secret=os.getenv("CLOUDINARY_API_SECRET"),
    secure=True,
)

# Make a small green test image in memory
buf = io.BytesIO()
Image.new("RGB", (200, 200), (34, 139, 34)).save(buf, "JPEG")
buf.seek(0)

result = cloudinary.uploader.upload(buf, folder="leaflens-test", resource_type="image")
print("uploaded:", result["secure_url"])
print("public_id:", result["public_id"])

cloudinary.uploader.destroy(result["public_id"])
print("test image deleted")