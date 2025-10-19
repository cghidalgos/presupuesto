from flask import Flask, render_template, redirect, url_for, flash, request, Response
from config import Config
from datetime import date, timedelta
from models import db, User, Area, Concepto, Gasto, PresupuestoMensual
from forms import LoginForm, RegisterForm, AreaForm, ConceptoForm, GastoForm
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
import os

app = Flask(__name__)
app.config.from_object(Config)

# ensure instance folder exists
os.makedirs(os.path.join(os.path.dirname(__file__), 'instance'), exist_ok=True)

db.init_app(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    form = RegisterForm()
    if form.validate_on_submit():
        # NOTE: for demo we store password as-is. For production, hash with werkzeug.security
        user = User(name=form.name.data, email=form.email.data, password=form.password.data, aporte=form.aporte.data)
        db.session.add(user)
        db.session.commit()
        flash('Usuario registrado. Por favor inicia sesión.', 'success')
        return redirect(url_for('login'))
    return render_template('register.html', form=form)

@app.route('/login', methods=['GET', 'POST'])
def login():
    form = LoginForm()
    if form.validate_on_submit():
        user = User.query.filter_by(email=form.email.data).first()
        if user and user.password == form.password.data:
            login_user(user)
            return redirect(url_for('dashboard'))
        flash('Credenciales incorrectas', 'danger')
    return render_template('login.html', form=form)

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('index'))

# Áreas: crear y listar
@app.route('/areas', methods=['GET', 'POST'])
@login_required
def areas_view():
    form = AreaForm()
    if form.validate_on_submit():
        area = Area(nombre=form.nombre.data)
        db.session.add(area)
        db.session.commit()
        flash('Área creada', 'success')
        return redirect(url_for('areas_view'))
    areas = Area.query.all()
    return render_template('areas.html', form=form, areas=areas)

# Dashboard
@app.route('/dashboard')
@login_required
def dashboard():
    areas = Area.query.all()
    conceptos = Concepto.query.all()
    gastos = Gasto.query.order_by(Gasto.fecha.desc()).limit(30).all()

    total_presupuestado = sum(c.valor_presupuestado for c in conceptos)
    total_gastado = sum(c.total_gastado for c in conceptos)
    total_restante = max(total_presupuestado - total_gastado, 0)

    usuarios = User.query.all()
    aporte_info = []
    for u in usuarios:
        aport_expected = total_presupuestado * u.aporte
        aport_paid = sum(g.monto for g in u.gastos)
        aporte_info.append({'user': u, 'expected': aport_expected, 'paid': aport_paid, 'diff': aport_paid - aport_expected})

    return render_template('dashboard.html', areas=areas, conceptos=conceptos, gastos=gastos,
                           total_presupuestado=total_presupuestado, total_gastado=total_gastado,
                           total_restante=total_restante, aporte_info=aporte_info)

from calendar import month_name
from datetime import datetime, timedelta

# Presupuestar mes siguiente (después de app y configuración)
@app.route('/presupuestar_mes_siguiente', methods=['GET', 'POST'])
@login_required
def presupuestar_mes_siguiente():
    # Objetivo: presupuestar el "mes siguiente" respecto a HOY,
    # pero tomando como referencia el mes inmediatamente anterior al mes objetivo.
    # Ejemplo: si hoy es octubre, el objetivo es noviembre y la referencia debe ser octubre (no septiembre).
    hoy = datetime.today().date()
    this_month_first_day = hoy.replace(day=1)
    next_month_first_day = (this_month_first_day + timedelta(days=32)).replace(day=1)
    # Mes anterior al objetivo
    prev_month_last_day = next_month_first_day - timedelta(days=1)
    last_month_first_day = prev_month_last_day.replace(day=1)

    prev_month_label = f"{month_name[last_month_first_day.month]} {last_month_first_day.year}"
    next_month_label = f"{month_name[next_month_first_day.month]} {next_month_first_day.year}"

    conceptos = Concepto.query.all()
    sugerencias = []
    for c in conceptos:
        # Gastado en el mes anterior al objetivo
        gastado_prev = sum(
            g.monto for g in c.gastos
            if g.fecha.date() >= last_month_first_day and g.fecha.date() <= prev_month_last_day
        )
        # Presupuesto del mes anterior al objetivo (si existe en PresupuestoMensual)
        pm_prev = PresupuestoMensual.query.filter_by(
            concepto_id=c.id,
            year=last_month_first_day.year,
            month=last_month_first_day.month
        ).first()
        presupuestado_prev = pm_prev.valor_presupuestado if pm_prev else c.valor_presupuestado

        # Regla: si gastó más que el presupuesto previo, sugerir subir a lo gastado;
        # si gastó menos, sugerir bajar a lo gastado; si igual, mantener.
        if gastado_prev > presupuestado_prev:
            sugerido = gastado_prev
        elif gastado_prev < presupuestado_prev:
            sugerido = gastado_prev
        else:
            sugerido = presupuestado_prev

        sugerencias.append({
            'id': c.id,
            'nombre': c.nombre,
            'presupuestado_anterior': presupuestado_prev,
            'gastado_anterior': gastado_prev,
            'sugerido': sugerido
        })

    if request.method == 'POST':
        for s in sugerencias:
            nuevo_valor = float(request.form.get(f'presupuesto_{s["id"]}', s['sugerido']))
            # upsert presupuesto mensual para el siguiente mes
            pm = PresupuestoMensual.query.filter_by(concepto_id=s['id'], year=next_month_first_day.year, month=next_month_first_day.month).first()
            if not pm:
                pm = PresupuestoMensual(concepto_id=s['id'], year=next_month_first_day.year, month=next_month_first_day.month, valor_presupuestado=nuevo_valor)
                db.session.add(pm)
            else:
                pm.valor_presupuestado = nuevo_valor
        db.session.commit()
        flash(f'Presupuesto de {next_month_label} guardado', 'success')
        return redirect(url_for('conceptos_view'))

    return render_template('presupuestar_mes.html', sugerencias=sugerencias, prev_month=prev_month_label, next_month=next_month_label)
# Editar Área
@app.route('/areas/editar/<int:area_id>', methods=['GET', 'POST'])
@login_required
def editar_area(area_id):
    area = Area.query.get_or_404(area_id)
    form = AreaForm(obj=area)
    if form.validate_on_submit():
        area.nombre = form.nombre.data
        db.session.commit()
        flash('Área actualizada', 'success')
        return redirect(url_for('areas_view'))
    return render_template('areas.html', form=form, areas=Area.query.all(), editar_area=area)

@app.route('/conceptos', methods=['GET', 'POST'])
@login_required
def conceptos_view():
    form = ConceptoForm()
    form.area_id.choices = [(a.id, a.nombre) for a in Area.query.order_by(Area.nombre).all()]
    if form.validate_on_submit():
        c = Concepto(nombre=form.nombre.data, valor_presupuestado=form.valor_presupuestado.data, area_id=form.area_id.data)
        db.session.add(c)
        db.session.commit()
        flash('Concepto creado', 'success')
        return redirect(url_for('conceptos_view'))
    conceptos = Concepto.query.all()
    return render_template('conceptos.html', form=form, conceptos=conceptos)

# Editar Concepto
@app.route('/conceptos/editar/<int:concepto_id>', methods=['GET', 'POST'])
@login_required
def editar_concepto(concepto_id):
    concepto = Concepto.query.get_or_404(concepto_id)
    form = ConceptoForm(obj=concepto)
    form.area_id.choices = [(a.id, a.nombre) for a in Area.query.order_by(Area.nombre).all()]
    if form.validate_on_submit():
        concepto.nombre = form.nombre.data
        concepto.valor_presupuestado = form.valor_presupuestado.data
        concepto.area_id = form.area_id.data
        db.session.commit()
        flash('Concepto actualizado', 'success')
        return redirect(url_for('conceptos_view'))
    return render_template('conceptos.html', form=form, conceptos=Concepto.query.all(), editar_concepto=concepto)

@app.route('/gastos', methods=['GET', 'POST'])
@login_required
def gastos_view():
    form = GastoForm()
    form.concepto_id.choices = [(c.id, f"{c.nombre} ({c.area.nombre})") for c in Concepto.query.all()]
    if form.validate_on_submit():
        gasto = Gasto(concepto_id=form.concepto_id.data, usuario_id=current_user.id, monto=form.monto.data)
        db.session.add(gasto)
        db.session.commit()
        flash('Gasto registrado', 'success')
        return redirect(url_for('gastos_view'))
    gastos = Gasto.query.order_by(Gasto.fecha.desc()).all()
    return render_template('gastos.html', form=form, gastos=gastos)

@app.route('/reporte_mes')
@login_required
def reporte_mes():
    # Selección de mes/año por querystring, por defecto mes/año actuales
    y = request.args.get('year', type=int)
    m = request.args.get('month', type=int)
    today = datetime.today().date()
    if not y:
        y = today.year
    if not m:
        m = today.month

    # Calcular mes anterior y siguiente para navegación
    prev_y, prev_m = (y - 1, 12) if m == 1 else (y, m - 1)
    next_y, next_m = (y + 1, 1) if m == 12 else (y, m + 1)

    conceptos = Concepto.query.all()
    report = []
    total_pres = 0.0
    total_gasto = 0.0
    total_pend = 0.0
    counts = { 'green': 0, 'yellow': 0, 'lilac': 0, 'orange': 0, 'red': 0 }

    for c in conceptos:
        # Presupuesto mensual si existe, si no usar el valor base del concepto
        pm = PresupuestoMensual.query.filter_by(concepto_id=c.id, year=y, month=m).first()
        presupuestado = pm.valor_presupuestado if pm else c.valor_presupuestado

        # Gastado en el mes/año seleccionados
        gastado = sum(g.monto for g in c.gastos if g.fecha.year == y and g.fecha.month == m)
        pendiente = presupuestado - gastado  # permitir negativos para sobrepresupuesto

        total_pres += presupuestado
        total_gasto += gastado
        total_pend += pendiente

        # Clasificar estado para contador
        if pendiente < 0:
            counts['red'] += 1
            state = 'red'
        elif pendiente == 0:
            counts['green'] += 1
            state = 'green'
        elif presupuestado > 0 and pendiente == presupuestado:
            counts['yellow'] += 1
            state = 'yellow'
        else:
            ratio = 0 if presupuestado == 0 else (pendiente / presupuestado)
            if ratio < 0.2:
                counts['lilac'] += 1
                state = 'lilac'
            else:
                counts['orange'] += 1
                state = 'orange'

        report.append({
            'concepto': c,
            'presupuestado': presupuestado,
            'gastado': gastado,
            'pendiente': pendiente,
            'state': state,
        })

    month_label = f"{month_name[m]} {y}"

    # Exportar CSV si se solicita
    if request.args.get('format') == 'csv':
        import io, csv
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(['Año', 'Mes', 'Área', 'Concepto', 'Presupuestado', 'Gastado', 'Pendiente'])
        for row in report:
            writer.writerow([
                y,
                m,
                row['concepto'].area.nombre,
                row['concepto'].nombre,
                int(round(row['presupuestado'])),
                int(round(row['gastado'])),
                int(round(row['pendiente'])),
            ])
        writer.writerow([])
        writer.writerow(['Totales', '', '', '', int(round(total_pres)), int(round(total_gasto)), int(round(total_pend))])
        csv_data = output.getvalue()
        output.close()
        return Response(
            csv_data,
            mimetype='text/csv',
            headers={'Content-Disposition': f'attachment; filename="reporte_{y}-{m:02d}.csv"'}
        )

    return render_template(
        'reporte_mes.html',
        report=report,
        year=y,
        month=m,
        month_label=month_label,
        total_pres=total_pres,
        total_gasto=total_gasto,
        total_pend=total_pend,
        prev_y=prev_y,
        prev_m=prev_m,
        next_y=next_y,
        next_m=next_m,
        counts=counts,
    )

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5002)