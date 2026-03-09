"""Scheduler service: per-monitor intervals, priority queue, worker pool."""
import asyncio
import logging
import random
import time as time_mod
from datetime import datetime, timezone

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import async_session
from app.models.monitor import Monitor
from app.models.price import PriceHistory
from app.services.alert_service import AlertService
from app.services.availability_service import AvailabilityService
from app.services.notification_service import NotificationService
from app.services.price_parser import PriceParser
from app.services.scraper_service import ScraperService, ScrapeConfig
from app.services.screenshot_service import ScreenshotService

logger = logging.getLogger(__name__)


class SchedulerService:
    def __init__(self, scraper: ScraperService, max_concurrent: int = 5):
        self.scraper = scraper
        self.max_concurrent = max_concurrent
        self._semaphore = asyncio.Semaphore(max_concurrent)
        self._queue: asyncio.PriorityQueue = asyncio.PriorityQueue()
        self._running = False
        self._workers: list[asyncio.Task] = []
        self._scheduled: dict[int, float] = {}  # monitor_id -> next_run_time
        self.notification_service = NotificationService()

    async def start(self):
        if self._running:
            return
        self._running = True
        async with async_session() as session:
            result = await session.execute(
                select(Monitor).where(Monitor.is_active == True)
            )
            monitors = list(result.scalars().all())
            await self._distribute_evenly(monitors)
        for _ in range(self.max_concurrent):
            task = asyncio.create_task(self._worker())
            self._workers.append(task)
        asyncio.create_task(self._scheduler_loop())
        logger.info(f"Scheduler started with {self.max_concurrent} workers")

    async def stop(self):
        self._running = False
        for w in self._workers:
            w.cancel()
        self._workers.clear()

    async def schedule_monitor(self, monitor_id: int, interval: int):
        next_run = time_mod.time() + interval
        self._scheduled[monitor_id] = next_run

    async def unschedule_monitor(self, monitor_id: int):
        self._scheduled.pop(monitor_id, None)

    async def enqueue_immediate(self, monitor_ids: list[int]):
        for mid in monitor_ids:
            await self._queue.put((time_mod.time(), mid))

    async def _distribute_evenly(self, monitors: list):
        now = time_mod.time()
        if not monitors:
            return
        for i, m in enumerate(monitors):
            jitter = random.uniform(0, min(m.check_interval, 60))
            next_run = now + jitter
            self._scheduled[m.id] = next_run

    async def _scheduler_loop(self):
        while self._running:
            now = time_mod.time()
            for mid, next_run in list(self._scheduled.items()):
                if now >= next_run:
                    await self._queue.put((next_run, mid))
                    # Reschedule
                    async with async_session() as session:
                        result = await session.execute(
                            select(Monitor.check_interval).where(Monitor.id == mid)
                        )
                        interval = result.scalar() or 300
                    self._scheduled[mid] = now + interval
            await asyncio.sleep(5)

    async def _worker(self):
        while self._running:
            try:
                priority, monitor_id = await asyncio.wait_for(self._queue.get(), timeout=10)
            except asyncio.TimeoutError:
                continue
            except asyncio.CancelledError:
                break
            async with self._semaphore:
                await self._check_monitor(monitor_id)

    async def _check_monitor(self, monitor_id: int):
        async with async_session() as session:
            result = await session.execute(select(Monitor).where(Monitor.id == monitor_id))
            monitor = result.scalar_one_or_none()
            if not monitor or not monitor.is_active:
                return
            old_price = float(monitor.last_price) if monitor.last_price else None
            config = ScrapeConfig(
                css_selector=monitor.css_selector,
                xpath_selector=monitor.xpath_selector,
                js_expression=monitor.js_expression,
                currency=monitor.currency,
            )
            # Load macros
            from app.models.macro import Macro
            macros_result = await session.execute(
                select(Macro).where(Macro.monitor_id == monitor_id).order_by(Macro.step_order)
            )
            macros = list(macros_result.scalars().all())
            config.macro_steps = [{"action_type": m.action_type, "selector": m.selector, "params": m.params} for m in macros]

            scrape_result = await self.scraper.scrape_with_retry(monitor.url, config)

            if scrape_result.error and scrape_result.price is None:
                monitor.consecutive_failures = (monitor.consecutive_failures or 0) + 1
                monitor.last_error = scrape_result.error
                if monitor.consecutive_failures == 3:
                    await self.notification_service.send_telegram(
                        str(monitor.user_id),
                        f"⚠️ Монитор <b>{monitor.name}</b> не работает: {scrape_result.error}",
                    )
                await session.commit()
                return

            # Success — reset failures
            was_failing = (monitor.consecutive_failures or 0) >= 3
            monitor.consecutive_failures = 0
            monitor.last_error = None
            monitor.last_price = scrape_result.price
            monitor.last_raw_text = scrape_result.raw_text
            monitor.last_checked = datetime.utcnow()
            monitor.availability_status = scrape_result.availability_status

            if was_failing:
                await self.notification_service.send_telegram(
                    str(monitor.user_id),
                    f"✅ Монитор <b>{monitor.name}</b> восстановлен",
                )

            # Save screenshot
            screenshot_id = None
            if scrape_result.screenshot:
                ss_service = ScreenshotService(session)
                ss = await ss_service.save_screenshot(monitor_id, scrape_result.screenshot)
                screenshot_id = ss.id

            # Save price history
            ph = PriceHistory(
                monitor_id=monitor_id,
                price=scrape_result.price,
                raw_text=scrape_result.raw_text,
                availability_status=scrape_result.availability_status,
                screenshot_id=screenshot_id,
            )
            session.add(ph)

            # Evaluate alerts
            if scrape_result.price is not None:
                alert_service = AlertService(session)
                alerts = await alert_service.evaluate_conditions(monitor, old_price, scrape_result.price)
                if alerts:
                    for alert in alerts:
                        channels = [{"channel_type": "telegram", "config": {"chat_id": str(monitor.user_id)}}]
                        screenshot_data = scrape_result.screenshot if scrape_result.price != old_price else None
                        alert_msg = {
                            "message": f"<b>{monitor.name}</b>\n{alert['message']}\n<a href='{monitor.url}'>Открыть</a>",
                            "monitor_id": monitor_id,
                            "url": monitor.url,
                            "old_price": old_price,
                            "new_price": scrape_result.price,
                        }
                        await self.notification_service.send(channels, alert_msg, screenshot_data)

            await session.commit()
            logger.info(f"Checked monitor {monitor_id}: price={scrape_result.price}")
