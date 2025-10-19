from datetime import datetime, date
from app import app
from models import db, User, Area, Concepto, Gasto, PresupuestoMensual

# Helper to get or create

def get_or_create_user(name: str, email: str, password: str = "password", aporte: float = 0.5):
    u = User.query.filter_by(email=email).first()
    if not u:
        u = User(name=name, email=email, password=password, aporte=aporte)
        db.session.add(u)
        db.session.commit()
    return u


def get_or_create_area(nombre: str):
    a = Area.query.filter_by(nombre=nombre).first()
    if not a:
        a = Area(nombre=nombre)
        db.session.add(a)
        db.session.commit()
    return a


def get_or_create_concepto(nombre: str, area: Area):
    c = Concepto.query.filter_by(nombre=nombre, area_id=area.id).first()
    if not c:
        c = Concepto(nombre=nombre, area_id=area.id, valor_presupuestado=0)
        db.session.add(c)
        db.session.commit()
    return c


def upsert_presupuesto(concepto_id: int, year: int, month: int, valor: float):
    pm = PresupuestoMensual.query.filter_by(concepto_id=concepto_id, year=year, month=month).first()
    if not pm:
        pm = PresupuestoMensual(concepto_id=concepto_id, year=year, month=month, valor_presupuestado=valor)
        db.session.add(pm)
    else:
        pm.valor_presupuestado = valor
    db.session.commit()


def ensure_gasto_mes(concepto_id: int, usuario_id: int, year: int, month: int, monto: float):
    # check if there's already any gasto for this concepto in this month
    first_day = date(year, month, 1)
    if month == 12:
        next_month_first = date(year + 1, 1, 1)
    else:
        next_month_first = date(year, month + 1, 1)
    exists = (
        db.session.query(Gasto)
        .filter(
            Gasto.concepto_id == concepto_id,
            Gasto.fecha >= datetime.combine(first_day, datetime.min.time()),
            Gasto.fecha < datetime.combine(next_month_first, datetime.min.time()),
        )
        .first()
        is not None
    )
    if not exists:
        # Put the gasto on the 15th of the month at noon
        day = 15
        gasto_fecha = datetime(year, month, min(day, 28), 12, 0, 0)
        g = Gasto(concepto_id=concepto_id, usuario_id=usuario_id, monto=monto, fecha=gasto_fecha)
        db.session.add(g)
        db.session.commit()


DATA = {
    2025: {
        8: {  # Agosto
            "Agua": {"pres": 108000, "gastado": 95200},
            "Energia": {"pres": 135000, "gastado": 126000},
            "Gas": {"pres": 16000, "gastado": 15600},
            "Internet": {"pres": 89900, "gastado": 72500},
            "Administración": {"pres": 284300, "gastado": 313000},
        },
        9: {  # Septiembre
            "Agua": {"pres": 108000, "gastado": 166000},
            "Energia": {"pres": 135000, "gastado": 156300},
            "Gas": {"pres": 16000, "gastado": 16000},
            "Internet": {"pres": 89900, "gastado": 95500},
            "Administración": {"pres": 313000, "gastado": 255600},
        },
        10: {  # Octubre
            "Agua": {"pres": 160000, "gastado": 135860},
            "Energia": {"pres": 145000, "gastado": 138321},
            "Gas": {"pres": 16000, "gastado": 15626},
            "Internet": {"pres": 95500, "gastado": 95500},
            "Administración": {"pres": 256000, "gastado": 284300},
        },
    }
}


if __name__ == "__main__":
    with app.app_context():
        # Ensure base entities
        area = get_or_create_area("Servicios")
        user = get_or_create_user(name="Seed User", email="seed@example.com", password="seed123", aporte=0.5)

        for year, months in DATA.items():
            for month, conceptos in months.items():
                for nombre, vals in conceptos.items():
                    concepto = get_or_create_concepto(nombre, area)
                    upsert_presupuesto(concepto.id, year, month, float(vals["pres"]))
                    ensure_gasto_mes(concepto.id, user.id, year, month, float(vals["gastado"]))
        print("Datos de agosto, septiembre y octubre insertados/actualizados correctamente.")
