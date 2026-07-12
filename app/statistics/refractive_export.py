"""Export refractive follow-up cohort (Excel / CSV / simple PDF). No PII."""

from __future__ import annotations

import csv
import io
from datetime import datetime
from typing import Any

from openpyxl import Workbook

from app.clinical.astigmatism import ORIENTATION_LABELS
from app.services.refractive import RefractiveResults

_HEADERS = [
    "case_code",
    "eye",
    "surgeon",
    "visit_date",
    "sphere",
    "cylinder",
    "axis",
    "seq",
    "cylinder_magnitude",
    "orientation",
    "j0",
    "j45",
    "seq_stars",
    "astig_stars",
    "overall_stars",
]


def _row_values(row: dict[str, Any]) -> list[Any]:
    orient = row.get("orientation")
    return [
        row.get("case_code"),
        row.get("eye"),
        row.get("surgeon"),
        row.get("visit_date"),
        row.get("sphere"),
        row.get("cylinder"),
        row.get("axis"),
        row.get("seq"),
        row.get("cylinder_magnitude"),
        ORIENTATION_LABELS.get(orient, orient),
        row.get("j0"),
        row.get("j45"),
        row.get("seq_stars"),
        row.get("astig_stars"),
        row.get("overall_stars"),
    ]


def export_refractive_xlsx(results: RefractiveResults) -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.title = "Refractivo"
    ws.append(_HEADERS)
    for row in results.rows:
        ws.append(_row_values(row))

    summary = wb.create_sheet("Resumen")
    summary.append(["metric", "value"])
    summary.append(["n_cases", results.n_cases])
    summary.append(["mean_seq", results.mean_seq])
    summary.append(["mean_cylinder_signed", results.mean_cylinder_signed])
    summary.append(["mean_residual_cyl", results.mean_residual_cyl])
    summary.append(["mean_j0", results.mean_j0])
    summary.append(["mean_j45", results.mean_j45])
    mv = results.mean_vector or {}
    summary.append(["centroid_magnitude", mv.get("magnitude")])
    summary.append(["mean_axis", mv.get("mean_axis")])
    for key, val in (results.orientation_pct or {}).items():
        summary.append([f"orientation_pct_{key}", val])

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def export_refractive_csv(results: RefractiveResults) -> bytes:
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(_HEADERS)
    for row in results.rows:
        writer.writerow(_row_values(row))
    return buf.getvalue().encode("utf-8-sig")


def export_refractive_pdf(results: RefractiveResults) -> bytes:
    """Minimal text PDF without external PDF libraries."""
    lines = [
        "PhacoStats — Resultados refractivos (cilindro negativo)",
        f"Generado: {datetime.utcnow().isoformat(timespec='seconds')}Z",
        f"Casos: {results.n_cases}",
        f"SEQ media: {results.mean_seq}",
        f"Cilindro medio (firmado): {results.mean_cylinder_signed}",
        f"|Cyl| medio: {results.mean_residual_cyl}",
        f"J0 medio: {results.mean_j0}",
        f"J45 medio: {results.mean_j45}",
        f"Centroide |C|: {(results.mean_vector or {}).get('magnitude')}",
        f"Eje medio (vector): {(results.mean_vector or {}).get('mean_axis')}",
        "Orientacion %: "
        + ", ".join(f"{k}={v}" for k, v in (results.orientation_pct or {}).items()),
        "",
        "case | sph | cyl | axis | SEQ | |C| | orient | J0 | J45 | stars",
    ]
    for row in results.rows[:200]:
        lines.append(
            f"{row.get('case_code')} | {row.get('sphere')} | {row.get('cylinder')} | "
            f"{row.get('axis')} | {row.get('seq')} | {row.get('cylinder_magnitude')} | "
            f"{row.get('orientation')} | {row.get('j0')} | {row.get('j45')} | "
            f"{row.get('overall_stars')}"
        )
    if len(results.rows) > 200:
        lines.append(f"... ({len(results.rows) - 200} filas adicionales omitidas en PDF)")

    content = "\n".join(lines)
    # Escape PDF special chars
    safe = content.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
    # Simple one-page-ish multi-line text object
    stream = f"BT /F1 9 Tf 40 800 Td 12 TL ({safe.replace(chr(10), ') Tj T* (')}) Tj ET"
    objects = []
    objects.append("1 0 obj<< /Type /Catalog /Pages 2 0 R >>endobj\n")
    objects.append("2 0 obj<< /Type /Pages /Kids [3 0 R] /Count 1 >>endobj\n")
    objects.append(
        "3 0 obj<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
        "/Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>endobj\n"
    )
    stream_bytes = stream.encode("latin-1", errors="replace")
    objects.append(
        f"4 0 obj<< /Length {len(stream_bytes)} >>stream\n".encode()
        + stream_bytes
        + b"\nendstream\nendobj\n"
    )
    objects.append(b"5 0 obj<< /Type /Font /Subtype /Type1 /BaseFont /Courier >>endobj\n")

    out = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for obj in objects:
        offsets.append(len(out))
        if isinstance(obj, str):
            out.extend(obj.encode("latin-1", errors="replace"))
        else:
            out.extend(obj)
    xref_pos = len(out)
    out.extend(f"xref\n0 {len(offsets)}\n".encode())
    out.extend(b"0000000000 65535 f \n")
    for off in offsets[1:]:
        out.extend(f"{off:010d} 00000 n \n".encode())
    out.extend(
        f"trailer<< /Size {len(offsets)} /Root 1 0 R >>\nstartxref\n{xref_pos}\n%%EOF\n".encode()
    )
    return bytes(out)
