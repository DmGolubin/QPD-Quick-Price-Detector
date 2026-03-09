"""Multi-channel notification service: Telegram, Email, Webhook, Discord, Slack."""
import asyncio
import json
import logging
from typing import Optional

import aiohttp

from app.config import settings

logger = logging.getLogger(__name__)


class NotificationService:
    def __init__(self):
        self.bot_token = settings.TELEGRAM_BOT_TOKEN
        self.default_chat_id = settings.TELEGRAM_CHAT_ID

    async def send(self, channels: list[dict], alert: dict, screenshot: bytes | None = None) -> list[dict]:
        results = []
        for ch in channels:
            ch_type = ch.get("channel_type", "telegram")
            config = ch.get("config", {})
            if isinstance(config, str):
                try:
                    config = json.loads(config)
                except json.JSONDecodeError:
                    config = {}
            success = False
            for attempt in range(3):
                try:
                    if ch_type == "telegram":
                        chat_id = config.get("chat_id", self.default_chat_id)
                        success = await self.send_telegram(chat_id, alert["message"], screenshot)
                    elif ch_type == "email":
                        success = await self.send_email(config.get("to", ""), alert.get("subject", "Price Alert"), alert["message"])
                    elif ch_type == "webhook":
                        success = await self.send_webhook(config.get("url", ""), alert)
                    elif ch_type == "discord":
                        success = await self.send_discord(config.get("webhook_url", ""), alert["message"])
                    elif ch_type == "slack":
                        success = await self.send_slack(config.get("webhook_url", ""), alert["message"])
                    if success:
                        break
                except Exception as e:
                    logger.warning(f"Notification attempt {attempt + 1} failed for {ch_type}: {e}")
                    if attempt < 2:
                        await asyncio.sleep(10)
            results.append({"channel": ch_type, "success": success})
        return results

    async def send_telegram(self, chat_id: str, message: str, screenshot: bytes | None = None) -> bool:
        if not self.bot_token:
            return False
        async with aiohttp.ClientSession() as session:
            if screenshot:
                url = f"https://api.telegram.org/bot{self.bot_token}/sendPhoto"
                data = aiohttp.FormData()
                data.add_field("chat_id", str(chat_id))
                data.add_field("caption", message[:1024])
                data.add_field("parse_mode", "HTML")
                data.add_field("photo", screenshot, filename="screenshot.jpg", content_type="image/jpeg")
                async with session.post(url, data=data, timeout=aiohttp.ClientTimeout(total=30)) as resp:
                    if resp.status == 429:
                        retry_after = (await resp.json()).get("parameters", {}).get("retry_after", 30)
                        await asyncio.sleep(retry_after)
                        return False
                    return resp.status == 200
            else:
                url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
                payload = {"chat_id": str(chat_id), "text": message, "parse_mode": "HTML", "disable_web_page_preview": True}
                async with session.post(url, json=payload, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                    if resp.status == 429:
                        retry_after = (await resp.json()).get("parameters", {}).get("retry_after", 30)
                        await asyncio.sleep(retry_after)
                        return False
                    return resp.status == 200

    async def send_email(self, to: str, subject: str, body: str) -> bool:
        try:
            import aiosmtplib
            # Placeholder — requires SMTP config
            logger.info(f"Email to {to}: {subject}")
            return True
        except ImportError:
            logger.warning("aiosmtplib not installed")
            return False

    async def send_webhook(self, url: str, payload: dict) -> bool:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                return 200 <= resp.status < 300

    async def send_discord(self, webhook_url: str, message: str) -> bool:
        payload = {"embeds": [{"description": message, "color": 5814783}]}
        async with aiohttp.ClientSession() as session:
            async with session.post(webhook_url, json=payload, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                return 200 <= resp.status < 300

    async def send_slack(self, webhook_url: str, message: str) -> bool:
        payload = {"blocks": [{"type": "section", "text": {"type": "mrkdwn", "text": message}}]}
        async with aiohttp.ClientSession() as session:
            async with session.post(webhook_url, json=payload, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                return 200 <= resp.status < 300
