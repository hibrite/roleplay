import os
import sqlite3
from flask import Flask, render_template, request, redirect, url_for, session, g

app = Flask(__name__)
# 設定密鑰以啟用 Session 功能，確保多人登入不串線
app.secret_key = os.urandom(24)
DATABASE = 'database.db'
# 強制在每次啟動網頁伺服器時，都檢查並初始化資料庫
with app.app_context():
    init_db()

def get_db():
    db = getattr(g, '_database', None)
    if db is None:
        db = g._database = sqlite3.connect(DATABASE)
        db.row_factory = sqlite3.Row
    return db

@app.teardown_appcontext
def close_connection(exception):
    db = getattr(g, '_database', None)
    if db is not None:
        db.close()

# 初始化資料庫
def init_db():
    with app.app_context():
        db = get_db()
        # 使用者資料表
        db.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL
            )
        ''')
        # 文章資料表
        db.execute('''
            CREATE TABLE IF NOT EXISTS posts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                content TEXT NOT NULL,
                author TEXT NOT NULL,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        # 留言資料表
        db.execute('''
            CREATE TABLE IF NOT EXISTS comments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                post_id INTEGER NOT NULL,
                content TEXT NOT NULL,
                author TEXT NOT NULL,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(post_id) REFERENCES posts(id)
            )
        ''')
        db.commit()

@app.route('/')
def index():
    db = get_db()
    
    # 確保 Session 裡的帳號清單存在
    if 'user_list' not in session:
        session['user_list'] = []
    if 'current_user' not in session:
        session['current_user'] = None

    # 撈取所有文章（依照時間倒序）
    posts = db.execute('SELECT * FROM posts ORDER BY timestamp DESC').fetchall()
    
    # 撈取所有留言
    comments = db.execute('SELECT * FROM comments ORDER BY timestamp ASC').fetchall()
    
    return render_template('index.html', 
                           posts=posts, 
                           comments=comments,
                           current_user=session['current_user'], 
                           user_list=session['user_list'])

# 創建或登入新帳號
@app.route('/login', methods=['POST'])
def login():
    username = request.form.get('username').strip()
    if username:
        db = get_db()
        # 如果使用者不存在，就建立新帳號
        try:
            db.execute('INSERT INTO users (username) VALUES (?)', (username,))
            db.commit()
        except sqlite3.IntegrityError:
            pass # 帳號已存在，直接允許登入
        
        # 將帳號加入當前瀏覽器的快速切換清單
        ulist = session.get('user_list', [])
        if username not in ulist:
            ulist.append(username)
            session['user_list'] = ulist
            
        session['current_user'] = username
    return redirect(url_for('index'))

# 快速切換帳號
@app.route('/switch_user/<username>')
def switch_user(username):
    if 'user_list' in session and username in session['user_list']:
        session['current_user'] = username
    return redirect(url_for('index'))

# 登出當前帳號（從側邊欄移除）
@app.route('/logout/<username>')
def logout(username):
    ulist = session.get('user_list', [])
    if username in ulist:
        ulist.remove(username)
        session['user_list'] = ulist
    if session.get('current_user') == username:
        session['current_user'] = ulist[0] if ulist else None
    return redirect(url_for('index'))

# 發布新文章
@app.route('/create_post', methods=['POST'])
def create_post():
    if not session.get('current_user'):
        return redirect(url_for('index'))
    
    title = request.form.get('title')
    content = request.form.get('content')
    author = session['current_user']
    
    if title and content:
        db = get_db()
        db.execute('INSERT INTO posts (title, content, author) VALUES (?, ?, ?)', (title, content, author))
        db.commit()
    return redirect(url_for('index'))

# 發表留言
@app.route('/create_comment/<int:post_id>', methods=['POST'])
def create_comment(post_id):
    if not session.get('current_user'):
        return redirect(url_for('index'))
    
    content = request.form.get('content')
    author = session['current_user']
    
    if content:
        db = get_db()
        db.execute('INSERT INTO comments (post_id, content, author) VALUES (?, ?, ?)', (post_id, content, author))
        db.commit()
    return redirect(url_for('index'))

if __name__ == '__main__':
    init_db()
    # 取得雲端平台指派的 Port，預設為 5000
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)