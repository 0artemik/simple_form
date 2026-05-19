import sqlite3
import pandas as pd
from flask import Flask, render_template, request, send_file, redirect, url_for, flash
from datetime import datetime
import os

app = Flask(__name__)
app.secret_key = 'your-secret-key-here-change-in-production'

DATABASE = 'database.db'

def init_db():
    """Создаёт таблицу, если её нет."""
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

@app.route('/', methods=['GET', 'POST'])
def index():
    if request.method == 'POST':
        full_name = request.form.get('full_name', '').strip()
        birth_date = request.form.get('birth_date', '').strip()
        phone = request.form.get('phone', '').strip()

        # Простейшая валидация
        if not full_name or not birth_date or not phone:
            flash('Все поля обязательны для заполнения!', 'error')
            return redirect(url_for('index'))

        # Проверка формата даты (YYYY-MM-DD)
        try:
            datetime.strptime(birth_date, '%Y-%m-%d')
        except ValueError:
            flash('Неверный формат даты. Используйте ГГГГ-ММ-ДД', 'error')
            return redirect(url_for('index'))
        
        # Проверка согласия
        if not request.form.get('consent'):
            flash('Необходимо принять условия согласия!', 'error')
            return redirect(url_for('index'))

        # Сохраняем в БД
        conn = sqlite3.connect(DATABASE)
        c = conn.cursor()
        c.execute('INSERT INTO persons (full_name, birth_date, phone) VALUES (?, ?, ?)',
                  (full_name, birth_date, phone))
        conn.commit()
        conn.close()

        flash('Данные успешно сохранены!', 'success')
        return redirect(url_for('index'))

    return render_template('index.html')

@app.route('/export')
def export():
    """Экспорт всей таблицы в XLSX."""
    conn = sqlite3.connect(DATABASE)
    df = pd.read_sql_query("SELECT id, full_name, birth_date, phone, created_at FROM persons", conn)
    conn.close()

    if df.empty:
        flash('База данных пуста. Нечего экспортировать.', 'warning')
        return redirect(url_for('index'))

    # Сохраняем во временный файл
    output_path = 'export_persons.xlsx'
    df.to_excel(output_path, index=False, engine='openpyxl')

    # Отправляем файл и удаляем после отправки (опционально)
    return_data = send_file(output_path, as_attachment=True, download_name='persons_export.xlsx')

    # Удаляем временный файл после отправки (можно не удалять, если файл нужен)
    # Для простоты оставим, при следующем экспорте перезапишется
    return return_data

if __name__ == '__main__':
    init_db()
    app.run(debug=True, host='0.0.0.0', port=5001)
