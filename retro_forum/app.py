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
        # 新增欄位 (安全執行)
        cur.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS permission VARCHAR(20) DEFAULT '初級'")
        cur.execute("ALTER TABLE posts ADD COLUMN IF NOT EXISTS likes INTEGER DEFAULT 0")
        cur.execute("ALTER TABLE posts ADD COLUMN IF NOT EXISTS board VARCHAR(50) DEFAULT '一般討論'")
        
        cur.execute('''CREATE TABLE IF NOT EXISTS comments (
            id SERIAL PRIMARY KEY,
            post_id INTEGER REFERENCES posts(id),
            username VARCHAR(50),
            content TEXT,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )''')
        # 維持原本的 Table 建立邏輯
        cur.execute('''CREATE TABLE IF NOT EXISTS users (
                username VARCHAR(50) PRIMARY KEY,
                status VARCHAR(10) DEFAULT 'hidden',
                current_device_id TEXT DEFAULT NULL,
                bio TEXT DEFAULT '',
                permission VARCHAR(20) DEFAULT '初級'
            )''')
        cur.execute('''CREATE TABLE IF NOT EXISTS posts (
                id SERIAL PRIMARY KEY,
                username VARCHAR(50),
                title TEXT,
                content TEXT,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                status VARCHAR(10) DEFAULT 'visible',
                is_edited BOOLEAN DEFAULT FALSE,
                edit_history TEXT DEFAULT '[]',
                likes INTEGER DEFAULT 0,
                board VARCHAR(50) DEFAULT '一般討論'
            )''')
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
    device_id = request.cookies.get('device_id') or str(uuid.uuid4())
    db = get_db()
    with db.cursor() as cur:
        # 1. 抓取所有貼文 (用於主頁)
        cur.execute('SELECT * FROM posts WHERE status != %s ORDER BY id DESC', ('deleted',))
        posts = cur.fetchall()
        
        # 2. 抓取熱門貼文 (用於側邊欄)
        cur.execute('SELECT * FROM posts WHERE status != %s ORDER BY likes DESC LIMIT 5', ('deleted',))
        hot_posts = cur.fetchall()
        
    resp = make_response(render_template('index.html', posts=posts, hot_posts=hot_posts, current_user=session.get('current_user')))
    resp.set_cookie('device_id', device_id, max_age=60*60*24*365*10, httponly=True)
    return resp

@app.route('/like_post/<int:post_id>')
def like_post(post_id):
    db = get_db()
    with db.cursor() as cur:
        cur.execute('UPDATE posts SET likes = likes + 1 WHERE id = %s', (post_id,))
        db.commit()
    return redirect(url_for('index'))

@app.route('/register', methods=['POST'])
def register():
    username = request.form.get('username', '').strip()
    device_id = get_device_id()
    if not username: return redirect(url_for('index'))

    db = get_db()
    with db.cursor() as cur:
        cur.execute('SELECT username FROM users WHERE username = %s AND status != %s', (username, 'deleted'))
        if cur.fetchone():
            flash('此帳號已存在，請更換名稱！', 'error')
        else:
            cur.execute('INSERT INTO users (username, status, current_device_id) VALUES (%s, %s, %s)', 
                        (username, 'active', device_id))
            db.commit()
            session['current_user'] = username
    return redirect(url_for('index'))

@app.route('/login', methods=['POST'])
def login():
    username = request.form.get('username', '').strip()
    device_id = request.cookies.get('device_id')
    
    db = get_db()
    with db.cursor() as cur:
        cur.execute('SELECT status, current_device_id FROM users WHERE username = %s', (username,))
        user = cur.fetchone()
        
        if user:
            # 如果這帳號已經被別的裝置佔用了
            if user['current_device_id'] and user['current_device_id'] != device_id:
                flash('此帳號已在其他裝置登入中！', 'error')
            else:
                # 登入成功，將此裝置 ID 綁定到該帳號
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
        # 1. 確保只處理非已刪除狀態的帳號，防止重複疊加
        cur.execute('SELECT status FROM users WHERE username = %s', (username,))
        user = cur.fetchone()
        
        if user and user['status'] != 'deleted':
            # 建立一個唯一的刪除後名稱
            timestamp = int(datetime.now().timestamp())
            new_name = f"{username}_deleted_{timestamp}"
            
            # 2. 更新使用者名稱與狀態
            cur.execute('UPDATE users SET username = %s, status = %s WHERE username = %s', 
                        (new_name, 'deleted', username))
            
            # 3. 同步修改該用戶發出的所有貼文名稱 (關鍵步驟！)
            cur.execute('UPDATE posts SET username = %s WHERE username = %s', 
                        (new_name, username))
            
            db.commit()
            flash(f'帳號 {username} 已成功註銷。', 'success')
        else:
            flash('此帳號已註銷或不存在。', 'error')

        # 4. 如果目前登入的是此帳號，強制登出
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

@app.route('/add_comment/<int:post_id>', methods=['POST'])
def add_comment(post_id):
    if 'current_user' not in session:
        flash('請先登入後再留言！', 'error')
        return redirect(url_for('view_post', post_id=post_id))
    
    content = request.form.get('content', '').strip()
    if not content:
        flash('留言內容不能為空！', 'error')
        return redirect(url_for('view_post', post_id=post_id))

    db = get_db()
    with db.cursor() as cur:
        # 檢查貼文是否存在
        cur.execute('SELECT id FROM posts WHERE id = %s AND status != %s', (post_id, 'deleted'))
        if not cur.fetchone():
            flash('此貼文不存在。', 'error')
            return redirect(url_for('index'))
            
        cur.execute('INSERT INTO comments (post_id, username, content) VALUES (%s, %s, %s)', 
                    (post_id, session['current_user'], content))
        db.commit()
        
    return redirect(url_for('view_post', post_id=post_id))

@app.route('/post/<int:post_id>')
def view_post(post_id):
    db = get_db()
    with db.cursor() as cur:
        # 獲取貼文
        cur.execute('SELECT * FROM posts WHERE id = %s', (post_id,))
        post = cur.fetchone()
        # 獲取留言
        cur.execute('SELECT * FROM comments WHERE post_id = %s ORDER BY timestamp ASC', (post_id,))
        comments = cur.fetchall()
    return render_template('post_detail.html', post=post, comments=comments, current_user=session.get('current_user'))

if __name__ == '__main__':
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))