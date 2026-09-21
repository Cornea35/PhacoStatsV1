"""Center branding helpers and contrast-safe theme tokens."""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.models import Center, CenterBranding


def _hex_to_rgb(color: str) -> tuple[int, int, int]:
    c = color.lstrip("#")
    if len(c) == 3:
        c = "".join(ch * 2 for ch in c)
    return int(c[0:2], 16), int(c[2:4], 16), int(c[4:6], 16)


def relative_luminance(color: str) -> float:
    r, g, b = _hex_to_rgb(color)

    def chan(v: int) -> float:
        x = v / 255.0
        return x / 12.92 if x <= 0.03928 else ((x + 0.055) / 1.055) ** 2.4

    return 0.2126 * chan(r) + 0.7152 * chan(g) + 0.0722 * chan(b)


def contrast_ratio(c1: str, c2: str) -> float:
    l1, l2 = relative_luminance(c1), relative_luminance(c2)
    lighter, darker = max(l1, l2), min(l1, l2)
    return (lighter + 0.05) / (darker + 0.05)


def accessible_text_on(bg: str) -> str:
    """Pick black/white text for WCAG-ish contrast on bg."""
    white = contrast_ratio(bg, "#ffffff")
    black = contrast_ratio(bg, "#111111")
    return "#ffffff" if white >= black else "#111111"


@dataclass
class BrandTheme:
    center_id: int | None
    code: str
    short_name: str
    full_name: str
    primary: str
    secondary: str
    accent: str
    text: str
    on_primary: str
    logo_url: str | None
    logo_dark_url: str | None
    cover_url: str | None
    placeholder: str | None
    show_powered_by: bool
    report_header: str | None

    def css_variables(self) -> str:
        return (
            f"--brand-primary:{self.primary};"
            f"--brand-secondary:{self.secondary};"
            f"--brand-accent:{self.accent};"
            f"--brand-text:{self.text};"
            f"--brand-on-primary:{self.on_primary};"
            f"--codet-blue:{self.primary};"
            f"--codet-blue-dark:{self.secondary};"
        )


DEFAULT_THEME = BrandTheme(
    center_id=None,
    code="PHACO",
    short_name="PhacoStats",
    full_name="PhacoStats",
    primary="#0b5ea8",
    secondary="#084a86",
    accent="#5aa6e8",
    text="#1a1a1a",
    on_primary="#ffffff",
    logo_url=None,
    logo_dark_url=None,
    cover_url=None,
    placeholder=None,
    show_powered_by=True,
    report_header=None,
)


def theme_from_branding(center: Center | None, branding: CenterBranding | None) -> BrandTheme:
    if center is None:
        return DEFAULT_THEME
    b = branding or center.branding
    if b is None:
        return BrandTheme(
            center_id=center.id,
            code=center.code,
            short_name=center.short_name,
            full_name=center.full_name,
            primary="#0b5ea8",
            secondary="#084a86",
            accent="#c9a227",
            text="#1a1a1a",
            on_primary="#ffffff",
            logo_url=None,
            logo_dark_url=None,
            cover_url=None,
            placeholder=center.short_name,
            show_powered_by=True,
            report_header=None,
        )
    primary = b.primary_color or "#0b5ea8"
    return BrandTheme(
        center_id=center.id,
        code=center.code,
        short_name=b.short_name or center.short_name,
        full_name=b.full_name or center.full_name,
        primary=primary,
        secondary=b.secondary_color or "#084a86",
        accent=b.accent_color or "#c9a227",
        text=b.text_color or "#1a1a1a",
        on_primary=accessible_text_on(primary),
        logo_url=f"/static/uploads/{b.logo_path}" if b.logo_path else None,
        logo_dark_url=f"/static/uploads/{b.logo_dark_path}" if b.logo_dark_path else None,
        cover_url=f"/static/uploads/{b.cover_image_path}" if b.cover_image_path else None,
        placeholder=b.placeholder_label,
        show_powered_by=bool(b.show_powered_by),
        report_header=b.report_header_text,
    )


def get_theme_for_center(db: Session, center_id: int | None) -> BrandTheme:
    if not center_id:
        return DEFAULT_THEME
    center = db.get(Center, center_id)
    return theme_from_branding(center, center.branding if center else None)


def get_theme_for_code(db: Session, code: str | None) -> BrandTheme:
    if not code:
        return DEFAULT_THEME
    center = db.query(Center).filter(Center.code == code, Center.is_active.is_(True)).first()
    return theme_from_branding(center, center.branding if center else None)


def list_active_centers(db: Session) -> list[Center]:
    return db.query(Center).filter(Center.is_active.is_(True)).order_by(Center.short_name).all()
