"""Persistent catalogue and local administrator credentials. No external dependencies."""
import hashlib
from contextlib import contextmanager
import hmac
import json
import os
import re
from pathlib import Path
import secrets
import sqlite3
import time
import uuid

VEHICLES = {'car', 'moto', 'scooter', 'escooter', 'bike', 'other'}
CATEGORIES = {'mounts', 'electronics', 'storage', 'care'}


def password_hash(password, salt=None):
    salt = salt or secrets.token_hex(16)
    digest = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt), n=16384, r=8, p=1).hex()
    return salt + ':' + digest


def password_matches(password, stored):
    return hmac.compare_digest(password_hash(password, stored.split(':')[0]), stored)


def validate_product(data, categories=None):
    if not isinstance(data, dict):
        raise ValueError('A product object is required.')
    def string(key, limit, required=False):
        value = data.get(key, '')
        if not isinstance(value, str) or len(value) > limit:
            raise ValueError(f'{key}: maximum {limit} characters.')
        value = value.strip()
        if required and not value:
            raise ValueError(f'{key} is required.')
        return value
    product = {key: string(key, limit, required) for key, limit, required in (
        ('name', 140, True), ('sku', 80, True), ('description', 3000, False),
        ('admin_comment', 3000, False), ('lead_time', 240, False), ('image', 200, False))}
    images = data.get('images', [product['image']] if product['image'] else [])
    if not isinstance(images, list) or len(images) > 12 or any(not isinstance(image, str) or not image or len(image) > 200 for image in images):
        raise ValueError('Choose up to 12 valid product images.')
    product['images'] = list(dict.fromkeys(images))
    product['image'] = product['images'][0] if product['images'] else ''
    for key, options in [('category', CATEGORIES if categories is None else categories), ('status', {'draft', 'active', 'archived'}),
                         ('availability', {'concept', 'preorder', 'stock'})]:
        if data.get(key) not in options:
            raise ValueError(f'Invalid {key}.')
        product[key] = data[key]
    price = data.get('price_cents')
    if price is not None and (type(price) is not int or not 1 <= price <= 100000000):
        raise ValueError('Price must be between CHF 0.01 and CHF 1,000,000.')
    product['price_cents'] = price
    stock = data.get('stock', 0)
    if type(stock) is not int or not 0 <= stock <= 100000:
        raise ValueError('Stock must be a whole number between 0 and 100,000.')
    product['stock'] = stock
    if product['availability'] != 'concept' and price is None:
        raise ValueError('Set a price before offering this product.')
    if product['availability'] == 'preorder' and not product['lead_time']:
        raise ValueError('Add an estimated delivery window for preorders.')
    return product


class Store:
    def __init__(self, directory):
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.db_path = self.directory / 'shop.sqlite3'
        with self.connect() as db:
            db.executescript('''
                CREATE TABLE IF NOT EXISTS products(id TEXT PRIMARY KEY, sku TEXT UNIQUE NOT NULL,
                    data TEXT NOT NULL, revision INTEGER NOT NULL DEFAULT 1, updated_at INTEGER NOT NULL);
                CREATE TABLE IF NOT EXISTS admins(username TEXT PRIMARY KEY, password TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS sessions(token TEXT PRIMARY KEY, csrf TEXT NOT NULL,
                    username TEXT NOT NULL, expires INTEGER NOT NULL);
                CREATE TABLE IF NOT EXISTS login_attempts(address TEXT NOT NULL, created INTEGER NOT NULL);
                CREATE TABLE IF NOT EXISTS customers(email TEXT PRIMARY KEY, password TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS customer_profiles(email TEXT PRIMARY KEY, data TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS customer_sessions(token TEXT PRIMARY KEY, csrf TEXT NOT NULL,
                    email TEXT NOT NULL, expires INTEGER NOT NULL);
                CREATE TABLE IF NOT EXISTS questions(id TEXT PRIMARY KEY, product_id TEXT NOT NULL,
                    product_name TEXT NOT NULL, author TEXT NOT NULL, message TEXT NOT NULL,
                    request_id TEXT NOT NULL, created INTEGER NOT NULL, UNIQUE(author, request_id));
                CREATE TABLE IF NOT EXISTS question_replies(id TEXT PRIMARY KEY, question_id TEXT NOT NULL,
                    message TEXT NOT NULL, created INTEGER NOT NULL, is_read INTEGER NOT NULL DEFAULT 0);
                CREATE INDEX IF NOT EXISTS replies_question ON question_replies(question_id);
                CREATE TABLE IF NOT EXISTS admin_question_reads(question_id TEXT PRIMARY KEY, seen_at INTEGER NOT NULL);
                CREATE TABLE IF NOT EXISTS admin_service_reads(request_kind TEXT NOT NULL, request_id TEXT NOT NULL,
                    seen_version INTEGER NOT NULL, PRIMARY KEY(request_kind,request_id));
                CREATE TABLE IF NOT EXISTS custom_lab_requests(id TEXT PRIMARY KEY, email TEXT NOT NULL,
                    customer_email TEXT, request_type TEXT NOT NULL, product_name TEXT NOT NULL,
                    vehicle_type TEXT NOT NULL, vehicle_model TEXT NOT NULL, vehicle_year TEXT NOT NULL DEFAULT '', budget TEXT NOT NULL,
                    description TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'new', created INTEGER NOT NULL);
                CREATE INDEX IF NOT EXISTS custom_lab_customer ON custom_lab_requests(customer_email,created);
                CREATE TABLE IF NOT EXISTS service_replies(id TEXT PRIMARY KEY, request_kind TEXT NOT NULL,
                    request_id TEXT NOT NULL, message TEXT NOT NULL, created INTEGER NOT NULL,
                    sender TEXT NOT NULL DEFAULT 'admin', is_read INTEGER NOT NULL DEFAULT 0);
                CREATE INDEX IF NOT EXISTS service_replies_request ON service_replies(request_kind,request_id,created);
                CREATE TABLE IF NOT EXISTS orders(id TEXT PRIMARY KEY, payment_session_id TEXT UNIQUE,
                    customer_email TEXT NOT NULL, items TEXT NOT NULL, amount_cents INTEGER NOT NULL,
                    currency TEXT NOT NULL, status TEXT NOT NULL, created INTEGER NOT NULL, updated INTEGER NOT NULL);
                CREATE TABLE IF NOT EXISTS checkout_requests(request_id TEXT PRIMARY KEY, customer_email TEXT NOT NULL,
                    order_id TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS email_deliveries(event_key TEXT PRIMARY KEY, status TEXT NOT NULL,
                    updated INTEGER NOT NULL, error TEXT NOT NULL DEFAULT '');
            ''')
            if not db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='categories'").fetchone():
                db.execute('CREATE TABLE categories(id TEXT PRIMARY KEY, name TEXT NOT NULL COLLATE NOCASE UNIQUE)')
                db.executemany('INSERT INTO categories VALUES (?,?)', [('mounts', 'Mounts & adapters'), ('electronics', 'Power & electronics'), ('storage', 'Storage & utility'), ('care', 'Detailing & care')])
            if 'sender' not in {row['name'] for row in db.execute('PRAGMA table_info(question_replies)')}:
                db.execute("ALTER TABLE question_replies ADD COLUMN sender TEXT NOT NULL DEFAULT 'admin'")
            db.execute("DELETE FROM service_replies WHERE request_kind='installation'")
            db.execute("DELETE FROM admin_service_reads WHERE request_kind='installation'")
            db.execute('DROP TABLE IF EXISTS installation_requests')
            if 'vehicle_year' not in {row['name'] for row in db.execute('PRAGMA table_info(custom_lab_requests)')}:
                db.execute("ALTER TABLE custom_lab_requests ADD COLUMN vehicle_year TEXT NOT NULL DEFAULT ''")
            order_columns={row['name'] for row in db.execute('PRAGMA table_info(orders)')}
            if 'public_id' not in order_columns: db.execute("ALTER TABLE orders ADD COLUMN public_id TEXT")
            if 'shipping' not in order_columns: db.execute("ALTER TABLE orders ADD COLUMN shipping TEXT NOT NULL DEFAULT '{}'")
            if 'fulfillment_status' not in order_columns: db.execute("ALTER TABLE orders ADD COLUMN fulfillment_status TEXT NOT NULL DEFAULT 'ordered'")
            if 'status_updated' not in order_columns: db.execute("ALTER TABLE orders ADD COLUMN status_updated INTEGER NOT NULL DEFAULT 0")
            if 'status_read' not in order_columns: db.execute("ALTER TABLE orders ADD COLUMN status_read INTEGER NOT NULL DEFAULT 1")
            if 'admin_read' not in order_columns: db.execute("ALTER TABLE orders ADD COLUMN admin_read INTEGER NOT NULL DEFAULT 0")
            if 'policy_version' not in order_columns: db.execute("ALTER TABLE orders ADD COLUMN policy_version TEXT NOT NULL DEFAULT ''")
            if 'policy_accepted_at' not in order_columns: db.execute("ALTER TABLE orders ADD COLUMN policy_accepted_at INTEGER")
            for old_order in db.execute('SELECT id FROM orders WHERE public_id IS NULL OR public_id=""'):
                db.execute('UPDATE orders SET public_id=? WHERE id=?',('WOBLI-'+old_order['id'].upper(),old_order['id']))
            db.execute('CREATE UNIQUE INDEX IF NOT EXISTS orders_public_id ON orders(public_id)')
            if not db.execute('SELECT 1 FROM admins').fetchone():
                password = secrets.token_urlsafe(20)
                db.execute('INSERT INTO admins VALUES (?, ?)', ('admin', password_hash(password)))
                credential_file = self.directory / 'admin-access.txt'
                with os.fdopen(os.open(credential_file, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), 'w') as handle:
                    handle.write('Wobli — local administrator\n\nUsername: admin\nPassword: ' + password + '\n\nOpen Admin access in the website footer. Change this generated password in the admin Security panel.\nKeep this file private. It is never served by the website.\n')
        os.chmod(self.db_path, 0o600)

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.db_path, timeout=10)
        db.row_factory = sqlite3.Row
        try:
            with db:
                yield db
        finally:
            db.close()

    @staticmethod
    def decode(row):
        return dict(json.loads(row['data']), id=row['id'], revision=row['revision'])

    def products(self, admin=False):
        with self.connect() as db:
            products = [self.decode(row) for row in db.execute('SELECT * FROM products ORDER BY updated_at DESC, id')]
        if admin:
            return products
        public_products = []
        for product in products:
            if product['status'] == 'active':
                product.pop('admin_comment', None)
                public_products.append(product)
        return public_products

    def next_sku(self):
        with self.connect() as db:
            rows = db.execute("SELECT sku FROM products WHERE sku LIKE 'WOBLI-%'")
            numbers = [int(match.group(1)) for row in rows if (match := re.fullmatch(r'WOBLI-(\d+)', row['sku'], re.IGNORECASE))]
        return f'WOBLI-{max(numbers, default=0) + 1:03d}'

    def categories(self):
        with self.connect() as db:
            return [dict(row) for row in db.execute('SELECT id,name FROM categories ORDER BY name COLLATE NOCASE')]

    def save_category(self, data, category_id=None):
        name = data.get('name')
        if not isinstance(name, str) or not 1 <= len(name.strip()) <= 80 or any(ord(c) < 32 for c in name):
            raise ValueError('Enter a category name of 1–80 characters.')
        with self.connect() as db:
            try:
                if category_id:
                    if db.execute('UPDATE categories SET name=? WHERE id=?', (name.strip(), category_id)).rowcount == 0:
                        raise LookupError('Category not found.')
                else:
                    category_id = uuid.uuid4().hex
                    db.execute('INSERT INTO categories VALUES (?,?)', (category_id, name.strip()))
            except sqlite3.IntegrityError as exc:
                raise ValueError('A category with this name already exists.') from exc
        return {'id': category_id, 'name': name.strip()}

    def delete_category(self, category_id):
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            if any(json.loads(row['data'])['category'] == category_id for row in db.execute('SELECT data FROM products')):
                raise ValueError('Move all products out of this category before deleting it, including drafts and archived products.')
            if db.execute('DELETE FROM categories WHERE id=?', (category_id,)).rowcount == 0:
                raise LookupError('Category not found.')

    def save(self, data, product_id=None):
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            product = validate_product(data, {row['id'] for row in db.execute('SELECT id FROM categories')})
            try:
                if product_id:
                    old = db.execute('SELECT * FROM products WHERE id=?', (product_id,)).fetchone()
                    if not old:
                        raise LookupError('Product not found.')
                    if type(data.get('revision')) is not int or data['revision'] != old['revision']:
                        raise RuntimeError('This product was changed elsewhere. Reload it before saving.')
                    db.execute('UPDATE products SET sku=?,data=?,revision=revision+1,updated_at=? WHERE id=?',
                               (product['sku'], json.dumps(product), time.time_ns(), product_id))
                else:
                    product_id = uuid.uuid4().hex
                    db.execute('INSERT INTO products VALUES (?,?,?,1,?)', (product_id, product['sku'], json.dumps(product), time.time_ns()))
            except sqlite3.IntegrityError as exc:
                raise ValueError('That SKU is already used by another product.') from exc
            return self.decode(db.execute('SELECT * FROM products WHERE id=?', (product_id,)).fetchone())

    def seed(self):
        """Keep a new shop empty; products are created through the admin area."""

    def login(self, username, password, address):
        now = int(time.time())
        with self.connect() as db:
            db.execute('DELETE FROM login_attempts WHERE created < ?', (now - 900,))
            count = db.execute('SELECT COUNT(*) FROM login_attempts WHERE address=?', (address,)).fetchone()[0]
            if count >= 10:
                raise TimeoutError('Too many sign-in attempts. Try again in 15 minutes.')
            db.execute('INSERT INTO login_attempts VALUES (?,?)', (address, now))
            row = db.execute('SELECT * FROM admins WHERE username=?', (username,)).fetchone()
        # A dummy hash prevents a cheap timing distinction for unknown usernames.
        stored = row['password'] if row else password_hash('invalid-admin-password', '00' * 16)
        if not password_matches(password, stored) or not row:
            raise PermissionError('Incorrect username or password.')
        token, csrf = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
        with self.connect() as db:
            db.execute('DELETE FROM login_attempts WHERE address=?', (address,))
            db.execute('DELETE FROM sessions WHERE expires < ?', (now,))
            db.execute('INSERT INTO sessions VALUES (?,?,?,?)',
                       (hashlib.sha256(token.encode()).hexdigest(), csrf, username, now + 28800))
        return token, {'username': username, 'csrf': csrf}

    def session(self, token):
        with self.connect() as db:
            row = db.execute('SELECT username,csrf FROM sessions WHERE token=? AND expires>?',
                             (hashlib.sha256(token.encode()).hexdigest(), int(time.time()))).fetchone()
        return dict(row) if row else None

    def logout(self, token):
        with self.connect() as db:
            db.execute('DELETE FROM sessions WHERE token=?', (hashlib.sha256(token.encode()).hexdigest(),))

    def change_password(self, username, current, new):
        if not isinstance(new, str) or not 12 <= len(new) <= 128:
            raise ValueError('Use a new password of 12–128 characters.')
        if not isinstance(current, str) or len(current) > 128:
            raise ValueError('Invalid current password.')
        with self.connect() as db:
            row = db.execute('SELECT password FROM admins WHERE username=?', (username,)).fetchone()
            if not password_matches(current, row['password']):
                raise PermissionError('Current password is incorrect.')
            db.execute('UPDATE admins SET password=? WHERE username=?', (password_hash(new), username))
            db.execute('DELETE FROM sessions WHERE username=?', (username,))

    def quote(self, items):
        if not isinstance(items, list) or len(items) > 100:
            raise ValueError('Cart must contain at most 100 product lines.')
        catalogue = {p['id']: p for p in self.products()}
        lines, seen, total = [], set(), 0
        for item in items:
            if not isinstance(item, dict) or not isinstance(item.get('id'), str) or item['id'] in seen:
                raise ValueError('Invalid or duplicate cart item.')
            seen.add(item['id'])
            quantity = item.get('quantity')
            if type(quantity) is not int or not 1 <= quantity <= 99:
                raise ValueError('Quantity must be between 1 and 99.')
            p = catalogue.get(item['id'])
            issue = None
            if not p:
                issue = 'This product is no longer available.'
            elif p['availability'] == 'concept' or p['price_cents'] is None:
                issue = 'This product is not open for orders.'
            elif p['availability'] == 'stock' and quantity > p['stock']:
                issue = f'Only {p["stock"]} available. Please adjust the quantity.'
            amount = 0 if issue else p['price_cents'] * quantity
            total += amount
            lines.append(dict(id=item['id'], quantity=quantity, product=p, issue=issue, line_total_cents=amount))
        return dict(lines=lines, subtotal_cents=total, currency='CHF', checkout_enabled=False)

    ORDER_ADDRESS_LIMITS={'name':100,'surname':100,'phone':40,'address':200,'address_extra':200,'postal_code':24,'city':100,'country':100}
    ORDER_STATUSES={'ordered','in_preparation','ready_to_send','sent','cancelled'}

    def validate_order_address(self, data):
        if not isinstance(data,dict): raise ValueError('Enter your delivery details.')
        result={}
        for key,limit in self.ORDER_ADDRESS_LIMITS.items():
            value=data.get(key,'')
            if not isinstance(value,str) or len(value)>limit or any(ord(c)<32 for c in value): raise ValueError(f'{key}: enter valid text up to {limit} characters.')
            result[key]=value.strip()
        for key in ('name','surname','phone','address','postal_code','city','country'):
            if not result[key]: raise ValueError('Complete all required delivery fields.')
        return result

    def create_order(self, email, quote, request_id, shipping=None, policy_version=''):
        order_id=uuid.uuid4().hex;now=int(time.time())
        public_id='WOBLI-'+order_id.upper();shipping=self.validate_order_address(shipping or {})
        if not isinstance(policy_version,str) or not policy_version.strip(): raise ValueError('Accept the Terms and Conditions and Return and Refund Policy to continue.')
        policy_version=policy_version.strip()
        items=[{'id':line['id'],'name':line['product']['name'],'quantity':line['quantity'],'unit_amount':line['product']['price_cents']} for line in quote['lines']]
        with self.connect() as db:
            old=db.execute('SELECT customer_email,order_id FROM checkout_requests WHERE request_id=?',(request_id,)).fetchone()
            if old:
                if old['customer_email']!=email: raise ValueError('This checkout request was already used.')
                return old['order_id']
            db.execute('INSERT INTO orders(id,payment_session_id,customer_email,items,amount_cents,currency,status,created,updated,public_id,shipping,fulfillment_status,status_updated,status_read,policy_version,policy_accepted_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',(order_id,None,email,json.dumps(items),quote['subtotal_cents'],'chf','creating',now,now,public_id,json.dumps(shipping),'ordered',now,1,policy_version,now))
            db.execute('INSERT INTO checkout_requests VALUES (?,?,?)',(request_id,email,order_id))
        return order_id

    def attach_payment_session(self, order_id, session_id):
        with self.connect() as db:
            row=db.execute('SELECT payment_session_id FROM orders WHERE id=?',(order_id,)).fetchone()
            if not row: raise LookupError('Order not found.')
            if row['payment_session_id'] and row['payment_session_id']!=session_id: raise RuntimeError('Checkout request conflict.')
            db.execute("UPDATE orders SET payment_session_id=?,status=CASE WHEN status='creating' THEN 'open' ELSE status END,updated=? WHERE id=?",(session_id,int(time.time()),order_id))

    def mark_order_paid(self, session_id, payment_status):
        status='paid' if payment_status in {'paid','no_payment_required'} else 'payment_failed'
        with self.connect() as db:
            db.execute('UPDATE orders SET status=?,updated=? WHERE payment_session_id=?',(status,int(time.time()),session_id))

    def customer_orders(self, email):
        """Return payment records belonging only to the signed-in customer."""
        with self.connect() as db:
            rows=db.execute("SELECT id,public_id,items,shipping,amount_cents,currency,status,fulfillment_status,status_updated,status_read,created,updated FROM orders WHERE customer_email=? AND status='paid' ORDER BY created DESC,id DESC",(email,)).fetchall()
        orders=[]
        for row in rows:
            order=dict(row)
            try: order['items']=json.loads(order['items'])
            except (TypeError,json.JSONDecodeError): order['items']=[]
            try: order['shipping']=json.loads(order['shipping'])
            except (TypeError,json.JSONDecodeError): order['shipping']={}
            orders.append(order)
        return orders

    def cancel_customer_order(self,email,order_id):
        """Cancel the customer's paid, unshipped order and return it for email delivery."""
        now=int(time.time())
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            row=db.execute("SELECT id,public_id,customer_email,items,shipping,amount_cents,currency,status,fulfillment_status,created FROM orders WHERE id=? AND customer_email=? AND status='paid'",(order_id,email)).fetchone()
            if not row: raise LookupError('Order not found.')
            if row['fulfillment_status']=='sent': raise ValueError('This order has already been sent and can no longer be cancelled online. Please contact the shop team.')
            changed=row['fulfillment_status']!='cancelled'
            if changed:
                db.execute("UPDATE orders SET fulfillment_status='cancelled',status_updated=?,status_read=1,admin_read=0,updated=? WHERE id=?",(now,now,order_id))
        order=dict(row);order['fulfillment_status']='cancelled'
        for key,fallback in [('items',[]),('shipping',{})]:
            try:order[key]=json.loads(order[key])
            except (TypeError,json.JSONDecodeError):order[key]=fallback
        return order,changed

    def read_order_updates(self,email):
        with self.connect() as db: db.execute('UPDATE orders SET status_read=1 WHERE customer_email=?',(email,))

    def admin_orders(self):
        with self.connect() as db:
            rows=db.execute("SELECT id,public_id,customer_email,items,shipping,amount_cents,currency,status,fulfillment_status,status_updated,admin_read,policy_version,policy_accepted_at,created,updated FROM orders WHERE status='paid' ORDER BY created DESC,id DESC").fetchall()
        result=[]
        for row in rows:
            order=dict(row)
            for key,fallback in [('items',[]),('shipping',{})]:
                try: order[key]=json.loads(order[key])
                except (TypeError,json.JSONDecodeError): order[key]=fallback
            result.append(order)
        return result

    def read_order_admin(self,order_id):
        with self.connect() as db:
            if db.execute('UPDATE orders SET admin_read=1 WHERE id=?',(order_id,)).rowcount==0:raise LookupError('Order not found.')

    def update_order_status(self,order_id,data):
        status=data.get('status')
        if status not in self.ORDER_STATUSES: raise ValueError('Choose a valid order status.')
        now=int(time.time())
        with self.connect() as db:
            row=db.execute('SELECT fulfillment_status FROM orders WHERE id=?',(order_id,)).fetchone()
            if not row: raise LookupError('Order not found.')
            changed=row['fulfillment_status']!=status
            if changed:
                db.execute('UPDATE orders SET fulfillment_status=?,status_updated=?,status_read=0,updated=? WHERE id=?',(status,now,now,order_id))
        order=next((item for item in self.admin_orders() if item['id']==order_id),None)
        return order,changed

    def owns_payment_session(self, email, session_id):
        with self.connect() as db:
            row=db.execute('SELECT id FROM orders WHERE customer_email=? AND payment_session_id=?',(email,session_id)).fetchone()
        return row['id'] if row else None

    def order_for_payment_session(self,session_id):
        with self.connect() as db:
            row=db.execute("SELECT id,public_id,customer_email,items,shipping,amount_cents,currency,status,fulfillment_status,created FROM orders WHERE payment_session_id=? AND status='paid'",(session_id,)).fetchone()
        if not row:return None
        order=dict(row)
        try:order['items']=json.loads(order['items'])
        except (TypeError,json.JSONDecodeError):order['items']=[]
        try:order['shipping']=json.loads(order['shipping'])
        except (TypeError,json.JSONDecodeError):order['shipping']={}
        return order

    def question_for_email(self,question_id):
        with self.connect() as db: row=db.execute('SELECT id,author,product_name,message,created FROM questions WHERE id=?',(question_id,)).fetchone()
        return dict(row) if row else None

    def claim_email(self,event_key):
        now=int(time.time())
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            row=db.execute('SELECT status,updated FROM email_deliveries WHERE event_key=?',(event_key,)).fetchone()
            if row and (row['status']=='sent' or (row['status']=='sending' and row['updated']>now-300)):return False
            db.execute("INSERT INTO email_deliveries(event_key,status,updated,error) VALUES (?,'sending',?,'') ON CONFLICT(event_key) DO UPDATE SET status='sending',updated=excluded.updated,error=''",(event_key,now))
        return True

    def finish_email(self,event_key,sent,error=''):
        with self.connect() as db: db.execute('UPDATE email_deliveries SET status=?,updated=?,error=? WHERE event_key=?',('sent' if sent else 'failed',int(time.time()),error[:100],event_key))

    def account_attempt(self, address):
        now = int(time.time())
        with self.connect() as db:
            db.execute('DELETE FROM login_attempts WHERE created < ?', (now - 900,))
            if db.execute('SELECT COUNT(*) FROM login_attempts WHERE address=?', (address,)).fetchone()[0] >= 10:
                raise TimeoutError('Too many attempts. Try again in 15 minutes.')
            db.execute('INSERT INTO login_attempts VALUES (?,?)', (address, now))

    def customer_auth(self, email, password, address, register=False, confirmation=None):
        self.account_attempt('account:' + address)
        if not isinstance(email, str) or len(email) > 254 or not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+', email.strip()):
            raise ValueError('Enter a valid email address.')
        email = email.strip().lower()
        if not isinstance(password, str) or not 1 <= len(password) <= 128:
            raise ValueError('Enter a password of at most 128 characters.')
        if register:
            if len(password) < 8 or confirmation != password:
                raise ValueError('Use at least 8 characters and matching passwords.')
            hashed = password_hash(password)
            with self.connect() as db:
                try:
                    db.execute('INSERT INTO customers VALUES (?,?)', (email, hashed))
                except sqlite3.IntegrityError:
                    raise ValueError('Unable to create this account. Try signing in instead.')
        else:
            with self.connect() as db:
                row = db.execute('SELECT password FROM customers WHERE email=?', (email,)).fetchone()
            stored = row['password'] if row else password_hash('invalid-customer', '00' * 16)
            if not password_matches(password, stored) or not row:
                raise PermissionError('Incorrect email or password.')
        token, csrf = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
        with self.connect() as db:
            db.execute('DELETE FROM customer_sessions WHERE expires < ?', (int(time.time()),))
            db.execute('INSERT INTO customer_sessions VALUES (?,?,?,?)', (hashlib.sha256(token.encode()).hexdigest(), csrf, email, int(time.time()) + 28800))
        return token, {'username': email, 'csrf': csrf, 'role': 'customer', 'name': self.customer_name(email)}

    def customer_name(self, email):
        with self.connect() as db:
            row = db.execute('SELECT data FROM customer_profiles WHERE email=?', (email,)).fetchone()
        return json.loads(row['data']).get('name', '').strip() if row else ''

    def customer_session(self, token):
        with self.connect() as db:
            row = db.execute('SELECT email,csrf FROM customer_sessions WHERE token=? AND expires>?', (hashlib.sha256(token.encode()).hexdigest(), int(time.time()))).fetchone()
        return {'username': row['email'], 'csrf': row['csrf'], 'role': 'customer', 'name': self.customer_name(row['email'])} if row else None

    def customer_logout(self, token):
        with self.connect() as db:
            db.execute('DELETE FROM customer_sessions WHERE token=?', (hashlib.sha256(token.encode()).hexdigest(),))

    def save_question(self, author, data):
        message, product_id, request_id = data.get('message'), data.get('product_id'), data.get('request_id')
        if not isinstance(message, str) or not 1 <= len(message.strip()) <= 3000:
            raise ValueError('Write a question of 1–3000 characters.')
        if not isinstance(product_id, str) or not isinstance(request_id, str) or not re.fullmatch(r'[a-f0-9-]{32,36}', request_id):
            raise ValueError('Invalid question request.')
        with self.connect() as db:
            old = db.execute('SELECT id FROM questions WHERE author=? AND request_id=?', (author, request_id)).fetchone()
            if old: return old['id']
            row = db.execute('SELECT * FROM products WHERE id=?', (product_id,)).fetchone()
            if not row or self.decode(row)['status'] != 'active':
                raise LookupError('This product is no longer available.')
            if db.execute('SELECT COUNT(*) FROM questions WHERE author=? AND created>?', (author, int(time.time()) - 3600)).fetchone()[0] >= 10:
                raise TimeoutError('You can send up to 10 questions per hour. Please try again later.')
            question_id = uuid.uuid4().hex
            db.execute('INSERT INTO questions VALUES (?,?,?,?,?,?,?)', (question_id, product_id, self.decode(row)['name'], author, message.strip(), request_id, int(time.time())))
        return question_id

    def questions(self):
        with self.connect() as db:
            questions = [dict(row) for row in db.execute('SELECT id,product_id,product_name,author,message,created FROM questions ORDER BY created DESC LIMIT 500')]
            for question in questions:
                question['replies'] = self.question_replies(db, question['id'])
                latest=1+len(question['replies'])
                seen=db.execute('SELECT seen_at FROM admin_question_reads WHERE question_id=?',(question['id'],)).fetchone()
                question['admin_read']=bool(seen and seen['seen_at']>=latest)
            return questions

    def read_question_admin(self, question_id):
        with self.connect() as db:
            question=db.execute('SELECT created FROM questions WHERE id=?',(question_id,)).fetchone()
            if not question: raise LookupError('Question not found.')
            latest=1+db.execute('SELECT COUNT(*) FROM question_replies WHERE question_id=?',(question_id,)).fetchone()[0]
            db.execute('INSERT INTO admin_question_reads VALUES (?,?) ON CONFLICT(question_id) DO UPDATE SET seen_at=excluded.seen_at',(question_id,latest))

    def question_replies(self, db, question_id):
        return [dict(row) for row in db.execute('SELECT id,message,created,is_read,sender FROM question_replies WHERE question_id=? ORDER BY created,rowid', (question_id,))]

    def reply_question(self, question_id, data, customer_email=None):
        message, request_id = data.get('message'), data.get('request_id')
        if not isinstance(message, str) or not 1 <= len(message.strip()) <= 3000:
            raise ValueError('Write a reply of 1–3000 characters.')
        if not isinstance(request_id, str) or not re.fullmatch(r'[a-f0-9]{32}', request_id):
            raise ValueError('Invalid reply request.')
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            question = db.execute('SELECT author FROM questions WHERE id=?', (question_id,)).fetchone()
            if not question or (customer_email is not None and question['author'] != customer_email):
                raise LookupError('Question not found.')
            sender = 'customer' if customer_email is not None else 'admin'
            old = db.execute('SELECT question_id,message,sender FROM question_replies WHERE id=?', (request_id,)).fetchone()
            if old:
                if old['question_id'] != question_id or old['message'] != message.strip() or old['sender'] != sender:
                    raise ValueError('This reply request was already used.')
                return request_id
            if customer_email is not None and db.execute("SELECT COUNT(*) FROM question_replies r JOIN questions q ON q.id=r.question_id WHERE q.author=? AND r.sender='customer' AND r.created>?", (customer_email, int(time.time()) - 3600)).fetchone()[0] >= 30:
                raise TimeoutError('You can send up to 30 replies per hour. Please try again later.')
            db.execute('INSERT INTO question_replies(id,question_id,message,created,sender,is_read) VALUES (?,?,?,?,?,?)', (request_id, question_id, message.strip(), int(time.time()), sender, int(sender == 'customer')))
        return request_id

    def read_replies(self, email, data):
        ids = data.get('ids')
        if not isinstance(ids, list) or len(ids) > 500 or any(not isinstance(value, str) for value in ids):
            raise ValueError('Invalid replies.')
        with self.connect() as db:
            for reply_id in ids:
                db.execute('UPDATE question_replies SET is_read=1 WHERE id=? AND question_id IN (SELECT id FROM questions WHERE author=?)', (reply_id, email))
                db.execute("UPDATE service_replies SET is_read=1 WHERE id=? AND request_kind='custom_lab' AND request_id IN (SELECT id FROM custom_lab_requests WHERE customer_email=?)", (reply_id,email))

    def notification_counts(self, account):
        with self.connect() as db:
            if account['role'] == 'customer':
                messages = db.execute("SELECT COUNT(*) FROM question_replies r JOIN questions q ON q.id=r.question_id WHERE q.author=? AND r.sender='admin' AND r.is_read=0", (account['username'],)).fetchone()[0]
                custom_lab = db.execute("SELECT COUNT(*) FROM service_replies r JOIN custom_lab_requests c ON c.id=r.request_id WHERE r.request_kind='custom_lab' AND c.customer_email=? AND r.sender='admin' AND r.is_read=0",(account['username'],)).fetchone()[0]
                orders=db.execute("SELECT COUNT(*) FROM orders WHERE customer_email=? AND status_read=0",(account['username'],)).fetchone()[0]
                return {'messages':messages,'custom_lab':custom_lab,'orders':orders,'total':messages+custom_lab+orders}
            messages = 0
            for question in db.execute('SELECT id,created FROM questions'):
                latest = db.execute('SELECT sender FROM question_replies WHERE question_id=? ORDER BY created DESC,rowid DESC LIMIT 1', (question['id'],)).fetchone()
                latest_time=1+db.execute('SELECT COUNT(*) value FROM question_replies WHERE question_id=?',(question['id'],)).fetchone()['value']
                seen=db.execute('SELECT seen_at FROM admin_question_reads WHERE question_id=?',(question['id'],)).fetchone()
                if (latest is None or latest['sender']=='customer') and not (seen and seen['seen_at']>=latest_time): messages += 1
            custom_lab = sum(not request['admin_read'] for request in self.custom_lab_requests())
            orders=db.execute("SELECT COUNT(*) FROM orders WHERE status='paid' AND admin_read=0").fetchone()[0]
            return {'messages': messages, 'custom_lab': custom_lab,'orders':orders,
                    'total': messages + custom_lab + orders}

    def delete_question(self, question_id):
        with self.connect() as db:
            if db.execute('DELETE FROM questions WHERE id=?', (question_id,)).rowcount == 0:
                raise LookupError('Question not found. It may already have been deleted.')
            db.execute('DELETE FROM question_replies WHERE question_id=?', (question_id,))
            db.execute('DELETE FROM admin_question_reads WHERE question_id=?', (question_id,))

    def save_custom_lab(self, data, customer_email, address):
        self.account_attempt('custom-lab:' + address)
        email = customer_email or data.get('email')
        if not isinstance(email, str) or len(email) > 254 or not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+', email.strip()):
            raise ValueError('Enter a valid email address.')
        request_type = data.get('request_type')
        if request_type not in {'new_product', 'custom_product'}:
            raise ValueError('Choose a request type.')
        def text(key, limit, required=False):
            value = data.get(key, '')
            if not isinstance(value, str) or len(value) > limit or (required and not value.strip()):
                raise ValueError(f'Enter {key.replace("_", " ")} up to {limit} characters.')
            return value.strip()
        product_name = text('product_name', 140, request_type == 'new_product')
        description = text('description', 3000, True)
        if request_type == 'custom_product':
            vehicle_type = data.get('vehicle_type')
            if vehicle_type not in VEHICLES: raise ValueError('Choose a vehicle type.')
            vehicle_model, vehicle_year, budget = text('vehicle_model', 140, True), text('vehicle_year', 20, True), text('budget', 100, True)
        else:
            vehicle_type = vehicle_model = vehicle_year = budget = ''
        request_id = uuid.uuid4().hex
        with self.connect() as db:
            db.execute('INSERT INTO custom_lab_requests(id,email,customer_email,request_type,product_name,vehicle_type,vehicle_model,vehicle_year,budget,description,status,created) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)',
                       (request_id,email.strip().lower(),customer_email,request_type,product_name,vehicle_type,vehicle_model,vehicle_year,budget,description,'new',int(time.time())))
        return request_id

    def custom_lab_requests(self, customer_email=None):
        with self.connect() as db:
            rows = db.execute('SELECT * FROM custom_lab_requests ORDER BY created DESC,id DESC') if customer_email is None else db.execute('SELECT * FROM custom_lab_requests WHERE customer_email=? ORDER BY created DESC,id DESC',(customer_email,))
            requests = [dict(row) for row in rows]
            for request in requests:
                request['replies'] = self.service_replies(db, 'custom_lab', request['id'])
                request['admin_read'] = self.service_admin_read(db,'custom_lab',request)
            return requests

    def update_custom_lab(self, request_id, data):
        status=data.get('status')
        if status not in {'new','reviewing','contacted','accepted','completed','declined'}: raise ValueError('Invalid Custom Lab status.')
        with self.connect() as db:
            if db.execute('UPDATE custom_lab_requests SET status=? WHERE id=?',(status,request_id)).rowcount==0: raise LookupError('Custom Lab request not found.')

    def delete_custom_lab(self, request_id):
        with self.connect() as db:
            if db.execute('DELETE FROM custom_lab_requests WHERE id=?',(request_id,)).rowcount==0: raise LookupError('Custom Lab request not found.')
            db.execute("DELETE FROM service_replies WHERE request_kind='custom_lab' AND request_id=?",(request_id,))
            db.execute("DELETE FROM admin_service_reads WHERE request_kind='custom_lab' AND request_id=?",(request_id,))

    def service_replies(self, db, kind, request_id):
        return [dict(row) for row in db.execute('SELECT id,message,created,sender,is_read FROM service_replies WHERE request_kind=? AND request_id=? ORDER BY created,rowid',(kind,request_id))]

    def service_admin_read(self, db, kind, request):
        version=1+sum(reply['sender']=='customer' for reply in request['replies'])
        seen=db.execute('SELECT seen_version FROM admin_service_reads WHERE request_kind=? AND request_id=?',(kind,request['id'])).fetchone()
        return bool(seen and seen['seen_version']>=version)

    def read_service_admin(self, kind, request_id):
        if kind != 'custom_lab': raise ValueError('Invalid request type.')
        table='custom_lab_requests'
        with self.connect() as db:
            if not db.execute(f'SELECT 1 FROM {table} WHERE id=?',(request_id,)).fetchone(): raise LookupError('Request not found.')
            version=1+db.execute("SELECT COUNT(*) FROM service_replies WHERE request_kind=? AND request_id=? AND sender='customer'",(kind,request_id)).fetchone()[0]
            db.execute('INSERT INTO admin_service_reads VALUES (?,?,?) ON CONFLICT(request_kind,request_id) DO UPDATE SET seen_version=excluded.seen_version',(kind,request_id,version))

    def reply_service_request(self, kind, request_id, data, customer_email=None):
        if kind != 'custom_lab': raise ValueError('Invalid request type.')
        message, reply_id = data.get('message'), data.get('request_id')
        if not isinstance(message,str) or not 1 <= len(message.strip()) <= 3000: raise ValueError('Write a reply of 1–3000 characters.')
        if not isinstance(reply_id,str) or not re.fullmatch(r'[a-f0-9]{32}',reply_id): raise ValueError('Invalid reply request.')
        table = 'custom_lab_requests'
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            request=db.execute(f'SELECT customer_email FROM {table} WHERE id=?',(request_id,)).fetchone()
            if not request or (customer_email is not None and request['customer_email']!=customer_email): raise LookupError('Request not found.')
            sender='customer' if customer_email is not None else 'admin'
            old=db.execute('SELECT request_kind,request_id,message,sender FROM service_replies WHERE id=?',(reply_id,)).fetchone()
            if old:
                if old['request_kind']!=kind or old['request_id']!=request_id or old['message']!=message.strip() or old['sender']!=sender: raise ValueError('This reply request was already used.')
                return reply_id
            if customer_email is not None:
                count=db.execute(f"SELECT COUNT(*) FROM service_replies r JOIN {table} s ON s.id=r.request_id WHERE r.request_kind=? AND r.sender='customer' AND s.customer_email=? AND r.created>?",(kind,customer_email,int(time.time())-3600)).fetchone()[0]
                if count>=30: raise TimeoutError('You can send up to 30 replies per hour. Please try again later.')
            db.execute('INSERT INTO service_replies VALUES (?,?,?,?,?,?,?)',(reply_id,kind,request_id,message.strip(),int(time.time()),sender,int(sender=='customer')))
            if customer_email is None:
                db.execute("UPDATE custom_lab_requests SET status='contacted' WHERE id=? AND status='new'",(request_id,))
        return reply_id

    PROFILE_LIMITS = {'name': 100, 'surname': 100, 'phone': 40, 'address': 200,
                      'address_extra': 200, 'postal_code': 24, 'city': 100, 'country': 100}

    def customer_profile(self, email):
        with self.connect() as db:
            if not db.execute('SELECT 1 FROM customers WHERE email=?', (email,)).fetchone():
                raise PermissionError('Please sign in again.')
            row = db.execute('SELECT data FROM customer_profiles WHERE email=?', (email,)).fetchone()
            messages = [dict(message) for message in db.execute(
                'SELECT id,product_name,message,created FROM questions WHERE author=? ORDER BY created DESC, id DESC', (email,))]
            for message in messages:
                message['replies'] = self.question_replies(db, message['id'])
        return {'email': email, 'details': json.loads(row['data']) if row else {key: '' for key in self.PROFILE_LIMITS}, 'orders': self.customer_orders(email), 'messages': messages, 'custom_lab': self.custom_lab_requests(email)}

    def save_customer_profile(self, email, data):
        values = {}
        for key, limit in self.PROFILE_LIMITS.items():
            value = data.get(key, '')
            if not isinstance(value, str) or len(value) > limit or any(ord(c) < 32 for c in value):
                raise ValueError(f'{key}: enter text up to {limit} characters.')
            values[key] = value.strip()
        with self.connect() as db:
            if not db.execute('SELECT 1 FROM customers WHERE email=?', (email,)).fetchone():
                raise PermissionError('Please sign in again.')
            db.execute('INSERT INTO customer_profiles VALUES (?,?) ON CONFLICT(email) DO UPDATE SET data=excluded.data', (email, json.dumps(values)))
        return self.customer_profile(email)

    def change_customer_credentials(self, email, data, kind):
        self.account_attempt('settings:' + email)
        current = data.get('current')
        if not isinstance(current, str) or len(current) > 128:
            raise ValueError('Enter your current password.')
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute('SELECT password FROM customers WHERE email=?', (email,)).fetchone()
            if not row:
                raise PermissionError('Please sign in again.')
            if not password_matches(current, row['password']):
                raise ValueError('Current password is incorrect.')
            if kind == 'email':
                new_email = data.get('email')
                if not isinstance(new_email, str) or len(new_email) > 254 or not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+', new_email.strip()):
                    raise ValueError('Enter a valid email address.')
                new_email = new_email.strip().lower()
                if new_email == email:
                    raise ValueError('Enter a different email address.')
                if db.execute('SELECT 1 FROM customers WHERE email=?', (new_email,)).fetchone():
                    raise ValueError('That email is unavailable.')
                db.execute('UPDATE customers SET email=? WHERE email=?', (new_email, email))
                db.execute('UPDATE customer_profiles SET email=? WHERE email=?', (new_email, email))
                db.execute('UPDATE questions SET author=? WHERE author=?', (new_email, email))
                db.execute('UPDATE custom_lab_requests SET customer_email=?,email=? WHERE customer_email=?', (new_email, new_email, email))
                db.execute('UPDATE orders SET customer_email=? WHERE customer_email=?', (new_email, email))
                db.execute('UPDATE checkout_requests SET customer_email=? WHERE customer_email=?', (new_email, email))
            elif kind == 'password':
                new = data.get('password')
                if not isinstance(new, str) or not 8 <= len(new) <= 128 or data.get('confirmation') != new:
                    raise ValueError('Use 8–128 characters and matching passwords.')
                db.execute('UPDATE customers SET password=? WHERE email=?', (password_hash(new), email))
            else:
                raise ValueError('Invalid settings change.')
            db.execute('DELETE FROM customer_sessions WHERE email=?', (email,))

    def delete_customer(self, email):
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            if not db.execute('SELECT 1 FROM customers WHERE email=?',(email,)).fetchone():
                raise PermissionError('Please sign in again.')
            question_ids=[row['id'] for row in db.execute('SELECT id FROM questions WHERE author=?',(email,))]
            custom_ids=[row['id'] for row in db.execute('SELECT id FROM custom_lab_requests WHERE customer_email=?',(email,))]
            for question_id in question_ids:
                db.execute('DELETE FROM question_replies WHERE question_id=?',(question_id,))
                db.execute('DELETE FROM admin_question_reads WHERE question_id=?',(question_id,))
            for kind,ids in [('custom_lab',custom_ids)]:
                for request_id in ids:
                    db.execute('DELETE FROM service_replies WHERE request_kind=? AND request_id=?',(kind,request_id))
                    db.execute('DELETE FROM admin_service_reads WHERE request_kind=? AND request_id=?',(kind,request_id))
            db.execute('DELETE FROM questions WHERE author=?',(email,))
            db.execute('DELETE FROM custom_lab_requests WHERE customer_email=?',(email,))
            db.execute('DELETE FROM customer_profiles WHERE email=?',(email,))
            db.execute('DELETE FROM customer_sessions WHERE email=?',(email,))
            db.execute('DELETE FROM customers WHERE email=?',(email,))
