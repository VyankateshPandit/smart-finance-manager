from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
from flask_mysqldb import MySQL
import MySQLdb.cursors
from flask_mail import Mail, Message
from flask_cors import CORS
import re
import os
from werkzeug.security import generate_password_hash, check_password_hash
from dotenv import load_dotenv
from chatboatservice import generate_financial_advice
from expensemanagement import get_user_expenses, add_user_expense, delete_user_expense

from urllib.parse import quote_plus
from flask_migrate import Migrate
from models import db, User, Expense
from brevoemailservice import send_otp_email

load_dotenv()

app = Flask(__name__)

# Enable CORS for React Frontend
# Add your deployed frontend URL to FRONTEND_URL in .env (e.g. https://your-site.netlify.app)
_frontend_url = os.getenv("FRONTEND_URL", "")
_allowed_origins = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://localhost:3000",
    "http://127.0.0.1:3000",
]
if _frontend_url:
    _allowed_origins.append(_frontend_url)

CORS(app,
     supports_credentials=True,
     resources={r"/*": {
         "origins": _allowed_origins,
         "allow_headers": ["Content-Type", "Authorization", "Cookie", "X-Requested-With"],
         "methods": ["GET", "POST", "PUT", "DELETE", "OPTIONS"],
         "supports_credentials": True
     }}
)

@app.after_request
def add_cors_headers(response):
    origin = request.headers.get('Origin')
    if origin in _allowed_origins:
        response.headers['Access-Control-Allow-Origin'] = origin
        response.headers['Access-Control-Allow-Credentials'] = 'true'
        response.headers['Access-Control-Allow-Headers'] = 'Content-Type, Authorization, Cookie, X-Requested-With'
        response.headers['Access-Control-Allow-Methods'] = 'GET, POST, PUT, DELETE, OPTIONS'
    return response

# Secret key for mail and session
app.secret_key = os.getenv("SECRET_KEY", "sfm_super_secret_jwt_and_session_key_2026")

# Session Cookie Configuration for Cross-Origin Requests
_is_production = bool(os.getenv("FRONTEND_URL", ""))  # True when a prod frontend URL is set
app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE='None' if _is_production else 'Lax',
    SESSION_COOKIE_SECURE=_is_production,  # Must be True with SameSite=None
)

# MySQL Configuration for flask-mysqldb
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = int(os.getenv("DB_PORT", 15106))
DB_USER = os.getenv("DB_USER", "root")
DB_PASS = os.getenv("DB_PASS", "")
DB_NAME = os.getenv("DB_NAME", "defaultdb")

app.config['MYSQL_HOST'] = DB_HOST
app.config['MYSQL_PORT'] = DB_PORT
app.config['MYSQL_USER'] = DB_USER
app.config['MYSQL_PASSWORD'] = DB_PASS
app.config['MYSQL_DB'] = DB_NAME

# Flask-SQLAlchemy & Flask-Migrate Configuration
encoded_pass = quote_plus(DB_PASS) if DB_PASS else ""
if encoded_pass:
    app.config['SQLALCHEMY_DATABASE_URI'] = f"mysql+mysqldb://{DB_USER}:{encoded_pass}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
else:
    app.config['SQLALCHEMY_DATABASE_URI'] = f"mysql+mysqldb://{DB_USER}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db.init_app(app)
migrate = Migrate(app, db)

from datetime import datetime, timedelta
import random

# Auto-create tables and ensure OTP verification columns exist
with app.app_context():
    try:
        db.create_all()
        # Verify / add columns for OTP verification if needed
        from sqlalchemy import inspect, text
        inspector = inspect(db.engine)
        if 'users' in inspector.get_table_names():
            cols = [c['name'] for c in inspector.get_columns('users')]
            with db.engine.connect() as conn:
                if 'is_verified' not in cols:
                    conn.execute(text("ALTER TABLE users ADD COLUMN is_verified BOOLEAN NOT NULL DEFAULT 0"))
                if 'otp_code' not in cols:
                    conn.execute(text("ALTER TABLE users ADD COLUMN otp_code VARCHAR(10) NULL"))
                if 'otp_expiry' not in cols:
                    conn.execute(text("ALTER TABLE users ADD COLUMN otp_expiry DATETIME NULL"))
                conn.commit()
        print(" Database schema and columns verified successfully.")
    except Exception as e:
        print(f" Database connection/init note: {e}")

# Asynchronously sync initial financial knowledge base with Pinecone (if configured)
import threading
from loadembeddings import sync_initial_knowledge_base
threading.Thread(target=sync_initial_knowledge_base, daemon=True).start()

# Mail configuration (Brevo / SMTP)
app.config['MAIL_SERVER'] = os.getenv("MAIL_SERVER", 'smtp-relay.brevo.com')
app.config['MAIL_PORT'] = int(os.getenv("MAIL_PORT", 587))
app.config['MAIL_USE_TLS'] = os.getenv("MAIL_USE_TLS", "true").lower() in ("true", "1", "yes")
app.config['MAIL_USE_SSL'] = os.getenv("MAIL_USE_SSL", "false").lower() in ("true", "1", "yes")
app.config['MAIL_USERNAME'] = os.getenv("MAIL_USERNAME", "")
app.config['MAIL_PASSWORD'] = os.getenv("MAIL_PASSWORD", "")
app.config['MAIL_DEFAULT_SENDER'] = os.getenv("MAIL_DEFAULT_SENDER", os.getenv("MAIL_USERNAME", "noreply@smartfinancemanager.com"))

mail = Mail(app)
mysql = MySQL(app)

# Helper function to get current logged in user id
def get_current_user_id():
    return session.get('id') or session.get('user_id')

# ==============================================================================
# REST API ENDPOINTS (FOR REACT FRONTEND)
# ==============================================================================

@app.route('/api/auth/me', methods=['GET'])
def api_me():
    user_id = get_current_user_id()
    if not user_id:
        return jsonify({"authenticated": False, "user": None}), 200
    
    try:
        cursor = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
        cursor.execute('SELECT id, fname, lname, email, is_verified, created_at FROM users WHERE id = %s', (user_id,))
        user = cursor.fetchone()
        if user:
            return jsonify({
                "authenticated": True,
                "user": {
                    "id": user['id'],
                    "fname": user['fname'],
                    "lname": user['lname'],
                    "email": user['email'],
                    "is_verified": bool(user.get('is_verified', 0)),
                    "created_at": str(user['created_at']) if user.get('created_at') else None
                }
            }), 200
    except Exception as e:
        return jsonify({"authenticated": False, "error": str(e)}), 500
    
    return jsonify({"authenticated": False, "user": None}), 200


@app.route('/api/auth/login', methods=['POST'])
def api_login():
    data = request.get_json() or request.form
    email = data.get('email', '').strip().lower()
    password = data.get('password', '')

    if not email or not password:
        return jsonify({"success": False, "error": "Email and password are required."}), 400

    try:
        cursor = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
        cursor.execute('SELECT * FROM users WHERE email = %s', (email,))
        account = cursor.fetchone()

        if account and check_password_hash(account['password'], password):
            # Check if email is verified
            if not account.get('is_verified'):
                # Generate new OTP code and send email
                otp_code = f"{random.randint(100000, 999999)}"
                otp_expiry = datetime.utcnow() + timedelta(minutes=10)
                cursor.execute('UPDATE users SET otp_code = %s, otp_expiry = %s WHERE id = %s', (otp_code, otp_expiry, account['id']))
                mysql.connection.commit()
                send_otp_email(mail, account['email'], account['fname'], otp_code)

                return jsonify({
                    "success": False,
                    "require_otp": True,
                    "email": account['email'],
                    "error": "Your email is not verified yet. We have sent a new verification code to your email."
                }), 403

            session['loggedin'] = True
            session['id'] = account['id']
            session['user_id'] = account['id']
            session['email'] = account['email']
            session.modified = True

            return jsonify({
                "success": True,
                "message": "Login successful!",
                "user": {
                    "id": account['id'],
                    "fname": account['fname'],
                    "lname": account['lname'],
                    "email": account['email']
                }
            }), 200
        else:
            return jsonify({"success": False, "error": "Incorrect email or password."}), 401
    except Exception as e:
        return jsonify({"success": False, "error": f"Database error: {str(e)}"}), 500


@app.route('/api/auth/signup', methods=['POST'])
def api_signup():
    data = request.get_json() or request.form
    fname = (data.get('fname') or data.get('first_name', '')).strip()
    lname = (data.get('lname') or data.get('last_name', '')).strip()
    email = data.get('email', '').strip().lower()
    password = data.get('password', '')
    confirm_password = data.get('confirm_password', '')

    if not fname or not lname or not email or not password:
        return jsonify({"success": False, "error": "Please fill out all fields!"}), 400

    if not re.match(r'[^@]+@[^@]+\.[^@]+', email):
        return jsonify({"success": False, "error": "Invalid email address format."}), 400

    if len(password) < 6:
        return jsonify({"success": False, "error": "Password must be at least 6 characters long."}), 400

    if confirm_password and password != confirm_password:
        return jsonify({"success": False, "error": "Passwords do not match."}), 400

    otp_code = f"{random.randint(100000, 999999)}"
    otp_expiry = datetime.utcnow() + timedelta(minutes=10)
    hashed_password = generate_password_hash(password)

    try:
        cursor = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
        cursor.execute('SELECT * FROM users WHERE email = %s', (email,))
        existing_account = cursor.fetchone()

        if existing_account:
            if existing_account.get('is_verified'):
                return jsonify({"success": False, "error": "An account with this email already exists!"}), 409
            else:
                # Update unverified user with new credentials and freshly generated OTP
                cursor.execute('''
                    UPDATE users 
                    SET fname = %s, lname = %s, password = %s, otp_code = %s, otp_expiry = %s 
                    WHERE email = %s
                ''', (fname, lname, hashed_password, otp_code, otp_expiry, email))
                mysql.connection.commit()
        else:
            cursor.execute('''
                INSERT INTO users (fname, lname, email, password, is_verified, otp_code, otp_expiry) 
                VALUES (%s, %s, %s, %s, 0, %s, %s)
            ''', (fname, lname, email, hashed_password, otp_code, otp_expiry))
            mysql.connection.commit()

        # Send OTP email
        email_sent, mail_err = send_otp_email(mail, email, fname, otp_code)

        return jsonify({
            "success": True,
            "require_otp": True,
            "email": email,
            "message": f"Verification code sent to {email}. Please enter it to activate your account.",
            "email_sent": email_sent
        }), 200

    except Exception as e:
        mysql.connection.rollback()
        return jsonify({"success": False, "error": f"Database error: {str(e)}"}), 500


@app.route('/api/auth/verify-otp', methods=['POST'])
def api_verify_otp():
    data = request.get_json() or request.form
    email = (data.get('email') or '').strip().lower()
    otp = (data.get('otp') or data.get('otp_code') or '').strip()

    if not email or not otp:
        return jsonify({"success": False, "error": "Email and verification code are required."}), 400

    try:
        cursor = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
        cursor.execute('SELECT * FROM users WHERE email = %s', (email,))
        user = cursor.fetchone()

        if not user:
            return jsonify({"success": False, "error": "No user found with this email."}), 404

        if user.get('is_verified') and not user.get('otp_code'):
            return jsonify({"success": True, "message": "Email is already verified. Please log in."}), 200

        user_otp = str(user.get('otp_code') or '').strip()
        expiry = user.get('otp_expiry')

        if not user_otp or user_otp != otp:
            return jsonify({"success": False, "error": "Invalid verification code. Please check and try again."}), 400

        if expiry and datetime.utcnow() > expiry:
            return jsonify({"success": False, "error": "Verification code has expired. Please request a new one."}), 400

        # Activate user account
        cursor.execute('UPDATE users SET is_verified = 1, otp_code = NULL, otp_expiry = NULL WHERE id = %s', (user['id'],))
        mysql.connection.commit()

        # Automatically log in the user
        session['loggedin'] = True
        session['id'] = user['id']
        session['user_id'] = user['id']
        session['email'] = user['email']
        session.modified = True

        return jsonify({
            "success": True,
            "message": "Email verified successfully!",
            "user": {
                "id": user['id'],
                "fname": user['fname'],
                "lname": user['lname'],
                "email": user['email']
            }
        }), 200

    except Exception as e:
        mysql.connection.rollback()
        return jsonify({"success": False, "error": f"Database error: {str(e)}"}), 500


@app.route('/api/auth/resend-otp', methods=['POST'])
def api_resend_otp():
    data = request.get_json() or request.form
    email = (data.get('email') or '').strip().lower()

    if not email:
        return jsonify({"success": False, "error": "Email address is required."}), 400

    try:
        cursor = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
        cursor.execute('SELECT * FROM users WHERE email = %s', (email,))
        user = cursor.fetchone()

        if not user:
            return jsonify({"success": False, "error": "No account found with this email."}), 404

        if user.get('is_verified'):
            return jsonify({"success": False, "error": "This email is already verified. You can log in directly."}), 400

        otp_code = f"{random.randint(100000, 999999)}"
        otp_expiry = datetime.utcnow() + timedelta(minutes=10)

        cursor.execute('UPDATE users SET otp_code = %s, otp_expiry = %s WHERE id = %s', (otp_code, otp_expiry, user['id']))
        mysql.connection.commit()

        email_sent, mail_err = send_otp_email(mail, user['email'], user['fname'], otp_code)

        return jsonify({
            "success": True,
            "message": f"A new verification code has been sent to {email}.",
            "email_sent": email_sent
        }), 200

    except Exception as e:
        mysql.connection.rollback()
        return jsonify({"success": False, "error": f"Database error: {str(e)}"}), 500


@app.route('/api/auth/logout', methods=['POST', 'GET'])
def api_logout():
    session.pop('loggedin', None)
    session.pop('id', None)
    session.pop('user_id', None)
    session.pop('email', None)
    return jsonify({"success": True, "message": "Logged out successfully."}), 200


@app.route('/api/profile', methods=['GET'])
def api_profile():
    user_id = get_current_user_id()
    if not user_id:
        return jsonify({"success": False, "error": "Unauthorized"}), 401

    try:
        cursor = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
        cursor.execute('SELECT id, fname, lname, email, created_at FROM users WHERE id = %s', (user_id,))
        user_details = cursor.fetchone()

        if not user_details:
            return jsonify({"success": False, "error": "User not found"}), 404

        return jsonify({
            "success": True,
            "user": {
                "id": user_details['id'],
                "fname": user_details['fname'],
                "lname": user_details['lname'],
                "email": user_details['email'],
                "created_at": str(user_details['created_at']) if user_details.get('created_at') else None
            }
        }), 200
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route('/api/delete_account', methods=['DELETE', 'POST'])
def api_delete_account():
    user_id = get_current_user_id()
    if not user_id:
        return jsonify({"success": False, "error": "Unauthorized"}), 401

    try:
        cursor = mysql.connection.cursor()
        cursor.execute("DELETE FROM expenses WHERE user_id = %s", (user_id,))
        cursor.execute("DELETE FROM users WHERE id = %s", (user_id,))
        mysql.connection.commit()
        cursor.close()

        session.clear()
        return jsonify({"success": True, "message": "Account deleted successfully."}), 200
    except Exception as e:
        mysql.connection.rollback()
        return jsonify({"success": False, "error": str(e)}), 500


@app.route('/api/expenses', methods=['GET'])
def api_get_expenses():
    user_id = get_current_user_id()
    if not user_id:
        return jsonify({"success": False, "error": "Unauthorized"}), 401

    try:
        expense_data, total = get_user_expenses(user_id)
        return jsonify({
            "success": True,
            "expense_data": expense_data,
            "total": total
        }), 200
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route('/api/expenses/add', methods=['POST'])
def api_add_expense():
    user_id = get_current_user_id()
    if not user_id:
        return jsonify({"success": False, "error": "Unauthorized"}), 401

    data = request.get_json() or request.form
    try:
        amount = int(float(data.get('amount') or data.get('expenseAmount', 0)))
        category = data.get('category') or data.get('expenseCategory', '')

        expense_data, total, message = add_user_expense(user_id, amount, category)
        return jsonify({
            "success": True,
            "message": message,
            "expense_data": expense_data,
            "total": total
        }), 200
    except ValueError as ve:
        return jsonify({"success": False, "error": str(ve)}), 400
    except Exception as e:
        db.session.rollback()
        return jsonify({"success": False, "error": str(e)}), 500


@app.route('/api/expenses/delete', methods=['POST'])
def api_delete_expense():
    user_id = get_current_user_id()
    if not user_id:
        return jsonify({"success": False, "error": "Unauthorized"}), 401

    data = request.get_json() or request.form
    try:
        amount = int(float(data.get('amount') or data.get('deleteAmount', 0)))
        category = data.get('category') or data.get('deleteCategorySelect', '')

        expense_data, total, message = delete_user_expense(user_id, amount, category)
        return jsonify({
            "success": True,
            "message": message,
            "expense_data": expense_data,
            "total": total
        }), 200
    except ValueError as ve:
        return jsonify({"success": False, "error": str(ve)}), 400
    except Exception as e:
        db.session.rollback()
        return jsonify({"success": False, "error": str(e)}), 500

@app.route("/api/ask_ai", methods=["POST"])
def api_ask_ai():
    try:
        user_id = get_current_user_id()
        data = request.get_json() or {}
        prompt = data.get("prompt", "")
        expense_context = data.get("expense_data")

        if not prompt or not prompt.strip():
            return jsonify({"success": False, "error": "Prompt cannot be empty."}), 400

        result = generate_financial_advice(prompt, expense_context, user_id=user_id)
        if isinstance(result, dict):
            return jsonify({
                "success": True,
                "response": result.get("response"),
                "structured": result.get("structured")
            }), 200

        return jsonify({"success": True, "response": result}), 200
    except ValueError as ve:
        print(f"\n❌ [/api/ask_ai] Bad Request: {ve}")
        return jsonify({"success": False, "error": str(ve)}), 400
    except Exception as e:
        import traceback
        err_trace = traceback.format_exc()
        print(f"\n❌ [/api/ask_ai] 500 Internal Server Error:\n{err_trace}")
        return jsonify({
            "success": False,
            "error": str(e),
            "traceback": err_trace
        }), 500


@app.route('/api/contact', methods=['POST'])
def api_contact():
    data = request.get_json() or request.form
    name = data.get('name', '').strip()
    email = data.get('email', '').strip()
    subject = data.get('subject', '').strip()
    message_text = data.get('message', '').strip()

    if not name or not email or not subject or not message_text:
        return jsonify({"success": False, "error": "Please fill out all contact form fields."}), 400

    try:
        msg = Message(
            subject=f"[SFM Contact] {subject}",
            sender=app.config['MAIL_USERNAME'],
            recipients=['vyankateshpandit1511@gmail.com']
        )
        msg.body = f"Name: {name}\nEmail: {email}\nSubject: {subject}\n\nMessage:\n{message_text}"
        mail.send(msg)
        return jsonify({"success": True, "message": "Your message has been sent! We will contact you soon."}), 200
    except Exception as e:
        return jsonify({"success": False, "error": f"Error sending email: {str(e)}"}), 500


# ==============================================================================
# LEGACY SSR ROUTES (FOR BACKWARD COMPATIBILITY)
# ==============================================================================

@app.route('/')
def index():
    if 'loggedin' in session:
        return redirect(url_for('dashboard'))
    return render_template('login.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        cursor = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
        cursor.execute('SELECT * FROM users WHERE email = %s', (email,))
        account = cursor.fetchone()
        if account and check_password_hash(account['password'], password):
            session['loggedin'] = True
            session['id'] = account['id']
            session['user_id'] = account['id']
            session['email'] = account['email']
            return redirect(url_for('dashboard'))
        else:
            flash('Incorrect email or password', 'danger')
    return render_template('login.html')

@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        fname = request.form.get('first_name')
        lname = request.form.get('last_name')
        email = request.form.get('email')
        password = request.form.get('password')
        confirm_password = request.form.get('confirm_password')
        cursor = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
        cursor.execute('SELECT * FROM users WHERE email = %s', (email,))
        account = cursor.fetchone()
        if account:
            flash('Account already exists!', 'danger')
        elif not re.match(r'[^@]+@[^@]+\.[^@]+', email):
            flash('Invalid email address!', 'danger')
        elif password != confirm_password:
            flash('Passwords do not match!', 'danger')
        elif not email or not password:
            flash('Please fill out all fields!', 'danger')
        else:
            hashed_password = generate_password_hash(password)
            cursor.execute('INSERT INTO users (fname,lname,email, password) VALUES (%s,%s,%s, %s)', 
                           (fname,lname,email, hashed_password))
            mysql.connection.commit()
            flash('Account created successfully!', 'success')
            return redirect(url_for('login'))
    return render_template('signup.html')

@app.route('/profile')
def profile():
    if 'loggedin' not in session:
        return redirect(url_for('login'))
    cursor = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
    cursor.execute('SELECT * FROM users WHERE id = %s', (session['id'],))
    user_details = cursor.fetchone()
    return render_template('profile.html', 
                           email=session.get('email'), 
                           user_details=user_details,
                           first_name=user_details.get('fname', '') if user_details else '',
                           last_name=user_details.get('lname', '') if user_details else '')

@app.route('/graph')
def graph():
    if 'loggedin' not in session:
        return redirect(url_for('login'))
    user_id = session['id']
    expense_data, total = get_user_expenses(user_id)
    return render_template('graph.html', expense_data=expense_data, total=total)

@app.route('/contact', methods=['GET', 'POST'])
def contact():
    if 'loggedin' not in session:
        return redirect(url_for('login'))
    message = ''
    if request.method == 'POST':
        name = request.form.get('name')
        email = request.form.get('email')
        subject = request.form.get('subject')
        message_text = request.form.get('message')
        if not name or not email or not subject or not message_text:
            message = 'Please fill out all fields'
        else:
            try:
                msg = Message(subject=subject, sender=app.config['MAIL_USERNAME'], recipients=['vyankateshpandit1511@gmail.com'])
                msg.body = f"Name: {name}\nEmail: {email}\nMessage: {message_text}"
                mail.send(msg)
                message = 'Your message has been sent! We will contact you soon.'
            except Exception as e:
                message = f'Error sending email: {str(e)}'
    cursor = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
    cursor.execute('SELECT * FROM users WHERE id = %s', (session['id'],))
    user_details = cursor.fetchone()
    return render_template('contact.html', email=session.get('email'), user_details=user_details,
                           first_name=user_details.get('fname', '') if user_details else '',
                           last_name=user_details.get('lname', '') if user_details else '', message=message)

@app.route('/expenses', methods=["GET", "POST"])
def expenses():
    if 'loggedin' not in session:
        return redirect(url_for('login'))
    user_id = session['id']
    if request.method == "POST":
        if "expenseAmount" in request.form and "expenseCategory" in request.form:
            try:
                amount = int(float(request.form["expenseAmount"]))
                category = request.form["expenseCategory"]
                add_user_expense(user_id, amount, category)
            except Exception:
                pass
    expense_data, total = get_user_expenses(user_id)
    return render_template('expenses.html', expense_data=expense_data, total=total)

@app.route('/ask_ai', methods=["POST"])
def ask_ai():
    return api_ask_ai()

@app.route('/dashboard')
def dashboard():
    if 'loggedin' not in session:
        return redirect(url_for('login'))
    cursor = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
    cursor.execute('SELECT * FROM users WHERE id = %s', (session['id'],))
    user_details = cursor.fetchone()
    return render_template('dashboard.html', email=session.get('email'), user_details=user_details,
                           first_name=user_details.get('fname', '') if user_details else '',
                           last_name=user_details.get('lname', '') if user_details else '')

@app.route('/sip_cal')
def sip_cal():
    if 'loggedin' not in session:
        return redirect(url_for('login'))
    return render_template('sip_cal.html')

@app.route('/lumsum_cal')
def lumsum_cal():
    if 'loggedin' not in session:
        return redirect(url_for('login'))
    return render_template('lumsum_cal.html')

@app.route('/delete_account')
def delete_account():
    if 'loggedin' not in session:
        return redirect(url_for('login'))
    return api_delete_account()

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

if __name__ == '__main__':
    app.run(debug=True, port=5000)
