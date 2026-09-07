import os
from datetime import datetime
from flask import Flask, render_template, request, redirect, url_for, session, flash, make_response
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from sqlalchemy import func

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'vow-secure-2026-vihan-online-work')
basedir = os.path.abspath(os.path.dirname(__file__))
# Permanent storage - SQLite database file, NOT localStorage
app.config['SQLALCHEMY_DATABASE_URI'] = f'sqlite:///{os.path.join(basedir, "vow_database.db")}'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

# --- MODELS ---
class Complaint(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    complaint_id = db.Column(db.String(50), unique=True, nullable=False)  # e.g. SACHIN-6789
    name = db.Column(db.String(120), nullable=False)
    phone = db.Column(db.String(20), nullable=False)
    service = db.Column(db.String(100), nullable=False)
    complaint_text = db.Column(db.Text, nullable=False)
    resolved = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class Admin(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(200), nullable=False)

def generate_complaint_id(name, phone):
    base_name = ''.join([c for c in name if c.isalpha()]).upper()[:12] or "USER"
    last4 = phone.strip()[-4:] if len(phone.strip()) >= 4 else phone.strip()
    base_id = f"{base_name}-{last4}"
    # Make unique if exists
    existing = Complaint.query.filter(Complaint.complaint_id.like(f"{base_id}%")).count()
    return base_id if existing == 0 else f"{base_id}-{existing+1}"

def init_db():
    db.create_all()
    if not Admin.query.filter_by(username='admin').first():
        admin = Admin(username='admin', password_hash=generate_password_hash('Vow@123'))
        db.session.add(admin)
        db.session.commit()

# Initialize on startup
with app.app_context():
    init_db()

def login_required(f):
    from functools import wraps
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get('admin_logged_in'):
            return redirect(url_for('admin_login'))
        return f(*args, **kwargs)
    return decorated

# --- ROUTES ---
@app.route('/', methods=['GET', 'POST'])
def home():
    if request.method == 'POST':
        name = request.form.get('name','').strip()
        phone = request.form.get('phone','').strip()
        service = request.form.get('service','').strip()
        complaint_text = request.form.get('complaint','').strip()
        if not all([name, phone, service, complaint_text]):
            flash('All fields are required.', 'error')
            return redirect(url_for('home'))
        if not phone.isdigit() or len(phone) < 10:
            flash('Enter valid phone number.', 'error')
            return redirect(url_for('home'))
        cid = generate_complaint_id(name, phone)
        c = Complaint(complaint_id=cid, name=name, phone=phone, service=service, complaint_text=complaint_text)
        db.session.add(c)
        db.session.commit()
        return render_template('success.html', complaint=c)
    return render_template('index.html')

@app.route('/admin/login', methods=['GET', 'POST'])
def admin_login():
    if request.method == 'POST':
        username = request.form.get('username','').strip()
        password = request.form.get('password','')
        admin = Admin.query.filter_by(username=username).first()
        if admin and check_password_hash(admin.password_hash, password):
            session['admin_logged_in'] = True
            session['admin_username'] = admin.username
            return redirect(url_for('dashboard'))
        flash('Invalid username or password.', 'error')
    return render_template('login.html')

@app.route('/admin/logout')
def admin_logout():
    session.clear()
    return redirect(url_for('admin_login'))

@app.route('/admin/dashboard')
@login_required
def dashboard():
    today = datetime.utcnow().date()
    month_start = today.replace(day=1)
    
    total = Complaint.query.count()
    today_count = Complaint.query.filter(func.date(Complaint.created_at) == today).count()
    month_count = Complaint.query.filter(Complaint.created_at >= datetime.combine(month_start, datetime.min.time())).count()
    pending = Complaint.query.filter_by(resolved=False).count()
    resolved = Complaint.query.filter_by(resolved=True).count()

    # Search & Filter
    search = request.args.get('q','').strip()
    service_filter = request.args.get('service','').strip()
    status_filter = request.args.get('status','').strip()

    query = Complaint.query.order_by(Complaint.created_at.desc())
    if search:
        like = f"%{search}%"
        query = query.filter(
            (Complaint.complaint_id.ilike(like)) |
            (Complaint.name.ilike(like)) |
            (Complaint.phone.ilike(like)) |
            (Complaint.complaint_text.ilike(like))
        )
    if service_filter:
        query = query.filter(Complaint.service == service_filter)
    if status_filter == 'resolved':
        query = query.filter(Complaint.resolved == True)
    elif status_filter == 'pending':
        query = query.filter(Complaint.resolved == False)

    complaints = query.all()
    services = [s[0] for s in db.session.query(Complaint.service).distinct().all() if s[0]]

    return render_template('dashboard.html', complaints=complaints, total=total, today_count=today_count, month_count=month_count, pending=pending, resolved=resolved, services=services, search=search)

@app.route('/admin/add', methods=['POST'])
@login_required
def admin_add():
    name = request.form.get('name','').strip()
    phone = request.form.get('phone','').strip()
    service = request.form.get('service','').strip()
    complaint_text = request.form.get('complaint','').strip()
    if not all([name, phone, service, complaint_text]):
        flash('All fields required', 'error')
        return redirect(url_for('dashboard'))
    cid = generate_complaint_id(name, phone)
    c = Complaint(complaint_id=cid, name=name, phone=phone, service=service, complaint_text=complaint_text)
    db.session.add(c)
    db.session.commit()
    flash(f'Complaint {cid} added successfully', 'success')
    return redirect(url_for('dashboard'))

@app.route('/admin/toggle/<int:complaint_id>')
@login_required
def toggle_status(complaint_id):
    c = Complaint.query.get_or_404(complaint_id)
    c.resolved = not c.resolved
    db.session.commit()
    return redirect(url_for('dashboard'))

@app.route('/admin/delete/<int:complaint_id>')
@login_required
def delete_complaint(complaint_id):
    c = Complaint.query.get_or_404(complaint_id)
    db.session.delete(c)
    db.session.commit()
    flash(f'{c.complaint_id} deleted', 'success')
    return redirect(url_for('dashboard'))

@app.route('/admin/export/pdf')
@login_required
def export_pdf():
    complaints = Complaint.query.order_by(Complaint.created_at.desc()).all()
    html = render_template('pdf_report.html', complaints=complaints, now=datetime.utcnow(), total=len(complaints))
    try:
        from weasyprint import HTML
        pdf = HTML(string=html).write_pdf()
        response = make_response(pdf)
        response.headers['Content-Type'] = 'application/pdf'
        response.headers['Content-Disposition'] = 'attachment; filename=VOW_Business_Report.pdf'
        return response
    except Exception as e:
        # Fallback printable HTML if weasyprint not installed
        return html

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
