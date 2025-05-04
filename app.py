from flask import Flask, request, jsonify, render_template
import sqlite3
import os
from datetime import datetime, timedelta
from urllib.parse import urlparse

app = Flask(__name__, template_folder='templates', static_folder='static')

# 数据库文件路径
DB_FILE = 'recharge.db'


def init_db():
    """初始化数据库"""
    conn = get_db()
    cursor = conn.cursor()

        # 创建用户表，添加钻石余额字段
        cursor.execute('''
        CREATE TABLE users (
            user_id TEXT PRIMARY KEY,
            username TEXT NOT NULL,
            password TEXT NOT NULL,
            phone TEXT,
            balance REAL DEFAULT 0.00,
            diamonds INTEGER DEFAULT 0,
            vip_type TEXT DEFAULT NULL,
            vip_expire_date TIMESTAMP DEFAULT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        ''')

        # 创建充值记录表
        cursor.execute('''
        CREATE TABLE recharge_records (
            record_id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT NOT NULL,
            amount REAL NOT NULL,
            recharge_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            status TEXT DEFAULT 'success',
            payment_method TEXT,
            FOREIGN KEY (user_id) REFERENCES users(user_id)
        )
        ''')

        # 创建商城商品表
        cursor.execute('''
        CREATE TABLE shop_items (
            item_id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            price INTEGER NOT NULL
        )
        ''')

        # 创建用户皮肤拥有表
        cursor.execute('''
        CREATE TABLE user_skins (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT NOT NULL,
            item_id INTEGER NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users(user_id),
            FOREIGN KEY (item_id) REFERENCES shop_items(item_id)
        )
        ''')

        # 插入商城商品
        shop_items = [
            ('皮肤1', 100),
            ('皮肤2', 200),
            ('皮肤3', 300),
            ('皮肤4', 400),
            ('皮肤5', 500),
            ('皮肤6', 600)
        ]
        cursor.executemany("INSERT INTO shop_items (name, price) VALUES (?,?)", shop_items)

        conn.commit()
        conn.close()

# 数据库连接函数
def get_db():
    if os.environ.get('RENDER'):
        # Render环境使用PostgreSQL
        db_url = os.environ.get('DATABASE_URL')
        conn = psycopg2.connect(db_url)
    else:
        # 本地开发使用SQLite
        import sqlite3
        conn = sqlite3.connect('local.db')
        conn.row_factory = sqlite3.Row
    return conn


# 初始化数据库
init_db()


@app.route('/')
def index():
    """首页，显示登录界面"""
    return render_template('login.html')


@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        phone = request.form.get('phone')
        password = request.form.get('password')
        confirm_password = request.form.get('confirm_password')

        if password != confirm_password:
            return jsonify({'success': False, 'message': '两次输入的密码不一致'}), 400

        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("SELECT MAX(CAST(SUBSTR(user_id, 5) AS INTEGER)) FROM users")
        last_id = cursor.fetchone()[0]
        if last_id is None:
            new_id = 1
        else:
            new_id = last_id + 1
        user_id = f"2025{new_id:03d}"

        try:
            cursor.execute("INSERT INTO users (user_id, username, password, phone) VALUES (?,?,?,?)",
                           (user_id, phone, password, phone))
            conn.commit()
            return jsonify({'success': True, 'message': '注册成功', 'user_id': user_id})
        except sqlite3.IntegrityError:
            return jsonify({'success': False, 'message': '注册失败，请重试'}), 500
        finally:
            conn.close()
    return render_template('register.html')


@app.route('/login', methods=['POST'])
def login():
    user_id = request.form.get('user_id')
    password = request.form.get('password')

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE user_id =? AND password =?", (user_id, password))
    user = cursor.fetchone()
    conn.close()

    if user:
        return jsonify({'success': True, 'message': '登录成功', 'user_id': user_id})
    else:
        return jsonify({'success': False, 'message': '用户名或密码错误'}), 401


@app.route('/dashboard')
def dashboard():
    user_id = request.args.get('user_id')
    return render_template('dashboard.html', user_id=user_id)


# 获取用户钻石余额
@app.route('/api/diamonds/<user_id>', methods=['GET'])
def get_diamonds(user_id):
    try:
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute('SELECT diamonds FROM users WHERE user_id =?', (user_id,))
        user = cursor.fetchone()

        if user:
            return jsonify({'diamonds': user['diamonds']})
        else:
            return jsonify({'error': '用户不存在'}), 404
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        conn.close()


# 获取商城商品列表及用户拥有情况
@app.route('/api/shop_items/<user_id>', methods=['GET'])
def get_shop_items(user_id):
    try:
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM shop_items')
        items = []
        for row in cursor.fetchall():
            cursor.execute('SELECT * FROM user_skins WHERE user_id =? AND item_id =?', (user_id, row['item_id']))
            owned = cursor.fetchone() is not None
            items.append({
                'item_id': row['item_id'],
                'name': row['name'],
                'price': row['price'],
                'owned': owned
            })
        return jsonify(items)
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        conn.close()


# 充值接口
@app.route('/api/recharge', methods=['POST'])
def recharge():
    try:
        data = request.get_json()
        user_id = data.get('user_id')
        amount = data.get('amount', 0)
        payment_method = data.get('payment_method')
        password = data.get('password')

        if amount not in [6, 30, 98, 198, 328, 648]:
            return jsonify({'success': False, 'message': '不支持的充值金额'}), 400

        conn = get_db()
        cursor = conn.cursor()

        # 开始事务
        conn.execute('BEGIN TRANSACTION')

        # 1. 创建充值记录
        cursor.execute('''
            INSERT INTO recharge_records (user_id, amount, payment_method)
            VALUES (?,?,?)
        ''', (user_id, amount, payment_method))

        # 2. 更新用户余额
        cursor.execute('''
            UPDATE users 
            SET balance = balance +? 
            WHERE user_id =?
        ''', (amount, user_id))

        # 3. 更新用户钻石余额
        diamonds_to_add = amount * 10
        cursor.execute('''
            UPDATE users 
            SET diamonds = diamonds +? 
            WHERE user_id =?
        ''', (diamonds_to_add, user_id))

        # 提交事务
        conn.commit()

        # 获取更新后的钻石余额
        cursor.execute('SELECT diamonds FROM users WHERE user_id =?', (user_id,))
        new_diamonds = cursor.fetchone()['diamonds']

        return jsonify({
            'success': True,
            'new_diamonds': new_diamonds
        })
    except Exception as e:
        conn.rollback()
        return jsonify({'success': False, 'message': str(e)}), 500
    finally:
        conn.close()


# 购买商品接口
@app.route('/api/buy_item', methods=['POST'])
def buy_item():
    try:
        data = request.get_json()
        user_id = data.get('user_id')
        item_id = data.get('item_id')

        conn = get_db()
        cursor = conn.cursor()

        # 获取用户钻石余额
        cursor.execute('SELECT diamonds FROM users WHERE user_id =?', (user_id,))
        user = cursor.fetchone()
        user_diamonds = user['diamonds']

        # 获取商品价格
        cursor.execute('SELECT price FROM shop_items WHERE item_id =?', (item_id,))
        item = cursor.fetchone()
        item_price = item['price']

        if user_diamonds < item_price:
            return jsonify({'success': False, 'message': '钻石余额不足'}), 400

        # 检查用户是否已经拥有该皮肤
        cursor.execute('SELECT * FROM user_skins WHERE user_id =? AND item_id =?', (user_id, item_id))
        owned = cursor.fetchone()
        if owned:
            return jsonify({'success': False, 'message': '你已经拥有该皮肤'}), 400

        # 开始事务
        conn.execute('BEGIN TRANSACTION')

        # 扣除用户钻石余额
        cursor.execute('''
            UPDATE users 
            SET diamonds = diamonds -? 
            WHERE user_id =?
        ''', (item_price, user_id))

        # 记录用户拥有的皮肤
        cursor.execute('INSERT INTO user_skins (user_id, item_id) VALUES (?,?)', (user_id, item_id))

        # 提交事务
        conn.commit()

        # 获取更新后的钻石余额
        cursor.execute('SELECT diamonds FROM users WHERE user_id =?', (user_id,))
        new_diamonds = cursor.fetchone()['diamonds']

        return jsonify({
            'success': True,
            'new_diamonds': new_diamonds
        })
    except Exception as e:
        conn.rollback()
        return jsonify({'success': False, 'message': str(e)}), 500
    finally:
        conn.close()


# 获取用户中心信息
@app.route('/api/user_center/<user_id>', methods=['GET'])
def user_center(user_id):
    try:
        conn = get_db()
        cursor = conn.cursor()

        # 获取用户基本信息
        cursor.execute('SELECT user_id, phone, diamonds, vip_type, vip_expire_date FROM users WHERE user_id =?',
                       (user_id,))
        user = cursor.fetchone()

        # 获取用户拥有的皮肤
        cursor.execute('''
            SELECT si.name 
            FROM user_skins us 
            JOIN shop_items si ON us.item_id = si.item_id 
            WHERE us.user_id =?
        ''', (user_id,))
        skins = [row['name'] for row in cursor.fetchall()]

        return jsonify({
            'user_id': user['user_id'],
            'phone': user['phone'],
            'diamonds': user['diamonds'],
            'vip_type': user['vip_type'],
            'vip_expire_date': user['vip_expire_date'],
            'skins': skins
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        conn.close()


# 会员购买接口
@app.route('/api/buy_vip', methods=['POST'])
def buy_vip():
    try:
        data = request.get_json()
        user_id = data.get('user_id')
        vip_type = data.get('vip_type')
        payment_method = data.get('payment_method')
        password = data.get('password')

        amount = 30 if vip_type == '小会员' else 120

        conn = get_db()
        cursor = conn.cursor()

        # 获取用户余额
        cursor.execute('SELECT balance FROM users WHERE user_id =?', (user_id,))
        user = cursor.fetchone()
        user_balance = user['balance']

        if user_balance < amount:
            return jsonify({'success': False, 'message': '余额不足，请先充值'}), 400

        # 开始事务
        conn.execute('BEGIN TRANSACTION')

        # 扣除用户余额
        cursor.execute('''
            UPDATE users 
            SET balance = balance -? 
            WHERE user_id =?
        ''', (amount, user_id))

        # 更新用户会员信息
        expire_date = datetime.now() + timedelta(days=30)
        cursor.execute('''
            UPDATE users 
            SET vip_type =?, vip_expire_date =? 
            WHERE user_id =?
        ''', (vip_type, expire_date, user_id))

        # 创建充值记录
        cursor.execute('''
            INSERT INTO recharge_records (user_id, amount, payment_method)
            VALUES (?,?,?)
        ''', (user_id, amount, payment_method))

        # 提交事务
        conn.commit()

        # 获取更新后的钻石余额
        cursor.execute('SELECT diamonds FROM users WHERE user_id =?', (user_id,))
        new_diamonds = cursor.fetchone()['diamonds']

        return jsonify({
            'success': True,
            'new_diamonds': new_diamonds
        })
    except Exception as e:
        conn.rollback()
        return jsonify({'success': False, 'message': str(e)}), 500
    finally:
        conn.close()


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
