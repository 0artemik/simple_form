import sqlite3
import pandas as pd
from flask import Flask, render_template, request, send_file, redirect, url_for, flash, abort, Response
from datetime import datetime
from functools import wraps
from werkzeug.security import check_password_hash  # добавлен импорт для проверки хеша

app = Flask(__name__)
app.secret_key = 'your-secret-key-here-change-in-production'

DATABASE = 'database.db'

# Настройки для админки (пароль хранится в виде хеша)
ADMIN_USERNAME = 'admin'
ADMIN_PASSWORD_HASH = 'scrypt:32768:8:1$nuwPRu2QnaqLMhzd$dcb673a5be6db73c5564b62793c176fb5f6c15f83417cea468bfd81349aad6b133d6564a6936ea6d96595edc6bd16d935e7b2113a0704fe545ee3b2bee2a97ac'

def init_db():
    conn = sqlite3.connect(DATABASE)
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS persons (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            full_name TEXT NOT NULL,
            birth_date TEXT NOT NULL,
            phone TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    conn.commit()
    conn.close()

# --- Декоратор для HTTP Basic Auth ---
def check_auth(username, password):
    return username == ADMIN_USERNAME and check_password_hash(ADMIN_PASSWORD_HASH, password)

def authenticate():
    return Response(
        'Доступ запрещён. Введите логин и пароль.',
        401,
        {'WWW-Authenticate': 'Basic realm="Admin Panel"'}
    )

def requires_auth(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        auth = request.authorization
        if not auth or not check_auth(auth.username, auth.password):
            return authenticate()
        return f(*args, **kwargs)
    return decorated

@app.route('/', methods=['GET', 'POST'])
def index():
    if request.method == 'POST':
        full_name = request.form.get('full_name', '').strip()
        birth_date = request.form.get('birth_date', '').strip()
        phone = request.form.get('phone', '').strip()

        if not full_name or not birth_date or not phone:
            flash('Все поля обязательны для заполнения!', 'error')
            return redirect(url_for('index'))

        try:
            datetime.strptime(birth_date, '%Y-%m-%d')
        except ValueError:
            flash('Неверный формат даты. Используйте ГГГГ-ММ-ДД', 'error')
            return redirect(url_for('index'))

        # Проверка согласия (чекбокс)
        if not request.form.get('consent'):
            flash('Необходимо принять условия согласия!', 'error')
            return redirect(url_for('index'))

        conn = sqlite3.connect(DATABASE)
        c = conn.cursor()
        c.execute('INSERT INTO persons (full_name, birth_date, phone) VALUES (?, ?, ?)',
                  (full_name, birth_date, phone))
        conn.commit()
        conn.close()

        flash('Данные успешно сохранены!', 'success')
        return redirect(url_for('index'))

    return render_template('index.html')

@app.route('/admin')
@requires_auth
def admin_panel():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute("SELECT id, full_name, birth_date, phone, created_at FROM persons ORDER BY created_at DESC")
    persons = cur.fetchall()
    conn.close()
    return render_template('admin.html', persons=persons)

@app.route('/export')
@requires_auth
def export():
    conn = sqlite3.connect(DATABASE)
    df = pd.read_sql_query("SELECT id, full_name, birth_date, phone, created_at FROM persons", conn)
    conn.close()

    if df.empty:
        flash('База данных пуста. Нечего экспортировать.', 'warning')
        return redirect(url_for('admin_panel'))

    output_path = 'export_persons.xlsx'
    df.to_excel(output_path, index=False, engine='openpyxl')
    return send_file(output_path, as_attachment=True, download_name='persons_export.xlsx')

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
