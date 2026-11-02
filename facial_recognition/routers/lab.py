"""Entrega o HTML da bancada temporária."""
from pathlib import Path
from fastapi import APIRouter
from fastapi.responses import FileResponse

router = APIRouter()

FRONTEND = Path(__file__).resolve().parents[1] / 'frontend'


@router.get('/lab', include_in_schema=False)
async def lab():
    """Entrega a página pública da bancada em GET /lab.

    A página não concede acesso privado por si só. Login, dados administrativos e operações
    biométricas continuam protegidos pelas respectivas rotas.

    Returns:
        FileResponse: Arquivo frontend/index.html servido pela aplicação.
    """
    return FileResponse(FRONTEND / 'index.html')
