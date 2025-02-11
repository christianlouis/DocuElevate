#!/usr/bin/env python3

from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    admin_username: str
    admin_password: str
    aws_access_key_id: str
    aws_secret_access_key: str
    aws_region: str
    aws_textract_role_arn: str
    database_url: str
    redis_url: str
    s3_bucket_name: str
    openai_api_key: str
    workdir: str
    dropbox_app_key: str
    dropbox_app_secret: str
    dropbox_token_file_path: str
    dropbox_folder: str
    dropbox_refresh_token: str
    nextcloud_upload_url: str
    nextcloud_username: str
    nextcloud_password: str
    nextcloud_folder: str
    paperless_ngx_url: str
    paperless_ngx_api_token: str
    paperless_host: str

    class Config:
        env_file = ".env"

settings = Settings()
