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



    class Config:
        env_file = ".env"

settings = Settings()
