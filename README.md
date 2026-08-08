# FASA Error Monitor

Dashboard interno para consultar y analizar los errores registrados por Visual FoxPro en `sys_errores`.

## Stack

- FastAPI + SQLAlchemy
- Vue 3 + Vite + Chart.js
- Docker Compose
- Nginx dentro del contenedor web
- Nginx del servidor como reverse proxy
- MySQL existente de FASA con usuario de solo lectura
- SQLite local persistente para cachear errores sincronizados desde sucursales

## Puesta en marcha

1. Clonar el repositorio.
2. Copiar `.env.example` a `.env`.
3. Completar `.env` con la conexión central y las credenciales de lectura de las sucursales.
4. Ejecutar:

```bash
docker compose up -d --build
```

5. El stack queda escuchando solo en `127.0.0.1:8088` del servidor.
6. Configurar el Nginx del host usando `deploy/nginx-host.conf.example`.

Verificación:

```bash
curl http://127.0.0.1:8088/api/health
```

## Usuario MySQL central

El dashboard necesita leer `sys_errores` y `sucursales`:

```sql
CREATE USER 'error_dashboard'@'IP_DEL_SERVIDOR_DASHBOARD'
IDENTIFIED BY 'UNA_CLAVE_SEGURA';

GRANT SELECT ON fasa.sys_errores
TO 'error_dashboard'@'IP_DEL_SERVIDOR_DASHBOARD';

GRANT SELECT ON fasa.sucursales
TO 'error_dashboard'@'IP_DEL_SERVIDOR_DASHBOARD';

FLUSH PRIVILEGES;
```

No necesita `INSERT`, `UPDATE` ni `DELETE` sobre el MySQL central.

## Sincronización manual de sucursales

Las sucursales activas se leen desde la tabla central `sucursales`. Se utilizan:

- `id_sucursal`
- `nombre`
- `servidor`
- `puerto`
- `Activo`

El host y puerto se obtienen automáticamente de esa tabla. Usuario, contraseña y base remota se configuran en `.env`:

```env
REMOTE_DB_NAME=fasa
REMOTE_DB_USER=error_dashboard
REMOTE_DB_PASSWORD=clave_remota
REMOTE_ERROR_TABLE=sys_errores
REMOTE_CONNECT_TIMEOUT=8
SYNC_BATCH_SIZE=1000
```

El usuario remoto debe tener únicamente:

```sql
GRANT SELECT ON fasa.sys_errores
TO 'error_dashboard'@'IP_DEL_SERVIDOR_DASHBOARD';
```

En el dashboard aparece un selector de sucursal. Al elegir una sucursal remota aparece el botón **Sincronizar ahora**.

La sincronización:

1. consulta el último `id_error` ya importado para esa sucursal;
2. trae solamente errores posteriores;
3. procesa todos los lotes pendientes en una sola ejecución;
4. guarda los errores remotos en `/data/sync.db` dentro de un volumen Docker persistente;
5. nunca escribe en el MySQL de la sucursal ni en el MySQL central;
6. permite consultar los errores sincronizados aunque la sucursal luego quede desconectada.

El volumen persistente está definido en `docker-compose.yml` como `error_sync_data`.

## Configuración principal

```env
APP_PORT=8088

DB_HOST=192.168.0.10
DB_PORT=3306
DB_NAME=fasa
DB_USER=error_dashboard
DB_PASSWORD=clave_central
DB_CHARSET=utf8mb4

ERROR_TABLE=sys_errores
ERROR_ID_COLUMN=id_error
BRANCHES_TABLE=sucursales

REMOTE_DB_NAME=fasa
REMOTE_DB_USER=error_dashboard
REMOTE_DB_PASSWORD=clave_remota
REMOTE_DB_CHARSET=utf8mb4
REMOTE_ERROR_TABLE=sys_errores

SYNC_DB_PATH=/data/sync.db
```

Todas las credenciales se cargan desde `.env`. `.env` está ignorado por Git y no debe versionarse.

## Endpoints

- `GET /api/health`
- `GET /api/errors`
- `GET /api/errors/{id}`
- `GET /api/dashboard/summary`
- `GET /api/dashboard/timeline`
- `GET /api/dashboard/top?field=nro_error`
- `GET /api/dashboard/versions`
- `GET /api/branches`
- `POST /api/sync/{id_sucursal}`
- `GET /api/branches/{id_sucursal}/errors`

FastAPI expone documentación en `/api/docs`.

## Diagnóstico

```bash
docker compose logs -f api
docker compose logs -f web
```

Para reconstruir después de un `git pull`:

```bash
docker compose up -d --build
```
