from flask import Flask, render_template, redirect, url_for, flash, request, Response
from config import Config
from datetime import date, timedelta
from models import db, User, Area, Concepto, Gasto, PresupuestoMensual
from forms import LoginForm, RegisterForm, AreaForm, ConceptoForm, GastoForm
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
import os
import unicodedata
import re

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

# Eliminar Concepto
@app.route('/conceptos/eliminar/<int:concepto_id>', methods=['POST'])
@login_required
def eliminar_concepto(concepto_id):
    concepto = Concepto.query.get_or_404(concepto_id)
    gastos_asociados = len(concepto.gastos)
    presupuestos_asociados = len(getattr(concepto, 'presupuestos_mensuales', []))

    if gastos_asociados > 0 or presupuestos_asociados > 0:
        flash(
            f'No se puede eliminar el concepto "{concepto.nombre}" porque tiene '
            f'{gastos_asociados} gasto(s) y {presupuestos_asociados} presupuesto(s) mensual(es) asociados.',
            'danger'
        )
        return redirect(url_for('conceptos_view'))

    db.session.delete(concepto)
    db.session.commit()
    flash('Concepto eliminado', 'success')
    return redirect(url_for('conceptos_view'))

@app.route('/usuarios', methods=['GET', 'POST'])
@login_required
def usuarios_view():
    usuarios = User.query.all()
    
    if request.method == 'POST':
        # Recoger los nuevos aportes desde el formulario
        nuevos_aportes = {}
        total_aporte = 0.0
        
        for u in usuarios:
            try:
                nuevo_aporte = float(request.form.get(f'aporte_{u.id}', 0))
                if nuevo_aporte < 0 or nuevo_aporte > 100:
                    flash(f'El aporte de {u.name} debe estar entre 0 y 100%', 'danger')
                    return redirect(url_for('usuarios_view'))
                nuevos_aportes[u.id] = nuevo_aporte / 100.0
                total_aporte += nuevo_aporte
            except ValueError:
                flash(f'Valor inválido para el aporte de {u.name}', 'danger')
                return redirect(url_for('usuarios_view'))
        
        # Validar que la suma sea 100%
        if abs(total_aporte - 100.0) > 0.01:  # tolerancia de 0.01% para errores de redondeo
            flash(f'La suma de los aportes debe ser 100%. Actualmente es {total_aporte:.2f}%', 'danger')
            return redirect(url_for('usuarios_view'))
        
        # Actualizar los aportes
        for u in usuarios:
            u.aporte = nuevos_aportes[u.id]
        
        db.session.commit()
        flash('Aportes actualizados correctamente', 'success')
        return redirect(url_for('usuarios_view'))
    
    # Calcular suma actual de aportes
    total_actual = sum(u.aporte for u in usuarios) * 100
    
    return render_template('usuarios.html', usuarios=usuarios, total_actual=total_actual)

@app.route('/gastos', methods=['GET', 'POST'])
@login_required
def gastos_view():
    form = GastoForm()
    form.concepto_id.choices = [(c.id, f"{c.nombre} ({c.area.nombre})") for c in Concepto.query.all()]
    # Establecer fecha actual como valor por defecto
    if request.method == 'GET':
        form.fecha.data = datetime.today().date()
    if form.validate_on_submit():
        # Validar presupuesto mensual y advertir si se excede (pero permitir el registro)
        concepto = Concepto.query.get(form.concepto_id.data)
        fecha_gasto = datetime.combine(form.fecha.data, datetime.min.time())
        year = fecha_gasto.year
        month = fecha_gasto.month

        # Obtener presupuesto mensual o usar valor base
        pm = PresupuestoMensual.query.filter_by(concepto_id=concepto.id, year=year, month=month).first()
        presupuesto_mes = pm.valor_presupuestado if pm else concepto.valor_presupuestado

        # Calcular total gastado en ese mes (sin incluir el gasto actual)
        gastado_mes = sum(g.monto for g in concepto.gastos if g.fecha.year == year and g.fecha.month == month)

        # Calcular lo que quedaría disponible antes de este gasto
        disponible = presupuesto_mes - gastado_mes

        if form.monto.data > max(disponible, 0):
            exceso = form.monto.data - max(disponible, 0)
            flash(
                f'Advertencia: el gasto excede el presupuesto disponible para {concepto.nombre} en {month}/{year} '
                f'por ${exceso:,.0f}. Se registrará de todas formas.',
                'warning'
            )

        gasto = Gasto(concepto_id=form.concepto_id.data, usuario_id=current_user.id, monto=form.monto.data, fecha=fecha_gasto)
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
    # Agrupar por nombre de concepto (normalizado: trim, colapsar espacios, sin acentos, lower)
    group_map = {}
    for c in conceptos:
        raw_name = (c.nombre or '')
        name_strip = raw_name.strip()
        name_collapsed = re.sub(r"\s+", " ", name_strip)
        name_nfd = unicodedata.normalize('NFD', name_collapsed)
        name_no_accents = ''.join(ch for ch in name_nfd if unicodedata.category(ch) != 'Mn')
        key = name_no_accents.lower()

        # Presupuesto mensual si existe, si no usar el valor base del concepto
        pm = PresupuestoMensual.query.filter_by(concepto_id=c.id, year=y, month=m).first()
        presup_c = pm.valor_presupuestado if pm else c.valor_presupuestado

        # Gastos del mes/año seleccionados para este concepto
        gastos_mes_c = [g for g in c.gastos if g.fecha.year == y and g.fecha.month == m]
        gastado_c = sum(g.monto for g in gastos_mes_c)

        if key not in group_map:
            group_map[key] = {
                'concepto_name': name_collapsed if name_collapsed else c.nombre,
                'area_name': c.area.nombre if c.area else '',
                'presupuestado': 0.0,
                'gastado': 0.0,
                'gastos': [],
                'group_key': key.replace(' ', '-'),
                'source_count': 0,
            }
        group_map[key]['presupuestado'] += float(presup_c or 0)
        group_map[key]['gastado'] += float(gastado_c or 0)
        group_map[key]['gastos'].extend(gastos_mes_c)
        group_map[key]['source_count'] += 1

    # Construir reporte final desde los grupos
    report = []
    total_pres = 0.0
    total_gasto = 0.0
    total_pend = 0.0
    total_exceso = 0.0
    counts = { 'green': 0, 'yellow': 0, 'lilac': 0, 'orange': 0, 'red': 0 }

    for g in group_map.values():
        presupuestado = g['presupuestado']
        gastado = g['gastado']
        pendiente = presupuestado - gastado
        exceso = max(gastado - presupuestado, 0)

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

        total_pres += presupuestado
        total_gasto += gastado
        total_pend += pendiente
        total_exceso += exceso

        report.append({
            'area_name': g['area_name'],
            'concepto_name': g['concepto_name'],
            'presupuestado': presupuestado,
            'gastado': gastado,
            'pendiente': pendiente,
            'exceso': exceso,
            'state': state,
            'gastos': g['gastos'],
            'group_key': g['group_key'],
            'source_count': g['source_count'],
        })

    month_label = f"{month_name[m]} {y}"

    # Calcular aporte esperado por usuario
    usuarios = User.query.all()
    aportes_usuarios = []
    for u in usuarios:
        aporte_esperado = total_pres * u.aporte
        aportes_usuarios.append({
            'nombre': u.name,
            'porcentaje': u.aporte * 100,
            'aporte_esperado': aporte_esperado
        })

    # Exportar CSV si se solicita
    if request.args.get('format') == 'csv':
        import io, csv
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(['Año', 'Mes', 'Área', 'Concepto', 'Presupuestado', 'Gastado', 'Pendiente', 'Exceso'])
        for row in report:
            writer.writerow([
                y,
                m,
                row['area_name'],
                row['concepto_name'],
                int(round(row['presupuestado'])),
                int(round(row['gastado'])),
                int(round(row['pendiente'])),
                int(round(row['exceso'])),
            ])
        writer.writerow([])
        writer.writerow(['Totales', '', '', '', int(round(total_pres)), int(round(total_gasto)), int(round(total_pend)), int(round(total_exceso))])
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
        total_exceso=total_exceso,
        prev_y=prev_y,
        prev_m=prev_m,
        next_y=next_y,
        next_m=next_m,
        counts=counts,
        aportes_usuarios=aportes_usuarios,
    )

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5002)