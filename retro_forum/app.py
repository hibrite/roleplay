import os
import uuid  # 引入 UUID 庫
import psycopg2
import json
from psycopg2.extras import DictCursor
from flask import Flask, render_template, request, redirect, url_for, session, g, flash, make_response
from flask import session
from datetime import datetime

app = Flask(__name__)
app.secret_key = os.urandom(24)
DATABASE_URL = os.environ.get("DATABASE_URL")

def get_db():
    if 'db' not in g:
        if not DATABASE_URL:
            raise RuntimeError("DATABASE_URL 未設定！")
        g.db = psycopg2.connect(DATABASE_URL, cursor_factory=DictCursor)
    return g.db

def init_db():
    db = get_db()
    with db.cursor() as cur:
        cur.execute('''
            CREATE TABLE IF NOT EXISTS users (
                username VARCHAR(50) PRIMARY KEY,
                status VARCHAR(10) DEFAULT 'hidden',
                current_device_id TEXT DEFAULT NULL,
                bio TEXT DEFAULT ''
            )
        ''')
        cur.execute('''
            CREATE TABLE IF NOT EXISTS posts (
                id SERIAL PRIMARY KEY,
                username VARCHAR(50),
                title TEXT,
                content TEXT,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                status VARCHAR(10) DEFAULT 'visible',
                is_edited BOOLEAN DEFAULT FALSE,
                edit_history TEXT DEFAULT '[]'
            )
        ''')
        db.commit()

@app.teardown_appcontext
def close_db(e):
    db = g.pop('db', None)
    if db is not None:
        db.close()

with app.app_context():
    init_db()

def get_device_id():
    # 嘗試從 Cookie 取得 device_id
    device_id = request.cookies.get('device_id')
    # 如果沒有，則生成一個新的 UUID
    if not device_id:
        device_id = str(uuid.uuid4())
    return device_id

@app.route('/')
def index():
    # 確保每個訪問的人都有 device_id
    device_id = get_device_id()
    
    db = get_db()
    with db.cursor() as cur:
        cur.execute('SELECT * FROM posts WHERE status != %s ORDER BY timestamp DESC', ('deleted',))
        posts = cur.fetchall()
        
        cur.execute('SELECT username, bio FROM users')
        user_list = cur.fetchall()
        
    # 設定 Response，把 device_id 塞進 Cookie 存起來
    resp = make_response(render_template('index.html', user_list=user_list, posts=posts, current_user=session.get('current_user')))
    resp.set_cookie('device_id', device_id, max_age=60*60*24*365*10) # 保存一年
    return resp

@app.route('/register', methods=['POST'])
def register():
    username = request.form.get('username').strip()
    device_id = get_device_id()
    if not username: return redirect(url_for('index'))
    db = get_db()
    with db.cursor() as cur:
        cur.execute('SELECT username FROM users WHERE username = %s', (username,))
        if cur.fetchone():
            flash('此帳號已存在，請更換名稱！', 'error')
        else:
            # 存入 status 為 active 與目前的 device_id
            cur.execute('INSERT INTO users (username, status, current_device_id) VALUES (%s, %s, %s)', 
                        (username, 'active', device_id))
            db.commit()
            session['current_user'] = username
    return redirect(url_for('index'))

@app.route('/login', methods=['POST'])
def login():
    username = request.form.get('username', '').strip()
    device_id = get_device_id() # 使用從 Cookie 讀到的 ID
    
    db = get_db()
    with db.cursor() as cur:
        cur.execute('SELECT status, current_device_id FROM users WHERE username = %s', (username,))
        user = cur.fetchone()
        
        if user:
            # 檢查是否已綁定且裝置不符
            if user['status'] == 'active' and user['current_device_id'] != device_id:
                flash('此帳號已在其他裝置登入！', 'error')
            else:
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
        # 解除狀態並清空 device_id
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

# 處理編輯個人檔案的資料更新
@app.route('/update_profile/<old_username>', methods=['POST'])
def update_profile(old_username):
    new_username = request.form.get('new_username').strip()
    bio = request.form.get('bio').strip()
    
    db = get_db()
    with db.cursor() as cur:
        # 更新使用者資料
        cur.execute('UPDATE users SET username = %s, bio = %s WHERE username = %s', 
                    (new_username, bio, old_username))
        db.commit()
        
        # 如果正在登入中，同步更新 session
        if session.get('current_user') == old_username:
            session['current_user'] = new_username
            
    return redirect(url_for('index'))

@app.route('/delete_post/<int:post_id>')
def delete_post(post_id):
    current_user = session.get('current_user')
    db = get_db()
    with db.cursor() as cur:
        # 檢查該貼文是否屬於當前用戶，防止惡意刪除他人貼文
        cur.execute('UPDATE posts SET status = %s WHERE id = %s AND username = %s', 
                    ('deleted', post_id, current_user))
        db.commit()
    return redirect(url_for('index'))

@app.route('/edit_post/<int:post_id>', methods=['POST'])
def edit_post(post_id):
    current_user = session.get('current_user')
    new_title = request.form['title']
    new_content = request.form['content']
    
    db = get_db()
    with db.cursor() as cur:
        # 1. 取得舊資料以寫入歷史
        cur.execute('SELECT content, edit_history FROM posts WHERE id = %s AND username = %s', (post_id, current_user))
        post = cur.fetchone()
        
        if post:
            history = json.loads(post['edit_history'])
            history.append({'content': post['content'], 'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M')})
            
            # 2. 更新資料
            cur.execute('''UPDATE posts SET title = %s, content = %s, is_edited = TRUE, edit_history = %s 
                           WHERE id = %s''', 
                        (new_title, new_content, json.dumps(history), post_id))
            db.commit()
            
    return redirect(url_for('index'))

if __name__ == '__main__':
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))