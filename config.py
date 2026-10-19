import os
from dotenv import load_dotenv

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Explicitly load .env from the backend directory
load_dotenv(os.path.join(BASE_DIR, ".env"))


class Config:
    DB_HOST = os.getenv("DB_HOST", "localhost")
    DB_PORT = os.getenv("DB_PORT", "3306")
    DB_NAME = os.getenv("DB_NAME", "university_impact")
    DB_USER = os.getenv("DB_USER", "root")
    DB_PASSWORD = os.getenv("DB_PASSWORD", "")

    # Set USE_SQLITE=1 in .env for local dev/testing without a MySQL server
    # (e.g. quick grading/demo). Production/deployment should use MySQL.
    if os.getenv("USE_SQLITE", "0") == "1":
        SQLALCHEMY_DATABASE_URI = "sqlite:///" + os.path.join(BASE_DIR, "dev.db")
    else:
        SQLALCHEMY_DATABASE_URI = (
            f"mysql+pymysql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
        )
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", "dev-secret-change-me")
    JWT_EXPIRY_HOURS = int(os.getenv("JWT_EXPIRY_HOURS", "12"))

    # Anthropic (Optional/Fallback)
    ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
    ANTHROPIC_MODEL = os.getenv("ANTHROPIC_MODEL", "claude-3-haiku-20240307")

    # Google Gemini AI
    GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")

    ML_MODEL_PATH = os.path.join(BASE_DIR, "ml", "risk_model.joblib")

    REPORTS_DIR = os.path.join(BASE_DIR, "reports_output")
    EXPORTS_DIR = os.path.join(BASE_DIR, "exports_output")

    DEBUG = os.getenv("FLASK_DEBUG", "1") == "1"