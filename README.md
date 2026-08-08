# FASA Error Monitor

Dashboard interno para consultar y analizar los errores registrados por Visual FoxPro en `sys_errores`.

## Stack

- FastAPI + SQLAlchemy
- Vue 3 + Vite + Chart.js
- Docker Compose
- Nginx (contenedor web) detrás del Nginx del servidor
- MySQL existente de FASA (solo lectura)

## Puesta en marcha

1. Clonar el repositorio.
2. Copiar `.env.example` a `.env`.
3. Completar únicamente `.env` con la conexión real a MySQL.
4. Ejecutar:

```bash
docker compose up -d --build
```

5. Abrir `http://IP_SERVIDOR:8088` o configurar el Nginx del host usando `deploy/nginx-host.conf.example`.

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
ERROR_ID_COLUMN=id
APP_PORT=8088
```

Si la clave primaria de `sys_errores` no se llama `id`, cambiar `ERROR_ID_COLUMN` por el nombre real.

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

## Endpoints

- `GET /api/health`
- `GET /api/errors`
- `GET /api/errors/{id}`
- `GET /api/dashboard/summary`
- `GET /api/dashboard/timeline`
- `GET /api/dashboard/top?field=nro_error`

FastAPI también expone documentación en `/api/docs`.

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
