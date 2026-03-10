"""FastAPI 依赖注入。"""

from collections.abc import AsyncGenerator

from fastapi import HTTPException
from langchain_core.runnables import Runnable
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.db import async_session_maker


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """提供异步数据库会话。"""
    async with async_session_maker() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


def get_llm() -> Runnable:
    """提供 LLM（ChatOpenAI），用于影视技能抽取。未配置 OPENAI_API_KEY 时抛出 503。"""
    if not settings.openai_api_key:
        raise HTTPException(
            status_code=503,
            detail="OPENAI_API_KEY not configured; set it in .env to use film extraction endpoints",
        )
    try:
        from langchain_openai import ChatOpenAI
    except ImportError as e:
        raise HTTPException(
            status_code=503,
            detail="Install langchain-openai (e.g. uv sync --group dev) to use film extraction endpoints",
        ) from e
    kwargs: dict = {
        "model": settings.openai_model,
        "temperature": 0,
        "api_key": settings.openai_api_key,
        }
    if settings.openai_base_url:
        kwargs["base_url"] = settings.openai_base_url
    return ChatOpenAI(**kwargs)
