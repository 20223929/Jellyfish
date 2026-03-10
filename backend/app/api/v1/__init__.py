"""API v1 路由聚合。"""

from fastapi import APIRouter

from app.api.v1.routes import film, health

router = APIRouter()

router.include_router(health.router, tags=["health"])
router.include_router(film.router, prefix="/film", tags=["film"])
