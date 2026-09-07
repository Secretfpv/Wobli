"""Local-only Wobli server. Run: python3 server/app.py"""
import argparse
from concurrent.futures import ThreadPoolExecutor
import os
import hashlib
from http import HTTPStatus
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import mimetypes
from pathlib import Path
import re
import secrets
import struct
from urllib.parse import urlsplit, unquote

from store import Store
from email_service import Mailer

ROOT = Path(__file__).resolve().parent.parent
PUBLIC = ROOT / 'webpage'
POLICY_VERSION = '2026-09-07'


class Handler(BaseHTTPRequestHandler):
    server_version = 'WobliLocal/1.0'

    def log_message(self, *args):
        # Never log credentials, request bodies, cookies or query strings.
        pass

    def headers_common(self):
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('X-Frame-Options', 'DENY')
        self.send_header('Referrer-Policy', 'no-referrer')
        self.send_header('Cache-Control', 'no-store')
        self.send_header('Content-Security-Policy', "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; connect-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'")

    def json_response(self, code, value, cookie=None):
        body = json.dumps(value).encode()
        self.send_response(code)
        self.headers_common()
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        if cookie:
            self.send_header('Set-Cookie', cookie)
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def token(self, name="wobli_admin"):
        try:
            cookies = SimpleCookie(self.headers.get('Cookie', ''))
            return cookies[name].value if name in cookies else ''
        except Exception:
            return ''

    def require_admin(self, write=False):
        session = self.server.store.session(self.token())
        if not session:
            raise PermissionError('Sign in as an administrator first.')
        if write and not secrets.compare_digest(self.headers.get('X-CSRF-Token', ''), session['csrf']):
            raise PermissionError('Security token expired. Sign in again.')
        return session

    def account(self, write=False):
        session = self.server.store.session(self.token())
        account = dict(session, role='admin') if session else self.server.store.customer_session(self.token('wobli_customer'))
        if write:
            if not account:
                raise PermissionError('Please log in to ask a question.')
            if not secrets.compare_digest(self.headers.get('X-CSRF-Token', ''), account['csrf']):
                raise PermissionError('Your session expired. Please log in again.')
        return account

    def body(self, limit=131072, raw=False):
        if self.headers.get('Transfer-Encoding'):
            raise ValueError('Chunked requests are not supported.')
        try:
            length = int(self.headers.get('Content-Length', '0'))
        except ValueError:
            raise ValueError('Invalid request size.')
        if length < 0 or length > limit:
            raise ValueError('Request is too large.')
        data = self.rfile.read(length)
        if raw:
            return data
        if self.headers.get_content_type() != 'application/json':
            raise ValueError('JSON is required.')
        try:
            value = json.loads(data)
        except (ValueError, UnicodeDecodeError):
            raise ValueError('Invalid JSON.')
        if not isinstance(value, dict):
            raise ValueError('A JSON object is required.')
        return value

    def validated_image(self, path):
        if not path:
            return
        if not isinstance(path, str) or not re.fullmatch(r'(?:assets/[A-Za-z0-9_.-]+\.(?:png|jpg|jpeg|webp)|uploads/[a-f0-9]{64}\.(?:png|jpg|webp))', path):
            raise ValueError('Use an uploaded image or a local image from assets.')
        file = PUBLIC / path if path.startswith('assets/') else self.server.store.directory / path
        if not file.is_file():
            raise ValueError('The selected image does not exist.')

    def dispatch(self):
        host = self.headers.get('Host', '')
        if host not in self.server.allowed_hosts:
            self.json_response(403, {'error': 'Invalid host.'})
            return
        path = urlsplit(self.path).path
        if self.command not in ('GET', 'HEAD'):
            if self.headers.get('Origin') not in self.server.allowed_origins:
                self.json_response(403, {'error': 'Cross-origin writes are not allowed.'})
                return
        store = self.server.store
        try:
            if self.command == 'GET' and path == '/api/account/session':
                return self.json_response(200, {'account': self.account()})
            if self.command == 'GET' and path == '/api/account/notifications':
                account = self.account()
                if not account: raise PermissionError('Please sign in to see notifications.')
                return self.json_response(200, store.notification_counts(account))
            if self.command == 'POST' and path in ('/api/account/login', '/api/account/register'):
                data = self.body()
                token, account = store.customer_auth(data.get('email'), data.get('password'), self.client_address[0], path.endswith('/register'), data.get('confirmation'))
                store.customer_logout(self.token('wobli_customer'))
                store.logout(self.token())
                return self.json_response(200, {'account': account}, f'wobli_customer={token}; HttpOnly; SameSite=Strict; Path=/; Max-Age=28800')
            if self.command == 'POST' and path == '/api/account/logout':
                self.account(write=True)
                store.customer_logout(self.token('wobli_customer')); store.logout(self.token())
                return self.json_response(200, {'ok': True}, 'wobli_customer=; HttpOnly; SameSite=Strict; Path=/; Max-Age=0')
            if self.command == 'DELETE' and path == '/api/account':
                account=self.account(write=True)
                if account['role']!='customer': raise PermissionError('A customer account is required.')
                store.delete_customer(account['username'])
                return self.json_response(200,{'ok':True},'wobli_customer=; HttpOnly; SameSite=Strict; Path=/; Max-Age=0')
            if path in ('/api/account/profile', '/api/account/email', '/api/account/password', '/api/account/replies/read', '/api/account/orders/read'):
                account = self.account(write=self.command != 'GET')
                if not account or account['role'] != 'customer':
                    raise PermissionError('A customer account is required.')
                if self.command == 'POST' and path == '/api/account/replies/read':
                    store.read_replies(account['username'], self.body())
                    return self.json_response(200, {'ok': True})
                if self.command == 'POST' and path == '/api/account/orders/read':
                    store.read_order_updates(account['username'])
                    return self.json_response(200, {'ok': True})
                if self.command == 'GET' and path == '/api/account/profile':
                    return self.json_response(200, {'profile': store.customer_profile(account['username'])})
                if self.command == 'PUT' and path == '/api/account/profile':
                    return self.json_response(200, {'profile': store.save_customer_profile(account['username'], self.body())})
                if self.command == 'POST' and path in ('/api/account/email', '/api/account/password'):
                    store.change_customer_credentials(account['username'], self.body(), path.rsplit('/', 1)[1])
                    return self.json_response(200, {'ok': True}, 'wobli_customer=; HttpOnly; SameSite=Strict; Path=/; Max-Age=0')
            customer_reply = re.fullmatch(r'/api/account/questions/([a-f0-9]{32})/replies', path)
            if self.command == 'POST' and customer_reply:
                account = self.account(write=True)
                if account['role'] != 'customer':
                    raise PermissionError('A customer account is required.')
                return self.json_response(201, {'id': store.reply_question(customer_reply[1], self.body(), customer_email=account['username'])})
            customer_order_cancel=re.fullmatch(r'/api/account/orders/([a-f0-9]{32})/cancel',path)
            if self.command=='POST' and customer_order_cancel:
                account=self.account(write=True)
                if account['role']!='customer': raise PermissionError('A customer account is required.')
                order,changed=store.cancel_customer_order(account['username'],customer_order_cancel[1])
                if changed:self.server.email_executor.submit(self.server.mailer.send_order_cancelled,order)
                return self.json_response(200,{'order':order,'cancelled':changed})
            customer_service_reply=re.fullmatch(r'/api/account/(installations|custom-lab)/([a-f0-9]{32})/replies',path)
            if self.command=='POST' and customer_service_reply:
                account=self.account(write=True)
                if account['role']!='customer': raise PermissionError('A customer account is required.')
                kind='installation' if customer_service_reply[1]=='installations' else 'custom_lab'
                return self.json_response(201,{'id':store.reply_service_request(kind,customer_service_reply[2],self.body(),account['username'])})
            if self.command == 'POST' and path == '/api/questions':
                account = self.account(write=True)
                question_id=store.save_question(account['username'], self.body())
                question=store.question_for_email(question_id)
                if question:self.server.email_executor.submit(self.server.mailer.send_question,question)
                return self.json_response(201, {'id': question_id})
            if self.command == 'POST' and path == '/api/installations':
                account = self.account()
                if not account or account['role'] != 'customer': raise PermissionError('Log in or create an account to make an installation request.')
                customer_email = account['username']
                if not secrets.compare_digest(self.headers.get('X-CSRF-Token', ''), account['csrf']):
                    raise PermissionError('Your session expired. Please log in again.')
                return self.json_response(201, {'id': store.save_installation(self.body(), customer_email, self.client_address[0])})
            if self.command == 'POST' and path == '/api/custom-lab':
                account = self.account()
                if not account or account['role']!='customer': raise PermissionError('Log in or create an account to make a Custom Lab request.')
                customer_email=account['username']
                if not secrets.compare_digest(self.headers.get('X-CSRF-Token',''),account['csrf']): raise PermissionError('Your session expired. Please log in again.')
                return self.json_response(201, {'id':store.save_custom_lab(self.body(),customer_email,self.client_address[0])})
            if self.command == 'GET' and path == '/api/categories':
                return self.json_response(200, {'categories': store.categories()})
            if self.command == 'GET' and path == '/api/products':
                return self.json_response(200, {'products': store.products()})
            if self.command == 'GET' and path == '/api/admin/session':
                session = store.session(self.token())
                return self.json_response(200, {'admin': session})
            if self.command == 'POST' and path == '/api/admin/login':
                data = self.body()
                username, password = data.get('username'), data.get('password')
                if not isinstance(username, str) or not isinstance(password, str) or len(username) > 100 or len(password) > 128:
                    raise ValueError('Invalid login details.')
                token, session = store.login(username.strip(), password, self.client_address[0])
                store.customer_logout(self.token('wobli_customer'))
                old = self.token()
                if old:
                    store.logout(old)
                return self.json_response(200, {'admin': session}, f'wobli_admin={token}; HttpOnly; SameSite=Strict; Path=/; Max-Age=28800')
            if self.command == 'POST' and path == '/api/cart/quote':
                return self.json_response(200, store.quote(self.body().get('items')))
            if path.startswith('/api/admin/'):
                session = self.require_admin(write=self.command != 'GET')
                if self.command == 'POST' and path == '/api/admin/logout':
                    store.logout(self.token())
                    return self.json_response(200, {'ok': True}, 'wobli_admin=; HttpOnly; SameSite=Strict; Path=/; Max-Age=0')
                if self.command == 'POST' and path == '/api/admin/password':
                    data = self.body()
                    store.change_password(session['username'], data.get('current'), data.get('new'))
                    return self.json_response(200, {'ok': True}, 'wobli_admin=; HttpOnly; SameSite=Strict; Path=/; Max-Age=0')
                if self.command == 'GET' and path == '/api/admin/questions':
                    return self.json_response(200, {'questions': store.questions()})
                if self.command == 'GET' and path == '/api/admin/installations':
                    return self.json_response(200, {'installations': store.installations()})
                if self.command == 'GET' and path == '/api/admin/custom-lab': return self.json_response(200, {'requests':store.custom_lab_requests()})
                if self.command == 'GET' and path == '/api/admin/orders': return self.json_response(200, {'orders':store.admin_orders()})
                order_match=re.fullmatch(r'/api/admin/orders/([a-f0-9]{32})',path)
                if self.command=='PUT' and order_match:
                    order,changed=store.update_order_status(order_match[1],self.body())
                    if changed and order and order['fulfillment_status']=='cancelled':self.server.email_executor.submit(self.server.mailer.send_order_cancelled,order)
                    return self.json_response(200,{'ok':True})
                order_read=re.fullmatch(r'/api/admin/orders/([a-f0-9]{32})/read',path)
                if self.command=='POST' and order_read:
                    store.read_order_admin(order_read[1]);return self.json_response(200,{'ok':True})
                service_reply=re.fullmatch(r'/api/admin/(installations|custom-lab)/([a-f0-9]{32})/replies',path)
                if self.command=='POST' and service_reply:
                    kind='installation' if service_reply[1]=='installations' else 'custom_lab'
                    return self.json_response(201,{'id':store.reply_service_request(kind,service_reply[2],self.body())})
                service_read=re.fullmatch(r'/api/admin/(installations|custom-lab)/([a-f0-9]{32})/read',path)
                if self.command=='POST' and service_read:
                    kind='installation' if service_read[1]=='installations' else 'custom_lab'
                    store.read_service_admin(kind,service_read[2]); return self.json_response(200,{'ok':True})
                custom_match=re.fullmatch(r'/api/admin/custom-lab/([a-f0-9]{32})',path)
                if custom_match and self.command=='PUT': store.update_custom_lab(custom_match[1],self.body()); return self.json_response(200,{'ok':True})
                if custom_match and self.command=='DELETE': store.delete_custom_lab(custom_match[1]); return self.json_response(200,{'ok':True})
                installation_match = re.fullmatch(r'/api/admin/installations/([a-f0-9]{32})', path)
                if installation_match and self.command == 'PUT':
                    store.update_installation(installation_match[1], self.body())
                    return self.json_response(200, {'ok': True})
                if installation_match and self.command == 'DELETE':
                    store.delete_installation(installation_match[1])
                    return self.json_response(200, {'ok': True})
                question_match = re.fullmatch(r'/api/admin/questions/([a-f0-9]{32})', path)
                reply_match = re.fullmatch(r'/api/admin/questions/([a-f0-9]{32})/replies', path)
                read_match = re.fullmatch(r'/api/admin/questions/([a-f0-9]{32})/read', path)
                if self.command == 'POST' and read_match:
                    store.read_question_admin(read_match[1]); return self.json_response(200, {'ok':True})
                if self.command == 'POST' and reply_match:
                    data=self.body();reply_id=store.reply_question(reply_match[1],data)
                    question=store.question_for_email(reply_match[1])
                    if question:self.server.email_executor.submit(self.server.mailer.send_question_reply,question,reply_id,data.get('message','').strip())
                    return self.json_response(201, {'id': reply_id})
                if self.command == 'DELETE' and question_match:
                    store.delete_question(question_match[1])
                    return self.json_response(200, {'ok': True})
                if self.command == 'POST' and path == '/api/admin/categories':
                    return self.json_response(201, {'category': store.save_category(self.body())})
                category_match = re.fullmatch(r'/api/admin/categories/([a-z0-9]+)', path)
                if category_match and self.command == 'PUT':
                    return self.json_response(200, {'category': store.save_category(self.body(), category_match[1])})
                if category_match and self.command == 'DELETE':
                    store.delete_category(category_match[1])
                    return self.json_response(200, {'ok': True})
                if self.command == 'GET' and path == '/api/admin/products':
                    return self.json_response(200, {'products': store.products(admin=True)})
                if self.command == 'POST' and path == '/api/admin/products':
                    data = self.body()
                    self.validated_image(data.get('image', ''))
                    images = data.get('images', [])
                    if not isinstance(images, list) or len(images) > 12:
                        raise ValueError('Choose up to 12 product images.')
                    for image in images:
                        self.validated_image(image)
                    return self.json_response(201, {'product': store.save(data)})
                match = re.fullmatch(r'/api/admin/products/([a-f0-9]{32})', path)
                if self.command == 'PUT' and match:
                    data = self.body()
                    self.validated_image(data.get('image', ''))
                    images = data.get('images', [])
                    if not isinstance(images, list) or len(images) > 12:
                        raise ValueError('Choose up to 12 product images.')
                    for image in images:
                        self.validated_image(image)
                    return self.json_response(200, {'product': store.save(data, match[1])})
                if self.command == 'POST' and path == '/api/admin/upload':
                    data = self.body(limit=5 * 1024 * 1024, raw=True)
                    mime = self.headers.get_content_type()
                    if mime == 'image/png' and data.startswith(b'\x89PNG\r\n\x1a\n') and len(data) >= 24:
                        width, height = struct.unpack('>II', data[16:24])
                        if not 0 < width <= 8000 or not 0 < height <= 8000:
                            raise ValueError('Image dimensions must be below 8000 pixels.')
                        extension = 'png'
                    elif mime == 'image/jpeg' and data.startswith(b'\xff\xd8\xff') and data.endswith(b'\xff\xd9'):
                        extension = 'jpg'
                    elif mime == 'image/webp' and data.startswith(b'RIFF') and data[8:12] == b'WEBP':
                        extension = 'webp'
                    else:
                        raise ValueError('Choose a PNG, JPEG or WebP image (maximum 5 MB).')
                    directory = store.directory / 'uploads'
                    directory.mkdir(exist_ok=True, mode=0o700)
                    name = hashlib.sha256(data).hexdigest() + '.' + extension
                    (directory / name).write_bytes(data)
                    return self.json_response(201, {'image': 'uploads/' + name})
            if path.startswith('/api/') or self.command not in ('GET', 'HEAD'):
                return self.json_response(404, {'error': 'Not found.'})
            self.serve_static(path)
        except PermissionError as exc:
            self.json_response(403, {'error': str(exc)})
        except TimeoutError as exc:
            self.json_response(429, {'error': str(exc)})
        except LookupError as exc:
            self.json_response(404, {'error': str(exc)})
        except RuntimeError as exc:
            self.json_response(409, {'error': str(exc)})
        except ValueError as exc:
            self.json_response(400, {'error': str(exc)})
        except Exception:
            self.json_response(500, {'error': 'The server could not complete this request.'})

    def serve_static(self, path):
        path = unquote(path).lstrip('/') or 'index.html'
        if path == 'index.html':
            file = PUBLIC / path
        elif re.fullmatch(r'(styles|scripts|assets)/[A-Za-z0-9_.-]+\.(css|js|png|jpg|jpeg|webp)', path):
            file = PUBLIC / path
        elif re.fullmatch(r'uploads/[a-f0-9]{64}\.(png|jpg|webp)', path):
            file = self.server.store.directory / path
        else:
            return self.json_response(404, {'error': 'Not found.'})
        if not file.is_file():
            return self.json_response(404, {'error': 'Not found.'})
        data = file.read_bytes()
        self.send_response(200)
        self.headers_common()
        self.send_header('Content-Type', mimetypes.guess_type(file)[0] or 'application/octet-stream')
        self.send_header('Content-Length', str(len(data)))
        self.end_headers()
        if self.command != 'HEAD':
            self.wfile.write(data)

    do_GET = dispatch
    do_HEAD = dispatch
    do_POST = dispatch
    do_PUT = dispatch
    do_DELETE = dispatch


def make_server(port=8082, directory=None):
    data_directory = directory or os.environ.get('WOBLI_DATA_DIR') or ROOT.parent / 'local-files' / '.data'
    if directory is None and not os.environ.get('WOBLI_DATA_DIR') and not Path(data_directory).is_dir():
        raise RuntimeError('Set WOBLI_DATA_DIR to private persistent storage before starting this copy. See README.md.')
    store = Store(data_directory)
    store.seed()
    server = ThreadingHTTPServer(('127.0.0.1', port), Handler)
    server.store = store
    actual_port = server.server_address[1]
    server.allowed_hosts = {f'127.0.0.1:{actual_port}', f'localhost:{actual_port}'}
    server.public_origin=os.environ.get('PUBLIC_ORIGIN',f'http://localhost:{actual_port}').rstrip('/')
    server.allowed_origins={f'http://{host}' for host in server.allowed_hosts}|{server.public_origin}
    server.mailer=Mailer(store)
    server.email_executor=ThreadPoolExecutor(max_workers=2,thread_name_prefix='wobli-email')
    return server


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', type=int, default=8082)
    args = parser.parse_args()
    server = make_server(args.port)
    print(f'Wobli is ready at http://127.0.0.1:{server.server_address[1]}', flush=True)
    print('Initial admin access: private data directory/admin-access.txt.', flush=True)
    print('Transactional email: '+('configured' if server.mailer.enabled else 'not configured'),flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        server.server_close()
