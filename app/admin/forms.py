from flask_wtf import FlaskForm
from wtforms import (
    BooleanField,
    IntegerField,
    StringField,
    SubmitField,
    TextAreaField,
)
from wtforms.validators import DataRequired, Length, NumberRange, Optional


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
    answer = StringField("Answer", validators=[DataRequired(), Length(max=255)])
    is_published = BooleanField("Published")
    submit = SubmitField("Save puzzle")
