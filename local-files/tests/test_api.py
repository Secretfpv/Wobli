import http.client
import json
import sys
import tempfile
import threading
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'wasmer-app' / 'server'))
from app import make_server
from store import password_hash


class ApiTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.server = make_server(0, self.temp.name)
        self.port = self.server.server_address[1]
        with self.server.store.connect() as db:
            db.execute('UPDATE admins SET password=?', (password_hash('Test-only-password-123'),))
        self.server.store.save(dict(name='Test object', sku='TEST-001', description='Test fixture', category='mounts',
                                    status='active', availability='stock', vehicle=['other'], price_cents=2500,
                                    stock=10, image='', lead_time=''))
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.cookie = ''; self.csrf = ''

    def tearDown(self):
        self.server.shutdown(); self.server.server_close(); self.thread.join(); self.temp.cleanup()

    def request(self, method, path, body=None, **headers):
        conn = http.client.HTTPConnection('127.0.0.1', self.port)
        defaults = {'Origin': f'http://127.0.0.1:{self.port}', 'Content-Type': 'application/json', 'Cookie': self.cookie, 'X-CSRF-Token': self.csrf}
        defaults.update(headers)
        conn.request(method, path, json.dumps(body) if body is not None else None, defaults)
        response = conn.getresponse(); status = response.status; info = dict(response.getheaders()); raw = response.read(); conn.close()
        return status, json.loads(raw) if info.get('Content-Type', '').startswith('application/json') else raw, info

    def test_customer_questions_are_authenticated_private_and_idempotent(self):
        product = self.server.store.products()[0]
        payload = {'product_id': product['id'], 'message': 'Does this fit my bike?', 'request_id': 'a' * 32}
        self.assertEqual(self.request('POST', '/api/questions', payload)[0], 403)
        credentials = {'email': 'test@example.com', 'password': 'Test-password-123', 'confirmation': 'different'}
        self.assertEqual(self.request('POST', '/api/account/register', credentials)[0], 400)
        credentials['confirmation'] = credentials['password']
        status, data, headers = self.request('POST', '/api/account/register', credentials)
        self.assertEqual(status, 200)
        self.cookie = headers['Set-Cookie'].split(';')[0]; self.csrf = data['account']['csrf']
        self.assertEqual(data['account']['role'], 'customer')
        self.assertEqual(self.request('GET', '/api/admin/questions')[0], 403)
        self.assertEqual(self.request('GET', '/api/admin/products')[0], 403)
        self.assertEqual(self.request('POST', '/api/questions', payload, **{'X-CSRF-Token': ''})[0], 403)
        self.assertEqual(self.request('POST', '/api/questions', payload)[0], 201)
        self.assertEqual(self.request('POST', '/api/questions', payload)[0], 201)
        self.assertEqual(len(self.server.store.questions()), 1)
        self.assertEqual(self.server.store.questions()[0]['author'], 'test@example.com')
        self.assertEqual(self.request('POST', '/api/account/logout', {})[0], 200)
        self.assertEqual(self.request('POST', '/api/questions', payload)[0], 403)
        self.assertEqual(self.request('POST', '/api/account/login', credentials)[0], 200)

    def test_replies_require_admin_and_read_receipts_require_owner_csrf(self):
        token, customer = self.server.store.customer_auth('reader@example.com', 'Test-password-123', 'reply-fixture', True, 'Test-password-123')
        question = self.server.store.save_question('reader@example.com', {'product_id': self.server.store.products()[0]['id'], 'message': 'Fits?', 'request_id': 'd' * 32})
        path = '/api/admin/questions/' + question + '/replies'
        payload = {'message': 'Yes.', 'request_id': 'e' * 32}
        self.assertEqual(self.request('POST', path, payload)[0], 403)
        self.cookie = 'wobli_customer=' + token; self.csrf = customer['csrf']
        self.assertEqual(self.request('POST', path, payload)[0], 403)
        _, data, headers = self.request('POST', '/api/admin/login', {'username': 'admin', 'password': 'Test-only-password-123'})
        self.cookie = headers['Set-Cookie'].split(';')[0]; self.csrf = data['admin']['csrf']
        self.assertEqual(self.request('POST', path, payload, **{'X-CSRF-Token': ''})[0], 403)
        self.assertEqual(self.request('POST', path, payload)[0], 201)
        token, customer = self.server.store.customer_auth('reader@example.com', 'Test-password-123', 'reader-login')
        self.cookie = 'wobli_customer=' + token; self.csrf = customer['csrf']
        self.assertEqual(self.request('GET', '/api/account/profile')[1]['profile']['messages'][0]['replies'][0]['is_read'], 0)
        read = '/api/account/replies/read'
        self.assertEqual(self.request('POST', read, {'ids': ['e' * 32]}, **{'X-CSRF-Token': ''})[0], 403)
        self.assertEqual(self.request('POST', read, {'ids': ['e' * 32]})[0], 200)
        self.assertEqual(self.request('GET', '/api/account/profile')[1]['profile']['messages'][0]['replies'][0]['is_read'], 1)
        customer_path = '/api/account/questions/' + question + '/replies'
        followup = {'message': 'Thanks! What about installation?', 'request_id': 'f' * 32, 'sender': 'admin'}
        self.assertEqual(self.request('POST', customer_path, followup, **{'X-CSRF-Token': ''})[0], 403)
        self.assertEqual(self.request('POST', customer_path, followup)[0], 201)
        self.assertEqual(self.request('POST', customer_path, followup)[0], 201)
        replies = self.server.store.questions()[0]['replies']
        self.assertEqual(len(replies), 2)
        self.assertEqual(replies[-1]['sender'], 'customer')
        self.assertEqual(replies[-1]['is_read'], 1)
        other_token, other = self.server.store.customer_auth('other-reader@example.com', 'Test-password-123', 'other-reply-fixture', True, 'Test-password-123')
        self.cookie = 'wobli_customer=' + other_token; self.csrf = other['csrf']
        self.assertEqual(self.request('POST', customer_path, followup)[0], 404)
        self.assertEqual(self.request('GET', '/api/account/profile')[1]['profile']['messages'], [])
        self.cookie = ''; self.csrf = ''
        self.assertEqual(self.request('POST', customer_path, followup)[0], 403)

    def test_category_writes_require_admin(self):
        self.assertEqual(self.request('GET', '/api/categories')[0], 200)
        self.assertEqual(self.request('POST', '/api/admin/categories', {'name': 'Lights'})[0], 403)
        _, data, headers = self.request('POST', '/api/admin/login', {'username': 'admin', 'password': 'Test-only-password-123'})
        self.cookie = headers['Set-Cookie'].split(';')[0]; self.csrf = data['admin']['csrf']
        self.assertEqual(self.request('POST', '/api/admin/categories', {'name': 'Lights'}, **{'X-CSRF-Token': ''})[0], 403)
        status, data, _ = self.request('POST', '/api/admin/categories', {'name': 'Lights'})
        self.assertEqual(status, 201)
        path = '/api/admin/categories/' + data['category']['id']
        self.assertEqual(self.request('PUT', path, {'name': 'Lighting'})[0], 200)
        self.assertEqual(self.request('DELETE', path, **{'X-CSRF-Token': ''})[0], 403)
        self.assertEqual(self.request('DELETE', path)[0], 200)

    def test_installation_guest_customer_and_admin_access(self):
        product = self.server.store.products()[0]
        payload = {'email':'guest@example.com','vehicle_type':'car','vehicle_model':'BMW G20','vehicle_year':'2022','product_id':product['id'],'comment':'Console'}
        self.assertEqual(self.request('POST','/api/installations',payload)[0],403)
        custom={'request_type':'new_product','product_name':'Helmet dock','description':'Please add it'}
        self.assertEqual(self.request('POST','/api/custom-lab',custom)[0],403)
        credentials={'email':'member@example.com','password':'Member-password-123','confirmation':'Member-password-123'}
        status,data,headers=self.request('POST','/api/account/register',credentials);self.assertEqual(status,200)
        self.cookie=headers['Set-Cookie'].split(';')[0];self.csrf=data['account']['csrf']
        self.assertEqual(self.request('POST','/api/installations',payload,**{'X-CSRF-Token':''})[0],403)
        self.assertEqual(self.request('POST','/api/installations',payload)[0],201)
        self.assertEqual(self.request('POST','/api/custom-lab',custom,**{'X-CSRF-Token':''})[0],403)
        self.assertEqual(self.request('POST','/api/custom-lab',custom)[0],201)
        profile=self.request('GET','/api/account/profile')[1]['profile']
        self.assertEqual(len(profile['installations']),1);self.assertEqual(profile['installations'][0]['email'],'member@example.com');self.assertEqual(len(profile['custom_lab']),1)
        self.assertEqual(self.request('GET','/api/admin/installations')[0],403)
        _,data,headers=self.request('POST','/api/admin/login',{'username':'admin','password':'Test-only-password-123'})
        self.cookie=headers['Set-Cookie'].split(';')[0];self.csrf=data['admin']['csrf']
        installations=self.request('GET','/api/admin/installations')[1]['installations'];self.assertEqual(len(installations),1)
        path='/api/admin/installations/'+installations[0]['id']
        self.assertEqual(self.request('PUT',path,{'status':'contacted'},**{'X-CSRF-Token':''})[0],403)
        self.assertEqual(self.request('PUT',path,{'status':'contacted'})[0],200)
        self.assertEqual(self.request('DELETE',path)[0],200)

    def test_question_deletion_requires_admin_and_csrf(self):
        product = self.server.store.products()[0]
        question_id = self.server.store.save_question('test@example.com', {'product_id': product['id'], 'message': 'Question to remove', 'request_id': 'b' * 32})
        path = '/api/admin/questions/' + question_id
        self.assertEqual(self.request('DELETE', path)[0], 403)
        token, customer = self.server.store.customer_auth('customer@example.com', 'Test-password-123', 'fixture', True, 'Test-password-123')
        self.cookie = 'wobli_customer=' + token; self.csrf = customer['csrf']
        self.assertEqual(self.request('DELETE', path)[0], 403)
        _, data, headers = self.request('POST', '/api/admin/login', {'username': 'admin', 'password': 'Test-only-password-123'})
        self.cookie = headers['Set-Cookie'].split(';')[0]; self.csrf = data['admin']['csrf']
        self.assertEqual(self.request('DELETE', path, **{'X-CSRF-Token': ''})[0], 403)
        self.assertEqual(len(self.server.store.questions()), 1)
        self.assertEqual(self.request('DELETE', path)[0], 200)
        self.assertEqual(self.server.store.questions(), [])
        self.assertEqual(self.request('DELETE', path)[0], 404)
        self.assertEqual(len(self.server.store.products()), 1)

    def test_profiles_are_private_and_email_changes_sign_out(self):
        self.assertEqual(self.request('GET', '/api/account/profile')[0], 403)
        credentials = {'email': 'profile@example.com', 'password': 'Profile-password-123', 'confirmation': 'Profile-password-123'}
        _, data, headers = self.request('POST', '/api/account/register', credentials)
        self.cookie = headers['Set-Cookie'].split(';')[0]; self.csrf = data['account']['csrf']
        self.assertEqual(self.request('PUT', '/api/account/profile', {'name': 'Alice'}, **{'X-CSRF-Token': ''})[0], 403)
        self.assertEqual(self.request('PUT', '/api/account/profile', {'name': 'Alice', 'email': 'other@example.com'})[0], 200)
        self.assertEqual(self.request('GET', '/api/account/profile')[1]['profile']['email'], 'profile@example.com')
        self.server.store.customer_auth('other@example.com', 'Other-password-123', 'fixture', True, 'Other-password-123')
        self.assertEqual(self.server.store.customer_profile('other@example.com')['details']['name'], '')
        self.assertEqual(self.request('POST', '/api/account/email', {'current': credentials['password'], 'email': 'other@example.com'})[0], 400)
        self.assertEqual(self.request('POST', '/api/account/email', {'current': credentials['password'], 'email': 'changed@example.com'})[0], 200)
        self.assertEqual(self.request('GET', '/api/account/profile')[0], 403)
        self.assertEqual(self.server.store.customer_profile('changed@example.com')['details']['name'], 'Alice')

    def test_admin_product_cart_security_flow(self):
        self.assertEqual(self.request('GET','/api/checkout/config')[0],404)
        self.assertEqual(self.request('GET', '/api/admin/products')[0], 403)
        for path in ['/.data/admin-access.txt', '/server/store.py', '/uploads/../shop.sqlite3']:
            self.assertEqual(self.request('GET', path)[0], 404)
        status, data, headers = self.request('POST', '/api/admin/login', {'username': 'admin', 'password': 'Test-only-password-123'})
        self.assertEqual(status, 200)
        self.assertIn('HttpOnly', headers['Set-Cookie']); self.assertIn('SameSite=Strict', headers['Set-Cookie'])
        self.cookie = headers['Set-Cookie'].split(';')[0]; self.csrf = data['admin']['csrf']
        product = dict(name='API test', sku='API-001', description='', admin_comment='Private production note', category='mounts', vehicle=['car'], status='active', availability='stock', price_cents=2500, stock=3, image='', lead_time='')
        self.assertEqual(self.request('POST', '/api/admin/products', product, **{'X-CSRF-Token': ''})[0], 403)
        self.assertEqual(self.request('POST', '/api/admin/products', product, Origin='https://evil.example')[0], 403)
        status, data, _ = self.request('POST', '/api/admin/products', product)
        self.assertEqual(status, 201); product = data['product']
        self.assertEqual(product['admin_comment'], 'Private production note')
        public_product = next(item for item in self.request('GET', '/api/products')[1]['products'] if item['id'] == product['id'])
        self.assertNotIn('admin_comment', public_product)
        status, quote, _ = self.request('POST', '/api/cart/quote', {'items': [{'id': product['id'], 'quantity': 2, 'price_cents': 1}]})
        self.assertEqual(status, 200); self.assertEqual(quote['subtotal_cents'], 5000); self.assertFalse(quote['checkout_enabled'])
        product['status'] = 'archived'
        self.assertEqual(self.request('PUT', '/api/admin/products/' + product['id'], product)[0], 200)
        self.assertEqual(self.request('PUT', '/api/admin/products/' + product['id'], product)[0], 409)
        self.assertEqual(self.request('POST', '/api/admin/logout', {})[0], 200)
        self.assertEqual(self.request('GET', '/api/admin/products')[0], 403)

if __name__ == '__main__': unittest.main()
