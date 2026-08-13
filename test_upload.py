import os
import time
import subprocess
import threading
import requests
from requests.exceptions import ConnectionError

# 1. Start moto_server in the background
moto_proc = subprocess.Popen(["moto_server", "-p", "5000"])
time.sleep(2) # wait for moto server to start

# 2. Configure environment for Django
os.environ['AWS_ACCESS_KEY_ID'] = 'test-key'
os.environ['AWS_SECRET_ACCESS_KEY'] = 'test-secret'
os.environ['AWS_STORAGE_BUCKET_NAME'] = 'test-bucket'
os.environ['AWS_S3_ENDPOINT_URL'] = 'http://127.0.0.1:5000'
os.environ['AWS_S3_REGION_NAME'] = 'us-east-1'
os.environ['DEBUG'] = 'True'

# Create the bucket in moto
import boto3
s3 = boto3.client('s3', endpoint_url='http://127.0.0.1:5000', aws_access_key_id='test', aws_secret_access_key='test', region_name='us-east-1')
s3.create_bucket(Bucket='test-bucket')

# 3. Setup Django
import django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'cysd_erp.settings')
django.setup()

from django.core.files.storage import default_storage
from django.core.files.base import ContentFile

print("Uploading file to S3 storage backend...")
file_name = default_storage.save("test_photo.jpg", ContentFile(b"fake image content"))
print(f"File uploaded as: {file_name}")

print("Confirming file is retrievable...")
file_url = default_storage.url(file_name)
print(f"File URL: {file_url}")

# Fetch the file content back
try:
    with default_storage.open(file_name, 'rb') as f:
        content = f.read()
    if content == b"fake image content":
        print("Success! File content matches.")
    else:
        print("Error: File content mismatch.")
except Exception as e:
    print(f"Error reading file: {e}")

# Cleanup Moto
moto_proc.terminate()
