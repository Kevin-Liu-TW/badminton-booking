import os

class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY", "default-secret")
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    LIFF_ID = os.environ.get("LIFF_ID", "")
    PORT = int(os.environ.get("PORT", 5000))

class DevelopmentConfig(Config):
    SQLALCHEMY_DATABASE_URI = os.environ.get("DATABASE_URL_DEV", "sqlite:///dev.db")
    DEBUG = True

class StagingConfig(Config):
    SQLALCHEMY_DATABASE_URI = os.environ.get("DATABASE_URL_STAGING")
    DEBUG = False

class ProductionConfig(Config):
    SQLALCHEMY_DATABASE_URI = os.environ.get("DATABASE_URL")
    DEBUG = False

config_map = {
    "development": DevelopmentConfig,
    "staging": StagingConfig,
    "production": ProductionConfig
}