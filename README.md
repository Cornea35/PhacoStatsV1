# PhacoStats V1 — CODET Vision Institute

Aplicación web para registrar **facoemulsificaciones anónimas**, complicaciones, seguimientos refractivos y reintervenciones en el **CODET Vision Institute**.

> **Importante:** no almacene datos identificables de pacientes. Use solo códigos anónimos (p. ej. `CASE-0001`).

Esta es la **versión de publicación V1**: arranca **sin cirugías**. Solo se crean cuentas iniciales vacías.

## Stack

- Python 3.12+
- FastAPI + Jinja2 + Bootstrap 5
- SQLAlchemy + SQLite (PostgreSQL vía `DATABASE_URL`)
- Chart.js, openpyxl, Pytest

## Instalación

```powershell
cd C:\Users\Fellow\PhacoStatsV1
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env
```

Edite `.env` y cambie `SECRET_KEY` antes de publicar.

## Ejecutar

```powershell
uvicorn app.main:app --host 127.0.0.1 --port 8001
```

Abra http://127.0.0.1:8001

### Cuentas iniciales (cambiar contraseñas)

| Usuario | Contraseña temporal | Rol |
|---------|---------------------|-----|
| `admin` | `admin123` | Administrador |
| `coord` | `coord123` | Coordinadora |
| `cirujano1` | `cirujano123` | Cirujano |

No se generan cirugías, complicaciones ni follow-ups de demostración.

## Roles (resumen)

Matriz en `app/permissions.py`.

- **Administrador:** acceso completo, Analytics, usuarios, exports clínicos.
- **Cirujano:** sus cirugías, métricas propias, refractivo, reintervenciones propias.
- **Coordinadora:** lista operativa, reintervenciones, export limitado; **sin** métricas clínicas comparativas ni refractivo.

> El rol Coordinadora tiene acceso operativo a la lista de cirugías y seguimiento de reintervenciones, pero no tiene acceso a métricas clínicas individuales o comparativas de cirujanos.

## Publicación

1. `SECRET_KEY` fuerte y único en `.env`
2. `DEBUG=false`
3. Preferir PostgreSQL en producción (`DATABASE_URL=postgresql+psycopg://...`)
4. HTTPS / reverse proxy (nginx, Caddy, etc.)
5. Cambiar contraseñas de las cuentas iniciales
6. No subir `.env`, `*.db` ni backups al repositorio

## Tests

```powershell
pytest -q
```

## Licencia / uso

Uso institucional educativo y de calidad clínica. Datos anónimos únicamente.
