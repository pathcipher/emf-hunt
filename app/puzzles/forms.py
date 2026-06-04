from flask_wtf import FlaskForm
from wtforms import StringField, SubmitField
from wtforms.validators import DataRequired, Length


class AnswerForm(FlaskForm):
    answer = StringField("Answer", validators=[DataRequired(), Length(max=255)])
    submit = SubmitField("Submit answer")
