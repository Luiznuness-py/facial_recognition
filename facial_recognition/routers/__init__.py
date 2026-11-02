"""Agrega um router por grupo de endpoints para registrar no app."""
from facial_recognition.routers.auth import router as auth_v1_router
from facial_recognition.routers.teams import router as teams_v1_router
from facial_recognition.routers.users import router as users_v1_router
from facial_recognition.routers.lab import router as lab_v1_router
from facial_recognition.routers.access_requests import router as access_requests_v1_router


from fastapi import APIRouter

router = APIRouter()

router.include_router(auth_v1_router, prefix='/api/v1')
router.include_router(teams_v1_router, prefix='/api/v1')
router.include_router(users_v1_router, prefix='/api/v1')
router.include_router(access_requests_v1_router, prefix='/api/v1')


router.include_router(lab_v1_router)
