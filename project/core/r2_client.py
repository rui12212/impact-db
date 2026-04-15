import io
import logging
import boto3
import requests
from botocore.config import Config

from core.config import (
    R2_ACCOUNT_ID,
    R2_ACCESS_KEY_ID,
    R2_SECRET_ACCESS_KEY,
    R2_BUCKET_NAME,
    R2_FOLDER,
    R2_PUBLIC_URL_BASE,
)

logger = logging.getLogger(__name__)

_s3_client = None

def get_r2_client():
    global _s3_client
    if _s3_client is None:
        _s3_client = boto3.client(
            "s3",
            endpoint_url = f"https://{R2_ACCOUNT_ID}.r2.cloudflarestorage.com",
            aws_access_key_id = R2_ACCESS_KEY_ID,
            aws_secret_access_key = R2_SECRET_ACCESS_KEY,
            region_name = "auto",
            config= Config(signature_version= "s3v4"),
        )
    return _s3_client

def upload_from_url(telegra_url: str, file_name: str, content_type:str = "application/octet-stream") -> str:
    # Download actual binary file from the telegram and upload to R2.
    # then return public url
    response = requests.get(telegra_url, stream=True, timeout=180)
    response.raise_for_status()

    object_key = f"{R2_FOLDER}/{file_name}"
    get_r2_client().upload_fileobj(
        io.BytesIO(response.content),
        R2_BUCKET_NAME,
        object_key,
        ExtraArgs={"ContentType": content_type},
    )
    logger.info("Uploaded to R2: %s", object_key)
    return f"{R2_PUBLIC_URL_BASE}/{object_key}"

def upload_from_path(file_path: str, file_name:str, content_type:str = "application/octet-stream") -> str:
    # upload file from LOCAL FILE PATH. then return public url
    object_key = f"{R2_FOLDER}/{file_name}"
    with open(file_path, "rb") as f:
        get_r2_client().upload_fileobj(
            f,
            R2_BUCKET_NAME,
            object_key,
            ExtraArgs={"ContentType": content_type},
        )
    logger.info("Uploaded to R2: %s", object_key)
    return f"{R2_PUBLIC_URL_BASE}/{object_key}"