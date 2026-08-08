from datetime import date, datetime, timedelta
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from .branches import router as branches_router
from .config import get_settings
from .database import engine, get_db

settings = get_settings()
app = FastAPI(
    title=settings.app_name,
    version="0.3.0",
    docs_url="/api/docs",
    openapi_url="/api/openapi.json",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)
app.include_router(branches_router)

DbSession = Annotated[Session, Depends(get_db)]
TABLE = settings.error_table
ID = settings.error_id_column

TOP_FIELDS = {
    "nro_error": "nro_error",
    "metodo": "metodo",
    "formulario": "formulario",
    "usuario": "usuario",
    "maquina": "maquina",
    "version_sistema": "version_sistema",
    "objeto": "objeto",
}

GROUP_MODES = {
    "error": ("nro_error", "CAST(nro_error AS CHAR)"),
    "formulario": ("formulario", "COALESCE(NULLIF(TRIM(formulario), ''), '(sin formulario)')"),
    "metodo": ("metodo", "COALESCE(NULLIF(TRIM(metodo), ''), '(sin método)')"),
    "firma": (
        "firma",
        "CONCAT(COALESCE(CAST(nro_error AS CHAR), '-'), ' · ', "
        "COALESCE(NULLIF(TRIM(formulario), ''), '(sin formulario)'), ' · ', "
        "COALESCE(NULLIF(TRIM(metodo), ''), '(sin método)'))",
    ),
}


def rows_to_dicts(result):
    return [dict(row._mapping) for row in result]


def origin_filter(branch_id: int, alias: str = ""):
    prefix = f"{alias}." if alias else ""
    if branch_id == 0:
        return f"{prefix}id_sucursal_origen IS NULL", {}
    if branch_id > 0:
        return f"{prefix}id_sucursal_origen = :branch_id", {"branch_id": branch_id}
    return "", {}


def build_filters(*, desde=None, hasta=None, nro_error=None, metodo=None, formulario=None,
                  usuario=None, maquina=None, version=None, q=None, branch_id=-1):
    clauses, params = [], {}
    origin, origin_params = origin_filter(branch_id)
    if origin:
        clauses.append(origin)
        params.update(origin_params)
    if desde:
        clauses.append("fecha_hora >= :desde")
        params["desde"] = datetime.combine(desde, datetime.min.time())
    if hasta:
        clauses.append("fecha_hora < :hasta_exclusivo")
        params["hasta_exclusivo"] = datetime.combine(hasta + timedelta(days=1), datetime.min.time())
    if nro_error is not None:
        clauses.append("nro_error = :nro_error")
        params["nro_error"] = nro_error
    for name, value, column in [
        ("metodo", metodo, "metodo"),
        ("formulario", formulario, "formulario"),
        ("usuario", usuario, "usuario"),
        ("maquina", maquina, "maquina"),
    ]:
        if value:
            clauses.append(f"`{column}` LIKE :{name}")
            params[name] = f"%{value}%"
    if version:
        clauses.append("version_sistema = :version")
        params["version"] = version
    if q:
        clauses.append(
            "CONCAT_WS(' ', mensaje, nom_error, metodo, objeto, formulario, control, "
            "codigo_fuente, call_stack, info_extra) LIKE :q"
        )
        params["q"] = f"%{q}%"
    return (" WHERE " + " AND ".join(clauses) if clauses else ""), params


@app.get("/api/health")
def health():
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
            columns = [row[0] for row in conn.execute(text(f"SHOW COLUMNS FROM `{TABLE}`"))]
        return {
            "status": "ok", "database": "ok", "table": TABLE,
            "id_column": ID, "id_column_found": ID in columns, "columns": columns,
        }
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=503, detail=f"Base de datos no disponible: {exc.__class__.__name__}")


@app.get("/api/errors")
def list_errors(
    db: DbSession,
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=100),
    branch_id: int = Query(-1, ge=-1),
    desde: date | None = None,
    hasta: date | None = None,
    nro_error: int | None = None,
    metodo: str | None = None,
    formulario: str | None = None,
    usuario: str | None = None,
    maquina: str | None = None,
    version: str | None = None,
    q: str | None = None,
):
    where, params = build_filters(
        desde=desde, hasta=hasta, nro_error=nro_error, metodo=metodo,
        formulario=formulario, usuario=usuario, maquina=maquina, version=version,
        q=q, branch_id=branch_id,
    )
    total = db.execute(text(f"SELECT COUNT(*) FROM `{TABLE}`{where}"), params).scalar_one()
    params.update({"limit": page_size, "offset": (page - 1) * page_size})
    data_sql = text(
        f"SELECT `{ID}` AS _id, t.* FROM `{TABLE}` t{where} "
        f"ORDER BY fecha_hora DESC, `{ID}` DESC LIMIT :limit OFFSET :offset"
    )
    return {
        "items": rows_to_dicts(db.execute(data_sql, params)),
        "page": page,
        "page_size": page_size,
        "total": total,
        "pages": max(1, (total + page_size - 1) // page_size),
    }


@app.get("/api/errors/{error_id}")
def get_error(error_id: int, db: DbSession):
    sql = text(f"SELECT `{ID}` AS _id, t.* FROM `{TABLE}` t WHERE `{ID}` = :error_id LIMIT 1")
    row = db.execute(sql, {"error_id": error_id}).first()
    if not row:
        raise HTTPException(status_code=404, detail="Error no encontrado")
    return dict(row._mapping)


@app.get("/api/dashboard/summary")
def dashboard_summary(
    db: DbSession,
    days: int = Query(30, ge=1, le=3650),
    branch_id: int = Query(-1, ge=-1),
):
    since = datetime.now() - timedelta(days=days)
    origin, origin_params = origin_filter(branch_id)
    clauses = ["fecha_hora >= :since"]
    if origin:
        clauses.append(origin)
    params = {"since": since, **origin_params}
    where = " WHERE " + " AND ".join(clauses)
    row = db.execute(text(f"""
        SELECT COUNT(*) AS total,
               SUM(fecha_hora >= CURDATE()) AS hoy,
               COUNT(DISTINCT nro_error) AS tipos_error,
               COUNT(DISTINCT maquina) AS equipos,
               COUNT(DISTINCT usuario) AS usuarios,
               MAX(fecha_hora) AS ultimo_error
        FROM `{TABLE}`{where}
    """), params).first()

    version_clauses = ["version_sistema IS NOT NULL", "version_sistema <> ''"]
    if origin:
        version_clauses.append(origin)
    latest_version = db.execute(text(
        f"SELECT version_sistema FROM `{TABLE}` WHERE {' AND '.join(version_clauses)} "
        "ORDER BY fecha_hora DESC LIMIT 1"
    ), origin_params).scalar()
    result = dict(row._mapping) if row else {}
    result.update({"version_actual": latest_version, "days": days, "branch_id": branch_id})
    return result


@app.get("/api/dashboard/timeline")
def dashboard_timeline(
    db: DbSession,
    days: int = Query(30, ge=1, le=365),
    branch_id: int = Query(-1, ge=-1),
):
    since = (datetime.now() - timedelta(days=days - 1)).date()
    origin, origin_params = origin_filter(branch_id)
    clauses = ["fecha_hora >= :since"]
    if origin:
        clauses.append(origin)
    rows = db.execute(text(f"""
        SELECT DATE(fecha_hora) AS fecha, COUNT(*) AS cantidad
        FROM `{TABLE}` WHERE {' AND '.join(clauses)}
        GROUP BY DATE(fecha_hora) ORDER BY fecha ASC
    """), {"since": since, **origin_params})
    return {"items": rows_to_dicts(rows), "days": days, "branch_id": branch_id}


@app.get("/api/dashboard/top")
def dashboard_top(
    db: DbSession,
    field: str = Query("nro_error"),
    days: int = Query(30, ge=1, le=3650),
    limit: int = Query(10, ge=1, le=50),
    branch_id: int = Query(-1, ge=-1),
):
    column = TOP_FIELDS.get(field)
    if not column:
        raise HTTPException(status_code=400, detail=f"Campo inválido. Opciones: {', '.join(TOP_FIELDS)}")
    since = datetime.now() - timedelta(days=days)
    origin, origin_params = origin_filter(branch_id)
    clauses = ["fecha_hora >= :since", f"`{column}` IS NOT NULL", f"CAST(`{column}` AS CHAR) <> ''"]
    if origin:
        clauses.append(origin)
    rows = db.execute(text(f"""
        SELECT `{column}` AS valor, COUNT(*) AS cantidad, MAX(fecha_hora) AS ultimo
        FROM `{TABLE}`
        WHERE {' AND '.join(clauses)}
        GROUP BY `{column}` ORDER BY cantidad DESC LIMIT :limit
    """), {"since": since, "limit": limit, **origin_params})
    return {"field": field, "items": rows_to_dicts(rows), "branch_id": branch_id}


@app.get("/api/dashboard/repeated")
def dashboard_repeated(
    db: DbSession,
    group_by: str = Query("firma"),
    days: int = Query(30, ge=1, le=3650),
    limit: int = Query(20, ge=1, le=100),
    branch_id: int = Query(-1, ge=-1),
):
    mode = GROUP_MODES.get(group_by)
    if not mode:
        raise HTTPException(status_code=400, detail="Agrupación inválida")
    _, expression = mode
    since = datetime.now() - timedelta(days=days)
    origin, origin_params = origin_filter(branch_id, "e")
    clauses = ["e.fecha_hora >= :since"]
    if origin:
        clauses.append(origin)

    rows = db.execute(text(f"""
        SELECT
            {expression} AS grupo,
            COUNT(*) AS cantidad,
            COUNT(DISTINCT COALESCE(e.id_sucursal_origen, 0)) AS sucursales,
            MIN(e.fecha_hora) AS primero,
            MAX(e.fecha_hora) AS ultimo,
            MAX(e.mensaje) AS mensaje_ejemplo,
            GROUP_CONCAT(DISTINCT COALESCE(s.nombre, 'Casa Central') ORDER BY COALESCE(s.nombre, 'Casa Central') SEPARATOR ', ') AS origenes
        FROM `{TABLE}` e
        LEFT JOIN `{settings.branches_table}` s ON s.id_sucursal = e.id_sucursal_origen
        WHERE {' AND '.join(clauses)}
        GROUP BY {expression}
        HAVING COUNT(*) > 1
        ORDER BY cantidad DESC, ultimo DESC
        LIMIT :limit
    """), {"since": since, "limit": limit, **origin_params})
    return {"group_by": group_by, "items": rows_to_dicts(rows), "branch_id": branch_id}


@app.get("/api/dashboard/versions")
def dashboard_versions(db: DbSession, limit: int = Query(15, ge=1, le=100)):
    rows = db.execute(text(f"""
        SELECT version_sistema AS version, COUNT(*) AS cantidad,
               MIN(fecha_hora) AS primero, MAX(fecha_hora) AS ultimo
        FROM `{TABLE}`
        WHERE version_sistema IS NOT NULL AND version_sistema <> ''
        GROUP BY version_sistema ORDER BY ultimo DESC LIMIT :limit
    """), {"limit": limit})
    return {"items": rows_to_dicts(rows)}
