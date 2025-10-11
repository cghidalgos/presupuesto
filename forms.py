from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, SubmitField, FloatField, SelectField, IntegerField
from wtforms.validators import DataRequired, Email, NumberRange


class LoginForm(FlaskForm):
    email = StringField('Email', validators=[DataRequired(), Email()])
    password = PasswordField('Password', validators=[DataRequired()])
    submit = SubmitField('Ingresar')


class RegisterForm(FlaskForm):
    name = StringField('Nombre', validators=[DataRequired()])
    email = StringField('Email', validators=[DataRequired(), Email()])
    password = PasswordField('Password', validators=[DataRequired()])
    aporte = FloatField('Aporte (porcentaje, ej. 0.67)', validators=[DataRequired(), NumberRange(min=0, max=1)])
    submit = SubmitField('Registrar')


class AreaForm(FlaskForm):
    nombre = StringField('Nombre área', validators=[DataRequired()])
    submit = SubmitField('Guardar área')


class ConceptoForm(FlaskForm):
    nombre = StringField('Nombre concepto', validators=[DataRequired()])
    valor_presupuestado = FloatField('Valor presupuestado', validators=[DataRequired()])
    area_id = SelectField('Área', coerce=int)
    submit = SubmitField('Guardar concepto')


class GastoForm(FlaskForm):
    concepto_id = SelectField('Concepto', coerce=int)
    monto = FloatField('Monto', validators=[DataRequired()])
    submit = SubmitField('Registrar gasto')