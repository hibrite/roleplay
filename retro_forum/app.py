import os
import psycopg2
from psycopg2.extras import DictCursor
from flask import Flask, render_template, request, redirect, url_for, session, g

app = Flask(__name__)
app.secret_key = os.urandom(24)

# 確保從 Render 的環境變數讀取，若無則使用預設值
DATABASE_URL = os.environ.get("DATABASE_URL")

def get_db():
    if 'db' not in g:
        g.db = psycopg2.connect(DATABASE_URL, cursor_factory=DictCursor)
    return g.db

@app.teardown_appcontext
def close_db(e):
    db = g.pop('db', None)
    if db is not None:
        db.close()

# 首頁：顯示所有文章與用戶列表
@app.route('/')
def index():
    db = get_db()
    with db.cursor() as cur:
        # 抓取文章
        cur.execute('SELECT * FROM posts ORDER BY timestamp DESC')
        posts = cur.fetchall()
        # 抓取所有用戶供側欄切換
        cur.execute('SELECT * FROM users')
        users = cur.fetchall()
    return render_template('index.html', posts=posts, users=users, current_user=session.get('current_user'))

# 註冊帳號
@app.route('/register', methods=['POST'])
def register():
    username = request.form.get('username').strip()
    if username:
        db = get_db()
        with db.cursor() as cur:
            try:
                cur.execute('INSERT INTO users (username) VALUES (%s)', (username,))
                db.commit()
            except:
                db.rollback() # 避免重複註冊錯誤
        session['current_user'] = username
    return redirect(url_for('index'))

# 登入帳號
@app.route('/login', methods=['POST'])
def login():
    username = request.form.get('username').strip()
    db = get_db()
    with db.cursor() as cur:
        cur.execute('SELECT * FROM users WHERE username = %s', (username,))
        user = cur.fetchone()
        if user:
            session['current_user'] = username
    return redirect(url_for('index'))

# 切換帳號
@app.route('/switch_user/<username>')
def switch_user(username):
    session['current_user'] = username
    return redirect(url_for('index'))

# 發布文章
@app.route('/post', methods=['POST'])
def post():
    if 'current_user' not in session: return redirect(url_for('index'))
    title = request.form.get('title')
    content = request.form.get('content')
    username = session['current_user']
    db = get_db()
    with db.cursor() as cur:
        cur.execute('INSERT INTO posts (username, title, content) VALUES (%s, %s, %s)', (username, title, content))
        db.commit()
    return redirect(url_for('index'))

# 登出
@app.route('/logout')
def logout():
    session.pop('current_user', None)
    return redirect(url_for('index'))

if __name__ == '__main__':
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))