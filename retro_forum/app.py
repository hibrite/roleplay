import os
import psycopg2
from psycopg2.extras import DictCursor
from flask import Flask, render_template, request, redirect, url_for, session, g

app = Flask(__name__)
app.secret_key = os.urandom(24)

# ==========================================
# 【請在這裡填入你剛剛在 Supabase 複製的 URI 網址】
# ==========================================
DATABASE_URL = "postgresql://postgres:c!XC94s56MHMZB#@db.jupusfomxhlxpyxmgega.supabase.co:5432/postgres"

def get_db():
    if 'db' not in g:
        g.db = psycopg2.connect(DATABASE_URL, cursor_factory=DictCursor)
    return g.db

@app.teardown_appcontext
def close_db(e):
    db = g.pop('db', None)
    if db is not None:
        db.close()

def init_db():
    with app.app_context():
        db = get_db()
        with db.cursor() as cur:
            # 建立使用者資料表
            cur.execute('''
                CREATE TABLE IF NOT EXISTS users (
                    id SERIAL PRIMARY KEY,
                    username TEXT UNIQUE NOT NULL,
                    password TEXT NOT NULL
                )
            ''')
            # 建立文章資料表
            cur.execute('''
                CREATE TABLE IF NOT EXISTS posts (
                    id SERIAL PRIMARY KEY,
                    username TEXT NOT NULL,
                    title TEXT NOT NULL,
                    content TEXT NOT NULL,
                    room TEXT NOT NULL,
                    timestamp TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            # 建立留言資料表
            cur.execute('''
                CREATE TABLE IF NOT EXISTS comments (
                    id SERIAL PRIMARY KEY,
                    post_id INTEGER NOT NULL,
                    username TEXT NOT NULL,
                    content TEXT NOT NULL,
                    timestamp TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            db.commit()

# 強制在每次啟動伺服器時，檢查並建立雲端資料表
with app.app_context():
    init_db()

@app.route('/')
def index():
    db = get_db()
    with db.cursor() as cur:
        cur.execute('SELECT * FROM posts ORDER BY timestamp DESC')
        posts = cur.fetchall()
        cur.execute('SELECT * FROM comments ORDER BY timestamp ASC')
        comments = cur.fetchall()
    
    current_user = session.get('current_user')
    user_list = session.get('user_list', [])
    return render_template('index.html', posts=posts, comments=comments, current_user=current_user, user_list=user_list)

@app.route('/login', methods=['POST'])
def login():
    username = request.form.get('username')
    password = request.form.get('password')
    action = request.form.get('action')
    
    db = get_db()
    with db.cursor() as cur:
        if action == 'register':
            try:
                cur.execute('INSERT INTO users (username, password) VALUES (%s, %s)', (username, password))
                db.commit()
            except psycopg2.IntegrityError:
                db.rollback()
                return "此使用者名稱已被註冊！<a href='/'>返回</a>"
        else:
            cur.execute('SELECT * FROM users WHERE username = %s AND password = %s', (username, password))
            user = cur.fetchone()
            if not user:
                return "密碼錯誤或使用者不存在！<a href='/'>返回</a>"
    
    session['current_user'] = username
    user_list = session.get('user_list', [])
    if username not in user_list:
        user_list.append(username)
        session['user_list'] = user_list
        
    return redirect(url_for('index'))

@app.route('/logout')
def logout():
    username = session.get('current_user')
    session.pop('current_user', None)
    user_list = session.get('user_list', [])
    if username in user_list:
        user_list.remove(username)
        session['user_list'] = user_list
    return redirect(url_for('index'))

@app.route('/post', methods=['POST'])
def post():
    if 'current_user' not in session:
        return redirect(url_for('index'))
    
    title = request.form.get('title')
    content = request.form.get('content')
    room = request.form.get('room')
    username = session['current_user']
    
    db = get_db()
    with db.cursor() as cur:
        cur.execute('INSERT INTO posts (username, title, content, room) VALUES (%s, %s, %s, %s)', (username, title, content, room))
        db.commit()
        
    return redirect(url_for('index'))

@app.route('/comment/<int:post_id>', methods=['POST'])
def comment(post_id):
    if 'current_user' not in session:
        return redirect(url_for('index'))
    
    content = request.form.get('content')
    username = session['current_user']
    
    db = get_db()
    with db.cursor() as cur:
        cur.execute('INSERT INTO comments (post_id, username, content) VALUES (%s, %s, %s)', (post_id, username, content))
        db.commit()
        
    return redirect(url_for('index'))

if __name__ == '__main__':
    app.run(debug=True)