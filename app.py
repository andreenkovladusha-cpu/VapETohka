import os
from flask import Flask, render_template, request, redirect, url_for, flash, session
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from flask_bcrypt import Bcrypt

app = Flask(__name__)
# Секретный ключ для защиты сессий и куки
app.config['SECRET_KEY'] = 'vape_tokha_secret_key_2026'
# Подключение базы данных SQLite
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///vapeshop.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)
bcrypt = Bcrypt(app)

# Настройка менеджера авторизации пользователей
login_manager = LoginManager(app)
login_manager.login_view = 'login'
login_manager.login_message = 'Для просмотра этой страницы необходимо войти в аккаунт.'
login_manager.login_message_category = 'info'

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# =========================================================================
# БАЗА ДАННЫХ (МОДЕЛИ)
# =========================================================================

# Таблица пользователей (Пункт 2)
class User(db.Model, UserMixin):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password = db.Column(db.String(60), nullable=False)

# Таблица товаров (базовая витрина)
class Product(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    price = db.Column(db.Integer, nullable=False)  # Цена в BYN
    image = db.Column(db.String(100), default='default.jpg')
    category = db.Column(db.String(50))

# Таблица промокодов (Пункт 6)
class Promocode(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(20), unique=True, nullable=False)
    discount_percent = db.Column(db.Integer, nullable=False)  # Процент скидки
    is_active = db.Column(db.Boolean, default=True)

# =========================================================================
# МАРШРУТЫ (БИЗНЕС-ЛОГИКА)
# =========================================================================

# Главная страница — Каталог товаров
@app.route('/')
def index():
    products = Product.query.all()
    # Если корзины еще нет в сессии, создаем пустую
    if 'cart' not in session:
        session['cart'] = []
    return render_template('index.html', products=products)

# Добавление товара в корзину
@app.route('/add_to_cart/<int:product_id>')
def add_to_cart(product_id):
    if 'cart' not in session:
        session['cart'] = []
    
    # Добавляем ID товара в список корзины
    cart = session['cart']
    cart.append(product_id)
    session['cart'] = cart
    flash('Товар добавлен в корзину!', 'success')
    return redirect(url_for('index'))

# Страница корзины с расчетом цены и вводом промокода
@app.route('/cart')
def cart_page():
    cart_ids = session.get('cart', [])
    # Извлекаем из БД только те товары, которые лежат в корзине
    cart_items = Product.query.filter(Product.id.in_(cart_ids)).all() if cart_ids else []
    
    # Считаем чистую стоимость без скидок
    total_price = sum(item.price for item in cart_items)
    
    # Проверяем, применен ли промокод
    discount = 0
    promo_code = session.get('applied_promo', None)
    if promo_code:
        promo = Promocode.query.filter_by(code=promo_code, is_active=True).first()
        if promo:
            discount = (total_price * promo.discount_percent) // 100
            
    final_price = total_price - discount
    return render_template('cart.html', cart_items=cart_items, total_price=total_price, final_price=final_price, discount=discount, promo_code=promo_code)

# Применение промокода (Пункт 6)
@app.route('/apply_promo', methods=['POST'])
def apply_promo():
    code_input = request.form.get('promo_code').strip().upper()
    promo = Promocode.query.filter_by(code=code_input, is_active=True).first()
    
    if promo:
        session['applied_promo'] = promo.code
        flash(f'Промокод {promo.code} успешно применен! Скидка {promo.discount_percent}%', 'success')
    else:
        flash('Такой промокод не существует или его срок истек.', 'danger')
        
    return redirect(url_for('cart_page'))

# Очистить корзину и промокоды
@app.route('/clear_cart')
def clear_cart():
    session.pop('cart', None)
    session.pop('applied_promo', None)
    return redirect(url_for('cart_page'))

# ----------------- АВТОРИЗАЦИЯ И ПРОФИЛЬ (Пункт 2) -----------------

# Регистрация нового аккаунта
@app.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('profile'))
    
    if request.method == 'POST':
        username = request.form.get('username')
        email = request.form.get('email')
        password = request.form.get('password')
        
        user_exists = User.query.filter((User.username == username) | (User.email == email)).first()
        if user_exists:
            flash('Пользователь с таким именем или email уже существует.', 'danger')
            return redirect(url_for('register'))
        
        # Хэшируем пароль перед записью в БД ради безопасности
        hashed_password = bcrypt.generate_password_hash(password).decode('utf-8')
        new_user = User(username=username, email=email, password=hashed_password)
        
        db.session.add(new_user)
        db.session.commit()
        flash('Аккаунт успешно создан! Войдите в систему.', 'success')
        return redirect(url_for('login'))
        
    return render_template('register.html')

# Вход в аккаунт
@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('profile'))
        
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        user = User.query.filter_by(email=email).first()
        
        if user and bcrypt.check_password_hash(user.password, password):
            login_user(user)
            return redirect(url_for('profile'))
        else:
            flash('Неверный логин или пароль. Попробуйте снова.', 'danger')
            
    return render_template('login.html')

# Личный кабинет (Защищен авторизацией)
@app.route('/profile')
@login_required
def profile():
    return render_template('profile.html', user=current_user)

# Выход из аккаунта
@app.route('/logout')
def logout():
    logout_user()
    session.pop('applied_promo', None)  # сбрасываем промокод при выходе
    return redirect(url_for('index'))

# =========================================================================
# ИНИЦИАЛИЗАЦИЯ БАЗЫ ДАННЫХ И ЗАПУСК
# =========================================================================
if __name__ == '__main__':
    with app.app_context():
        db.create_all()  # Автоматически создаем таблицы, если их нет
        
        # Заполняем базу базовыми товарами для теста, если она пустая
        if not Product.query.first():
            items = [
                Product(name="Электронная сигарета XROS 4", price=95, category="Поды"),
                Product(name="Жидкость Husky Double Ice (30мл)", price=25, category="Жидкости"),
                Product(name="Испаритель Vaporesso 0.6 Ом", price=10, category="Испарители")
            ]
            db.session.bulk_save_objects(items)
            
        # Создаем секретный промокод на 20% скидку
        if not Promocode.query.filter_by(code='MINSK2026').first():
            demo_promo = Promocode(code='MINSK2026', discount_percent=20)
            db.session.add(demo_promo)
            
        db.session.commit()
            
    app.run(debug=True)
