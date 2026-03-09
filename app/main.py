"""Price Monitor Pro — Entry point."""
import asyncio
import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.config import settings
from app.database import engine, async_session, Base
from app.api.router import api_v1_router
from app.api.health import router as health_router
from app.web.routes import router as web_router
from app.web.visual_selector import router as selector_router
from app.services.scraper_service import ScraperService
from app.services.scheduler_service import SchedulerService
from app.services.template_service import TemplateService

logging.basicConfig(
    level=getattr(logging, settings.LOG_LEVEL),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

scraper: ScraperService | None = None
scheduler: SchedulerService | None = None
bot_app = None


def _normalize_db_url_for_asyncpg(url: str) -> str:
    """Convert any DB URL variant to plain postgresql:// for asyncpg raw connection."""
    if url.startswith("postgresql+asyncpg://"):
        return url.replace("postgresql+asyncpg://", "postgresql://", 1)
    if url.startswith("postgres://"):
        return url.replace("postgres://", "postgresql://", 1)
    return url


async def run_migrations():
    """Run SQL migrations from app/migrations/."""
    import asyncpg
    db_url = _normalize_db_url_for_asyncpg(settings.DATABASE_URL)
    conn = await asyncpg.connect(db_url)
    try:
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS schema_migrations (
                id SERIAL PRIMARY KEY,
                filename VARCHAR(255) UNIQUE NOT NULL,
                applied_at TIMESTAMP DEFAULT NOW()
            )
        """)
        migrations_dir = Path(__file__).parent / "migrations"
        if migrations_dir.exists():
            for sql_file in sorted(migrations_dir.glob("*.sql")):
                row = await conn.fetchrow(
                    "SELECT id FROM schema_migrations WHERE filename = $1", sql_file.name
                )
                if row:
                    continue
                logger.info(f"Applying migration: {sql_file.name}")
                sql = sql_file.read_text(encoding="utf-8")
                await conn.execute(sql)
                await conn.execute(
                    "INSERT INTO schema_migrations (filename) VALUES ($1)", sql_file.name
                )
                logger.info(f"Migration applied: {sql_file.name}")
    finally:
        await conn.close()


async def init_bot():
    """Initialize Telegram bot."""
    global bot_app
    if not settings.TELEGRAM_BOT_TOKEN:
        logger.warning("TELEGRAM_BOT_TOKEN not set, bot disabled")
        return
    from telegram.ext import (
        Application, CommandHandler, CallbackQueryHandler,
        ConversationHandler, MessageHandler, filters,
    )
    from app.bot.handlers import (
        cmd_start, cmd_add_start, cmd_add_name, cmd_add_url,
        cmd_add_selector, cmd_add_thresholds, cmd_add_confirm, cmd_add_cancel,
        cmd_list, cmd_check, cmd_stats, cmd_report, cmd_settings,
        cmd_export, cmd_apikey, cmd_digest, cmd_help, handle_url_message,
        NAME, URL, SELECTOR, THRESHOLDS, CONFIRM,
    )
    from app.bot.callbacks import callback_handler

    bot_app = Application.builder().token(settings.TELEGRAM_BOT_TOKEN).build()

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("add", cmd_add_start)],
        states={
            NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, cmd_add_name)],
            URL: [MessageHandler(filters.TEXT & ~filters.COMMAND, cmd_add_url)],
            SELECTOR: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, cmd_add_selector),
                CommandHandler("skip", cmd_add_selector),
            ],
            THRESHOLDS: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, cmd_add_thresholds),
                CommandHandler("skip", cmd_add_thresholds),
            ],
            CONFIRM: [
                CommandHandler("confirm", cmd_add_confirm),
                CommandHandler("cancel", cmd_add_cancel),
            ],
        },
        fallbacks=[CommandHandler("cancel", cmd_add_cancel)],
    )

    bot_app.add_handler(conv_handler)
    bot_app.add_handler(CommandHandler("start", cmd_start))
    bot_app.add_handler(CommandHandler("list", cmd_list))
    bot_app.add_handler(CommandHandler("check", cmd_check))
    bot_app.add_handler(CommandHandler("stats", cmd_stats))
    bot_app.add_handler(CommandHandler("report", cmd_report))
    bot_app.add_handler(CommandHandler("settings", cmd_settings))
    bot_app.add_handler(CommandHandler("export", cmd_export))
    bot_app.add_handler(CommandHandler("apikey", cmd_apikey))
    bot_app.add_handler(CommandHandler("digest", cmd_digest))
    bot_app.add_handler(CommandHandler("help", cmd_help))
    bot_app.add_handler(CallbackQueryHandler(callback_handler))
    bot_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_url_message))

    await bot_app.initialize()
    await bot_app.start()
    await bot_app.updater.start_polling(drop_pending_updates=True)
    logger.info("Telegram bot started")


async def seed_templates():
    async with async_session() as session:
        ts = TemplateService(session)
        await ts.seed_templates()
    logger.info("Store templates seeded")


async def _wait_for_db(max_retries: int = 10, delay: float = 3.0):
    """Wait until the database is reachable."""
    import asyncpg
    db_url = _normalize_db_url_for_asyncpg(settings.DATABASE_URL)
    for attempt in range(1, max_retries + 1):
        try:
            conn = await asyncpg.connect(db_url)
            await conn.close()
            logger.info(f"Database reachable (attempt {attempt})")
            return True
        except Exception as e:
            logger.warning(f"DB not ready (attempt {attempt}/{max_retries}): {e}")
            if attempt < max_retries:
                await asyncio.sleep(delay)
    logger.error("Database not reachable after all retries")
    return False


async def _background_init():
    """Initialize heavy services in background so the server starts immediately."""
    global scraper, scheduler

    if not settings.DATABASE_URL:
        logger.warning("DATABASE_URL not set — skipping DB-dependent init")
    else:
        # Wait for DB to be ready (Railway may start app before Postgres)
        db_ready = await _wait_for_db()

        if db_ready:
            # 1. Migrations
            try:
                await run_migrations()
            except Exception as e:
                logger.error(f"Migration failed: {e}", exc_info=True)

            # 2. Seed templates
            try:
                await seed_templates()
            except Exception as e:
                logger.error(f"Template seeding failed: {e}", exc_info=True)
        else:
            logger.error("Skipping migrations and templates — DB unreachable")

    # 3. Scraper (Playwright)
    try:
        scraper = ScraperService(
            max_browsers=settings.MAX_BROWSERS,
            proxy_url=settings.PROXY_URL,
        )
        await scraper.initialize()
    except Exception as e:
        logger.error(f"Scraper init failed: {e}", exc_info=True)
        scraper = None

    # 4. Scheduler
    try:
        if scraper:
            scheduler = SchedulerService(scraper, max_concurrent=settings.MAX_CONCURRENT_CHECKS)
            await scheduler.start()
    except Exception as e:
        logger.error(f"Scheduler start failed: {e}", exc_info=True)
        scheduler = None

    # 5. Telegram bot
    try:
        await init_bot()
    except Exception as e:
        logger.error(f"Telegram bot init failed: {e}", exc_info=True)

    logger.info("Background initialization complete")


@asynccontextmanager
async def lifespan(app: FastAPI):
    global scraper, scheduler
    logger.info("Starting Price Monitor Pro...")

    # Launch all heavy init in background — server starts immediately
    init_task = asyncio.create_task(_background_init())

    logger.info("Server is ready, background services initializing...")
    yield

    # Shutdown: cancel background init if still running
    if not init_task.done():
        init_task.cancel()
        try:
            await init_task
        except asyncio.CancelledError:
            pass

    logger.info("Shutting down...")
    if bot_app:
        try:
            await bot_app.updater.stop()
            await bot_app.stop()
            await bot_app.shutdown()
        except Exception as e:
            logger.error(f"Bot shutdown error: {e}")
    if scheduler:
        try:
            await scheduler.stop()
        except Exception as e:
            logger.error(f"Scheduler shutdown error: {e}")
    if scraper:
        try:
            await scraper.shutdown()
        except Exception as e:
            logger.error(f"Scraper shutdown error: {e}")


app = FastAPI(title="Price Monitor Pro", lifespan=lifespan)

# CORS
origins = settings.CORS_ORIGINS.split(",") if settings.CORS_ORIGINS != "*" else ["*"]
app.add_middleware(CORSMiddleware, allow_origins=origins, allow_credentials=True,
                   allow_methods=["*"], allow_headers=["*"])

# Static files
app.mount("/static", StaticFiles(directory="static"), name="static")

# Routers
app.include_router(health_router)
app.include_router(api_v1_router)
app.include_router(web_router)
app.include_router(selector_router)
