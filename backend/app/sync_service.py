from urllib.parse import quote_plus

from sqlalchemy import create_engine, text
from sqlalchemy.exc import SQLAlchemyError

from .config import get_settings
from .sync_store import (
    get_last_remote_id,
    mark_sync_error,
    mark_sync_success,
    save_remote_errors,
)

settings = get_settings()


def _remote_url(host: str, port: int) -> str:
    user = quote_plus(settings.remote_db_user)
    password = quote_plus(settings.remote_db_password)
    return (
        f"mysql+pymysql://{user}:{password}@{host}:{port}/"
        f"{settings.remote_db_name}?charset={settings.remote_db_charset}"
    )


def sync_branch(branch: dict) -> dict:
    branch_id = int(branch["id_sucursal"])
    branch_name = str(branch["nombre"]).strip()
    host = str(branch["servidor"]).strip()
    port = int(branch.get("puerto") or 3306)

    if not host:
        raise ValueError(f"La sucursal {branch_name} no tiene servidor configurado")

    last_remote_id = get_last_remote_id(branch_id)
    initial_last_id = last_remote_id
    total_fetched = 0
    total_imported = 0

    engine = create_engine(
        _remote_url(host, port),
        pool_pre_ping=True,
        pool_recycle=300,
        connect_args={"connect_timeout": settings.remote_connect_timeout},
    )

    try:
        with engine.connect() as conn:
            while True:
                rows = conn.execute(
                    text(
                        f"SELECT * FROM `{settings.remote_error_table}` "
                        "WHERE id_error > :last_id ORDER BY id_error ASC LIMIT :batch_size"
                    ),
                    {"last_id": last_remote_id, "batch_size": settings.sync_batch_size},
                ).mappings().all()

                if not rows:
                    break

                data = [dict(row) for row in rows]
                total_fetched += len(data)
                total_imported += save_remote_errors(branch_id, branch_name, data)
                last_remote_id = max(int(row["id_error"]) for row in data)

                if len(data) < settings.sync_batch_size:
                    break

        mark_sync_success(branch_id, branch_name, last_remote_id, total_imported)
        return {
            "status": "ok",
            "branch_id": branch_id,
            "branch": branch_name,
            "imported": total_imported,
            "fetched": total_fetched,
            "previous_last_remote_id": initial_last_id,
            "last_remote_id": last_remote_id,
        }
    except (SQLAlchemyError, OSError, ValueError) as exc:
        mark_sync_error(branch_id, branch_name, str(exc))
        raise
    finally:
        engine.dispose()
