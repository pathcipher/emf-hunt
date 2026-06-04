from flask_wtf import FlaskForm
from wtforms import StringField, SubmitField
from wtforms.validators import DataRequired, Length


class CreateTeamForm(FlaskForm):
    name = StringField("Team name", validators=[DataRequired(), Length(min=2, max=80)])
    submit = SubmitField("Create team")


class JoinTeamForm(FlaskForm):
    join_code = StringField(
        "Join code", validators=[DataRequired(), Length(min=4, max=12)]
    )
    submit = SubmitField("Join team")
