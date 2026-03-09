"""Authentication service: users, API keys, JWT sessions."""
import hashlib
import secrets
from datetime import datetime, timedelta, timezone

from jose import jwt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.user import APIKey, User


class AuthService:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_or_create_user(self, telegram_chat_id: str, username: str | None = None) -> User:
        result = await self.session.execute(
            select(User).where(User.telegram_chat_id == str(telegram_chat_id))
        )
        user = result.scalar_one_or_none()
        if user:
            return user
        user = User(telegram_chat_id=str(telegram_chat_id), username=username)
        self.session.add(user)
        await self.session.commit()
        await self.session.refresh(user)
        return user

    async def get_user_by_id(self, user_id: int) -> User | None:
        result = await self.session.execute(select(User).where(User.id == user_id))
        return result.scalar_one_or_none()

    async def generate_api_key(self, user_id: int, name: str = "default") -> str:
        raw_key = secrets.token_hex(32)
        key_hash = hashlib.sha256(raw_key.encode()).hexdigest()
        key_prefix = raw_key[:8]
        api_key = APIKey(user_id=user_id, key_hash=key_hash, key_prefix=key_prefix, name=name)
        self.session.add(api_key)
        await self.session.commit()
        return raw_key

    async def authenticate_api_key(self, key: str) -> User | None:
        key_hash = hashlib.sha256(key.encode()).hexdigest()
        result = await self.session.execute(
            select(APIKey).where(APIKey.key_hash == key_hash, APIKey.is_active == True)
        )
        api_key = result.scalar_one_or_none()
        if not api_key:
            return None
        api_key.last_used_at = datetime.utcnow()
        await self.session.commit()
        return await self.get_user_by_id(api_key.user_id)

    def create_session_token(self, user_id: int) -> str:
        payload = {
            "sub": str(user_id),
            "exp": datetime.now(timezone.utc) + timedelta(hours=24),
            "iat": datetime.now(timezone.utc),
        }
        return jwt.encode(payload, settings.API_SECRET_KEY, algorithm="HS256")

    def verify_session_token(self, token: str) -> int | None:
        try:
            payload = jwt.decode(token, settings.API_SECRET_KEY, algorithms=["HS256"])
            return int(payload["sub"])
        except Exception:
            return None
