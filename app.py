from flask import Flask, render_template, request, redirect, url_for, session, flash ,jsonify
from flask_mysqldb import MySQL
import MySQLdb.cursors
from flask_mail import Mail, Message
import re
import os
import google.generativeai as genai
from werkzeug.security import generate_password_hash, check_password_hash
import mysql.connector 
from dotenv import load_dotenv
app = Flask(__name__)
load_dotenv()
# MySQL Configuration
app.config['MYSQL_HOST'] = os.getenv("DB_HOST")
app.config['MYSQL_USER'] = os.getenv("DB_USER")
app.config['MYSQL_PASSWORD'] = os.getenv("DB_PASS")
app.config['MYSQL_DB'] = os.getenv("DB_NAME")

# Secret key for mail and session
app.secret_key = os.urandom(24)

# Mail configuration
app.config['MAIL_SERVER'] = 'smtp.elasticemail.com'
app.config['MAIL_PORT'] = 2525  
app.config['MAIL_USERNAME'] = '-' #elasticemail verified gmail
app.config['MAIL_PASSWORD'] = '-' #elasticemail password
app.config['MAIL_USE_TLS'] = True
app.config['MAIL_USE_SSL'] = False

mail = Mail(app)

# Initialize MySQL
mysql = MySQL(app)

# Ask ai apikey
genai.configure(api_key=os.getenv("GEMINI_API")) #gemini api key

@app.route('/')
def index():
    # If user is already logged in, redirect to dashboard
    if 'loggedin' in session:
        return redirect(url_for('dashboard'))
    return render_template('login.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    # Check if POST request
    if request.method == 'POST':
        # Get form data
        email = request.form['email']
        password = request.form['password']
        
        # Check if account exists
        cursor = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
        cursor.execute('SELECT * FROM users WHERE email = %s', (email,))
        account = cursor.fetchone()
        
        # Verify account and password
        if account and check_password_hash(account['password'], password):
            # Create session data
            session['loggedin'] = True
            session['id'] = account['id']
            session['user_id'] = account['id']  # Added to fix the expenses route
            session['email'] = account['email']
            
            # Redirect to dashboard
            return redirect(url_for('dashboard'))
        else:
            # Account doesn't exist or password incorrect
            flash('Incorrect email or password', 'danger')
    
    return render_template('login.html')

@app.route('/signup', methods=['GET', 'POST'])
def signup():
    # Check if POST request
    if request.method == 'POST':
        # Get form data
        fname = request.form['first_name']
        lname = request.form['last_name']
        email = request.form['email']
        password = request.form['password']
        confirm_password = request.form['confirm_password']
        
        # Validate form data
        cursor = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
        cursor.execute('SELECT * FROM users WHERE email = %s', (email,))
        account = cursor.fetchone()
        
        # Validation checks
        if account:
            flash('Account already exists!', 'danger')
        elif not re.match(r'[^@]+@[^@]+\.[^@]+', email):
            flash('Invalid email address!', 'danger')
        elif password != confirm_password:
            flash('Passwords do not match!', 'danger')
        elif not email or not password:
            flash('Please fill out all fields!', 'danger')
        else:
            # Hash the password
            hashed_password = generate_password_hash(password)
            
            # Insert new user
            cursor.execute('INSERT INTO users (fname,lname,email, password) VALUES (%s,%s,%s, %s)', 
                           (fname,lname,email, hashed_password))
            mysql.connection.commit()
            
            flash('Account created successfully!', 'success')
            return redirect(url_for('login'))
    
    return render_template('signup.html')

@app.route('/profile')
def profile():
    # Check if user is logged in
    if 'loggedin' not in session:
        return redirect(url_for('login'))
    
    # Fetch user details
    cursor = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
    cursor.execute('SELECT * FROM users WHERE id = %s', (session['id'],))
    user_details = cursor.fetchone()
    
    return render_template('profile.html', 
                           email=session['email'], 
                           user_details=user_details,
                           first_name=user_details['fname'],
                           last_name=user_details['lname'])

@app.route('/graph')
def graph():
    # Check if user is logged in
    if 'loggedin' not in session:
        return redirect(url_for('login'))
    
    user_id = session['id']
    
    # Create cursor for database operations
    cursor = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
    
    # Fetch user's current expenses (latest record)
    cursor.execute("""
        SELECT * FROM expenses 
        WHERE user_id = %s 
        ORDER BY created_at DESC 
        LIMIT 1
    """, (user_id,))
    
    expense_data = cursor.fetchone()
    
    # If no expenses found, initialize with zeros
    if not expense_data:
        expense_data = {
            'food': 0,
            'travel': 0,
            'entertainment': 0,
            'shopping': 0,
            'other': 0
        }
    
    # Calculate total
    total = (
        expense_data['food'] + 
        expense_data['travel'] + 
        expense_data['entertainment'] + 
        expense_data['shopping'] + 
        expense_data['other']
    )
    
    # Render the graph template with the expense data
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
                msg = Message(subject=subject,
                              sender=app.config['MAIL_USERNAME'],
                              recipients=['vyankateshpandit1511@gmail.com'])  # Replace with the recipient email
                msg.body = f"Name: {name}\nEmail: {email}\nMessage: {message_text}"
                mail.send(msg)

                message = 'Your message has been sent! We will contact you soon.'
            except Exception as e:
                message = f'Error sending email: {str(e)}'

    # Fetch user details
    cursor = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
    cursor.execute('SELECT * FROM users WHERE id = %s', (session['id'],))
    user_details = cursor.fetchone()

    return render_template('contact.html', 
                           email=session['email'],
                           user_details=user_details,
                           first_name=user_details['fname'],
                           last_name=user_details['lname'],
                           message=message)


@app.route('/expenses', methods=["GET", "POST"])
def expenses():
    # Check if user is logged in
    if 'loggedin' not in session:
        return redirect(url_for('login'))
    
    user_id = session['id']
    response = ""
    
    # Create cursor for database operations
    cursor = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
    
    if request.method == "GET":
        # Fetch user's current expenses
        cursor.execute("""
            SELECT * FROM expenses 
            WHERE user_id = %s 
            ORDER BY created_at DESC 
            LIMIT 1
        """, (user_id,))
        
        expense_data = cursor.fetchone()
        
        # If no expenses found, initialize with zeros
        if not expense_data:
            expense_data = {
                'food': 0,
                'travel': 0,
                'entertainment': 0,
                'shopping': 0,
                'other': 0
            }
        
        # Calculate total
        total = (
            expense_data['food'] + 
            expense_data['travel'] + 
            expense_data['entertainment'] + 
            expense_data['shopping'] + 
            expense_data['other']
        )
        
        return render_template('expenses.html', response="", expense_data=expense_data, total=total)
    
    elif request.method == "POST":
        try:
            # Handle add expense
            if "expenseAmount" in request.form and "expenseCategory" in request.form:
                amount = int(float(request.form["expenseAmount"]))
                category = request.form["expenseCategory"].lower()
                
                # First, get the latest expense record for this user
                cursor.execute("""
                    SELECT * FROM expenses 
                    WHERE user_id = %s 
                    ORDER BY created_at DESC 
                    LIMIT 1
                """, (user_id,))
                
                current_expenses = cursor.fetchone()
                
                # If no records exist, create a new one with zeros
                if not current_expenses:
                    cursor.execute("""
                        INSERT INTO expenses 
                        (user_id, food, travel, entertainment, shopping, other) 
                        VALUES (%s, 0, 0, 0, 0, 0)
                    """, (user_id,))
                    mysql.connection.commit()
                    
                    cursor.execute("""
                        SELECT * FROM expenses 
                        WHERE user_id = %s 
                        ORDER BY created_at DESC 
                        LIMIT 1
                    """, (user_id,))
                    current_expenses = cursor.fetchone()
                
                # Update the expense for the specific category
                food = current_expenses['food']
                travel = current_expenses['travel']
                entertainment = current_expenses['entertainment']
                shopping = current_expenses['shopping']
                other = current_expenses['other']
                
                # Update the appropriate category
                if category == 'food':
                    food += amount
                elif category == 'travel':
                    travel += amount
                elif category == 'entertainment':
                    entertainment += amount
                elif category == 'shopping':
                    shopping += amount
                elif category == 'other':
                    other += amount
                
                # Insert a new record with updated values
                cursor.execute("""
                    INSERT INTO expenses 
                    (user_id, food, travel, entertainment, shopping, other) 
                    VALUES (%s, %s, %s, %s, %s, %s)
                """, (user_id, food, travel, entertainment, shopping, other))
                
                mysql.connection.commit()
                flash("Expense added successfully!", "success")
            
            # Handle delete expense
            elif "deleteAmount" in request.form and "deleteCategorySelect" in request.form:
                amount = int(float(request.form["deleteAmount"]))
                category = request.form["deleteCategorySelect"].lower()
                
                # Get the latest expense record
                cursor.execute("""
                    SELECT * FROM expenses 
                    WHERE user_id = %s 
                    ORDER BY created_at DESC 
                    LIMIT 1
                """, (user_id,))
                
                current_expenses = cursor.fetchone()
                
                if not current_expenses:
                    flash("No expenses found to delete.", "danger")
                else:
                    # Check if there's enough to delete
                    if current_expenses[category] >= amount:
                        # Create new record with updated values
                        food = current_expenses['food']
                        travel = current_expenses['travel']
                        entertainment = current_expenses['entertainment']
                        shopping = current_expenses['shopping']
                        other = current_expenses['other']
                        
                        # Update the appropriate category
                        if category == 'food':
                            food -= amount
                        elif category == 'travel':
                            travel -= amount
                        elif category == 'entertainment':
                            entertainment -= amount
                        elif category == 'shopping':
                            shopping -= amount
                        elif category == 'other':
                            other -= amount
                        
                        # Insert a new record with updated values
                        cursor.execute("""
                            INSERT INTO expenses 
                            (user_id, food, travel, entertainment, shopping, other) 
                            VALUES (%s, %s, %s, %s, %s, %s)
                        """, (user_id, food, travel, entertainment, shopping, other))
                        
                        mysql.connection.commit()
                        flash(f"Deleted Rs {amount} from {category.capitalize()}", "success")
                    else:
                        flash(f"Cannot delete more than the available amount in {category.capitalize()}", "danger")
            
        except Exception as e:
            mysql.connection.rollback()
            flash(f"An error occurred: {str(e)}", "danger")
            return render_template('expenses.html', response=f"Error: {str(e)}")
        
        # Fetch updated expense data to refresh the page
        cursor.execute("""
            SELECT * FROM expenses 
            WHERE user_id = %s 
            ORDER BY created_at DESC 
            LIMIT 1
        """, (user_id,))
        
        expense_data = cursor.fetchone()
        
        if not expense_data:
            expense_data = {
                'food': 0,
                'travel': 0,
                'entertainment': 0,
                'shopping': 0,
                'other': 0
            }
        
        # Calculate total
        total = (
            expense_data['food'] + 
            expense_data['travel'] + 
            expense_data['entertainment'] + 
            expense_data['shopping'] + 
            expense_data['other']
        )
        
        return render_template('expenses.html', expense_data=expense_data, total=total)
    
@app.route("/ask_ai", methods=["POST"])
def ask_ai():
    try:
        data = request.get_json()
        prompt = data.get("prompt", "")

        model = genai.GenerativeModel("gemini-2.5-flash-lite")
        reply = model.generate_content(prompt)

        return jsonify({"response": reply.text})
    except Exception as e:
        return jsonify({"error": str(e)})

@app.route('/dashboard')
def dashboard():
    # Check if user is logged in
    if 'loggedin' not in session:
        return redirect(url_for('login'))
    
    # Fetch additional user details
    cursor = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
    cursor.execute('SELECT * FROM users WHERE id = %s', (session['id'],))
    user_details = cursor.fetchone()
    
    return render_template('dashboard.html', 
                           email=session['email'], 
                           user_details=user_details,
                           first_name=user_details['fname'],
                           last_name=user_details['lname'])

@app.route('/sip_cal')
def sip_cal():
    # Check if user is logged in
    if 'loggedin' not in session:
        return redirect(url_for('login'))
    return render_template('sip_cal.html')

@app.route('/lumsum_cal')
def lumsum_cal():
    # Check if user is logged in
    if 'loggedin' not in session:
        return redirect(url_for('login'))
    return render_template('lumsum_cal.html')

@app.route('/delete_account')
@app.route('/delete_account')
def delete_account():
    # Check if user is logged in
    if 'loggedin' not in session or 'id' not in session:
        flash('You must be logged in to delete your account', 'danger')
        return redirect(url_for('login'))
    
    user_id = session['id']
    cursor = mysql.connection.cursor()
    
    # First, delete all expenses related to this user
    cursor.execute("DELETE FROM expenses WHERE user_id = %s", (user_id,))
    
    # Then delete the user
    cursor.execute("DELETE FROM users WHERE id = %s", (user_id,))
    
    mysql.connection.commit()
    cursor.close()
    
    # Clear session variables
    session.pop('loggedin', None)
    session.pop('id', None)
    session.pop('user_id', None)
    session.pop('email', None)
    
    flash('Account deleted successfully!', 'success')
    return redirect(url_for('login'))

@app.route('/logout')
def logout():
    # Remove session data
    session.pop('loggedin', None)
    session.pop('id', None)
    session.pop('user_id', None)  # Added to clear this session variable
    session.pop('email', None)
    
    return redirect(url_for('login'))

if __name__ == '__main__':
    app.run(debug=True)