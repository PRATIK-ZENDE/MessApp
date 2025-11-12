from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, send_file, abort
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from flask_wtf.csrf import CSRFProtect
from datetime import datetime, date, timedelta
import os
import json
import csv
from io import StringIO, BytesIO
import qrcode
import secrets
import base64
import string
import hmac
import hashlib
from urllib.parse import quote

# Load environment variables from .env file
from dotenv import load_dotenv
load_dotenv()

# Initialize Flask
app = Flask(__name__)
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'dev-secret-key')
default_db_path = os.path.join(app.root_path, 'instance', 'mess_management.db')
default_db_uri = 'sqlite:///' + default_db_path.replace('\\', '/')
database_uri = os.getenv('DATABASE_URL', default_db_uri)

# Normalize sqlite URI if environment variable provides a relative path
if database_uri.startswith('sqlite:///') and not database_uri.startswith('sqlite:////'):
    relative_path = database_uri.replace('sqlite:///', '', 1)
    if not os.path.isabs(relative_path):
        absolute_path = os.path.join(app.root_path, relative_path)
        database_uri = 'sqlite:///' + os.path.normpath(absolute_path).replace('\\', '/')

app.config['SQLALCHEMY_DATABASE_URI'] = database_uri
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['WTF_CSRF_ENABLED'] = True  # Enable CSRF protection
app.config['WTF_CSRF_SECRET_KEY'] = os.getenv('WTF_CSRF_SECRET_KEY', 'dev-csrf-key')

# UPI Payment Configuration (fallbacks used only if Mess settings not present)
app.config['UPI_ID'] = os.getenv('UPI_ID', 'mess@oksbi')
app.config['UPI_NAME'] = os.getenv('UPI_NAME', 'Mess Management')

def ensure_sqlite_directory(database_uri: str) -> None:
    """Ensure folder for SQLite DB exists before engine initialization."""
    if database_uri.startswith('sqlite:///'):
        relative_path = database_uri.replace('sqlite:///', '', 1)
        full_path = os.path.normpath(os.path.join(app.root_path, relative_path))
        directory = os.path.dirname(full_path)
        if directory:
            os.makedirs(directory, exist_ok=True)


ensure_sqlite_directory(app.config['SQLALCHEMY_DATABASE_URI'])

# Initialize extensions
db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'
csrf = CSRFProtect(app)

# Models
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)
    is_admin = db.Column(db.Boolean, default=False)
    # Multi-mess support: each admin (and potentially staff) belongs to a mess
    mess_id = db.Column(db.Integer, db.ForeignKey('mess.id'), nullable=True)
    
    def set_password(self, password):
        self.password_hash = generate_password_hash(password)
        
    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

class Settings(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    key = db.Column(db.String(50), unique=True, nullable=False)
    value = db.Column(db.String(255), nullable=False)
    description = db.Column(db.String(255))
    
    @staticmethod
    def get_value(key, default=None):
        setting = Settings.query.filter_by(key=key).first()
        return setting.value if setting else default
    
    @staticmethod
    def set_value(key, value, description=None):
        setting = Settings.query.filter_by(key=key).first()
        if setting:
            setting.value = str(value)
            if description:
                setting.description = description
        else:
            setting = Settings(key=key, value=str(value), description=description)
            db.session.add(setting)
        db.session.commit()

class Student(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    roll_no = db.Column(db.String(50), unique=True)
    department = db.Column(db.String(100))
    contact = db.Column(db.String(15))
    email = db.Column(db.String(120))
    address = db.Column(db.Text)
    password_hash = db.Column(db.String(200))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    mess_id = db.Column(db.Integer, db.ForeignKey('mess.id'), nullable=True)  # Multi-mess scoping
    attendance = db.relationship('Attendance', backref='student', lazy=True, cascade='all, delete-orphan')
    bills = db.relationship('Bill', backref='student', lazy=True, cascade='all, delete-orphan')
    payments = db.relationship('Payment', backref='student', lazy=True, cascade='all, delete-orphan')
    
    def set_password(self, password):
        self.password_hash = generate_password_hash(password)
    
    def check_password(self, password):
        if not self.password_hash:
            return False
        return check_password_hash(self.password_hash, password)

class Attendance(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey('student.id'), nullable=False)
    date = db.Column(db.Date, nullable=False, default=date.today)
    meal_type = db.Column(db.String(10), nullable=False)  # 'lunch' or 'dinner'
    timestamp = db.Column(db.DateTime, nullable=False, default=datetime.now)
    method = db.Column(db.String(10), default='manual')  # 'manual' or 'qr'
    marked_by = db.Column(db.String(50), nullable=False)
    session_id = db.Column(db.Integer, db.ForeignKey('attendance_session.id'), nullable=True)
    
    def to_dict(self):
        return {
            'id': self.id,
            'student': {
                'id': self.student.id,
                'name': self.student.name
            },
            'date': self.date.strftime('%Y-%m-%d'),
            'meal_type': self.meal_type,
            'timestamp': self.timestamp.strftime('%Y-%m-%d %H:%M:%S'),
            'method': self.method,
            'marked_by': self.marked_by
        }

class AttendanceSession(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    token = db.Column(db.String(100), unique=True, nullable=False)
    date = db.Column(db.Date, nullable=False, default=date.today)
    meal_type = db.Column(db.String(10), nullable=False)
    created_by = db.Column(db.String(50), nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.now)
    expires_at = db.Column(db.DateTime, nullable=False)
    is_active = db.Column(db.Boolean, default=True)
    mess_id = db.Column(db.Integer, db.ForeignKey('mess.id'), nullable=True)  # Scope session to a mess
    attendances = db.relationship('Attendance', backref='session', lazy=True)
    
    def is_valid(self):
        return self.is_active and datetime.now() < self.expires_at
    
    def to_dict(self):
        return {
            'id': self.id,
            'token': self.token,
            'date': self.date.strftime('%Y-%m-%d'),
            'meal_type': self.meal_type,
            'created_by': self.created_by,
            'created_at': self.created_at.strftime('%Y-%m-%d %H:%M:%S'),
            'expires_at': self.expires_at.strftime('%Y-%m-%d %H:%M:%S'),
            'is_active': self.is_active,
            'attendance_count': len(self.attendances)
        }

class Bill(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey('student.id'), nullable=False)
    month = db.Column(db.Integer, nullable=False)
    year = db.Column(db.Integer, nullable=False)
    amount = db.Column(db.Float, nullable=False)
    days_present = db.Column(db.Float, nullable=False)
    paid = db.Column(db.Boolean, default=False)
    daily_rate = db.Column(db.Float, nullable=False, default=100.0)
    generated_on = db.Column(db.DateTime, default=datetime.utcnow)
    mess_id = db.Column(db.Integer, db.ForeignKey('mess.id'), nullable=True)  # Scope bill to mess
    payments = db.relationship('Payment', backref='bill', lazy=True, cascade='all, delete-orphan')

    @property
    def latest_payment(self):
        if not self.payments:
            return None
        return max(self.payments, key=lambda payment: payment.created_at or datetime.min)

    @property
    def payment_status(self):
        if self.paid:
            return 'paid'
        if any(payment.status == 'submitted' for payment in self.payments):
            return 'pending_verification'
        if any(payment.status == 'rejected' for payment in self.payments):
            return 'rejected'
        return 'pending'


class Payment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    bill_id = db.Column(db.Integer, db.ForeignKey('bill.id'), nullable=False)
    student_id = db.Column(db.Integer, db.ForeignKey('student.id'), nullable=False)
    amount = db.Column(db.Float, nullable=False)
    method = db.Column(db.String(50), nullable=True)
    reference = db.Column(db.String(120), nullable=True)
    notes = db.Column(db.Text, nullable=True)
    status = db.Column(db.String(20), nullable=False, default='submitted')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    verified_at = db.Column(db.DateTime, nullable=True)
    verified_by = db.Column(db.String(80), nullable=True)
    mess_id = db.Column(db.Integer, db.ForeignKey('mess.id'), nullable=True)  # Scope payment to mess (redundant but helpful for reporting)

    def to_dict(self):
        return {
            'id': self.id,
            'bill_id': self.bill_id,
            'student_id': self.student_id,
            'amount': round(self.amount or 0.0, 2),
            'method': self.method,
            'reference': self.reference,
            'notes': self.notes,
            'status': self.status,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
            'verified_at': self.verified_at.isoformat() if self.verified_at else None,
            'verified_by': self.verified_by,
            'student_name': self.student.name if self.student else None,
        }

# Multi-mess parent entity
class Mess(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(150), unique=True, nullable=False)
    daily_meal_rate = db.Column(db.Float, nullable=False, default=100.0)
    upi_id = db.Column(db.String(150))
    upi_name = db.Column(db.String(150))
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    # Relationships
    users = db.relationship('User', backref='mess', lazy=True)
    students = db.relationship('Student', backref='mess', lazy=True)
    sessions = db.relationship('AttendanceSession', backref='mess', lazy=True)
    bills = db.relationship('Bill', backref='mess', lazy=True)
    payments = db.relationship('Payment', backref='mess', lazy=True)

    def __repr__(self):
        return f"<Mess {self.name}>"

def current_mess():
    if current_user.is_authenticated and getattr(current_user, 'mess_id', None):
        return Mess.query.get(current_user.mess_id)
    return None

def get_effective_upi():
    """Return (upi_id, upi_name) preferring current mess, then Settings, then app.config."""
    mess = current_mess()
    if mess and (mess.upi_id or mess.upi_name):
        return mess.upi_id or app.config.get('UPI_ID'), mess.upi_name or app.config.get('UPI_NAME')
    # Fallback to Settings for backward-compat
    upi_id = Settings.get_value('upi_id', app.config.get('UPI_ID'))
    upi_name = Settings.get_value('upi_name', app.config.get('UPI_NAME'))
    return upi_id, upi_name

def get_effective_daily_rate():
    mess = current_mess()
    if mess and mess.daily_meal_rate:
        return float(mess.daily_meal_rate)
    try:
        return float(Settings.get_value('daily_meal_rate', '100.0'))
    except Exception:
        return 100.0


def error_response(message, status_code=400):
    """Standardized JSON error response"""
    return jsonify({'success': False, 'error': message}), status_code

# Utility Functions
def get_current_meal_type():
    """Determine current meal type based on time of day"""
    current_hour = datetime.now().hour
    return 'dinner' if current_hour >= 15 else 'lunch'

def generate_temp_password(length: int = 10) -> str:
    """Generate a secure temporary password (alphanumeric, avoiding ambiguous chars)."""
    alphabet = string.ascii_letters + string.digits
    # Optionally avoid ambiguous chars (0/O, 1/l/I) by filtering
    ambiguous = set('0O1lI')
    candidates = ''.join(ch for ch in alphabet if ch not in ambiguous)
    return ''.join(secrets.choice(candidates) for _ in range(max(6, length)))

def get_date_range(range_type, start_date=None, end_date=None):
    """Get date range based on filter type"""
    today = date.today()
    
    if range_type == 'today':
        return today, today
    elif range_type == 'yesterday':
        yesterday = today - timedelta(days=1)
        return yesterday, yesterday
    elif range_type == 'thisWeek':
        start = today - timedelta(days=today.weekday())
        return start, today
    elif range_type == 'lastWeek':
        end = today - timedelta(days=today.weekday() + 1)
        start = end - timedelta(days=6)
        return start, end
    elif range_type == 'thisMonth':
        start = today.replace(day=1)
        return start, today
    elif range_type == 'custom' and start_date and end_date:
        return datetime.strptime(start_date, '%Y-%m-%d').date(), datetime.strptime(end_date, '%Y-%m-%d').date()
    
    return today, today

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# Authentication Routes
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
        
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        user = User.query.filter_by(username=username).first()
        if user and user.check_password(password):
            login_user(user)
            next_page = request.args.get('next')
            return redirect(next_page) if next_page else redirect(url_for('dashboard'))
        
        flash('Invalid username or password', 'error')
    return render_template('login.html')

@app.route('/signup', methods=['GET', 'POST'])
def signup():
    # Allow creation of a new Mess with an admin user.
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))

    if request.method == 'POST':
        mess_name = request.form.get('mess_name', '').strip()
        admin_username = request.form.get('admin_username', '').strip()
        admin_password = request.form.get('admin_password', '').strip()
        daily_meal_rate = request.form.get('daily_meal_rate')
        upi_id = request.form.get('upi_id', '').strip()
        upi_name = request.form.get('upi_name', '').strip()

        errors = []
        if not mess_name:
            errors.append('Mess name is required.')
        if not admin_username:
            errors.append('Admin username is required.')
        if not admin_password or len(admin_password) < 6:
            errors.append('Admin password must be at least 6 characters.')
        if Mess.query.filter_by(name=mess_name).first():
            errors.append('Mess name already exists.')
        if User.query.filter_by(username=admin_username).first():
            errors.append('Admin username already taken.')

        try:
            daily_meal_rate_val = float(daily_meal_rate or 0)
            if daily_meal_rate_val <= 0:
                errors.append('Daily meal rate must be positive.')
        except ValueError:
            errors.append('Daily meal rate must be a number.')

        if errors:
            for e in errors:
                flash(e, 'error')
            return render_template('signup.html')

        # Create Mess
        mess = Mess(
            name=mess_name,
            daily_meal_rate=daily_meal_rate_val,
            upi_id=upi_id or None,
            upi_name=upi_name or None
        )
        db.session.add(mess)
        db.session.flush()  # Get mess.id before creating user

        # Create Admin User
        admin_user = User(
            username=admin_username,
            is_admin=True,
            mess_id=mess.id
        )
        admin_user.set_password(admin_password)
        db.session.add(admin_user)

        try:
            db.session.commit()
            login_user(admin_user)
            flash('Mess created and admin account registered successfully!', 'success')
            return redirect(url_for('dashboard'))
        except Exception as e:
            db.session.rollback()
            flash(f'Error creating mess: {e}', 'error')
            return render_template('signup.html')

    return render_template('signup.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('index'))

@app.route('/dashboard')
@login_required
def dashboard():
    return render_template('dashboard.html')

# Student Authentication Routes
@app.route('/student/login', methods=['GET', 'POST'])
def student_login():
    from flask import session
    # Redirect if already logged in unless forced to show login
    force = request.args.get('force')
    if 'student_id' in session and force != '1':
        return redirect(url_for('student_dashboard'))
    
    if request.method == 'POST':
        roll_no = request.form.get('roll_no')
        password = request.form.get('password')
        
        student = Student.query.filter_by(roll_no=roll_no).first()
        if student and student.check_password(password):
            # Store student ID in session
            session['student_id'] = student.id
            session['student_name'] = student.name
            session.permanent = True  # Make session persist across browser restarts
            
            # Check for pending notifications
            pending_bills = Bill.query.filter_by(student_id=student.id, paid=False).count()
            pending_payments = Payment.query.filter_by(student_id=student.id, status='submitted').count()
            rejected_payments = Payment.query.filter_by(student_id=student.id, status='rejected').count()
            
            # Show welcome message with notifications
            if rejected_payments > 0:
                flash(f'Welcome back, {student.name}! You have {rejected_payments} rejected payment(s) that need resubmission.', 'warning')
            elif pending_payments > 0:
                flash(f'Welcome back, {student.name}! You have {pending_payments} payment(s) awaiting admin verification.', 'info')
            elif pending_bills > 0:
                flash(f'Welcome, {student.name}! You have {pending_bills} unpaid bill(s).', 'info')
            else:
                flash(f'Welcome, {student.name}!', 'success')
            
            next_page = request.args.get('next')
            return redirect(next_page) if next_page else redirect(url_for('student_dashboard'))
        
        flash('Invalid roll number or password', 'error')
    return render_template('student_login.html', force_login=(force == '1'))

@app.route('/student/logout')
def student_logout():
    from flask import session
    session.pop('student_id', None)
    session.pop('student_name', None)
    flash('Logged out successfully', 'success')
    return redirect(url_for('index'))

def student_required(f):
    """Decorator to require student login"""
    from functools import wraps
    @wraps(f)
    def decorated_function(*args, **kwargs):
        from flask import session
        if 'student_id' not in session:
            flash('Please login to access this page', 'error')
            return redirect(url_for('student_login'))
        return f(*args, **kwargs)
    return decorated_function

@app.route('/student/dashboard')
@student_required
def student_dashboard():
    from flask import session
    student = Student.query.get(session['student_id'])
    
    # Get current month stats
    today = date.today()
    start_of_month = today.replace(day=1)
    
    # Total attendance this month
    monthly_attendance = Attendance.query.filter(
        Attendance.student_id == student.id,
        Attendance.date >= start_of_month,
        Attendance.date <= today
    ).all()
    
    # Today's attendance
    today_attendance = Attendance.query.filter(
        Attendance.student_id == student.id,
        Attendance.date == today
    ).all()
    
    # Current month bill
    current_bill = Bill.query.filter(
        Bill.student_id == student.id,
        Bill.month == today.month,
        Bill.year == today.year
    ).first()
    pending_payment = None
    if current_bill:
        pending_payment = Payment.query.filter_by(bill_id=current_bill.id, status='submitted').order_by(Payment.created_at.desc()).first()
    recent_payments = Payment.query.filter_by(student_id=student.id).order_by(Payment.created_at.desc()).limit(3).all()
    
    # Recent meal history (last 7 days)
    seven_days_ago = today - timedelta(days=7)
    recent_meals = Attendance.query.filter(
        Attendance.student_id == student.id,
        Attendance.date >= seven_days_ago,
        Attendance.date <= today
    ).order_by(Attendance.date.desc()).all()
    
    # Meal type breakdown this month
    lunch_count = sum(1 for a in monthly_attendance if a.meal_type == 'lunch')
    dinner_count = sum(1 for a in monthly_attendance if a.meal_type == 'dinner')
    
    return render_template('student_dashboard.html',
                         student=student,
                         total_attendance=len(monthly_attendance),
                         lunch_count=lunch_count,
                         dinner_count=dinner_count,
                         today_attendance=today_attendance,
                         current_bill=current_bill,
                         pending_payment=pending_payment,
                         recent_payments=recent_payments,
                         recent_meals=recent_meals)

@app.route('/student/attendance')
@student_required
def student_attendance():
    from flask import session
    import calendar
    student = Student.query.get(session['student_id'])
    
    # Get view type (calendar or list)
    view_type = request.args.get('view', 'calendar')
    
    # Get calendar month/year with safe conversion
    today = date.today()
    try:
        month_param = request.args.get('month', '')
        calendar_month = int(month_param) if month_param else today.month
    except (ValueError, TypeError):
        calendar_month = today.month
    
    try:
        year_param = request.args.get('year', '')
        calendar_year = int(year_param) if year_param else today.year
    except (ValueError, TypeError):
        calendar_year = today.year
    
    # Calculate previous and next month
    if calendar_month == 1:
        prev_month, prev_year = 12, calendar_year - 1
    else:
        prev_month, prev_year = calendar_month - 1, calendar_year
    
    if calendar_month == 12:
        next_month, next_year = 1, calendar_year + 1
    else:
        next_month, next_year = calendar_month + 1, calendar_year
    
    # Get month name
    month_names = ['', 'January', 'February', 'March', 'April', 'May', 'June',
                   'July', 'August', 'September', 'October', 'November', 'December']
    calendar_month_name = month_names[calendar_month]
    
    # Build calendar data
    cal = calendar.monthcalendar(calendar_year, calendar_month)
    
    # Get all attendance for the month
    first_day = date(calendar_year, calendar_month, 1)
    if calendar_month == 12:
        last_day = date(calendar_year + 1, 1, 1) - timedelta(days=1)
    else:
        last_day = date(calendar_year, calendar_month + 1, 1) - timedelta(days=1)
    
    month_attendance = Attendance.query.filter(
        Attendance.student_id == student.id,
        Attendance.date >= first_day,
        Attendance.date <= last_day
    ).all()
    
    # Create a dictionary of attendance by date
    attendance_by_date = {}
    for att in month_attendance:
        if att.date not in attendance_by_date:
            attendance_by_date[att.date] = {'lunch': False, 'dinner': False}
        attendance_by_date[att.date][att.meal_type] = True
    
    # Build calendar days array
    calendar_days = []
    for week in cal:
        for day in week:
            if day == 0:
                calendar_days.append({'empty': True})
            else:
                day_date = date(calendar_year, calendar_month, day)
                is_future = day_date > today
                has_lunch = attendance_by_date.get(day_date, {}).get('lunch', False)
                has_dinner = attendance_by_date.get(day_date, {}).get('dinner', False)
                
                calendar_days.append({
                    'empty': False,
                    'day': day,
                    'is_future': is_future,
                    'has_lunch': has_lunch,
                    'has_dinner': has_dinner
                })
    
    # Get filter parameters for list view
    date_range = request.args.get('dateRange', 'thisMonth')
    meal_type = request.args.get('mealType', 'all')
    
    # Get date range for list view
    if date_range == 'thisMonth':
        start_date = today.replace(day=1)
        end_date = today
    elif date_range == 'lastMonth':
        first_of_month = today.replace(day=1)
        end_date = first_of_month - timedelta(days=1)
        start_date = end_date.replace(day=1)
    elif date_range == 'thisWeek':
        start_date = today - timedelta(days=today.weekday())
        end_date = today
    else:  # all time
        start_date = student.created_at.date() if student.created_at else today - timedelta(days=365)
        end_date = today
    
    # Query attendance for list view
    query = Attendance.query.filter(
        Attendance.student_id == student.id,
        Attendance.date.between(start_date, end_date)
    )
    
    if meal_type != 'all':
        query = query.filter(Attendance.meal_type == meal_type)
    
    attendance_records = query.order_by(Attendance.date.desc()).all()
    
    # Calculate statistics
    total_days = (end_date - start_date).days + 1
    attendance_count = len(attendance_records)
    lunch_count = sum(1 for a in attendance_records if a.meal_type == 'lunch')
    dinner_count = sum(1 for a in attendance_records if a.meal_type == 'dinner')
    
    return render_template('student_attendance.html',
                         student=student,
                         attendance_records=attendance_records,
                         total_days=total_days,
                         attendance_count=attendance_count,
                         lunch_count=lunch_count,
                         dinner_count=dinner_count,
                         date_range=date_range,
                         meal_type=meal_type,
                         calendar_days=calendar_days,
                         calendar_month=calendar_month,
                         calendar_year=calendar_year,
                         calendar_month_name=calendar_month_name,
                         prev_month=prev_month,
                         prev_year=prev_year,
                         next_month=next_month,
                         next_year=next_year)

@app.route('/student/bills')
@student_required
def student_bills():
    from flask import session
    student = Student.query.get(session['student_id'])
    
    # Get all bills for this student
    bills = Bill.query.filter_by(student_id=student.id).order_by(Bill.year.desc(), Bill.month.desc()).all()
    
    # Calculate totals
    total_amount = sum(bill.amount for bill in bills)
    paid_amount = sum(bill.amount for bill in bills if bill.paid)
    pending_amount = total_amount - paid_amount
    pending_verification_amount = sum(bill.amount for bill in bills if bill.payment_status == 'pending_verification')
    rejected_amount = sum(bill.amount for bill in bills if bill.payment_status == 'rejected')
    outstanding_amount = max(pending_amount - pending_verification_amount, 0)
    pending_verification_count = sum(1 for bill in bills if bill.payment_status == 'pending_verification')
    rejected_count = sum(1 for bill in bills if bill.payment_status == 'rejected')
    due_count = sum(1 for bill in bills if bill.payment_status == 'pending')
    recent_payments = Payment.query.filter_by(student_id=student.id).order_by(Payment.created_at.desc()).limit(5).all()
    
    return render_template('student_bills.html',
                         student=student,
                         bills=bills,
                         total_amount=total_amount,
                         paid_amount=paid_amount,
                         pending_amount=pending_amount,
                         outstanding_amount=outstanding_amount,
                         pending_verification_amount=pending_verification_amount,
                         rejected_amount=rejected_amount,
                         pending_verification_count=pending_verification_count,
                         rejected_count=rejected_count,
                         due_count=due_count,
                         recent_payments=recent_payments)


@app.route('/student/bills/<int:bill_id>/generate-upi-link', methods=['POST'])
@student_required
def generate_upi_payment_link(bill_id):
    """Generate UPI deep link for direct payment through UPI apps"""
    from flask import session
    student = Student.query.get_or_404(session['student_id'])
    bill = Bill.query.get_or_404(bill_id)
    
    if bill.student_id != student.id:
        return jsonify({'success': False, 'message': 'Unauthorized'}), 403
    if bill.paid:
        return jsonify({'success': False, 'message': 'Bill already paid'}), 400
    
    # Generate unique transaction reference with mess scoping
    mess_prefix = f"M{student.mess_id}-" if getattr(student, 'mess_id', None) else ""
    txn_ref = f"{mess_prefix}BILL{bill.id}-STU{student.id}-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}"

    # Resolve UPI parameters from Mess preference
    upi_id_val, upi_name_val = get_effective_upi()
    upi_id = upi_id_val or app.config.get('UPI_ID', 'merchant@upi')
    payee_name = quote(upi_name_val or app.config.get('UPI_NAME', 'Mess Management'))
    amount = f"{bill.amount:.2f}"
    transaction_note = quote(f"Mess Bill #{bill.id} - {student.roll_no}")
    
    # Generate UPI deep link (works with all UPI apps)
    upi_link = f"upi://pay?pa={upi_id}&pn={payee_name}&am={amount}&cu=INR&tn={transaction_note}&tr={txn_ref}"
    
    # Generate UPI QR code
    qr = qrcode.QRCode(version=1, box_size=10, border=4)
    qr.add_data(upi_link)
    qr.make(fit=True)
    qr_img = qr.make_image(fill_color="black", back_color="white")
    
    # Convert QR to base64
    buffered = BytesIO()
    qr_img.save(buffered, format="PNG")
    qr_base64 = base64.b64encode(buffered.getvalue()).decode()
    
    return jsonify({
        'success': True,
        'upi_link': upi_link,
        'qr_code': f'data:image/png;base64,{qr_base64}',
        'transaction_ref': txn_ref,
        'amount': amount,
        'upi_id': upi_id,
        'payee_name': upi_name_val or app.config.get('UPI_NAME', 'Mess Management')
    })


@app.route('/student/bills/<int:bill_id>/initiate-payment', methods=['POST'])
@student_required
def student_initiate_payment(bill_id):
    from flask import session
    student = Student.query.get_or_404(session['student_id'])
    bill = Bill.query.get_or_404(bill_id)
    if bill.student_id != student.id:
        return jsonify({'success': False, 'message': 'You are not authorized to pay this bill.'}), 403
    if bill.paid:
        return jsonify({'success': False, 'message': 'Bill is already marked as paid.'}), 400

    data = request.get_json(silent=True) or {}
    try:
        amount = float(data.get('amount', 0))
    except (TypeError, ValueError):
        return jsonify({'success': False, 'message': 'Invalid amount specified.'}), 400

    if amount <= 0 or amount > bill.amount:
        return jsonify({'success': False, 'message': 'Payment amount must be greater than 0 and no more than the bill total.'}), 400

    payment_method = (data.get('method') or '').strip().lower()
    allowed_methods = {'upi', 'card', 'netbanking', 'cash', 'wallet', 'other'}
    if payment_method and payment_method not in allowed_methods:
        return jsonify({'success': False, 'message': 'Unsupported payment method.'}), 400

    # Prevent multiple pending submissions
    pending_payment = Payment.query.filter_by(bill_id=bill.id, status='submitted').first()
    if pending_payment:
        return jsonify({'success': False, 'message': 'A payment is already pending verification for this bill.'}), 400

    reference = (data.get('reference') or '').strip()
    if not reference:
        return jsonify({'success': False, 'message': 'Please provide a transaction reference or UPI ID.'}), 400

    notes = (data.get('notes') or '').strip() or None
    payment = Payment(
        bill_id=bill.id,
        student_id=student.id,
        amount=amount,
        method=payment_method or 'upi',
        reference=reference,
        notes=notes,
        status='submitted'
    )
    try:
        db.session.add(payment)
        db.session.commit()
        return jsonify({
            'success': True,
            'message': 'Payment submitted for verification. The admin will confirm shortly.',
            'payment': payment.to_dict()
        })
    except Exception as exc:
        db.session.rollback()
        return jsonify({'success': False, 'message': f'Could not submit payment: {exc}'}), 500


@app.route('/student/bills/<int:bill_id>/payments')
@student_required
def student_bill_payments(bill_id):
    from flask import session
    student = Student.query.get_or_404(session['student_id'])
    bill = Bill.query.get_or_404(bill_id)
    if bill.student_id != student.id:
        return jsonify({'success': False, 'message': 'You are not authorized to view these payments.'}), 403

    payments = [payment.to_dict() for payment in sorted(bill.payments, key=lambda p: p.created_at or datetime.min, reverse=True)]
    return jsonify({'success': True, 'payments': payments, 'bill_paid': bill.paid})

@app.route('/student/profile', methods=['GET', 'POST'])
@student_required
def student_profile():
    from flask import session
    student = Student.query.get(session['student_id'])
    
    if request.method == 'POST':
        # Update contact info
        student.contact = request.form.get('contact')
        student.email = request.form.get('email')
        student.address = request.form.get('address')
        
        # Update password if provided
        new_password = request.form.get('new_password')
        confirm_password = request.form.get('confirm_password')
        
        if new_password:
            if new_password == confirm_password:
                student.set_password(new_password)
                flash('Password updated successfully', 'success')
            else:
                flash('Passwords do not match', 'error')
                return redirect(url_for('student_profile'))
        
        try:
            db.session.commit()
            flash('Profile updated successfully', 'success')
        except Exception as e:
            db.session.rollback()
            flash(f'Error updating profile: {str(e)}', 'error')
        
        return redirect(url_for('student_profile'))
    
    return render_template('student_profile.html', student=student)

@app.route('/admin/profile', methods=['GET', 'POST'])
@login_required
def admin_profile():
    """Admin profile page with password change"""
    if request.method == 'POST':
        action = request.form.get('action')
        
        if action == 'change_password':
            current_password = request.form.get('current_password')
            new_password = request.form.get('new_password')
            confirm_password = request.form.get('confirm_password')
            
            # Validate current password
            if not current_user.check_password(current_password):
                flash('Current password is incorrect', 'error')
                return redirect(url_for('admin_profile'))
            
            # Validate new password
            if not new_password or len(new_password) < 6:
                flash('New password must be at least 6 characters', 'error')
                return redirect(url_for('admin_profile'))
            
            if new_password != confirm_password:
                flash('New passwords do not match', 'error')
                return redirect(url_for('admin_profile'))
            
            # Update password
            try:
                current_user.set_password(new_password)
                db.session.commit()
                flash('Password changed successfully!', 'success')
            except Exception as e:
                db.session.rollback()
                flash('Error changing password. Please try again.', 'error')
            
            return redirect(url_for('admin_profile'))
        
        elif action == 'update_info':
            # Update admin username if needed
            new_username = request.form.get('username', '').strip()
            if new_username and new_username != current_user.username:
                # Check if username already exists
                existing = User.query.filter_by(username=new_username).first()
                if existing:
                    flash('Username already taken', 'error')
                else:
                    current_user.username = new_username
                    try:
                        db.session.commit()
                        flash('Profile updated successfully!', 'success')
                    except Exception as e:
                        db.session.rollback()
                        flash('Error updating profile. Please try again.', 'error')
            
            return redirect(url_for('admin_profile'))
    
    # GET request
    mess = current_mess()
    return render_template('admin_profile.html', user=current_user, mess=mess)

@app.route('/settings', methods=['GET', 'POST'])
@login_required
def settings():
    if request.method == 'POST':
        try:
            # Update billing settings
            daily_rate = request.form.get('daily_meal_rate')
            if daily_rate:
                Settings.set_value('daily_meal_rate', daily_rate, 'Daily rate for 2 meals')
            
            # Update UPI payment settings
            upi_id = request.form.get('upi_id')
            if upi_id:
                Settings.set_value('upi_id', upi_id, 'UPI ID for receiving payments')
            
            upi_name = request.form.get('upi_name')
            if upi_name:
                Settings.set_value('upi_name', upi_name, 'Business name shown in UPI apps')
            
            flash('Settings updated successfully!', 'success')
        except Exception as e:
            flash(f'Error updating settings: {str(e)}', 'error')
        return redirect(url_for('settings'))
    
    # GET request - show current settings from Mess
    upi_id_val, upi_name_val = get_effective_upi()
    daily_rate = get_effective_daily_rate()
    
    return render_template('settings.html',
        daily_meal_rate=str(daily_rate),
        upi_id=upi_id_val or app.config.get('UPI_ID', 'merchant@upi'),
        upi_name=upi_name_val or app.config.get('UPI_NAME', 'Mess Management')
    )

# Student Management Routes
@app.route('/student/update/<int:student_id>', methods=['POST'])
@login_required
def update_student(student_id):
    try:
        app.logger.info(f'Updating student {student_id}')
        app.logger.debug(f'Form data: {request.form}')
        
        student = Student.query.get_or_404(student_id)
        if not student:
            return jsonify({'success': False, 'error': 'Student not found'}), 404
        
        # Update student fields
        student.name = request.form.get('name', student.name)
        student.contact = request.form.get('contact', student.contact)
        student.email = request.form.get('email', student.email)
        student.address = request.form.get('address', student.address)
        
        # Validate required fields
        if not student.name:
            return jsonify({'success': False, 'error': 'Name is required'}), 400
            
        db.session.commit()
        app.logger.info(f'Student {student_id} updated successfully')
        return jsonify({
            'success': True, 
            'message': 'Student updated successfully',
            'student': {
                'id': student.id,
                'name': student.name,
                'contact': student.contact,
                'email': student.email,
                'address': student.address
            }
        })
    except Exception as e:
        app.logger.error(f'Error updating student {student_id}: {str(e)}')
        db.session.rollback()
        return error_response('Failed to update student. Please try again.', 500)

@app.route('/students')
@login_required
def students():
    # Get pagination parameters
    page = request.args.get('page', 1, type=int)
    per_page = 50
    
    # Filter by current user's mess and paginate
    pagination = Student.query.filter_by(mess_id=current_user.mess_id)\
        .order_by(Student.id.asc())\
        .paginate(page=page, per_page=per_page, error_out=False)
    
    return render_template('students.html', 
                         students=pagination.items,
                         pagination=pagination)

@app.route('/student/add', methods=['GET', 'POST'])
@login_required
def add_student():
    if request.method == 'POST':
        # Validate CSRF token (handled automatically by Flask-WTF)
        name = request.form.get('name', '').strip()
        contact = request.form.get('contact', '').strip()
        email = request.form.get('email', '').strip()
        address = request.form.get('address', '').strip()
        
        # Validate required fields
        if not name:
            flash('Name is required', 'error')
            return render_template('add_student.html')
            
        # Validate contact number format
        if contact and not contact.isdigit():
            flash('Contact number should contain only digits', 'error')
            return render_template('add_student.html')
        
        # Generate roll number automatically (STU0001, STU0002, etc.)
        last_student = Student.query.order_by(Student.id.desc()).first()
        if last_student and last_student.roll_no and last_student.roll_no.startswith('STU'):
            try:
                last_num = int(last_student.roll_no[3:])
                new_roll_no = f'STU{last_num + 1:04d}'
            except (ValueError, IndexError):
                # If parsing fails, use ID-based approach
                new_roll_no = f'STU{(last_student.id + 1):04d}'
        else:
            # First student or no valid roll_no found, start from STU0001
            new_roll_no = 'STU0001'
            
        # Create new student with mess_id
        student = Student(
            name=name,
            roll_no=new_roll_no,
            contact=contact if contact else None,
            email=email if email else None,
            address=address if address else None,
            mess_id=current_user.mess_id
        )
        
        try:
            # Generate and set a temporary password for the student
            temp_password = generate_temp_password(10)
            student.set_password(temp_password)
            db.session.add(student)
            db.session.commit()
            flash(f'Student added successfully with Roll No: {new_roll_no}. Initial Password: {temp_password}', 'success')
            return redirect(url_for('students'))
        except Exception as e:
            db.session.rollback()
            app.logger.error(f'Error adding student: {str(e)}')
            flash(f'Error adding student: {str(e)}', 'error')
            return render_template('add_student.html')
            
    return render_template('add_student.html')

@app.route('/student/delete/<int:student_id>', methods=['POST'])
@login_required
def delete_student(student_id):
    student = Student.query.get_or_404(student_id)
    if not student:
        flash('Student not found', 'error')
        return redirect(url_for('students'))
        
    try:
        student_name = student.name  # Store name before deletion
        
        # Start transaction
        db.session.begin_nested()
        
        try:
            # Delete associated records first
            attendance_count = Attendance.query.filter_by(student_id=student_id).delete()
            bills_count = Bill.query.filter_by(student_id=student_id).delete()
            
            # Delete student
            db.session.delete(student)
            
            # Commit the nested transaction
            db.session.commit()
            
            # Commit the outer transaction
            db.session.commit()
            
            flash(f'Student {student_name} and all associated records deleted successfully', 'success')
            
        except Exception as inner_error:
            # Rollback the nested transaction
            db.session.rollback()
            raise inner_error
            
    except Exception as e:
        # Rollback the main transaction
        db.session.rollback()
        flash(f'Error deleting student: {str(e)}', 'error')
        app.logger.error(f'Error deleting student {student_id}: {str(e)}')
    
    return redirect(url_for('students'))

@app.route('/student/reset-password/<int:student_id>', methods=['POST'])
@login_required
def reset_student_password(student_id):
    """Generate a new temporary password for a student and return it."""
    student = Student.query.get_or_404(student_id)
    try:
        new_password = generate_temp_password(10)
        student.set_password(new_password)
        db.session.commit()
        return jsonify({
            'success': True,
            'message': f"Password reset for {student.name}",
            'password': new_password
        })
    except Exception as e:
        db.session.rollback()
        return error_response('Failed to reset password. Please try again.', 500)

# Attendance Routes
@app.route('/attendance', methods=['GET', 'POST'])
@login_required
def attendance():
    if request.method == 'POST':
        student_id = request.form.get('student_id')
        attendance_date = request.form.get('date')
        meal_types = request.form.getlist('meal_type')  # Get all selected meal types
        
        if not meal_types:
            flash('Please select at least one meal type', 'error')
            return redirect(url_for('attendance'))
            
        attendance_date = datetime.strptime(attendance_date, '%Y-%m-%d').date() if attendance_date else datetime.now().date()
        success_count = 0
        
        for meal_type in meal_types:
            # Check for duplicate attendance
            existing = Attendance.query.filter_by(
                student_id=student_id,
                date=attendance_date,
                meal_type=meal_type
            ).first()
            
            if existing:
                flash(f'Attendance for {meal_type} already marked', 'warning')
                continue
            
            # Create new attendance record
            attendance = Attendance(
                student_id=student_id,
                date=attendance_date,
                meal_type=meal_type,
                method='manual',
                marked_by=current_user.username,
                timestamp=datetime.now()
            )
            db.session.add(attendance)
            success_count += 1
        
        if success_count > 0:
            try:
                db.session.commit()
                flash(f'Attendance marked successfully for {success_count} meal(s)', 'success')
            except Exception as e:
                db.session.rollback()
                flash(f'Error marking attendance: {str(e)}', 'error')
        
        return redirect(url_for('attendance'))
    
    # GET request handling with filters - scope by mess
    students = Student.query.filter_by(mess_id=current_user.mess_id).order_by(Student.name).all()

    # Query parameters
    date_range = request.args.get('dateRange', 'today')
    meal_type = request.args.get('mealType', 'all')
    sort = request.args.get('sort', 'recent')
    start_date_arg = request.args.get('startDate')
    end_date_arg = request.args.get('endDate')

    # Compute date range
    start_date, end_date = get_date_range(date_range, start_date_arg, end_date_arg)

    # Build query
    query = Attendance.query.join(Student).filter(Attendance.date.between(start_date, end_date))
    if meal_type != 'all':
        query = query.filter(Attendance.meal_type == meal_type)

    # Sorting
    if sort == 'name':
        query = query.order_by(Student.name.asc(), Attendance.timestamp.desc())
    elif sort == 'mealType':
        query = query.order_by(Attendance.meal_type.asc(), Attendance.timestamp.desc())
    else:  # 'recent'
        query = query.order_by(Attendance.timestamp.desc())

    today_attendance = query.all()

    return render_template(
        'attendance.html',
        students=students,
        today_attendance=today_attendance,
        current_meal=get_current_meal_type()
    )

@app.route('/mark-attendance', methods=['POST'])
@login_required
def mark_attendance():
    """Mark student attendance"""
    if request.is_json:
        data = request.get_json()
        student_id = data.get('student_id')
        method = data.get('method', 'manual')
        meal_type = data.get('meal_type') or get_current_meal_type()
    else:
        student_id = request.form.get('student_id')
        method = request.form.get('method', 'manual')
        meal_type = request.form.get('meal_type') or get_current_meal_type()
    
    if not student_id:
        return jsonify({'success': False, 'message': 'Student ID is required'})
    
    # Validate student exists
    student = Student.query.get(student_id)
    if not student:
        return jsonify({'success': False, 'message': 'Student not found'})
    
    # Check for duplicate attendance
    today = date.today()
    existing = Attendance.query.filter_by(
        student_id=student_id,
        date=today,
        meal_type=meal_type
    ).first()
    
    if existing:
        return jsonify({
            'success': False, 
            'message': f'Attendance for {meal_type} already marked'
        })
    
    # Create new attendance record
    attendance = Attendance(
        student_id=student_id,
        date=today,
        meal_type=meal_type,
        method=method,
        marked_by=current_user.username,
        timestamp=datetime.now()
    )
    
    try:
        db.session.add(attendance)
        db.session.commit()
        return jsonify({
            'success': True,
            'message': f'Attendance marked successfully for {student.name}'
        })
    except Exception as e:
        db.session.rollback()
        return error_response('Failed to mark attendance. Please try again.', 500)

@app.route('/delete-attendance/<int:attendance_id>', methods=['POST'])
@login_required
def delete_attendance(attendance_id):
    """Delete an attendance record"""
    attendance = Attendance.query.get_or_404(attendance_id)
    
    try:
        student_name = attendance.student.name
        attendance_date = attendance.date.strftime('%Y-%m-%d')
        meal_type = attendance.meal_type
        
        db.session.delete(attendance)
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': f'Deleted {student_name}\'s {meal_type} attendance for {attendance_date}'
        })
    except Exception as e:
        db.session.rollback()
        return error_response('Failed to delete attendance. Please try again.', 500)

@app.route('/update-attendance/<int:attendance_id>', methods=['POST'])
@login_required
def update_attendance(attendance_id):
    """Update an attendance record's date and/or meal type with duplicate checks"""
    attendance = Attendance.query.get_or_404(attendance_id)

    try:
        # Accept either JSON or form data
        if request.is_json:
            data = request.get_json() or {}
            new_date_str = data.get('date')
            new_meal_type = data.get('meal_type')
        else:
            new_date_str = request.form.get('date')
            new_meal_type = request.form.get('meal_type')

        # Validate inputs (default to current values if not provided)
        if new_date_str:
            try:
                new_date = datetime.strptime(new_date_str, '%Y-%m-%d').date()
            except ValueError:
                return jsonify({'success': False, 'message': 'Invalid date format'}), 400
        else:
            new_date = attendance.date

        if new_meal_type:
            if new_meal_type not in ['lunch', 'dinner']:
                return jsonify({'success': False, 'message': 'Invalid meal type'}), 400
        else:
            new_meal_type = attendance.meal_type

        # If nothing changes, just return success
        if new_date == attendance.date and new_meal_type == attendance.meal_type:
            return jsonify({'success': True, 'message': 'No changes detected'}), 200

        # Duplicate check for same student/date/meal combination
        duplicate = Attendance.query.filter(
            Attendance.student_id == attendance.student_id,
            Attendance.date == new_date,
            Attendance.meal_type == new_meal_type,
            Attendance.id != attendance.id
        ).first()

        if duplicate:
            return jsonify({
                'success': False,
                'message': f'Attendance already exists for {attendance.student.name} on {new_date} ({new_meal_type})'
            }), 409

        # Apply updates
        attendance.date = new_date
        attendance.meal_type = new_meal_type
        attendance.timestamp = datetime.now()

        db.session.commit()

        return jsonify({
            'success': True,
            'message': 'Attendance updated successfully',
            'attendance': attendance.to_dict()
        })
    except Exception as e:
        db.session.rollback()
        return error_response('Failed to update attendance. Please try again.', 500)

@app.route('/create-attendance-session', methods=['POST'])
@login_required
def create_attendance_session():
    """Create a new attendance session and generate QR code"""
    meal_type = request.form.get('meal_type') or get_current_meal_type()
    duration = int(request.form.get('duration', 120))  # Duration in minutes, default 120 (2 hours)
    
    # Generate unique token
    token = secrets.token_urlsafe(32)
    
    # Create session with mess_id
    session = AttendanceSession(
        token=token,
        date=date.today(),
        meal_type=meal_type,
        created_by=current_user.username,
        created_at=datetime.now(),
        expires_at=datetime.now() + timedelta(minutes=duration),
        is_active=True,
        mess_id=current_user.mess_id
    )
    
    try:
        db.session.add(session)
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': f'Session created for {meal_type}',
            'session': session.to_dict(),
            'scan_url': url_for('scan_attendance', token=token, _external=True)
        })
    except Exception as e:
        db.session.rollback()
        return error_response('Failed to create session. Please try again.', 500)

@app.route('/get-session-qr/<int:session_id>')
@login_required
def get_session_qr(session_id):
    """Generate QR code image for attendance session"""
    session = AttendanceSession.query.get_or_404(session_id)
    
    # Verify session belongs to current user's mess
    if session.mess_id != current_user.mess_id:
        abort(403)
    
    # Create scan URL
    scan_url = url_for('scan_attendance', token=session.token, _external=True)
    
    # Generate QR code
    qr = qrcode.QRCode(version=1, box_size=10, border=5)
    qr.add_data(scan_url)
    qr.make(fit=True)
    
    img = qr.make_image(fill_color="black", back_color="white")
    
    # Convert to bytes
    img_io = BytesIO()
    img.save(img_io, 'PNG')
    img_io.seek(0)
    
    return send_file(img_io, mimetype='image/png')

@app.route('/scan/<token>')
def scan_attendance(token):
    """Public page for students to scan and mark their attendance"""
    from flask import session as flask_session
    
    attendance_session = AttendanceSession.query.filter_by(token=token).first()
    
    if not attendance_session:
        return render_template('scan_error.html', message='Invalid QR code')
    
    if not attendance_session.is_valid():
        return render_template('scan_error.html', message='This session has expired')
    
    students = Student.query.order_by(Student.name).all()
    
    # Check if student is logged in
    logged_in_student_id = flask_session.get('student_id')
    
    return render_template('scan_attendance.html', 
                         session=attendance_session, 
                         students=students,
                         logged_in_student_id=logged_in_student_id)

@app.route('/submit-attendance/<token>', methods=['POST'])
@csrf.exempt
def submit_attendance(token):
    """Handle student attendance submission via QR scan"""
    session = AttendanceSession.query.filter_by(token=token).first()
    
    if not session or not session.is_valid():
        return jsonify({'success': False, 'message': 'Session expired or invalid'})
    
    student_id = request.form.get('student_id')
    
    if not student_id:
        return jsonify({'success': False, 'message': 'Please select your name'})
    
    student = Student.query.get(student_id)
    if not student:
        return jsonify({'success': False, 'message': 'Student not found'})
    
    # Check for duplicate attendance
    existing = Attendance.query.filter_by(
        student_id=student_id,
        date=session.date,
        meal_type=session.meal_type
    ).first()
    
    if existing:
        return jsonify({
            'success': False,
            'message': f'You have already marked attendance for {session.meal_type}'
        })
    
    # Create attendance record
    attendance = Attendance(
        student_id=student_id,
        date=session.date,
        meal_type=session.meal_type,
        method='qr_scan',
        marked_by=student.name,
        timestamp=datetime.now(),
        session_id=session.id
    )
    
    try:
        db.session.add(attendance)
        db.session.commit()
        return jsonify({
            'success': True,
            'message': f'Attendance marked successfully for {student.name}!'
        })
    except Exception as e:
        db.session.rollback()
        return error_response('Failed to mark attendance.', 500)

@app.route('/close-session/<int:session_id>', methods=['POST'])
@login_required
def close_session(session_id):
    """Close an attendance session"""
    session = AttendanceSession.query.get_or_404(session_id)
    
    # Verify session belongs to current user's mess
    if session.mess_id != current_user.mess_id:
        abort(403)
    
    session.is_active = False
    
    try:
        db.session.commit()
        return jsonify({
            'success': True,
            'message': 'Session closed successfully'
        })
    except Exception as e:
        db.session.rollback()
        return error_response('Failed to close session. Please try again.', 500)

@app.route('/get-active-sessions')
@login_required
def get_active_sessions():
    """Get all active attendance sessions for current mess"""
    sessions = AttendanceSession.query.filter_by(
        mess_id=current_user.mess_id,
        date=date.today(),
        is_active=True
    ).order_by(AttendanceSession.created_at.desc()).all()
    
    return jsonify({
        'success': True,
        'sessions': [s.to_dict() for s in sessions]
    })

@app.route('/export-attendance')
@login_required
def export_attendance():
    """Export attendance data as CSV"""
    # Get filter parameters
    date_range = request.args.get('dateRange', 'today')
    meal_type = request.args.get('mealType', 'all')
    start_date = request.args.get('startDate')
    end_date = request.args.get('endDate')
    
    # Get date range
    start_date, end_date = get_date_range(date_range, start_date, end_date)
    
    # Query records
    query = Attendance.query.join(Student)
    query = query.filter(Attendance.date.between(start_date, end_date))
    if meal_type != 'all':
        query = query.filter(Attendance.meal_type == meal_type)
    records = query.order_by(Attendance.date, Student.name).all()
    
    # Create CSV
    output = StringIO()
    writer = csv.writer(output)
    writer.writerow(['Date', 'Time', 'Student ID', 'Student Name', 'Meal', 'Method', 'Marked By'])
    
    for record in records:
        writer.writerow([
            record.date.strftime('%Y-%m-%d'),
            record.timestamp.strftime('%H:%M:%S'),
            record.student.id,
            record.student.name,
            record.meal_type.capitalize(),
            record.method.capitalize(),
            record.marked_by
        ])
    
    # Create response (use BytesIO for send_file)
    csv_bytes = BytesIO()
    csv_bytes.write(output.getvalue().encode('utf-8'))
    csv_bytes.seek(0)
    return send_file(
        csv_bytes,
        mimetype='text/csv',
        as_attachment=True,
        download_name=f'attendance_{start_date}_to_{end_date}.csv'
    )

@app.route('/generate_qr/<int:student_id>')
@login_required
def generate_qr(student_id):
    try:
        # Get student data
        student = Student.query.get_or_404(student_id)
        
        # Create QR code data
        data = {
            'student_id': student_id,
            'name': student.name,
            'timestamp': datetime.now().isoformat()
        }
        
        # Convert data to JSON string
        json_data = json.dumps(data)
        
        # Generate QR code with better error correction and size
        qr = qrcode.QRCode(
            version=None,  # Automatically determine version
            error_correction=qrcode.constants.ERROR_CORRECT_H,  # Highest error correction
            box_size=10,
            border=4,
        )
        qr.add_data(json.dumps(data))
        qr.make(fit=True)

        # Create QR code image with better visibility
        img = qr.make_image(fill_color="black", back_color="white")
        
        # Save QR code to bytes
        img_io = BytesIO()
        img.save(img_io, 'PNG')
        img_io.seek(0)
        
        return send_file(
            img_io,
            mimetype='image/png',
            as_attachment=False,
            download_name=f'qr_code_{student.name.lower().replace(" ", "_")}.png'
        )
        
    except Exception as e:
        flash(f'Error generating QR code: {str(e)}', 'error')
        return redirect(url_for('students'))
# Billing Routes
@app.route('/billing')
@login_required
def billing():
    try:
        # Get all bills with student information for current mess only, sorted by student ID
        bills = Bill.query.join(Student)\
            .filter(Student.mess_id == current_user.mess_id)\
            .order_by(Student.id.asc(), Bill.generated_on.desc()).all()
        students = Student.query.filter_by(mess_id=current_user.mess_id)\
            .order_by(Student.id.asc()).all()
        
        # Get current month and year for default form values
        current_month = datetime.now().month
        current_year = datetime.now().year
        
        # Calculate total, paid, and pending amounts
        total_amount = sum(bill.amount for bill in bills)
        paid_amount = sum(bill.amount for bill in bills if bill.paid)
        pending_amount = total_amount - paid_amount
        
        return render_template('billing.html',
                             bills=bills,
                             students=students,
                             current_month=current_month,
                             current_year=current_year,
                             total_amount=total_amount,
                             paid_amount=paid_amount,
                             pending_amount=pending_amount)
    except Exception as e:
        flash(f'Error loading billing page: {str(e)}', 'error')
        return redirect(url_for('dashboard'))

@app.route('/generate-bill', methods=['POST'])
@login_required
def generate_bill():
    try:
        # Validate input data
        student_id = request.form.get('student_id')
        month = request.form.get('month')
        year = request.form.get('year')
        
        if not all([student_id, month, year]):
            return jsonify({
                'success': False,
                'message': 'Please provide all required fields'
            }), 400
            
        try:
            student_id = int(student_id)
            month = int(month)
            year = int(year)
        except ValueError:
            return jsonify({
                'success': False,
                'message': 'Invalid input values'
            }), 400
            
        # Validate student exists
        student = Student.query.get(student_id)
        if not student:
            return jsonify({
                'success': False,
                'message': 'Student not found'
            }), 404

        # Check if bill already exists
        existing_bill = Bill.query.filter_by(
            student_id=student_id,
            month=month,
            year=year
        ).first()

        if existing_bill:
            return jsonify({
                'success': False,
                'message': f'Bill already exists for {student.name} for {month}/{year}'
            }), 409

        # Get attendance for the given month
        start_date = datetime(year, month, 1).date()
        if month == 12:
            end_date = datetime(year + 1, 1, 1).date()
        else:
            end_date = datetime(year, month + 1, 1).date()

        attendance_records = Attendance.query.filter(
            Attendance.student_id == student_id,
            Attendance.date >= start_date,
            Attendance.date < end_date
        ).all()

        # Calculate total meals
        total_meals = len(attendance_records)

        # If no attendance records found
        if total_meals == 0:
            return jsonify({
                'success': False,
                'message': f'No attendance records found for {student.name} in {month}/{year}'
            }), 404

        # Calculate bill amount
        # Get daily rate from mess settings
        daily_rate = get_effective_daily_rate()
        meal_rate = daily_rate / 2  # Rate per meal (assuming 2 meals per day)
        total_amount = round(total_meals * meal_rate, 2)

        try:
            # Create new bill
            new_bill = Bill(
                student_id=student_id,
                month=month,
                year=year,
                amount=total_amount,
                days_present=total_meals,  # Store number of meals
                daily_rate=meal_rate,  # Store rate per meal
                generated_on=datetime.now(),
                paid=False
            )

            db.session.add(new_bill)
            db.session.commit()

            return jsonify({
                'success': True,
                'message': f'Bill generated successfully for {student.name}'
            }), 201
            
        except Exception as e:
            db.session.rollback()
            return error_response('Failed to save bill. Please try again.', 500)
            
    except Exception as e:
        return error_response('Server error. Please try again.', 500)

@app.route('/bill/<int:bill_id>')
@login_required
def get_bill(bill_id):
    try:
        bill = Bill.query.get_or_404(bill_id)
        
        # Format date according to local time
        generated_on = bill.generated_on.strftime('%Y-%m-%d %H:%M:%S') if bill.generated_on else None
        
        # Get month name
        months = ['January', 'February', 'March', 'April', 'May', 'June',
                 'July', 'August', 'September', 'October', 'November', 'December']
        month_name = months[bill.month - 1] if 1 <= bill.month <= 12 else 'Unknown'
        
        payments = [payment.to_dict() for payment in sorted(bill.payments, key=lambda p: p.created_at or datetime.min, reverse=True)]

        return jsonify({
            'id': bill.id,
            'student': {
                'name': bill.student.name,
                'roll_no': getattr(bill.student, 'roll_no', 'N/A'),
                'department': getattr(bill.student, 'department', 'N/A'),
                'contact': bill.student.contact or 'N/A',
                'email': bill.student.email or 'N/A'
            },
            'month': bill.month,
            'month_name': month_name,
            'year': bill.year,
            'amount': round(bill.amount, 2),
            'days_present': bill.days_present,
            'daily_rate': bill.daily_rate,
            'generated_on': generated_on,
            'paid': bill.paid,
            'payment_status': bill.payment_status,
            'payments': payments
        })
    except Exception as e:
        return error_response('Failed to retrieve bill details.', 500)


@app.route('/bill/<int:bill_id>/payments')
@login_required
def get_bill_payments(bill_id):
    bill = Bill.query.get_or_404(bill_id)
    payments = [payment.to_dict() for payment in sorted(bill.payments, key=lambda p: p.created_at or datetime.min, reverse=True)]
    return jsonify({'success': True, 'payments': payments, 'bill': {'id': bill.id, 'paid': bill.paid}})

@app.route('/payment/<int:payment_id>/update', methods=['POST'])
@login_required
def update_payment_status(payment_id):
    payment = Payment.query.get_or_404(payment_id)
    
    # Verify payment belongs to current user's mess
    if payment.student.mess_id != current_user.mess_id:
        abort(403)
    
    data = request.get_json(silent=True) or {}
    action = (data.get('action') or '').lower()
    if action not in {'verify', 'reject'}:
        return jsonify({'success': False, 'message': 'Unsupported action.'}), 400

    if action == 'verify':
        if payment.bill.paid:
            return jsonify({'success': False, 'message': 'Bill is already marked paid.'}), 400
        payment.status = 'verified'
        payment.verified_at = datetime.utcnow()
        payment.verified_by = current_user.username
        payment.bill.paid = True
        for other_payment in payment.bill.payments:
            if other_payment.id != payment.id and other_payment.status == 'submitted':
                other_payment.status = 'rejected'
        message = f'Payment #{payment.id} verified and bill marked as paid.'
    else:
        if payment.status == 'verified':
            return jsonify({'success': False, 'message': 'Cannot reject a verified payment.'}), 400
        payment.status = 'rejected'
        payment.verified_at = datetime.utcnow()
        payment.verified_by = current_user.username
        message = f'Payment #{payment.id} rejected.'

    try:
        db.session.commit()
        return jsonify({'success': True, 'message': message})
    except Exception as exc:
        db.session.rollback()
        return jsonify({'success': False, 'message': f'Failed to update payment: {exc}'}), 500


@app.route('/bill/<int:bill_id>/mark-paid', methods=['POST'])
@login_required
def mark_bill_paid(bill_id):
    try:
        bill = Bill.query.get_or_404(bill_id)
        
        # Check if bill is already paid
        if bill.paid:
            return jsonify({
                'success': False,
                'message': 'Bill is already marked as paid'
            }), 400

        data = request.get_json(silent=True) or {}
        payment_id = data.get('payment_id')
        method = data.get('method')
        reference = data.get('reference')
        notes = data.get('notes')

        if payment_id:
            payment = Payment.query.get(payment_id)
            if not payment or payment.bill_id != bill.id:
                return jsonify({'success': False, 'message': 'Invalid payment reference provided.'}), 400
            if payment.status == 'verified':
                return jsonify({'success': False, 'message': 'Payment already verified.'}), 400
            payment.status = 'verified'
            payment.verified_at = datetime.utcnow()
            payment.verified_by = current_user.username
            # Mark other pending payments as rejected to avoid duplicates
            for other_payment in bill.payments:
                if other_payment.id != payment.id and other_payment.status == 'submitted':
                    other_payment.status = 'rejected'
        else:
            manual_payment = Payment(
                bill_id=bill.id,
                student_id=bill.student_id,
                amount=bill.amount,
                method=(method or 'manual'),
                reference=reference or f'MANUAL-{datetime.utcnow().strftime("%Y%m%d%H%M%S")}',
                notes=notes,
                status='verified',
                verified_at=datetime.utcnow(),
                verified_by=current_user.username
            )
            db.session.add(manual_payment)
        
        bill.paid = True
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': f'Bill #{bill.id} for {bill.student.name} marked as paid'
        })
    except Exception as e:
        db.session.rollback()
        return error_response('Failed to update bill payment status.', 500)

@app.route('/bill/<int:bill_id>', methods=['DELETE'])
@login_required
def delete_bill(bill_id):
    try:
        bill = Bill.query.get_or_404(bill_id)
        
        # Store bill info for confirmation message
        student_name = bill.student.name
        bill_month = bill.month
        bill_year = bill.year
        
        # Check if bill is already paid
        if bill.paid:
            return jsonify({
                'success': False,
                'message': 'Cannot delete a paid bill'
            }), 400
            
        db.session.delete(bill)
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': f'Bill for {student_name} ({bill_month}/{bill_year}) deleted successfully'
        })
    except Exception as e:
        db.session.rollback()
        return error_response('Failed to delete bill.', 500)

def init_db():
    """Initialize database and create admin user if it doesn't exist"""
    try:
        # Ensure SQLite database directory exists
        database_uri = app.config['SQLALCHEMY_DATABASE_URI']
        if database_uri.startswith('sqlite:///'):
            db_relative = database_uri.replace('sqlite:///', '', 1)
            db_path = os.path.join(app.root_path, db_relative)
            db_dir = os.path.dirname(db_path)
            os.makedirs(db_dir, exist_ok=True)
        
        with app.app_context():
            # Create tables if they don't exist
            db.create_all()

            # Ensure at least one mess exists (for legacy single-mess installs)
            from sqlalchemy import select
            if not Mess.query.first():
                default_mess = Mess(name='Default Mess', daily_meal_rate=100.0, upi_id=app.config.get('UPI_ID'), upi_name=app.config.get('UPI_NAME'))
                db.session.add(default_mess)
                db.session.flush()
                print('Created default mess record.')
            
            # Check if admin user exists
            admin = User.query.filter_by(username='admin').first()
            if not admin:
                # Create admin user only if it doesn't exist
                # Attach to first mess
                first_mess = Mess.query.first()
                admin = User(username='admin', is_admin=True, mess_id=first_mess.id if first_mess else None)
                admin.set_password('admin123')
                db.session.add(admin)
                db.session.commit()
                print("Admin user created successfully.")
            else:
                print("Admin user already exists.")
            
            # Initialize default settings
            if not Settings.query.filter_by(key='daily_meal_rate').first():
                Settings.set_value('daily_meal_rate', '100.0', 'Daily rate for 2 meals (lunch + dinner)')
                print("Default settings created.")
            
            print("Database initialized successfully.")
            
    except Exception as e:
        print(f"Error initializing database: {str(e)}")
        raise

# Initialize database
def create_app():
    init_db()
    return app


if __name__ == '__main__':
    print("Initializing database...")
    init_db()
    print("Starting Flask application...")
    app.run(debug=True)
