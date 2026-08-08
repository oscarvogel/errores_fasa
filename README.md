# FASA Error Monitor

Dashboard interno para consultar y analizar los errores registrados por Visual FoxPro en `sys_errores`.

## Stack

- FastAPI + SQLAlchemy
- Vue 3 + Vite + Chart.js
- Docker Compose
- Nginx dentro del contenedor web
- Nginx del servidor como reverse proxy
- MySQL existente de FASA, idealmente con usuario de solo lectura

## Puesta en marcha

1. Clonar el repositorio.
2. Copiar `.env.example` a `.env`.
3. Completar únicamente `.env` con la conexión real a MySQL.
4. Ejecutar:

```bash
docker compose up -d --build
```

5. El stack queda escuchando solo en `127.0.0.1:8088` del servidor, para no exponerlo directamente a la red.
6. Configurar el Nginx del host usando `deploy/nginx-host.conf.example`.

Para verificarlo directamente desde el servidor:

```bash
curl http://127.0.0.1:8088/api/health
```

## Configuración

Todas las credenciales y datos sensibles se leen desde `.env`. El archivo `.env` está ignorado por Git y **no debe versionarse**.

Variables principales:

```env
DB_HOST=192.168.0.10
DB_PORT=3306
DB_NAME=fasa
DB_USER=error_dashboard
DB_PASSWORD=cambiar
ERROR_TABLE=sys_errores
ERROR_ID_COLUMN=id_error
APP_PORT=8088
```

La estructura actual de FASA usa `id_error` como clave primaria de `sys_errores`.

### Usuario MySQL recomendado

Usar un usuario exclusivo de solo lectura:

```sql
CREATE USER 'error_dashboard'@'IP_DEL_SERVIDOR_DASHBOARD'
IDENTIFIED BY 'UNA_CLAVE_SEGURA';

GRANT SELECT
ON fasa.sys_errores
TO 'error_dashboard'@'IP_DEL_SERVIDOR_DASHBOARD';

FLUSH PRIVILEGES;
```

## Tabla soportada

El dashboard está preparado para la tabla actual `sys_errores`, incluyendo los campos de diagnóstico (`call_stack`, `codigo_fuente`, `tablas_abiertas`, `sql_state`, versiones, formulario/control) y también los campos de seguimiento ya existentes: `estado`, `resuelto_por`, `fecha_resol` y `solucion`.

La primera versión del dashboard es de consulta. Para permitir marcar errores como resueltos desde la web habrá que habilitar permisos de escritura específicos y endpoints separados; no se recomienda dar permisos amplios al usuario de lectura.

## Endpoints

- `GET /api/health`
- `GET /api/errors`
- `GET /api/errors/{id}`
- `GET /api/dashboard/summary`
- `GET /api/dashboard/timeline`
- `GET /api/dashboard/top?field=nro_error`
- `GET /api/dashboard/versions`

FastAPI expone documentación en `/api/docs`.

## Filtros de errores

`GET /api/errors` acepta:

- `page`
- `page_size`
- `desde`
- `hasta`
- `nro_error`
- `metodo`
- `formulario`
- `usuario`
- `maquina`
- `version`
- `q` para búsqueda general

Ejemplo:

```text
/api/errors?desde=2026-08-01&version=3.0.292&q=btnsalir
```

## Diagnóstico inicial

Después del primer arranque ejecutar:

```bash
curl http://127.0.0.1:8088/api/health
```

Además de comprobar MySQL, devuelve las columnas detectadas y confirma si `ERROR_ID_COLUMN` existe.

Ver logs:

```bash
docker compose logs -f api
docker compose logs -f web
```

## Desarrollo local

Backend:

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Frontend:

```bash
cd frontend
npm install
npm run dev
```

Vite reenvía `/api` a `http://127.0.0.1:8000` durante desarrollo.
