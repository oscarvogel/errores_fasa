# FASA Error Monitor

Dashboard interno para consultar y analizar los errores registrados por Visual FoxPro en `sys_errores`.

## Stack

- FastAPI + SQLAlchemy
- Vue 3 + Vite + Chart.js
- Docker Compose
- Nginx dentro del contenedor web
- Nginx del servidor como reverse proxy
- MySQL existente de FASA

## Puesta en marcha

1. Ejecutar primero la migración `sql/001_sync_sucursales.sql` en la base MySQL de Casa Central.
2. Clonar o actualizar el repositorio.
3. Copiar `.env.example` a `.env`.
4. Completar `.env` con conexión central, usuario de sincronización y credenciales remotas.
5. Ejecutar:

```bash
docker compose up -d --build
```

6. El stack queda escuchando solo en `127.0.0.1:8088` del servidor.

## Cambio de estructura requerido

Los errores sincronizados desde sucursales se insertan directamente en `sys_errores` de Casa Central. El `id_error` local continúa siendo AUTO_INCREMENT; nunca se copia el `id_error` remoto como clave primaria.

La migración agrega:

```sql
ALTER TABLE sys_errores
    ADD COLUMN sincronizado TINYINT(1) NOT NULL DEFAULT 0 AFTER tablas_abiertas,
    ADD COLUMN id_sucursal_origen INT NULL AFTER sincronizado,
    ADD COLUMN id_error_origen INT NULL AFTER id_sucursal_origen,
    ADD COLUMN fecha_sincronizacion DATETIME NULL AFTER id_error_origen,
    ADD UNIQUE KEY uq_error_origen (id_sucursal_origen, id_error_origen),
    ADD KEY idx_sucursal_origen (id_sucursal_origen),
    ADD KEY idx_sincronizado (sincronizado),
    ADD KEY idx_fecha_sincronizacion (fecha_sincronizacion);
```

Semántica:

- error generado en Casa Central: `sincronizado = 0`, origen en `NULL`;
- error importado: `sincronizado = 1`, `id_sucursal_origen` identifica la sucursal y `id_error_origen` conserva el ID original;
- `(id_sucursal_origen, id_error_origen)` es único y evita duplicados;
- `fecha_sincronizacion` indica cuándo se copió al servidor central.

## Usuarios MySQL recomendados

### Dashboard central: solo lectura

```sql
CREATE USER 'error_dashboard'@'IP_DEL_SERVIDOR_DASHBOARD'
IDENTIFIED BY 'UNA_CLAVE_SEGURA';

GRANT SELECT ON fasa.sys_errores TO 'error_dashboard'@'IP_DEL_SERVIDOR_DASHBOARD';
GRANT SELECT ON fasa.sucursales TO 'error_dashboard'@'IP_DEL_SERVIDOR_DASHBOARD';
```

### Sincronizador local: lectura + inserción

```sql
CREATE USER 'error_sync'@'IP_DEL_SERVIDOR_DASHBOARD'
IDENTIFIED BY 'OTRA_CLAVE_SEGURA';

GRANT SELECT, INSERT ON fasa.sys_errores TO 'error_sync'@'IP_DEL_SERVIDOR_DASHBOARD';
```

El sincronizador no necesita `UPDATE`, `DELETE`, `ALTER` ni `DROP`.

### Usuario de cada sucursal: solo lectura

```sql
GRANT SELECT ON fasa.sys_errores
TO 'error_dashboard'@'IP_DEL_SERVIDOR_DASHBOARD';
```

## Sincronización manual de sucursales

Las sucursales activas se leen desde la tabla central `sucursales`, usando `id_sucursal`, `nombre`, `servidor`, `puerto` y `Activo`.

El botón **Sincronizar ahora** realiza:

1. obtiene el mayor `id_error_origen` ya guardado para la sucursal;
2. conecta al MySQL remoto con usuario de solo lectura;
3. trae solamente `sys_errores.id_error > ultimo_id`;
4. inserta cada registro en `sys_errores` central con un nuevo `id_error` local;
5. guarda `sincronizado = 1`, sucursal, ID remoto y fecha de sincronización;
6. usa el índice único para impedir duplicados;
7. no escribe nunca en la base MySQL remota.

## Configuración `.env`

```env
APP_PORT=8088

# Dashboard / lectura central
DB_HOST=192.168.0.10
DB_PORT=3306
DB_NAME=fasa
DB_USER=error_dashboard
DB_PASSWORD=clave_central
DB_CHARSET=utf8mb4

# Escritura controlada de registros sincronizados en Casa Central
SYNC_DB_USER=error_sync
SYNC_DB_PASSWORD=clave_sync

ERROR_TABLE=sys_errores
ERROR_ID_COLUMN=id_error
BRANCHES_TABLE=sucursales

# Lectura de sucursales remotas
REMOTE_DB_NAME=fasa
REMOTE_DB_USER=error_dashboard
REMOTE_DB_PASSWORD=clave_remota
REMOTE_DB_CHARSET=utf8mb4
REMOTE_ERROR_TABLE=sys_errores
REMOTE_CONNECT_TIMEOUT=8
SYNC_BATCH_SIZE=1000

TZ=America/Argentina/Buenos_Aires
```

Todas las credenciales se cargan desde `.env`; `.env` está ignorado por Git y no debe versionarse.

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
