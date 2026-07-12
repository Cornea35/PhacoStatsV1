#!/usr/bin/env python3
"""Migrate follow-ups stored in plus-cylinder notation to minus-cylinder.

Conversion:
  new_sphere   = sphere + cylinder
  new_cylinder = -cylinder
  new_axis     = axis + 90; if > 180 subtract 180

Then recalculate SEQ, orientation, stars (via evaluate_refraction).

Usage:
  .\\.venv\\Scripts\\python.exe migrate_positive_cylinder.py
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.clinical.astigmatism import plus_to_minus_cylinder
from app.clinical.refractive import evaluate_refraction
from app.database import SessionLocal
from app.main import _ensure_schema
from app.models import FollowUp


def migrate(db) -> dict[str, int]:
    rows = db.query(FollowUp).filter(FollowUp.cylinder > 0).all()
    converted = 0
    for fu in rows:
        sph, cyl, axis = plus_to_minus_cylinder(fu.sphere, fu.cylinder, fu.axis)
        result = evaluate_refraction(sph, cyl, axis)
        fu.sphere = sph
        fu.cylinder = cyl
        fu.axis = axis
        fu.spherical_equivalent = result.spherical_equivalent
        fu.residual_astigmatism = result.residual_astigmatism
        fu.astigmatism_orientation = result.astigmatism_orientation
        fu.spherical_equivalent_stars = result.spherical_equivalent_stars
        fu.astigmatism_stars = result.astigmatism_stars
        fu.overall_refractive_stars = result.overall_refractive_stars
        converted += 1

    # Also recompute orientation/stars for already-negative rows if orientation
    # was stored under the OLD WTR/ATR definition (reclassify all active).
    reclassified = 0
    for fu in db.query(FollowUp).filter(FollowUp.cylinder <= 0).all():
        result = evaluate_refraction(fu.sphere, fu.cylinder, fu.axis)
        changed = (
            fu.astigmatism_orientation != result.astigmatism_orientation
            or fu.spherical_equivalent != result.spherical_equivalent
            or fu.astigmatism_stars != result.astigmatism_stars
            or fu.spherical_equivalent_stars != result.spherical_equivalent_stars
            or fu.overall_refractive_stars != result.overall_refractive_stars
            or fu.residual_astigmatism != result.residual_astigmatism
        )
        if changed:
            fu.spherical_equivalent = result.spherical_equivalent
            fu.residual_astigmatism = result.residual_astigmatism
            fu.astigmatism_orientation = result.astigmatism_orientation
            fu.spherical_equivalent_stars = result.spherical_equivalent_stars
            fu.astigmatism_stars = result.astigmatism_stars
            fu.overall_refractive_stars = result.overall_refractive_stars
            reclassified += 1

    db.commit()
    return {"converted_plus": converted, "reclassified": reclassified}


def main() -> None:
    t0 = time.perf_counter()
    _ensure_schema()
    db = SessionLocal()
    try:
        stats = migrate(db)
        print("Migracion cilindro positivo -> negativo")
        print(f"  Convertidos (+cyl): {stats['converted_plus']}")
        print(f"  Reclasificados:     {stats['reclassified']}")
        print(f"  Tiempo: {time.perf_counter() - t0:.2f} s")
    finally:
        db.close()


if __name__ == "__main__":
    main()
