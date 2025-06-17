from flask import Flask, render_template, request, redirect, url_for, flash, session
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
import numpy as np
import joblib
import os  # For secret key

from dotenv import load_dotenv
load_dotenv()
# --- App Configuration ---
app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('FLASK_SECRET_KEY', 'fallback_secret_key')

# Fetch MySQL credentials securely from .env
db_user = os.getenv('DB_USER')
db_password = os.getenv('DB_PASSWORD')
db_host = os.getenv('DB_HOST', 'localhost')
db_name = os.getenv('DB_NAME', 'booksonn')
print("DB_USER:", db_user)
print("DB_PASSWORD:", db_password)

app.config['SQLALCHEMY_DATABASE_URI'] = f'mysql+pymysql://{db_user}:{db_password}@{db_host}/{db_name}'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

# --- Load ML Models ---
popular_df = joblib.load('popular.joblib')
pt = joblib.load('pt.joblib')
books = joblib.load('books.joblib')
similarity_scores = joblib.load('similarity_scores.joblib')


# --- Database Model ---
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)  # Increased length for future hashing algos

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def __repr__(self):
        return f'<User {self.username}>'


# --- Helper Function for Login Required ---
from functools import wraps


def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('Please log in to access this page.', 'warning')
            return redirect(url_for('login', next=request.url))
        return f(*args, **kwargs)

    return decorated_function


# --- Routes ---
@app.route('/')
def index():
    return render_template('index.html',
                           book_name=list(popular_df['Book-Title'].values),
                           author=list(popular_df['Book-Author'].values),
                           image=list(popular_df['Image-URL-M'].values),
                           votes=list(popular_df['num_ratings'].values),
                           rating=list(popular_df['avg_rating'].values)
                           )


@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if 'user_id' in session:
        return redirect(url_for('index'))
    if request.method == 'POST':
        username = request.form.get('username')
        email = request.form.get('email')
        password = request.form.get('password')
        confirm_password = request.form.get('confirm_password')

        if not username or not email or not password or not confirm_password:
            flash('All fields are required.', 'danger')
            return render_template('signup.html')

        if password != confirm_password:
            flash('Passwords do not match.', 'danger')
            return render_template('signup.html', username=username, email=email)

        existing_user = User.query.filter((User.username == username) | (User.email == email)).first()
        if existing_user:
            flash('Username or email already exists.', 'danger')
            return render_template('signup.html', username=username, email=email)

        new_user = User(username=username, email=email)
        new_user.set_password(password)
        db.session.add(new_user)
        try:
            db.session.commit()
            flash('Account created successfully! Please log in.', 'success')
            return redirect(url_for('login'))
        except Exception as e:
            db.session.rollback()
            flash(f'An error occurred: {str(e)}', 'danger')
            app.logger.error(f"Error during signup: {e}")

    return render_template('signup.html')


@app.route('/login', methods=['GET', 'POST'])
def login():
    if 'user_id' in session:
        return redirect(url_for('index'))
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')

        if not username or not password:
            flash('Username and password are required.', 'danger')
            return render_template('login.html')

        user = User.query.filter_by(username=username).first()

        if user and user.check_password(password):
            session['user_id'] = user.id
            session['username'] = user.username
            flash('Logged in successfully!', 'success')
            next_page = request.args.get('next')
            return redirect(next_page or url_for('index'))
        else:
            flash('Invalid username or password.', 'danger')

    return render_template('login.html')


@app.route('/logout')
def logout():
    session.pop('user_id', None)
    session.pop('username', None)
    flash('You have been logged out.', 'info')
    return redirect(url_for('login'))


@app.route('/recommend')
@login_required  # Protect this route
def recommend_ui():
    return render_template('recommend.html', user_input_value='')


@app.route('/recommend_books', methods=['POST'])
@login_required  # Protect this route
def recommend():
    user_input = request.form.get('user_input')
    data = []
    error_message = None

    try:
        indices = np.where(pt.index == user_input)[0]
        if len(indices) == 0:
            error_message = f"Book '{user_input}' not found in our recommendation database. Please check the title and try again."
        else:
            index = indices[0]
            similar_items = sorted(list(enumerate(similarity_scores[index])), key=lambda x: x[1], reverse=True)[1:5]
            if not similar_items:
                error_message = f"No recommendations found for '{user_input}'. Try a different book."
            else:
                for i in similar_items:
                    item = []
                    book_title_recommended = pt.index[i[0]]
                    temp_df = books[books['Book-Title'] == book_title_recommended]
                    if not temp_df.empty:
                        unique_book_entry = temp_df.drop_duplicates('Book-Title')
                        item.extend(list(unique_book_entry['Book-Title'].values))
                        item.extend(list(unique_book_entry['Book-Author'].values))
                        item.extend(list(unique_book_entry['Image-URL-M'].values))
                        data.append(item)
                    else:
                        app.logger.warning(f"Recommended book '{book_title_recommended}' not found in books DataFrame.")
                if not data and not error_message:
                    error_message = f"Found recommendations for '{user_input}', but had trouble fetching their details."
    except Exception as e:
        app.logger.error(f"Error in recommendation: {e}")
        error_message = "An unexpected error occurred while fetching recommendations. Please try again."
        data = []

    return render_template('recommend.html', data=data, error_message=error_message, user_input_value=user_input)


@app.route('/about')
def about():
    return render_template('about.html')


@app.route('/dashboard')  # Example protected route
@login_required
def dashboard():
    return render_template('dashboard.html')


if __name__ == '__main__':
    with app.app_context():
        db.create_all()  # Create database tables if they don't exist
    app.run(debug=True)