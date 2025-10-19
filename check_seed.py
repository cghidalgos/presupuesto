from app import app
from models import db, Concepto, PresupuestoMensual, Gasto
from datetime import date

if __name__ == '__main__':
    with app.app_context():
        conceptos = [c.nombre for c in Concepto.query.order_by(Concepto.nombre).all()]
        print('Conceptos:', conceptos)
        for month in (8,9,10):
            pms = PresupuestoMensual.query.filter_by(year=2025, month=month).all()
            total_pres = sum(pm.valor_presupuestado for pm in pms)
            print(f"2025-{month:02d} presupuestos: {len(pms)} conceptos, total={total_pres}")
        for nombre in ("Agua","Energia","Gas","Internet","Administración"):
            c = Concepto.query.filter_by(nombre=nombre).first()
            if not c:
                print(f"Concepto faltante: {nombre}")
                continue
            for m in (8,9,10):
                pm = PresupuestoMensual.query.filter_by(concepto_id=c.id, year=2025, month=m).first()
                gastado = sum(g.monto for g in c.gastos if g.fecha.year==2025 and g.fecha.month==m)
                print(f"{nombre} 2025-{m:02d}: pres={(pm.valor_presupuestado if pm else None)} gastado={gastado}")
