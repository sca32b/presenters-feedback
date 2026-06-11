import os

from pydantic_settings import BaseSettings

# Windows batch scripts can add trailing spaces to env vars (set VAR=true && ...)
# Strip whitespace before Pydantic validates
_local_dev_raw = os.environ.get("LOCAL_DEV", "")
if _local_dev_raw != _local_dev_raw.strip():
    os.environ["LOCAL_DEV"] = _local_dev_raw.strip()


class Settings(BaseSettings):
    local_dev: bool = False
    environment: str = "dev"
    aws_region: str = "us-east-1"
    s3_bucket: str = "presenters-feedback-dev"
    dynamodb_table: str = "presenters-feedback-dev"
    cognito_user_pool_id: str = ""
    cognito_app_client_id: str = ""
    bedrock_model_id: str = "us.anthropic.claude-fable-5"
    cors_allowed_origins: str = "*"
    upload_url_expiry: int = 300  # 5 minutes
    max_audio_size_mb: int = 50

    class Config:
        env_file = ".env"


settings = Settings()
