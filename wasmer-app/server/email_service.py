"""Transactional email through authenticated SMTP. Secrets stay in environment variables."""
import html
import os
import smtplib
import ssl
from email.message import EmailMessage
from email.utils import formataddr


def money(cents):
    return f"CHF {cents / 100:,.2f}"


class Mailer:
    def __init__(self, store):
        self.store=store
        self.host=os.environ.get('SMTP_HOST','').strip()
        try: self.port=int(os.environ.get('SMTP_PORT','587'))
        except ValueError: self.port=0
        self.user=os.environ.get('SMTP_USER','').strip()
        self.password=os.environ.get('SMTP_PASSWORD','').strip()
        self.from_name=os.environ.get('SMTP_FROM_NAME','Wobli').strip() or 'Wobli'
        self.admin=os.environ.get('ADMIN_EMAIL','').strip()
        self.enabled=bool(self.host and self.port and self.user and self.password and self.admin and 'PASTE_' not in self.password)

    def deliver(self,event_key,recipient,subject,text_body,html_body,reply_to=None):
        key=f'{event_key}:{recipient.lower()}'
        if not self.enabled or not self.store.claim_email(key): return False
        message=EmailMessage()
        message['From']=formataddr((self.from_name,self.user));message['To']=recipient;message['Subject']=subject
        if reply_to: message['Reply-To']=reply_to
        message.set_content(text_body)
        message.add_alternative(html_body,subtype='html')
        try:
            context=ssl.create_default_context()
            with smtplib.SMTP(self.host,self.port,timeout=20) as smtp:
                smtp.ehlo();smtp.starttls(context=context);smtp.ehlo();smtp.login(self.user,self.password);smtp.send_message(message)
            self.store.finish_email(key,True);return True
        except Exception as exc:
            self.store.finish_email(key,False,type(exc).__name__)
            print(f'Email delivery failed ({event_key}, {type(exc).__name__}).',flush=True)
            return False

    @staticmethod
    def shell(title,content):
        return f'''<!doctype html><html><body style="margin:0;background:#080d12;color:#eef7fb;font-family:Arial,sans-serif"><div style="max-width:620px;margin:auto;padding:36px 24px"><div style="color:#69d7ff;letter-spacing:3px;font-size:12px">WOBLI</div><h1 style="font-size:26px">{html.escape(title)}</h1><div style="background:#101820;border:1px solid #263845;border-radius:16px;padding:24px;line-height:1.65">{content}</div><p style="color:#7f929f;font-size:12px;margin-top:24px">This is an automatic transactional email from Wobli.</p></div></body></html>'''

    def send_order(self,order):
        shipping=order['shipping'];items=order['items'];order_id=order['public_id']
        item_text='\n'.join(f"- {item['quantity']} × {item['name']} — {money(item['quantity']*item['unit_amount'])}" for item in items)
        item_html=''.join(f"<p>{item['quantity']} × {html.escape(item['name'])} <strong style='float:right'>{money(item['quantity']*item['unit_amount'])}</strong></p>" for item in items)
        address=', '.join(filter(None,[shipping['address'],shipping.get('address_extra',''),f"{shipping['postal_code']} {shipping['city']}",shipping['country']]))
        customer_text=f"Thank you for your order, {shipping['name']}!\n\nYour payment was successful and order {order_id} is confirmed.\n\n{item_text}\n\nTotal: {money(order['amount_cents'])}\nDelivery: {address}\n\nYou can follow its status in My orders on your Wobli profile."
        customer_html=self.shell('Thank you for your order!',f"<p>Hello {html.escape(shipping['name'])},</p><p>Your payment was successful. Order <strong>{html.escape(order_id)}</strong> is confirmed.</p>{item_html}<p style='border-top:1px solid #263845;padding-top:14px'><strong>Total: {money(order['amount_cents'])}</strong></p><p>Delivery: {html.escape(address)}</p><p>You can follow its status in <strong>My orders</strong> on your profile.</p>")
        self.deliver(f'order:{order["id"]}:customer',order['customer_email'],f'Order {order_id} confirmed',customer_text,customer_html)
        admin_text=f"New paid order {order_id}\n\nCustomer: {shipping['name']} {shipping['surname']}\nEmail: {order['customer_email']}\nTelephone: {shipping['phone']}\nDelivery: {address}\n\n{item_text}\n\nTotal: {money(order['amount_cents'])}"
        admin_html=self.shell(f'New order {order_id}',f"<p><strong>{html.escape(shipping['name'])} {html.escape(shipping['surname'])}</strong><br>{html.escape(order['customer_email'])}<br>{html.escape(shipping['phone'])}</p><p>Delivery: {html.escape(address)}</p>{item_html}<p style='border-top:1px solid #263845;padding-top:14px'><strong>Total: {money(order['amount_cents'])}</strong></p>")
        self.deliver(f'order:{order["id"]}:admin',self.admin,f'New paid order {order_id}',admin_text,admin_html,order['customer_email'])

    def send_order_cancelled(self,order):
        shipping=order['shipping'];order_id=order['public_id'];name=shipping.get('name','Customer')
        item_text='\n'.join(f"- {item['quantity']} × {item['name']}" for item in order['items'])
        item_html=''.join(f"<p>{item['quantity']} × {html.escape(item['name'])}</p>" for item in order['items'])
        customer_text=f"Hello {name},\n\nOrder {order_id} has been cancelled.\n\n{item_text}\n\nTotal paid: {money(order['amount_cents'])}\n\nIf a refund is due, Wobli will process it separately and send confirmation."
        customer_html=self.shell('Your order has been cancelled',f"<p>Hello {html.escape(name)},</p><p>Order <strong>{html.escape(order_id)}</strong> has been cancelled.</p>{item_html}<p><strong>Total paid: {money(order['amount_cents'])}</strong></p><p>If a refund is due, Wobli will process it separately and send confirmation.</p>")
        self.deliver(f'order-cancelled:{order["id"]}:customer',order['customer_email'],f'Order {order_id} cancelled',customer_text,customer_html)
        admin_text=f"Customer cancelled order {order_id}\n\nCustomer: {name} {shipping.get('surname','')}\nEmail: {order['customer_email']}\nTelephone: {shipping.get('phone','')}\n\n{item_text}\n\nTotal paid: {money(order['amount_cents'])}\n\nReview the payment and process any refund that is due."
        admin_html=self.shell(f'Order {order_id} cancelled',f"<p><strong>{html.escape(name)} {html.escape(shipping.get('surname',''))}</strong><br>{html.escape(order['customer_email'])}<br>{html.escape(shipping.get('phone',''))}</p>{item_html}<p><strong>Total paid: {money(order['amount_cents'])}</strong></p><p>Review the payment and process any refund that is due.</p>")
        self.deliver(f'order-cancelled:{order["id"]}:admin',self.admin,f'Customer cancelled order {order_id}',admin_text,admin_html,order['customer_email'])

    def send_question(self,question):
        email=question['author'];product=question['product_name'];body=question['message']
        customer_text=f"Thank you for your message!\n\nWe received your question about {product}.\n\nYour message:\n{body}\n\nWe will reply as soon as possible. You can follow the conversation in your Wobli profile."
        customer_html=self.shell('Thank you for your message!',f"<p>We received your question about <strong>{html.escape(product)}</strong>.</p><p style='border-left:2px solid #69d7ff;padding-left:14px'>{html.escape(body)}</p><p>We will reply as soon as possible. You can follow the conversation in your profile.</p>")
        self.deliver(f'question:{question["id"]}:customer',email,f'We received your question about {product}',customer_text,customer_html)
        admin_text=f"New product question\n\nCustomer: {email}\nProduct: {product}\n\nQuestion:\n{body}"
        admin_html=self.shell('New product question',f"<p>Customer: <strong>{html.escape(email)}</strong><br>Product: <strong>{html.escape(product)}</strong></p><p style='border-left:2px solid #ff941f;padding-left:14px'>{html.escape(body)}</p>")
        self.deliver(f'question:{question["id"]}:admin',self.admin,f'New question: {product}',admin_text,admin_html,email)

    def send_question_reply(self,question,reply_id,reply):
        email=question['author'];product=question['product_name'];original=question['message']
        text=f"Wobli replied to your question about {product}.\n\nOur reply:\n{reply}\n\nYour original question:\n{original}\n\nYou can continue the conversation from Messages in your Wobli profile."
        content=f"<p>We replied to your question about <strong>{html.escape(product)}</strong>.</p><p style='border-left:2px solid #ff941f;padding-left:14px'><strong>Wobli</strong><br>{html.escape(reply)}</p><p style='color:#8da0ad'>Your original question:</p><p style='border-left:2px solid #69d7ff;padding-left:14px'>{html.escape(original)}</p><p>You can continue the conversation from <strong>Messages</strong> in your profile.</p>"
        self.deliver(f'question-reply:{reply_id}',email,f'We replied about {product}',text,self.shell('You have a new reply',content))
