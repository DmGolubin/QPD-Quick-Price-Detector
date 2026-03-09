import asyncio
import logging
import threading

import uvicorn
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from config import POLL_INTERVAL, WEB_PORT
from database import init_db
from bot import build_bot_app, scheduled_check
from web import web_app
from scraper import close_browser

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s"
)
logger = logging.getLogger("price-tracker")


def run_web_server():
    """Run FastAPI in a separate thread."""
    uvicorn.run(web_app, host="0.0.0.0", port=WEB_PORT, log_level="info")


async def main():
    logger.info("=== Price Tracker Starting ===")

    # Init database
    init_db()
    logger.info("Database ready")

    # Start web server in background thread
    web_thread = threading.Thread(target=run_web_server, daemon=True)
    web_thread.start()
    logger.info(f"Web dashboard on port {WEB_PORT}")

    # Start scheduler
    scheduler = AsyncIOScheduler()
    scheduler.add_job(scheduled_check, 'interval', seconds=POLL_INTERVAL, id='price_check')
    scheduler.start()
    logger.info(f"Scheduler started (every {POLL_INTERVAL}s)")

    # Start Telegram bot
    bot_app = build_bot_app()
    logger.info("Telegram bot starting...")

    try:
        await bot_app.initialize()
        await bot_app.start()
        await bot_app.updater.start_polling(drop_pending_updates=True)
        logger.info("Bot is running. Press Ctrl+C to stop.")

        # Keep running
        while True:
            await asyncio.sleep(1)
    except (KeyboardInterrupt, SystemExit):
        logger.info("Shutting down...")
    finally:
        scheduler.shutdown()
        await bot_app.updater.stop()
        await bot_app.stop()
        await bot_app.shutdown()
        await close_browser()
        logger.info("Shutdown complete")


if __name__ == "__main__":
    asyncio.run(main())
