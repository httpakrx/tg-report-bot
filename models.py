from datetime import datetime
from app import db
from flask_login import UserMixin

class Admin(UserMixin, db.Model):
    """Admin user model"""
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(64), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)

class Report(db.Model):
    """Purchase issue report model"""
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, nullable=False)
    username = db.Column(db.String(128), nullable=False)
    category = db.Column(db.String(64), nullable=False)
    description = db.Column(db.Text, nullable=False)
    status = db.Column(db.String(32), default="Pending")  # Pending, In Progress, Resolved, Rejected
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
