from flask import Flask, render_template, redirect, url_for, request, flash
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from flask_migrate import Migrate
import os

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///site.db'
app.config['SECRET_KEY'] = 'your_secret_key'
app.config['UPLOAD_FOLDER'] = 'static/uploads'
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16 MB limit

db = SQLAlchemy(app)
migrate = Migrate(app, db)
login_manager = LoginManager(app)
login_manager.login_view = 'login'

# Ensure the upload directory exists
if not os.path.exists(app.config['UPLOAD_FOLDER']):
    os.makedirs(app.config['UPLOAD_FOLDER'])

# Database Models
class User(db.Model, UserMixin):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    mobile = db.Column(db.String(20), unique=True, nullable=False)
    account_number = db.Column(db.String(20), unique=True, nullable=False)
    ifsc_code = db.Column(db.String(20), nullable=False)
    bank_name = db.Column(db.String(100), nullable=False)
    password = db.Column(db.String(256), nullable=False)  # Store hashed password
    is_admin = db.Column(db.Boolean, default=False)

class Image(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    filename = db.Column(db.String(255), nullable=False)
    status = db.Column(db.String(20), default='pending')

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

@app.route('/')
def home():
    return redirect(url_for("login"))

# User Registration
import csv

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        name = request.form['name']
        mobile = request.form['mobile']
        account_number = request.form['account_number']
        ifsc_code = request.form['ifsc_code']
        bank_name = request.form['bank_name']
        password = request.form['password']

        # Check if user already exists
        existing_user = User.query.filter_by(mobile=mobile).first()
        if existing_user:
            flash("Mobile number already registered!", "danger")
            return redirect(url_for('register'))

        # Hash password before storing
        hashed_password = generate_password_hash(password, method='pbkdf2:sha256')

        # Save user in database
        user = User(
            name=name,
            mobile=mobile,
            account_number=account_number,
            ifsc_code=ifsc_code,
            bank_name=bank_name,
            password=hashed_password,
            is_admin=False
        )
        db.session.add(user)
        db.session.commit()

        # Save user details in a CSV file
        csv_filename = "users.csv"
        file_exists = os.path.isfile(csv_filename)

        with open(csv_filename, mode="a", newline="") as file:
            writer = csv.writer(file)
            
            # Write the header if the file is newly created
            if not file_exists:
                writer.writerow(["Name", "Mobile", "Account Number", "IFSC Code", "Bank Name"])
            
            # Write user details
            writer.writerow([name, mobile, account_number, ifsc_code, bank_name])

        flash("Registered successfully! Please login.", "success")
        return redirect(url_for('login'))

    return render_template('register.html')


# User & Admin Login
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        mobile = request.form['mobile']
        password = request.form['password']
        user = User.query.filter_by(mobile=mobile).first()
        
        if user and check_password_hash(user.password, password):
            login_user(user)
            return redirect(url_for('dashboard'))
        
        flash("Invalid mobile number or password", "danger")
    
    return render_template('login.html')

# Logout
@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))

# User Dashboard
@app.route('/dashboard')
@login_required
def dashboard():
    if current_user.is_admin:
        users = User.query.filter_by(is_admin=False).all()
        return render_template('admin_dashboard.html', users=users)
    
    images = Image.query.filter_by(user_id=current_user.id).all()

    # Pass user details to the template
    return render_template(
        'user_dashboard.html', 
        images=images, 
        account_number=current_user.account_number,
        ifsc_code=current_user.ifsc_code,
        bank_name=current_user.bank_name
    )


# Image Upload
# Image Upload
@app.route('/upload', methods=['POST'])
@login_required
def upload():
    if 'images' not in request.files:
        flash("No file part", "danger")
        return redirect(url_for('dashboard'))

    files = request.files.getlist('images')

    # Get the current image count for the user
    user_images_count = Image.query.filter_by(user_id=current_user.id).count()

    # Check if the total uploads exceed 100
    if user_images_count + len(files) > 100:
        flash("You can upload only up to 100 images!", "danger")
        return redirect(url_for('dashboard'))

    for file in files:
        if file:
            filename = file.filename
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)

            # Ensure the folder exists before saving
            if not os.path.exists(app.config['UPLOAD_FOLDER']):
                os.makedirs(app.config['UPLOAD_FOLDER'])

            file.save(filepath)

            img = Image(user_id=current_user.id, filename=filename)
            db.session.add(img)

    db.session.commit()
    flash("Images uploaded successfully!", "success")
    return redirect(url_for('dashboard'))

# Admin View: List User Profiles
@app.route('/admin/user/<int:user_id>')
@login_required
def view_user(user_id):
    if not current_user.is_admin:
        return redirect(url_for('dashboard'))
    
    images = Image.query.filter_by(user_id=user_id).all()
    return render_template('admin_view_user.html', images=images, user_id=user_id)

# Admin Action: Approve/Deny Images
@app.route('/admin/update_status/<int:image_id>/<status>')
@login_required
def update_status(image_id, status):
    if not current_user.is_admin:
        return redirect(url_for('dashboard'))
    
    img = Image.query.get(image_id)
    if img:
        img.status = status
        db.session.commit()
        flash(f"Image {status}!", "success")
    return redirect(url_for('view_user', user_id=img.user_id))

# Initialize Database & Create Predefined Admin
if __name__ == "__main__":
    with app.app_context():
        db.create_all()

        # Create a predefined admin if it does not exist
        admin_mobile = "9999999999"
        admin_password = "admin123"
        admin = User.query.filter_by(mobile=admin_mobile).first()
        if not admin:
            hashed_admin_password = generate_password_hash(admin_password, method='pbkdf2:sha256')
            admin = User(
                name="Admin", 
                mobile=admin_mobile, 
                account_number="0000000000",  # Default admin details
                ifsc_code="BANK000000",
                bank_name="Admin Bank",
                password=hashed_admin_password,
                is_admin=True
            )
            db.session.add(admin)
            db.session.commit()
            print("Admin account created with mobile:", admin_mobile)

    app.run(debug=True)
