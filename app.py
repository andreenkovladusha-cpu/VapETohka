import os
from flask import Flask, render_template, request, redirect, url_for, session, jsonify
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from datetime import datetime

app = Flask(__name__, template_folder='vapepages')
app.secret_key = 'vape_tochka_monumental_black_key_2026'

# Настройка папки для загрузки картинок
UPLOAD_FOLDER = os.path.join('static', 'uploads')
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///vape_shop.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

# --- МОДЕЛИ БАЗЫ ДАННЫХ ---
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(120), nullable=False)
    is_admin = db.Column(db.Boolean, default=False)

class Product(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    price = db.Column(db.Integer, nullable=False)
    category = db.Column(db.String(50), nullable=False, default="Другое")
    desc = db.Column(db.Text, nullable=True)
    image_file = db.Column(db.String(200), nullable=True)  # Поле для имени картинки

class Review(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), nullable=False)
    text = db.Column(db.Text, nullable=False)
    rating = db.Column(db.Integer, nullable=False)

class Order(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), nullable=False)
    total_price = db.Column(db.Integer, nullable=False)
    status = db.Column(db.String(50), default="Новый")
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    items = db.relationship('OrderItem', backref='order', lazy=True, cascade="all, delete-orphan")

class OrderItem(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey('order.id'), nullable=False)
    product_name = db.Column(db.String(100), nullable=False)
    price = db.Column(db.Integer, nullable=False)
    quantity = db.Column(db.Integer, nullable=False)

# Автоматическое создание папок и базы данных
with app.app_context():
    os.makedirs(UPLOAD_FOLDER, exist_ok=True)
    db.create_all()
    # Дефолтный суперадмин
    if not User.query.filter_by(username='admin').first():
        db.session.add(User(username='admin', password_hash=generate_password_hash('admin123'), is_admin=True))
    db.session.commit()

# --- ОСНОВНЫЕ МАРШРУТЫ САЙТА ---
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/catalog')
def catalog():
    search_query = request.args.get('search', '').strip()
    category_filter = request.args.get('category', '').strip()
    query = Product.query
    if search_query:
        query = query.filter(Product.name.contains(search_query))
    if category_filter:
        query = query.filter_by(category=category_filter)
    return render_template('catalog.html', products=query.all(), search=search_query, current_category=category_filter)

@app.route('/reviews', methods=['GET', 'POST'])
def reviews():
    if request.method == 'POST':
        if 'user' not in session:
            return redirect(url_for('login'))
        text = request.form.get('review_text')
        rating = int(request.form.get('stars', 5))
        if text:
            db.session.add(Review(username=session['user'], text=text, rating=rating))
            db.session.commit()
        return redirect(url_for('reviews'))
    return render_template('reviews.html', reviews=Review.query.all())

# --- АВТОРИЗАЦИЯ ---
@app.route('/register', methods=['GET', 'POST'])
def register():
    error = None
    if request.method == 'POST':
        username = request.form.get('username').strip()
        password = request.form.get('password')
        if User.query.filter_by(username=username).first():
            error = "Этот логин уже занят!"
        elif len(username) < 3 or len(password) < 4:
            error = "Слишком короткий логин или пароль!"
        else:
            db.session.add(User(username=username, password_hash=generate_password_hash(password)))
            db.session.commit()
            session['user'] = username
            session['is_admin'] = False
            return redirect(url_for('index'))
    return render_template('register.html', error=error)

@app.route('/login', methods=['GET', 'POST'])
def login():
    error = None
    if request.method == 'POST':
        username = request.form.get('username').strip()
        password = request.form.get('password')
        user = User.query.filter_by(username=username).first()
        if user and check_password_hash(user.password_hash, password):
            session['user'] = user.username
            session['is_admin'] = user.is_admin
            return redirect(url_for('index'))
        error = "Неверный логин или пароль!"
    return render_template('login.html', error=error)

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('index'))

@app.route('/api/checkout', methods=['POST'])
def checkout():
    if 'user' not in session:
        return jsonify({"success": False, "message": "Необходимо войти в систему!"}), 401
    data = request.get_json()
    cart_items = data.get('cart', [])
    if not cart_items:
        return jsonify({"success": False, "message": "Корзина пуста!"}), 400
    
    total_price = 0
    new_order = Order(username=session['user'], total_price=0)
    db.session.add(new_order)
    db.session.flush()
    
    for item in cart_items:
        total_price += int(item['price']) * int(item['quantity'])
        db.session.add(OrderItem(order_id=new_order.id, product_name=item['name'], price=int(item['price']), quantity=int(item['quantity'])))
        
    new_order.total_price = total_price
    db.session.commit()
    return jsonify({"success": True, "message": "Заказ оформлен!"})

# --- АДМИН ПАНЕЛЬ ---
@app.route('/admin', methods=['GET', 'POST'])
def admin():
    if not session.get('is_admin'):
        return "Доступ запрещен!", 403
        
    if request.method == 'POST':
        action = request.form.get('action')
        if action == 'add_product':
            name = request.form.get('name')
            price = int(request.form.get('price', 0))
            category = request.form.get('category')
            desc = request.form.get('desc')
            
            # Логика сохранения картинки
            file = request.files.get('product_image')
            filename = None
            if file and file.filename != '':
                filename = secure_filename(file.filename)
                # Добавляем уникальный маркер времени к файлу, чтобы имена не дублировались
                filename = f"{int(datetime.utcnow().timestamp())}_{filename}"
                file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
                
            if name and price:
                db.session.add(Product(name=name, price=price, category=category, desc=desc, image_file=filename))
        elif action == 'delete_product':
            Product.query.filter_by(id=int(request.form.get('product_id'))).delete()
        elif action == 'delete_review':
            Review.query.filter_by(id=int(request.form.get('review_id'))).delete()
        elif action == 'toggle_admin':
            user = User.query.get(int(request.form.get('user_id')))
            if user and user.username != 'admin':
                user.is_admin = not user.is_admin
        elif action == 'delete_user':
            user = User.query.get(int(request.form.get('user_id')))
            if user and user.username != 'admin':
                db.session.delete(user)
        elif action == 'update_order_status':
            order = Order.query.get(int(request.form.get('order_id')))
            if order:
                order.status = request.form.get('status')
        elif action == 'delete_order':
            Order.query.filter_by(id=int(request.form.get('order_id'))).delete()
            
        db.session.commit()
        return redirect(url_for('admin'))

    # Считаем кассу
    revenue = db.session.query(db.func.sum(Order.total_price)).filter(Order.status == 'Выдан').scalar() or 0
    pending = db.session.query(db.func.sum(Order.total_price)).filter(Order.status != 'Выдан', Order.status != 'Отменен').scalar() or 0
    stats = {"total_users": User.query.count(), "total_products": Product.query.count(), "total_reviews": Review.query.count(), "total_orders": Order.query.count(), "revenue": revenue, "pending_revenue": pending}
    
    return render_template('admin.html', products=Product.query.all(), reviews=Review.query.all(), users=User.query.all(), orders=Order.query.order_by(Order.created_at.desc()).all(), stats=stats)

if __name__ == '__main__':
    app.run(debug=True)
