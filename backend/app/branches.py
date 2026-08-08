from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from .config import get_settings
from .database import get_db
from .sync_service import sync_branch
from .sync_store import get_remote_errors, get_sync_status

settings = get_settings()
router = APIRouter(prefix="/api", tags=["sucursales"])


def _get_branch(db: Session, branch_id: int) -> dict:
    row = db.execute(
        text(
            f"SELECT id_sucursal, TRIM(nombre) AS nombre, direccion, servidor, puerto, Activo "
            f"FROM `{settings.branches_table}` WHERE id_sucursal = :id LIMIT 1"
        ),
        {"id": branch_id},
    ).mappings().first()
    if not row:
        raise HTTPException(status_code=404, detail="Sucursal no encontrada")
    branch = dict(row)
    if not branch.get("servidor"):
        raise HTTPException(status_code=400, detail="La sucursal no tiene servidor configurado")
    return branch


@router.get("/branches")
def list_branches(db: Session = Depends(get_db)):
    try:
        rows = db.execute(
            text(
                f"SELECT id_sucursal, TRIM(nombre) AS nombre, direccion, servidor, puerto, Activo "
                f"FROM `{settings.branches_table}` WHERE Activo = b'1' ORDER BY nombre"
            )
        ).mappings().all()
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=500, detail=f"No se pudo leer sucursales: {exc.__class__.__name__}")

    statuses = {item["branch_id"]: item for item in get_sync_status()}
    items = []
    for row in rows:
        item = dict(row)
        item["sync"] = statuses.get(item["id_sucursal"])
        items.append(item)
    return {"items": items}


@router.post("/sync/{branch_id}")
def sync_branch_endpoint(branch_id: int, db: Session = Depends(get_db)):
    branch = _get_branch(db, branch_id)
    try:
        result = sync_branch(branch)
        result["sync"] = get_sync_status(branch_id)
        return result
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail=f"No se pudo sincronizar {str(branch['nombre']).strip()}: {exc}",
        )


@router.get("/branches/{branch_id}/errors")
def branch_errors(branch_id: int):
    items = get_remote_errors(branch_id)
    items.sort(key=lambda item: str(item.get("fecha_hora") or ""), reverse=True)
    return {"items": items, "total": len(items)}
