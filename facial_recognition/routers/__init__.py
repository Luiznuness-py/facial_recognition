"""Agrega um router por grupo de endpoints para registrar no app."""
from fastapi import APIRouter

from facial_recognition.routers.auth import router as auth_v1_router
from facial_recognition.routers.teams import router as teams_v1_router
from facial_recognition.routers.users import router as users_v1_router
from facial_recognition.routers.lab import router as lab_v1_router
from facial_recognition.routers.access_requests import router as access_requests_v1_router
from facial_recognition.routers.admin import router as admin_router
from facial_recognition.routers.biological_agents import router as agents_router
from facial_recognition.routers.validations import router as validations_router
from facial_recognition.routers.vault import router as vault_router
from facial_recognition.routers.publications import router as publications_router

router = APIRouter()

router.include_router(auth_v1_router, prefix='/api/v1')
router.include_router(teams_v1_router, prefix='/api/v1')
router.include_router(users_v1_router, prefix='/api/v1')
router.include_router(access_requests_v1_router, prefix='/api/v1')
router.include_router(admin_router, prefix='/api/v1')
router.include_router(agents_router, prefix='/api/v1')
router.include_router(validations_router, prefix='/api/v1')
router.include_router(vault_router, prefix='/api/v1')
router.include_router(publications_router, prefix='/api/v1')
router.include_router(lab_v1_router)
