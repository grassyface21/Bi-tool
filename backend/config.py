import os
from dotenv import load_dotenv

load_dotenv()

# AWS credentials
AWS_ACCESS_KEY_ID = os.getenv("AWS_ACCESS_KEY_ID")
AWS_SECRET_ACCESS_KEY = os.getenv("AWS_SECRET_ACCESS_KEY")
AWS_SESSION_TOKEN = os.getenv("AWS_SESSION_TOKEN")
AWS_REGION = os.getenv("AWS_REGION", "us-east-1")
BEDROCK_MODEL_ID = os.getenv("BEDROCK_MODEL_ID", "us.anthropic.claude-sonnet-4-6")

# Session configuration
SESSION_TIMEOUT = 86400  # 24 hours in seconds
SESSION_CLEANUP_INTERVAL = 3600  # 1 hour in seconds

# File upload limits
MAX_FILE_SIZE = 100 * 1024 * 1024  # 100MB
MAX_FILES_PER_UPLOAD = 10
ALLOWED_EXTENSIONS = {".csv", ".xlsx"}
ALLOWED_MIME_TYPES = {
    "text/csv",
    "application/vnd.ms-excel",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "text/plain",
    "application/octet-stream",
}

# Code execution
CODE_EXECUTION_TIMEOUT = 30  # seconds
MAX_RESULT_ROWS = 10000
