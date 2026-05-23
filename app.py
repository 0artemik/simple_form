import os
import sqlite3
import pandas as pd
from flask import Flask, render_template, request, send_file, redirect, url_for, flash, abort, Response, jsonify
from datetime import datetime, date, timedelta
from functools import wraps
from werkzeug.security import check_password_hash
from dateutil.relativedelta import relativedelta
import io

app = Flask(__name__)
app.secret_key = 'your-secret-key-here-change-in-production'

DATA_DIR = '/app/data'
os.makedirs(DATA_DIR, exist_ok=True)
DATABASE = os.path.join(DATA_DIR, 'database.db')

ADMIN_USERNAME = 'admin'
ADMIN_PASSWORD_HASH = 'scrypt:32768:8:1$nuwPRu2QnaqLMhzd$dcb673a5be6db73c5564b62793c176fb5f6c15f83417cea468bfd81349aad6b133d6564a6936ea6d96595edc6bd16d935e7b2113a0704fe545ee3b2bee2a97ac'

GAME_ZONES = ['Стационарный VR', 'Арена', 'Автосимулятор', 'Приставка', 'ПК клуб']
DURATIONS = ['30 мин', '1 час', '2 часа', '3 часа', '4 часа', 'Более 4 часов']


def init_db():
    conn = sqlite3.connect(DATABASE)
    c = conn.cursor()

    c.execute('''
        CREATE TABLE IF NOT EXISTS persons (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            full_name TEXT NOT NULL,
            birth_date TEXT NOT NULL,
            phone TEXT NOT NULL,
            game_zone TEXT DEFAULT '',
            duration TEXT DEFAULT '',
            budget TEXT DEFAULT '',
            created_at TEXT DEFAULT (datetime('now'))
        )
    ''')

    for col, col_type in [('game_zone', "TEXT DEFAULT ''"),
                          ('duration', "TEXT DEFAULT ''"),
                          ('budget', "TEXT DEFAULT ''")]:
        try:
            c.execute(f"ALTER TABLE persons ADD COLUMN {col} {col_type}")
        except sqlite3.OperationalError:
            pass

    c.execute('''
        CREATE TABLE IF NOT EXISTS children (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            person_id INTEGER NOT NULL,
            child_name TEXT NOT NULL,
            child_birth_date TEXT NOT NULL,
            FOREIGN KEY (person_id) REFERENCES persons (id)
        )
    ''')

    conn.commit()
    conn.close()


def parse_date(date_str):
    """
    Принимает дату в формате ДД.ММ.ГГГГ (с формы) или ГГГГ-ММ-ДД (старые записи).
    Возвращает дату в формате ГГГГ-ММ-ДД для хранения в БД.
    Бросает ValueError если формат не распознан.
    """
    date_str = (date_str or '').strip()
    if not date_str:
        raise ValueError('Дата не указана')
    # Новый формат с формы: ДД.ММ.ГГГГ
    if '.' in date_str:
        return datetime.strptime(date_str, '%d.%m.%Y').strftime('%Y-%m-%d')
    # Старый формат (на случай прямого POST): ГГГГ-ММ-ДД
    return datetime.strptime(date_str, '%Y-%m-%d').strftime('%Y-%m-%d')


def get_age(birth_date_str, as_of=None):
    if not birth_date_str:
        return ""
    try:
        bd = datetime.strptime(birth_date_str, '%Y-%m-%d').date()
    except (ValueError, TypeError):
        return ""
    today = as_of or date.today()
    return relativedelta(today, bd).years


def msk_today():
    """Текущая дата по МСК (UTC+3)"""
    return (datetime.utcnow() + timedelta(hours=3)).date()


# --- HTTP Basic Auth ---
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
        full_name  = request.form.get('full_name', '').strip()
        phone      = request.form.get('phone', '').strip()
        game_zone  = request.form.get('game_zone', '').strip()

        if not full_name or not phone:
            flash('Все поля обязательны для заполнения!', 'error')
            return redirect(url_for('index'))

        if not game_zone:
            flash('Выберите игровую зону!', 'error')
            return redirect(url_for('index'))

        if game_zone not in GAME_ZONES:
            flash('Некорректная игровая зона.', 'error')
            return redirect(url_for('index'))

        # Дата рождения: принимаем ДД.ММ.ГГГГ, конвертируем в ГГГГ-ММ-ДД
        try:
            birth_date = parse_date(request.form.get('birth_date', ''))
        except ValueError:
            flash('Неверный формат даты рождения. Используйте ДД.ММ.ГГГГ', 'error')
            return redirect(url_for('index'))

        if not request.form.get('consent'):
            flash('Необходимо принять условия согласия!', 'error')
            return redirect(url_for('index'))

        created_at = (datetime.utcnow() + timedelta(hours=3)).strftime('%Y-%m-%d %H:%M:%S')

        conn = sqlite3.connect(DATABASE)
        c = conn.cursor()
        c.execute(
            'INSERT INTO persons (full_name, birth_date, phone, game_zone, created_at) VALUES (?, ?, ?, ?, ?)',
            (full_name, birth_date, phone, game_zone, created_at)
        )
        person_id = c.lastrowid

        child_name           = request.form.get('child_name', '').strip()
        child_birth_date_raw = request.form.get('child_birth_date', '').strip()

        if child_name and child_birth_date_raw:
            try:
                child_birth_date = parse_date(child_birth_date_raw)
            except ValueError:
                conn.close()
                flash('Неверный формат даты рождения ребёнка. Используйте ДД.ММ.ГГГГ', 'error')
                return redirect(url_for('index'))

            c.execute(
                'INSERT INTO children (person_id, child_name, child_birth_date) VALUES (?, ?, ?)',
                (person_id, child_name, child_birth_date)
            )

        conn.commit()
        conn.close()

        flash('Данные успешно сохранены!', 'success')
        return redirect(url_for('index'))

    return render_template('index.html', game_zones=GAME_ZONES)


@app.route('/admin')
@requires_auth
def admin_panel():
    today_str   = msk_today().strftime('%Y-%m-%d')
    filter_date = request.args.get('date', today_str).strip()
    show_all    = request.args.get('all', '0')

    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    query  = "SELECT id, full_name, birth_date, phone, game_zone, duration, budget, created_at FROM persons"
    params = ()
    if show_all != '1' and filter_date:
        query += " WHERE DATE(created_at) = ?"
        params = (filter_date,)
    query += " ORDER BY created_at DESC"
    cur.execute(query, params)
    persons = cur.fetchall()

    persons_with_children = []
    for p in persons:
        cur.execute(
            "SELECT child_name, child_birth_date FROM children WHERE person_id = ? ORDER BY id",
            (p['id'],)
        )
        children = cur.fetchall()
        persons_with_children.append({
            'id':         p['id'],
            'full_name':  p['full_name'],
            'birth_date': p['birth_date'],
            'phone':      p['phone'],
            'game_zone':  p['game_zone'] or '',
            'duration':   p['duration']  or '',
            'budget':     p['budget']    or '',
            'created_at': p['created_at'],
            'children':   children
        })

    conn.close()
    return render_template(
        'admin.html',
        persons=persons_with_children,
        game_zones=GAME_ZONES,
        durations=DURATIONS,
        filter_date=filter_date,
        show_all=show_all,
        today=today_str
    )


@app.route('/update_row/<int:person_id>', methods=['POST'])
@requires_auth
def update_row(person_id):
    full_name = request.form.get('full_name', '').strip()
    phone     = request.form.get('phone',     '').strip()
    game_zone = request.form.get('game_zone', '').strip()
    duration  = request.form.get('duration',  '').strip()
    budget    = request.form.get('budget',    '').strip()

    if game_zone and game_zone not in GAME_ZONES:
        game_zone = ''
    if duration and duration not in DURATIONS:
        duration = ''

    conn = sqlite3.connect(DATABASE)
    c = conn.cursor()
    c.execute(
        "UPDATE persons SET full_name = ?, phone = ?, game_zone = ?, duration = ?, budget = ? WHERE id = ?",
        (full_name, phone, game_zone, duration, budget, person_id)
    )
    conn.commit()
    conn.close()
    flash('Данные обновлены.', 'success')
    return redirect(url_for('admin_panel', date=request.args.get('date', '')))


@app.route('/update_all', methods=['POST'])
@requires_auth
def update_all():
    """Массовое обновление записей (принимает JSON)"""
    data = request.get_json(force=True)
    if not isinstance(data, list):
        return jsonify({'success': False, 'message': 'Неверный формат данных'}), 400

    conn = sqlite3.connect(DATABASE)
    c = conn.cursor()
    updated = 0
    for item in data:
        pid       = item.get('id')
        full_name = item.get('full_name', '').strip()
        phone     = item.get('phone',     '').strip()
        game_zone = item.get('game_zone', '').strip()
        duration  = item.get('duration',  '').strip()
        budget    = item.get('budget',    '').strip()

        if not pid:
            continue
        if game_zone and game_zone not in GAME_ZONES:
            game_zone = ''
        if duration and duration not in DURATIONS:
            duration = ''

        c.execute(
            "UPDATE persons SET full_name = ?, phone = ?, game_zone = ?, duration = ?, budget = ? WHERE id = ?",
            (full_name, phone, game_zone, duration, budget, pid)
        )
        updated += c.rowcount

    conn.commit()
    conn.close()
    return jsonify({'success': True, 'updated': updated})


@app.route('/export-amo')
@requires_auth
def export_amo():
    filter_date = request.args.get('date', '').strip()
    export_all  = request.args.get('all',  '0')

    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    query  = "SELECT id, full_name, birth_date, phone, game_zone, duration, budget, created_at FROM persons"
    params = ()
    if filter_date and export_all != '1':
        query += " WHERE DATE(created_at) = ?"
        params = (filter_date,)
    query += " ORDER BY created_at ASC"
    cur.execute(query, params)
    persons = cur.fetchall()

    cur.execute("SELECT phone, MIN(id) as first_id FROM persons GROUP BY phone")
    first_occurrence = {row['phone']: row['first_id'] for row in cur.fetchall()}

    rows = []
    for p in persons:
        cur.execute(
            "SELECT child_name, child_birth_date FROM children WHERE person_id = ? ORDER BY id",
            (p['id'],)
        )
        children = cur.fetchall()

        if children:
            age = get_age(children[0]['child_birth_date'])
        else:
            age = get_age(p['birth_date'])

        child_names       = ', '.join([c['child_name']        for c in children]) if children else '-'
        child_birth_dates = ', '.join([c['child_birth_date']  for c in children]) if children else '-'

        created_str = p['created_at']
        if created_str:
            try:
                dt = datetime.strptime(created_str, '%Y-%m-%d %H:%M:%S')
                created_datetime = dt.strftime('%Y-%m-%d %H:%M')
            except ValueError:
                created_datetime = created_str
        else:
            created_datetime = ''

        zone = p['game_zone'] or ''
        dur  = p['duration']  or ''
        if zone and dur:
            deal_name = f"{zone} {dur}"
        elif zone:
            deal_name = f"{zone} (время не указано)"
        elif dur:
            deal_name = f"Игровая зона не указана {dur}"
        else:
            deal_name = f"Сделка {p['phone']}"

        client_type = 'Новый клиент'
        if p['phone'] in first_occurrence and p['id'] > first_occurrence[p['phone']]:
            client_type = 'Повторное посещение'

        rows.append({
            'Название сделки':        deal_name,
            'Этап сделки':            'Успешно реализовано',
            'ФИО клиента':            p['full_name'],
            'Тип клиента':            client_type,
            'Предоплата':             '0',
            'Дата и время создания':  created_datetime,
            'Длительность':           dur if dur else '60 мин',
            'Возраст':                age,
            'Источник':               'Оффлайн/На месте',
            'Вид мероприятия':        'одиночная игра',
            'Администратор':          '-',
            'Количество участников':  '1',
            'Дата и время начала':    created_datetime,
            'Имя ребенка':            child_names,
            'Дата рождения ребенка':  child_birth_dates,
            'Бюджет':                 p['budget'] or '',
            'Полное имя':             p['full_name'],
            'Рабочий телефон':        p['phone']
        })

    conn.close()

    if not rows:
        flash('Нет данных для экспорта.', 'warning')
        return redirect(url_for('admin_panel', date=filter_date))

    df = pd.DataFrame(rows)
    column_order = [
        'Название сделки', 'Этап сделки', 'ФИО клиента', 'Тип клиента',
        'Предоплата', 'Дата и время создания', 'Длительность', 'Возраст',
        'Источник', 'Вид мероприятия', 'Администратор', 'Количество участников',
        'Дата и время начала', 'Имя ребенка', 'Дата рождения ребенка', 'Бюджет',
        'Полное имя', 'Рабочий телефон'
    ]
    df = df[column_order]

    str_buffer = io.StringIO()
    df.to_csv(str_buffer, index=False, encoding='utf-8', lineterminator='\n', sep=';')
    csv_content = '\ufeff' + str_buffer.getvalue()
    output = io.BytesIO(csv_content.encode('utf-8'))
    output.seek(0)

    date_label = filter_date if (filter_date and export_all != '1') else 'all'
    filename   = f'amo_import_{date_label}.csv'

    return send_file(output, as_attachment=True, download_name=filename, mimetype='text/csv; charset=utf-8')


@app.route('/export')
@requires_auth
def export():
    filter_date = request.args.get('date', '').strip()
    export_all  = request.args.get('all',  '0')

    conn   = sqlite3.connect(DATABASE)
    query  = "SELECT id, full_name, birth_date, phone, game_zone, duration, budget, created_at FROM persons"
    params = ()
    if filter_date and export_all != '1':
        query += " WHERE DATE(created_at) = ?"
        params = (filter_date,)

    df = pd.read_sql_query(query, conn, params=params)
    conn.close()

    if df.empty:
        flash('База данных пуста. Нечего экспортировать.', 'warning')
        return redirect(url_for('admin_panel', date=filter_date))

    output_path = 'export_persons.xlsx'
    df.to_excel(output_path, index=False, engine='openpyxl')
    return send_file(output_path, as_attachment=True, download_name='persons_export.xlsx')


init_db()

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5001)
