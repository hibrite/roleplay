import os
import psycopg2
from psycopg2.extras import DictCursor
from flask import Flask, render_template, request, redirect, url_for, session

app = Flask(__name__)
# 設定 Session 金鑰，用於記錄登入狀態
app.secret_key = os.urandom(24)

# 從環境變數讀取資料庫網址 [cite: 1, 33]
DATABASE_URL = os.environ.get("DATABASE_URL")

def get_db():
    # 建立資料庫連線
    return psycopg2.connect(DATABASE_URL, cursor_factory=DictCursor)

@app.route('/')
def index():
    db = get_db()
    with db.cursor() as cur:
        # 獲取所有文章 (依時間倒序)
        cur.execute('SELECT * FROM posts ORDER BY timestamp DESC')
        posts = cur.fetchall()
        # 獲取所有已註冊帳號，用於側欄顯示
        cur.execute('SELECT username FROM users')
        user_list = [row['username'] for row in cur.fetchall()]
    db.close()
    return render_template('index.html', posts=posts, user_list=user_list, current_user=session.get('current_user'))

@app.route('/login', methods=['POST'])
def login():
    username = request.form.get('username').strip()
    if not username:
        return redirect(url_for('index'))
    
    db = get_db()
    with db.cursor() as cur:
        cur.execute('SELECT * FROM users WHERE username = %s', (username,))
        user = cur.fetchone()
        if user:
            # 帳號存在，直接登入
            session['current_user'] = username
        else:
            # 帳號不存在，自動註冊並登入
            cur.execute('INSERT INTO users (username) VALUES (%s)', (username,))
            db.commit()
            session['current_user'] = username
    db.close()
    return redirect(url_for('index'))

@app.route('/switch_user/<username>')
def switch_user(username):
    # 切換當前操作帳號
    session['current_user'] = username
    return redirect(url_for('index'))

@app.route('/logout/<username>')
def logout_user(username):
    # 登出並移除該帳號的使用權限
    if session.get('current_user') == username:
        session.pop('current_user', None)
    return redirect(url_for('index'))

@app.route('/create_post', methods=['POST'])
def create_post():
    if 'current_user' not in session:
        return redirect(url_for('index'))
    title = request.form.get('title')
    content = request.form.get('content')
    db = get_db()
    with db.cursor() as cur:
        cur.execute('INSERT INTO posts (username, title, content) VALUES (%s, %s, %s)', 
                    (session['current_user'], title, content))
        db.commit()
    db.close()
    return redirect(url_for('index'))

if __name__ == '__main__':
    # 啟動應用程式
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))