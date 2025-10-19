from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from datetime import datetime


db = SQLAlchemy()


class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=False) # simple: store plaintext? in real app hash it
    aporte = db.Column(db.Float, default=0.5) # porcentaje (0-1)
    gastos = db.relationship('Gasto', backref='user', lazy=True)


class Area(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(120), nullable=False)
    conceptos = db.relationship('Concepto', backref='area', lazy=True)


class Concepto(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(120), nullable=False)
    valor_presupuestado = db.Column(db.Float, default=0.0)
    area_id = db.Column(db.Integer, db.ForeignKey('area.id'), nullable=False)
    gastos = db.relationship('Gasto', backref='concepto', lazy=True)

    @property
    def total_gastado(self):
        return sum(g.monto for g in self.gastos)

    @property
    def restante(self):
        return max(self.valor_presupuestado - self.total_gastado, 0)


class Gasto(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    concepto_id = db.Column(db.Integer, db.ForeignKey('concepto.id'), nullable=False)
    usuario_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    monto = db.Column(db.Float, nullable=False)
    fecha = db.Column(db.DateTime, default=datetime.utcnow)