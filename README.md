# PhacoStats V1 — plataforma multicentro

Aplicación web educativa para seguimiento de resultados y complicaciones de cirugía de catarata, con **múltiples centros**, membresías por rol, branding institucional y **Surgical Risk Profile**.

> **Importante:** no almacene datos identificables de pacientes. Use solo códigos anónimos (p. ej. `CASE-0001`).  
> PhacoStats es una herramienta de **mejora de calidad / educación**, no un ranking punitivo ni un sistema autónomo de decisión clínica.

**PhacoStats · Created by Dr. Erik Navas**

## Stack

- Python 3.12+ · FastAPI · Jinja2 · Bootstrap 5
- SQLAlchemy · SQLite / PostgreSQL (`DATABASE_URL`)
- Chart.js · openpyxl · Pytest

## Arquitectura multicentro

- Tablas: `centers`, `center_branding`, `center_memberships`, `supervisor_assignments`, `registration_requests`, `audit_logs`, `risk_model_runs`
- El **rol efectivo** vive en la membresía (`center_memberships`); `users.role` / `users.institution_id` se sincronizan con el centro activo (compatibilidad)
- Consultas operativas y clínicas validan centro (coordinador/center_admin) o permiten alcance global solo a `general_admin`
- Centros sembrados: **CODET** y **Hospital Universitario UANL** (`HU_UANL`, placeholder tipográfico hasta cargar logo oficial)

### Migración

Al arrancar, `_ensure_schema()` + `migrate_users_and_cases_to_centers()`:

1. Crea columnas aditivas (`email`, `account_status`, `center_id`, …)
2. Crea centros CODET y HU_UANL con branding
3. Mapea `admin` → `general_admin`
4. Crea membresías y asocia casos existentes a CODET
5. **No borra** datos clínicos

## Roles (matriz en `app/permissions.py`)

| Rol | Alcance |
|-----|---------|
| `general_admin` | Todos los centros, branding, crear `center_admin`, bitácora, analytics global |
| `center_admin` | Solo su centro; aprueba registros; no crea otros admins |
| `surgeon` | Sus casos + Mis resultados (risk profile) |
| `supervisor` | Cirujanos asignados (misma institución) |
| `coordinator` | Captura operativa de casos / reintervenciones; sin analytics clínica confidencial |

## Instalación

```powershell
cd C:\Users\Fellow\PhacoStatsV1
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env
uvicorn app.main:app --host 127.0.0.1 --port 8001
```

### Cuentas locales de desarrollo (cambiar en producción)

| Usuario | Contraseña | Rol |
|---------|------------|-----|
| `admin` | `admin123` | Administrador general |
| `coord` | `coord123` | Coordinador (CODET) |
| `cirujano1` | `cirujano123` | Cirujano (CODET) |

## Crear centros y administradores

1. Entrar como `general_admin`
2. **Centros** → crear centro / editar branding / subir logo PNG o SVG
3. En cada centro: **Crear administrador de centro** (solo `general_admin`)

## Logo Hospital Universitario UANL

1. Obtener archivo oficial (PNG transparente o SVG)
2. `Centros` → fila UANL → campo **Logo PNG/SVG** → Guardar branding
3. Hasta entonces se muestra el placeholder tipográfico configurado

Archivos se guardan en `app/static/uploads/` (no versionar logos institucionales sensibles si aplica política local).

## Surgical Risk Profile

- Rutas: `/admin/risk-profile`, `/my/risk-profile`
- Modelo MVP: regresión logística con regularización L2 + interacciones clínicas fijas
- Umbrales: mín. casos/eventos; combinaciones insuficientes muestran mensaje explícito
- Entrega observado vs esperado, O/E, factores y recomendaciones **educativas** (no causales)

## Pruebas

```powershell
.\.venv\Scripts\python.exe -m pytest tests/ -q
```

## Publicación (Render)

Ver `render.yaml`. Tras desplegar, cambiar contraseñas y cargar logos oficiales.
