import os
import json
import logging
from datetime import datetime
from functools import wraps

from flask import Flask, render_template, request, jsonify, redirect, url_for, session, flash
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.orm import DeclarativeBase
from werkzeug.security import generate_password_hash, check_password_hash

# Configure logging
logging.basicConfig(level=logging.DEBUG)

# Initialize Flask and SQLAlchemy
class Base(DeclarativeBase):
    pass

db = SQLAlchemy(model_class=Base)
app = Flask(__name__)
app.secret_key = os.environ.get("SESSION_SECRET", "default_secret_key_for_development")

# Configure the SQLite database
app.config["SQLALCHEMY_DATABASE_URI"] = os.environ.get("DATABASE_URL", "sqlite:///telegram_bot.db")
app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {
    "pool_recycle": 300,
    "pool_pre_ping": True,
}
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

# Initialize the app with the extension
db.init_app(app)

# Import models after db initialization to avoid circular imports
from models import Admin, Report

# Initialize database
with app.app_context():
    db.create_all()
    # Create default admin user if not exists
    admin = Admin.query.filter_by(username="admin").first()
    if not admin:
        default_admin = Admin(
            username="admin",
            password_hash=generate_password_hash("admin123")
        )
        db.session.add(default_admin)
        db.session.commit()
        logging.info("Default admin user created")

# Login required decorator
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'admin_id' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

# Routes
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        admin = Admin.query.filter_by(username=username).first()
        
        if admin and check_password_hash(admin.password_hash, password):
            session['admin_id'] = admin.id
            return redirect(url_for('dashboard'))
        else:
            flash('Invalid username or password')
    
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.pop('admin_id', None)
    return redirect(url_for('login'))

@app.route('/dashboard')
@login_required
def dashboard():
    return render_template('dashboard.html')

@app.route('/reports')
@login_required
def reports():
    return render_template('reports.html')

# API Routes
@app.route('/api/reports', methods=['GET'])
@login_required
def get_reports():
    reports = Report.query.order_by(Report.timestamp.desc()).all()
    report_list = []
    
    for report in reports:
        timestamp_str = report.timestamp.isoformat() if report.timestamp else datetime.utcnow().isoformat()
        
        report_list.append({
            'id': report.id,
            'user_id': report.user_id,
            'username': report.username,
            'category': report.category,
            'description': report.description,
            'status': report.status,
            'timestamp': timestamp_str
        })
    
    return jsonify(report_list)

@app.route('/api/reports/<int:report_id>', methods=['PUT'])
@login_required
def update_report(report_id):
    report = Report.query.get_or_404(report_id)
    data = request.json
    
    if 'status' in data:
        report.status = data['status']
    
    db.session.commit()
    return jsonify({'success': True})

# Import and start the Telegram bot in a separate thread
try:
    logging.info("Attempting to start Telegram bot...")
    from bot import start_bot
    start_bot()
    logging.info("Telegram bot initialization completed")
except Exception as e:
    logging.error(f"Error starting Telegram bot: {e}")
    logging.warning("Application will run without Telegram bot functionality")
