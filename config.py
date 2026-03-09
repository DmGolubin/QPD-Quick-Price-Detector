import os

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://postgres:rUNgtCwxCNibmTGiqufRGVpLEYkuDThn@shuttle.proxy.rlwy.net:23253/railway"
)
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "8749748849:AAHP-4VP_FPv7Ay_o1h_CoOkUJ3SXj7omlo")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "524596366")
POLL_INTERVAL = int(os.getenv("POLL_INTERVAL", "300"))  # seconds
WEB_PORT = int(os.getenv("PORT", os.getenv("WEB_PORT", "8080")))  # Railway uses PORT
