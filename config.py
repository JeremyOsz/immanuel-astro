import os
from typing import List
from dotenv import load_dotenv

load_dotenv()

class Config:
    """Configuration class for the Astrology API."""
    
    # API Key settings
    API_KEY = os.getenv("API_KEY", "your-secret-api-key-here")
    
    # Allowed origins for CORS (if you want to add CORS later)
    ALLOWED_ORIGINS: List[str] = [
        "http://localhost:3000",  # React dev server
        "http://localhost:5173",  # Vite dev server
        "http://localhost:8080",  # Vue dev server
        # Add your production domains here
    ]
    
    # Environment
    ENVIRONMENT = os.getenv("ENVIRONMENT", "development")
    
    # Server settings
    HOST = os.getenv("HOST", "0.0.0.0")
    PORT = int(os.getenv("PORT", "8000"))

# Create a config instance
config = Config() 