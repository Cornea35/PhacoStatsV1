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

## Publicación en Render (recomendado)

El repo ya incluye `render.yaml` (web + PostgreSQL gratis).

1. Entra en [https://render.com](https://render.com) e inicia sesión con GitHub (`Cornea35`).
2. **New → Blueprint** → selecciona el repo **PhacoStatsV1**.
3. Aplica el blueprint (crea `phacostats-v1` + base `phacostats-db`).
4. Espera el primer deploy (unos minutos).
5. Abre la URL tipo `https://phacostats-v1.onrender.com`.
6. Entra con `admin` / `admin123` y **cambia las contraseñas**.

Variables que Render configura solo:

| Variable | Valor |
|----------|--------|
| `DATABASE_URL` | PostgreSQL del blueprint (persistente) |
| `SECRET_KEY` | Generado automáticamente |
| `DEBUG` | `false` |

**Importante:** no uses solo SQLite en Render free: el disco se borra al redesplegar. PostgreSQL del blueprint conserva cirugías y usuarios.

### Checklist de publicación

1. `SECRET_KEY` fuerte (Render lo genera)
2. `DEBUG=false`
3. PostgreSQL (`DATABASE_URL`)
4. HTTPS (incluido en Render)
5. Cambiar contraseñas iniciales
6. No subir `.env` ni `*.db` al repositorio

## Tests

```powershell
pytest -q
```

## Licencia / uso

Uso institucional educativo y de calidad clínica. Datos anónimos únicamente.
