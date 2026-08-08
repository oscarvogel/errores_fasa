from datetime import datetime
from urllib.parse import quote_plus

from sqlalchemy import create_engine, text
from sqlalchemy.exc import SQLAlchemyError

from .config import get_settings

settings = get_settings()

SYNC_FIELDS = [
    "fecha_hora", "nro_error", "metodo", "linea", "objeto", "nom_error", "mensaje",
    "usuario", "maquina", "call_stack", "sys_info", "info_extra", "imagen", "estado",
    "resuelto_por", "fecha_resol", "solucion", "formulario", "control", "clase_formulario",
    "clase_control", "alias_actual", "recno", "datasession", "usuario_windows",
    "version_sistema", "version_vfp", "error_externo", "sql_state", "codigo_fuente",
    "tablas_abiertas",
]


def _remote_url(host: str, port: int) -> str:
    user = quote_plus(settings.remote_db_user)
    password = quote_plus(settings.remote_db_password)
    return (
        f"mysql+pymysql://{user}:{password}@{host}:{port}/"
        f"{settings.remote_db_name}?charset={settings.remote_db_charset}"
    )


def _local_writer_engine():
    return create_engine(
        settings.sync_database_url,
        pool_pre_ping=True,
        pool_recycle=300,
    )


def get_branch_sync_status(branch_id: int) -> dict:
    engine = _local_writer_engine()
    try:
        with engine.connect() as conn:
            row = conn.execute(
                text(
                    f"""
                    SELECT
                        COALESCE(MAX(id_error_origen), 0) AS last_remote_id,
                        MAX(fecha_sincronizacion) AS last_success_at,
                        COUNT(*) AS total_imported
                    FROM `{settings.error_table}`
                    WHERE id_sucursal_origen = :branch_id
                      AND sincronizado = 1
                    """
                ),
                {"branch_id": branch_id},
            ).mappings().first()
            return dict(row) if row else {
                "last_remote_id": 0,
                "last_success_at": None,
                "total_imported": 0,
            }
    finally:
        engine.dispose()


def sync_branch(branch: dict) -> dict:
    branch_id = int(branch["id_sucursal"])
    branch_name = str(branch["nombre"]).strip()
    host = str(branch["servidor"]).strip()
    port = int(branch.get("puerto") or 3306)

    if not host:
        raise ValueError(f"La sucursal {branch_name} no tiene servidor configurado")

    local_engine = _local_writer_engine()
    remote_engine = create_engine(
        _remote_url(host, port),
        pool_pre_ping=True,
        pool_recycle=300,
        connect_args={"connect_timeout": settings.remote_connect_timeout},
    )

    imported_total = 0
    fetched_total = 0

    try:
        with local_engine.connect() as local_conn:
            last_id = int(
                local_conn.execute(
                    text(
                        f"SELECT COALESCE(MAX(id_error_origen), 0) "
                        f"FROM `{settings.error_table}` "
                        "WHERE id_sucursal_origen = :branch_id AND sincronizado = 1"
                    ),
                    {"branch_id": branch_id},
                ).scalar_one()
            )

        previous_last_id = last_id

        while True:
            with remote_engine.connect() as remote_conn:
                rows = remote_conn.execute(
                    text(
                        f"SELECT * FROM `{settings.remote_error_table}` "
                        "WHERE id_error > :last_id ORDER BY id_error ASC LIMIT :batch_size"
                    ),
                    {"last_id": last_id, "batch_size": settings.sync_batch_size},
                ).mappings().all()

            if not rows:
                break

            fetched_total += len(rows)
            now = datetime.now()

            insert_columns = SYNC_FIELDS + [
                "sincronizado",
                "id_sucursal_origen",
                "id_error_origen",
                "fecha_sincronizacion",
            ]
            column_sql = ", ".join(f"`{name}`" for name in insert_columns)
            value_sql = ", ".join(f":{name}" for name in insert_columns)
            insert_sql = text(
                f"INSERT IGNORE INTO `{settings.error_table}` ({column_sql}) VALUES ({value_sql})"
            )

            payloads = []
            for remote_row in rows:
                row = dict(remote_row)
                payload = {field: row.get(field) for field in SYNC_FIELDS}
                payload.update(
                    {
                        "sincronizado": 1,
                        "id_sucursal_origen": branch_id,
                        "id_error_origen": int(row["id_error"]),
                        "fecha_sincronizacion": now,
                    }
                )
                payloads.append(payload)

            with local_engine.begin() as local_conn:
                result = local_conn.execute(insert_sql, payloads)
                imported_total += result.rowcount or 0

            last_id = max(int(row["id_error"]) for row in rows)

            if len(rows) < settings.sync_batch_size:
                break

        return {
            "status": "ok",
            "branch_id": branch_id,
            "branch": branch_name,
            "imported": imported_total,
            "fetched": fetched_total,
            "previous_last_remote_id": previous_last_id,
            "last_remote_id": last_id,
            "synced_at": datetime.now().isoformat(timespec="seconds"),
        }

    except (SQLAlchemyError, OSError, ValueError):
        raise
    finally:
        remote_engine.dispose()
        local_engine.dispose()
