"""Admin-editable site settings (key/value), e.g. the customisable success page.

Values are authored by admins and may contain trusted HTML — rendered with
``|safe`` like puzzle content, within the same trust boundary.
"""
from __future__ import annotations

from .extensions import db
from .models import Setting

# Setting keys.
SUCCESS_HTML = "success_html"
PARALLEL_MODE_KEY = "parallel_mode"  # "true" / "false"; unset -> fall back to config
ANNOUNCEMENT_HTML = "announcement_html"  # site-wide banner; empty -> hidden

# Shown when no custom success page has been set.
DEFAULT_SUCCESS_HTML = (
    "<h1>🚀 You did it!</h1>"
    "<p>Your team has solved every puzzle in the hunt. Stellar work.</p>"
)


def get_setting(key: str, default: str = "") -> str:
    row = db.session.get(Setting, key)
    return row.value if row is not None else default


def set_setting(key: str, value: str) -> None:
    row = db.session.get(Setting, key)
    if row is None:
        row = Setting(key=key, value=value or "")
        db.session.add(row)
    else:
        row.value = value or ""
    db.session.commit()
