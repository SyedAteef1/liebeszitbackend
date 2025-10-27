"""
Application Configuration
Centralized configuration management
"""
import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    """Base configuration"""
    
    # Flask
    SECRET_KEY = os.getenv("FLASK_SECRET", "change_this_in_production")
    DEBUG = os.getenv("DEBUG", "False").lower() == "true"
    
    # URLs
    BACKEND_URL = os.getenv("BASE_URL", "https://localhost:5000")
    FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:3000")
    
    # MongoDB
    MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017/")
    DATABASE_NAME = "feeta"
    
    # GitHub OAuth
    GITHUB_CLIENT_ID = os.getenv("GITHUB_CLIENT_ID")
    GITHUB_CLIENT_SECRET = os.getenv("GITHUB_CLIENT_SECRET")
    
    # Slack OAuth
    SLACK_CLIENT_ID = os.getenv("SLACK_CLIENT_ID")
    SLACK_CLIENT_SECRET = os.getenv("SLACK_CLIENT_SECRET")
    
    # AI API Keys
    GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
    
    # Session
    SESSION_COOKIE_SECURE = False  # Set to True in production with HTTPS
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'Lax'
    SESSION_COOKIE_DOMAIN = 'localhost'
    
    @staticmethod
    def validate():
        """Validate required configuration"""
        required = ['GEMINI_API_KEY', 'MONGO_URI']
        missing = [key for key in required if not getattr(Config, key)]
        if missing:
            raise ValueError(f"Missing required configuration: {', '.join(missing)}")
        
        print("✅ Configuration validated")


