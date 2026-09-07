import sys
import json
from pathlib import Path
import tempfile
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'wasmer-app' / 'server'))
from store import Store, password_hash


class StoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.store = Store(self.temp.name)
        with self.store.connect() as db:
            db.execute('UPDATE admins SET password=? WHERE username=?', (password_hash('Test-only-password-123'), 'admin'))

    def tearDown(self):
        self.temp.cleanup()

    def product(self, **changes):
        p = dict(name='Test mount', sku='TEST-001', description='Test', category='mounts', status='active',
                 availability='stock', vehicle=['car'], price_cents=5990, stock=4, image='', lead_time='')
        p.update(changes)
        return p

    def test_profile_messages_are_private_and_persistent(self):
        password = 'Message-test-password'
        for email in ['one@example.com', 'two@example.com']:
            self.store.customer_auth(email, password, email, True, password)
        product = self.store.save(self.product())
        question = self.store.save_question('one@example.com', {'product_id': product['id'], 'message': 'Does this fit?', 'request_id': 'a' * 32})
        reopened = Store(self.temp.name)
        self.assertEqual(reopened.customer_profile('two@example.com')['messages'], [])
        messages = reopened.customer_profile('one@example.com')['messages']
        self.assertEqual([message['id'] for message in messages], [question])
        self.assertEqual(messages[0]['message'], 'Does this fit?')
        self.assertEqual(reopened.save_customer_profile('one@example.com', {'name': 'One'})['messages'], messages)
        self.assertEqual(reopened.notification_counts({'role':'admin','username':'admin'})['messages'],1)
        reopened.read_question_admin(question)
        self.assertEqual(reopened.notification_counts({'role':'admin','username':'admin'})['messages'],0)
        payload = {'message': 'Yes, it fits.', 'request_id': 'b' * 32}
        reply = reopened.reply_question(question, payload)
        self.assertEqual(reopened.reply_question(question, payload), reply)
        reopened = Store(self.temp.name)
        self.assertEqual(len(reopened.questions()[0]['replies']), 1)
        self.assertEqual(reopened.notification_counts({'role':'customer', 'username':'one@example.com'})['total'], 1)
        self.assertEqual(reopened.notification_counts({'role':'admin', 'username':'admin'})['total'], 0)
        self.assertEqual(reopened.customer_profile('two@example.com')['messages'], [])
        reopened.read_replies('two@example.com', {'ids': [reply]})
        self.assertEqual(reopened.customer_profile('one@example.com')['messages'][0]['replies'][0]['is_read'], 0)
        reopened.read_replies('one@example.com', {'ids': [reply]})
        self.assertEqual(Store(self.temp.name).customer_profile('one@example.com')['messages'][0]['replies'][0]['is_read'], 1)
        self.assertEqual(reopened.notification_counts({'role':'customer', 'username':'one@example.com'})['total'], 0)
        with self.assertRaises(ValueError):
            reopened.reply_question(question, {'message': ' ', 'request_id': 'c' * 32})
        reopened.delete_question(question)
        with reopened.connect() as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM question_replies').fetchone()[0], 0)

    def test_category_lifecycle_and_other_vehicle(self):
        category = self.store.save_category({'name': 'Lighting'})
        product = self.store.save(self.product(category=category['id'], vehicle=['other']))
        self.store.save_category({'name': 'Lights & signals'}, category['id'])
        reopened = Store(self.temp.name)
        self.assertIn({'id': category['id'], 'name': 'Lights & signals'}, reopened.categories())
        self.assertEqual(reopened.products()[0]['vehicle'], ['other'])
        with self.assertRaises(ValueError):
            reopened.save_category({'name': 'lights & signals'})
        with self.assertRaises(ValueError):
            reopened.delete_category(category['id'])
        reopened.save(dict(product, category='mounts'), product['id'])
        reopened.delete_category(category['id'])
        self.assertNotIn(category['id'], [c['id'] for c in Store(self.temp.name).categories()])
        with self.assertRaises(ValueError):
            reopened.save(self.product(sku='REMOVED', category=category['id']))
        reopened.delete_category('care')
        self.assertNotIn('care', [c['id'] for c in Store(self.temp.name).categories()])

    def test_customer_account_deletion_removes_private_data(self):
        email='delete@example.com';password='Delete-test-password'
        self.store.customer_auth(email,password,'delete-test',True,password)
        self.store.save_customer_profile(email,{'name':'Delete Me'})
        product=self.store.save(self.product(sku='DELETE-001'))
        question=self.store.save_question(email,{'product_id':product['id'],'message':'Private question','request_id':'e'*32})
        self.store.reply_question(question,{'message':'Private reply','request_id':'f'*32})
        self.store.delete_customer(email)
        with self.store.connect() as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM customers WHERE email=?',(email,)).fetchone()[0],0)
            self.assertEqual(db.execute('SELECT COUNT(*) FROM questions WHERE author=?',(email,)).fetchone()[0],0)
            self.assertEqual(db.execute('SELECT COUNT(*) FROM question_replies WHERE question_id=?',(question,)).fetchone()[0],0)

    def test_installation_requests_are_private_and_manageable(self):
        product = self.store.save(self.product())
        data = {'email':'guest@example.com','vehicle_type':'car','vehicle_model':'BMW G20','vehicle_year':'2022','product_id':product['id'],'comment':'Centre console'}
        guest = self.store.save_installation(data, None, 'guest-install')
        member = self.store.save_installation(dict(data, email='ignored@example.com'), 'member@example.com', 'member-install')
        self.assertEqual(self.store.installations('member@example.com')[0]['email'], 'member@example.com')
        self.assertEqual(self.store.installations('guest@example.com'), [])
        self.assertEqual(len(self.store.installations()), 2)
        self.assertFalse(self.store.installations('member@example.com')[0]['admin_read'])
        self.store.read_service_admin('installation',member)
        self.assertTrue(self.store.installations('member@example.com')[0]['admin_read'])
        reply=self.store.reply_service_request('installation',member,{'message':'We can install this next week.','request_id':'d'*32})
        self.assertEqual(self.store.installations('member@example.com')[0]['replies'][0]['id'],reply)
        self.assertEqual(self.store.notification_counts({'role':'customer','username':'member@example.com'})['installations'],1)
        self.store.read_replies('member@example.com',{'ids':[reply]})
        self.assertEqual(self.store.notification_counts({'role':'customer','username':'member@example.com'})['installations'],0)
        customer_reply=self.store.reply_service_request('installation',member,{'message':'Next week works.','request_id':'1'*32},'member@example.com')
        self.assertEqual(self.store.installations('member@example.com')[0]['replies'][-1]['id'],customer_reply)
        self.assertFalse(self.store.installations('member@example.com')[0]['admin_read'])
        self.store.update_installation(member, {'status':'scheduled'})
        self.assertEqual(self.store.installations('member@example.com')[0]['status'], 'scheduled')
        with self.assertRaises(ValueError): self.store.update_installation(member, {'status':'unknown'})
        self.store.delete_installation(guest)
        self.assertEqual(len(Store(self.temp.name).installations()), 1)

    def test_custom_lab_modes_privacy_and_status(self):
        suggestion={'email':'guest@example.com','request_type':'new_product','product_name':'Helmet dock','description':'Please add this.'}
        guest=self.store.save_custom_lab(suggestion,None,'custom-guest')
        custom={'request_type':'custom_product','vehicle_type':'moto','vehicle_model':'Yamaha MT-07','vehicle_year':'2021','budget':'CHF 500','description':'Custom display mount'}
        member=self.store.save_custom_lab(custom,'member@example.com','custom-member')
        self.assertEqual(self.store.custom_lab_requests('guest@example.com'),[])
        self.assertEqual(self.store.custom_lab_requests('member@example.com')[0]['budget'],'CHF 500')
        self.store.update_custom_lab(member,{'status':'reviewing'})
        self.assertEqual(self.store.custom_lab_requests('member@example.com')[0]['status'],'reviewing')
        with self.assertRaises(ValueError): self.store.save_custom_lab({'request_type':'new_product','description':'No name'},'x@example.com','invalid-custom')
        self.store.delete_custom_lab(guest)
        self.assertEqual(len(Store(self.temp.name).custom_lab_requests()),1)

    def test_customer_account_survives_database_reopen(self):
        password = 'Persistent-test-password'
        token, account = self.store.customer_auth('Customer@Example.com', password, 'register-test', True, password)
        self.assertEqual(account['username'], 'customer@example.com')
        reopened = Store(self.temp.name)
        self.assertEqual(reopened.customer_session(token)['username'], account['username'])
        reopened.customer_logout(token)
        self.assertIsNone(reopened.customer_session(token))
        with self.assertRaises(PermissionError):
            reopened.customer_auth('customer@example.com', 'wrong-password', 'bad-login')
        token, signed_in = reopened.customer_auth('customer@example.com', password, 'good-login')
        self.assertEqual(signed_in['role'], 'customer')
        self.assertIsNone(reopened.session(token))
        with reopened.connect() as db:
            stored = db.execute('SELECT password FROM customers').fetchone()['password']
        self.assertNotEqual(stored, password)
        with self.assertRaises(ValueError):
            reopened.customer_auth('CUSTOMER@example.com', password, 'duplicate-test', True, password)

    def test_customer_profile_email_and_password_changes(self):
        password = 'Profile-test-password'
        token, _ = self.store.customer_auth('old@example.com', password, 'profile', True, password)
        p = self.store.save(self.product())
        self.store.save_question('old@example.com', {'product_id': p['id'], 'message': 'A question', 'request_id': 'c' * 32})
        self.store.save_customer_profile('old@example.com', {'name': 'Test', 'surname': 'Person', 'city': 'Lausanne'})
        self.assertEqual(Store(self.temp.name).customer_profile('old@example.com')['details']['city'], 'Lausanne')
        with self.assertRaises(ValueError):
            self.store.change_customer_credentials('old@example.com', {'current': 'wrong', 'email': 'new@example.com'}, 'email')
        self.store.change_customer_credentials('old@example.com', {'current': password, 'email': 'NEW@example.com'}, 'email')
        self.assertIsNone(self.store.customer_session(token))
        self.assertEqual(self.store.customer_profile('new@example.com')['details']['name'], 'Test')
        self.assertEqual(self.store.questions()[0]['author'], 'new@example.com')
        self.assertEqual(self.store.customer_profile('new@example.com')['messages'][0]['message'], 'A question')
        with self.assertRaises(PermissionError):
            self.store.customer_auth('old@example.com', password, 'old-login')
        token, _ = self.store.customer_auth('new@example.com', password, 'new-login')
        self.store.change_customer_credentials('new@example.com', {'current': password, 'password': 'Replacement-123', 'confirmation': 'Replacement-123'}, 'password')
        self.assertIsNone(self.store.customer_session(token))
        with self.assertRaises(PermissionError):
            self.store.customer_auth('new@example.com', password, 'old-password')
        self.assertEqual(self.store.customer_auth('new@example.com', 'Replacement-123', 'new-password')[1]['role'], 'customer')

    def test_create_edit_and_persist(self):
        p = self.store.save(self.product())
        p['price_cents'] = 6900
        updated = self.store.save(p, p['id'])
        self.assertEqual(updated['revision'], 2)
        self.assertEqual(Store(self.temp.name).products()[0]['price_cents'], 6900)

    def test_gallery_persistence_cover_and_legacy_image(self):
        p = self.store.save(self.product(image='assets/cover.png'))
        self.assertEqual(p['images'], ['assets/cover.png'])
        p['images'] = ['assets/second.png', 'assets/cover.png']
        p = self.store.save(p, p['id'])
        self.assertEqual(p['image'], 'assets/second.png')
        self.assertEqual(Store(self.temp.name).products()[0]['images'], p['images'])
        p['images'] = []
        self.assertEqual(self.store.save(p, p['id'])['image'], '')
        with self.assertRaises(ValueError):
            self.store.save(self.product(images=['image.png'] * 13))
        with self.assertRaises(ValueError):
            self.store.save(self.product(images='not-a-list'))

    def test_drafts_archives_hidden_and_conflicts_rejected(self):
        p = self.store.save(self.product(status='draft'))
        self.assertEqual(self.store.products(), [])
        self.assertEqual(len(self.store.products(admin=True)), 1)
        p['status'] = 'active'
        self.store.save(p, p['id'])
        with self.assertRaises(RuntimeError): self.store.save(p, p['id'])
        p = self.store.products()[0]; p['status'] = 'archived'
        self.store.save(p, p['id'])
        self.assertEqual(self.store.products(), [])

    def test_duplicate_sku_and_invalid_inputs(self):
        self.store.save(self.product())
        with self.assertRaises(ValueError): self.store.save(self.product())
        for patch in ({'price_cents': -1}, {'stock': 1.5}, {'vehicle': ['spaceship']}, {'status': 'invalid'}, {'price_cents': True}, {'availability': 'preorder', 'lead_time': ''}):
            with self.subTest(patch=patch), self.assertRaises(ValueError): self.store.save(self.product(**patch))

    def test_cart_uses_server_price_and_checks_stock(self):
        p = self.store.save(self.product())
        quote = self.store.quote([dict(id=p['id'], quantity=2, price_cents=1)])
        self.assertEqual(quote['subtotal_cents'], 11980)
        self.assertFalse(quote['checkout_enabled'])
        shipping={'name':'Test','surname':'Buyer','phone':'+41 79 000 00 00','address':'Main Street 1','address_extra':'','postal_code':'1000','city':'Lausanne','country':'Switzerland'}
        order=self.store.create_order('buyer@example.com',quote,'2'*32,shipping,'2026-09-07')
        self.assertEqual(self.store.create_order('buyer@example.com',quote,'2'*32,shipping,'2026-09-07'),order)
        with self.store.connect() as db:
            accepted=db.execute('SELECT policy_version,policy_accepted_at FROM orders WHERE id=?',(order,)).fetchone()
        self.assertEqual(accepted['policy_version'],'2026-09-07')
        self.assertGreater(accepted['policy_accepted_at'],0)
        self.store.attach_payment_session(order,'payment_test_server_price')
        self.store.mark_order_paid('payment_test_server_price','paid')
        orders=self.store.customer_orders('buyer@example.com')
        self.assertEqual(len(orders),1)
        self.assertEqual((orders[0]['id'],orders[0]['status'],orders[0]['amount_cents']),(order,'paid',11980))
        self.assertEqual(orders[0]['items'][0]['unit_amount'],5990)
        self.assertEqual(self.store.customer_orders('other@example.com'),[])
        self.assertEqual(self.store.owns_payment_session('buyer@example.com','payment_test_server_price'),order)
        self.assertIsNone(self.store.owns_payment_session('other@example.com','payment_test_server_price'))
        admin_order=self.store.admin_orders()[0]
        self.assertEqual(admin_order['shipping']['city'],'Lausanne')
        self.assertEqual(self.store.notification_counts({'role':'admin','username':'admin'})['orders'],1)
        self.store.read_order_admin(order)
        self.assertEqual(self.store.notification_counts({'role':'admin','username':'admin'})['orders'],0)
        self.store.update_order_status(order,{'status':'in_preparation'})
        self.assertEqual(self.store.customer_orders('buyer@example.com')[0]['fulfillment_status'],'in_preparation')
        self.assertEqual(self.store.notification_counts({'role':'customer','username':'buyer@example.com'})['orders'],1)
        self.store.read_order_updates('buyer@example.com')
        self.assertEqual(self.store.notification_counts({'role':'customer','username':'buyer@example.com'})['orders'],0)
        cancelled,changed=self.store.cancel_customer_order('buyer@example.com',order)
        self.assertTrue(changed);self.assertEqual(cancelled['fulfillment_status'],'cancelled')
        self.assertEqual(self.store.customer_orders('buyer@example.com')[0]['fulfillment_status'],'cancelled')
        self.assertEqual(self.store.notification_counts({'role':'admin','username':'admin'})['orders'],1)
        self.assertFalse(self.store.cancel_customer_order('buyer@example.com',order)[1])
        with self.assertRaises(LookupError):self.store.cancel_customer_order('other@example.com',order)
        self.store.update_order_status(order,{'status':'sent'})
        with self.assertRaises(ValueError):self.store.cancel_customer_order('buyer@example.com',order)
        with self.store.connect() as db:
            saved=db.execute('SELECT amount_cents,status,items FROM orders WHERE id=?',(order,)).fetchone()
            self.assertEqual((saved['amount_cents'],saved['status']),(11980,'paid'))
            self.assertEqual(json.loads(saved['items'])[0]['unit_amount'],5990)
        self.assertTrue(self.store.quote([dict(id=p['id'], quantity=5)])['lines'][0]['issue'])
        p['price_cents'] = 10000; self.store.save(p, p['id'])
        self.assertEqual(self.store.quote([dict(id=p['id'], quantity=2)])['subtotal_cents'], 20000)
        with self.assertRaises(ValueError): self.store.quote([dict(id=p['id'], quantity=-1)])
        with self.assertRaises(ValueError): self.store.quote([dict(id=p['id'], quantity=1)] * 2)

    def test_preorder_concept_and_unavailable_cart(self):
        p = self.store.save(self.product(availability='preorder', lead_time='3 weeks', stock=0))
        self.assertIsNone(self.store.quote([dict(id=p['id'], quantity=3)])['lines'][0]['issue'])
        p['availability'] = 'concept'; self.store.save(p, p['id'])
        self.assertTrue(self.store.quote([dict(id=p['id'], quantity=1)])['lines'][0]['issue'])
        self.assertTrue(self.store.quote([dict(id='missing', quantity=1)])['lines'][0]['issue'])

    def test_login_session_logout_and_password_change(self):
        with self.assertRaises(PermissionError): self.store.login('admin', 'wrong', 'test')
        token, admin = self.store.login('admin', 'Test-only-password-123', 'test')
        self.assertEqual(self.store.session(token)['csrf'], admin['csrf'])
        with self.store.connect() as db:
            stored = db.execute('SELECT token FROM sessions').fetchone()[0]
            self.assertNotEqual(stored, token)
        self.store.change_password('admin', 'Test-only-password-123', 'New-test-password-456')
        self.assertIsNone(self.store.session(token))
        with self.assertRaises(PermissionError): self.store.login('admin', 'Test-only-password-123', 'test')
        token, _ = self.store.login('admin', 'New-test-password-456', 'test')
        self.store.logout(token)
        self.assertIsNone(self.store.session(token))

    def test_rate_limit_and_credential_permissions(self):
        for _ in range(10):
            with self.assertRaises(PermissionError): self.store.login('admin', 'bad', 'attacker')
        with self.assertRaises(TimeoutError): self.store.login('admin', 'Test-only-password-123', 'attacker')
        self.assertEqual((Path(self.temp.name) / 'admin-access.txt').stat().st_mode & 0o777, 0o600)

    def test_seed_is_idempotent(self):
        self.store.seed(); self.store.seed()
        self.assertEqual(len(self.store.products()), 0)
        self.assertTrue(all(p['availability'] == 'concept' and p['price_cents'] is None for p in self.store.products()))

if __name__ == '__main__': unittest.main()
