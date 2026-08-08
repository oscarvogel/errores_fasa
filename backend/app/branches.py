from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from .config import get_settings
from .database import get_db
from .sync_service import get_branch_sync_status, sync_branch

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

    items = []
    for row in rows:
        item = dict(row)
        try:
            item["sync"] = get_branch_sync_status(int(item["id_sucursal"]))
        except SQLAlchemyError:
            item["sync"] = None
        items.append(item)
    return {"items": items}


@router.post("/sync/{branch_id}")
def sync_branch_endpoint(branch_id: int, db: Session = Depends(get_db)):
    branch = _get_branch(db, branch_id)
    try:
        result = sync_branch(branch)
        result["sync"] = get_branch_sync_status(branch_id)
        return result
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail=f"No se pudo sincronizar {str(branch['nombre']).strip()}: {exc}",
        )


@router.get("/branches/{branch_id}/errors")
def branch_errors(branch_id: int, db: Session = Depends(get_db)):
    _get_branch(db, branch_id)
    rows = db.execute(
        text(
            f"SELECT `{settings.error_id_column}` AS _id, t.* "
            f"FROM `{settings.error_table}` t "
            "WHERE sincronizado = 1 AND id_sucursal_origen = :branch_id "
            f"ORDER BY fecha_hora DESC, `{settings.error_id_column}` DESC"
        ),
        {"branch_id": branch_id},
    ).mappings().all()
    return {"items": [dict(row) for row in rows], "total": len(rows)}
