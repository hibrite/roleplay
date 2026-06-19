import os
import psycopg2
from psycopg2.extras import DictCursor
from flask import Flask, render_template, request, redirect, url_for, session, g, flash
from flask import session

app = Flask(__name__)
app.secret_key = os.urandom(24)
DATABASE_URL = os.environ.get("DATABASE_URL")

def get_db():
    if 'db' not in g:
        g.db = psycopg2.connect(DATABASE_URL, cursor_factory=DictCursor)
    return g.db

def init_db():
    db = get_db()
    with db.cursor() as cur:
        cur.execute('''
            CREATE TABLE IF NOT EXISTS users (
                username VARCHAR(50) PRIMARY KEY,
                status VARCHAR(10) DEFAULT 'active',
                current_device_id VARCHAR(100) DEFAULT NULL
            )
        ''')
        db.commit()

@app.teardown_appcontext
def close_db(e):
    db = g.pop('db', None)
    if db is not None:
        db.close()

@app.route('/')
def index():
    db = get_db()
    with db.cursor() as cur:
        cur.execute('SELECT * FROM posts ORDER BY timestamp DESC')
        posts = cur.fetchall()
        
        # 關鍵：只抓取狀態為 active 的用戶
        cur.execute('SELECT username FROM users WHERE status = %s', ('active',))
        user_list = [row['username'] for row in cur.fetchall()]
        
    return render_template('index.html', posts=posts, user_list=user_list, current_user=session.get('current_user'))

@app.route('/register', methods=['POST'])
def register():
    username = request.form.get('username').strip()
    if not username: return redirect(url_for('index'))
    db = get_db()
    with db.cursor() as cur:
        cur.execute('SELECT username FROM users WHERE username = %s', (username,))
        if cur.fetchone():
            flash('此帳號已存在，請更換名稱！', 'error')
        else:
            cur.execute('INSERT INTO users (username) VALUES (%s)', (username,))
            db.commit()
            session['current_user'] = username
    return redirect(url_for('index'))

@app.route('/login', methods=['POST'])
def login():
    username = request.form.get('username').strip()
    device_id = session.sid  # 獲取當前瀏覽器的唯一 session ID
    db = get_db()
    with db.cursor() as cur:
        # 檢查帳號是否存在
        cur.execute('SELECT current_device_id FROM users WHERE username = %s', (username,))
        user = cur.fetchone()
        
        if user:
            # 判斷是否已被其他人登入 (current_device_id 不為空且不是自己)
            if user['current_device_id'] and user['current_device_id'] != device_id:
                flash('此帳號已在其他裝置登入，請先於該裝置登出！', 'error')
            else:
                # 登入成功，鎖定此裝置
                cur.execute('UPDATE users SET status = %s, current_device_id = %s WHERE username = %s', 
                            ('active', device_id, username))
                db.commit()
                session['current_user'] = username
        else:
            flash('查無此帳號！', 'error')
    return redirect(url_for('index'))

@app.route('/switch_user/<username>')
def switch_user(username):
    session['current_user'] = username
    return redirect(url_for('index'))

@app.route('/delete_user/<username>')
def delete_user(username):
    db = get_db()
    with db.cursor() as cur:
        # 刪除該使用者
        cur.execute('DELETE FROM users WHERE username = %s', (username,))
        db.commit()
        # 如果剛好是目前登入的使用者，執行登出
        if session.get('current_user') == username:
            session.pop('current_user', None)
    return redirect(url_for('index'))

@app.route('/logout/<username>')
def logout_user(username):
    db = get_db()
    with db.cursor() as cur:
        # 登出時，解除裝置鎖定並隱藏帳號
        cur.execute('UPDATE users SET status = %s, current_device_id = NULL WHERE username = %s', 
                    ('hidden', username))
        db.commit()
        if session.get('current_user') == username:
            session.pop('current_user', None)
    return redirect(url_for('index'))

@app.route('/create_post', methods=['POST'])
def create_post():
    if 'current_user' not in session: return redirect(url_for('index'))
    title, content = request.form.get('title'), request.form.get('content')
    db = get_db()
    with db.cursor() as cur:
        cur.execute('INSERT INTO posts (username, title, content) VALUES (%s, %s, %s)', (session['current_user'], title, content))
        db.commit()
    return redirect(url_for('index'))

if __name__ == '__main__':
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))