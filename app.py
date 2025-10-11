from flask import Flask, render_template, redirect, url_for, flash, request
from config import Config
from models import db, User, Area, Concepto, Gasto
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

@app.route('/dashboard')
@login_required
def dashboard():
    # resumen por areas y totales
    areas = Area.query.all()
    conceptos = Concepto.query.all()
    gastos = Gasto.query.order_by(Gasto.fecha.desc()).limit(30).all()

    total_presupuestado = sum(c.valor_presupuestado for c in conceptos)
    total_gastado = sum(c.total_gastado for c in conceptos)
    total_restante = max(total_presupuestado - total_gastado, 0)

    # calcular aporte esperado y ya pagado por usuario
    usuarios = User.query.all()
    aporte_info = []
    for u in usuarios:
        aport_expected = total_presupuestado * u.aporte
        aport_paid = sum(g.monto for g in u.gastos)
        aporte_info.append({'user': u, 'expected': aport_expected, 'paid': aport_paid, 'diff': aport_paid - aport_expected})

    return render_template('dashboard.html', areas=areas, conceptos=conceptos, gastos=gastos,
                           total_presupuestado=total_presupuestado, total_gastado=total_gastado,
                           total_restante=total_restante, aporte_info=aporte_info)

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
    # ejemplo: resumen por concepto/área
    conceptos = Concepto.query.all()
    report = []
    for c in conceptos:
        report.append({
            'concepto': c,
            'presupuestado': c.valor_presupuestado,
            'gastado': c.total_gastado,
            'restante': c.restante
        })
    return render_template('reporte_mes.html', report=report)

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5002)