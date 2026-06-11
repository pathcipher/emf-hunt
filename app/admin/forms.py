import json

from flask_wtf import FlaskForm
from wtforms import (
    BooleanField,
    FileField,
    IntegerField,
    MultipleFileField,
    StringField,
    SubmitField,
    TextAreaField,
)
from wtforms.validators import DataRequired, Length, NumberRange, Optional, ValidationError


def _validate_answer_json(form, field):
    """Validate that the answer field is valid JSON (list or single string)."""
    value = field.data.strip()
    if not value:
        raise ValidationError("Answer is required.")

    try:
        parsed = json.loads(value)
        # Accept either a list of strings or a single string
        if isinstance(parsed, list):
            if not all(isinstance(ans, str) for ans in parsed):
                raise ValidationError("All answers must be strings.")
            if not parsed:
                raise ValidationError("Answer list cannot be empty.")
        elif not isinstance(parsed, str):
            raise ValidationError("Answer must be a JSON string or list of strings.")
    except json.JSONDecodeError:
        # If it's not valid JSON, treat it as a single string answer (backward compat)
        if not isinstance(value, str) or not value:
            raise ValidationError("Answer must be a valid string or JSON list.")


class PuzzleForm(FlaskForm):
    order_index = IntegerField(
        "Order", validators=[DataRequired(), NumberRange(min=1)]
    )
    title = StringField("Title", validators=[DataRequired(), Length(max=160)])
    # Trusted, admin-authored HTML/JS — intentionally not sanitized.
    content_html = TextAreaField(
        "Puzzle HTML", validators=[Optional(), Length(max=100000)]
    )
    handler_url = StringField(
        "Handler URL (optional)",
        validators=[Optional(), Length(max=500)],
        render_kw={
            "placeholder": "https://puzzles.internal/api/puzzle/time-based"
        },
    )
    answer = TextAreaField(
        "Answer(s)",
        validators=[DataRequired(), _validate_answer_json],
        render_kw={
            "rows": "4",
            "placeholder": '["hello", "hi", "hey"]\nor\n"hello"',
        },
    )
    is_published = BooleanField("Published")
    submit = SubmitField("Save puzzle")


class MediaUploadForm(FlaskForm):
    # Per-file validation (extension allowlist) happens in the route via
    # app.media.save_puzzle_media; this form just carries the files + CSRF token.
    files = MultipleFileField("Images")
    submit = SubmitField("Upload images")


class SuccessPageForm(FlaskForm):
    # Trusted, admin-authored HTML for the "you finished" page. Leave blank to
    # fall back to the built-in default. Supports a {{team_name}} placeholder.
    content_html = TextAreaField(
        "Success page HTML", validators=[Optional(), Length(max=100000)]
    )
    submit = SubmitField("Save success page")


class BrandingUploadForm(FlaskForm):
    # Extension validation happens in the route via app.branding.save_branding.
    file = FileField("File")
    submit = SubmitField("Upload")
