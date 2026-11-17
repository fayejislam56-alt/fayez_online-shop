#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
FAYEZ ONLINE SHOP - ENTERPRISE E-COMMERCE ECOSYSTEM (v12.4 - Gaming Categories & Pro AI Shopping Assistant)
"""

import os
import random
import sqlite3
import secrets
import difflib
import re
import json
import base64
import urllib.request
import urllib.parse
import getpass
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from functools import wraps
from flask import (
    Flask, render_template_string, request, redirect, url_for, 
    session, flash, g, jsonify, Response
)
from flask_mail import Mail, Message
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename

# Keep deployable code in the repository and mutable data on a persistent disk.
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = (os.environ.get('FAYEZ_DATA_DIR') or BASE_DIR).strip()
os.makedirs(DATA_DIR, exist_ok=True)
app = Flask(__name__, static_folder=os.path.join(DATA_DIR, 'static'))
app.config['MAX_CONTENT_LENGTH'] = 26 * 1024 * 1024  # 3 product images plus form data
app.permanent_session_lifetime = timedelta(days=30)
DATABASE = os.path.join(DATA_DIR, 'fayez_online_shop.db')

# Load owner mail settings from a local .env file (no extra package required).
ENV_FILE = os.path.join(BASE_DIR, '.env')
if os.path.isfile(ENV_FILE):
    try:
        with open(ENV_FILE, 'r', encoding='utf-8') as _env:
            for _line in _env:
                _line = _line.strip()
                if _line and not _line.startswith('#') and '=' in _line:
                    _key, _value = _line.split('=', 1)
                    os.environ.setdefault(_key.strip(), _value.strip().strip('\"').strip("'"))
    except OSError:
        pass

# Load the secret AFTER .env has been read. Keep it stable between restarts,
# otherwise Flask invalidates every customer's session whenever the app restarts.
_secret_from_env = os.environ.get('FAYEZ_SECRET_KEY', '').strip()
_secret_file = os.path.join(DATA_DIR, '.fayez_secret_key')
if _secret_from_env:
    app.secret_key = _secret_from_env
else:
    try:
        if os.path.isfile(_secret_file):
            with open(_secret_file, 'r', encoding='utf-8') as _sf:
                app.secret_key = _sf.read().strip()
        else:
            _new_secret = secrets.token_urlsafe(48)
            fd = os.open(_secret_file, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(fd, 'w', encoding='utf-8') as _sf:
                _sf.write(_new_secret)
            app.secret_key = _new_secret
    except FileExistsError:
        with open(_secret_file, 'r', encoding='utf-8') as _sf:
            app.secret_key = _sf.read().strip()
    except OSError:
        # Fallback for read-only folders; set FAYEZ_SECRET_KEY in .env for
        # persistent sessions when the script folder is not writable.
        app.secret_key = secrets.token_urlsafe(48)

if not app.secret_key:
    raise RuntimeError('FAYEZ_SECRET_KEY is empty. Set a persistent secret in .env.')

SUPPORT_EMAIL = 'fayejislam56@gmail.com'
BKASH_MERCHANT_NUMBER = (os.environ.get('BKASH_MERCHANT_NUMBER', '01307313063').strip() or '01307313063')
NAGAD_MERCHANT_NUMBER = os.environ.get('NAGAD_MERCHANT_NUMBER', '').strip()
ROCKET_MERCHANT_NUMBER = os.environ.get('ROCKET_MERCHANT_NUMBER', '').strip()
HOTLINE_PHONE = '+880 1307-313063'
WHATSAPP_NUMBER = '+880 1307-313063'
CURATED_CATEGORY_SLUGS = (
    'mens-fashion','womens-fashion','kids-fashion-new','shoes-footwear','watches','mobile-phones',
    'laptops-computers','headphones-speakers','mobile-accessories','skincare','makeup-cosmetics',
    'perfumes-fragrances','personal-care-grooming','home-kitchen','furniture-home-decor',
    'cleaning-organization','groceries','snacks-chocolates','beverages','organic-natural-food',
    'sports-fitness','books-stationery','car-bike-accessories','bags-backpacks',
    'three-piece','laavish-furniture'
)

app.config['MAIL_SERVER'] = 'smtp.gmail.com'
app.config['MAIL_PORT'] = 587
app.config['MAIL_USE_TLS'] = True
app.config['MAIL_USERNAME'] = os.environ.get('MAIL_USERNAME', SUPPORT_EMAIL)
app.config['MAIL_PASSWORD'] = os.environ.get('MAIL_PASSWORD', '').replace(' ', '')
app.config['MAIL_TIMEOUT'] = 25
app.config['MAIL_SUPPRESS_SEND'] = False
app.config['MAIL_DEFAULT_SENDER'] = ('Fayez Online Shop', app.config['MAIL_USERNAME'] or SUPPORT_EMAIL)

mail = Mail(app)

# Product image uploads: files are stored locally beside the app, never as executable files.
PRODUCT_UPLOAD_DIR = os.path.join(DATA_DIR, 'static', 'uploads', 'products')
ALLOWED_PRODUCT_IMAGE_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.webp', '.gif'}
MAX_PRODUCT_IMAGE_BYTES = 8 * 1024 * 1024
os.makedirs(PRODUCT_UPLOAD_DIR, exist_ok=True)

def _save_product_image(field_name):
    uploaded = request.files.get(field_name)
    if not uploaded or not uploaded.filename:
        return None
    original = secure_filename(uploaded.filename)
    ext = os.path.splitext(original)[1].lower()
    if ext not in ALLOWED_PRODUCT_IMAGE_EXTENSIONS:
        raise ValueError('ছবি JPG, JPEG, PNG, WEBP অথবা GIF ফরম্যাটে দিন।')
    data = uploaded.stream.read(MAX_PRODUCT_IMAGE_BYTES + 1)
    if not data:
        raise ValueError('আপলোড করা ছবিটি খালি।')
    if len(data) > MAX_PRODUCT_IMAGE_BYTES:
        raise ValueError('প্রতিটি ছবি সর্বোচ্চ ৮ MB হতে পারবে।')
    # Basic file-signature validation prevents renamed non-image files being accepted.
    signatures = {
        '.jpg': (b'\xff\xd8\xff',), '.jpeg': (b'\xff\xd8\xff',),
        '.png': (b'\x89PNG\r\n\x1a\n',), '.gif': (b'GIF87a', b'GIF89a'),
        '.webp': (b'RIFF',)
    }
    if not any(data.startswith(sig) for sig in signatures[ext]):
        raise ValueError('ফাইলের ধরন ও ছবির কনটেন্ট মিলছে না।')
    if ext == '.webp' and data[8:12] != b'WEBP':
        raise ValueError('সঠিক WEBP ছবি আপলোড করুন।')
    filename = secrets.token_hex(16) + ext
    target = os.path.join(PRODUCT_UPLOAD_DIR, filename)
    with open(target, 'xb') as out:
        out.write(data)
    return '/static/uploads/products/' + filename

def _resolve_product_image(field_name, url_field, current=None, required=False):
    uploaded_path = _save_product_image(field_name)
    if uploaded_path:
        return uploaded_path
    url = (request.form.get(url_field) or '').strip()
    if url:
        if not url.startswith(('https://', 'http://')):
            raise ValueError('ছবির URL অবশ্যই http:// অথবা https:// দিয়ে শুরু হতে হবে।')
        return url
    if current:
        return current
    if required:
        raise ValueError('প্রধান পণ্যের ছবি আপলোড করুন অথবা ছবির URL দিন।')
    return None

def send_account_otp(recipient, subject, otp, purpose):
    """Send an OTP through Gmail SMTP; credentials must be supplied by the store owner."""
    username = app.config.get('MAIL_USERNAME') or ''
    password = app.config.get('MAIL_PASSWORD') or ''
    if not username or not password:
        raise RuntimeError('GMAIL_APP_PASSWORD_MISSING: .env ফাইলে MAIL_USERNAME এবং Gmail App Password হিসেবে MAIL_PASSWORD সেট করা নেই।')
    if '@' not in (recipient or ''):
        raise ValueError('OTP_RECIPIENT_INVALID: ইমেইল ঠিকানাটি সঠিক নয়।')
    # Keep the visible sender aligned with the authenticated Gmail account.
    app.config['MAIL_DEFAULT_SENDER'] = ('Fayez Online Shop', username)
    msg = Message(subject, recipients=[recipient])
    msg.body = (
        f'Fayez Online Shop - {purpose}\n\n'
        f'আপনার ৬-ডিজিটের OTP কোড: {otp}\n'
        'কোডটি ১০ মিনিটের মধ্যে ব্যবহার করুন। কাউকে এই কোড দেবেন না।'
    )
    mail.send(msg)


# SendMySMS gateway: uses the existing local .env credentials; never asks for a new key.
SENDMYSMS_ENDPOINT = os.environ.get('SMS_API_URL', 'https://sendmysms.net/api.php').strip()
SENDMYSMS_USERNAME = os.environ.get('SMS_API_USERNAME', os.environ.get('SENDMYSMS_API_USERNAME', 'fayej12')).strip()
# Owner-provided SendMySMS API key (keep this Python file private).
SENDMYSMS_API_KEY = (os.environ.get('SMS_API_KEY') or os.environ.get('SENDMYSMS_API_KEY') or '').strip()

def normalize_bd_mobile(value):
    digits = re.sub(r'\D', '', value or '')
    if digits.startswith('00880'):
        digits = digits[2:]
    if digits.startswith('8801') and len(digits) == 13:
        digits = '0' + digits[3:]
    elif len(digits) == 10 and digits.startswith('1'):
        digits = '0' + digits
    if len(digits) != 11 or not digits.startswith('01'):
        raise ValueError('সঠিক বাংলাদেশি মোবাইল নম্বর দিন (01XXXXXXXXX)।')
    return digits

def send_sms_otp(recipient, otp, purpose='অ্যাকাউন্ট যাচাই'):
    api_key = SENDMYSMS_API_KEY.strip()
    username = (os.environ.get('SMS_API_USERNAME') or os.environ.get('SENDMYSMS_API_USERNAME') or SENDMYSMS_USERNAME).strip()
    if not api_key:
        raise RuntimeError('SMS_API_KEY_MISSING: Python ফাইলের পাশের .env-এ আপনার আগে দেওয়া SMS API Key পাওয়া যায়নি।')
    phone = normalize_bd_mobile(recipient)
    message = f'Fayez Online Shop: আপনার {purpose} OTP হলো {otp}। ১০ মিনিটের মধ্যে ব্যবহার করুন। কাউকে কোডটি দেবেন না।'
    payload = urllib.parse.urlencode({'user': username, 'key': api_key, 'to': phone, 'msg': message}).encode('utf-8')
    req = urllib.request.Request(SENDMYSMS_ENDPOINT, data=payload, headers={'Content-Type':'application/x-www-form-urlencoded','Accept':'application/json'}, method='POST')
    try:
        with urllib.request.urlopen(req, timeout=25) as response:
            result = json.loads(response.read().decode('utf-8', errors='replace'))
    except Exception as exc:
        raise RuntimeError('SMS_GATEWAY_CONNECTION_ERROR: SMS সার্ভারে সংযোগ করা যায়নি।') from exc
    if str(result.get('status','')).upper() != 'OK':
        raise RuntimeError('SMS_GATEWAY_ERROR: ' + str(result.get('response') or 'SMS পাঠানো যায়নি।'))
    return True

def send_registration_otp(email, phone, otp):
    if phone:
        return send_sms_otp(phone, otp, 'রেজিস্ট্রেশন')
    return send_account_otp(email, 'Email Verification OTP - Fayez Online Shop', otp, 'ইমেইল ভেরিফিকেশন')


# SMS API key is embedded above; no .env prompt is required.

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

@app.context_processor
def inject_store_context():
    count = 0
    customer_id = session.get('customer_id')
    if customer_id:
        try:
            count = get_db().execute('SELECT COALESCE(SUM(quantity),0) FROM cart WHERE customer_id=?', (customer_id,)).fetchone()[0]
        except sqlite3.Error:
            count = 0
    return {'cart_count': int(count or 0)}

def init_db():
    with app.app_context():
        db = get_db()
        cur = db.cursor()
        
        cur.execute('''CREATE TABLE IF NOT EXISTS admins (
            id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT UNIQUE NOT NULL, password_hash TEXT NOT NULL
        )''')
        
        cur.execute('''CREATE TABLE IF NOT EXISTS customers (
            id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, email TEXT UNIQUE NOT NULL, 
            phone TEXT, password_hash TEXT NOT NULL, is_verified INTEGER DEFAULT 1
        )''')

        cur.execute('''CREATE TABLE IF NOT EXISTS categories (
            id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT UNIQUE NOT NULL, slug TEXT UNIQUE NOT NULL, image TEXT
        )''')

        cur.execute('''CREATE TABLE IF NOT EXISTS products (
            id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, sku TEXT UNIQUE NOT NULL, category_id INTEGER, 
            price REAL NOT NULL, old_price REAL, discount_percent INTEGER DEFAULT 0, stock INTEGER NOT NULL DEFAULT 0, 
            country_of_origin TEXT DEFAULT 'Bangladesh', colors TEXT DEFAULT 'Black, Blue', description TEXT, 
            image TEXT, image2 TEXT, image3 TEXT, is_flash_sale INTEGER DEFAULT 0, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (category_id) REFERENCES categories (id)
        )''')

        cur.execute('''CREATE TABLE IF NOT EXISTS reviews (
            id INTEGER PRIMARY KEY AUTOINCREMENT, product_id INTEGER, customer_name TEXT, rating INTEGER, comment TEXT, 
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (product_id) REFERENCES products (id)
        )''')

        # Safe additive migrations for existing customer databases.
        product_columns = {row['name'] for row in cur.execute('PRAGMA table_info(products)').fetchall()}
        if 'brand' not in product_columns:
            cur.execute("ALTER TABLE products ADD COLUMN brand TEXT DEFAULT ''")
        if 'source_url' not in product_columns:
            cur.execute("ALTER TABLE products ADD COLUMN source_url TEXT DEFAULT ''")
        if 'source_checked_at' not in product_columns:
            cur.execute("ALTER TABLE products ADD COLUMN source_checked_at TEXT DEFAULT ''")
        if 'sizes' not in product_columns:
            cur.execute("ALTER TABLE products ADD COLUMN sizes TEXT DEFAULT ''")
        if 'unit_type' not in product_columns:
            cur.execute("ALTER TABLE products ADD COLUMN unit_type TEXT DEFAULT ''")
        if 'unit_value' not in product_columns:
            cur.execute("ALTER TABLE products ADD COLUMN unit_value TEXT DEFAULT ''")
        if 'is_active' not in product_columns:
            cur.execute("ALTER TABLE products ADD COLUMN is_active INTEGER NOT NULL DEFAULT 1")
        review_columns = {row['name'] for row in cur.execute('PRAGMA table_info(reviews)').fetchall()}
        if 'customer_id' not in review_columns:
            cur.execute("ALTER TABLE reviews ADD COLUMN customer_id INTEGER")

        cur.execute('''CREATE TABLE IF NOT EXISTS banners (
            id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT NOT NULL, subtitle TEXT NOT NULL, 
            image_url TEXT NOT NULL, link_url TEXT NOT NULL
        )''')

        cur.execute('''CREATE TABLE IF NOT EXISTS coupons (
            id INTEGER PRIMARY KEY AUTOINCREMENT, code TEXT UNIQUE NOT NULL, discount_percent REAL NOT NULL
        )''')
        coupon_columns = {row['name'] for row in cur.execute('PRAGMA table_info(coupons)').fetchall()}
        for col, ddl in [('discount_type', "TEXT NOT NULL DEFAULT 'percent'"), ('discount_amount', 'REAL NOT NULL DEFAULT 0'), ('expires_at', 'TEXT'), ('max_uses', 'INTEGER'), ('used_count', 'INTEGER NOT NULL DEFAULT 0'), ('is_active', 'INTEGER NOT NULL DEFAULT 1')]:
            if col not in coupon_columns:
                cur.execute(f'ALTER TABLE coupons ADD COLUMN {col} {ddl}')

        cur.execute('''CREATE TABLE IF NOT EXISTS cart (
            id INTEGER PRIMARY KEY AUTOINCREMENT, customer_id INTEGER, product_id INTEGER, quantity INTEGER NOT NULL
        )''')

        cur.execute('''CREATE TABLE IF NOT EXISTS orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT, order_id TEXT UNIQUE NOT NULL, customer_id INTEGER, 
            total_amount REAL NOT NULL, delivery_charge REAL NOT NULL, discount_amount REAL DEFAULT 0.0, 
            payment_method TEXT NOT NULL, sender_phone TEXT, trx_id TEXT, division TEXT, district TEXT, upazila TEXT, shipping_address TEXT, 
            order_status TEXT DEFAULT 'Pending', created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )''')

        # Social sign-in identities are stored separately from customer passwords.
        cur.execute('''CREATE TABLE IF NOT EXISTS customer_social_accounts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            provider TEXT NOT NULL,
            provider_user_id TEXT NOT NULL,
            customer_id INTEGER NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(provider, provider_user_id),
            FOREIGN KEY(customer_id) REFERENCES customers(id)
        )''')
        order_columns = {row['name'] for row in cur.execute('PRAGMA table_info(orders)').fetchall()}
        if 'recipient_name' not in order_columns:
            cur.execute("ALTER TABLE orders ADD COLUMN recipient_name TEXT")

        cur.execute('''CREATE TABLE IF NOT EXISTS order_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT, order_id INTEGER, product_id INTEGER, product_name TEXT, quantity INTEGER NOT NULL, price REAL NOT NULL
        )''')

        # Admin credentials are created from the owner-provided FAYEZ_ADMIN_PASSWORD.

            
        if cur.execute("SELECT COUNT(*) FROM coupons").fetchone()[0] == 0:
            cur.execute("INSERT INTO coupons (code, discount_percent) VALUES (?, ?)", ('FAYEZ10', 10.0))

        # Seed up to 20 different campaign banners without deleting owner-created banners.
        banners_data = [
            ('মেগা গ্যাজেট অফার', 'নতুন হেডফোন ও অডিও গিয়ারে বিশেষ ছাড়', 'https://images.unsplash.com/photo-1505740420928-5e560c06d30e?w=1400', '/shop'),
            ('গেমিং গিয়ার জোন', 'গেমিং কিবোর্ড, মাউস ও হেডসেট কালেকশন', 'https://images.unsplash.com/photo-1593305841991-05c297ba4575?w=1400', '/shop?cat=19'),
            ('Men’s Fashion', 'প্রিমিয়াম পুরুষদের পোশাকের নতুন কালেকশন', 'https://images.unsplash.com/photo-1515886657613-9f3515b0c78f?w=1400', '/shop?cat=2'),
            ('Women’s Fashion', 'নারীদের জন্য ট্রেন্ডি ও এলিগ্যান্ট স্টাইল', 'https://images.unsplash.com/photo-1483985988355-763728e1935b?w=1400', '/shop?cat=2'),
            ('স্মার্টফোন ও অ্যাক্সেসরিজ', 'দৈনন্দিন ব্যবহারের স্মার্ট টেক পণ্য', 'https://images.unsplash.com/photo-1511707171634-5f897ff02aa9?w=1400', '/shop'),
            ('ল্যাপটপ ও কম্পিউটার', 'কাজ ও পড়াশোনার জন্য প্রয়োজনীয় ডিভাইস', 'https://images.unsplash.com/photo-1496181133206-80ce9b88a853?w=1400', '/shop'),
            ('ঘর সাজানোর কালেকশন', 'আপনার ঘরের জন্য আধুনিক ডিজাইন', 'https://images.unsplash.com/photo-1616486338812-3dadae4b4ace?w=1400', '/shop'),
            ('কিচেন এসেনশিয়ালস', 'রান্নাঘরের স্মার্ট ও দরকারি পণ্য', 'https://images.unsplash.com/photo-1556911220-e15b29be8c8f?w=1400', '/shop'),
            ('বিউটি ও স্কিন কেয়ার', 'নিজের যত্নে বেছে নিন পছন্দের পণ্য', 'https://images.unsplash.com/photo-1596462502278-27bfdc403348?w=1400', '/shop'),
            ('স্পোর্টস ও ফিটনেস', 'সক্রিয় জীবনের জন্য স্পোর্টস গিয়ার', 'https://images.unsplash.com/photo-1517836357463-d25dfeac3438?w=1400', '/shop'),
            ('ঘড়ি ও অ্যাক্সেসরিজ', 'স্টাইলের সঙ্গে সময়ের নিখুঁত সমন্বয়', 'https://images.unsplash.com/photo-1523275335684-37898b6baf30?w=1400', '/shop'),
            ('শু কালেকশন', 'প্রতিদিনের জন্য আরামদায়ক জুতা', 'https://images.unsplash.com/photo-1542291026-7eec264c27ff?w=1400', '/shop'),
            ('ব্যাগ ও ট্রাভেল', 'ভ্রমণ ও দৈনন্দিন ব্যবহারের ব্যাগ', 'https://images.unsplash.com/photo-1553062407-98eeb64c6a62?w=1400', '/shop'),
            ('বই ও স্টেশনারি', 'পড়াশোনা ও অফিসের প্রয়োজনীয় সামগ্রী', 'https://images.unsplash.com/photo-1507842217343-583bb7270b66?w=1400', '/shop'),
            ('বেবি ও টয়', 'শিশুদের জন্য আনন্দময় কালেকশন', 'https://images.unsplash.com/photo-1566004100631-35d015d6a491?w=1400', '/shop'),
            ('গ্রোসারি ও সুপারশপ', 'দৈনন্দিন প্রয়োজনীয় পণ্য এক জায়গায়', 'https://images.unsplash.com/photo-1542838132-92c53300491e?w=1400', '/shop'),
            ('অটোমোটিভ কালেকশন', 'গাড়ি ও বাইকের প্রয়োজনীয় অ্যাক্সেসরিজ', 'https://images.unsplash.com/photo-1503376780353-7e6692767b70?w=1400', '/shop'),
            ('প্রফেশনাল টুলস', 'কাজের জন্য নির্ভরযোগ্য টুলস ও হার্ডওয়্যার', 'https://images.unsplash.com/photo-1581092335397-9583fe92d232?w=1400', '/shop'),
            ('মিউজিক ও অডিও', 'সুরের সঙ্গে থাকুন আরও কাছাকাছি', 'https://images.unsplash.com/photo-1511379938547-c1f69419868d?w=1400', '/shop'),
            ('আউটডোর ও গার্ডেন', 'বাগান ও আউটডোরের জন্য প্রয়োজনীয় পণ্য', 'https://images.unsplash.com/photo-1416879595882-3373a0480b5b?w=1400', '/shop'),
            ('প্রিমিয়াম ওয়াচ কালেকশন', 'আপনার স্টাইলে যোগ হোক আভিজাত্য', 'https://images.unsplash.com/photo-1524805444758-089113d48a6d?w=1400', '/shop'),
            ('পেট কেয়ার স্পেশাল', 'প্রিয় পোষা প্রাণীর যত্নে সেরা পছন্দ', 'https://images.unsplash.com/photo-1583337130417-3346a1be7dee?w=1400', '/shop'),
            ('ফ্রেশ গ্রোসারি ডিল', 'প্রতিদিনের বাজার এখন আরও সহজ', 'https://images.unsplash.com/photo-1542838132-92c53300491e?w=1400', '/shop'),
            ('প্রিমিয়াম ফার্নিচার', 'ঘর হোক আরও সুন্দর ও আরামদায়ক', 'https://images.unsplash.com/photo-1555041469-a586c61ea9bc?w=1400', '/shop'),
            ('ক্যামেরা ও ক্রিয়েটর গিয়ার', 'আপনার প্রতিটি মুহূর্ত হোক অসাধারণ', 'https://images.unsplash.com/photo-1516035069371-29a1b244cc32?w=1400', '/shop')
        ]
        existing_titles = {r['title'] for r in cur.execute('SELECT title FROM banners').fetchall()}
        for _banner in banners_data:
            if _banner[0] not in existing_titles and cur.execute('SELECT COUNT(*) FROM banners').fetchone()[0] < 25:
                cur.execute('INSERT INTO banners (title, subtitle, image_url, link_url) VALUES (?, ?, ?, ?)', _banner)

        # The storefront's curated 30 categories. Each category has its own image URL.
        all_21_cats = [
            ("Men's Fashion", 'mens-fashion', 'https://images.unsplash.com/photo-1529139574466-a303027c1d8b?w=900&auto=format&fit=crop&q=90'),
            ("Women's Fashion", 'womens-fashion', 'https://images.unsplash.com/photo-1539109136881-3be0616acf4b?w=900&auto=format&fit=crop&q=90'),
            ("Kids' Fashion", 'kids-fashion-new', 'https://images.unsplash.com/photo-1503919005314-30d93d07d823?w=900&auto=format&fit=crop&q=90'),
            ('Shoes & Footwear', 'shoes-footwear', 'https://images.unsplash.com/photo-1542291026-7eec264c27ff?w=900&auto=format&fit=crop&q=85'),
            ('Watches', 'watches', 'https://images.unsplash.com/photo-1523275335684-37898b6baf30?w=900&auto=format&fit=crop&q=85'),
            ('Mobile Phones', 'mobile-phones', 'https://images.unsplash.com/photo-1511707171634-5f897ff02aa9?w=900&auto=format&fit=crop&q=85'),
            ('Laptops & Computers', 'laptops-computers', 'https://images.unsplash.com/photo-1496181133206-80ce9b88a853?w=900&auto=format&fit=crop&q=85'),
            ('Headphones & Speakers', 'headphones-speakers', 'https://images.unsplash.com/photo-1505740420928-5e560c06d30e?w=900&auto=format&fit=crop&q=85'),
            ('Gaming Products', 'gaming-products', 'https://images.unsplash.com/photo-1593305841991-05c297ba4575?w=900&auto=format&fit=crop&q=85'),
            ('Mobile Accessories', 'mobile-accessories', 'https://images.unsplash.com/photo-1601593346740-925612772716?w=900&auto=format&fit=crop&q=90'),
            ('Skincare', 'skincare', 'https://images.unsplash.com/photo-1601049541289-9b1b7bbbfe19?w=900&auto=format&fit=crop&q=85'),
            ('Makeup & Cosmetics', 'makeup-cosmetics', 'https://images.unsplash.com/photo-1522335789203-aabd1fc54bc9?w=900&auto=format&fit=crop&q=85'),
            ('Perfumes & Fragrances', 'perfumes-fragrances', 'https://images.unsplash.com/photo-1594035910387-fea47794261f?w=900&auto=format&fit=crop&q=85'),
            ('Hair Care', 'hair-care', 'https://images.unsplash.com/photo-1522337360788-8b13dee7a37e?w=900&auto=format&fit=crop&q=85'),
            ('Personal Care & Grooming', 'personal-care-grooming', 'https://images.unsplash.com/photo-1556229010-6c3f2c9ca5f8?w=900&auto=format&fit=crop&q=90'),
            ('Home & Kitchen', 'home-kitchen', 'https://images.unsplash.com/photo-1556911220-e15b29be8c8f?w=900&auto=format&fit=crop&q=85'),
            ('Home Appliances', 'home-appliances', 'https://images.unsplash.com/photo-1556911220-e15b29be8c8f?w=900&auto=format&fit=crop&q=90'),
            ('Kitchen Appliances', 'kitchen-appliances', 'https://images.unsplash.com/photo-1556911220-bff31c812dba?w=900&auto=format&fit=crop&q=90'),
            ('Furniture & Home Decor', 'furniture-home-decor', 'https://images.unsplash.com/photo-1555041469-a586c61ea9bc?w=900&auto=format&fit=crop&q=85'),
            ('Cleaning & Organization', 'cleaning-organization', 'https://images.unsplash.com/photo-1581578731548-c64695cc6952?w=900&auto=format&fit=crop&q=90'),
            ('Groceries', 'groceries', 'https://images.unsplash.com/photo-1542838132-92c53300491e?w=900&auto=format&fit=crop&q=85'),
            ('Snacks & Chocolates', 'snacks-chocolates', 'https://images.unsplash.com/photo-1621939514649-280e2aa2f2e4?w=900&auto=format&fit=crop&q=85'),
            ('Beverages', 'beverages', 'https://images.unsplash.com/photo-1544145945-f90425340c7e?w=900&auto=format&fit=crop&q=85'),
            ('Organic & Natural Food', 'organic-natural-food', 'https://images.unsplash.com/photo-1540420773420-3366772f4999?w=900&auto=format&fit=crop&q=85'),
            ('Baby Products', 'baby-products', 'https://images.unsplash.com/photo-1515488042361-ee00e0ddd4e4?w=900&auto=format&fit=crop&q=85'),
            ('Sports & Fitness', 'sports-fitness', 'https://images.unsplash.com/photo-1517649763962-0c623066013b?w=900&auto=format&fit=crop&q=85'),
            ('Books & Stationery', 'books-stationery', 'https://images.unsplash.com/photo-1524995997946-a1c2e315a42f?w=900&auto=format&fit=crop&q=85'),
            ('Car & Bike Accessories', 'car-bike-accessories', 'https://images.unsplash.com/photo-1503376780353-7e6692767b70?w=900&auto=format&fit=crop&q=85'),
            ('Toys & Games', 'toys-games', 'https://images.unsplash.com/photo-1515488042361-ee00e0ddd4e4?w=900&auto=format&fit=crop&q=85'),
            ('Bags & Backpacks', 'bags-backpacks', 'https://images.unsplash.com/photo-1553062407-98eeb64c6a62?w=900&auto=format&fit=crop&q=85'),
            ('Three-Piece', 'three-piece', 'https://images.unsplash.com/photo-1610030469983-98e550d6193c?w=1000&auto=format&fit=crop&q=90'),
            ('Gaming Consoles', 'gaming-consoles', 'https://images.unsplash.com/photo-1606813907291-d86efa9b94db?w=1000&auto=format&fit=crop&q=90'),
            ('PC Components', 'pc-components', 'https://images.unsplash.com/photo-1587202372775-e229f172b9d7?w=1000&auto=format&fit=crop&q=90'),
            ('Gaming Chairs & Desks', 'gaming-chairs-desks', 'https://images.unsplash.com/photo-1598550476439-6847785fcea6?w=1000&auto=format&fit=crop&q=90')
        ]
        # Remove the unwanted categories from future starter seeding as well.
        _owner_removed_slugs = {
            'home-appliances', 'kitchen-appliances', 'lighting', 'hair-care',
            'gaming-products', 'gaming-consoles', 'pc-components', 'gaming-chairs-desks',
            'toys-games', 'baby-products', 'baby-care'
        }
        all_21_cats = [item for item in all_21_cats if item[1] not in _owner_removed_slugs]
        # On a genuinely new database, create the starter categories once.
        # On an existing database, do not recreate categories the shop owner deleted.
        if cur.execute("SELECT COUNT(*) FROM categories").fetchone()[0] == 0:
            cur.executemany(
                "INSERT OR IGNORE INTO categories (name, slug, image) VALUES (?, ?, ?)",
                all_21_cats
            )
        extra_categories = []
        category_image_map = {}
        for cname, cslug in extra_categories:
            cimg = category_image_map.get(cslug, 'https://images.unsplash.com/photo-1441986300917-64674bd600d8?w=600')
            cur.execute("INSERT OR IGNORE INTO categories (name, slug, image) VALUES (?, ?, ?)", (cname, cslug, cimg))
            cur.execute("UPDATE categories SET image=? WHERE slug=?", (cimg, cslug))

        for cname, cslug, cimg in all_21_cats:
            # Update images only for categories that already exist. Do not recreate
            # categories the shop owner has intentionally deleted.
            cur.execute("UPDATE categories SET image = ? WHERE slug = ?", (cimg, cslug))
        # Internal legacy categories are retained only for the built-in sample catalogue.
        cur.execute("INSERT OR IGNORE INTO categories (name, slug, image) VALUES (?, ?, ?)", ('Legacy Gaming', 'gaming', 'https://images.unsplash.com/photo-1612287233202-b51b36619df0?w=600'))
        cur.execute("INSERT OR IGNORE INTO categories (name, slug, image) VALUES (?, ?, ?)", ('Legacy Tools', 'tools', 'https://images.unsplash.com/photo-1581092335397-9583fe92d232?w=600'))

        legacy_category_map = {
            'fashion':'mens-fashion', 'computers':'laptops-computers', 'gaming':'gaming-products',
            'electronics':'mobile-phones', 'mobile-accessories':'mobile-accessories', 'home-kitchen':'home-kitchen',
            'health-beauty':'personal-care-grooming', 'groceries':'groceries', 'sports':'sports-fitness',
            'books':'books-stationery', 'baby-toys':'baby-products', 'automotive':'car-bike-accessories',
            'watch-jewelry':'watches', 'shoes':'shoes-footwear', 'luggage':'bags-backpacks',
            'furniture':'furniture-home-decor', 'office':'books-stationery', 'tools':'home-appliances',
            'men-fashion':'mens-fashion', 'women-fashion':'womens-fashion', 'kids-fashion':'kids-fashion-new',
            'premium-accessories':'bags-backpacks', 'televisions':'home-appliances', 'audio-speakers':'headphones-speakers',
            'cameras':'laptops-computers', 'printers-scanners':'laptops-computers', 'networking':'laptops-computers',
            'smart-home':'home-appliances', 'bedding-bath':'home-kitchen', 'cleaning-supplies':'cleaning-organization',
            'personal-care':'personal-care-grooming', 'baby-care':'baby-products', 'food-snacks':'snacks-chocolates',
            'fresh-produce':'groceries', 'dairy-bakery':'groceries', 'outdoor-camping':'sports-fitness',
            'cycling':'sports-fitness', 'art-craft':'books-stationery', 'travel-accessories':'bags-backpacks',
            'car-accessories':'car-bike-accessories', 'pet-supplies':'groceries', 'pet-food':'groceries',
            'gardening':'home-kitchen', 'music':'headphones-speakers'
        }
        for old_slug, new_slug in legacy_category_map.items():
            old_row = cur.execute('SELECT id FROM categories WHERE slug=?', (old_slug,)).fetchone()
            new_row = cur.execute('SELECT id FROM categories WHERE slug=?', (new_slug,)).fetchone()
            if old_row and new_row and old_row['id'] != new_row['id']:
                cur.execute('UPDATE products SET category_id=? WHERE category_id=?', (new_row['id'], old_row['id']))

        # Daraz-referenced starter electronics catalogue. Idempotent by SKU;
        # existing products and owner data are never overwritten. Prices are
        # reference snapshots, not live-synced supplier prices. Stock remains 0
        # until the shop owner confirms actual inventory and supplier terms.
        curated_electronics = [
            {
                'sku':'FZ-DZ-SAM-A07-464', 'slug':'mobile-phones',
                'name':'Samsung Galaxy A07 4/64GB (Official Warranty)', 'brand':'Samsung',
                'price':21499, 'old_price':22299,
                'image':'https://img.drz.lazcdn.com/g/kf/Scf3a947516264a05835b230c2ef50340U.jpg_720x720q80.jpg_.webp',
                'description':'4GB RAM + 64GB storage, 6.5-inch HD+ display, 1-year brand warranty (as listed by Daraz seller). Reference price snapshot: ৳21,499. Price and availability may change. Stock must be confirmed by Fayez Online Shop before sale.',
                'url':'https://www.daraz.com.bd/products/samsung-galaxy-a07-464gb65-hd-display-i563818818.html'
            },
            {
                'sku':'FZ-DZ-LOG-G102', 'slug':'gaming-products',
                'name':'Logitech G102 LIGHTSYNC RGB Gaming Mouse', 'brand':'Logitech',
                'price':1855, 'old_price':2099,
                'image':'https://img.drz.lazcdn.com/static/bd/p/40cf0de51fd650ba3173506901e30f7b.png_720x720q80.png_.webp',
                'description':'Wired gaming mouse, LIGHTSYNC RGB lighting, 6 programmable buttons and up to 8,000 DPI gaming-grade sensor. Daraz product-page reference price: ৳1,855. Price and availability may change. Stock must be confirmed before sale.',
                'url':'https://www.daraz.com.bd/products/logitech-g102-light-sync-gaming-mouse-with-customizable-rgb-lighting-6-programmable-buttons-gaming-grade-sensor-8-k-dpi-tracking168mn-color-light-weight-i1600095226.html'
            },
            {
                'sku':'FZ-DZ-ORA-FPN', 'slug':'headphones-speakers',
                'name':'Oraimo FreePods Neo TWS Bluetooth Earbuds (OTW-330S)', 'brand':'Oraimo',
                'price':1418, 'old_price':2999,
                'image':'https://img.drz.lazcdn.com/static/bd/p/4b201e4145d119a287254786da8c96b7.png_720x720q80.png_.webp',
                'description':'True wireless earbuds, Bluetooth 5.3, built-in microphone, USB Type-C charging and rechargeable case. Daraz product-page reference price: ৳1,418. Price and availability may change. Stock must be confirmed before sale.',
                'url':'https://www.daraz.com.bd/products/otw-330s-i1585723270.html'
            },
            {
                'sku':'FZ-DZ-LOG-K120', 'slug':'laptops-computers',
                'name':'Logitech K120 Full-Size USB Keyboard (Bangla Layout)', 'brand':'Logitech',
                'price':788, 'old_price':799,
                'image':'https://img.drz.lazcdn.com/static/bd/p/72d36195de4b7e44984a042723ed3441.png_720x720q80.png_.webp',
                'description':'Full-size wired USB keyboard, Bangla layout, spill-resistant design and 3-year brand warranty as listed. Daraz reference price: ৳788; listing shows 4.9/5 from 636 ratings and 1.2K sold. Price and availability may change. Stock must be confirmed before sale.',
                'url':'https://www.daraz.com.bd/products/logitech-k120-wired-keyboard-for-windows-usb-plug-and-play-full-size-spill-resistant-curved-space-bar-pclaptop-bangla-layout-i274553920.html'
            },
            {
                'sku':'FZ-DZ-TPL-EC220G5', 'slug':'pc-components',
                'name':'TP-Link EC220-G5 V3 AC1200 Dual-Band Gigabit Wi-Fi Router', 'brand':'TP-Link',
                'price':3500, 'old_price':4000,
                'image':'https://img.drz.lazcdn.com/static/bd/p/dec58173d7228e7e25d2f1ab2471cc4d.png_720x720q80.png_.webp',
                'description':'Dual-band 2.4GHz/5GHz AC1200 Wi-Fi, four external antennas, Gigabit WAN/LAN ports and EasyMesh support. Daraz product-page reference price: ৳3,500; seller listing states 1-year brand warranty. Price and availability may change. Stock must be confirmed before sale.',
                'url':'https://www.daraz.com.bd/products/tp-link-ec220-g5-v3-ac1200-i525379240.html'
            },
        ]
        for item in curated_electronics:
            if cur.execute('SELECT 1 FROM products WHERE sku=?', (item['sku'],)).fetchone():
                continue
            cat = cur.execute('SELECT id FROM categories WHERE slug=?', (item['slug'],)).fetchone()
            if not cat:
                continue
            cur.execute("""INSERT INTO products
                (name, sku, category_id, price, old_price, discount_percent, stock, country_of_origin, colors, description, image, image2, image3, is_flash_sale, brand, source_url, source_checked_at)
                VALUES (?, ?, ?, ?, ?, ?, 0, 'Various', 'As listed', ?, ?, '', '', 0, ?, ?, '2026-11-16')""",
                (item['name'], item['sku'], cat['id'], item['price'], item['old_price'],
                 round((item['old_price']-item['price'])/item['old_price']*100) if item['old_price'] else 0,
                 item['description'] + ' Source: ' + item['url'], item['image'], item['brand'], item['url']))
        
        # Additional products from Daraz Bangladesh campaign/category listings checked on 2026-11-16.
        # Listing snapshots only: prices can change; no stock is claimed. Product photos are left
        # blank so the shop owner can upload the exact images from their own supplier listings.
        daraz_listing_products = [
            ('FZ-DZ-LST-0001','mens-fashion',"Men's Baggy Jeans Plus Size 2026 Wide Leg Denim Pants",599),
            ('FZ-DZ-LST-0002','toys-games','FLH DO1 EPP Foam RC Fighter Jet 2.4G 4-Channel Drone Toy',1455),
            ('FZ-DZ-LST-0003','home-kitchen','RFL Best Buy SS Single Wall Water Bottle 650ML',285),
            ('FZ-DZ-LST-0004','snacks-chocolates','Saad Hot Tomato Sauce 500 gm',119),
            ('FZ-DZ-LST-0005','groceries','Honey Nuts 500gm',345),
            ('FZ-DZ-LST-0006','home-appliances','GoodKnight Liquid Mosquito Repellent Refill 45ml (Pack of 2)',235),
            ('FZ-DZ-LST-0007','toys-games','Rescue Team Toy Car Set 4 in 1 (Police, Ambulance, Fire Car, Helicopter)',553),
            ('FZ-DZ-LST-0008','mobile-accessories','DJI Osmo Pocket / Pocket 3 Screen Protector Glass',248),
            ('FZ-DZ-LST-0009','toys-games','FLH GT 40 PRO Brushless RC Drone Dual Camera',6014),
            ('FZ-DZ-LST-0010','baby-products','Kids Lunch Box Cow Shape Kitchen Box',139),
            ('FZ-DZ-LST-0011','mobile-accessories','XT-02 S03/R1 Bluetooth Remote Selfie Stick with Tripod',280),
            ('FZ-DZ-LST-0012','womens-fashion','Export Quality Soft Cotton Bra Set for Women (Assorted)',63),
            ('FZ-DZ-LST-0013','mobile-accessories','Portable Mini Mobile Cooler Fan for Android & iPhone',280),
            ('FZ-DZ-LST-0014','sports-fitness','Adjustable Hand Grip Strengthener 5-60Kg',159),
            ('FZ-DZ-LST-0015','bags-backpacks','Stylish Mini Backpack 10L Lightweight Daypack',135),
            ('FZ-DZ-LST-0016','home-appliances','JYSUPER Turbo Handheld Portable Fan T-812',499),
            ('FZ-DZ-LST-0017','home-kitchen','Digital Portable Weight Scale 50Kg',326),
            ('FZ-DZ-LST-0018','womens-fashion','Magic Stick Invisible Silicone Push-Up Bra',147),
            ('FZ-DZ-LST-0019','kitchen-appliances','Electric Rechargeable Handheld Coffee Mixer',375),
            ('FZ-DZ-LST-0020','kitchen-appliances','Mini Electric Eggbeater Stainless Steel Mixer',670),
            ('FZ-DZ-LST-0021','headphones-speakers','CAT STN-28 Over-Ear Wireless Bluetooth LED Headset',423),
            ('FZ-DZ-LST-0022','mobile-accessories','AA AAA 1.2V Battery Charger 4-Slot',220),
            ('FZ-DZ-LST-0023','home-kitchen','SF-400 Digital LCD Kitchen Scale 10Kg',364),
            ('FZ-DZ-LST-0024','skincare','Beauty Glazed Blackhead Nose Pore Strips (5 pcs)',95),
            ('FZ-DZ-LST-0025','home-appliances','Lithium Rechargeable Mini Table Fan with LED Light',979),
            ('FZ-DZ-LST-0026','womens-fashion','China Linen Fabric Long Kurti with Stylish Koti',456),
            ('FZ-DZ-LST-0027','gaming-products','RGB Gaming Keyboard and Mouse Combo G21-B',975),
            ('FZ-DZ-LST-0028','mobile-accessories','USB-C 5-in-1 Multiport Hub with 4K HDMI and 100W PD',678),
            ('FZ-DZ-LST-0029','skincare',"Skin 'O Care and Repair Sunscreen SPF 50+ PA+++ 50ml",320),
            ('FZ-DZ-LST-0030','snacks-chocolates','Potato Chips (Ready to Fry) 1kg',165),
            ('FZ-DZ-LST-0031','headphones-speakers','Portable Wireless Bluetooth Speaker Multi Color',261),
            ('FZ-DZ-LST-0032','gaming-products','Mobile Gaming Fingertip Gloves (4 pcs)',285),
            ('FZ-DZ-LST-0033','shoes-footwear','Stylish Casual Sneakers for Men',470),
            ('FZ-DZ-LST-0034','books-stationery','LCD Writing Tablet 8.5 / 10 / 12 Inch',165),
            ('FZ-DZ-LST-0035','mobile-accessories','4-in-1 Mobile Adapter Charger with USB and PD Ports',184),
            ('FZ-DZ-LST-0036','womens-fashion','Fish Cut Petticoat for Women',160),
            ('FZ-DZ-LST-0037','womens-fashion','Stylish Long Linen Skirt for Women',249),
            ('FZ-DZ-LST-0038','mobile-phones','Proton RE-PowerX Feature Phone with 3000mAh Battery',1420),
            ('FZ-DZ-LST-0039','womens-fashion',"Women's 2-Piece Nightwear Set Tops & Shorts",95),
            ('FZ-DZ-LST-0040','womens-fashion','Readymade Cotton Three-Piece with Embroidery Work',699),
            ('FZ-DZ-LST-0041','gaming-consoles','FLH R36S Retro Game Console 64GB with 21000+ Games',3614),
            ('FZ-DZ-LST-0042','kitchen-appliances','8-in-1 Mini Portable Electric Sewing Machine',1229),
            ('FZ-DZ-LST-0043','personal-care-grooming','Professional Stainless Steel Lice & Nit Removal Comb',59),
            ('FZ-DZ-LST-0045','personal-care-grooming','Lavino Nourishing Lotion Intense Hydration',149),
            ('FZ-DZ-LST-0046','mens-fashion','GoodMan Premium Full Sleeve Hoodie Jacket for Men',630),
            ('FZ-DZ-LST-0047','home-appliances','VISION Twin Tub Washing Machine RE-002-SATOM 8kg',13990),
            ('FZ-DZ-LST-0048','home-appliances','CASIFY Portable Mini Room Heater',959),
            ('FZ-DZ-LST-0049','cleaning-organization','Partex 2-Ply Toilet Tissue Paper 4-Roll Value Pack',95),
            ('FZ-DZ-LST-0050','cleaning-organization','Get Out Cockroach Killing Gel 15gm',299),
        ]
        listing_sources = {
            'https://pages.daraz.com.bd/wow/gcp/route/daraz/bd/upr/router?at_iframe=1&data_prefetch=true&hybrid=1&prefetch_replace=1&wh_pid=%2Flazada%2Fmegascenario%2Fbd%2F3_3_26_bd%2Feid-campaign',
            'https://pages.daraz.com.bd/wow/gcp/route/daraz/bd/upr/router?at_iframe=1&data_prefetch=true&hybrid=1&prefetch_replace=1&wh_pid=%2Flazada%2Fmegascenario%2Fbd%2F99_ext_2026%2F99extendtopdealsfashion'
        }
        listing_source = sorted(listing_sources)[0]
        for sku, slug, name, price in daraz_listing_products:
            if cur.execute('SELECT 1 FROM products WHERE sku=?', (sku,)).fetchone():
                continue
            cat = cur.execute('SELECT id FROM categories WHERE slug=?', (slug,)).fetchone()
            if not cat:
                continue
            desc = ('Daraz Bangladesh campaign listing snapshot dated 2026-11-16. Displayed reference price: '
                    f'৳{price:,}. This is not a live price feed; seller price and availability may change. '
                    'Product image to be uploaded by Fayez Online Shop owner. Confirm supplier, exact model, '
                    'warranty and current price before accepting customer orders.')
            cur.execute("""INSERT INTO products
                (name, sku, category_id, price, old_price, discount_percent, stock, country_of_origin, colors,
                 description, image, image2, image3, is_flash_sale, brand, source_url, source_checked_at)
                VALUES (?, ?, ?, ?, NULL, 0, 0, 'As listed by seller', 'As listed by seller', ?, '', '', '', 0, '', ?, '2026-11-16')""",
                (name, sku, cat['id'], price, desc, listing_source))

        if cur.execute("SELECT COUNT(*) FROM products").fetchone()[0] == 0:
            # Use the internal legacy rows created immediately above. The public
            # gaming-products/home-appliances categories may have been intentionally removed.
            game_row = cur.execute("SELECT id FROM categories WHERE slug='gaming'").fetchone()
            tools_row = cur.execute("SELECT id FROM categories WHERE slug='tools'").fetchone()
            if not game_row or not tools_row:
                # Do not crash startup if a database has been manually customized.
                db.commit()
                return
            c_game = game_row['id']
            c_tools = tools_row['id']
            
            sample_items = []
            gaming_photos = [
              'https://images.unsplash.com/photo-1593305841991-05c297ba4575?w=600','https://images.unsplash.com/photo-1612287233202-b51b36619df0?w=600','https://images.unsplash.com/photo-1592840496694-26d035b52b48?w=600','https://images.unsplash.com/photo-1603481546238-487240415921?w=600','https://images.unsplash.com/photo-1587202372775-e229f172b9d7?w=600',
              'https://images.unsplash.com/photo-1593640408182-31c70c8268f5?w=600','https://images.unsplash.com/photo-1597872200969-2b65d56bd16b?w=600','https://images.unsplash.com/photo-1600861194942-f883de0dfe96?w=600','https://images.unsplash.com/photo-1614294149010-950b698f72c0?w=600','https://images.unsplash.com/photo-1598550476439-6847785fcea6?w=600',
              'https://images.unsplash.com/photo-1587829741301-dc798b83add3?w=600','https://images.unsplash.com/photo-1527814050087-3793815479db?w=600','https://images.unsplash.com/photo-1615663245857-ac93bb7c39e7?w=600','https://images.unsplash.com/photo-1613141411244-0e4ac259d217?w=600','https://images.unsplash.com/photo-1593118247619-e2d6f056869e?w=600',
              'https://images.unsplash.com/photo-1612287230202-1ff1d85d1bdf?w=600','https://images.unsplash.com/photo-1592840496694-26d035b52b48?w=600','https://images.unsplash.com/photo-1605901309584-818e25960a8f?w=600','https://images.unsplash.com/photo-1616588589676-62b3fe8e3e4f?w=600','https://images.unsplash.com/photo-1593508512255-86ab42a8e620?w=600',
              'https://images.unsplash.com/photo-1591488320449-011701bb6704?w=600','https://images.unsplash.com/photo-1614294149010-950b698f72c0?w=600','https://images.unsplash.com/photo-1603481546238-487240415921?w=600','https://images.unsplash.com/photo-1593305841991-05c297ba4575?w=600','https://images.unsplash.com/photo-1612287233202-b51b36619df0?w=600'
            ]
            tool_photos = [
              'https://images.unsplash.com/photo-1581092335397-9583fe92d232?w=600','https://images.unsplash.com/photo-1504148455328-c376907d081c?w=600','https://images.unsplash.com/photo-1530124566582-a618bc2615dc?w=600','https://images.unsplash.com/photo-1581147036324-c1c89c2c8b5c?w=600','https://images.unsplash.com/photo-1581783898377-1c85bf937427?w=600',
              'https://images.unsplash.com/photo-1581235720704-06d3acfcb36f?w=600','https://images.unsplash.com/photo-1586864387967-d02ef85d93e8?w=600','https://images.unsplash.com/photo-1504917595217-d4dc5ebe6122?w=600','https://images.unsplash.com/photo-1621905251918-48416bd8575a?w=600','https://images.unsplash.com/photo-1581244277943-fe4a9c777189?w=600',
              'https://images.unsplash.com/photo-1581092160562-40aa08e78837?w=600','https://images.unsplash.com/photo-1581092918056-0c4c3acf3789?w=600','https://images.unsplash.com/photo-1581092580497-e0d23cbdf1dc?w=600','https://images.unsplash.com/photo-1581092795360-fd1ca04f0952?w=600','https://images.unsplash.com/photo-1581092160607-ee22621dd758?w=600',
              'https://images.unsplash.com/photo-1530124566582-a618bc2615dc?w=600','https://images.unsplash.com/photo-1504148455328-c376907d081c?w=600','https://images.unsplash.com/photo-1586864387967-d02ef85d93e8?w=600','https://images.unsplash.com/photo-1581147036324-c1c89c2c8b5c?w=600','https://images.unsplash.com/photo-1581783898377-1c85bf937427?w=600',
              'https://images.unsplash.com/photo-1581092335397-9583fe92d232?w=600','https://images.unsplash.com/photo-1581092160562-40aa08e78837?w=600','https://images.unsplash.com/photo-1581092918056-0c4c3acf3789?w=600','https://images.unsplash.com/photo-1581244277943-fe4a9c777189?w=600','https://images.unsplash.com/photo-1504917595217-d4dc5ebe6122?w=600'
            ]
            for i in range(1, 26):
                sample_items.append((f'Gaming Pro Gear Item #{i}', f'GM-PRO-{i}', c_game, 1500.0 + i*100, 2500.0 + i*100, 20, 0, 'China', 'RGB, Black', 
                                     f'High performance gaming gear item #{i}.', gaming_photos[i-1], '', '', 1 if i <= 4 else 0))
            for i in range(1, 26):
                sample_items.append((f'Heavy Duty Hardware Tool #{i}', f'TL-HW-{i}', c_tools, 800.0 + i*50, 1200.0 + i*50, 15, 0, 'Taiwan', 'Yellow, Steel', 
                                     f'Professional grade hardware tool item #{i}.', tool_photos[i-1], '', '', 0))
            
            cur.executemany("""INSERT INTO products (name, sku, category_id, price, old_price, discount_percent, stock, country_of_origin, colors, description, image, image2, image3, is_flash_sale) 
                              VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""", sample_items)

        # Never invent or substitute product photos. Generic stock-photo URLs are
        # cleared; duplicate product image URLs are cleared from later products.
        # Category/banner editorial images remain category/banner-only.
        generic_product_hosts = ('images.unsplash.com',)
        seen_product_images = set()
        for product_row in cur.execute(
            "SELECT id, image, image2, image3 FROM products ORDER BY id"
        ).fetchall():
            used_here = set()
            updates = {}
            for image_col in ('image', 'image2', 'image3'):
                image_url = (product_row[image_col] or '').strip()
                if not image_url:
                    continue
                if any(host in image_url.lower() for host in generic_product_hosts):
                    updates[image_col] = ''
                    continue
                if image_url in seen_product_images or image_url in used_here:
                    updates[image_col] = ''
                    continue
                seen_product_images.add(image_url)
                used_here.add(image_url)
            if updates:
                cur.execute(
                    "UPDATE products SET " + ", ".join(f"{col}=?" for col in updates) + " WHERE id=?",
                    (*updates.values(), product_row['id'])
                )
        # Owner-requested category cleanup. Product records are preserved; only their
        # category assignment is cleared before these unwanted category rows are removed.
        unwanted_category_slugs = (
            'home-appliances', 'kitchen-appliances', 'lighting', 'luggage',
            'hair-care', 'gaming-products', 'toys-games', 'baby-products', 'baby-care'
        )
        unwanted_category_names = {
            'home appliances', 'kitchen appliances', 'lighting', 'hair care',
            'gaming products', 'electric gaming', 'toys & games', 'baby products', 'baby care'
        }
        unwanted_rows = cur.execute('SELECT id, name, slug FROM categories').fetchall()
        for unwanted in unwanted_rows:
            if unwanted['slug'] in unwanted_category_slugs or (unwanted['name'] or '').strip().lower() in unwanted_category_names:
                # Preserve product records; only clear their link to a removed category.
                cur.execute('UPDATE products SET category_id=NULL WHERE category_id=?', (unwanted['id'],))
                cur.execute('DELETE FROM categories WHERE id=?', (unwanted['id'],))

        db.commit()

def admin_required(f):
    @wraps(f)
    def wrap(*args, **kwargs):
        if not session.get('is_admin'):
            flash('অ্যাডমিন অ্যাক্সেস প্রয়োজন।', 'danger')
            return redirect(url_for('admin_login'))
        return f(*args, **kwargs)
    return wrap

def customer_required(f):
    @wraps(f)
    def wrap(*args, **kwargs):
        if not session.get('customer_id'):
            flash('অনুগ্রহ করে প্রথমে লগইন করুন।', 'warning')
            return redirect(url_for('customer_login'))
        return f(*args, **kwargs)
    return wrap

BASE_HTML = '''<!DOCTYPE html>
<html lang="bn">
<head>
    <meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Fayez Online Shop - Enterprise E-Commerce</title>
    <meta name="theme-color" content="#5145cd">
    <meta name="apple-mobile-web-app-capable" content="yes">
    <meta name="apple-mobile-web-app-status-bar-style" content="default">
    <meta name="apple-mobile-web-app-title" content="Fayez Shop">
    <link rel="manifest" href="/manifest.webmanifest">
    <link rel="apple-touch-icon" href="/pwa-icon-512.png">
    <link rel="icon" type="image/png" href="/pwa-icon-512.png">
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
    <style>
        :root { --primary: #101828; --accent: #6d5dfc; --ink:#172033; --muted:#667085; --surface:#ffffff; --canvas:#f5f6fa; --line:#eaecf0; --radius:22px; }
        body { font-family: Inter, -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; background: var(--canvas); color: var(--ink); letter-spacing:-.01em; }
        .container { max-width: 1320px; }
        .section-title, h1, h2, h3 { letter-spacing: -.035em; }
        .btn-primary { background: linear-gradient(120deg,#5145cd,#7968f4); border-color: transparent; box-shadow: 0 7px 18px #6255d322; }
        .btn-primary:hover { background: linear-gradient(120deg,#4035b4,#6655df); transform: translateY(-1px); }
        .product-card { border: 1px solid #edf0f5; border-radius: 18px; box-shadow: 0 5px 18px #17203308; }
        .category-box { border-radius: 18px; box-shadow: 0 5px 18px #17203308; }
        .category-box img { height: 118px; }
        .ai-cute-avatar { background: linear-gradient(135deg,#111827,#7568ef); border: 3px solid #fff; }
        @media(max-width:576px){ .category-box img { height: 92px; } .carousel-item img { height: 250px; } }
        .navbar-brand { font-weight: 800; color: var(--accent) !important; letter-spacing: 0.5px; }
        .product-card { transition: all 0.25s ease; border: none; border-radius: 14px; overflow: hidden; background: #fff; position: relative; text-decoration: none; color: inherit; display: block; }
        .product-card:hover { transform: translateY(-6px); box-shadow: 0 14px 28px rgba(0,0,0,0.09); }
        .badge-discount { background: #dc2626; color: white; font-size: 0.75rem; font-weight: 700; padding: 4px 10px; border-radius: 6px; position: absolute; top: 10px; left: 10px; z-index: 2; }
        .category-box { background: white; border-radius: 14px; overflow: hidden; border: 1px solid #e2e8f0; transition: 0.25s; text-decoration: none; color: inherit; display: block; text-align: center; padding-bottom: 10px; }
        .category-box:hover { transform: translateY(-4px); box-shadow: 0 8px 18px rgba(37,99,235,0.12); border-color: var(--accent); }
        .category-box img { width: 100%; height: 95px; object-fit: cover; }
        .carousel-item img { height: 420px; object-fit: cover; filter: brightness(0.78); }
        .feature-card { background: white; border-radius: 14px; padding: 20px; border: 1px solid #e2e8f0; transition: 0.2s; }
        .feature-card:hover { border-color: var(--accent); transform: translateY(-3px); }
        
        @keyframes floatBounce {
            0%, 100% { transform: translateY(0); }
            50% { transform: translateY(-6px); }
        }
        .ai-cute-launcher { position: fixed; bottom: 25px; right: 25px; z-index: 1050; cursor: pointer; display: flex; align-items: center; gap: 10px; animation: floatBounce 3s ease-in-out infinite; }
        .ai-cute-badge { background: white; color: #0f172a; padding: 8px 14px; border-radius: 20px; font-weight: 700; font-size: 0.85rem; box-shadow: 0 6px 20px rgba(0,0,0,0.12); border: 1px solid #e2e8f0; }
        .ai-cute-avatar { width: 64px; height: 64px; border-radius: 50%; background: linear-gradient(135deg, #3b82f6 0%, #8b5cf6 100%); padding: 3px; box-shadow: 0 8px 25px rgba(59,130,246,0.45); display: flex; align-items: center; justify-content: center; transition: 0.3s; }
        .ai-cute-avatar:hover { transform: scale(1.08); }
        .ai-cute-avatar img { width: 100%; height: 100%; border-radius: 50%; object-fit: cover; background: white; }
        
        .ai-chat-box { position: fixed; bottom: 102px; right: 25px; width: min(440px, calc(100vw - 28px)); height: min(680px, calc(100vh - 135px)); background: white; border-radius: 20px; box-shadow: 0 15px 40px rgba(0,0,0,0.18); z-index: 1050; display: none; flex-direction: column; overflow: hidden; border: 1px solid #e2e8f0; }
        .ai-chat-header { background: linear-gradient(125deg, #17152f 0%, #39317e 55%, #6958e8 100%); color: white; padding: 18px 20px; display: flex; justify-content: space-between; align-items: center; }
        .ai-chat-body { flex: 1; padding: 18px; overflow-y: auto; background: #f8fafc; font-size: 0.9rem; display: flex; flex-direction: column; gap: 10px; }
        .ai-quick-chips { padding: 11px 13px; background: #f1f5f9; display: flex; gap: 6px; overflow-x: auto; border-top: 1px solid #e2e8f0; }
        .ai-chip { background: white; border: 1px solid #d9d6f4; border-radius: 16px; padding: 7px 12px; font-size: 0.75rem; white-space: nowrap; cursor: pointer; color: #334155; transition: 0.2s; }
        .ai-chip:hover { background: #2563eb; color: white; border-color: #2563eb; }
        .ai-chat-footer { padding: 13px 14px; background: white; border-top: 1px solid #e2e8f0; display: flex; gap: 6px; }
        .msg-bubble { padding: 10px 14px; border-radius: 16px; max-width: 82%; line-height: 1.45; }
        .msg-user { background: linear-gradient(135deg, #2563eb, #4f46e5); color: white; align-self: flex-end; border-bottom-right-radius: 4px; }
        .msg-ai { background: white; color: #1e293b; align-self: flex-start; border-bottom-left-radius: 4px; border: 1px solid #e2e8f0; box-shadow: 0 2px 5px rgba(0,0,0,0.03); }

        footer { background: var(--primary); color: #94a3b8; padding: 60px 0 25px; margin-top: 70px; }
        footer h5 { color: white; font-weight: 700; margin-bottom: 18px; }
        footer a { color: #94a3b8; text-decoration: none; transition: 0.2s; }
        footer a:hover { color: white; }
        /* FAYEZ SIGNATURE DESIGN SYSTEM — consistent across every storefront page */
        .navbar{padding:.85rem 0!important;background:rgba(255,255,255,.94)!important;backdrop-filter:blur(18px);border-bottom:1px solid rgba(16,24,40,.06)}
        .navbar-brand{font-weight:900;letter-spacing:-.7px;color:#17152f!important}
        .navbar-brand i{background:linear-gradient(135deg,#7165f5,#a78bfa);color:#fff;padding:11px;border-radius:14px}
        .nav-link{color:#475467!important;font-weight:650!important}.nav-link:hover{color:var(--accent)!important}
        .btn-primary{background:linear-gradient(135deg,#6558ed,#8b5cf6)!important;border:0!important;box-shadow:0 8px 18px rgba(109,93,252,.18)}
        .btn-primary:hover{filter:brightness(1.06);transform:translateY(-1px)}
        .form-control,.form-select{border:1px solid #e4e7ec;border-radius:13px;min-height:46px;padding:.7rem .9rem;background:#fff}
        .form-control:focus,.form-select:focus{border-color:#9b91ff;box-shadow:0 0 0 .22rem rgba(109,93,252,.12)}
        .card,.feature-card{border:1px solid rgba(16,24,40,.065)!important;border-radius:var(--radius)!important;box-shadow:0 8px 28px rgba(16,24,40,.045)!important}
        .product-card{border:1px solid #edf0f5;border-radius:20px;box-shadow:0 5px 20px rgba(16,24,40,.035)}
        .product-card:hover{transform:translateY(-5px);box-shadow:0 18px 38px rgba(16,24,40,.10)}
        .category-box{border:1px solid #edf0f5;border-radius:19px;padding-bottom:13px;box-shadow:0 4px 16px rgba(16,24,40,.035)!important}
        .category-box img{height:118px;transition:transform .35s}.category-box:hover img{transform:scale(1.045)}
        .feature-card{padding:19px;background:linear-gradient(145deg,#fff,#fbfbff)}
        .carousel{border-radius:0 0 30px 30px;overflow:hidden;background:#111827}
        .carousel-item{position:relative}.carousel-item:after{content:"";position:absolute;inset:0;background:linear-gradient(90deg,rgba(13,18,36,.78),rgba(13,18,36,.34) 55%,rgba(13,18,36,.08));pointer-events:none}
        .carousel-item img{height:clamp(330px,43vw,540px);object-fit:cover;filter:none}
        .carousel-caption{z-index:2;left:9%;right:auto;bottom:18%;max-width:620px;text-align:left!important}
        .carousel-caption h1{font-size:clamp(2rem,4.4vw,4.25rem);line-height:1.06;letter-spacing:-1.8px;text-shadow:none}
        .carousel-caption p{font-size:clamp(1rem,1.5vw,1.2rem);max-width:510px;color:#e9eaf4!important}
        .carousel-indicators{z-index:3}.carousel-control-prev,.carousel-control-next{z-index:3;width:7%}
        .section-heading{font-weight:850;letter-spacing:-.8px;color:#17152f}
        .auth-shell{max-width:1040px;margin:54px auto;display:grid;grid-template-columns:1.03fr .97fr;background:#fff;border:1px solid #eaecf0;border-radius:30px;overflow:hidden;box-shadow:0 25px 80px rgba(16,24,40,.10)}
        .auth-art{padding:54px;background:radial-gradient(circle at 15% 15%,#a99fff 0,#7465ee 34%,#26224f 100%);color:#fff;display:flex;flex-direction:column;justify-content:space-between;min-height:550px;position:relative;overflow:hidden}
        .auth-art:after{content:"";position:absolute;width:360px;height:360px;border:1px solid rgba(255,255,255,.18);border-radius:50%;right:-130px;bottom:-140px;box-shadow:0 0 0 35px rgba(255,255,255,.04),0 0 0 75px rgba(255,255,255,.035)}
        .auth-art>*{position:relative;z-index:1}.auth-art h1{font-size:clamp(2rem,4vw,3.2rem);font-weight:850;letter-spacing:-1.5px;line-height:1.08}
        .auth-panel{padding:54px;display:flex;flex-direction:column;justify-content:center}.auth-panel h2{font-weight:850;letter-spacing:-1px;color:#17152f}
        .auth-panel .form-control{min-height:52px}.auth-panel .btn{min-height:52px;font-weight:750}
        footer{margin-top:85px!important;background:#11152a!important;border-radius:30px 30px 0 0}
        @media(max-width:767px){.auth-shell{display:block;margin:22px 12px;border-radius:22px}.auth-art{min-height:230px;padding:28px}.auth-art h1{font-size:2rem}.auth-panel{padding:28px}.carousel-item img{height:360px}.carousel-caption{left:8%;right:8%;bottom:12%}.carousel-caption h1{font-size:2rem}.category-box img{height:100px}.navbar form{width:100%!important}}

/* V12.6 premium storefront */
body{background:#f7f8fc;color:#151827}.navbar{padding:14px 0!important;background:rgba(255,255,255,.97)!important;border-bottom:1px solid #eceef4;box-shadow:0 8px 28px rgba(18,24,40,.045)!important}.navbar .container{gap:16px}.navbar-brand{font-size:1.55rem!important;letter-spacing:-1.2px}.navbar-brand i{background:#171b32!important;color:#fff!important;border-radius:13px;padding:10px!important}.nav-search{width:min(100%,480px)!important}.nav-search .form-control{height:48px;border-radius:14px 0 0 14px!important;background:#f6f7fb;border-color:#e9ebf2;padding-left:18px}.nav-search .btn{height:48px;border-radius:0 14px 14px 0!important;background:#6958e8!important}.navbar .btn{font-weight:700;padding:9px 16px}.cart-count-badge{display:inline-grid;place-items:center;min-width:20px;height:20px;padding:0 5px;border-radius:99px;background:#e11d48;color:#fff;font-size:.7rem;font-weight:850;vertical-align:top;margin-left:3px}
.store-hero{position:relative;margin:22px auto 0;width:min(1320px,calc(100% - 36px));border-radius:28px;overflow:hidden;background:#171b32;min-height:450px;box-shadow:0 24px 60px rgba(22,25,50,.16)}.store-hero .carousel-item{height:450px}.store-hero .carousel-item img{height:100%;width:100%;object-fit:cover;opacity:.73}.store-hero .carousel-item:after{background:linear-gradient(90deg,rgba(13,17,36,.88),rgba(13,17,36,.60) 47%,rgba(13,17,36,.06))}.store-hero .carousel-caption{left:8%;right:auto;bottom:17%;max-width:590px;text-align:left!important}.store-hero .carousel-caption .badge{background:#ffffff20!important;border:1px solid #ffffff50;color:#fff!important;font-size:.75rem;letter-spacing:1.4px}.store-hero .carousel-caption h1{font-size:clamp(2.5rem,5vw,4.7rem);font-weight:850;letter-spacing:-2.5px;line-height:1.02;margin:16px 0}.store-hero .carousel-caption p{font-size:1.08rem;line-height:1.7;color:#e5e7f1!important}.store-hero .hero-cta{background:#fff!important;color:#171b32!important;border:0!important;border-radius:12px!important;padding:14px 23px!important;font-weight:800}.store-hero .carousel-indicators{justify-content:flex-start;margin-left:8%;bottom:22px}.store-hero .carousel-indicators button{width:22px;height:4px;border:0;border-radius:5px}
.home-wrap{max-width:1320px;margin:auto;padding:0 18px}.trust-row{display:grid;grid-template-columns:repeat(4,1fr);gap:14px;margin:22px auto 54px}.trust-item{display:flex;align-items:center;gap:13px;padding:18px 20px;background:#fff;border:1px solid #eceef4;border-radius:17px}.trust-icon{width:44px;height:44px;display:grid;place-items:center;border-radius:13px;background:#f0efff;color:#6858e8;font-size:1.15rem;flex:0 0 auto}.trust-item b{display:block;font-size:.91rem;color:#171b32}.trust-item small{color:#81879a;font-size:.78rem}.home-section{margin:0 auto 58px}.section-top{display:flex;align-items:end;justify-content:space-between;margin-bottom:21px;gap:12px}.eyebrow{color:#7768e9;font-weight:800;font-size:.72rem;letter-spacing:1.6px;text-transform:uppercase;margin-bottom:7px}.section-title{font-size:clamp(1.55rem,2.7vw,2.15rem);font-weight:850;letter-spacing:-1.1px;color:#171b32;margin:0}.section-sub{color:#858b9d;margin:7px 0 0;font-size:.92rem}
.category-grid{display:grid;grid-template-columns:repeat(6,minmax(0,1fr));gap:15px}.category-box{border:1px solid #eceef4!important;border-radius:18px!important;padding:10px!important;background:#fff;box-shadow:none!important;transition:.25s;min-height:160px}.category-box img{height:112px!important;border-radius:12px;object-fit:cover}.category-box h6{font-size:.85rem!important;font-weight:750!important;color:#282d40!important;margin-top:12px!important}.category-box:hover{transform:translateY(-5px);border-color:#c9c2ff!important;box-shadow:0 16px 32px rgba(43,39,95,.08)!important}
.deal-panel{background:linear-gradient(115deg,#211c48,#5144a7);border-radius:24px;padding:28px;color:#fff;overflow:hidden;position:relative}.deal-panel .section-title{color:#fff}.deal-panel .section-sub{color:#d9d5f7}.product-grid{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:18px}.product-card{border:1px solid #eceef4!important;border-radius:19px!important;box-shadow:none!important;overflow:hidden;background:#fff;transition:.25s}.product-card:hover{transform:translateY(-6px);box-shadow:0 18px 40px rgba(20,25,55,.10)!important;border-color:#d9d5ff!important}.product-card .card-img-top{height:220px!important;object-fit:contain!important;background:#f7f8fb;padding:15px}.product-card .card-body{padding:16px!important}.product-card h6{white-space:normal!important;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden;min-height:40px;line-height:1.4}.product-card .btn{border-radius:10px!important;font-size:.82rem;font-weight:750}.badge-discount{border-radius:8px!important;top:12px!important;left:12px!important}.home-empty{background:#fff;border:1px dashed #d8dbea;border-radius:18px;padding:36px;text-align:center;color:#7a8093}.search-head{background:#fff;border:1px solid #eceef4;border-radius:20px;padding:24px;margin-bottom:24px}
@media(max-width:991px){.trust-row{grid-template-columns:repeat(2,1fr)}.category-grid{grid-template-columns:repeat(4,minmax(0,1fr))}.product-grid{grid-template-columns:repeat(3,minmax(0,1fr))}.nav-search{width:100%!important}}
@media(max-width:600px){.store-hero{width:calc(100% - 20px);margin-top:10px;border-radius:19px;min-height:390px}.store-hero .carousel-item{height:390px}.store-hero .carousel-caption{left:7%;right:7%;bottom:15%}.store-hero .carousel-caption h1{font-size:2.25rem;letter-spacing:-1.3px}.store-hero .carousel-caption p{font-size:.9rem}.trust-row{gap:9px;margin:14px auto 38px}.trust-item{padding:12px;gap:9px}.trust-icon{width:36px;height:36px}.trust-item b{font-size:.78rem}.trust-item small{font-size:.68rem}.category-grid{grid-template-columns:repeat(3,minmax(0,1fr));gap:9px}.category-box{min-height:135px;padding:7px!important}.category-box img{height:88px!important}.category-box h6{font-size:.72rem!important}.product-grid{grid-template-columns:repeat(2,minmax(0,1fr));gap:10px}.product-card .card-img-top{height:155px!important;padding:9px}.product-card .card-body{padding:11px!important}.deal-panel{padding:20px}.section-top{align-items:start}.home-wrap{padding:0 10px}}


        /* Fayez intelligent search - original storefront styling */
        .fayez-search .input-group{border:2px solid #e5e7ef;border-radius:14px;overflow:hidden;background:#fff;transition:.18s}
        .fayez-search:focus-within .input-group{border-color:#6558df;box-shadow:0 0 0 4px rgba(101,88,223,.12)}
        .fayez-search .form-control{border:0!important;box-shadow:none!important;background:#fff!important;min-width:0}
        .fayez-search .btn{border-radius:0!important;min-width:52px}
        .fayez-suggest{position:absolute;z-index:3000;top:calc(100% + 9px);left:0;right:0;background:#fff;border:1px solid #e7e9f0;border-radius:16px;box-shadow:0 22px 55px rgba(20,24,48,.18);overflow:hidden;max-height:min(70vh,520px);overflow-y:auto}
        .fayez-suggest-head{padding:11px 15px;background:#f8f8fc;color:#777d90;font-size:.72rem;font-weight:800;letter-spacing:.08em;text-transform:uppercase}
        .fayez-suggest-item{display:flex;align-items:center;gap:12px;padding:10px 14px;color:#20243a;text-decoration:none;border-top:1px solid #f0f1f5}
        .fayez-suggest-item:hover,.fayez-suggest-item.active{background:#f5f4ff;color:#28205f}
        .fayez-suggest-item img{width:48px;height:48px;object-fit:contain;background:#f7f8fb;border-radius:9px;flex:0 0 auto}
        .fayez-suggest-item .meta{min-width:0;flex:1}.fayez-suggest-item .name{font-size:.88rem;font-weight:750;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.fayez-suggest-item .sub{font-size:.75rem;color:#858a9a}.fayez-suggest-item .price{font-weight:800;color:#30266f;white-space:nowrap;font-size:.86rem}
        .fayez-suggest-foot{padding:11px 15px;background:#fbfbfd;color:#6257ce;font-weight:750;font-size:.82rem;text-align:center}.fayez-search .form-control::placeholder{color:#8990a2}.fayez-search .btn{min-width:58px}.fayez-suggest-item:focus{outline:2px solid #6958e8;outline-offset:-2px}
        .search-layout{display:grid;grid-template-columns:minmax(0,1fr);gap:16px}.search-filters{background:#fff;border:1px solid #e9ebf1;border-radius:16px;padding:18px;height:auto;position:static}.search-filters label{font-size:.85rem;font-weight:700}.search-filters form{display:grid;grid-template-columns:1.15fr .9fr 1fr 1fr auto auto;gap:12px;align-items:end}.search-filters .form-control,.search-filters .form-select{min-height:44px;border-radius:11px}.sr-head{box-shadow:0 12px 32px rgba(40,35,100,.12)}.search-filters .sr-filter-group{border:0;padding:0;min-width:0}.search-filters .sr-filter-title{margin:0 0 10px}.search-filters .btn{white-space:nowrap}.search-filters .form-control,.search-filters .form-select{font-size:.88rem}.search-toolbar{display:flex;justify-content:space-between;align-items:center;gap:12px;flex-wrap:wrap;background:#fff;border:1px solid #e9ebf1;border-radius:14px;padding:13px 16px;margin-bottom:16px}
        @media(max-width:767px){.fayez-search{width:100%!important}.fayez-suggest{position:fixed;left:10px;right:10px;top:145px}.search-layout{grid-template-columns:1fr}.search-filters{position:static}.search-filters form{grid-template-columns:1fr 1fr}.search-filters form>.sr-filter-title{grid-column:1/-1}.search-filters form>.sr-filter-group:first-of-type{grid-column:1/-1}.search-filters form>.btn{width:100%}.search-toolbar{align-items:stretch}}
        @media print { .no-print { display: none !important; } }
    .ai-chat-box{border-radius:24px;box-shadow:0 24px 75px rgba(20,18,55,.28);border:1px solid #dedbf8}.ai-chat-header small{display:block;margin-top:5px}.ai-chat-header .ai-status{font-size:.72rem;color:#d7fbe8}.ai-chat-body{background:linear-gradient(180deg,#f7f7ff,#f8fafc)}.ai-quick-chips{flex-wrap:wrap;max-height:112px;overflow-y:auto}.ai-chip{font-weight:700}.ai-chat-footer .form-control{height:44px;border:1px solid #dedcf0}.ai-chat-footer .btn{width:44px!important;height:44px!important;background:#6958e8;border:0}.ai-feature-note{font-size:.73rem;color:#6f6b91;padding:0 15px 10px;background:#f1f0fb}@media(max-width:520px){.ai-chat-box{right:10px;bottom:86px;width:calc(100vw - 20px);height:calc(100dvh - 105px);max-height:690px}.ai-cute-launcher{right:14px;bottom:14px}.ai-cute-avatar{width:58px;height:58px}}
    .collection-grid{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:16px}.collection-tile{height:250px;position:relative;overflow:hidden;border-radius:20px;display:block;color:#fff;text-decoration:none;background:#20243a;box-shadow:0 12px 28px rgba(20,25,50,.12)}.collection-tile:after{content:"";position:absolute;inset:0;background:linear-gradient(0deg,rgba(10,14,30,.88),rgba(10,14,30,.03) 78%)}.collection-tile img{width:100%;height:100%;object-fit:cover;transition:transform .45s}.collection-tile:hover img{transform:scale(1.06)}.collection-tile span{position:absolute;z-index:1;left:18px;right:14px;bottom:17px;display:flex;flex-direction:column;gap:5px}.collection-tile small{font-size:.66rem;letter-spacing:1.4px;font-weight:800;color:#dedbff}.collection-tile b{font-size:1.18rem;line-height:1.2}.collection-tile em{font-style:normal;font-size:.82rem;color:#fff;margin-top:4px}.collection-tile em i{margin-left:5px}.category-box img{background:#f1f3f8;transition:transform .35s}.category-box:hover img{transform:scale(1.045)}@media(max-width:900px){.collection-grid{grid-template-columns:repeat(2,minmax(0,1fr))}}@media(max-width:520px){.collection-grid{gap:10px}.collection-tile{height:190px;border-radius:15px}.collection-tile span{left:12px;bottom:12px}.collection-tile b{font-size:1rem}}

        /* FAYEZ LUXURY REFRESH — warm ivory / cream / champagne, mobile first */
        :root{--primary:#273b32;--accent:#b99558;--ink:#282820;--muted:#77746b;--surface:#fffefa;--canvas:#f7f4ec;--line:#e9e2d5;--radius:18px}
        html{scroll-behavior:smooth} body{background:#faf8f2;color:#302f29;font-family:Inter,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}
        .navbar{background:rgba(255,254,250,.97)!important;border-bottom:1px solid #eee7da!important;box-shadow:0 3px 18px #51452a0a;padding:.55rem 0!important}
        .navbar-brand{color:#26392f!important;font-weight:850;letter-spacing:.1px}.navbar-brand i{background:linear-gradient(135deg,#d8c49b,#ad8a4d)!important;color:#fff!important;border-radius:12px}
        .nav-link{color:#4c5148!important;font-weight:650!important}.nav-link:hover{color:#a78349!important}
        .btn-primary{background:linear-gradient(135deg,#b99860,#967441)!important;border:0!important;color:#fff!important;box-shadow:0 6px 16px #9a79402b!important}
        .btn-primary:hover{filter:brightness(1.04);transform:translateY(-1px)}
        .btn-outline-primary{color:#947344!important;border-color:#c6ad7e!important}.btn-outline-primary:hover{background:#b99860!important;color:white!important}
        .form-control,.form-select{border-color:#e6dfd2!important;border-radius:12px!important;background:#fffefa!important}.form-control:focus,.form-select:focus{border-color:#c4a66d!important;box-shadow:0 0 0 .2rem #c4a66d22!important}
        .card,.feature-card{background:#fffefa!important;border:1px solid #eee7db!important;border-radius:18px!important;box-shadow:0 7px 24px #4a3d2609!important}
        .product-card{background:#fffefa!important;border:1px solid #eee8dd!important;border-radius:16px!important;box-shadow:0 5px 18px #4a3d260a!important}
        .product-card:hover{box-shadow:0 13px 28px #4a3d2618!important;border-color:#d9c7a5!important}
        .product-card .text-primary,.product-card .price,.section-title{color:#34483a!important}
        .category-box{background:#fffefa!important;border:1px solid #eee6d8!important;border-radius:16px!important;box-shadow:0 4px 16px #4a3d2609!important}
        .category-box:hover{border-color:#c5aa77!important}.category-box img{background:#f3eee4}
        .carousel{border-radius:0 0 22px 22px!important;background:#e9e0d0!important}
        .carousel-item:after{background:linear-gradient(90deg,rgba(37,48,39,.68),rgba(37,48,39,.23) 60%,rgba(37,48,39,.03))!important}
        .carousel-caption h1{font-family:Georgia,'Times New Roman',serif!important;font-weight:600!important;letter-spacing:-.7px!important}
        .carousel-caption p{color:#fffaf0!important}
        .section-heading{color:#2d4034!important;font-family:Georgia,'Times New Roman',serif!important;font-weight:700!important}
        footer{background:#26382f!important;color:#e9e2d5!important;border-radius:22px 22px 0 0!important}footer h5{color:#fffaf0!important}footer a{color:#d6cbb8!important}
        .badge-discount{background:#a66d50!important;border-radius:20px!important}
        @media(max-width:767px){
          .container{padding-left:13px!important;padding-right:13px!important}
          .navbar{padding:.42rem 0!important}.navbar-brand{font-size:1rem!important}.navbar-brand i{padding:8px!important;border-radius:10px!important}
          .nav-link{font-size:.84rem!important;padding:.42rem .5rem!important}
          .carousel{border-radius:0 0 16px 16px!important}.carousel-item img{height:255px!important;min-height:255px!important;object-fit:cover!important}
          .carousel-caption{left:6%!important;right:6%!important;bottom:9%!important}.carousel-caption h1{font-size:1.65rem!important;line-height:1.12!important}.carousel-caption p{font-size:.82rem!important;line-height:1.35!important;margin:.35rem 0 .65rem!important}.carousel-caption .btn{font-size:.8rem!important;padding:.48rem .85rem!important}
          .carousel-indicators{margin-bottom:.45rem!important}.carousel-control-prev,.carousel-control-next{width:9%!important}
          .section-heading{font-size:1.28rem!important}.category-box{border-radius:13px!important;padding-bottom:8px!important}.category-box img{height:82px!important}.category-box h6,.category-box .fw-bold{font-size:.78rem!important;margin:.35rem 0!important}
          .product-card{border-radius:13px!important}.product-card img{max-height:155px!important;object-fit:contain!important}.product-card .card-body{padding:.65rem!important}.product-card h6,.product-card .nm{font-size:.82rem!important;line-height:1.3!important}.product-card .btn{font-size:.76rem!important;padding:.42rem .55rem!important}
          .feature-card{padding:12px!important}.ai-cute-launcher{right:12px!important;bottom:14px!important}.ai-cute-avatar{width:49px!important;height:49px!important}.ai-cute-badge{font-size:.72rem!important;padding:6px 9px!important}
          footer{margin-top:35px!important;border-radius:16px 16px 0 0!important;padding:34px 0 18px!important}
        }


        /* FAYEZ NAVIGATION UX UPDATE — sticky desktop header + always-accessible mobile controls */
        html{scroll-padding-top:92px}
        .navbar.sticky-top{position:sticky!important;top:0;z-index:1040!important}
        .navbar .container{min-height:66px}
        .mobile-search-wrap,.mobile-bottom-nav{display:none}
        .navbar .navbar-collapse{min-width:0}
        .navbar .nav-link{white-space:nowrap}
        @media(max-width:991.98px){
          body{padding-bottom:82px!important}
          .navbar.sticky-top{top:0!important}
          .navbar .container{gap:8px;flex-wrap:wrap}
          .navbar-brand{margin-right:auto!important}
          .navbar-toggler{border:1px solid #e7e1d5!important;border-radius:10px!important;padding:7px 10px!important}
          .navbar-collapse{flex-basis:100%;width:100%;padding:8px 2px 12px}
          .navbar-collapse .navbar-nav{align-items:stretch!important;gap:3px}
          .navbar-collapse .nav-link{padding:10px 12px!important;border-radius:10px}
          .navbar-collapse .nav-link:hover{background:#f5f1e8}
          .navbar-collapse .nav-search{width:100%!important;max-width:none!important;margin:8px 0 12px!important}
          .navbar-collapse .navbar-nav:last-child{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:7px}
          .navbar-collapse .navbar-nav:last-child .nav-item{margin:0!important}
          .navbar-collapse .navbar-nav:last-child .btn{width:100%;min-height:40px;display:flex;align-items:center;justify-content:center}
          .mobile-search-wrap{display:block;position:sticky;top:66px;z-index:1035;background:rgba(250,248,242,.97);backdrop-filter:blur(12px);padding:8px 12px 10px;border-bottom:1px solid #eee7da}
          .navbar:has(#navContent.show) + .mobile-search-wrap{position:relative;top:auto}
          .mobile-search-form{width:100%;max-width:760px;margin:0 auto}
          .mobile-search-form .input-group{border:1px solid #e7dfd0;border-radius:13px;overflow:hidden;background:#fffefa;box-shadow:0 4px 14px #51452a0a}
          .mobile-search-form .form-control{height:44px;border:0!important;min-width:0}
          .mobile-search-form .btn{min-width:50px;border-radius:0!important}
          .mobile-bottom-nav{display:grid;grid-template-columns:repeat(5,minmax(0,1fr));position:fixed;left:0;right:0;bottom:0;z-index:1090;padding:7px 5px calc(7px + env(safe-area-inset-bottom));background:rgba(255,254,250,.98);backdrop-filter:blur(16px);border-top:1px solid #e9e2d5;box-shadow:0 -8px 25px rgba(38,48,39,.09)}
          .mobile-bottom-link{display:flex;flex-direction:column;align-items:center;justify-content:center;gap:4px;min-width:0;min-height:54px;color:#62685e;text-decoration:none;font-size:.68rem;font-weight:750;line-height:1.1}
          .mobile-bottom-link i{font-size:1.12rem;color:#9a7b47}
          .mobile-bottom-link:active,.mobile-bottom-link:focus{color:#26392f;background:#f5f0e6;border-radius:11px}
          .ai-cute-launcher{bottom:92px!important}
          #fayezInstallBtn{bottom:92px!important}
        }
        @media(min-width:992px){
          .mobile-search-wrap,.mobile-bottom-nav{display:none!important}
          .navbar.sticky-top{position:sticky!important}
        }
        @media(max-width:420px){
          .mobile-search-wrap{top:60px;padding:7px 9px 8px}
          .mobile-search-form .form-control{height:42px;font-size:.9rem}
          .mobile-bottom-link{font-size:.62rem}
          .mobile-bottom-link i{font-size:1.05rem}
        }

        /* FAYEZ AMAZON-INSPIRED PROFESSIONAL HEADER — visual polish only; existing routes and features stay intact. */
        .bg-dark.text-white.text-center.py-2.small.no-print{
          background:linear-gradient(100deg,#111827 0%,#202b43 55%,#111827 100%)!important;
          color:#f8fafc!important;font-size:.79rem!important;letter-spacing:.12px;
          padding:9px 12px!important;border-bottom:1px solid rgba(255,255,255,.08)
        }
        .bg-dark.text-white.text-center.py-2.small.no-print .text-warning{color:#ffc247!important}
        .navbar.sticky-top{
          background:rgba(255,255,255,.97)!important;backdrop-filter:blur(18px);
          border-bottom:1px solid #e8ebf1!important;box-shadow:0 8px 28px rgba(17,24,39,.075)!important;
          padding:10px 0!important
        }
        .navbar .container{gap:18px;min-height:70px}
        .navbar-brand{display:inline-flex;align-items:center;white-space:nowrap;color:#17243b!important;
          font-size:1.42rem!important;font-weight:900!important;letter-spacing:-1.05px!important}
        .navbar-brand i{background:linear-gradient(135deg,#17243b,#344765)!important;color:#ffc247!important;
          border-radius:13px!important;padding:11px!important;box-shadow:0 5px 14px rgba(23,36,59,.16)}
        .navbar .navbar-nav{gap:3px}
        .navbar .nav-link{color:#344054!important;font-size:.91rem;font-weight:750!important;
          padding:11px 12px!important;border-radius:11px;transition:background .18s ease,color .18s ease,transform .18s ease}
        .navbar .nav-link:hover,.navbar .nav-link:focus{color:#17243b!important;background:#f3f5f8;transform:translateY(-1px)}
        .navbar .nav-link i{color:#64748b}
        .navbar .nav-search{width:min(39%,520px)!important;max-width:520px;margin-left:auto!important;margin-right:auto!important}
        .navbar .nav-search .input-group{border:2px solid #e6a928;border-radius:13px;overflow:hidden;background:#fff;
          box-shadow:0 3px 12px rgba(23,36,59,.055);transition:box-shadow .2s,border-color .2s}
        .navbar .nav-search .input-group:focus-within{border-color:#d99508;box-shadow:0 0 0 4px rgba(245,178,45,.16)}
        .navbar .nav-search .form-control{height:46px;min-height:46px;border:0!important;border-radius:0!important;
          box-shadow:none!important;background:#fff!important;padding-left:15px!important;font-size:.9rem}
        .navbar .nav-search .btn{height:46px;min-width:54px;border:0!important;border-radius:0!important;
          background:linear-gradient(135deg,#f8c34e,#efa91c)!important;color:#17243b!important;box-shadow:none!important}
        .navbar .nav-search .btn:hover{filter:brightness(.97)}
        .navbar .navbar-nav .btn{font-size:.84rem;font-weight:800;padding:9px 14px!important;white-space:nowrap}
        .navbar .btn-outline-primary{color:#24344f!important;border:1px solid #cbd3df!important;background:#fff!important}
        .navbar .btn-outline-primary:hover{background:#f3f5f8!important;border-color:#9aa8bb!important}
        .navbar .btn-primary{background:linear-gradient(135deg,#17243b,#344765)!important;color:#fff!important;
          border:1px solid #17243b!important;box-shadow:0 5px 13px rgba(23,36,59,.16)!important}
        .navbar .btn-danger{background:#fff!important;color:#b42318!important;border:1px solid #f1c5c1!important}
        .navbar .btn-danger:hover{background:#fff5f4!important}
        .cart-count-badge{background:#f2ad27!important;color:#17243b!important;font-weight:900!important;
          box-shadow:0 0 0 2px #fff;margin-left:4px}
        .mobile-search-wrap{background:rgba(255,255,255,.98)!important;border-bottom:1px solid #e8ebf1!important;
          box-shadow:0 5px 16px rgba(17,24,39,.045)}
        .mobile-search-form .input-group{border:2px solid #e6a928!important;border-radius:12px!important;
          box-shadow:0 3px 12px rgba(23,36,59,.05)!important}
        .mobile-search-form .btn{background:linear-gradient(135deg,#f8c34e,#efa91c)!important;color:#17243b!important}
        .mobile-bottom-nav{background:rgba(255,255,255,.985)!important;border-top:1px solid #e6eaf0!important;
          box-shadow:0 -8px 26px rgba(17,24,39,.09)!important}
        .mobile-bottom-link{color:#596579!important}
        .mobile-bottom-link i{color:#344765!important}
        .mobile-bottom-link:active,.mobile-bottom-link:focus{color:#17243b!important;background:#fff7e6!important}
        .navbar-toggler{border:1px solid #d8dee8!important;border-radius:11px!important}
        @media(max-width:991.98px){
          .navbar .container{min-height:58px;gap:8px}
          .navbar-brand{font-size:1.2rem!important}
          .navbar-brand i{padding:9px!important}
          .navbar-collapse{background:#fff;border-top:1px solid #edf0f4;margin-top:8px}
          .navbar-collapse .navbar-nav .nav-link{padding:11px 13px!important}
          .navbar-collapse .navbar-nav:last-child{grid-template-columns:repeat(2,minmax(0,1fr))!important}
          .navbar-collapse .nav-search{width:100%!important;max-width:none!important}
        }
        @media(min-width:992px){
          .navbar .navbar-collapse{align-items:center}
          .navbar .navbar-nav.align-items-center{gap:2px}
        }
        @media(max-width:420px){
          .bg-dark.text-white.text-center.py-2.small.no-print{font-size:.69rem!important;padding:8px 7px!important}
          .navbar-brand{font-size:1.08rem!important}
        }

        /* FAYEZ MOBILE-FIRST NAVIGATION — keep every key destination visible without opening a menu. */
        @media(max-width:991.98px){
          body{padding-bottom:calc(76px + env(safe-area-inset-bottom))!important;overflow-x:hidden}
          .bg-dark.text-white.text-center.py-2.small.no-print{
            white-space:normal!important;line-height:1.35!important;text-align:center!important;
            font-size:clamp(.65rem,2.7vw,.78rem)!important;padding:7px 9px!important
          }
          .navbar.sticky-top{position:relative!important;top:auto!important;padding:7px 0!important}
          .navbar .container{display:flex!important;align-items:center!important;gap:7px!important;
            min-height:0!important;padding-left:10px!important;padding-right:10px!important}
          .navbar-brand{font-size:clamp(1rem,4.8vw,1.2rem)!important;letter-spacing:-.55px!important;
            margin:0!important;max-width:calc(100% - 8px);white-space:nowrap!important}
          .navbar-brand i{font-size:.9em!important;padding:8px!important;margin-right:6px!important}
          /* The mobile menu is intentionally expanded: no important link is hidden behind a hamburger. */
          .navbar-toggler{display:none!important}
          #navContent,.navbar-collapse{
            display:flex!important;visibility:visible!important;flex:1 0 100%!important;
            flex-direction:column!important;align-items:stretch!important;width:100%!important;
            max-height:none!important;overflow:visible!important;border:0!important;
            background:transparent!important;margin:0!important;padding:5px 0 2px!important
          }
          .navbar .container{flex-wrap:wrap!important}
          #navContent .navbar-nav:first-of-type{
            display:flex!important;flex-direction:row!important;flex-wrap:wrap!important;
            align-items:stretch!important;gap:5px!important;width:100%!important;margin:0!important
          }
          #navContent .navbar-nav:first-of-type .nav-item{flex:1 1 auto!important;min-width:0!important;margin:0!important}
          #navContent .navbar-nav:first-of-type .nav-link{
            display:flex!important;align-items:center!important;justify-content:center!important;
            min-height:38px!important;padding:7px 9px!important;font-size:.78rem!important;
            white-space:normal!important;text-align:center!important;background:#f4f6f9!important;
            border:1px solid #e8edf3!important;border-radius:10px!important
          }
          #navContent .nav-search{
            order:2!important;display:block!important;flex:1 0 100%!important;
            width:100%!important;max-width:none!important;margin:7px 0!important
          }
          #navContent .nav-search .input-group{width:100%!important;min-width:0!important}
          #navContent .nav-search .form-control{
            min-width:0!important;width:1%!important;flex:1 1 auto!important;
            height:44px!important;min-height:44px!important;font-size:16px!important;
            padding:9px 11px!important
          }
          #navContent .nav-search .form-control::placeholder{font-size:.8rem!important}
          #navContent .nav-search .btn{height:44px!important;min-width:48px!important}
          #navContent .navbar-nav:last-child{
            order:3!important;display:grid!important;grid-template-columns:repeat(2,minmax(0,1fr))!important;
            gap:6px!important;width:100%!important;margin:0!important;padding:0!important;
            align-items:stretch!important
          }
          #navContent .navbar-nav:last-child .nav-item{min-width:0!important;margin:0!important}
          #navContent .navbar-nav:last-child .nav-link,
          #navContent .navbar-nav:last-child .btn{
            display:flex!important;align-items:center!important;justify-content:center!important;
            width:100%!important;min-width:0!important;min-height:40px!important;
            padding:7px 8px!important;margin:0!important;font-size:.78rem!important;
            line-height:1.2!important;white-space:normal!important;text-align:center!important;
            overflow-wrap:anywhere!important;border-radius:10px!important
          }
          #navContent .navbar-nav:last-child .btn{font-weight:800!important}
          #navContent .navbar-nav:last-child .btn-outline-primary,
          #navContent .navbar-nav:last-child .btn-primary,
          #navContent .navbar-nav:last-child .btn-danger{box-shadow:none!important}
          /* Do not show a second search field; the full-width main search stays visible above. */
          .mobile-search-wrap{display:none!important}
          .mobile-bottom-nav{
            display:grid!important;grid-template-columns:repeat(5,minmax(0,1fr))!important;
            padding:6px 4px calc(6px + env(safe-area-inset-bottom))!important
          }
          .mobile-bottom-link{min-height:50px!important;font-size:clamp(.61rem,2.4vw,.7rem)!important}
          .mobile-bottom-link span{white-space:nowrap!important}
          .ai-cute-launcher{bottom:calc(82px + env(safe-area-inset-bottom))!important}
          #fayezInstallBtn{bottom:calc(82px + env(safe-area-inset-bottom))!important}
        }
        @media(max-width:360px){
          .navbar-brand{font-size:1rem!important}
          #navContent .navbar-nav:first-of-type .nav-link{font-size:.72rem!important;padding:6px 6px!important}
          #navContent .navbar-nav:last-child .btn,
          #navContent .navbar-nav:last-child .nav-link{font-size:.72rem!important;padding:6px 5px!important}
          .bg-dark.text-white.text-center.py-2.small.no-print{font-size:.64rem!important}
        }
        @media(min-width:992px){
          .navbar-toggler{display:none!important}
        }

        </style>
</head>
<body>
    <div class="bg-dark text-white text-center py-2 small no-print">
        <i class="fa fa-truck-fast me-2 text-warning"></i> সারা দেশে দ্রুত হোম ডেলিভারি ও বিকাশ/নগদ/COD সুবিধা! হটলাইন: +880 1307-313063
    </div>

    <nav class="navbar navbar-expand-lg navbar-light bg-white sticky-top shadow-sm no-print">
        <div class="container">
            <a class="navbar-brand fs-3" href="/"><i class="fa fa-bag-shopping me-2"></i>FAYEZ SHOP</a>
            <button class="navbar-toggler" type="button" data-bs-toggle="collapse" data-bs-target="#navContent">
                <span class="navbar-toggler-icon"></span>
            </button>
            <div class="collapse navbar-collapse" id="navContent">
                <ul class="navbar-nav me-auto mb-2 mb-lg-0">
                    <li class="nav-item"><a class="nav-link fw-semibold active" href="/"><i class="fa fa-home me-1"></i> হোম</a></li>
                    <li class="nav-item"><a class="nav-link fw-semibold" href="/shop"><i class="fa fa-store me-1"></i> সকল পণ্য</a></li>
                    <li class="nav-item"><a class="nav-link fw-semibold" href="/track"><i class="fa fa-map-location-dot me-1"></i> ট্র্যাকিং</a></li>
                </ul>
                <form class="d-flex mx-auto my-2 my-lg-0 nav-search fayez-search" action="/shop" method="GET" autocomplete="off" style="width: 34%; position:relative">
                    <div class="input-group">
                        <input id="fayezSearchInput" class="form-control ps-3" type="search" name="q" role="combobox" aria-autocomplete="list" aria-expanded="false" aria-controls="fayezSearchSuggest" placeholder="পণ্যের নাম, ব্র্যান্ড, মডেল বা SKU লিখুন..." value="{{ request.args.get('q', '') }}">
                        <button class="btn btn-primary px-3" type="submit" aria-label="সার্চ"><i class="fa fa-search"></i></button>
                    </div>
                    <div id="fayezSearchSuggest" class="fayez-suggest" role="listbox" hidden></div>
                </form>
                <ul class="navbar-nav align-items-center ms-auto">
                    <li class="nav-item me-2"><a class="nav-link fw-semibold" href="/support"><i class="fa fa-headset me-1"></i>সাপোর্ট</a></li>
                    <li class="nav-item me-3"><a class="nav-link fw-semibold position-relative" href="/cart"><i class="fa fa-shopping-cart fa-lg text-primary"></i> কার্ট <span class="cart-count-badge">{{ cart_count }}</span></a></li>
                    {% if session.get('customer_id') %}
                        <li class="nav-item"><a href="/customer/dashboard" class="btn btn-outline-primary btn-sm me-2 rounded-pill px-3"><i class="fa fa-user-circle me-1"></i> ড্যাশবোর্ড ({{ session.get('customer_name') }})</a></li>
                        <li class="nav-item"><a href="/customer/logout" class="btn btn-danger btn-sm rounded-pill px-3">লগআউট</a></li>
                    {% else %}
                        <li class="nav-item me-2"><a class="btn btn-outline-primary btn-sm rounded-pill px-3" href="/customer/login">লগইন</a></li>
                        <li class="nav-item"><a class="btn btn-primary btn-sm rounded-pill px-3" href="/customer/register">রেজিস্ট্রেশন</a></li>
                    {% endif %}
                </ul>
            </div>
        </div>
    </nav>

    <!-- Always-visible mobile search: customers never need to open the dashboard/menu. -->
    <div class="mobile-search-wrap no-print">
        <form class="fayez-search mobile-search-form" action="/shop" method="GET" autocomplete="off">
            <div class="input-group">
                <input class="form-control ps-3" type="search" name="q" placeholder="পণ্য, ব্র্যান্ড বা SKU খুঁজুন..." aria-label="পণ্য সার্চ">
                <button class="btn btn-primary px-3" type="submit" aria-label="সার্চ"><i class="fa fa-search"></i></button>
            </div>
        </form>
    </div>

    <!-- Persistent mobile shortcuts for the store's most-used destinations. -->
    <nav class="mobile-bottom-nav no-print" aria-label="দ্রুত নেভিগেশন">
        <a href="/" class="mobile-bottom-link"><i class="fa fa-house"></i><span>হোম</span></a>
        <a href="/shop" class="mobile-bottom-link"><i class="fa fa-store"></i><span>পণ্য</span></a>
        <a href="/track" class="mobile-bottom-link"><i class="fa fa-truck-fast"></i><span>ট্র্যাকিং</span></a>
        <a href="/support" class="mobile-bottom-link"><i class="fa fa-headset"></i><span>সাপোর্ট</span></a>
        <a href="/cart" class="mobile-bottom-link"><i class="fa fa-bag-shopping"></i><span>কার্ট</span></a>
    </nav>

    <div class="container mt-3 no-print">
        {% with messages = get_flashed_messages(with_categories=true) %}
            {% if messages %}{% for c, m in messages %}
                <div class="alert alert-{{ c }} alert-dismissible fade show shadow-sm" role="alert">
                    {{ m }}<button type="button" class="btn-close" data-bs-dismiss="alert"></button>
                </div>
            {% endfor %}{% endif %}
        {% endwith %}
    </div>

    <main>{% block content %}{% endblock %}</main>

    <!-- Cute Desi AI Assistant Floating Widget -->
    <div class="ai-cute-launcher no-print" onclick="toggleAIChat()">
        <span class="ai-cute-badge d-none d-sm-inline">Fayez AI • Smart Shopping 🤖</span>
        <div class="ai-cute-avatar" title="Fayez AI Smart Shopping Assistant">
            <span aria-hidden="true" style="font-size:34px;line-height:1">✦</span>
        </div>
    </div>

    <div class="ai-chat-box no-print" id="aiChatBox">
        <div class="ai-chat-header">
            <div class="d-flex align-items-center gap-2">
                <span aria-hidden="true" style="width:34px;height:34px;border-radius:50%;background:#fff;color:#5145cd;display:grid;place-items:center;font-size:22px;font-weight:900">✦</span>
                <div>
                    <div class="fw-bold lh-1">Fayez AI Shopping Assistant ✨</div>
                    <small style="font-size: 0.72rem; opacity: 0.9;"><i class="fa fa-circle text-success me-1" style="font-size: 8px;"></i>পণ্য, বাজেট ও কেনাকাটায় স্মার্ট সহকারী</small>
                </div>
            </div>
            <button class="btn-close btn-close-white btn-sm" onclick="toggleAIChat()"></button>
        </div>
        <div class="ai-chat-body" id="aiChatBody">
            <div class="msg-bubble msg-ai">আসসালামু আলাইকুম! 👋 আমি Fayez AI। আপনার বাজেট ও প্রয়োজন বুঝে ক্যাটালগ থেকে পণ্য খুঁজে দিতে, দাম-স্টক জানাতে, বিকল্প তুলনা করতে এবং সঠিক ক্যাটাগরি বেছে নিতে সাহায্য করব। কী খুঁজছেন?</div>
        </div>
        <div class="ai-quick-chips">
            <span class="ai-chip" onclick="sendQuickAI('Gaming Collection দেখাও')">🎮 Gaming</span>
            <span class="ai-chip" onclick="sendQuickAI('Fashion Collection দেখাও')">👕 Fashion</span>
            <span class="ai-chip" onclick="sendQuickAI('৫০০০ টাকার মধ্যে ভালো পণ্য সাজেস্ট করো')">💰 বাজেট সাজেশন</span>
            <span class="ai-chip" onclick="sendQuickAI('দুটি পণ্য তুলনা করে দাও')">⚖️ পণ্য তুলনা</span>
            <span class="ai-chip" onclick="sendQuickAI('স্টকে কী কী আছে?')">📦 স্টক চেক</span>
            <span class="ai-chip" onclick="sendQuickAI('আমার অর্ডার দেখাও')">🧾 আমার অর্ডার</span>
            <span class="ai-chip" onclick="sendQuickAI('ডেলিভারি ও পেমেন্ট কীভাবে করব?')">🚚 ডেলিভারি ও পেমেন্ট</span>
        </div>
        <div class="ai-chat-footer">
            <input type="text" id="aiUserInput" class="form-control form-control-sm rounded-pill px-3" placeholder="পণ্য, বাজেট বা কেনাকাটার প্রশ্ন লিখুন..." onkeypress="if(event.key === 'Enter') sendAIMessage()">
            <button class="btn btn-primary btn-sm rounded-circle px-2" style="width: 34px; height: 34px;" onclick="sendAIMessage()"><i class="fa fa-paper-plane"></i></button>
        </div>
    </div>

    <footer class="no-print">
        <div class="container">
            <div class="row g-4 pb-4">
                <div class="col-lg-4 col-md-6">
                    <h4 class="text-white fw-bold mb-3"><i class="fa fa-bag-shopping text-primary me-2"></i>FAYEZ ONLINE SHOP</h4>
                    <p class="small">বাংলাদেশের অন্যতম বিশ্বস্ত এবং প্রিমিয়াম অনলাইন শপিং প্ল্যাটফর্ম। ১০০% অরিজিনাল পণ্য ও দ্রুততম হোম ডেলিভারির নিশ্চয়তা।</p>
                    <div class="d-flex gap-3 mt-3">
                        <a href="#" class="fs-5"><i class="fab fa-facebook"></i></a>
                        <a href="#" class="fs-5"><i class="fab fa-instagram"></i></a>
                        <a href="#" class="fs-5"><i class="fab fa-youtube"></i></a>
                        <a href="#" class="fs-5"><i class="fab fa-whatsapp"></i></a>
                    </div>
                </div>
                <div class="col-lg-2 col-md-6">
                    <h5>কুইক লিংক</h5>
                    <ul class="list-unstyled small d-flex flex-column gap-2">
                        <li><a href="/">হোম পেজ</a></li>
                        <li><a href="/shop">সকল পণ্য</a></li>
                        <li><a href="/track">অর্ডার ট্র্যাকিং</a></li>
                        <li><a href="/customer/login">কাস্টমার লগইন</a></li>
                    </ul>
                </div>
                <div class="col-lg-3 col-md-6">
                    <h5>কাস্টমার কেয়ার</h5>
                    <ul class="list-unstyled small d-flex flex-column gap-2">
                        <li><i class="fa fa-phone text-primary me-2"></i> হটলাইন: +880 1307-313063</li>
                        <li><i class="fa fa-envelope text-primary me-2"></i> fayejislam56@gmail.com</li>
                        <li><i class="fa fa-location-dot text-primary me-2"></i> ঢাকা, বাংলাদেশ</li>
                    </ul>
                </div>
                <div class="col-lg-3 col-md-6">
                    <h5>নিরাপদ পেমেন্ট মাধ্যম</h5>
                    <div class="d-flex flex-wrap gap-2">
                        <span class="badge bg-danger px-3 py-2">bKash</span>
                        <span class="badge bg-warning text-dark px-3 py-2">Nagad</span>
                        <span class="badge bg-info text-dark px-3 py-2">Rocket</span>
                        <span class="badge bg-success px-3 py-2">Cash On Delivery</span>
                    </div>
                </div>
            </div>
            <hr class="border-secondary">
            <div class="d-flex flex-column flex-md-row justify-content-between align-items-center small pt-2">
                <p class="mb-2 mb-md-0">© 2026 Fayez Online Shop. All Rights Reserved.</p>
                <a href="/admin/login" class="text-warning fw-semibold"><i class="fa fa-shield-halved me-1"></i>অ্যাডমিন পোর্টাল</a>
            </div>
        </div>
    </footer>

    <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/js/bootstrap.bundle.min.js"></script>
    <script>
        function togglePassword(inputId, iconId) {
            let input = document.getElementById(inputId);
            let icon = document.getElementById(iconId);
            if (input.type === "password") {
                input.type = "text";
                icon.classList.remove("fa-eye");
                icon.classList.add("fa-eye-slash");
            } else {
                input.type = "password";
                icon.classList.remove("fa-eye-slash");
                icon.classList.add("fa-eye");
            }
        }

        function toggleAIChat() {
            let box = document.getElementById('aiChatBox');
            box.style.display = box.style.display === 'flex' ? 'none' : 'flex';
        }

        function sendQuickAI(text) {
            document.getElementById('aiUserInput').value = text;
            sendAIMessage();
        }

        function addChatBubble(text, kind, extraClass='') {
            const body = document.getElementById('aiChatBody');
            const bubble = document.createElement('div');
            bubble.className = 'msg-bubble ' + kind + (extraClass ? ' ' + extraClass : '');
            bubble.textContent = text;
            body.appendChild(bubble);
            body.scrollTop = body.scrollHeight;
            return bubble;
        }
        async function sendAIMessage() {
            const input = document.getElementById('aiUserInput');
            const txt = input.value.trim();
            if (!txt) return;
            const sendBtn = document.querySelector('.ai-chat-footer button');
            addChatBubble(txt, 'msg-user');
            input.value = '';
            input.disabled = true;
            if (sendBtn) sendBtn.disabled = true;
            const typing = addChatBubble('লিখছি…', 'msg-ai', 'ai-typing');
            const started = Date.now();
            try {
                const response = await fetch('/ai/chat', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({message: txt})
                });
                const data = await response.json();
                const wait = Math.max(0, 2000 - (Date.now() - started));
                await new Promise(resolve => setTimeout(resolve, wait));
                typing.remove();
                addChatBubble(data.reply || 'দুঃখিত, উত্তর তৈরি করতে সমস্যা হয়েছে।', 'msg-ai');
            } catch (error) {
                typing.remove();
                addChatBubble('ইন্টারনেট বা সার্ভারে সমস্যা হয়েছে। আবার চেষ্টা করুন।', 'msg-ai');
            } finally {
                input.disabled = false;
                if (sendBtn) sendBtn.disabled = false;
                input.focus();
            }
        }
    </script>
<script>
(function(){
 const input=document.getElementById('fayezSearchInput');
 const panel=document.getElementById('fayezSearchSuggest');
 const mobileInput=document.querySelector('.mobile-search-form input[name="q"]');
 if(!input||!panel)return;
 let timer=null,active=-1,items=[],requestNo=0;
 const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
 function close(){panel.hidden=true;input.setAttribute('aria-expanded','false');active=-1;}
 function render(data,q){items=data.products||[];let html='';
  if(items.length){html='<div class="fayez-suggest-head">পণ্যের সাজেশন</div>'+items.map((p,i)=>`<a class="fayez-suggest-item" role="option" data-index="${i}" href="/product/${p.id}"><img src="${esc(p.image||'')}" onerror="this.style.visibility='hidden'" alt=""><span class="meta"><span class="name">${esc(p.name)}</span><span class="sub">${esc(p.brand||p.category||'পণ্য')} · ${esc(p.category||'')} · SKU: ${esc(p.sku||'')}</span></span><span class="price">৳ ${Number(p.price||0).toLocaleString('en-US')}</span></a>`).join('')+'<a class="fayez-suggest-foot d-block text-decoration-none" href="/shop?q='+encodeURIComponent(q)+'">সব ফলাফল দেখুন <i class="fa fa-arrow-right ms-1"></i></a>';}
  else html='<div class="p-3 small text-secondary">মিল পাওয়া যায়নি। অন্য বানান বা পণ্যের ধরন লিখে দেখুন।</div>';
  panel.innerHTML=html;panel.hidden=false;input.setAttribute('aria-expanded','true');
 }
 input.addEventListener('input',()=>{clearTimeout(timer);const q=input.value.trim();if(q.length<2){requestNo++;close();return;}const thisRequest=++requestNo;timer=setTimeout(async()=>{try{const r=await fetch('/search/suggest?q='+encodeURIComponent(q),{headers:{'Accept':'application/json'}});if(!r.ok)throw new Error('search');const data=await r.json();if(thisRequest===requestNo && input.value.trim()===q)render(data,q);}catch(e){if(thisRequest===requestNo)close();}},220);});
 input.addEventListener('keydown',e=>{const links=[...panel.querySelectorAll('.fayez-suggest-item')];if(e.key==='Escape'){close();return;}if(panel.hidden)return;if((e.key==='ArrowDown'||e.key==='ArrowUp')&&links.length){e.preventDefault();active=(active+(e.key==='ArrowDown'?1:-1)+links.length)%links.length;links.forEach((a,i)=>a.classList.toggle('active',i===active));}if(e.key==='Enter'&&active>=0&&links[active]){e.preventDefault();location.href=links[active].href;}});
 document.addEventListener('click',e=>{if(!e.target.closest('.fayez-search'))close();});
 input.addEventListener('focus',()=>{if(input.value.trim().length>=2)input.dispatchEvent(new Event('input'));});
 // Keep the mobile search in sync with the main smart-search field when available.
 if(mobileInput){
   mobileInput.addEventListener('input',()=>{ if(input){input.value=mobileInput.value;} });
   mobileInput.addEventListener('keydown',e=>{if(e.key==='Enter' && input){input.value=mobileInput.value;}});
 }
})();
</script>
<button id="fayezInstallBtn" type="button" aria-label="Install Fayez Online Shop" style="display:none;position:fixed;right:16px;bottom:18px;z-index:1050;border:0;border-radius:999px;padding:12px 18px;background:#5145cd;color:#fff;font-weight:700;box-shadow:0 8px 24px #17104444">
  <i class="fa fa-download me-2"></i>Install App
</button>
<script>
(()=>{
  if ('serviceWorker' in navigator && (location.protocol === 'https:' || location.hostname === 'localhost' || location.hostname === '127.0.0.1')) {
    window.addEventListener('load',()=>navigator.serviceWorker.register('/service-worker.js').catch(()=>{}));
  }
  const btn=document.getElementById('fayezInstallBtn');
  let installPrompt=null;
  if(/iphone|ipad|ipod/i.test(navigator.userAgent||'')){btn.style.display='block';}
  window.addEventListener('beforeinstallprompt',e=>{e.preventDefault();installPrompt=e;btn.style.display='block';});
  btn?.addEventListener('click',async()=>{
    if(installPrompt){installPrompt.prompt();await installPrompt.userChoice;installPrompt=null;btn.style.display='none';return;}
    const ua=navigator.userAgent||'';
    if(/iphone|ipad|ipod/i.test(ua)){alert('iPhone-এ Safari-এর Share বাটনে চাপুন, তারপর Add to Home Screen নির্বাচন করুন।');}
  });
  window.addEventListener('appinstalled',()=>{btn.style.display='none';});
})();
</script>
</body>
</html>
'''

# PWA endpoints are served by Flask so the project remains a single Python file.
_PWA_ICON = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAgAAAAIACAIAAAB7GkOtAAAIPUlEQVR42u3dMW4TYRSF0XgyxSD2AZTBe7BbZJdZETWLSIPkIg2S92CL3cRVRBulsKx4yP/n3XN2wATuN89GsNisDjcA5Bk8AgABAEAAABAAAAQAAAEAQAAAEAAABAAAAQBAAAAQAAAEAAABAEAAABAAAAQAAAEAQAAAEAAABAAAAQBAAAAQAAABAEAAABAAAAQAAAEAQAAAEAAABAAAAQCgV6NH0NZuv/QQSLZdHz2EVhab1cFTsPWgCgKAxQc9EACMPoiBAGD0QQwEALsPSiAAdh9QAgEw/YAMCIDdB5RAAEw/IAMCYPoBGRAA0w/IgACYfkAGBMD0AzLwzvxz0NYf/Nl3AfjxA04BATD9gAyUl/gRkPUHLEPcBWD6AadA4gVg/QFbkRgA6w9YjFfqfwRk+oE3q/1xUPELwPoDNiQxANYfsCRn1PwIyPQDs6v3cVDBC8D6A7YlMQDWH7AwiQGw/oCdSQyA9QesTWIArD9gcxIDYP0By5MYAOsP2J/EAFh/wAolBsD6A7YoMQDWH7BIiQGw/oBdSgyA9QesU2IArD9go3IvAADiAuD1H7BUiQGw/oC9SgyA9Qc0IPcCACAuAF7/AUdAYgCsP6ABiQGw/oAG5F4AAMQFwOs/4AhIDID1BzQg9wIAIC4AXv8BR4ALAICYAHj9BxwBiQGw/oAG5F4AAMQFwOs/4AhwAQAQEwCv/4AjwAUAQEwAvP4DjgAXAAAxAfD6DzgCXAAAxATA6z/gCHABACAAANQOgM9/ABouoQsAwAXg9R8gaQ9dAAAuAAAEoOq9A9CnJqvoAgBwAQAgAPUuHYDOvf82ugAAXAAACAAAAjAzXwAAdLKQLgAAFwAAAgCAAMzJFwAA/eykCwDABQCAAAAgAAAIwHV8AwzQ1Vq6AABcAAAIAAACAIAAACAAAAjARfwdUIDeNtMFAOACAEAAABAAAAQAAAEAQAAAEAAABAAAAQBAAAAQAAAEAAABAEAAABAAAAQAAAEAQAAAEAAABACAM0aPgCudnp7vf/z1HJr48u3zz19fPQdcAAAIAAACAIAAACAAAALgEQAIAAACAIAAACAAAAgAAAIAgAAAIAAACAAAAgCAAAAgAAAIAAACAIAAACAAAAgAAAIAgAAAIAAACAAAAgCAAAAIAAACAIAAACAAAAgAABWMHgGVTNPw8HjnOYALAAABAEAAABAAAAEAQAAAEAAABAAAAQBAAAAQAAAEAAABAEAAABAAAAQAAAEAQAAAEAAABAAAAQBAAAAQAAAEAAABAEAAABAAAAEAQAAAEAAABAAAAQBAAAAQAAA+ntEjoJLT6Xm7Ptb+Nf7+8/32duFnjQsAAAEAQAAAEAAABAAAAQBAAAAEAAABAEAAABAAAAQAAAEAQAAAEAAABAAAAQBAAAAQAAAEAAABAEAAABAAAAQAAAEAQAAAEAAABAAAAQBAAAAEAAABAEAAABAAAKoZPQIqmabh4fHOcwAXAAACAIAAACAAAAIAgAAAIAAACAAAAgCAAAAgAAAIAAACAIAAACAAAAgAAAIAgAAAIAAACAAAAgCAAAAgAAAIAAACAIAAACAAAAIAgAAAIAAACAAAAgCAAAAgAAAIAAACAIAAACAAAAgAAAIAgAAAIAAACAAAAgCAAAAgAAAIAAACAIAAACAAAAgAgAAAIAAACAAAAgCAAAAgAAAIAAACAIAAACAAAAgAAAIAgAAAIAAACAAAAgCAAAAgAAAIAAACAIAAACAAAAgAgAAAIAAApBg9Aq40fRp2+6XnAC4AAAQAAAEAQAAAEAAABAAAAQBAAAAQAAAEAAABAEAAABAAAAQAAAEAQAAAEAAAAQBAAAAQAAAEAAABAEAAABAAAAQAAAEAQAAAEAAABAAAAQBAAAAQAAAEAAABAEAAABAAAAQAAAEAQAAAEAAAAQBAAAAQAAAEAAABAEAAABAAAAQAAAEAQAAAEAAABACA6gHYro+eNUBXm+kCAHABACAAAAgAAAIAgAAAIACX8jdBAbpaSxcAgAsAAAEAQAAAEICr+R4YoJ+ddAEAuAAAEAAABGBmvgYA6GQhXQAALgAABAAAAZifrwEAethGFwCACwAAAah36QD0rMkqugAAXAAACEDVewegQ6320AUA4AJwBAAkLaELAMAFAIAAJNw+AM213UAXAIALwBEAkLR+LgAAF4AjACBp91wAAC4ARwBA0uK5AABcAJIIkLR1LgAAF4AwAiSt3ODpAGTum4+AAEL1GABHAOD13wUAQFgAHAGA1//cC0ADAOsfGgAAcgPgCAC8/udeABoAWP/QAGgAYP1zAwBAbgAcAYDX/9wLQAMAexUaAA0ALFVuAADIDYAjALBRuReABgDWKTQAGgDYpdwAaABgkXIDoAGALcoNgAYAVig3ABoA2J/cAGgAYHlyA6ABgM3JDYAGANYmNwAaANiZ3ABoAGBhcgOgAYBtudBiszpU/Wnt9ku/ZQHTH3QBOAUAS5IeAA0AbMgZlT8CesnHQYDpz7oAnAKAxUgPgAYAtuKVlI+AXvJxEOA18SbzP4V3CgCWIfQCcAoAXgrTAyADYPqTf/mD3wE+EQJ/9l0A6ZwCYPoFQAYA0y8AMgCYfgGQAcD0C4AMAKZfAJQAsPsCIAOA6RcAJQDsvgAoAWD3BUAMAKMvAGIAGH0B0APA4guAKoCtRwAA+L/8c9AAAgCAAAAgAAAIAAACAIAAACAAAAgAAAIAgAAAIAAACAAAAgCAAAAgAAAIAAACAIAAACAAAAgAAAIAgAAAIAAAAgCAAAAgAAAIAAACAIAAACAAAAgAAB/BP1Dbunej1HEoAAAAAElFTkSuQmCC")

@app.route('/manifest.webmanifest')
def pwa_manifest():
    return jsonify({
        'id': '/', 'name': 'Fayez Online Shop', 'short_name': 'Fayez Shop',
        'description': 'Fayez Online Shop - Smart shopping, smart lifestyle.',
        'start_url': '/', 'scope': '/', 'display': 'standalone',
        'background_color': '#f5f6fa', 'theme_color': '#5145cd',
        'orientation': 'portrait-primary',
        'icons': [{'src': '/pwa-icon-512.png', 'sizes': '512x512', 'type': 'image/png', 'purpose': 'any maskable'}]
    })

@app.route('/pwa-icon-512.png')
def pwa_icon():
    return Response(_PWA_ICON, mimetype='image/png', headers={'Cache-Control':'public, max-age=604800'})

@app.route('/service-worker.js')
def pwa_service_worker():
    worker = r"""const CACHE='fayez-shop-shell-v1';
const OFFLINE='/offline';
self.addEventListener('install',event=>{event.waitUntil((async()=>{const c=await caches.open(CACHE);await c.addAll([OFFLINE,'/manifest.webmanifest','/pwa-icon-512.png']);await self.skipWaiting();})());});
self.addEventListener('activate',event=>{event.waitUntil((async()=>{for(const k of await caches.keys())if(k!==CACHE)await caches.delete(k);await self.clients.claim();})());});
self.addEventListener('fetch',event=>{const req=event.request;const url=new URL(req.url);if(req.method!=='GET'||url.origin!==location.origin)return;if(url.pathname.startsWith('/admin')||url.pathname.startsWith('/api')||url.pathname.includes('login')||url.pathname.includes('logout')||url.pathname.includes('otp')||url.pathname.includes('password')||url.pathname==='/checkout')return;if(req.mode==='navigate'){event.respondWith(fetch(req).catch(async()=>await caches.match(OFFLINE)));return;}if(url.pathname==='/manifest.webmanifest'||url.pathname==='/pwa-icon-512.png'){event.respondWith(caches.match(req).then(hit=>hit||fetch(req)));}});
"""
    return Response(worker, mimetype='application/javascript', headers={'Service-Worker-Allowed':'/','Cache-Control':'no-cache'})

@app.route('/offline')
def pwa_offline():
    return Response('<!doctype html><html lang="bn"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Offline | Fayez Shop</title><body style="font-family:Arial,sans-serif;text-align:center;padding:15vh 20px;background:#f5f6fa;color:#172033"><h2>ইন্টারনেট সংযোগ নেই</h2><p>Fayez Online Shop ব্যবহার করতে আবার ইন্টারনেট সংযোগ দিন।</p><button onclick="location.reload()" style="padding:12px 20px;border:0;border-radius:24px;background:#5145cd;color:white">আবার চেষ্টা করুন</button></body></html>', mimetype='text/html')

@app.route('/')
def home():
    db = get_db()
    products = db.execute("SELECT * FROM products WHERE COALESCE(is_active,1)=1 AND COALESCE(TRIM(image),'')<>'' ORDER BY id DESC LIMIT 12").fetchall()
    flash_products = db.execute("SELECT * FROM products WHERE COALESCE(is_active,1)=1 AND is_flash_sale = 1 AND COALESCE(TRIM(image),'')<>'' ORDER BY id DESC LIMIT 4").fetchall()
    categories = db.execute('SELECT * FROM categories ORDER BY name COLLATE NOCASE').fetchall()
    categories = sorted(categories, key=lambda cat: CURATED_CATEGORY_SLUGS.index(cat['slug']) if cat['slug'] in CURATED_CATEGORY_SLUGS else 999)
    banners = db.execute('SELECT * FROM banners ORDER BY id LIMIT 25').fetchall()
    body = r'''    {% if banners %}
    <section id="heroCarousel" class="carousel slide store-hero" data-bs-ride="carousel" data-bs-interval="5200" data-bs-touch="true">
      <div class="carousel-indicators">{% for b in banners %}<button type="button" data-bs-target="#heroCarousel" data-bs-slide-to="{{ loop.index0 }}" {% if loop.first %}class="active"{% endif %} aria-label="Slide {{ loop.index }}"></button>{% endfor %}</div>
      <div class="carousel-inner">{% for b in banners %}<div class="carousel-item {% if loop.first %}active{% endif %}">
        <img src="{{ b.image_url }}" alt="{{ b.title }}" loading="{% if loop.first %}eager{% else %}lazy{% endif %}">
        <div class="carousel-caption"><span class="badge rounded-pill px-3 py-2">FAYEZ EXCLUSIVE • {{ '%02d'|format(loop.index) }}</span><h1>{{ b.title }}</h1><p>{{ b.subtitle }}</p><a href="{{ b.link_url }}" class="btn hero-cta">কালেকশন দেখুন <i class="fa fa-arrow-right ms-2"></i></a></div>
      </div>{% endfor %}</div>
      <button class="carousel-control-prev" type="button" data-bs-target="#heroCarousel" data-bs-slide="prev"><span class="carousel-control-prev-icon"></span></button><button class="carousel-control-next" type="button" data-bs-target="#heroCarousel" data-bs-slide="next"><span class="carousel-control-next-icon"></span></button>
    </section>
    {% else %}<section class="store-hero d-flex align-items-center px-4 px-lg-5"><div class="text-white" style="max-width:650px"><span class="badge bg-light text-dark rounded-pill px-3 py-2">FAYEZ ONLINE SHOP</span><h1 class="display-3 fw-bold mt-3">স্মার্ট শপিং,<br>স্মার্ট লাইফস্টাইল।</h1><p class="lead">আপনার প্রতিদিনের পছন্দের সবকিছু এক জায়গায়।</p><a class="btn hero-cta" href="/shop">এখনই শপিং করুন</a></div></section>{% endif %}
    <div class="home-wrap"><div class="trust-row">
      <div class="trust-item"><span class="trust-icon"><i class="fa fa-truck-fast"></i></span><div><b>দ্রুত ডেলিভারি</b><small>সারা বাংলাদেশে</small></div></div>
      <div class="trust-item"><span class="trust-icon"><i class="fa fa-shield-halved"></i></span><div><b>নিরাপদ কেনাকাটা</b><small>বিশ্বস্ত অর্ডার প্রসেস</small></div></div>
      <div class="trust-item"><span class="trust-icon"><i class="fa fa-rotate-left"></i></span><div><b>সহজ রিটার্ন</b><small>সহজ রিটার্ন সহায়তা</small></div></div>
      <div class="trust-item"><span class="trust-icon"><i class="fa fa-headset"></i></span><div><b>কাস্টমার সাপোর্ট</b><small>আপনার পাশে সবসময়</small></div></div></div>
    <section class="home-section"><div class="section-top"><div><div class="eyebrow">EXPLORE THE STORE</div><h2 class="section-title">আপনার পছন্দের ক্যাটাগরি</h2><p class="section-sub">এক জায়গায় প্রয়োজনীয় সবকিছু, সহজে খুঁজে নিন।</p></div><a href="/shop" class="btn btn-outline-dark rounded-pill px-3">সব ক্যাটাগরি <i class="fa fa-arrow-right ms-1"></i></a></div>
      {% if categories %}<div class="category-grid">{% for cat in categories %}<a href="/shop?cat={{ cat.id }}" class="category-box"><img src="{{ cat.image or 'https://images.unsplash.com/photo-1441986300917-64674bd600d8?w=500' }}" alt="{{ cat.name }}" loading="lazy" onerror="this.onerror=null;this.src='https://images.unsplash.com/photo-1441986300917-64674bd600d8?w=600'"><h6 class="mb-0 px-1 text-truncate">{{ cat.name }}</h6></a>{% endfor %}</div>{% else %}<div class="home-empty">ক্যাটাগরি যোগ করা হলে এখানে দেখা যাবে।</div>{% endif %}</section>
    <section class="home-section collection-showcase"><div class="section-top"><div><div class="eyebrow">FAYEZ SIGNATURE PICKS</div><h2 class="section-title">বিশেষ কালেকশন</h2><p class="section-sub">স্টাইল ও গেমিং—দুই জগতের সেরা পছন্দ এক জায়গায়।</p></div></div><div class="collection-grid">
      <a class="collection-tile" href="/shop?q=fashion"><img src="https://images.unsplash.com/photo-1529139574466-a303027c1d8b?w=1400&auto=format&fit=crop&q=92" alt="Fashion Collection" loading="lazy"><span><small>THE STYLE EDIT</small><b>Fashion Collection</b><em>নতুন স্টাইল আবিষ্কার করুন <i class="fa fa-arrow-right"></i></em></span></a>
      <a class="collection-tile" href="/shop?q=gaming"><img src="https://images.unsplash.com/photo-1593305841991-05c297ba4575?w=1400&auto=format&fit=crop&q=92" alt="Gaming Collection" loading="lazy"><span><small>ULTIMATE GAMING ZONE</small><b>Gaming Collection</b><em>গেমিং সেটআপ ও গিয়ার দেখুন <i class="fa fa-arrow-right"></i></em></span></a>
      <a class="collection-tile" href="/shop?q=skincare"><img src="https://images.unsplash.com/photo-1608248543803-ba4f8c70ae0b?w=1400&auto=format&fit=crop&q=90" alt="Beauty & Skincare Collection" loading="lazy"><span><small>GLOW & CARE EDIT</small><b>Beauty & Skincare</b><em>স্কিনকেয়ার ও বিউটি পছন্দ দেখুন <i class="fa fa-arrow-right"></i></em></span></a>
      <a class="collection-tile" href="/shop?q=home"><img src="https://images.unsplash.com/photo-1556911220-e15b29be8c8f?w=1400&auto=format&fit=crop&q=90" alt="Home & Kitchen Collection" loading="lazy"><span><small>HOME LIVING PICKS</small><b>Home & Kitchen</b><em>ঘর ও রান্নাঘরের প্রয়োজনীয় পণ্য <i class="fa fa-arrow-right"></i></em></span></a>
    </div></section>
    {% if flash_products %}<section class="home-section deal-panel"><div class="section-top"><div><div class="eyebrow" style="color:#d9d2ff">LIMITED TIME DEALS</div><h2 class="section-title">আজকের স্পেশাল ডিল</h2><p class="section-sub">সীমিত সময়ের নির্বাচিত অফারগুলো দেখে নিন।</p></div><a href="/shop" class="btn btn-light rounded-pill px-3 fw-bold">সব ডিল দেখুন</a></div><div class="product-grid">{% for p in flash_products %}<a href="/product/{{ p.id }}" class="product-card h-100">{% if p.discount_percent > 0 %}<span class="badge-discount">{{ p.discount_percent }}% OFF</span>{% endif %}{% if p.image %}<img src="{{ p.image }}" class="card-img-top" alt="{{ p.name }}" loading="lazy">{% else %}<div class="card-img-top d-flex align-items-center justify-content-center text-secondary bg-light" style="height:220px">ছবি যোগ করা হয়নি</div>{% endif %}<div class="card-body d-flex flex-column"><h6 class="fw-bold text-dark">{{ p.name }}</h6><div class="mt-auto"><span class="text-danger fw-bold fs-5">৳ {{ '%.0f'|format(p.price) }}</span>{% if p.old_price %}<small class="text-muted text-decoration-line-through ms-2">৳ {{ '%.0f'|format(p.old_price) }}</small>{% endif %}</div></div></a>{% endfor %}</div></section>{% endif %}
    <section class="home-section"><div class="section-top"><div><div class="eyebrow">JUST FOR YOU</div><h2 class="section-title">নতুন ও জনপ্রিয় পণ্য</h2><p class="section-sub">নতুন পছন্দগুলো ঘুরে দেখুন।</p></div><a href="/shop" class="btn btn-outline-dark rounded-pill px-3">সব পণ্য <i class="fa fa-arrow-right ms-1"></i></a></div>
      {% if products %}<div class="product-grid">{% for p in products %}<a href="/product/{{ p.id }}" class="product-card h-100">{% if p.discount_percent > 0 %}<span class="badge-discount">{{ p.discount_percent }}% OFF</span>{% endif %}{% if p.image %}<img src="{{ p.image }}" class="card-img-top" alt="{{ p.name }}" loading="lazy">{% else %}<div class="card-img-top d-flex align-items-center justify-content-center text-secondary bg-light" style="height:220px">ছবি যোগ করা হয়নি</div>{% endif %}<div class="card-body d-flex flex-column"><small class="text-muted mb-1">{{ p.sku }}</small><h6 class="fw-bold text-dark">{{ p.name }}</h6><div class="d-flex align-items-center gap-2 mt-auto mb-3"><span class="text-dark fw-bold fs-5">৳ {{ '%.0f'|format(p.price) }}</span>{% if p.old_price %}<small class="text-muted text-decoration-line-through">৳ {{ '%.0f'|format(p.old_price) }}</small>{% endif %}</div><span class="btn btn-outline-dark w-100">পণ্যটি দেখুন</span></div></a>{% endfor %}</div>{% else %}<div class="home-empty"><i class="fa fa-box-open fa-2x mb-3"></i><h5 class="fw-bold">এখনো কোনো পণ্য যোগ করা হয়নি</h5><p class="mb-0">অ্যাডমিন প্যানেল থেকে পণ্য যোগ করলে এখানে দেখা যাবে।</p></div>{% endif %}</section></div>'''
    return render_template_string(BASE_HTML.replace('{% block content %}{% endblock %}', body), products=products, flash_products=flash_products, categories=categories, banners=banners)

@app.route('/ai/chat', methods=['POST'])
def ai_chat():
    data = request.get_json(silent=True) or {}
    original = str(data.get('message') or '').strip()
    if not original:
        return jsonify({'reply': 'আপনি কী খুঁজছেন বা কী জানতে চান, একটু লিখুন।'})

    # Keep a short conversation context in this visitor's signed Flask session.
    history = session.get('fayez_ai_history', [])
    if not isinstance(history, list):
        history = []
    msg = original.casefold()
    db = get_db()

    # Resolve common follow-up phrases using the previous turn's product/category context.
    follow_up = any(x in msg for x in ['আরও', 'আর কি', 'আরেকটা', 'এটা', 'ওটা', 'সেটা', 'আর কোন', 'আরেকটি', 'দাম কত', 'কেমন হবে', 'তাহলে'])
    previous_query = ''
    previous_product = ''
    if history:
        previous_query = str(history[-1].get('query') or '')
        previous_product = str(history[-1].get('product') or '')
    search_text = original
    if follow_up and len(msg.split()) <= 7:
        if previous_product and any(x in msg for x in ['এটা', 'ওটা', 'সেটা', 'দাম কত', 'কেমন হবে']):
            search_text = previous_product
        elif previous_query:
            search_text = previous_query + ' ' + original

    # Search using meaningful terms; ignore common conversational filler.
    stop = {'আমি','আমার','তুমি','আপনি','একটা','দাও','দেখাও','চাই','করে','করো','কেমন','আছে','কি','কী','দাম','কত','ভাই','please','the','for','and','with','show','find'}
    tokens = [t.strip('.,!?()[]{}:;"\'') for t in search_text.casefold().replace(',', ' ').split()]
    tokens = [t for t in tokens if len(t) >= 2 and t not in stop][:8]
    found = []
    if tokens:
        clauses, values = [], []
        for token in tokens:
            clauses.append("(LOWER(p.name) LIKE ? OR LOWER(p.sku) LIKE ? OR LOWER(COALESCE(p.description,'')) LIKE ? OR LOWER(COALESCE(c.name,'')) LIKE ?)")
            values.extend([f'%{token}%', f'%{token}%', f'%{token}%', f'%{token}%'])
        found = db.execute(
            'SELECT p.id,p.name,p.price,p.old_price,p.stock,p.sku,p.category_id,c.name AS category '
            'FROM products p LEFT JOIN categories c ON c.id=p.category_id WHERE COALESCE(p.is_active,1)=1 AND (' + ' OR '.join(clauses) + ')'+
            ' ORDER BY CASE WHEN p.stock > 0 THEN 0 ELSE 1 END, p.id DESC LIMIT 5', values
        ).fetchall()

    lower = msg
    # Smart category and budget intents: recommendations are grounded in the live store catalogue.
    category_intents = [
        (('gaming-consoles','pc-components','gaming-chairs-desks','gaming-products'), ['গেমিং','gaming','গেম','কনসোল','console','gpu','গ্রাফিক্স','গেমিং পিসি']),
        (('mens-fashion','womens-fashion','kids-fashion-new','shoes-footwear','bags-backpacks'), ['ফ্যাশন','fashion','জামা','পোশাক','শার্ট','ড্রেস']),
        (('snacks-chocolates','beverages','groceries'), ['স্ন্যাক','snack','চকলেট','chocolate','ক্যান্ডি','candy'])
    ]
    intended_slugs = next((slugs for slugs, words in category_intents if any(w in lower for w in words)), ())
    # Accept both English and Bengali numerals, but only interpret a number as a budget
    # when the customer actually mentions a budget/price context.
    bangla_digits = str.maketrans('০১২৩৪৫৬৭৮৯', '0123456789')
    budget_text = lower.translate(bangla_digits)
    has_budget_context = any(k in budget_text for k in ['বাজেট','টাকার মধ্যে','এর মধ্যে','এর নিচে','under','below','within','৳','tk','taka'])
    budget_match = re.search(r'(?:৳\s*|tk\.?\s*)?([0-9]{3,7})\s*(?:টাকা|tk|taka)?', budget_text) if has_budget_context else None
    budget_limit = int(budget_match.group(1)) if budget_match else None
    asks_compare = any(k in lower for k in ['তুলনা','compare','comparison','কোনটা ভালো','পার্থক্য'])
    if intended_slugs or budget_limit:
        filters, params = [], []
        if intended_slugs:
            filters.append('c.slug IN (%s)' % ','.join('?' for _ in intended_slugs))
            params.extend(intended_slugs)
        if budget_limit:
            filters.append('p.price <= ?')
            params.append(budget_limit)
        smart_rows = db.execute('''SELECT p.id,p.name,p.price,p.old_price,p.stock,p.sku,p.category_id,c.name AS category
            FROM products p LEFT JOIN categories c ON c.id=p.category_id
            WHERE COALESCE(p.is_active,1)=1 AND (''' + ' AND '.join(filters) + ''')
            ORDER BY CASE WHEN p.stock>0 THEN 0 ELSE 1 END, p.price ASC LIMIT 5''', params).fetchall()
        if smart_rows:
            found = smart_rows
    greeting = any(k in lower for k in ['হ্যালো','হাই','hello','hi','আসসালামু','সালাম'])
    asks_delivery = any(k in lower for k in ['ডেলিভারি','delivery','কবে পাব','কত দিন'])
    asks_payment = any(k in lower for k in ['পেমেন্ট','payment','বিকাশ','bkash','নগদ','nagad','রকেট'])
    asks_discount = any(k in lower for k in ['ছাড়','ডিসকাউন্ট','discount','কুপন','coupon'])
    asks_stock = any(k in lower for k in ['স্টক','আছে কি','available','পাওয়া যাবে'])
    asks_price = any(k in lower for k in ['দাম','price','কত টাকা','কত'])
    asks_recommend = any(k in lower for k in ['সাজেস্ট','recommend','কোনটা ভালো','কোনটা কিনব','পরামর্শ','best'])
    asks_order = any(k in lower for k in ['আমার অর্ডার','অর্ডার কোথায়','অর্ডার কোথায়','order status','track order','অর্ডার ট্র্যাক','ট্র্যাকিং'])

    if asks_order:
        if session.get('customer_id'):
            my_orders = db.execute('SELECT order_id,order_status,tracking_number,courier_name,created_at,total_amount FROM orders WHERE customer_id=? ORDER BY id DESC LIMIT 3', (session['customer_id'],)).fetchall()
            if my_orders:
                status_labels = {'Pending':'অপেক্ষমাণ','Confirmed':'কনফার্ম','Processing':'প্রসেসিং','Shipped':'শিপমেন্ট হয়েছে','Delivered':'ডেলিভারি সম্পন্ন','Cancelled':'বাতিল'}
                order_lines = [f"• অর্ডার {o['order_id']} — {status_labels.get(o['order_status'], o['order_status'])}; মোট ৳{o['total_amount']:,.0f}; কুরিয়ার: {o['courier_name'] or 'এখনো নির্ধারিত নয়'}; ট্র্যাকিং: {o['tracking_number'] or 'শিপমেন্টের পর দেওয়া হবে'}" for o in my_orders]
                reply = 'আপনার সাম্প্রতিক অর্ডারগুলোর আপডেট:\n' + '\n'.join(order_lines)
            else:
                reply = 'আপনার অ্যাকাউন্টে এখনো কোনো অর্ডার পাওয়া যায়নি।'
        else:
            reply = 'আপনার অর্ডারের ব্যক্তিগত তথ্য নিরাপদ রাখতে আগে কাস্টমার অ্যাকাউন্টে লগইন করুন। তারপর আমাকে “আমার অর্ডার দেখাও” লিখুন।'
        last_product, last_query = previous_product, previous_query
    elif found:
        items = []
        for p in found:
            stock_text = f"স্টকে {p['stock']}টি" if p['stock'] > 0 else 'এই মুহূর্তে স্টক নেই'
            price_text = f"৳{p['price']:,.0f}"
            items.append(f"• {p['name']} — {price_text} ({stock_text}) | /product/{p['id']}")
        if budget_limit:
            reply = f'আপনার ৳{budget_limit:,.0f} বাজেটের মধ্যে ক্যাটালগে পাওয়া পণ্যগুলো (দাম ও স্টকসহ):\n' + '\n'.join(items)
        elif asks_compare:
            reply = 'তুলনা করার জন্য পাওয়া বিকল্পগুলো নিচে দিলাম। দাম, স্টক ও পণ্যের বিস্তারিত দেখে বেছে নিন:\n' + '\n'.join(items) + '\n\nদুটি নির্দিষ্ট পণ্যের নাম দিলে আরও নির্দিষ্টভাবে তুলনা করতে পারব।'
        elif intended_slugs:
            reply = 'আপনার পছন্দের কালেকশনে পাওয়া পণ্যগুলো:\n' + '\n'.join(items) + '\n\nকোনো নির্দিষ্ট বাজেট বা ফিচার থাকলে বলুন—আরও ভালোভাবে বেছে দেব।'
        elif asks_stock:
            reply = 'স্টক দেখে জানাচ্ছি—\n' + '\n'.join(items)
        elif asks_price:
            reply = 'ক্যাটালগে পাওয়া পণ্যগুলোর বর্তমান দাম:\n' + '\n'.join(items)
        elif asks_recommend:
            available = [p for p in found if p['stock'] > 0]
            if available:
                pick = available[0]
                reply = f"আপনার বলা বিষয় অনুযায়ী আগে এই পণ্যটি বিবেচনা করতে পারেন: {pick['name']} — ৳{pick['price']:,.0f}। তবে আপনার বাজেট ও কী কাজে ব্যবহার করবেন জানালে আরও ভালোভাবে তুলনা করে বলতে পারব।\n\nআরও বিকল্প:\n" + '\n'.join(items[1:])
            else:
                reply = 'মিল পাওয়া পণ্যগুলো আপাতত স্টকে নেই। চাইলে বাজেট বা বিকল্প ক্যাটাগরি বলুন।'
        else:
            reply = 'আপনার কথার সঙ্গে মিলে এমন পণ্য পেয়েছি:\n' + '\n'.join(items) + '\n\nআপনি চাইলে বাজেট, ব্যবহার বা কোন বৈশিষ্ট্য বেশি দরকার—সেটা বলুন; আমি তুলনা করে সাজেস্ট করব।'
        last_product = found[0]['name']
        last_query = str(found[0]['category'] or search_text)
    elif greeting:
        reply = 'ওয়ালাইকুম আসসালাম! 😊 কী ধরনের পণ্য খুঁজছেন? যেমন গেমিং PC পার্টস, GPU, প্রসেসর, মনিটর বা অন্য কিছু। বাজেট বললে সেই অনুযায়ী সাজিয়ে দিতে পারি।'
        last_product, last_query = '', ''
    elif asks_delivery:
        reply = 'ডেলিভারির সময় ও চার্জ আপনার ঠিকানা এবং অর্ডারের পণ্যের ওপর নির্ভর করতে পারে। আপনার জেলা ও উপজেলা বললে সঠিক তথ্য খুঁজে দিতে পারব।'
        last_product, last_query = previous_product, previous_query
    elif asks_payment:
        reply = 'চেকআউটে সাইটে দেখানো উপলভ্য পেমেন্ট মাধ্যম থেকে নির্বাচন করুন। bKash/Nagad/Rocket-এর নম্বর ও পেমেন্ট নির্দেশনা অর্ডার নিশ্চিত করার আগে সাইটে মিলিয়ে নেবেন।'
        last_product, last_query = previous_product, previous_query
    elif asks_discount:
        coupon = db.execute('SELECT code, discount_percent FROM coupons WHERE is_active=1 ORDER BY discount_percent DESC LIMIT 1').fetchone()
        if coupon:
            reply = f"সক্রিয় কুপন হিসেবে {coupon['code']} পাওয়া গেছে ({coupon['discount_percent']:g}% ছাড়)। Checkout-এ প্রয়োগের আগে শর্ত দেখে নিন।"
        else:
            reply = 'এই মুহূর্তে সক্রিয় কুপনের তথ্য পাওয়া যায়নি। অ্যাডমিন নতুন অফার যোগ করলে এখানে দেখা যাবে।'
        last_product, last_query = previous_product, previous_query
    elif follow_up and previous_product:
        reply = f"আপনি আগেরবার {previous_product} নিয়ে জানতে চেয়েছিলেন। আপনি কি এর দাম, স্টক, স্পেসিফিকেশন, নাকি এর বিকল্প পণ্য জানতে চান?"
        last_product, last_query = previous_product, previous_query
    else:
        reply = 'আমি পণ্যের ক্যাটালগ, দাম, স্টক, বাজেটভিত্তিক সাজেশন, ক্যাটাগরি খোঁজা, পণ্য তুলনা, অফার, পেমেন্ট ও ডেলিভারি বিষয়ে সাহায্য করতে পারি। শুরু করতে পণ্যের ধরন বা বাজেট লিখুন—যেমন “১০ হাজার টাকার মধ্যে গেমিং হেডসেট”।'
        last_product, last_query = previous_product, previous_query

    history.append({'query': (last_query or original[:80])[:80], 'product': last_product[:100], 'user': original[:120], 'assistant': reply[:320]})
    session['fayez_ai_history'] = history[-4:]
    session.modified = True
    return jsonify({'reply': reply})

def _search_normalize(value):
    value = (value or '').casefold().strip()
    value = re.sub(r"[^\w\u0980-\u09ff]+", " ", value)
    return ' '.join(value.split())


def _rank_products(db, query, limit=12):
    """Rank catalogue matches by exact, prefix, token and typo-tolerant similarity."""
    q = _search_normalize(query)
    if not q:
        return []
    rows = db.execute("""SELECT p.*, c.name AS category_name FROM products p
        LEFT JOIN categories c ON c.id=p.category_id
        WHERE COALESCE(p.is_active,1)=1
        ORDER BY CASE WHEN p.stock>0 THEN 0 ELSE 1 END, p.id DESC LIMIT 2500""").fetchall()
    q_tokens = q.split()
    ranked = []
    for row in rows:
        name = _search_normalize(row['name'])
        sku = _search_normalize(row['sku'])
        brand = _search_normalize(row['brand'] or '')
        desc = _search_normalize(row['description'] or '')
        category = _search_normalize(row['category_name'] or '')
        hay = ' '.join((name, sku, brand, category, desc))
        score = 0.0
        if q == name: score = 120
        elif q == sku: score = 118
        elif name.startswith(q): score = 105
        elif q in name: score = 95
        elif q in sku: score = 92
        elif q == brand: score = 110
        elif q in brand: score = 98
        elif q in category: score = 82
        elif q in desc: score = 55
        else:
            for token in q_tokens:
                candidates = name.split() + category.split() + sku.split() + brand.split()
                best = max((difflib.SequenceMatcher(None, token, word).ratio() for word in candidates), default=0)
                if best >= 0.72: score += best * 22
            if all(token in hay for token in q_tokens): score += 35
            elif all(any(difflib.SequenceMatcher(None, token, word).ratio() >= .78 for word in hay.split()) for token in q_tokens): score += 18
        if score > 0:
            ranked.append((score, row))
    ranked.sort(key=lambda item: (item[0], int(item[1]['stock'] or 0), int(item[1]['id'])), reverse=True)
    return [row for score, row in ranked[:limit]]


@app.route('/search/suggest')
def fayez_search_suggest():
    q = (request.args.get('q') or '').strip()[:100]
    products = _rank_products(get_db(), q, limit=7) if len(q) >= 2 else []
    return jsonify({'products': [dict(id=p['id'], name=p['name'], sku=p['sku'], brand=p['brand'] or '', price=p['price'], image=p['image'], category=p['category_name']) for p in products]})


@app.route('/shop')
def shop():
    db = get_db()
    cat = request.args.get('cat', '').strip()
    brand_filter = ' '.join((request.args.get('brand') or '').strip().split())[:80]
    q = ' '.join((request.args.get('q') or '').strip().split())[:100]
    if q or cat:
        _fayez_track_customer_event('shop_filter', None, ('q=' + q + '; cat=' + cat)[:250])
    if q:
        _fayez_track_customer_event('search', None, q)
    params = []
    where = ["COALESCE(TRIM(p.image),'') <> ''", "COALESCE(p.is_active,1)=1"]
    if cat:
        where.append('p.category_id = ?'); params.append(cat)
    if brand_filter:
        where.append("LOWER(COALESCE(p.brand,'')) LIKE ?"); params.append('%' + brand_filter.casefold() + '%')
    try:
        min_price = max(0, float(request.args.get('min_price') or 0))
        max_raw = request.args.get('max_price')
        max_price = max(0, float(max_raw)) if max_raw else None
        if min_price: where.append('p.price >= ?'); params.append(min_price)
        if max_price is not None: where.append('p.price <= ?'); params.append(max_price)
    except ValueError:
        min_price, max_price = 0, None
        flash('দামের ফিল্টার সঠিক নয়।', 'warning')
    stock_only = request.args.get('stock') == '1'
    if stock_only: where.append('p.stock > 0')
    sort = request.args.get('sort', 'relevance' if q else 'newest')
    if q:
        candidates = _rank_products(db, q, limit=2500)
        products = [p for p in candidates if (p['image'] or '').strip() and (not cat or str(p['category_id']) == cat)
                    and (not brand_filter or brand_filter.casefold() in (p['brand'] or '').casefold())
                    and float(p['price'] or 0) >= min_price
                    and (max_price is None or float(p['price'] or 0) <= max_price)
                    and (not stock_only or int(p['stock'] or 0) > 0)]
    else:
        sql = "SELECT p.* FROM products p WHERE 1=1"
        if where: sql += ' AND ' + ' AND '.join(where)
        order_by = {'price_low':'p.price ASC', 'price_high':'p.price DESC', 'name':'p.name COLLATE NOCASE ASC', 'popular':'p.id DESC', 'newest':'p.id DESC'}.get(sort, 'p.id DESC')
        products = db.execute(sql + ' ORDER BY ' + order_by + ' LIMIT 2500', params).fetchall()
    if sort == 'price_low': products = sorted(products, key=lambda p: float(p['price'] or 0))
    elif sort == 'price_high': products = sorted(products, key=lambda p: float(p['price'] or 0), reverse=True)
    elif sort == 'name': products = sorted(products, key=lambda p: (p['name'] or '').casefold())
    elif sort == 'newest': products = sorted(products, key=lambda p: int(p['id']), reverse=True)
    if q and not products:
        _fayez_track_customer_event('search_no_results', None, q)
    categories = db.execute('SELECT id,name FROM categories WHERE slug IN (%s) ORDER BY name' % ','.join('?' for _ in CURATED_CATEGORY_SLUGS), CURATED_CATEGORY_SLUGS).fetchall()
    body = r"""<style>
    .sr-wrap{max-width:1400px;margin:30px auto;padding:0 18px}.sr-head{background:linear-gradient(120deg,#201b4c,#4c43a2);color:#fff;border-radius:20px;padding:25px 28px;margin-bottom:22px}.sr-head h1{font-size:clamp(1.5rem,3vw,2.25rem);font-weight:850;margin:0}.sr-head p{color:#e3e0ff;margin:8px 0 0}.sr-filter-title{font-weight:850;margin-bottom:15px}.sr-filter-group{border-top:1px solid #eceef3;padding:15px 0}.sr-grid{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:16px}.sr-card{position:relative;display:flex;flex-direction:column;text-decoration:none;color:#1b2032;background:#fff;border:1px solid #e8eaf0;border-radius:16px;padding:12px;transition:.2s;min-width:0}.sr-card:hover{transform:translateY(-4px);box-shadow:0 14px 32px #18204412;border-color:#d5d0ff}.sr-card img{width:100%;height:190px;object-fit:contain;background:#f8f9fc;border-radius:11px}.sr-card .nm{font-weight:750;line-height:1.4;min-height:42px;margin:12px 0 5px}.sr-card .pr{font-size:1.15rem;font-weight:850;color:#30266f}.sr-card .sku{font-size:.72rem;color:#8990a2}.sr-toolbar{display:flex;justify-content:space-between;align-items:center;gap:12px;flex-wrap:wrap;background:#fff;border:1px solid #e8eaf0;border-radius:13px;padding:12px 15px;margin-bottom:14px}.sr-empty{background:#fff;border:1px solid #e8eaf0;border-radius:18px;padding:45px 20px;text-align:center}.sr-suggestion{display:inline-block;background:#f0efff;color:#4d42b1;border-radius:30px;padding:7px 13px;margin:5px;text-decoration:none;font-weight:700}
    @media(max-width:1050px){.sr-grid{grid-template-columns:repeat(3,minmax(0,1fr))}}@media(max-width:760px){.sr-wrap{padding:0 10px}.sr-grid{grid-template-columns:repeat(2,minmax(0,1fr));gap:10px}.sr-card img{height:145px}.sr-head{padding:20px}.sr-filter-title{margin-bottom:8px}}
    </style>
    <div class="sr-wrap">
      <section class="sr-head"><div class="small fw-bold text-uppercase" style="letter-spacing:1.5px;color:#c9c4ff">FAYEZ SMART SEARCH</div><h1>{% if q %}“{{ q }}” — সার্চ ফলাফল{% else %}সব পণ্য খুঁজে দেখুন{% endif %}</h1><p>{{ products|length }}টি প্রাসঙ্গিক পণ্য পাওয়া গেছে · দাম, ক্যাটাগরি ও স্টক দিয়ে ফিল্টার করুন</p></section>
      <div class="search-layout">
        <aside class="search-filters"><div class="sr-filter-title"><i class="fa fa-sliders me-2"></i>ফিল্টার</div><form method="get" action="/shop">
          <input type="hidden" name="q" value="{{ q }}">
          <div class="sr-filter-group"><label class="d-block mb-2">ক্যাটাগরি</label><select class="form-select" name="cat"><option value="">সব ক্যাটাগরি</option>{% for c in categories %}<option value="{{ c.id }}" {% if cat==c.id|string %}selected{% endif %}>{{ c.name }}</option>{% endfor %}</select></div>
          <div class="sr-filter-group"><label class="d-block mb-2">ব্র্যান্ড</label><input class="form-control" type="search" name="brand" value="{{ request.args.get('brand','') }}" placeholder="যেমন: Apple, Samsung"></div>
          <div class="sr-filter-group"><label class="d-block mb-2">দামের সীমা (৳)</label><input class="form-control mb-2" type="number" min="0" name="min_price" value="{{ request.args.get('min_price','') }}" placeholder="সর্বনিম্ন দাম"><input class="form-control" type="number" min="0" name="max_price" value="{{ request.args.get('max_price','') }}" placeholder="সর্বোচ্চ দাম"></div>
          <div class="sr-filter-group"><label><input type="checkbox" name="stock" value="1" {% if request.args.get('stock')=='1' %}checked{% endif %}> শুধু স্টকে আছে</label></div>
          <input type="hidden" name="sort" value="{{ sort }}"><button class="btn btn-primary w-100 mt-2">ফিল্টার প্রয়োগ</button><a href="/shop{% if q %}?q={{ q|urlencode }}{% endif %}" class="btn btn-light w-100 mt-2">ফিল্টার মুছুন</a>
        </form></aside>
        <section><div class="sr-toolbar"><span class="fw-bold">{{ products|length }}টি পণ্য</span><form method="get" class="d-flex align-items-center gap-2"><input type="hidden" name="q" value="{{ q }}"><input type="hidden" name="cat" value="{{ cat }}"><input type="hidden" name="brand" value="{{ request.args.get('brand','') }}"><input type="hidden" name="min_price" value="{{ request.args.get('min_price','') }}"><input type="hidden" name="max_price" value="{{ request.args.get('max_price','') }}"><input type="hidden" name="stock" value="{{ request.args.get('stock','') }}"><label class="small text-secondary">সাজান:</label><select name="sort" class="form-select form-select-sm" onchange="this.form.submit()"><option value="relevance" {% if sort=='relevance' %}selected{% endif %}>সেরা মিল</option><option value="newest" {% if sort=='newest' %}selected{% endif %}>নতুন পণ্য</option><option value="price_low" {% if sort=='price_low' %}selected{% endif %}>দাম কম থেকে বেশি</option><option value="price_high" {% if sort=='price_high' %}selected{% endif %}>দাম বেশি থেকে কম</option><option value="name" {% if sort=='name' %}selected{% endif %}>নাম অনুযায়ী</option></select></form></div>
        {% if products %}<div class="sr-grid">{% for p in products %}<a class="sr-card" href="/product/{{ p.id }}">{% if p.discount_percent %}<span class="badge bg-danger position-absolute" style="top:19px;left:19px">{{ p.discount_percent }}% ছাড়</span>{% endif %}{% if p.image %}<img src="{{ p.image }}" alt="{{ p.name }}" loading="lazy">{% else %}<div class="d-flex align-items-center justify-content-center bg-light rounded" style="height:190px;color:#9aa0ad">ছবি নেই</div>{% endif %}<div class="nm">{{ p.name }}</div>{% if p.brand %}<div class="small text-secondary">{{ p.brand }}</div>{% endif %}<div class="pr">৳ {{ '%.0f'|format(p.price) }}</div><div class="sku">SKU: {{ p.sku }} · {% if p.stock>0 %}<span class="text-success">স্টকে আছে</span>{% else %}<span class="text-danger">স্টক শেষ</span>{% endif %}</div><span class="btn btn-outline-primary btn-sm mt-3">বিস্তারিত দেখুন</span></a>{% endfor %}</div>
        {% else %}<div class="sr-empty"><i class="fa fa-magnifying-glass fa-3x text-secondary mb-3"></i><h4 class="fw-bold">এই শব্দে পণ্য পাওয়া যায়নি</h4><p class="text-secondary">বানান একটু বদলে, মডেল নম্বর দিয়ে অথবা ক্যাটাগরি বেছে আবার চেষ্টা করুন।</p><a href="/shop" class="sr-suggestion">সব পণ্য</a><a href="/shop?q=gaming" class="sr-suggestion">Gaming</a><a href="/shop?q=electronics" class="sr-suggestion">Electronics</a></div>{% endif %}</section>
      </div>
    </div>"""
    return render_template_string(BASE_HTML.replace('{% block content %}{% endblock %}', body), products=products, categories=categories, q=q, cat=cat, sort=sort)


# Privacy-conscious customer activity analytics; additive only.
def _fayez_track_customer_event(event_type, product_id=None, detail=None):
    customer_id=session.get("customer_id")
    if not customer_id: return
    try:
        db=get_db()
        db.execute("INSERT INTO customer_activity(customer_id,event_type,product_id,detail,created_at) VALUES(?,?,?,?,CURRENT_TIMESTAMP)",(int(customer_id),str(event_type)[:40],product_id,str(detail)[:250] if detail is not None else None))
        db.commit()
    except Exception: pass  # analytics must not interrupt checkout
def _fayez_init_customer_activity():
    db=get_db()
    db.execute("CREATE TABLE IF NOT EXISTS customer_activity (id INTEGER PRIMARY KEY AUTOINCREMENT, customer_id INTEGER NOT NULL, event_type TEXT NOT NULL, product_id INTEGER, detail TEXT, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)")
    db.execute("CREATE INDEX IF NOT EXISTS idx_customer_activity_customer ON customer_activity(customer_id,id DESC)")
    db.commit()

@app.route('/product/<int:pid>', methods=['GET', 'POST'])
def product_detail(pid):
    db = get_db()
    p = db.execute("SELECT products.*, categories.name AS cat_name FROM products LEFT JOIN categories ON products.category_id=categories.id WHERE products.id=? AND COALESCE(products.is_active,1)=1", (pid,)).fetchone()

    if not p or not (p['image'] or '').strip():
        # Products without an individual image stay in admin for correction,
        # but are not customer-visible until a proper product photo is added.
        return redirect(url_for('shop'))

    _fayez_track_customer_event('product_view', pid, f"{p['name']} | category={p['cat_name'] or 'Uncategorized'}")

    if request.method == 'POST':
        if not session.get('customer_id'):
            flash('রেটিং ও রিভিউ দিতে প্রথমে লগইন করুন।', 'warning')
            return redirect(url_for('customer_login'))
        try:
            rating = max(1, min(5, int(request.form.get('rating', 5))))
        except (TypeError, ValueError):
            rating = 5
        comment = (request.form.get('comment') or '').strip()[:2000]
        if not comment:
            flash('রিভিউ লেখাটি খালি রাখা যাবে না।', 'warning')
        else:
            buyer = db.execute('''SELECT 1 FROM orders o JOIN order_items oi ON oi.order_id=o.id
                WHERE o.customer_id=? AND oi.product_id=? LIMIT 1''', (session['customer_id'], pid)).fetchone()
            if not buyer:
                flash('শুধু এই পণ্যটি অর্ডার করেছেন এমন গ্রাহক রিভিউ দিতে পারবেন।', 'warning')
            else:
                already = db.execute('SELECT id FROM reviews WHERE product_id=? AND customer_id=?', (pid, session['customer_id'])).fetchone()
                if already:
                    flash('আপনি এই পণ্যে ইতিমধ্যে রিভিউ দিয়েছেন।', 'info')
                else:
                    db.execute('INSERT INTO reviews (product_id, customer_id, customer_name, rating, comment) VALUES (?, ?, ?, ?, ?)',
                               (pid, session['customer_id'], session['customer_name'], rating, comment))
                    db.commit()
                    flash('আপনার রিভিউ সফলভাবে যুক্ত হয়েছে!', 'success')
        return redirect(url_for('product_detail', pid=pid) + '#reviews')

    viewed = session.get('recently_viewed', [])
    session['recently_viewed'] = ([pid] + [x for x in viewed if x != pid])[:12]
    reviews = db.execute('SELECT * FROM reviews WHERE product_id=? ORDER BY id DESC', (pid,)).fetchall()
    has_purchased = False
    if session.get('customer_id'):
        has_purchased = bool(db.execute('''SELECT 1 FROM orders o JOIN order_items oi ON oi.order_id=o.id
            WHERE o.customer_id=? AND oi.product_id=? LIMIT 1''', (session['customer_id'], pid)).fetchone())
    stats = db.execute('SELECT COUNT(*) AS total, COALESCE(AVG(rating),0) AS average FROM reviews WHERE product_id=?', (pid,)).fetchone()
    related_products = db.execute('''SELECT * FROM products WHERE COALESCE(is_active,1)=1 AND category_id=? AND id!=? AND COALESCE(TRIM(image),'')<>''
        ORDER BY CASE WHEN stock>0 THEN 0 ELSE 1 END, ABS(price-?) ASC LIMIT 8''',
        (p['category_id'], pid, p['price'])).fetchall()
    images = []
    for key in ('image', 'image2', 'image3'):
        value = (p[key] or '').strip()
        if value and value not in images:
            images.append(value)

    body = r'''<style>
    .pd-wrap{max-width:1440px;margin:30px auto;padding:0 18px;color:#172033}
    .pd-crumb{font-size:.88rem;color:#64748b;margin-bottom:18px}.pd-crumb a{color:#475569;text-decoration:none}
    .pd-main{display:grid;grid-template-columns:minmax(0,1.12fr) minmax(330px,.9fr) minmax(260px,.62fr);gap:22px;align-items:start}
    .pd-panel{background:#fff;border:1px solid #e7eaf0;border-radius:18px;padding:22px;box-shadow:0 5px 24px rgba(15,23,42,.045)}
    .pd-gallery{position:sticky;top:18px}.pd-stage{height:480px;background:#f7f8fb;border-radius:14px;display:flex;align-items:center;justify-content:center;overflow:hidden;cursor:zoom-in}
    .pd-stage img{width:100%;height:100%;object-fit:contain;transition:transform .25s}.pd-stage.zoomed img{transform:scale(1.65)}
    .pd-thumbs{display:flex;gap:10px;flex-wrap:wrap;margin-top:12px}.pd-thumb{width:76px;height:76px;border:1px solid #dce1e9;border-radius:10px;padding:4px;background:#fff;cursor:pointer}.pd-thumb.active{border:2px solid #635bdb}.pd-thumb img{width:100%;height:100%;object-fit:contain;border-radius:6px}
    .pd-title{font-size:clamp(1.45rem,2vw,2rem);font-weight:800;line-height:1.25;letter-spacing:-.5px}.pd-price{font-size:2rem;font-weight:850;color:#211b55}.pd-old{color:#94a3b8;text-decoration:line-through}.pd-off{color:#b42318;background:#fff0ed;border-radius:20px;padding:5px 10px;font-weight:700;font-size:.85rem}
    .pd-stars{color:#f59e0b}.pd-divider{border:0;border-top:1px solid #edf0f4;margin:18px 0}.pd-buy{position:sticky;top:18px}.pd-buy .btn{border-radius:11px;font-weight:750;padding:13px}.pd-qty{width:132px}.pd-stock{font-weight:700}.pd-stock.ok{color:#16834a}.pd-stock.no{color:#b42318}.pd-feature{display:flex;gap:10px;align-items:flex-start;color:#475569;font-size:.9rem;margin:12px 0}.pd-feature i{color:#635bdb;width:18px;margin-top:3px}.pd-chip{display:inline-flex;border:1px solid #dce1e9;border-radius:8px;padding:7px 10px;margin:3px;font-size:.88rem}
    .pd-side-title{font-weight:800;font-size:1.08rem}.pd-related{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:14px}.pd-card{display:block;color:inherit;text-decoration:none;border:1px solid #e7eaf0;border-radius:14px;padding:12px;background:#fff;transition:.2s}.pd-card:hover{transform:translateY(-3px);box-shadow:0 8px 22px #10182812}.pd-card img{width:100%;height:155px;object-fit:contain;background:#f8fafc;border-radius:9px}.pd-card-name{font-weight:700;margin:10px 0 5px;min-height:42px}.pd-empty-image{height:100%;width:100%;display:flex;flex-direction:column;align-items:center;justify-content:center;color:#94a3b8;gap:10px}.pd-reviews{scroll-margin-top:20px}
    @media(max-width:1100px){.pd-main{grid-template-columns:minmax(0,1fr) minmax(0,1fr)}.pd-buy{position:static;grid-column:1/-1}.pd-gallery{position:static}}
    @media(max-width:650px){.pd-wrap{padding:0 12px;margin:18px auto}.pd-main{grid-template-columns:1fr;gap:12px}.pd-panel{padding:15px}.pd-stage{height:330px}.pd-related{grid-template-columns:repeat(2,minmax(0,1fr))}.pd-buy{grid-column:auto}.pd-title{font-size:1.35rem}}
    </style>
    <main class="pd-wrap">
      <div class="pd-crumb"><a href="/">হোম</a> › <a href="/shop">শপ</a> › {{ p.cat_name or 'পণ্য' }} › <b>{{ p.name }}</b></div>
      <div class="pd-main">
        <section class="pd-panel pd-gallery">
          <div class="pd-stage" id="pdStage" onclick="this.classList.toggle('zoomed')">
            {% if images %}<img id="pdMainImage" src="{{ images[0] }}" alt="{{ p.name }}" onerror="this.style.display='none';document.getElementById('pdImageFallback').style.display='flex'">{% endif %}
            <div class="pd-empty-image" id="pdImageFallback" style="display:{% if images %}none{% else %}flex{% endif %}"><i class="fa fa-image fa-3x"></i><b>এই পণ্যের ছবি যোগ করা হয়নি</b><small>অ্যাডমিন প্যানেল থেকে আলাদা পণ্যের ছবি যোগ করুন</small></div>
          </div>
          {% if images|length > 1 %}<div class="pd-thumbs">{% for image in images %}<button type="button" class="pd-thumb {% if loop.first %}active{% endif %}" onclick="pdChangeImage(this, {{ image|tojson }})" aria-label="ছবি {{ loop.index }}"><img src="{{ image }}" alt="{{ p.name }} ছবি {{ loop.index }}"></button>{% endfor %}</div>{% endif %}
          <div class="small text-secondary mt-3"><i class="fa fa-magnifying-glass-plus me-1"></i>ছবির ওপর ক্লিক করলে জুম হবে</div>
        </section>

        <section class="pd-panel">
          <div class="d-flex justify-content-between align-items-center gap-2 mb-3"><span class="badge rounded-pill text-bg-light border">{{ p.cat_name or 'Fayez Collection' }}</span><span class="small text-secondary">SKU: {{ p.sku }}</span></div>
          <h1 class="pd-title">{{ p.name }}</h1>
          <div class="d-flex align-items-center flex-wrap gap-2 mt-3"><span class="pd-stars">{% for i in range(1,6) %}<i class="fa {% if i <= (stats.average|round(0, 'common')|int) %}fa-star{% else %}fa-star-o{% endif %}"></i>{% endfor %}</span><a class="small text-decoration-none" href="#reviews">{{ '%.1f'|format(stats.average) }} / 5 · {{ stats.total }}টি রিভিউ</a><span class="text-secondary small">|</span><span class="small text-success">বিশ্বস্ত শপিং অভিজ্ঞতা</span></div>
          <hr class="pd-divider">
          <div class="d-flex align-items-baseline flex-wrap gap-3"><span class="pd-price">৳ {{ '%.0f'|format(p.price) }}</span>{% if p.old_price and p.old_price > p.price %}<span class="pd-old">৳ {{ '%.0f'|format(p.old_price) }}</span>{% endif %}{% if p.discount_percent > 0 %}<span class="pd-off">{{ p.discount_percent }}% ছাড়</span>{% endif %}</div>
          <div class="small text-secondary mt-1">দাম বাংলাদেশি টাকা (BDT)-তে</div>
          <hr class="pd-divider">
          <div class="mb-3"><b>রং / ভ্যারিয়েন্ট</b><div class="mt-2">{% for color in (p.colors or '').split(',') if color.strip() %}<span class="pd-chip">{{ color.strip() }}</span>{% else %}<span class="text-secondary small">ভ্যারিয়েন্টের তথ্য দেওয়া হয়নি</span>{% endfor %}</div></div>
          <div class="pd-feature"><i class="fa fa-box"></i><span>SKU: {{ p.sku }}</span></div>
          <div class="pd-feature"><i class="fa fa-earth-asia"></i><span>উৎপত্তি: {{ p.country_of_origin or 'তথ্য দেওয়া হয়নি' }}</span></div>
          <div class="pd-feature"><i class="fa fa-warehouse"></i><span class="pd-stock {% if p.stock > 0 %}ok{% else %}no{% endif %}">{% if p.stock > 0 %}স্টকে আছে{% else %}স্টক শেষ · অর্ডার করা যাচ্ছে না{% endif %}</span></div>
          <hr class="pd-divider">
          <h5 class="fw-bold">পণ্যের বিবরণ</h5><p class="text-secondary" style="white-space:pre-line">{{ p.description or 'এই পণ্যের বিস্তারিত বিবরণ এখনো যোগ করা হয়নি।' }}</p>
          <div class="d-flex flex-wrap gap-2 mt-4"><a href="/compare?ids={{ p.id }}" class="btn btn-outline-secondary btn-sm"><i class="fa fa-scale-balanced me-1"></i>তুলনা করুন</a>{% if session.get('customer_id') %}<form action="/customer/wishlist/add/{{ p.id }}" method="post"><button class="btn btn-outline-danger btn-sm"><i class="fa fa-heart me-1"></i>Wishlist</button></form>{% else %}<a href="/customer/login" class="btn btn-outline-danger btn-sm"><i class="fa fa-heart me-1"></i>Wishlist</a>{% endif %}</div>
        </section>

        <aside class="pd-panel pd-buy">
          <div class="pd-side-title">কেনার অপশন</div>
          <div class="d-flex justify-content-between mt-3"><span class="text-secondary">আজকের দাম</span><b>৳ {{ '%.0f'|format(p.price) }}</b></div>
          <div class="d-flex justify-content-between mt-2"><span class="text-secondary">ডেলিভারি</span><b>চেকআউটে হিসাব হবে</b></div>
          <hr class="pd-divider">
          {% if p.stock > 0 %}
          <form action="/cart/add/{{ p.id }}" method="POST" class="mb-2">
            <label class="form-label fw-bold small">পরিমাণ</label><div class="input-group pd-qty mb-3"><button class="btn btn-outline-secondary" type="button" onclick="pdQty(-1)">−</button><input class="form-control text-center" id="pdQty" type="number" name="quantity" min="1" max="{{ p.stock }}" value="1"><button class="btn btn-outline-secondary" type="button" onclick="pdQty(1)">+</button></div>
            <button class="btn btn-warning w-100 mb-2" type="submit"><i class="fa fa-cart-plus me-2"></i>কার্টে যোগ করুন</button>
          </form>
          <form action="/cart/buy-now/{{ p.id }}" method="POST"><input type="hidden" name="quantity" id="pdBuyQty" value="1"><button class="btn btn-primary w-100" type="submit"><i class="fa fa-bolt me-2"></i>এখনই কিনুন</button></form>
          {% else %}<button class="btn btn-secondary w-100" disabled>স্টক শেষ</button>{% endif %}
          <hr class="pd-divider">
          <div class="pd-feature"><i class="fa fa-shield-halved"></i><span>নিরাপদ অর্ডার প্রসেসিং</span></div>
          <div class="pd-feature"><i class="fa fa-truck-fast"></i><span>বাংলাদেশজুড়ে ডেলিভারি</span></div>
          <div class="pd-feature"><i class="fa fa-headset"></i><span>প্রয়োজনে কাস্টমার সাপোর্ট</span></div>
          <a href="/cart" class="btn btn-outline-dark w-100 mt-2">আমার কার্ট দেখুন</a>
        </aside>
      </div>

      <section class="pd-panel pd-reviews mt-4" id="reviews">
        <div class="d-flex justify-content-between align-items-center flex-wrap gap-2"><h4 class="fw-bold mb-0">গ্রাহক রিভিউ</h4><span class="pd-stars">★ {{ '%.1f'|format(stats.average) }} / 5 · {{ stats.total }}টি রিভিউ</span></div>
        {% if reviews %}<div class="row g-3 mt-2">{% for r in reviews %}<div class="col-md-6"><div class="border rounded-3 p-3 h-100"><div class="d-flex justify-content-between"><b>{{ r.customer_name }}</b><span class="pd-stars">{% for i in range(r.rating) %}★{% endfor %}</span></div><p class="text-secondary mb-0 mt-2">{{ r.comment }}</p></div></div>{% endfor %}</div>{% else %}<p class="text-secondary mt-3">এখনো কোনো রিভিউ নেই। আপনার অভিজ্ঞতা শেয়ার করুন।</p>{% endif %}
        {% if has_purchased %}<form method="POST" class="mt-4" style="max-width:650px"><h5 class="fw-bold">আপনার রিভিউ লিখুন</h5><div class="row g-2"><div class="col-sm-4"><select class="form-select" name="rating" required><option value="5">★★★★★ · ৫</option><option value="4">★★★★ · ৪</option><option value="3">★★★ · ৩</option><option value="2">★★ · ২</option><option value="1">★ · ১</option></select></div><div class="col-12"><textarea class="form-control" name="comment" rows="3" maxlength="2000" placeholder="পণ্যটি সম্পর্কে আপনার মতামত লিখুন" required></textarea></div><div class="col-12"><button class="btn btn-dark" type="submit">রিভিউ জমা দিন</button></div></div></form>{% elif session.get('customer_id') %}<p class="small text-secondary mt-4">এই পণ্যটি অর্ডার সম্পন্ন করার পর রিভিউ দিতে পারবেন।</p>{% else %}<p class="small text-secondary mt-4"><a href="/customer/login">লগইন</a> করে অর্ডার করা পণ্যের রিভিউ দিতে পারবেন।</p>{% endif %}
      </section>

      {% if related_products %}<section class="mt-5"><div class="d-flex justify-content-between align-items-end mb-3"><div><div class="small text-uppercase fw-bold text-secondary">YOU MAY ALSO LIKE</div><h3 class="fw-bold mb-0">একই ক্যাটাগরির আরও পণ্য</h3></div><a href="/shop?cat={{ p.category_id }}" class="text-decoration-none">সব দেখুন →</a></div><div class="pd-related">{% for rp in related_products %}<a class="pd-card" href="/product/{{ rp.id }}"><img src="{{ rp.image }}" alt="{{ rp.name }}" onerror="this.style.opacity='.15'"><div class="pd-card-name">{{ rp.name }}</div><b>৳ {{ '%.0f'|format(rp.price) }}</b>{% if rp.stock > 0 %}<small class="text-success d-block mt-1">স্টকে আছে</small>{% else %}<small class="text-danger d-block mt-1">স্টক নেই</small>{% endif %}</a>{% endfor %}</div></section>{% endif %}
    </main>
    <script>
      function pdChangeImage(button, src){document.querySelectorAll('.pd-thumb').forEach(x=>x.classList.remove('active'));button.classList.add('active');const img=document.getElementById('pdMainImage');const fallback=document.getElementById('pdImageFallback');if(img){img.style.display='block';img.src=src;}if(fallback)fallback.style.display='none';document.getElementById('pdStage').classList.remove('zoomed');}
      function pdQty(delta){const input=document.getElementById('pdQty');if(!input)return;const max=parseInt(input.max||'999',10);input.value=Math.max(1,Math.min(max,(parseInt(input.value||'1',10)+delta)));const buy=document.getElementById('pdBuyQty');if(buy)buy.value=input.value;}
      document.getElementById('pdQty')?.addEventListener('change',e=>{const buy=document.getElementById('pdBuyQty');if(buy)buy.value=e.target.value;});
    </script>'''
    return render_template_string(BASE_HTML.replace('{% block content %}{% endblock %}', body), p=p, reviews=reviews,
                                  related_products=related_products, stats=stats, images=images, has_purchased=has_purchased)

@app.route('/cart/add/<int:pid>', methods=['POST'])
def add_to_cart(pid):
    if not session.get('customer_id'):
        flash('কার্টে পণ্য যোগ করতে প্রথমে লগইন করুন।', 'warning')
        return redirect(url_for('customer_login'))
    try:
        qty = max(1, min(99, int(request.form.get('quantity', 1))))
    except (TypeError, ValueError):
        qty = 1
    db = get_db()
    product = db.execute('SELECT id, stock FROM products WHERE id=?', (pid,)).fetchone()
    if not product or product['stock'] <= 0:
        flash('এই পণ্যটি বর্তমানে স্টকে নেই।', 'warning')
        return redirect(url_for('product_detail', pid=pid))
    item = db.execute('SELECT * FROM cart WHERE customer_id = ? AND product_id = ?', (session['customer_id'], pid)).fetchone()
    existing_qty = item['quantity'] if item else 0
    if existing_qty + qty > product['stock']:
        flash(f"স্টকে সর্বোচ্চ {product['stock']}টি আছে।", 'warning')
        return redirect(url_for('product_detail', pid=pid))
    if item:
        db.execute('UPDATE cart SET quantity = quantity + ? WHERE id = ?', (qty, item['id']))
    else:
        db.execute('INSERT INTO cart (customer_id, product_id, quantity) VALUES (?, ?, ?)', (session['customer_id'], pid, qty))
    db.commit()
    _fayez_track_customer_event('cart_add', pid, f'quantity={qty}')
    flash('পণ্য সফলভাবে কার্টে যোগ হয়েছে! কার্টের সংখ্যা আপডেট হয়েছে।', 'success')
    return redirect(url_for('product_detail', pid=pid))

@app.route('/cart/buy-now/<int:pid>', methods=['POST'])
def buy_now(pid):
    if not session.get('customer_id'):
        flash('এখনই কিনতে প্রথমে লগইন করুন।', 'warning')
        return redirect(url_for('customer_login'))
    try:
        qty = max(1, min(99, int(request.form.get('quantity', 1))))
    except (TypeError, ValueError):
        qty = 1
    db = get_db()
    product = db.execute('SELECT id, stock FROM products WHERE id=?', (pid,)).fetchone()
    if not product or product['stock'] < qty:
        flash('পর্যাপ্ত স্টক নেই।', 'warning')
        return redirect(url_for('product_detail', pid=pid))
    item = db.execute('SELECT * FROM cart WHERE customer_id=? AND product_id=?', (session['customer_id'], pid)).fetchone()
    if item:
        db.execute('UPDATE cart SET quantity=? WHERE id=?', (qty, item['id']))
    else:
        db.execute('INSERT INTO cart(customer_id, product_id, quantity) VALUES(?,?,?)', (session['customer_id'], pid, qty))
    db.commit()
    _fayez_track_customer_event('buy_now', pid, f'quantity={qty}')
    return redirect(url_for('checkout'))

@app.route('/cart/remove/<int:cid>', methods=['POST'])
@customer_required
def remove_cart(cid):
    db = get_db()
    removed = db.execute('SELECT product_id, quantity FROM cart WHERE id=? AND customer_id=?', (cid, session['customer_id'])).fetchone()
    if removed:
        _fayez_track_customer_event('cart_remove', removed['product_id'], f"quantity={removed['quantity']}")
        db.execute('DELETE FROM cart WHERE id = ? AND customer_id = ?', (cid, session['customer_id']))
        db.commit()
    return redirect(url_for('cart_view'))

@app.route('/cart')
@customer_required
def cart_view():
    items = get_db().execute('SELECT cart.id as cid, products.name, products.price, products.image, products.sku, cart.quantity FROM cart JOIN products ON cart.product_id = products.id WHERE cart.customer_id = ? ORDER BY cart.id DESC', (session['customer_id'],)).fetchall()
    total = sum(i['price'] * i['quantity'] for i in items)
    total_qty = sum(i['quantity'] for i in items)
    body = '''
    <style>
      .cart-page{max-width:1050px;margin:38px auto;padding:0 16px}.cart-head{display:flex;justify-content:space-between;align-items:end;gap:12px;margin-bottom:22px}.cart-head h2{font-weight:850;letter-spacing:-.7px}.cart-layout{display:grid;grid-template-columns:minmax(0,1.7fr) minmax(260px,.8fr);gap:20px}.cart-list,.cart-summary{background:#fff;border:1px solid #e9edf4;border-radius:22px;box-shadow:0 12px 35px rgba(20,30,60,.055)}.cart-item{display:grid;grid-template-columns:94px minmax(0,1fr) auto;gap:16px;align-items:center;padding:18px;border-bottom:1px solid #eef0f5}.cart-item:last-child{border-bottom:0}.cart-thumb{width:94px;height:94px;border-radius:15px;object-fit:cover;background:#f3f5f9}.cart-item h6{font-weight:800;margin:0 0 6px}.cart-price{font-weight:850;color:#5145c7;white-space:nowrap}.cart-summary{padding:22px;height:max-content;position:sticky;top:95px}.cart-summary h5{font-weight:850}.cart-empty{background:#fff;border:1px dashed #d8ddea;border-radius:22px;padding:48px 20px;text-align:center}.cart-empty i{font-size:2.5rem;color:#8b83d8;margin-bottom:14px}@media(max-width:760px){.cart-layout{grid-template-columns:1fr}.cart-summary{position:static}.cart-head{align-items:start;flex-direction:column}}@media(max-width:480px){.cart-item{grid-template-columns:72px minmax(0,1fr);gap:12px;padding:13px}.cart-thumb{width:72px;height:82px}.cart-item-action{grid-column:2;display:flex;justify-content:space-between;align-items:center}.cart-price{font-size:.95rem}}
    </style>
    <main class="cart-page"><div class="cart-head"><div><div class="eyebrow">YOUR SHOPPING BAG</div><h2 class="mb-1">আপনার শপিং কার্ট</h2><p class="text-secondary mb-0">পছন্দের পণ্যগুলো একবার দেখে নিন, তারপর অর্ডার সম্পন্ন করুন।</p></div><a href="/shop" class="btn btn-outline-dark rounded-pill px-4"><i class="fa fa-arrow-left me-2"></i>কেনাকাটা চালিয়ে যান</a></div>
      {% if items %}<div class="cart-layout"><section class="cart-list">{% for i in items %}<article class="cart-item"><img class="cart-thumb" src="{{ i.image or 'https://images.unsplash.com/photo-1441986300917-64674bd600d8?w=400' }}" alt="{{ i.name }}" onerror="this.onerror=null;this.src='https://images.unsplash.com/photo-1441986300917-64674bd600d8?w=400'"><div><h6>{{ i.name }}</h6><small class="text-secondary">SKU: {{ i.sku or 'Fayez Product' }}</small><div class="text-secondary small mt-2">৳ {{ '%.2f'|format(i.price) }} × {{ i.quantity }}</div></div><div class="cart-item-action text-end"><div class="cart-price">৳ {{ '%.2f'|format(i.price * i.quantity) }}</div><form action="/cart/remove/{{ i.cid }}" method="POST" class="mt-2"><button class="btn btn-sm btn-light text-danger border rounded-pill px-3" aria-label="কার্ট থেকে সরান"><i class="fa fa-trash me-1"></i> সরান</button></form></div></article>{% endfor %}</section>
      <aside class="cart-summary"><h5>অর্ডার সামারি</h5><p class="text-secondary small">আপনার নির্বাচিত পণ্যের হিসাব</p><div class="d-flex justify-content-between mb-2"><span class="text-secondary">পণ্যের সংখ্যা</span><b>{{ total_qty }} টি</b></div><div class="d-flex justify-content-between mb-3"><span class="text-secondary">সাবটোটাল</span><b>৳ {{ '%.2f'|format(total) }}</b></div><hr><div class="d-flex justify-content-between align-items-center mb-3"><b>সর্বমোট</b><strong class="fs-4 text-primary">৳ {{ '%.2f'|format(total) }}</strong></div><small class="text-secondary d-block mb-3">ডেলিভারি চার্জ চেকআউটে ঠিকানা অনুযায়ী যোগ হবে।</small><a href="/checkout" class="btn btn-primary w-100 py-3 fw-bold rounded-pill">চেকআউটে এগিয়ে যান <i class="fa fa-arrow-right ms-2"></i></a><div class="text-center text-secondary small mt-3"><i class="fa fa-shield-halved me-1"></i> নিরাপদ অর্ডার প্রসেস</div></aside></div>
      {% else %}<div class="cart-empty"><i class="fa fa-bag-shopping d-block"></i><h4 class="fw-bold">আপনার কার্ট এখনো খালি</h4><p class="text-secondary">পছন্দের পণ্য কার্টে যোগ করুন—সব পণ্য এখানে দেখতে পাবেন।</p><a href="/shop" class="btn btn-primary rounded-pill px-4">শপিং শুরু করুন</a></div>{% endif %}</main>'''
    return render_template_string(BASE_HTML.replace('{% block content %}{% endblock %}', body), items=items, total=total, total_qty=total_qty)

@app.route('/checkout', methods=['GET', 'POST'])
@customer_required
def checkout():
    db = get_db()
    items = db.execute('SELECT products.id, products.name, products.price, cart.quantity FROM cart JOIN products ON cart.product_id = products.id WHERE cart.customer_id = ?', (session['customer_id'],)).fetchall()
    if not items: return redirect(url_for('shop'))
    subtotal = sum(i['price'] * i['quantity'] for i in items)
    
    discount_amount = 0.0
    applied_coupon = session.get('applied_coupon', '')
    if applied_coupon:
        coup = db.execute('SELECT * FROM coupons WHERE code = ?', (applied_coupon,)).fetchone()
        if coup:
            valid = bool(coup['is_active']) and (not coup['expires_at'] or str(coup['expires_at']) >= datetime.now().strftime('%Y-%m-%d')) and (not coup['max_uses'] or int(coup['used_count'] or 0) < int(coup['max_uses']))
            if valid:
                discount_amount = min(subtotal, float(coup['discount_amount'] or 0)) if coup['discount_type'] == 'fixed' else min(subtotal, subtotal * (float(coup['discount_percent'] or 0) / 100.0))
            else:
                session.pop('applied_coupon', None); applied_coupon = ''

    if request.method == 'POST':
        action = request.form.get('action')
        if action == 'apply_coupon':
            code = request.form.get('coupon_code', '').strip().upper()
            coup = db.execute('SELECT * FROM coupons WHERE code = ?', (code,)).fetchone()
            if coup:
                valid = bool(coup['is_active']) and (not coup['expires_at'] or str(coup['expires_at']) >= datetime.now().strftime('%Y-%m-%d')) and (not coup['max_uses'] or int(coup['used_count'] or 0) < int(coup['max_uses']))
                if valid:
                    session['applied_coupon'] = code
                    flash(f'কুপন "{code}" সফলভাবে অ্যাপ্লাই হয়েছে!', 'success')
                else:
                    session.pop('applied_coupon', None)
                    flash('এই কুপনটি বন্ধ, মেয়াদোত্তীর্ণ অথবা ব্যবহারের সীমা শেষ।', 'danger')
            else:
                session.pop('applied_coupon', None)
                flash('ভুল কুপন কোড!', 'danger')
            return redirect(url_for('checkout'))
            
        recipient_choice = request.form.get('recipient_choice', 'account').strip()
        recipient_name = (session.get('customer_name', '') if recipient_choice == 'account' else request.form.get('recipient_name', '').strip())
        if not recipient_name:
            flash('ডেলিভারি গ্রহণকারীর নাম লিখুন।', 'warning')
            return redirect(url_for('checkout'))
        division = request.form.get('division')
        district = request.form.get('district')
        upazila = (request.form.get('upazila') or request.form.get('upazila_manual') or '').strip()
        address = request.form.get('address')
        payment_method = request.form.get('payment_method')
        sender_phone_raw = (request.form.get('sender_phone') or '').strip()
        try:
            sender_phone = normalize_bd_mobile(sender_phone_raw)
            if not re.fullmatch(r'01[3-9][0-9]{8}', sender_phone):
                raise ValueError('Invalid Bangladesh mobile number')
        except ValueError:
            flash('অর্ডার কনফার্মেশনের জন্য সঠিক ১১ সংখ্যার বাংলাদেশি মোবাইল নম্বর দিন (01XXXXXXXXX)।', 'warning')
            return redirect(url_for('checkout'))
        # Keep the customer's latest delivery contact number on their account as well.
        db.execute('UPDATE customers SET phone=? WHERE id=?',
                   (sender_phone, session['customer_id']))
        trx_id = request.form.get('trx_id', '').strip()
        configured_mfs = {'bKash': BKASH_MERCHANT_NUMBER, 'Nagad': NAGAD_MERCHANT_NUMBER, 'Rocket': ROCKET_MERCHANT_NUMBER}
        if payment_method in configured_mfs:
            if not configured_mfs[payment_method]:
                flash(f'{payment_method} merchant number অ্যাডমিন সেট করেননি। আপাতত Cash on Delivery বেছে নিন।', 'warning')
                return redirect(url_for('checkout'))
            if not trx_id:
                flash('মোবাইল ব্যাংকিং পেমেন্টের জন্য TrxID দিতে হবে।', 'warning')
                return redirect(url_for('checkout'))
        if payment_method not in ('Cash on Delivery', 'bKash', 'Nagad', 'Rocket'):
            flash('সঠিক পেমেন্ট মাধ্যম নির্বাচন করুন।', 'warning')
            return redirect(url_for('checkout'))
        
        delivery_charge = 120.0 if division == 'Dhaka' else 150.0
        total_amount = (subtotal - discount_amount) + delivery_charge
        
        order_id = f"FYZ-{datetime.now().strftime('%y%m%d%H%M%S')}"
        cur = db.cursor()
        if applied_coupon:
            cur.execute("UPDATE coupons SET used_count=COALESCE(used_count,0)+1 WHERE code=?", (applied_coupon,))
        
        cur.execute('''INSERT INTO orders (order_id, customer_id, recipient_name, total_amount, delivery_charge, discount_amount, payment_method, sender_phone, trx_id, division, district, upazila, shipping_address) 
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
                    (order_id, session['customer_id'], recipient_name, total_amount, delivery_charge, discount_amount, payment_method, sender_phone, trx_id, division, district, upazila, address))
        db_oid = cur.lastrowid
        
        for i in items:
            cur.execute('INSERT INTO order_items (order_id, product_id, product_name, quantity, price) VALUES (?, ?, ?, ?, ?)', 
                        (db_oid, i['id'], i['name'], i['quantity'], i['price']))
            cur.execute('UPDATE products SET stock = stock - ? WHERE id = ?', (i['quantity'], i['id']))
            
        cur.execute('DELETE FROM cart WHERE customer_id = ?', (session['customer_id'],))
        session.pop('applied_coupon', None)
        db.commit()
        _fayez_track_customer_event('order_placed', None, f'order_id={order_id}')
        
        flash(f'অর্ডার কনফার্ম হয়েছে! অর্ডার আইডি: {order_id}', 'success')
        return redirect(url_for('invoice', oid=order_id))
        
    body = '''
    <div class="container my-5" style="max-width: 750px;">
        <div class="card p-4 shadow-sm border-0 rounded-4">
            <h4 class="fw-bold mb-4"><i class="fa fa-credit-card text-primary me-2"></i>নিরাপদ চেকআউট ও পেমেন্ট</h4>
            
            <form method="POST" class="mb-4">
                <input type="hidden" name="action" value="apply_coupon">
                <label class="form-label fw-semibold">কুপন কোড (যেমন: FAYEZ10)</label>
                <div class="input-group">
                    <input type="text" class="form-control" name="coupon_code" placeholder="কুপন কোড লিখুন" value="{{ applied_coupon }}">
                    <button class="btn btn-outline-dark" type="submit">অ্যাপ্লাই</button>
                </div>
            </form>

            <form method="POST">
                <div class="row g-3">
                    <div class="col-12">
                        <label class="form-label fw-semibold">ডেলিভারি গ্রহণকারীর নাম</label>
                        <select class="form-select" name="recipient_choice" id="recipientChoice" onchange="toggleRecipientName(this.value)">
                            <option value="account">আমার অ্যাকাউন্টের নাম — {{ session.get('customer_name', '') }}</option>
                            <option value="other">অন্য কারও নামে অর্ডার করব</option>
                        </select>
                        <input class="form-control mt-2" type="text" name="recipient_name" id="recipientName" maxlength="120" placeholder="যিনি পণ্য গ্রহণ করবেন তাঁর নাম" style="display:none" disabled>
                    </div>
                    <div class="col-md-6">
                        <label class="form-label fw-semibold">অর্ডার কনফার্মেশন ও ডেলিভারি মোবাইল নম্বর</label>
                        <input class="form-control" type="tel" name="sender_phone" placeholder="01XXXXXXXXX" value="{{ customer_phone or '' }}" inputmode="numeric" pattern="(88)?01[3-9][0-9]{8}" minlength="11" maxlength="14" autocomplete="tel" required>
                        <small class="text-secondary">১১ সংখ্যার সম্পূর্ণ সচল নম্বর দিন। এই নম্বরে অর্ডার কনফার্মেশনের জন্য যোগাযোগ করা হবে।</small>
                    </div>
                    <div class="col-md-4">
                        <label class="form-label fw-semibold">বিভাগ (Division)</label>
                        <select class="form-select" id="divisionSelect" name="division" onchange="updateDistricts()" required>
                            <option value="">বিভাগ সিলেক্ট করুন</option>
                            <option value="Dhaka">ঢাকা (Dhaka)</option>
                            <option value="Chattogram">চট্টগ্রাম (Chattogram)</option>
                            <option value="Rajshahi">রাজশাহী (Rajshahi)</option>
                            <option value="Khulna">খুলনা (Khulna)</option>
                            <option value="Sylhet">সিলেট (Sylhet)</option>
                            <option value="Barishal">বরিশাল (Barishal)</option>
                            <option value="Rangpur">রংপুর (Rangpur)</option>
                            <option value="Mymensingh">ময়মনসিংহ (Mymensingh)</option>
                        </select>
                    </div>
                    <div class="col-md-4">
                        <label class="form-label fw-semibold">জেলা (District)</label>
                        <select class="form-select" id="districtSelect" name="district" onchange="updateUpazilas()" required>
                            <option value="">প্রথমে বিভাগ সিলেক্ট করুন</option>
                        </select>
                    </div>
                    <div class="col-md-4">
                        <label class="form-label fw-semibold">উপজেলা (Upazila)</label>
                        <select class="form-select" id="upazilaSelect" name="upazila" required>
                            <option value="">প্রথমে জেলা সিলেক্ট করুন</option>
                        </select>
                        <input class="form-control mt-2" id="upazilaManual" name="upazila_manual" type="text" placeholder="আপনার উপজেলা/থানার নাম লিখুন" style="display:none" disabled>
                    </div>
                    <div class="col-12">
                        <label class="form-label fw-semibold">বাসা নম্বর, রোড ও ফোন নম্বর</label>
                        <textarea class="form-control" name="address" rows="2" placeholder="বাসা/রোড নম্বর, ফোন নম্বর ইত্যাদি..." required></textarea>
                    </div>
                    <div class="col-12">
                        <label class="form-label fw-semibold">পেমেন্ট মাধ্যম</label>
                        <select class="form-select" name="payment_method" id="payMethod" onchange="toggleMFS(this.value)">
                            <option value="Cash on Delivery">Cash on Delivery</option>
                            <option value="bKash" data-number="{{ bkash_number }}">bKash — Send Money ({{ bkash_number }})</option>
                            <option value="Nagad" data-number="{{ nagad_number }}">Nagad — Send Money{% if nagad_number %} ({{ nagad_number }}){% else %} (নম্বর সেট করা হয়নি){% endif %}</option>
                            <option value="Rocket" data-number="{{ rocket_number }}">Rocket — Send Money{% if rocket_number %} ({{ rocket_number }}){% else %} (নম্বর সেট করা হয়নি){% endif %}</option>
                        </select>
                        <small class="text-secondary d-block mt-2" id="paymentInstruction">bKash Send Money নম্বর: <b class="text-danger">{{ bkash_number }}</b>। টাকা পাঠানোর পর TrxID লিখুন।</small>
                    </div>
                    <div class="col-12" id="trxBox" style="display:none;">
                        <label class="form-label fw-semibold text-danger">ট্রানজেকশন আইডি (TrxID)</label>
                        <input type="text" class="form-control" name="trx_id" autocomplete="off" aria-label="Transaction ID">
                    </div>
                    
                    <div class="col-12 mt-3">
                        <div class="card bg-light p-3 border-0">
                            <div class="d-flex justify-content-between mb-1"><span>সাবটোটাল:</span> <b>৳ {{ "%.2f"|format(subtotal) }}</b></div>
                            {% if discount_amount > 0 %}<div class="d-flex justify-content-between mb-1 text-success"><span>ডিসকাউন্ট:</span> <b>- ৳ {{ "%.2f"|format(discount_amount) }}</b></div>{% endif %}
                            <div class="d-flex justify-content-between mb-1"><span>ডেলিভারি চার্জ:</span> <b>৳ ১২০.০০ (ঢাকা) / ১৫০.০০ (বাইরে)</b></div>
                            <hr>
                            <div class="d-flex justify-content-between fs-5 fw-bold text-primary"><span>সর্বমোট:</span> <span>৳ {{ "%.2f"|format(subtotal - discount_amount + 120.0) }}</span></div>
                        </div>
                    </div>
                    <div class="col-12 mt-3">
                        <button type="submit" class="btn btn-primary w-100 py-3 fw-bold rounded-pill shadow">অর্ডার কনফার্ম করুন</button>
                    </div>
                </div>
            </form>
        </div>
    </div>
    <script>
        const districtsData = {
            "Dhaka": ["ঢাকা", "ফরিদপুর", "গাজীপুর", "গোপালগঞ্জ", "কিশোরগঞ্জ", "মাদারীপুর", "মানিকগঞ্জ", "মুন্সিগঞ্জ", "নারায়ণগঞ্জ", "নরসিংদী", "রাজবাড়ী", "শরীয়তপুর", "টাঙ্গাইল"],
            "Chattogram": ["চট্টগ্রাম", "বান্দরবান", "ব্রাহ্মণবাড়িয়া", "চাঁদপুর", "কক্সবাজার", "কুমিল্লা", "ফেনী", "খাগড়াছড়ি", "লক্ষ্মীপুর", "নোয়াখালী", "রাঙ্গামাটি"],
            "Rajshahi": ["বগুড়া", "জয়পুরহাট", "নওগাঁ", "নাটোর", "চাঁপাইনবাবগঞ্জ", "পাবনা", "রাজশাহী", "সিরাজগঞ্জ"],
            "Khulna": ["বাগেরহাট", "চুয়াডাঙ্গা", "যশোর", "ঝিনাইদহ", "খুলনা", "কুষ্টিয়া", "মাগুরা", "মেহেরপুর", "নড়াইল", "সাতক্ষীরা"],
            "Sylhet": ["হবিগঞ্জ", "মৌলভীবাজার", "সুনামগঞ্জ", "সিলেট"],
            "Barishal": ["বরগুনা", "বরিশাল", "ভোলা", "ঝালকাঠি", "পটুয়াখালী", "পিরোজপুর"],
            "Rangpur": ["দিনাজপুর", "গাইবান্ধা", "কুড়িগ্রাম", "লালমনিরহাট", "নীলফামারী", "পঞ্চগড়", "রংপুর", "ঠাকুরগাঁও"],
            "Mymensingh": ["জামালপুর", "ময়মনসিংহ", "নেত্রকোণা", "শেরপুর"]
        };

        const upazilasData = {
            "ঢাকা": ["ধানমন্ডি", "গুলশান", "বনানী", "উত্তরা", "মিরপুর", "মোহাম্মদপুর", "তেজগাঁও", "রামপুরা", "সাভার", "কেরানীগঞ্জ"],
            "চট্টগ্রাম": ["কোতোয়ালী", "পাহাড়তলী", "খুলশী", "ডবলমুরিং", "পতেঙ্গা", "সীতাকুণ্ড", "বোয়ালখালী"],
            "রাজশাহী": ["বোয়ালিয়া", "মতিহার", "রাজশাহী সদর", "বাঘা", "চারঘাট"],
            "খুলনা": ["সোনাডাঙ্গা", "খালিশপুর", "দৌলতপুর", "কোতোয়ালী খুলনা", "বটিয়াঘাটা"],
            "সিলেট": ["সিলেট সদর", "দক্ষিণ সুরমা", "বিশ্বনাথ", "গোলাপগঞ্জ", "জকিগঞ্জ"],
            "বরিশাল": ["বরিশাল সদর", "বাবুগঞ্জ", "উজিরপুর", "বাকেরগঞ্জ"],
            "রংপুর": ["রংপুর সদর", "তারাগঞ্জ", "বদরগঞ্জ", "কাউনিয়া"],
            "ময়মনসিংহ": ["ময়মনসিংহ সদর", "ভালুকা", "ত্রিশাল", "মুক্তাগাছা"]
        };

        function updateDistricts() {
            let div = document.getElementById('divisionSelect').value;
            let distSelect = document.getElementById('districtSelect');
            distSelect.innerHTML = '<option value="">জেলা সিলেক্ট করুন</option>';
            document.getElementById('upazilaSelect').innerHTML = '<option value="">প্রথমে জেলা সিলেক্ট করুন</option>';
            if(div && districtsData[div]) {
                districtsData[div].forEach(d => {
                    distSelect.innerHTML += `<option value="${d}">${d}</option>`;
                });
            }
        }

        function updateUpazilas() {
            let dist = document.getElementById('districtSelect').value;
            let upaSelect = document.getElementById('upazilaSelect');
            const manual = document.getElementById('upazilaManual');
            upaSelect.innerHTML = '<option value="">উপজেলা সিলেক্ট করুন</option>';
            let list = upazilasData[dist] || [];
            if(list.length) {
                upaSelect.style.display = 'block'; upaSelect.disabled = false; upaSelect.required = true;
                manual.style.display = 'none'; manual.disabled = true; manual.required = false; manual.value = '';
                list.forEach(u => { upaSelect.innerHTML += `<option value="${u}">${u}</option>`; });
            } else {
                upaSelect.style.display = 'none'; upaSelect.disabled = true; upaSelect.required = false;
                manual.style.display = 'block'; manual.disabled = false; manual.required = true;
            }
        }

        function toggleRecipientName(val) {
            const field = document.getElementById('recipientName');
            const show = val === 'other';
            field.style.display = show ? 'block' : 'none';
            field.disabled = !show;
            field.required = show;
            if (!show) field.value = '';
        }
        function toggleMFS(val) {
            const show = ['bKash','Nagad','Rocket'].includes(val);
            const chosen = document.querySelector('#payMethod option:checked');
            const number = chosen ? (chosen.dataset.number || '') : '';
            const help = document.getElementById('paymentInstruction');
            if (val === 'Cash on Delivery') help.textContent = 'পণ্য হাতে পেয়ে মূল্য পরিশোধ করুন।';
            else help.textContent = val + ' Send Money নম্বর: ' + (number || 'অ্যাডমিনের কাছ থেকে নম্বর নিশ্চিত করুন') + '। টাকা পাঠানোর পর TrxID লিখুন।';
            const box = document.getElementById('trxBox');
            box.style.display = show ? 'block' : 'none';
            const trx = box.querySelector('input[name="trx_id"]');
            trx.required = show;
            if (!show) trx.value = '';
        }
        toggleMFS(document.getElementById('payMethod').value);
    </script>'''
    return render_template_string(BASE_HTML.replace('{% block content %}{% endblock %}', body),
                                  subtotal=subtotal, discount_amount=discount_amount, applied_coupon=applied_coupon,
                                  bkash_number=BKASH_MERCHANT_NUMBER, nagad_number=NAGAD_MERCHANT_NUMBER,
                                  rocket_number=ROCKET_MERCHANT_NUMBER, customer_phone=(get_db().execute('SELECT phone FROM customers WHERE id=?',(session['customer_id'],)).fetchone() or {'phone':''})['phone'] or '')

@app.route('/order/invoice/<oid>')
@customer_required
def invoice(oid):
    db = get_db()
    order = db.execute('SELECT * FROM orders WHERE order_id = ? AND customer_id = ?', (oid, session['customer_id'])).fetchone()
    if not order: return redirect(url_for('customer_dashboard'))
    items = db.execute('SELECT * FROM order_items WHERE order_id = ?', (order['id'],)).fetchall()
    
    delivery_date = (datetime.strptime(order['created_at'].split()[0], '%Y-%m-%d') + timedelta(days=4)).strftime('%d %B, %Y')
    
    INVOICE_HTML = '''<!DOCTYPE html>
    <html lang="bn">
    <head><meta charset="UTF-8"><title>Invoice</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
    </head>
    <body class="bg-light">
    <div class="container my-5" style="max-width: 750px;">
        <div class="card p-5 shadow border-0 rounded-4">
            <div class="d-flex justify-content-between align-items-center mb-3">
                <h3 class="fw-bold text-primary mb-0">FAYEZ ONLINE SHOP</h3>
                <button onclick="window.print()" class="btn btn-dark btn-sm no-print">প্রিন্ট / PDF</button>
            </div><hr>
            <p class="small"><b>অর্ডার আইডি:</b> {{ order.order_id }} | <b>গ্রহণকারী:</b> {{ order.recipient_name or '—' }} | <b>পেমেন্ট:</b> {{ order.payment_method }} {% if order.trx_id %}(TrxID: {{ order.trx_id }}){% endif %}</p>
            <p class="small"><b>শিপিং ঠিকানা:</b> উপজেলা: {{ order.upazila }}, জেলা: {{ order.district }}, বিভাগ: {{ order.division }}</p>
            
            <div class="card p-3 bg-light border-0 my-3">
                <h6 class="fw-bold text-success mb-2"><i class="fa fa-truck-fast me-2"></i>ডেলিভারি আপডেট ও লাইভ স্ট্যাটাস</h6>
                <div class="progress mb-2" style="height: 10px;">
                    <div class="progress-bar progress-bar-striped progress-bar-animated bg-success" role="progressbar" style="width: 65%;"></div>
                </div>
                <small class="text-muted">আপনার পণ্যটি বর্তমানে প্যাকেজিং ও শিপ্রুটে রয়েছে। সম্ভাব্য ডেলিভারি তারিখ: <b>''' + delivery_date + '''</b> এর মধ্যে!</small>
            </div>

            <table class="table table-bordered small">
                <thead><tr><th>পণ্য</th><th>পরিমাণ</th><th class="text-end">দাম</th></tr></thead>
                <tbody>
                    {% for i in items %}
                    <tr><td>{{ i.product_name }}</td><td>{{ i.quantity }}</td><td class="text-end">৳ {{ "%.2f"|format(i.price * i.quantity) }}</td></tr>
                    {% endfor %}
                </tbody>
            </table>
            <div class="text-end small">
                {% if order.discount_amount > 0 %}<p class="text-success mb-1">ডিসকাউন্ট: - ৳ {{ "%.2f"|format(order.discount_amount) }}</p>{% endif %}
                <p class="mb-1">ডেলিভারি চার্জ: ৳ {{ "%.2f"|format(order.delivery_charge) }}</p>
                <h5 class="fw-bold text-primary">সর্বমোট: ৳ {{ "%.2f"|format(order.total_amount) }}</h5>
            </div>
            <div class="mt-4 no-print"><a href="/customer/dashboard" class="btn btn-outline-secondary btn-sm">← ড্যাশবোর্ড</a></div>
        </div>
    </div>
    </body></html>'''
    
    return render_template_string(INVOICE_HTML, order=order, items=items)

@app.route('/track', methods=['GET', 'POST'])
def track_order():
    order = None
    searched = False
    status_label = 'অপেক্ষমাণ'
    status_index = 0
    if request.method == 'POST':
        oid = (request.form.get('order_id') or '').strip()[:80]
        searched = True
        if oid:
            order = get_db().execute('SELECT * FROM orders WHERE order_id = ?', (oid,)).fetchone()
    if order:
        labels = {'Pending':'অর্ডার গ্রহণ করা হয়েছে', 'Confirmed':'অর্ডার নিশ্চিত হয়েছে', 'Processing':'পণ্য প্রস্তুত হচ্ছে', 'Shipped':'কুরিয়ারে পাঠানো হয়েছে', 'Delivered':'পণ্য ডেলিভারি সম্পন্ন', 'Cancelled':'অর্ডার বাতিল'}
        status_label = labels.get(order['order_status'], str(order['order_status']))
        status_index = {'Pending':0,'Confirmed':1,'Processing':2,'Shipped':3,'Delivered':4,'Cancelled':-1}.get(order['order_status'],0)
    body = r'''<style>
    .track-wrap{max-width:980px;margin:38px auto;padding:0 16px}.track-hero{background:linear-gradient(120deg,#151b36,#594ac5);color:#fff;border-radius:26px;padding:34px;display:grid;grid-template-columns:1fr auto;gap:20px;align-items:center;box-shadow:0 18px 45px #24204a22}.track-hero h1{font-weight:900;font-size:clamp(1.7rem,4vw,2.55rem);letter-spacing:-.8px}.track-hero p{color:#e1defe;margin:8px 0 0;max-width:650px;line-height:1.7}.track-icon{width:94px;height:94px;border-radius:26px;background:#ffffff1c;display:grid;place-items:center;font-size:2.5rem}.track-search,.track-result,.track-support{background:#fff;border:1px solid #e9ebf2;border-radius:22px;padding:24px;margin-top:18px;box-shadow:0 12px 35px #1820440a}.track-search form{display:flex;gap:10px}.track-search input{min-height:54px;border-radius:13px}.track-search .btn{border-radius:13px;font-weight:800}.track-result h3{font-weight:900;letter-spacing:.4px}.track-status{display:inline-flex;align-items:center;gap:7px;background:#eeecff;color:#5145c7;border-radius:99px;padding:9px 14px;font-weight:800}.track-progress{display:grid;grid-template-columns:repeat(5,1fr);gap:6px;margin:24px 0 20px}.track-progress-step{text-align:center;position:relative;color:#9aa1b2;font-size:.78rem;font-weight:700}.track-progress-step:before{content:"";display:block;width:34px;height:34px;border-radius:50%;margin:0 auto 8px;background:#edf0f5;border:2px solid #e1e5ed}.track-progress-step.done{color:#198754}.track-progress-step.done:before{content:"✓";display:grid;place-items:center;background:#e5f7ed;border-color:#26a269;color:#16834d;font-size:1rem}.track-progress-step.current{color:#5548c6}.track-progress-step.current:before{background:#5548c6;border-color:#5548c6;box-shadow:0 0 0 5px #eeecff}.track-info{display:grid;grid-template-columns:repeat(3,1fr);gap:12px;margin-top:18px}.track-info>div{background:#f7f8fc;border-radius:14px;padding:14px}.track-info small{display:block;color:#737b8d;margin-bottom:4px}.track-info b{overflow-wrap:anywhere}.track-support{display:flex;justify-content:space-between;align-items:center;gap:18px;background:linear-gradient(120deg,#f7f6ff,#fff)}.track-support h5{font-weight:850}.track-support p{color:#687083;margin:0}.track-support .btn{white-space:nowrap;border-radius:99px;font-weight:800}@media(max-width:650px){.track-wrap{margin:20px auto;padding:0 10px}.track-hero{padding:23px;border-radius:20px;grid-template-columns:1fr}.track-icon{display:none}.track-search,.track-result,.track-support{padding:17px}.track-search form{flex-direction:column}.track-search .btn{min-height:48px}.track-progress-step{font-size:.64rem}.track-progress-step:before{width:28px;height:28px}.track-info{grid-template-columns:1fr 1fr}.track-support{align-items:flex-start;flex-direction:column}}
    </style><main class="track-wrap"><section class="track-hero"><div><span class="badge rounded-pill bg-light text-dark mb-3 px-3 py-2">FAYEZ ORDER CARE</span><h1>আপনার অর্ডারের প্রতিটি ধাপ থাকুক আপনার হাতেই</h1><p>অর্ডার আইডি দিয়ে পণ্যের বর্তমান অবস্থা, কুরিয়ার ও ট্র্যাকিং তথ্য সহজেই দেখুন। আপডেট পেতে অর্ডার আইডি ব্যবহার করুন।</p></div><div class="track-icon"><i class="fa fa-truck-fast"></i></div></section>
    <section class="track-search"><h5 class="fw-bold mb-2">অর্ডার ট্র্যাক করুন</h5><p class="text-secondary mb-3">অর্ডার কনফার্মেশনে পাওয়া Order ID লিখুন।</p><form method="POST"><input class="form-control" type="text" name="order_id" value="{{ request.form.get('order_id','') }}" placeholder="আপনার Order ID লিখুন" required aria-label="অর্ডার আইডি"><button class="btn btn-primary px-4" type="submit"><i class="fa fa-magnifying-glass me-2"></i>অর্ডার খুঁজুন</button></form>
    {% if searched and not order %}<div class="alert alert-warning mt-3 mb-0">এই Order ID দিয়ে কোনো অর্ডার পাওয়া যায়নি। আইডিটি আবার পরীক্ষা করুন অথবা আমাদের সাপোর্টে যোগাযোগ করুন।</div>{% endif %}</section>
    {% if order %}<section class="track-result"><div class="d-flex flex-wrap justify-content-between gap-3 align-items-center"><div><div class="small text-secondary fw-bold mb-1">ORDER ID</div><h3 class="mb-0">{{ order.order_id }}</h3></div><span class="track-status"><i class="fa fa-circle-check"></i>{{ status_label }}</span></div>
      {% if status_index >= 0 %}<div class="track-progress">{% for step in ['অর্ডার','নিশ্চিত','প্রস্তুত','শিপড','ডেলিভারি'] %}<div class="track-progress-step {% if loop.index0 < status_index %}done{% elif loop.index0 == status_index %}current{% endif %}">{{ step }}</div>{% endfor %}</div>{% else %}<div class="alert alert-danger mt-3">এই অর্ডারটি বাতিল করা হয়েছে। বিস্তারিত জানতে সাপোর্টে যোগাযোগ করুন।</div>{% endif %}
      <div class="track-info"><div><small>অর্ডারের তারিখ</small><b>{{ order.created_at }}</b></div><div><small>কুরিয়ার সার্ভিস</small><b>{{ order.courier_name or 'শিগগিরই আপডেট করা হবে' }}</b></div><div><small>ট্র্যাকিং নম্বর</small><b>{{ order.tracking_number or 'শিপমেন্টের পর দেওয়া হবে' }}</b></div><div><small>ডেলিভারি এলাকা</small><b>{{ order.upazila or '' }}, {{ order.district or '' }}</b></div><div><small>গ্রহণকারীর নাম</small><b>{{ order.recipient_name or '—' }}</b></div><div><small>সর্বমোট</small><b class="text-primary">৳ {{ '%.2f'|format(order.total_amount) }}</b></div></div>
      {% if order.shipped_at %}<p class="small text-secondary mt-3 mb-0"><i class="fa fa-truck me-1"></i>শিপমেন্টের সময়: {{ order.shipped_at }}</p>{% endif %}</section>{% endif %}
    <section class="track-support"><div><h5>২৪ ঘণ্টা ডেলিভারি ও অর্ডার সাপোর্ট</h5><p>আপনার কেনাকাটার প্রতিটি ধাপে আমরা সবসময় আপনার পাশে আছি। কোনো সহায়তা লাগলে আমাদের সঙ্গে যোগাযোগ করুন।</p></div><a class="btn btn-primary px-4" href="/support"><i class="fa fa-headset me-2"></i>সাপোর্ট নিন</a></section></main>'''
    return render_template_string(BASE_HTML.replace('{% block content %}{% endblock %}', body), order=order, searched=searched, status_label=status_label, status_index=status_index)


# -----------------------------------------------------------------------------
# Google and Facebook OAuth 2.0 sign-in.
# Configure these values in the hosting environment or the local .env file:
# GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET, FACEBOOK_APP_ID, FACEBOOK_APP_SECRET.
# Register callback URLs /auth/google/callback and /auth/facebook/callback.
# -----------------------------------------------------------------------------
from urllib.parse import urlencode
from urllib.request import Request, urlopen

def _oauth_setting(name):
    return (os.environ.get(name) or '').strip()

def _oauth_json(url, data=None, headers=None):
    payload = None if data is None else urlencode(data).encode('utf-8')
    req = Request(url, data=payload, headers=headers or {}, method='GET' if payload is None else 'POST')
    with urlopen(req, timeout=20) as response:
        return json.loads(response.read().decode('utf-8'))

def _oauth_start(provider):
    provider = provider.lower()
    state = secrets.token_urlsafe(32)
    session['oauth_state'] = state
    session['oauth_provider'] = provider
    callback = url_for('oauth_callback', provider=provider, _external=True)
    if provider == 'google':
        client_id = _oauth_setting('GOOGLE_CLIENT_ID')
        if not client_id or not _oauth_setting('GOOGLE_CLIENT_SECRET'):
            flash('Google Login চালু করতে GOOGLE_CLIENT_ID ও GOOGLE_CLIENT_SECRET সেট করতে হবে।', 'warning')
            return redirect(url_for('customer_login'))
        params = {
            'client_id': client_id, 'redirect_uri': callback, 'response_type': 'code',
            'scope': 'openid email profile', 'state': state, 'prompt': 'select_account'
        }
        return redirect('https://accounts.google.com/o/oauth2/v2/auth?' + urlencode(params))
    if provider == 'facebook':
        app_id = _oauth_setting('FACEBOOK_APP_ID')
        if not app_id or not _oauth_setting('FACEBOOK_APP_SECRET'):
            flash('Facebook Login চালু করতে FACEBOOK_APP_ID ও FACEBOOK_APP_SECRET সেট করতে হবে।', 'warning')
            return redirect(url_for('customer_login'))
        params = {
            'client_id': app_id, 'redirect_uri': callback, 'response_type': 'code',
            'scope': 'email,public_profile', 'state': state
        }
        return redirect('https://www.facebook.com/v21.0/dialog/oauth?' + urlencode(params))
    abort(404)

@app.route('/auth/<provider>')
def oauth_login(provider):
    if provider not in ('google', 'facebook'):
        abort(404)
    return _oauth_start(provider)

@app.route('/auth/<provider>/callback')
def oauth_callback(provider):
    if provider not in ('google', 'facebook'):
        abort(404)
    expected_state = session.pop('oauth_state', None)
    expected_provider = session.pop('oauth_provider', None)
    if not expected_state or expected_provider != provider or not secrets.compare_digest(
        expected_state, request.args.get('state', '')
    ):
        flash('নিরাপত্তা যাচাই সম্পন্ন হয়নি। আবার লগইন চেষ্টা করুন।', 'danger')
        return redirect(url_for('customer_login'))
    if request.args.get('error'):
        flash('সোশ্যাল লগইন বাতিল হয়েছে বা অনুমতি পাওয়া যায়নি।', 'warning')
        return redirect(url_for('customer_login'))
    code = request.args.get('code', '')
    if not code:
        flash('OAuth authorization code পাওয়া যায়নি।', 'danger')
        return redirect(url_for('customer_login'))

    callback = url_for('oauth_callback', provider=provider, _external=True)
    try:
        if provider == 'google':
            token = _oauth_json('https://oauth2.googleapis.com/token', {
                'code': code, 'client_id': _oauth_setting('GOOGLE_CLIENT_ID'),
                'client_secret': _oauth_setting('GOOGLE_CLIENT_SECRET'),
                'redirect_uri': callback, 'grant_type': 'authorization_code'
            }, {'Content-Type': 'application/x-www-form-urlencoded'})
            access_token = token.get('access_token')
            if not access_token:
                raise ValueError('Google access token পাওয়া যায়নি।')
            profile = _oauth_json('https://openidconnect.googleapis.com/v1/userinfo',
                                  headers={'Authorization': 'Bearer ' + access_token})
            if not profile.get('email') or not profile.get('email_verified'):
                raise ValueError('Google থেকে verified email পাওয়া যায়নি।')
            provider_user_id = str(profile['sub'])
            email = profile['email'].strip().lower()
            display_name = (profile.get('name') or email.split('@')[0]).strip()[:120]
        else:
            token = _oauth_json('https://graph.facebook.com/v21.0/oauth/access_token', {
                'client_id': _oauth_setting('FACEBOOK_APP_ID'),
                'client_secret': _oauth_setting('FACEBOOK_APP_SECRET'),
                'redirect_uri': callback, 'code': code
            })
            access_token = token.get('access_token')
            if not access_token:
                raise ValueError('Facebook access token পাওয়া যায়নি।')
            profile = _oauth_json(
                'https://graph.facebook.com/me?' + urlencode({
                    'fields': 'id,name,email', 'access_token': access_token
                })
            )
            if not profile.get('email'):
                raise ValueError('Facebook আপনার email দেয়নি। Facebook account-এ email permission চালু করে আবার চেষ্টা করুন।')
            provider_user_id = str(profile['id'])
            email = profile['email'].strip().lower()
            display_name = (profile.get('name') or email.split('@')[0]).strip()[:120]

        if not email or '@' not in email:
            raise ValueError('সোশ্যাল অ্যাকাউন্ট থেকে সঠিক email পাওয়া যায়নি।')

        db = get_db()
        linked = db.execute(
            'SELECT c.* FROM customer_social_accounts s JOIN customers c ON c.id=s.customer_id '
            'WHERE s.provider=? AND s.provider_user_id=?', (provider, provider_user_id)
        ).fetchone()
        if linked:
            customer = linked
        else:
            customer = db.execute(
                'SELECT * FROM customers WHERE lower(trim(email))=? ORDER BY id DESC LIMIT 1',
                (email,)
            ).fetchone()
            if not customer:
                random_password = secrets.token_urlsafe(48)
                cur = db.execute(
                    'INSERT INTO customers(name,email,phone,password_hash,is_verified) VALUES(?,?,?,?,1)',
                    (display_name or 'Shop Customer', email, None,
                     generate_password_hash(random_password, method='pbkdf2:sha256'))
                )
                customer = db.execute('SELECT * FROM customers WHERE id=?', (cur.lastrowid,)).fetchone()
            db.execute(
                'INSERT OR IGNORE INTO customer_social_accounts(provider,provider_user_id,customer_id) VALUES(?,?,?)',
                (provider, provider_user_id, customer['id'])
            )
            db.commit()

        session.clear()
        session['customer_id'] = customer['id']
        session['customer_name'] = customer['name']
        session.permanent = True
        _fayez_track_customer_event('login', None, provider.title() + ' OAuth login')
        flash(provider.title() + ' দিয়ে সফলভাবে লগইন হয়েছে!', 'success')
        return redirect(url_for('home'))
    except Exception as exc:
        app.logger.exception('%s OAuth login failed', provider)
        flash('সোশ্যাল লগইন সম্পন্ন হয়নি: ' + str(exc)[:220], 'danger')
        return redirect(url_for('customer_login'))


@app.route('/customer/login', methods=['GET', 'POST'])
def customer_login():
    if request.method == 'POST':
        identifier = request.form.get('identifier', request.form.get('email', '')).strip()
        email = identifier.lower()
        password = request.form.get('password', '')
        db = get_db()
        # Search every matching email row, newest first. Older databases may contain
        # duplicate email variants (case/whitespace differences); choosing the first
        # row can reject the correct password even when another matching row is valid.
        email_rows = db.execute(
            'SELECT * FROM customers WHERE lower(trim(email)) = ? ORDER BY id DESC',
            (email,)
        ).fetchall()
        candidates = list(email_rows)
        if not candidates:
            import re
            digits = re.sub(r'\D', '', identifier)
            phone_digits = digits[-11:] if len(digits) >= 11 else digits
            candidates = db.execute(
                "SELECT * FROM customers WHERE replace(replace(replace(replace(replace(phone,' ',''),'-',''),'+',''),'(',''),')','') LIKE ? ORDER BY id DESC",
                ('%' + phone_digits,)
            ).fetchall()

        c = None
        valid_password = False
        if password:
            for candidate in candidates:
                stored = (candidate['password_hash'] or '').strip()
                try:
                    matches = bool(stored) and check_password_hash(stored, password)
                except (ValueError, TypeError):
                    matches = False
                # Migrate legacy plaintext passwords to a secure hash on successful login.
                if not matches and stored and stored == password:
                    matches = True
                    db.execute(
                        'UPDATE customers SET password_hash=? WHERE id=?',
                        (generate_password_hash(password, method='pbkdf2:sha256'), candidate['id'])
                    )
                    db.commit()
                if matches:
                    c = candidate
                    valid_password = True
                    break
        if c and valid_password:
            session.clear()
            session['customer_id'], session['customer_name'] = c['id'], c['name']
            _fayez_track_customer_event('login', None, 'Customer login')
            if request.form.get('remember_me') == 'on':
                session.permanent = True
            flash('সফলভাবে লগইন করা হয়েছে!', 'success')
            return redirect(url_for('home'))
        flash('ইমেইল/ফোন নম্বর অথবা পাসওয়ার্ড ভুল।', 'danger')
    body = r'''<style>.auth-shell{max-width:1000px!important;margin:42px auto!important;border:1px solid #e9ebf2!important;border-radius:26px!important;overflow:hidden!important;box-shadow:0 22px 65px #171d3812!important}.auth-panel{padding:clamp(25px,5vw,48px)!important}.auth-panel .form-control{min-height:49px;border-radius:12px}.auth-panel .btn-primary{min-height:50px;font-weight:800;background:#5c50ce;border-color:#5c50ce}.auth-art{padding:clamp(25px,5vw,48px)!important}@media(max-width:760px){.auth-shell{margin:18px 10px!important;border-radius:20px!important}.auth-art{min-height:220px!important}.auth-panel{padding:25px 20px!important}}</style>
    <section class="auth-shell">
      <div class="auth-art">
        <div><div class="d-inline-flex align-items-center gap-2 mb-5"><span class="bg-white text-primary rounded-3 p-2"><i class="fa fa-bag-shopping fa-lg"></i></span><b class="text-white">FAYEZ SHOP</b></div>
          <span class="badge rounded-pill bg-white bg-opacity-25 text-white px-3 py-2 mb-3">WELCOME BACK</span>
          <h1>আপনার পছন্দের<br>শপিং আবার শুরু হোক।</h1>
          <p class="mt-3 text-white-50">নতুন কালেকশন, এক্সক্লুসিভ অফার এবং আপনার অর্ডার—সবকিছু এক জায়গায়।</p>
        </div>
        <div class="small text-white-50"><i class="fa fa-shield-halved me-2"></i>নিরাপদ অ্যাকাউন্ট • সহজ অর্ডার • দ্রুত ডেলিভারি</div>
      </div>
      <div class="auth-panel">
        <div class="mb-4"><span class="text-uppercase small fw-bold" style="color:#7668ef;letter-spacing:1.5px">Customer account</span><h2 class="mt-2 mb-2">আবার স্বাগতম 👋</h2><p class="text-secondary mb-0">আপনার অ্যাকাউন্টে প্রবেশ করতে তথ্য দিন।</p></div>
        <form method="POST" autocomplete="on">
          <div class="mb-3"><label class="form-label fw-semibold">ইমেইল অথবা ফোন নম্বর</label><input type="text" class="form-control" name="identifier" placeholder="name@example.com / 01XXXXXXXXX" autocomplete="username" required></div>
          <div class="mb-3"><div class="d-flex justify-content-between"><label class="form-label fw-semibold">পাসওয়ার্ড</label><a href="/customer/forgot-password" class="small text-decoration-none">পাসওয়ার্ড ভুলে গেছেন?</a></div>
            <div class="input-group"><input type="password" class="form-control" id="custLoginPass" name="password" placeholder="আপনার পাসওয়ার্ড" autocomplete="current-password" required><button class="btn btn-outline-secondary" type="button" onclick="togglePassword('custLoginPass', 'custLoginIcon')"><i class="fa fa-eye" id="custLoginIcon"></i></button></div>
          </div>
          <div class="form-check mb-4"><input class="form-check-input" type="checkbox" name="remember_me" id="rememberMe"><label class="form-check-label text-secondary" for="rememberMe">আমাকে মনে রাখুন</label></div>
          <button type="submit" class="btn btn-primary w-100 rounded-3">নিরাপদে লগইন করুন <i class="fa fa-arrow-right ms-2"></i></button>
        </form>
        <div class="d-flex align-items-center gap-3 my-3"><hr class="flex-grow-1"><span class="small text-secondary">অথবা</span><hr class="flex-grow-1"></div>
        <div class="d-grid gap-2">
          <a href="/auth/google" class="btn btn-outline-dark rounded-3 py-2"><i class="fa-brands fa-google me-2"></i>Google দিয়ে লগইন</a>
          <a href="/auth/facebook" class="btn btn-primary rounded-3 py-2" style="background:#1877f2;border-color:#1877f2"><i class="fa-brands fa-facebook me-2"></i>Facebook দিয়ে লগইন</a>
        </div>
        <p class="text-center mt-4 text-secondary">নতুন এখানে? <a href="/customer/register" class="fw-bold text-decoration-none">ফ্রি অ্যাকাউন্ট খুলুন</a></p>
        <div class="text-center small text-secondary mt-2"><i class="fa fa-lock me-1"></i>আপনার তথ্য সুরক্ষিত রাখা হয়</div>
      </div>
    </section>'''
    return render_template_string(BASE_HTML.replace('{% block content %}{% endblock %}', body))

@app.route('/customer/forgot-password', methods=['GET', 'POST'])
def forgot_password():
    if request.method == 'POST':
        email = (request.form.get('email') or '').strip().lower()
        phone_raw = (request.form.get('phone') or '').strip()
        identity = ''
        identity_type = ''
        if phone_raw:
            try:
                identity = normalize_bd_mobile(phone_raw)
                identity_type = 'phone'
            except ValueError as exc:
                flash(str(exc), 'danger')
        elif email and '@' in email:
            identity, identity_type = email, 'email'
        else:
            flash('রেজিস্টার্ড ইমেইল অথবা মোবাইল নম্বর দিন।', 'danger')

        if identity:
            db = get_db()
            try:
                db.execute('''CREATE TABLE IF NOT EXISTS password_reset_otps_v2 (
                    identity TEXT PRIMARY KEY, identity_type TEXT NOT NULL,
                    otp_hash TEXT NOT NULL, expires_at REAL NOT NULL)''')
                if identity_type == 'phone':
                    customer = db.execute(
                        "SELECT id FROM customers WHERE REPLACE(REPLACE(REPLACE(TRIM(COALESCE(phone,'')),' ',''),'-',''),'+','') IN (?,?) ORDER BY id DESC LIMIT 1",
                        (identity, '88' + identity[1:])
                    ).fetchone()
                else:
                    customer = db.execute(
                        'SELECT id FROM customers WHERE lower(trim(email))=? ORDER BY id DESC LIMIT 1',
                        (identity,)
                    ).fetchone()
                if not customer:
                    flash('এই ইমেইল/মোবাইল নম্বরে কোনো অ্যাকাউন্ট পাওয়া যায়নি। রেজিস্ট্রেশনের সময় ব্যবহৃত তথ্য দিন।', 'danger')
                else:
                    otp = f"{secrets.randbelow(1000000):06d}"
                    expires = (datetime.utcnow() + timedelta(minutes=10)).timestamp()
                    db.execute('INSERT OR REPLACE INTO password_reset_otps_v2(identity,identity_type,otp_hash,expires_at) VALUES(?,?,?,?)',
                               (identity, identity_type, generate_password_hash(otp, method='pbkdf2:sha256'), expires))
                    db.commit()
                    try:
                        if identity_type == 'phone':
                            send_sms_otp(identity, otp, 'পাসওয়ার্ড রিসেট')
                            session['reset_identity'] = identity
                            session['reset_identity_type'] = 'phone'
                            flash('আপনার মোবাইল নম্বরে SMS OTP পাঠানো হয়েছে।', 'success')
                        else:
                            send_account_otp(identity, 'Password Reset OTP - Fayez Online Shop', otp, 'পাসওয়ার্ড রিসেট')
                            session['reset_identity'] = identity
                            session['reset_identity_type'] = 'email'
                            flash('আপনার ইমেইলে পাসওয়ার্ড রিসেট OTP পাঠানো হয়েছে। Inbox ও Spam/Junk দেখুন।', 'success')
                        return redirect(url_for('reset_password'))
                    except Exception as exc:
                        db.execute('DELETE FROM password_reset_otps_v2 WHERE identity=?', (identity,))
                        db.commit()
                        app.logger.exception('Password reset OTP delivery failed')
                        err = str(exc).lower()
                        if 'sms_api_key_missing' in err:
                            flash('SMS পাঠানো যায়নি: SendMySMS API Key সেটিং পরীক্ষা করুন।', 'danger')
                        elif 'sms_gateway_error' in err:
                            flash('SMS প্রদানকারীর সার্ভার OTP গ্রহণ করেনি। SMS ব্যালেন্স/ক্রেডিট ও API সেটিংস পরীক্ষা করুন।', 'danger')
                        elif 'gmail_app_password_missing' in err:
                            flash('ইমেইল OTP পাঠাতে .env-এ MAIL_USERNAME ও MAIL_PASSWORD সেট করা নেই। মোবাইল নম্বর দিয়েও চেষ্টা করতে পারেন।', 'danger')
                        else:
                            flash('OTP পাঠানো যায়নি। SMS/ইমেইল সার্ভারের সেটিংস ও Terminal-এর error পরীক্ষা করুন।', 'danger')
            except sqlite3.Error:
                db.rollback()
                app.logger.exception('Password reset database error')
                flash('পাসওয়ার্ড রিসেটের ডেটাবেসে সমস্যা হয়েছে। আপনার fayez_online_shop.db ফাইলটি মুছবেন না।', 'danger')
            except Exception:
                db.rollback()
                app.logger.exception('Unexpected password reset error')
                flash('পাসওয়ার্ড রিসেট করা যায়নি। Terminal-এর error দেখে সমস্যা নির্ণয় করতে হবে।', 'danger')

    body = '''
    <div class="container my-5" style="max-width:460px;">
      <div class="card p-4 shadow-sm border-0 rounded-4">
        <h4 class="fw-bold text-center mb-2">পাসওয়ার্ড পুনরুদ্ধার</h4>
        <p class="text-secondary small text-center mb-4">ইমেইল অথবা মোবাইল নম্বর—যেকোনো একটি ব্যবহার করুন।</p>
        <form method="POST" autocomplete="on">
          <div class="mb-3"><label class="form-label fw-semibold">ইমেইল ঠিকানা (Email)</label><input type="email" class="form-control" name="email" autocomplete="email" placeholder="name@example.com"></div>
          <div class="text-center text-secondary small mb-3">— অথবা —</div>
          <div class="mb-3"><label class="form-label fw-semibold">মোবাইল নম্বর (SMS)</label><input type="tel" class="form-control" name="phone" autocomplete="tel" inputmode="tel" placeholder="01XXXXXXXXX"></div>
          <div class="form-text mb-3">যে মাধ্যমে OTP নিতে চান, শুধু সেই ঘরটি পূরণ করুন।</div>
          <button type="submit" class="btn btn-primary w-100 rounded-pill fw-bold py-2">OTP কোড পাঠান</button>
        </form>
        <div class="text-center mt-3"><a href="/customer/login" class="small text-decoration-none">← লগইন পেজে ফিরে যান</a></div>
      </div>
    </div>'''
    return render_template_string(BASE_HTML.replace('{% block content %}{% endblock %}', body))

@app.route('/customer/reset-password', methods=['GET', 'POST'])
def reset_password():
    identity = session.get('reset_identity')
    identity_type = session.get('reset_identity_type')
    if not identity and session.get('reset_email'):
        identity, identity_type = session.get('reset_email'), 'email'
    if not identity:
        return redirect(url_for('forgot_password'))
    if request.method == 'POST':
        entered_otp = (request.form.get('otp') or '').strip()
        new_pass = request.form.get('new_password') or ''
        db = get_db()
        db.execute('''CREATE TABLE IF NOT EXISTS password_reset_otps_v2 (
            identity TEXT PRIMARY KEY, identity_type TEXT NOT NULL,
            otp_hash TEXT NOT NULL, expires_at REAL NOT NULL)''')
        row = db.execute('SELECT * FROM password_reset_otps_v2 WHERE identity=? AND identity_type=?',
                         (identity, identity_type)).fetchone()
        legacy_row = None
        if row is None and identity_type == 'email':
            db.execute("CREATE TABLE IF NOT EXISTS password_reset_otps (email TEXT PRIMARY KEY, otp_hash TEXT NOT NULL, expires_at REAL NOT NULL)")
            legacy_row = db.execute('SELECT * FROM password_reset_otps WHERE lower(trim(email))=?', (identity.lower(),)).fetchone()
        otp_row = row or legacy_row
        if (otp_row and datetime.utcnow().timestamp() <= otp_row['expires_at']
                and check_password_hash(otp_row['otp_hash'], entered_otp) and len(new_pass) >= 8):
            new_password_hash = generate_password_hash(new_pass, method='pbkdf2:sha256')
            if identity_type == 'phone':
                matching_customers = db.execute(
                    "SELECT id FROM customers WHERE REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(TRIM(COALESCE(phone,'')),' ',''),'-',''),'+',''),'(',''),')','') IN (?,?)",
                    (identity, '88' + identity[1:])
                ).fetchall()
            else:
                matching_customers = db.execute(
                    'SELECT id FROM customers WHERE lower(trim(email))=? ORDER BY id DESC',
                    (identity.lower(),)
                ).fetchall()
            if not matching_customers:
                db.rollback()
                flash('পাসওয়ার্ড পরিবর্তন করা যায়নি: এই ইমেইল/ফোনের অ্যাকাউন্টটি আর পাওয়া যাচ্ছে না।', 'danger')
                return redirect(url_for('forgot_password'))
            for customer_row in matching_customers:
                db.execute('UPDATE customers SET password_hash=? WHERE id=?',
                           (new_password_hash, customer_row['id']))
            # Confirm the stored value is a valid hash before marking the OTP as used.
            saved_rows = db.execute(
                'SELECT password_hash FROM customers WHERE id IN (' + ','.join('?' for _ in matching_customers) + ')',
                tuple(r['id'] for r in matching_customers)
            ).fetchall()
            if len(saved_rows) != len(matching_customers) or not all(check_password_hash(r['password_hash'], new_pass) for r in saved_rows):
                db.rollback()
                flash('নতুন পাসওয়ার্ড ডেটাবেসে সেভ হয়নি। আবার চেষ্টা করুন।', 'danger')
                return redirect(url_for('forgot_password'))
            db.execute('DELETE FROM password_reset_otps_v2 WHERE identity=?', (identity,))
            if identity_type == 'email':
                try: db.execute('DELETE FROM password_reset_otps WHERE lower(trim(email))=?', (identity.lower(),))
                except sqlite3.Error: pass
            db.commit()
            session.pop('reset_identity', None)
            session.pop('reset_identity_type', None)
            session.pop('reset_email', None)
            flash('নতুন পাসওয়ার্ড সফলভাবে সেভ হয়েছে। এখন এই নতুন পাসওয়ার্ড দিয়ে লগইন করুন।', 'success')
            return redirect(url_for('customer_login'))
        flash('OTP ভুল/মেয়াদোত্তীর্ণ অথবা নতুন পাসওয়ার্ড ৮ অক্ষরের কম।', 'danger')

    delivery = 'SMS' if identity_type == 'phone' else 'ইমেইল'
    body = f'''<div class="container my-5" style="max-width:420px"><div class="card p-4 shadow-sm border-0 rounded-4">
      <h4 class="fw-bold text-center mb-3">নতুন পাসওয়ার্ড সেট করুন</h4>
      <p class="small text-secondary text-center">{delivery}-এ পাঠানো ৬-ডিজিট OTP লিখুন।</p>
      <form method="POST"><div class="mb-3"><label class="form-label">{delivery} OTP</label><input type="text" inputmode="numeric" pattern="[0-9]{{6}}" class="form-control" name="otp" maxlength="6" required></div>
      <div class="mb-3"><label class="form-label">নতুন পাসওয়ার্ড</label><input type="password" minlength="8" class="form-control" name="new_password" autocomplete="new-password" required></div>
      <button type="submit" class="btn btn-success w-100 rounded-pill fw-bold py-2">পাসওয়ার্ড আপডেট করুন</button></form></div></div>'''
    return render_template_string(BASE_HTML.replace('{% block content %}{% endblock %}', body))

@app.route('/customer/register', methods=['GET', 'POST'])
def customer_register():
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        email = request.form.get('email', '').strip().lower()
        phone_raw = request.form.get('phone', '').strip()
        password = request.form.get('password', '')
        phone = ''
        try:
            if phone_raw:
                phone = normalize_bd_mobile(phone_raw)
            if not name or len(name) > 120 or len(password) < 8 or (not email and not phone):
                raise ValueError('নাম, কমপক্ষে ৮ অক্ষরের পাসওয়ার্ড এবং ইমেইল অথবা ফোন—যেকোনো একটি দিন।')
            if email and ('@' not in email or len(email) > 254):
                raise ValueError('সঠিক ইমেইল ঠিকানা লিখুন।')
            db = get_db()
            if email and db.execute('SELECT 1 FROM customers WHERE lower(trim(email))=?', (email,)).fetchone():
                raise ValueError('এই ইমেইল দিয়ে ইতোমধ্যে অ্যাকাউন্ট রয়েছে।')
            if phone and db.execute("SELECT 1 FROM customers WHERE replace(replace(replace(replace(replace(phone,' ',''),'-',''),'+',''),'(',''),')','') LIKE ?", ('%'+phone[-11:],)).fetchone():
                raise ValueError('এই ফোন নম্বর দিয়ে ইতোমধ্যে অ্যাকাউন্ট রয়েছে।')
            # A separate pending table avoids changing or rebuilding the customer's existing table.
            db.execute('''CREATE TABLE IF NOT EXISTS pending_registrations_v2 (
                identity TEXT PRIMARY KEY, email TEXT, phone TEXT, name TEXT NOT NULL,
                password_hash TEXT NOT NULL, otp_hash TEXT NOT NULL, expires_at REAL NOT NULL
            )''')
            identity = ('phone:' + phone) if phone else ('email:' + email)
            otp = f"{secrets.randbelow(1000000):06d}"
            db.execute('''INSERT OR REPLACE INTO pending_registrations_v2
                (identity,email,phone,name,password_hash,otp_hash,expires_at) VALUES(?,?,?,?,?,?,?)''',
                (identity, email or None, phone or None, name,
                 generate_password_hash(password, method='pbkdf2:sha256'),
                 generate_password_hash(otp, method='pbkdf2:sha256'),
                 (datetime.utcnow()+timedelta(minutes=10)).timestamp()))
            db.commit()
            try:
                send_registration_otp(email, phone, otp)
            except Exception:
                db.execute('DELETE FROM pending_registrations_v2 WHERE identity=?', (identity,)); db.commit()
                app.logger.exception('Registration OTP delivery failed')
                raise
            session['reg_identity'] = identity
            flash(('আপনার ফোন নম্বরে SMS OTP পাঠানো হয়েছে।' if phone else 'আপনার ইমেইলে OTP পাঠানো হয়েছে।'), 'success')
            return redirect(url_for('customer_verify_otp'))
        except Exception as exc:
            app.logger.exception('Customer registration failed')
            message = str(exc)
            if 'SMS_GATEWAY_ERROR:' in message:
                message = message.split('SMS_GATEWAY_ERROR:',1)[1].strip()
            elif 'SMS_API_KEY_MISSING' in message:
                message = 'SMS API Key .env ফাইলে পাওয়া যায়নি। আপনার আগের API Key-সহ .env ফাইলটি এই Python ফাইলের পাশেই রাখুন।'
            elif 'GMAIL_APP_PASSWORD_MISSING' in message:
                message = 'ইমেইলে OTP পাঠাতে Gmail App Password সেট করা নেই। ফোন নম্বর দিয়ে চেষ্টা করতে পারেন।'
            elif '535' in message or 'Username and Password not accepted' in message:
                message = 'Gmail App Password সঠিক নয়। ফোন নম্বর দিয়ে চেষ্টা করতে পারেন।'
            flash(message or 'রেজিস্ট্রেশন সম্পন্ন হয়নি। তথ্য যাচাই করুন।', 'danger')

    body = r'''<style>
    .reg-shell{max-width:1040px;margin:42px auto;padding:0 16px;display:grid;grid-template-columns:.9fr 1.1fr;background:#fff;border:1px solid #e9ebf2;border-radius:26px;overflow:hidden;box-shadow:0 22px 65px #171d3812}.reg-art{background:radial-gradient(circle at 80% 20%,#7768e9,transparent 35%),linear-gradient(145deg,#171d38,#39317d);color:#fff;padding:44px;display:flex;flex-direction:column;justify-content:space-between;min-height:590px}.reg-art h1{font-weight:900;font-size:2.5rem;line-height:1.12;letter-spacing:-1px}.reg-art p{color:#d8d6f3;line-height:1.7}.reg-benefit{display:flex;gap:12px;align-items:center;margin-top:15px;color:#e8e7fb}.reg-benefit i{width:34px;height:34px;display:grid;place-items:center;border-radius:10px;background:#ffffff20}.reg-panel{padding:44px}.reg-panel h2{font-weight:850;letter-spacing:-.7px}.reg-panel .form-control{min-height:49px;border-radius:12px;border-color:#e2e5ed}.reg-submit{min-height:52px;border-radius:13px;font-weight:800;background:#5c50ce;border:0}.reg-field{margin-bottom:17px}.reg-field label{font-size:.9rem;font-weight:700;margin-bottom:7px}.pass-meter{height:6px;background:#eceef4;border-radius:20px;overflow:hidden;margin-top:9px}.pass-meter span{display:block;height:100%;width:0;background:#d34b58;transition:.2s}.reg-panel .input-group .btn{border-color:#e2e5ed;border-radius:0 12px 12px 0}.reg-panel .input-group input{border-radius:12px 0 0 12px}.reg-terms{font-size:.82rem;color:#73798a}@media(max-width:760px){.reg-shell{display:block;margin:18px 10px;border-radius:20px}.reg-art{min-height:0;padding:25px}.reg-art h1{font-size:1.8rem}.reg-art .reg-bullets{display:none}.reg-panel{padding:25px 20px}}
    </style><section class="reg-shell"><aside class="reg-art"><div><div class="d-flex align-items-center gap-2 mb-5"><span class="bg-white text-primary rounded-3 p-2"><i class="fa fa-bag-shopping"></i></span><b>FAYEZ ONLINE SHOP</b></div><span class="badge rounded-pill bg-white bg-opacity-25 px-3 py-2 mb-3">JOIN THE COMMUNITY</span><h1>আপনার স্মার্ট শপিং শুরু হোক এখান থেকেই।</h1><p class="mt-3">ইমেইল অথবা মোবাইল—যেকোনো একটি দিয়েই অ্যাকাউন্ট খুলুন।</p></div><div class="reg-bullets"><div class="reg-benefit"><i class="fa fa-shield-halved"></i><span>নিরাপদ OTP ভেরিফিকেশন</span></div><div class="reg-benefit"><i class="fa fa-truck-fast"></i><span>অর্ডার ও ডেলিভারি আপডেট</span></div><div class="reg-benefit"><i class="fa fa-heart"></i><span>পছন্দের পণ্য সংরক্ষণ</span></div></div></aside><div class="reg-panel"><div class="mb-4"><div class="small fw-bold text-uppercase" style="letter-spacing:1.3px;color:#695de0">CREATE YOUR ACCOUNT</div><h2 class="mt-2">নতুন অ্যাকাউন্ট খুলুন</h2><p class="text-secondary mb-0">ইমেইল অথবা ফোন নম্বর—যেকোনো একটি দিন। OTP সেই ঠিকানায়/নম্বরে যাবে।</p></div><form method="POST" autocomplete="on"><div class="reg-field"><label>পূর্ণ নাম</label><input type="text" class="form-control" name="name" maxlength="120" placeholder="আপনার নাম" autocomplete="name" required></div><div class="reg-field"><label>ইমেইল ঠিকানা (Optional)</label><input type="email" class="form-control" name="email" placeholder="ইমেইল না থাকলে খালি রাখুন" autocomplete="email"></div><div class="text-center small text-secondary mb-2">— অথবা —</div><div class="reg-field"><label>মোবাইল নম্বর (Optional)</label><input type="tel" class="form-control" name="phone" placeholder="01XXXXXXXXX" autocomplete="tel" inputmode="tel"></div><div class="small text-muted mb-3">উপরের ইমেইল অথবা ফোন নম্বর—কমপক্ষে একটি দিতে হবে। ফোন দিলে SMS OTP যাবে।</div><div class="reg-field"><label>পাসওয়ার্ড</label><div class="input-group"><input type="password" minlength="8" class="form-control" id="custRegPass" name="password" placeholder="কমপক্ষে ৮ অক্ষর" autocomplete="new-password" required oninput="checkPassStrength(this.value)"><button class="btn btn-outline-secondary" type="button" onclick="togglePassword('custRegPass','custRegEye')"><i class="fa fa-eye" id="custRegEye"></i></button></div><div class="pass-meter"><span id="passMeter"></span></div><div id="passStrength" class="small mt-2">বড় হাতের অক্ষর, ছোট হাতের অক্ষর, সংখ্যা ও চিহ্ন ব্যবহার করুন।</div></div><button type="submit" class="btn btn-primary reg-submit w-100">OTP পাঠিয়ে অ্যাকাউন্ট তৈরি করুন <i class="fa fa-arrow-right ms-2"></i></button></form><p class="reg-terms mt-3 mb-0">রেজিস্ট্রেশন করে আপনি আমাদের শর্তাবলিতে সম্মতি দিচ্ছেন।</p><p class="text-center mt-4 mb-0 text-secondary">আগে থেকেই অ্যাকাউন্ট আছে? <a href="/customer/login" class="fw-bold text-decoration-none">লগইন করুন</a></p></div></section>
    <script>function checkPassStrength(v){let n=0;if(v.length>=8)n++;if(/[A-Z]/.test(v))n++;if(/[a-z]/.test(v))n++;if(/[0-9]/.test(v))n++;if(/[^A-Za-z0-9]/.test(v))n++;let e=document.getElementById('passStrength'),m=document.getElementById('passMeter');let labels=['পাসওয়ার্ড লিখুন','দুর্বল পাসওয়ার্ড','মাঝারি পাসওয়ার্ড','ভালো পাসওয়ার্ড','শক্তিশালী পাসওয়ার্ড','খুব শক্তিশালী পাসওয়ার্ড'];e.textContent=labels[n];e.className='small mt-2 '+(n>=4?'text-success':n>=2?'text-warning':'text-danger');m.style.width=(n*20)+'%';m.style.background=n>=4?'#21966b':n>=2?'#d99a27':'#d34b58';}</script>'''
    return render_template_string(BASE_HTML.replace('{% block content %}{% endblock %}', body))

@app.route('/customer/resend-otp', methods=['POST'])
def customer_resend_otp():
    identity = session.get('reg_identity')
    if not identity:
        return redirect(url_for('customer_register'))
    db = get_db()
    db.execute('''CREATE TABLE IF NOT EXISTS pending_registrations_v2 (
        identity TEXT PRIMARY KEY, email TEXT, phone TEXT, name TEXT NOT NULL,
        password_hash TEXT NOT NULL, otp_hash TEXT NOT NULL, expires_at REAL NOT NULL)''')
    pending = db.execute('SELECT * FROM pending_registrations_v2 WHERE identity=?', (identity,)).fetchone()
    if not pending:
        flash('রেজিস্ট্রেশনের তথ্য পাওয়া যায়নি। আবার চেষ্টা করুন।', 'danger')
        return redirect(url_for('customer_register'))
    otp = f"{secrets.randbelow(1000000):06d}"
    db.execute('UPDATE pending_registrations_v2 SET otp_hash=?,expires_at=? WHERE identity=?',
               (generate_password_hash(otp, method='pbkdf2:sha256'), (datetime.utcnow()+timedelta(minutes=10)).timestamp(), identity))
    db.commit()
    try:
        send_registration_otp(pending['email'] or '', pending['phone'] or '', otp)
        flash('নতুন OTP পাঠানো হয়েছে।', 'success')
    except Exception as exc:
        app.logger.exception('Resend registration OTP failed')
        flash(str(exc), 'danger')
    return redirect(url_for('customer_verify_otp'))

@app.route('/customer/verify-otp', methods=['GET', 'POST'])
def customer_verify_otp():
    identity = session.get('reg_identity')
    if not identity:
        return redirect(url_for('customer_register'))
    db = get_db()
    db.execute('''CREATE TABLE IF NOT EXISTS pending_registrations_v2 (
        identity TEXT PRIMARY KEY, email TEXT, phone TEXT, name TEXT NOT NULL,
        password_hash TEXT NOT NULL, otp_hash TEXT NOT NULL, expires_at REAL NOT NULL)''')
    pending = db.execute('SELECT * FROM pending_registrations_v2 WHERE identity=?', (identity,)).fetchone()
    if not pending:
        flash('রেজিস্ট্রেশনের তথ্য পাওয়া যায়নি। আবার শুরু করুন।', 'danger')
        session.pop('reg_identity', None)
        return redirect(url_for('customer_register'))
    if request.method == 'POST':
        entered = request.form.get('otp', '').strip()
        if datetime.utcnow().timestamp() <= pending['expires_at'] and check_password_hash(pending['otp_hash'], entered):
            email = (pending['email'] or '').strip().lower()
            phone = pending['phone'] or ''
            # Existing schema has email NOT NULL; phone-only accounts get an internal non-deliverable alias.
            stored_email = email or ('phone.' + re.sub(r'\D','',phone) + '@phone.fayez.local')
            try:
                if phone:
                    duplicate = db.execute("SELECT id FROM customers WHERE replace(replace(replace(replace(replace(phone,' ',''),'-',''),'+',''),'(',''),')','') LIKE ?", ('%'+phone[-11:],)).fetchone()
                else:
                    duplicate = db.execute('SELECT id FROM customers WHERE lower(trim(email))=?', (stored_email,)).fetchone()
                if duplicate:
                    raise ValueError('এই ইমেইল/ফোন নম্বর দিয়ে ইতোমধ্যে অ্যাকাউন্ট রয়েছে।')
                cur = db.execute('INSERT INTO customers(name,email,phone,password_hash,is_verified) VALUES(?,?,?,?,1)',
                                 (pending['name'], stored_email, phone or None, pending['password_hash']))
                customer_id = cur.lastrowid
                db.execute('DELETE FROM pending_registrations_v2 WHERE identity=?', (identity,))
                db.commit()
                customer = db.execute('SELECT id,name FROM customers WHERE id=?', (customer_id,)).fetchone()
                session.clear()
                session['customer_id'], session['customer_name'] = customer['id'], customer['name']
                _fayez_track_customer_event('login', None, 'Customer registration verified')
                flash('OTP যাচাই সফল! আপনার অ্যাকাউন্ট তৈরি হয়েছে।', 'success')
                return redirect(url_for('customer_dashboard'))
            except Exception as exc:
                db.rollback()
                flash(str(exc), 'danger')
        else:
            flash('ভুল OTP অথবা কোডের মেয়াদ শেষ। আবার OTP পাঠান।', 'danger')
    channel = ('ফোন নম্বরে SMS' if pending['phone'] else 'ইমেইলে')
    body = f'''<div class="container my-5" style="max-width:430px"><div class="card p-4 shadow-sm border-0 rounded-4 text-center"><i class="fa fa-shield-halved fa-3x text-primary mb-3"></i><h4 class="fw-bold mb-2">OTP ভেরিফিকেশন</h4><p class="small text-muted mb-3">আপনার {channel} পাঠানো ৬-ডিজিটের কোডটি লিখুন।</p><form method="POST"><div class="mb-3"><input type="text" inputmode="numeric" pattern="[0-9]{{6}}" class="form-control text-center fs-4 fw-bold" name="otp" maxlength="6" placeholder="123456" required></div><button type="submit" class="btn btn-success w-100 rounded-pill fw-bold py-2">ভেরিফাই ও অ্যাকাউন্ট তৈরি করুন</button></form><form method="POST" action="/customer/resend-otp" class="mt-2"><button class="btn btn-outline-primary w-100" type="submit">আবার OTP পাঠান</button></form></div></div>'''
    return render_template_string(BASE_HTML.replace('{% block content %}{% endblock %}', body))

@app.route('/customer/dashboard')
@customer_required
def customer_dashboard():
    orders = get_db().execute('SELECT * FROM orders WHERE customer_id = ? ORDER BY id DESC', (session['customer_id'],)).fetchall()
    body = '''
    <div class="container my-5">
        <h3 class="fw-bold mb-3"><i class="fa fa-user-circle text-primary me-2"></i>স্বাগতম, {{ session.get('customer_name') }}!</h3>
        <div class="card p-4 shadow-sm border-0 rounded-4">
            <h5 class="fw-bold mb-3">আপনার অর্ডার ইতিহাস</h5>
            <div class="table-responsive">
                <table class="table align-middle">
                    <thead class="table-light"><tr><th>অর্ডার আইডি</th><th>মোট টাকা</th><th>পেমেন্ট</th><th>স্ট্যাটাস</th><th>ইনভয়েস</th></tr></thead>
                    <tbody>
                        {% for o in orders %}
                        <tr>
                            <td class="fw-bold text-primary">{{ o.order_id }}</td>
                            <td>৳ {{ "%.2f"|format(o.total_amount) }}</td>
                            <td>{{ o.payment_method }}</td>
                            <td><span class="badge {% if o.order_status == 'Confirmed' %}bg-success{% else %}bg-warning text-dark{% endif %}">{{ o.order_status }}</span></td>
                            <td><a href="/order/invoice/{{ o.order_id }}" class="btn btn-sm btn-outline-primary rounded-pill">ইনভয়েস</a></td>
                        </tr>
                        {% endfor %}
                    </tbody>
                </table>
            </div>
        </div>
    </div>'''
    return render_template_string(BASE_HTML.replace('{% block content %}{% endblock %}', body), orders=orders)

@app.route('/customer/logout')
def customer_logout():
    session.clear()
    flash('লগআউট সফল হয়েছে।', 'info')
    return redirect(url_for('home'))

@app.route('/admin/login', methods=['GET', 'POST'])
def admin_login():
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        adm = get_db().execute('SELECT * FROM admins WHERE username = ?', (username,)).fetchone()
        if adm and check_password_hash(adm['password_hash'], password):
            session.clear()
            session.permanent = True
            session['is_admin'] = True
            session['admin_username'] = adm['username']
            _fayez_log('admin_login', 'Owner login successful')
            return redirect(url_for('admin_dashboard'))
        flash('ভুল ইউজারনেম বা পাসওয়ার্ড। আবার চেষ্টা করুন।', 'danger')
    return render_template_string('''<!DOCTYPE html><html lang="bn"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>Fayez Owner Portal</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
    <style>
      body{min-height:100vh;background:radial-gradient(circle at 15% 15%,#1e3a5f 0,#0b1220 42%,#050914 100%);color:#f8fafc}
      .owner-card{width:min(92vw,440px);background:rgba(15,23,42,.94);border:1px solid rgba(148,163,184,.2)!important;box-shadow:0 24px 80px rgba(0,0,0,.45)!important;backdrop-filter:blur(14px)}
      .owner-mark{width:72px;height:72px;border-radius:22px;display:grid;place-items:center;margin:0 auto 18px;background:linear-gradient(135deg,#fbbf24,#f59e0b);color:#111827}
      .form-control{min-height:48px}.form-control:focus{border-color:#fbbf24;box-shadow:0 0 0 .2rem rgba(251,191,36,.15)}
    </style></head>
    <body class="d-flex align-items-center justify-content-center p-3">
    <div class="card owner-card p-4 p-md-5 rounded-4">
        <div class="text-center mb-4"><div class="owner-mark"><i class="fa fa-shield-halved fa-2x"></i></div><h3 class="fw-bold">Fayez Owner Login</h3><p class="small text-secondary mb-0">Fayez Online Shop · নিরাপদ মালিক প্রবেশ</p></div>
        {% with messages = get_flashed_messages(with_categories=true) %}{% for category, message in messages %}<div class="alert alert-{{ 'danger' if category == 'danger' else 'info' }} py-2 small" role="alert">{{ message }}</div>{% endfor %}{% endwith %}
        <form method="POST" autocomplete="on">
            <div class="mb-3"><label class="form-label small fw-semibold">ইউজারনেম</label><input type="text" class="form-control bg-dark text-white border-secondary" name="username" autocomplete="username" placeholder="আপনার Owner Username" required></div>
            <div class="mb-4"><label class="form-label small fw-semibold">পাসওয়ার্ড</label><div class="input-group">
                <input type="password" class="form-control bg-dark text-white border-secondary" id="adminPassInput" name="password" autocomplete="current-password" placeholder="আপনার পাসওয়ার্ড" required>
                <button class="btn btn-outline-secondary" type="button" onclick="toggleAdminPass()" aria-label="পাসওয়ার্ড দেখুন"><i class="fa fa-eye" id="adminEyeIcon"></i></button>
            </div></div>
            <button type="submit" class="btn btn-warning w-100 fw-bold rounded-pill py-3">নিরাপদে লগইন করুন <i class="fa fa-arrow-right ms-1"></i></button>
        </form>
        <div class="text-center mt-4"><a href="/" class="text-decoration-none small text-secondary">← স্টোরফ্রন্টে ফিরে যান</a></div>
        <div class="text-center mt-3"><span class="small text-secondary"><i class="fa fa-lock me-1"></i>Protected Owner Access</span></div>
    </div>
    <script>function toggleAdminPass(){let p=document.getElementById('adminPassInput');let ic=document.getElementById('adminEyeIcon');if(p.type==='password'){p.type='text';ic.classList.replace('fa-eye','fa-eye-slash')}else{p.type='password';ic.classList.replace('fa-eye-slash','fa-eye')}}</script>
    </body></html>''')

@app.route('/admin/dashboard')
@admin_required
def admin_dashboard():
    db = get_db()
    # Additive migration: records are preserved; purchase cost is needed for real profit reports.
    cols = {r['name'] for r in db.execute('PRAGMA table_info(products)').fetchall()}
    if 'purchase_price' not in cols:
        db.execute('ALTER TABLE products ADD COLUMN purchase_price REAL NOT NULL DEFAULT 0')
        db.commit()
    orders = db.execute('SELECT * FROM orders ORDER BY id DESC LIMIT 8').fetchall()
    products = db.execute('SELECT * FROM products WHERE COALESCE(is_active,1)=1 ORDER BY id DESC').fetchall()
    banners = db.execute('SELECT * FROM banners ORDER BY id DESC').fetchall()
    coupons = db.execute('SELECT * FROM coupons ORDER BY id DESC').fetchall()
    today = datetime.now().strftime('%Y-%m')
    sales = db.execute("SELECT COALESCE(SUM(total_amount),0) FROM orders WHERE substr(created_at,1,7)=? AND COALESCE(order_status,'') NOT IN ('Cancelled','Returned','Refunded')", (today,)).fetchone()[0]
    all_sales = db.execute("SELECT COALESCE(SUM(total_amount),0) FROM orders WHERE COALESCE(order_status,'') NOT IN ('Cancelled','Returned','Refunded')").fetchone()[0]
    total_orders = db.execute("SELECT COUNT(*) FROM orders WHERE COALESCE(order_status,'') NOT IN ('Cancelled','Returned','Refunded')").fetchone()[0]
    stock = db.execute("SELECT COUNT(*) product_count,COUNT(DISTINCT category_id) category_count,COALESCE(SUM(stock),0) stock_units FROM products WHERE category_id IN (SELECT id FROM categories WHERE slug IN (%s))" % ','.join('?' for _ in CURATED_CATEGORY_SLUGS), CURATED_CATEGORY_SLUGS).fetchone()
    sold = db.execute("SELECT COALESCE(SUM(oi.quantity),0) FROM order_items oi JOIN orders o ON o.id=oi.order_id WHERE COALESCE(o.order_status,'') NOT IN ('Cancelled','Returned','Refunded')").fetchone()[0]
    # Profit is based on recorded purchase cost. Old products with no cost entered are not falsely counted as profit.
    profit = db.execute("SELECT COALESCE(SUM((oi.price-COALESCE(p.purchase_price,0))*oi.quantity),0) FROM order_items oi JOIN orders o ON o.id=oi.order_id JOIN products p ON p.id=oi.product_id WHERE COALESCE(o.order_status,'') NOT IN ('Cancelled','Returned','Refunded')").fetchone()[0]
    month_profit = db.execute("SELECT COALESCE(SUM((oi.price-COALESCE(p.purchase_price,0))*oi.quantity),0) FROM order_items oi JOIN orders o ON o.id=oi.order_id JOIN products p ON p.id=oi.product_id WHERE substr(o.created_at,1,7)=? AND COALESCE(o.order_status,'') NOT IN ('Cancelled','Returned','Refunded')", (today,)).fetchone()[0]
    leaderboard = db.execute("SELECT c.id,c.name,c.email,c.phone,COUNT(o.id) orders,COALESCE(SUM(o.total_amount),0) spent,COALESCE(AVG(o.total_amount),0) average_order FROM customers c JOIN orders o ON o.customer_id=c.id WHERE COALESCE(o.order_status,'') NOT IN ('Cancelled','Returned','Refunded') GROUP BY c.id ORDER BY spent DESC,c.id ASC LIMIT 5").fetchall()
    week_sales = db.execute("SELECT COALESCE(SUM(total_amount),0) FROM orders WHERE date(created_at)>=date('now','localtime','weekday 0','-6 days') AND COALESCE(order_status,'') NOT IN ('Cancelled','Returned','Refunded')").fetchone()[0]
    district_sales = db.execute("SELECT COALESCE(NULLIF(TRIM(district),''),'ঠিকানা নেই') district,COUNT(*) orders,COALESCE(SUM(total_amount),0) sales FROM orders WHERE COALESCE(order_status,'') NOT IN ('Cancelled','Returned','Refunded') GROUP BY district ORDER BY sales DESC LIMIT 8").fetchall()
    division_sales = db.execute("SELECT COALESCE(NULLIF(TRIM(division),''),'ঠিকানা নেই') division,COUNT(*) orders,COALESCE(SUM(total_amount),0) sales FROM orders WHERE COALESCE(order_status,'') NOT IN ('Cancelled','Returned','Refunded') GROUP BY division ORDER BY sales DESC LIMIT 8").fetchall()
    low_stock = db.execute('SELECT id,name,stock,image FROM products WHERE COALESCE(is_active,1)=1 AND stock<=5 ORDER BY stock ASC LIMIT 5').fetchall()
    owner_profile = db.execute('SELECT * FROM owner_profile WHERE id=1').fetchone() if db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='owner_profile'").fetchone() else None
    return render_template_string(r'''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Fayez Online Shop | Admin</title>
<link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/css/bootstrap.min.css" rel="stylesheet"><link href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.5.2/css/all.min.css" rel="stylesheet"><script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
<style>
:root{--blue:#087cf0;--ink:#17243b;--muted:#718096;--line:#edf1f7;--bg:#f6f9fd}*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font-family:Inter,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}.sidebar{position:fixed;inset:0 auto 0 0;width:242px;background:#fff;border-right:1px solid var(--line);padding:24px 15px;overflow:auto;z-index:5}.brand{font-size:25px;font-weight:800;line-height:1.05;color:#14264a}.brand span{display:block;color:var(--blue);font-size:17px}.brandmark{display:flex;gap:12px;align-items:center;margin:4px 8px 24px}.brandmark i{font-size:37px;color:var(--blue)}.navlink{display:flex;align-items:center;gap:14px;padding:12px 13px;margin:3px 0;border-radius:9px;color:#263449;text-decoration:none;font-weight:600;font-size:14px}.navlink i{width:20px;color:#60718a;font-size:17px}.navlink:hover,.navlink.active{background:var(--blue);color:#fff}.navlink:hover i,.navlink.active i{color:#fff}.main{margin-left:242px;padding:18px 24px 36px}.topbar{height:48px;display:flex;align-items:center;justify-content:space-between;margin-bottom:24px}.search{background:#fff;border:1px solid var(--line);border-radius:12px;padding:12px 16px;width:min(55%,680px);color:#8190a5}.panel{background:#fff;border:1px solid #eef2f8;border-radius:16px;box-shadow:0 5px 18px #29466d08}.metric{padding:17px;min-height:118px}.metric .ico{width:48px;height:48px;border-radius:14px;display:grid;place-items:center;font-size:21px}.metric strong{font-size:25px;display:block;margin-top:7px}.section-title{font-weight:800;font-size:19px;margin:0}.quick{display:grid;grid-template-columns:repeat(5,minmax(0,1fr));gap:10px}.quick a{display:flex;flex-direction:column;align-items:center;justify-content:center;gap:9px;text-align:center;min-height:94px;padding:12px 7px;border-radius:13px;text-decoration:none;color:var(--ink);font-weight:700;font-size:13px;background:#f8fbff;border:1px solid #f0f4fa}.quick a:hover{border-color:#9ac9ff;background:#eff7ff}.quick i{font-size:23px;color:var(--blue)}.table th{font-size:12px;color:#728198;background:#f8fafd}.table td{font-size:13px;vertical-align:middle}.avatar{width:34px;height:34px;object-fit:cover;border-radius:50%;background:#edf2f8}.low{color:#e44b4b;font-size:12px}.chart-wrap{height:225px}.smallmuted{color:var(--muted);font-size:13px}@media(max-width:1050px){.sidebar{width:205px}.main{margin-left:205px}.quick{grid-template-columns:repeat(3,1fr)}}@media(max-width:700px){.sidebar{position:relative;width:auto;height:auto;padding:12px;display:flex;flex-wrap:wrap;gap:4px}.brandmark{width:100%;margin:3px 5px 8px}.navlink{padding:8px 9px;font-size:12px;margin:0}.navlink:not(.active){display:none}.sidebar.showall .navlink{display:flex}.main{margin:0;padding:13px}.topbar{margin-bottom:15px}.search{width:70%}.quick{grid-template-columns:repeat(2,1fr)}.metric strong{font-size:20px}.chart-wrap{height:190px}}
</style></head><body>
<aside class="sidebar" id="sidebar"><div class="brandmark"><i class="fa-solid fa-bag-shopping"></i><div class="brand">Fayez<span>Online Shop</span></div></div>
<a class="navlink active" href="/admin/dashboard"><i class="fa-solid fa-house"></i>Dashboard</a>
<a class="navlink" href="/admin/section/banners"><i class="fa-regular fa-image"></i>Hero Slider Banner Management</a><a class="navlink" href="/admin/section/coupons"><i class="fa-solid fa-ticket"></i>Coupon Code Management</a><a class="navlink" href="/admin/section/discounts"><i class="fa-solid fa-percent"></i>Discount Management</a><a class="navlink" href="/admin/section/categories"><i class="fa-solid fa-border-all"></i>Category Management</a><a class="navlink" href="/admin/section/products"><i class="fa-solid fa-box-open"></i>Product Management</a><a class="navlink" href="/admin/section/orders"><i class="fa-solid fa-cart-shopping"></i>Order Management</a><a class="navlink" href="/admin/customers"><i class="fa-solid fa-users"></i>Customer Management</a><a class="navlink" href="/admin/section/stock"><i class="fa-solid fa-layer-group"></i>Stock Management</a><a class="navlink" href="/admin/section/reports"><i class="fa-solid fa-chart-column"></i>Sales & Profit Report</a><a class="navlink" href="/admin/section/leaderboard"><i class="fa-solid fa-trophy"></i>LeaderBoard</a><a class="navlink" href="/admin/section/settings"><i class="fa-solid fa-gear"></i>Settings</a><a class="navlink" href="/admin/logout"><i class="fa-solid fa-right-from-bracket"></i>Logout</a>
</aside><main class="main"><header class="topbar"><button class="btn btn-light d-md-none" onclick="document.getElementById('sidebar').classList.toggle('showall')"><i class="fa fa-bars"></i></button><div class="search"><i class="fa fa-search me-2"></i>Search anything...</div><div class="d-flex align-items-center gap-3"><a href="/" target="_blank" class="text-decoration-none small">Live Shop ↗</a><div class="text-end"><b>Admin</b><div class="small text-primary">Super Admin</div></div></div></header>
<div class="d-flex justify-content-between align-items-center mb-3"><div><h2 class="fw-bold mb-1">▦ Admin Dashboard</h2><div class="smallmuted">Welcome back, Admin! Here's your business overview.</div></div><span class="badge bg-white text-dark border p-2"><i class="fa-regular fa-calendar me-1"></i> This Month</span></div>
<div class="row g-3 mb-4"><div class="col-6 col-xl-3"><div class="panel metric"><div class="d-flex align-items-center gap-3"><div class="ico" style="background:#e6f2ff;color:#1684f7"><i class="fa fa-cart-shopping"></i></div><div class="smallmuted">Total Sales</div></div><strong>৳{{ '%.0f'|format(all_sales) }}</strong><span class="small text-primary">{{ total_orders }} orders</span></div></div><div class="col-6 col-xl-3"><div class="panel metric"><div class="d-flex align-items-center gap-3"><div class="ico" style="background:#e5faef;color:#13b76b"><i class="fa fa-users"></i></div><div class="smallmuted">Total Orders</div></div><strong>{{ total_orders }}</strong><span class="small text-success">{{ sold }} items sold</span></div></div><div class="col-6 col-xl-3"><div class="panel metric"><div class="d-flex align-items-center gap-3"><div class="ico" style="background:#f2eaff;color:#914cf0"><i class="fa fa-coins"></i></div><div class="smallmuted">Total Profit*</div></div><strong>৳{{ '%.0f'|format(profit) }}</strong><span class="small text-success">This month ৳{{ '%.0f'|format(month_profit) }}</span></div></div><div class="col-6 col-xl-3"><div class="panel metric"><div class="d-flex align-items-center gap-3"><div class="ico" style="background:#fff0e2;color:#f28a20"><i class="fa fa-wallet"></i></div><div class="smallmuted">This Month Sales</div></div><strong>৳{{ '%.0f'|format(sales) }}</strong><span class="smallmuted">{{ stock.product_count }} পণ্য · {{ stock.category_count }} ক্যাটাগরি · রেকর্ডকৃত স্টক {{ stock.stock_units }}</span></div></div></div>
<div class="row g-3 mb-4"><div class="col-xl-7"><section class="panel p-3 h-100"><div class="d-flex justify-content-between mb-3"><h5 class="section-title"><i class="fa fa-chart-column text-primary me-2"></i>Sales Overview</h5><span class="smallmuted">Monthly</span></div><div class="chart-wrap"><canvas id="salesChart"></canvas></div></section></div><div class="col-xl-5"><section class="panel p-3 h-100"><div class="d-flex justify-content-between mb-3"><h5 class="section-title"><i class="fa fa-trophy text-warning me-2"></i>Top Customers</h5><a href="/admin/section/leaderboard" class="small text-primary">View All →</a></div>{% for c in leaderboard %}<div class="d-flex align-items-center gap-2 py-2 border-bottom"><span class="badge rounded-circle bg-warning text-dark">{{ loop.index }}</span><div class="flex-grow-1"><b class="small">{{ c.name }}</b><div class="smallmuted">{{ c.orders }} Orders</div></div><b class="small">৳{{ '%.0f'|format(c.spent) }}</b></div>{% else %}<p class="smallmuted">No customer orders yet.</p>{% endfor %}</section></div></div>
<section class="panel p-3 mb-4"><h5 class="section-title mb-3"><i class="fa fa-bolt text-warning me-2"></i>Quick Management</h5><div class="quick"><a href="/admin/section/banners"><i class="fa-regular fa-image"></i>Hero Slider Banner<br>Management</a><a href="/admin/section/coupons"><i class="fa-solid fa-ticket"></i>Coupon Code<br>Management</a><a href="/admin/section/discounts"><i class="fa fa-percent"></i>Discount<br>Management</a><a href="/admin/section/categories"><i class="fa fa-border-all"></i>Add New Category</a><a href="/admin/section/products"><i class="fa fa-box-open"></i>Add New Product</a><a href="/admin/section/orders"><i class="fa fa-cart-shopping"></i>Manage Orders</a><a href="/admin/customers"><i class="fa fa-users"></i>Manage Customers</a><a href="/admin/section/stock"><i class="fa fa-cubes"></i>Stock Management</a><a href="/admin/section/reports"><i class="fa fa-chart-line"></i>Sales Report</a><a href="/admin/section/leaderboard"><i class="fa fa-trophy"></i>Leaderboard</a></div></section>
<div class="row g-3 mb-4"><div class="col-md-4"><section class="panel p-3 h-100"><div class="smallmuted">এই সপ্তাহের বিক্রি</div><div class="fs-3 fw-bold text-primary">৳{{ '%.0f'|format(week_sales) }}</div></section></div><div class="col-md-4"><section class="panel p-3 h-100"><div class="smallmuted">জেলা অনুযায়ী বেশি ব্যবসা</div>{% for r in district_sales[:5] %}<div class="d-flex justify-content-between small border-bottom py-1"><span>{{ r.district }} ({{ r.orders }})</span><b>৳{{ '%.0f'|format(r.sales) }}</b></div>{% else %}<small class="text-muted">এখনো বিক্রির তথ্য নেই</small>{% endfor %}</section></div><div class="col-md-4"><section class="panel p-3 h-100"><div class="smallmuted">বিভাগ অনুযায়ী বেশি ব্যবসা</div>{% for r in division_sales[:5] %}<div class="d-flex justify-content-between small border-bottom py-1"><span>{{ r.division }} ({{ r.orders }})</span><b>৳{{ '%.0f'|format(r.sales) }}</b></div>{% else %}<small class="text-muted">এখনো বিক্রির তথ্য নেই</small>{% endfor %}</section></div></div>
<div class="row g-3"><div class="col-xl-7"><section class="panel p-3"><div class="d-flex justify-content-between mb-2"><h5 class="section-title"><i class="fa fa-cart-shopping text-primary me-2"></i>Recent Orders</h5><a href="/admin/section/orders" class="small text-primary">View All →</a></div><div class="table-responsive"><table class="table"><thead><tr><th>Order #</th><th>Customer</th><th>Amount</th><th>Status</th><th>Date</th><th>Action</th></tr></thead><tbody>{% for o in orders %}<tr><td>{{ o.order_id }}</td><td>{{ o.recipient_name or 'Customer' }}</td><td>৳{{ '%.0f'|format(o.total_amount) }}</td><td><span class="badge bg-info-subtle text-dark">{{ o.order_status }}</span></td><td>{{ o.created_at }}</td><td>{% if (o.order_status or '')|lower=='cancelled' %}<form method="post" action="/admin/order/delete-cancelled/{{ o.id }}" onsubmit="return confirm('এই Cancelled অর্ডারটি স্থায়ীভাবে ডিলিট করবেন?')"><button class="btn btn-sm btn-outline-danger">Delete</button></form>{% else %}<span class="text-muted small">—</span>{% endif %}</td></tr>{% else %}<tr><td colspan="6">No orders yet.</td></tr>{% endfor %}</tbody></table></div></section></div><div class="col-xl-5"><section class="panel p-3"><div class="d-flex justify-content-between mb-2"><h5 class="section-title"><i class="fa fa-triangle-exclamation text-danger me-2"></i>Stock Alert</h5><a href="/admin/section/stock" class="small text-primary">View All →</a></div>{% for p in low_stock %}<div class="d-flex align-items-center gap-3 py-2 border-bottom">{% if p.image %}<img src="{{ p.image }}" class="avatar">{% else %}<span class="avatar d-grid place-items-center"><i class="fa fa-box"></i></span>{% endif %}<div class="flex-grow-1"><b class="small">{{ p.name }}</b><div class="low">Only {{ p.stock }} left!</div></div><span class="badge bg-danger-subtle text-danger">Low Stock</span></div>{% else %}<p class="smallmuted">No low-stock products.</p>{% endfor %}</section></div></div>
<p class="smallmuted mt-3">* Profit হিসাব purchase price দেওয়া পণ্যের জন্য নির্ভরযোগ্য। পুরোনো পণ্যের ক্রয়মূল্য Product Management থেকে যোগ করুন।</p></main>
<script>const ctx=document.getElementById('salesChart');new Chart(ctx,{type:'line',data:{labels:['1','5','10','15','20','25','30'],datasets:[{label:'Sales',data:[0,0,0,0,0,0,{{ sales|int }}],borderColor:'#1684f7',backgroundColor:'#1684f722',fill:true,tension:.35},{label:'Profit',data:[0,0,0,0,0,0,{{ month_profit|int }}],borderColor:'#13b76b',backgroundColor:'#13b76b22',fill:true,tension:.35}]},options:{responsive:true,maintainAspectRatio:false,plugins:{legend:{position:'top'}},scales:{y:{beginAtZero:true}}}});</script></body></html>''', orders=orders, stock=stock, sold=sold, sales=sales, all_sales=all_sales, total_orders=total_orders, profit=profit, month_profit=month_profit, leaderboard=leaderboard, low_stock=low_stock, week_sales=week_sales, district_sales=district_sales, division_sales=division_sales)

def _ensure_category_admin_schema(db):
    """Safely add missing category columns without deleting existing records."""
    cols = {row['name'] for row in db.execute('PRAGMA table_info(categories)').fetchall()}
    if 'slug' not in cols:
        db.execute('ALTER TABLE categories ADD COLUMN slug TEXT')
        cols.add('slug')
    if 'image' not in cols:
        db.execute('ALTER TABLE categories ADD COLUMN image TEXT')
        cols.add('image')
    if 'image_url' in cols:
        db.execute("UPDATE categories SET image=image_url WHERE (image IS NULL OR image='') AND image_url IS NOT NULL")
    rows = db.execute("SELECT id,name FROM categories WHERE slug IS NULL OR TRIM(slug)='' ").fetchall()
    for row in rows:
        base = re.sub(r'[^a-z0-9]+', '-', (row['name'] or '').lower()).strip('-') or ('category-' + str(row['id']))
        slug, n = base, 2
        while db.execute('SELECT 1 FROM categories WHERE slug=? AND id<>?', (slug,row['id'])).fetchone():
            slug, n = f'{base}-{n}', n + 1
        db.execute('UPDATE categories SET slug=? WHERE id=?', (slug,row['id']))
    db.commit()


@app.route('/admin/section/<section>')
@admin_required
def admin_section(section):
    db=get_db()
    if section=='categories':
        _ensure_category_admin_schema(db)
    allowed={'banners':'Hero Slider Banner Management','coupons':'Coupon Code Management','discounts':'Discount Management','categories':'Category Management','products':'Product Management','orders':'Order Management','stock':'Stock Management','reports':'Sales & Profit Report','leaderboard':'Leaderboard','settings':'Settings'}
    if section not in allowed: return redirect(url_for('admin_dashboard'))
    title=allowed[section]
    if section=='banners':
        rows=db.execute('SELECT * FROM banners ORDER BY id DESC').fetchall()
        body='''<style>.media-preview{width:100%;height:150px;object-fit:cover;border-radius:12px;background:#f1f5f9;border:1px solid #e5eaf1}.banner-card{border:1px solid #edf1f7;border-radius:14px;padding:14px;height:100%}</style>
        <div class="alert alert-info small">ছবি ফাইল আপলোড করুন অথবা সরাসরি ইমেজ URL দিন। সেভ করার আগে প্রিভিউ দেখে নিন।</div>
        <form action="/admin/banner/add" method="post" enctype="multipart/form-data" class="row g-3 mb-4 p-3 bg-light rounded-4">
        <div class="col-md-6"><label class="form-label fw-semibold">ব্যানারের শিরোনাম</label><input class="form-control" name="title" placeholder="যেমন: ঈদ স্পেশাল অফার" required></div>
        <div class="col-md-6"><label class="form-label fw-semibold">সাবটাইটেল</label><input class="form-control" name="subtitle" placeholder="ব্যানারের ছোট বিবরণ" required></div>
        <div class="col-lg-6"><label class="form-label fw-semibold">ছবি আপলোড</label><input class="form-control" type="file" name="banner_file" accept="image/jpeg,image/png,image/webp,image/gif" onchange="previewBannerFile(this)"><small class="text-muted">JPG, PNG, WEBP বা GIF</small></div>
        <div class="col-lg-6"><label class="form-label fw-semibold">অথবা ছবির URL</label><input class="form-control" type="url" name="image_url" id="bannerUrl" placeholder="https://example.com/banner.jpg" oninput="previewBannerUrl(this.value)"></div>
        <div class="col-md-8"><label class="form-label fw-semibold">ক্লিক করলে কোথায় যাবে (লিংক)</label><input class="form-control" name="link_url" value="/shop" required></div>
        <div class="col-md-4"><label class="form-label fw-semibold">ছবির প্রিভিউ</label><img id="bannerPreview" class="media-preview" src="" alt="Banner preview" onerror="this.style.opacity=.25"></div>
        <div class="col-12"><button class="btn btn-primary px-4"><i class="fa fa-plus me-2"></i>নতুন ব্যানার যোগ করুন</button></div></form>
        <h5 class="fw-bold mb-3">আপনার ব্যানারসমূহ ({{ rows|length }})</h5><div class="row g-3">{% for r in rows %}<div class="col-md-6 col-xl-4"><div class="banner-card"><img class="media-preview mb-3" src="{{ r.image_url }}" alt="{{ r.title }}"><b>{{ r.title }}</b><p class="small text-muted mb-2">{{ r.subtitle }}</p><div class="small text-break mb-3">{{ r.link_url }}</div><form method="post" action="/admin/banner/del/{{ r.id }}" onsubmit="return confirm('এই ব্যানারটি মুছে ফেলবেন?')"><button class="btn btn-sm btn-outline-danger">মুছে ফেলুন</button></form></div></div>{% else %}<p class="text-muted">এখনো কোনো ব্যানার যোগ করা হয়নি।</p>{% endfor %}</div>
        <script>function previewBannerUrl(v){if(v)document.getElementById('bannerPreview').src=v}function previewBannerFile(i){if(i.files&&i.files[0])document.getElementById('bannerPreview').src=URL.createObjectURL(i.files[0])}</script>'''
    elif section=='coupons':
        rows=db.execute('SELECT * FROM coupons ORDER BY id DESC').fetchall()
        body='''<div class="alert alert-info small">শতাংশ ছাড় অথবা নির্দিষ্ট টাকার ছাড় তৈরি করুন। মেয়াদ ও ব্যবহারসীমা ঐচ্ছিক।</div>
        <form action="/admin/coupon/add" method="post" class="row g-3 mb-4 p-3 bg-light rounded-4">
        <div class="col-md-4"><label class="form-label fw-semibold">কুপন কোড</label><input class="form-control text-uppercase" name="code" placeholder="FAYEZ20" required></div>
        <div class="col-md-3"><label class="form-label fw-semibold">ছাড়ের ধরন</label><select class="form-select" name="discount_type" id="couponType" onchange="document.getElementById('couponValueLabel').textContent=this.value==='percent'?'ছাড় (%)':'ছাড়ের টাকা (৳)'"><option value="percent">শতাংশ (%)</option><option value="fixed">নির্দিষ্ট টাকা (৳)</option></select></div>
        <div class="col-md-3"><label class="form-label fw-semibold" id="couponValueLabel">ছাড় (%)</label><input class="form-control" type="number" step=".01" min=".01" name="discount" placeholder="20" required></div>
        <div class="col-md-3"><label class="form-label fw-semibold">মেয়াদ শেষ</label><input class="form-control" type="date" name="expires_at"></div>
        <div class="col-md-3"><label class="form-label fw-semibold">সর্বোচ্চ ব্যবহার</label><input class="form-control" type="number" min="1" name="max_uses" placeholder="যেমন 100"></div>
        <div class="col-md-3 d-flex align-items-end"><button class="btn btn-primary w-100">কুপন তৈরি করুন</button></div></form>
        <div class="table-responsive"><table class="table align-middle"><thead><tr><th>কোড</th><th>ছাড়</th><th>মেয়াদ</th><th>ব্যবহার</th><th>অবস্থা</th><th>কন্ট্রোল</th></tr></thead><tbody>{% for r in rows %}<tr><td><b>{{ r.code }}</b></td><td>{% if r.discount_type=='fixed' %}৳{{ r.discount_amount }}{% else %}{{ r.discount_percent }}%{% endif %}</td><td>{{ r.expires_at or 'নির্ধারিত নয়' }}</td><td>{{ r.used_count or 0 }} / {{ r.max_uses or '∞' }}</td><td><span class="badge {{ 'bg-success' if r.is_active else 'bg-secondary' }}">{{ 'চালু' if r.is_active else 'বন্ধ' }}</span></td><td><form class="d-inline" method="post" action="/admin/coupon/toggle/{{ r.id }}"><button class="btn btn-sm btn-outline-primary">{{ 'বন্ধ করুন' if r.is_active else 'চালু করুন' }}</button></form> <form class="d-inline" method="post" action="/admin/coupon/delete/{{ r.id }}" onsubmit="return confirm('কুপনটি ডিলিট করবেন?')"><button class="btn btn-sm btn-outline-danger">Delete</button></form></td></tr>{% else %}<tr><td colspan="6">কোনো কুপন নেই।</td></tr>{% endfor %}</tbody></table></div>'''
    elif section=='products':
        rows=db.execute("SELECT p.*,COALESCE(c.name,'Uncategorised') category_name FROM products p LEFT JOIN categories c ON c.id=p.category_id WHERE COALESCE(p.is_active,1)=1 ORDER BY p.id DESC").fetchall()
        cats=db.execute('SELECT * FROM categories ORDER BY name COLLATE NOCASE').fetchall()
        category_stats=db.execute("SELECT c.id,c.name,c.image,COUNT(CASE WHEN COALESCE(p.is_active,1)=1 THEN p.id END) product_count,COALESCE(SUM(CASE WHEN COALESCE(p.is_active,1)=1 THEN p.stock ELSE 0 END),0) stock_units FROM categories c LEFT JOIN products p ON p.category_id=c.id GROUP BY c.id ORDER BY c.name COLLATE NOCASE").fetchall()
        total_units=db.execute('SELECT COALESCE(SUM(stock),0) FROM products WHERE COALESCE(is_active,1)=1').fetchone()[0]
        inventory_cost=db.execute('SELECT COALESCE(SUM(COALESCE(purchase_price,0)*COALESCE(stock,0)),0) FROM products WHERE COALESCE(is_active,1)=1').fetchone()[0]
        body='''<style>.pm-hero{background:linear-gradient(125deg,#101c3b,#244b86);color:#fff;border-radius:18px;padding:22px}.pm-stat{border:1px solid #e7ebf2;border-radius:15px;padding:15px;height:100%}.pm-stat strong{font-size:1.6rem}.pm-cat{border:1px solid #e7ebf2;border-radius:14px;overflow:hidden;height:100%;background:var(--bs-body-bg);transition:.18s}.pm-cat:hover{transform:translateY(-3px);box-shadow:0 8px 22px #17255418}.pm-cat img{width:100%;height:105px;object-fit:cover}.pm-cat-body{padding:11px}.prod-preview{width:100%;height:130px;object-fit:contain;background:#f7f8fc;border:1px dashed #cbd5e1;border-radius:12px}.product-form .form-label{font-weight:650}</style>
        <div class="pm-hero mb-3"><div class="small opacity-75">FAYEZ ONLINE SHOP · CATALOG CENTER</div><h3 class="fw-bold mb-1">Product Management</h3><div class="opacity-75">Amazon / Daraz ধাঁচের সহজ ক্যাটালগ ও ইনভেন্টরি কন্ট্রোল</div></div>
        <div class="row g-3 mb-4"><div class="col-6 col-xl-3"><div class="pm-stat"><small class="text-secondary">মোট পণ্য</small><br><strong>{{ rows|length }}</strong><div class="small text-secondary">লাইভ ডেটাবেস হিসাব</div></div></div><div class="col-6 col-xl-3"><div class="pm-stat"><small class="text-secondary">মোট ক্যাটাগরি</small><br><strong>{{ cats|length }}</strong><div class="small text-secondary">সংরক্ষিত ক্যাটাগরি</div></div></div><div class="col-6 col-xl-3"><div class="pm-stat"><small class="text-secondary">মোট স্টক ইউনিট</small><br><strong>{{ total_units }}</strong><div class="small text-secondary">প্রকৃত স্টক যোগফল</div></div></div><div class="col-6 col-xl-3"><div class="pm-stat"><small class="text-secondary">স্টকের ক্রয়মূল্য</small><br><strong>৳{{ '%.0f'|format(inventory_cost) }}</strong><div class="small text-secondary">ক্রয়মূল্য × স্টক</div></div></div></div>
        <div class="d-flex justify-content-between align-items-center mb-3"><div><h5 class="fw-bold mb-1">ক্যাটাগরি অনুযায়ী পণ্য</h5><small class="text-secondary">প্রতিটি কার্ডে ক্যাটাগরির ছবি, পণ্যের সংখ্যা ও স্টক দেখুন।</small></div><span class="badge text-bg-primary">Live categories</span></div>
        <div class="row g-3 mb-4">{% for c in category_stats %}<div class="col-6 col-md-4 col-xl-3"><div class="pm-cat">{% if c.image %}<img src="{{ c.image }}" alt="{{ c.name }}" onerror="this.style.display='none'">{% endif %}<div class="pm-cat-body"><b>{{ c.name }}</b><div class="d-flex justify-content-between mt-2"><small class="text-secondary">পণ্য</small><b>{{ c.product_count }}</b></div><div class="d-flex justify-content-between"><small class="text-secondary">স্টক ইউনিট</small><b>{{ c.stock_units }}</b></div><span class="badge mt-2 {{ 'text-bg-success' if c.product_count else 'text-bg-secondary' }}">{{ 'পণ্য আছে' if c.product_count else 'এখনো পণ্য নেই' }}</span></div></div></div>{% else %}<div class="col-12"><div class="alert alert-light border">কোনো ক্যাটাগরি নেই। Category Management থেকে তৈরি করুন।</div></div>{% endfor %}</div>
        <div class="d-flex justify-content-between align-items-center flex-wrap gap-2 mb-3"><div><div class="fw-bold fs-5">Product Control Center</div><div class="small text-secondary">এক জায়গা থেকে পণ্য যোগ, খোঁজা, সম্পাদনা, স্টক ও বাল্ক ডিলিট করুন।</div></div><span class="badge text-bg-primary">{{ rows|length }}টি পণ্য</span></div><div class="alert alert-info small">কোনো ডেমো পণ্য রাখা নেই। নিজের পণ্য যোগ করতে নিচের ফর্ম ব্যবহার করুন। সর্বোচ্চ ৩টি ছবি, SKU, ক্রয়মূল্য, বিক্রয়মূল্য, স্টক ও ভ্যারিয়েন্ট যোগ করা যাবে।</div>
        <form action="/admin/product/add" method="post" enctype="multipart/form-data" class="product-form row g-3 mb-4 p-3 bg-light rounded-4">
        <div class="col-md-4"><label class="form-label">পণ্যের নাম</label><input class="form-control" name="name" placeholder="Product name" required></div><div class="col-md-2"><label class="form-label">SKU</label><input class="form-control" name="sku" placeholder="SKU" required></div><div class="col-md-2"><label class="form-label">ব্র্যান্ড</label><input class="form-control" name="brand" placeholder="Brand"></div><div class="col-md-4"><label class="form-label">ক্যাটাগরি</label><select class="form-select" name="cat" required>{% for c in cats %}<option value="{{ c.id }}">{{ c.name }}</option>{% endfor %}</select></div>
        <div class="col-md-3"><label class="form-label">ক্রয়মূল্য ৳</label><input class="form-control" type="number" min="0" step=".01" name="purchase_price" required></div><div class="col-md-3"><label class="form-label">বিক্রয়মূল্য ৳</label><input class="form-control" type="number" min="0" step=".01" name="price" required></div><div class="col-md-2"><label class="form-label">আগের দাম ৳</label><input class="form-control" type="number" min="0" step=".01" name="old_price"></div><div class="col-md-2"><label class="form-label">ছাড় %</label><input class="form-control" type="number" min="0" max="100" name="discount" value="0"></div><div class="col-md-2"><label class="form-label">স্টক</label><input class="form-control" type="number" min="0" name="stock" value="0" required></div>
        <div class="col-md-4"><label class="form-label">প্রধান ছবি</label><input class="form-control" type="file" name="image_file" accept="image/*" onchange="previewProduct(this,'pPrev1')"><input class="form-control mt-2" name="image" placeholder="অথবা ছবির URL"></div><div class="col-md-4"><label class="form-label">দ্বিতীয় ছবি</label><input class="form-control" type="file" name="image2_file" accept="image/*" onchange="previewProduct(this,'pPrev2')"><input class="form-control mt-2" name="image2" placeholder="অথবা URL"></div><div class="col-md-4"><label class="form-label">তৃতীয় ছবি</label><input class="form-control" type="file" name="image3_file" accept="image/*" onchange="previewProduct(this,'pPrev3')"><input class="form-control mt-2" name="image3" placeholder="অথবা URL"></div>
        <div class="col-md-4"><img id="pPrev1" class="prod-preview" alt="প্রধান ছবির প্রিভিউ"></div><div class="col-md-4"><img id="pPrev2" class="prod-preview" alt="দ্বিতীয় ছবির প্রিভিউ"></div><div class="col-md-4"><img id="pPrev3" class="prod-preview" alt="তৃতীয় ছবির প্রিভিউ"></div>
        <div class="col-md-3"><label class="form-label">পণ্যের পরিমাপ</label><select class="form-select" name="unit_type"><option value="">প্রযোজ্য নয়</option><option value="ml">মিলিলিটার (ml)</option><option value="L">লিটার (L)</option><option value="g">গ্রাম (g)</option><option value="kg">কেজি (kg)</option><option value="pcs">পিস</option><option value="pack">প্যাক</option><option value="pair">জোড়া</option><option value="meter">মিটার</option></select></div><div class="col-md-3"><label class="form-label">পরিমাণ / সাইজ</label><input class="form-control" name="unit_value" placeholder="যেমন 180, 500, 1"></div><div class="col-md-3"><label class="form-label">পোশাকের সাইজ</label><input class="form-control" name="sizes" placeholder="S, M, L, XL, XXL"></div><div class="col-md-3"><label class="form-label">কালার</label><input class="form-control" name="colors" placeholder="Black, White, Blue"></div><div class="col-md-4"><label class="form-label">উৎপত্তির দেশ</label><input class="form-control" name="country" placeholder="Bangladesh"></div>
        <div class="col-12"><label class="form-label">সম্পূর্ণ বিবরণ</label><textarea class="form-control" name="desc" rows="4" placeholder="উপাদান, মাপ, ফিচার, ব্যবহারবিধি, ওয়ারেন্টি..." required></textarea></div><div class="col-12"><button class="btn btn-primary px-4">পণ্য সেভ করুন</button></div></form>
        <div class="d-flex justify-content-between align-items-center flex-wrap gap-2"><h5 class="fw-bold">পণ্যের তালিকা ({{ rows|length }})</h5><input id="productSearch" class="form-control" style="max-width:250px" placeholder="নাম / SKU / ব্র্যান্ড খুঁজুন" oninput="filterProducts()"><select id="productCategoryFilter" class="form-select" style="max-width:220px" onchange="filterProducts()"><option value="">সব ক্যাটাগরি</option>{% for c in cats %}<option value="{{ c.id }}">{{ c.name }}</option>{% endfor %}</select><button class="btn btn-outline-danger btn-sm" type="submit" form="bulkProducts" onclick="return confirm('নির্বাচিত পণ্য মুছবেন? বিক্রির ইতিহাস থাকা পণ্য মুছবে না।')">নির্বাচিত পণ্য ডিলিট</button></div><form id="bulkProducts" method="post" action="/admin/products/bulk-delete"><input type="hidden" name="return_to" value="/admin/section/products"><div class="table-responsive"><table class="table align-middle"><tr><th><input type="checkbox" onclick="document.querySelectorAll('.productPick').forEach(x=>x.checked=this.checked)"></th><th>ছবি / পণ্য</th><th>ক্যাটাগরি</th><th>SKU</th><th>ক্রয় ৳</th><th>বিক্রয় ৳</th><th>স্টক</th><th>বিক্রি</th><th></th></tr>{% for p in rows %}<tr data-cat="{{ p.category_id }}"><td><input class="productPick" type="checkbox" name="ids" value="{{ p.id }}"></td><td><div class="d-flex align-items-center gap-2"><img src="{{ p.image }}" style="width:48px;height:48px;object-fit:contain;border-radius:8px"><b>{{ p.name }}</b></div></td><td>{{ p.category_name }}</td><td>{{ p.sku }}</td><td>৳{{ p.purchase_price or 0 }}</td><td>৳{{ p.price }}</td><td>{{ p.stock }}</td><td>{{ sold.get(p.id,0) }}</td><td><a class="btn btn-sm btn-outline-primary" href="/admin/product/edit/{{ p.id }}">Edit</a></td></tr>{% endfor %}</table></div></form>
        <script>function previewProduct(i,id){if(i.files&&i.files[0])document.getElementById(id).src=URL.createObjectURL(i.files[0])}function filterProducts(){let q=(document.getElementById("productSearch")?.value||"").toLowerCase(),c=document.getElementById("productCategoryFilter")?.value||"";document.querySelectorAll("#bulkProducts tbody tr[data-cat]").forEach(r=>{r.style.display=(!q||r.innerText.toLowerCase().includes(q))&&(!c||r.dataset.cat===c)?"":"none"})}</script>'''
        soldrows=db.execute("SELECT oi.product_id,SUM(oi.quantity) sold FROM order_items oi JOIN orders o ON o.id=oi.order_id WHERE COALESCE(o.order_status,'') NOT IN ('Cancelled','Returned','Refunded') GROUP BY oi.product_id").fetchall(); sold={x['product_id']:x['sold'] for x in soldrows}
        return render_template_string(_ADMIN_SECTION_HTML, title=title, body=render_template_string(body,rows=rows,cats=cats,sold=sold,category_stats=category_stats,total_units=total_units,inventory_cost=inventory_cost))
    elif section=='orders':
        rows=db.execute("SELECT o.*,c.name customer_name,c.email customer_email,c.phone customer_phone,(SELECT GROUP_CONCAT(oi.product_name || ' x ' || oi.quantity, '; ') FROM order_items oi WHERE oi.order_id=o.id) item_summary FROM orders o LEFT JOIN customers c ON c.id=o.customer_id ORDER BY o.id DESC").fetchall()
        body='''<div class="table-responsive"><table class="table align-middle"><tr><th>Order / Customer</th><th>পণ্যের বিস্তারিত</th><th>যোগাযোগ</th><th>ডেলিভারি ঠিকানা</th><th>Amount</th><th>Status</th><th>Update</th><th>Delete</th></tr>{% for o in rows %}<tr><td><b>{{ o.order_id }}</b><br>{{ o.recipient_name or o.customer_name or 'Customer' }}<br><small>Customer #{{ o.customer_id }}</small></td><td>{{ o.item_summary or 'পণ্যের তথ্য নেই' }}</td><td>{{ o.sender_phone or o.customer_phone or 'নম্বর নেই' }}<br><small>{{ o.customer_email or '' }}</small></td><td>{{ o.division or '' }}, {{ o.district or '' }}, {{ o.upazila or '' }}<br>{{ o.shipping_address or '' }}</td><td>৳{{ '%.2f'|format(o.total_amount) }}<br><small>ডিসকাউন্ট ৳{{ o.discount_amount or 0 }}</small></td><td>{{ o.order_status }}</td><td><form method="post" action="/admin/order/status/{{ o.id }}" class="d-flex flex-column gap-2"><select class="form-select" name="status">{% for st in ['Pending','Confirmed','Shipped','Delivered','Cancelled','Returned','Refunded'] %}<option {% if o.order_status==st %}selected{% endif %}>{{ st }}</option>{% endfor %}</select><button class="btn btn-primary">Save</button></form></td><td>{% if (o.order_status or '')|lower=='cancelled' %}<form method="post" action="/admin/order/delete-cancelled/{{ o.id }}" onsubmit="return confirm('এই Cancelled অর্ডারটি স্থায়ীভাবে ডিলিট করবেন?')"><button class="btn btn-sm btn-outline-danger">Delete</button></form>{% else %}—{% endif %}</td></tr>{% endfor %}</table></div>'''
    elif section=='stock':
        rows=db.execute("SELECT p.id,p.name,p.sku,p.stock,p.price,p.purchase_price,p.unit_type,p.unit_value,c.name category,COALESCE((SELECT SUM(oi.quantity) FROM order_items oi JOIN orders o ON o.id=oi.order_id WHERE oi.product_id=p.id AND COALESCE(o.order_status,'') NOT IN ('Cancelled','Returned','Refunded')),0) sold FROM products p JOIN categories c ON c.id=p.category_id WHERE COALESCE(p.is_active,1)=1 ORDER BY p.stock ASC,p.id DESC").fetchall()
        cat_summary=db.execute("SELECT c.name,COUNT(p.id) products,COALESCE(SUM(p.stock),0) units FROM categories c LEFT JOIN products p ON p.category_id=c.id GROUP BY c.id ORDER BY c.name").fetchall()
        body='''<div class="row g-3 mb-3"><div class="col-md-4"><div class="alert alert-primary mb-0"><b>{{ rows|length }}</b>টি পণ্য (ক্যাটাগরি নয়)</div></div><div class="col-md-4"><div class="alert alert-success mb-0"><b>{{ rows|sum(attribute='stock') }}</b> ইউনিট রেকর্ডকৃত বর্তমান স্টক</div></div><div class="col-md-4"><div class="alert alert-warning mb-0">কম স্টক: <b>{{ rows|selectattr('stock','le',5)|list|length }}</b>টি পণ্য</div></div></div><h5>ক্যাটাগরি অনুযায়ী স্টক</h5><div class="table-responsive mb-4"><table class="table table-sm"><tr><th>ক্যাটাগরি</th><th>পণ্য</th><th>স্টক ইউনিট</th></tr>{% for c in cat_summary %}<tr><td>{{ c.name }}</td><td>{{ c.products }}</td><td>{{ c.units }}</td></tr>{% endfor %}</table></div><div class="d-flex justify-content-between align-items-center mb-2"><h5>পণ্যভিত্তিক স্টক</h5><button class="btn btn-outline-danger btn-sm" type="submit" form="bulkStock" onclick="return confirm('নির্বাচিত পণ্য ডিলিট করবেন? বিক্রির ইতিহাস থাকা পণ্য মুছবে না।')">নির্বাচিত ডিলিট</button></div><form id="bulkStock" method="post" action="/admin/products/bulk-delete"><input type="hidden" name="return_to" value="/admin/section/stock"><div class="table-responsive"><table class="table align-middle"><tr><th><input type="checkbox" onclick="document.querySelectorAll('.stockPick').forEach(x=>x.checked=this.checked)"></th><th>Product</th><th>Category</th><th>SKU</th><th>Available</th><th>Sold</th><th>Purchase ৳</th><th>Selling ৳</th><th>Edit</th></tr>{% for p in rows %}<tr><td><input class="stockPick" type="checkbox" name="ids" value="{{ p.id }}"></td><td>{{ p.name }}</td><td>{{ p.category or '-' }}</td><td>{{ p.sku }}</td><td><b class="{{ 'text-danger' if p.stock<=5 else 'text-success' }}">{{ p.stock }} {{ p.unit_type or 'pcs' }}</b></td><td>{{ p.sold }}</td><td>{{ p.purchase_price or 0 }}</td><td>{{ p.price }}</td><td><a href="/admin/product/edit/{{ p.id }}" class="btn btn-sm btn-outline-primary">Update</a></td></tr>{% endfor %}</table></div></form>'''
    elif section=='leaderboard':
        rows=db.execute("SELECT c.id,c.name,c.email,c.phone,COUNT(o.id) orders,COALESCE(SUM(o.total_amount),0) spent,COALESCE(AVG(o.total_amount),0) average_order FROM customers c JOIN orders o ON o.customer_id=c.id WHERE COALESCE(o.order_status,'') NOT IN ('Cancelled','Returned','Refunded') GROUP BY c.id ORDER BY spent DESC,c.id ASC").fetchall()
        body='''<table class="table"><tr><th>Rank</th><th>Customer</th><th>Contact / ID</th><th>Orders</th><th>Total Purchase</th><th>Average Order</th></tr>{% for r in rows %}<tr><td>{{ loop.index }}</td><td>{{ r.name }}</td><td>{{ r.email }}<br>{{ r.phone or 'ফোন নেই' }} · #{{ r.id }}</td><td>{{ r.orders }}</td><td>৳{{ '%.0f'|format(r.spent) }}</td><td>৳{{ '%.0f'|format(r.average_order) }}</td></tr>{% endfor %}</table>'''
    elif section in ('reports','discounts','categories','settings'):
        if section=='reports':
            rows=db.execute("SELECT substr(created_at,1,7) month,COUNT(*) orders,COALESCE(SUM(total_amount),0) sales FROM orders WHERE COALESCE(order_status,'') NOT IN ('Cancelled','Returned','Refunded') GROUP BY substr(created_at,1,7) ORDER BY month DESC LIMIT 24").fetchall()
            weekly=db.execute("SELECT strftime('%Y-W%W',created_at) week,COUNT(*) orders,COALESCE(SUM(total_amount),0) sales FROM orders WHERE date(created_at)>=date('now','localtime','-84 days') AND COALESCE(order_status,'') NOT IN ('Cancelled','Returned','Refunded') GROUP BY strftime('%Y-W%W',created_at) ORDER BY week DESC LIMIT 12").fetchall()
            by_district=db.execute("SELECT COALESCE(NULLIF(TRIM(district),''),'ঠিকানা নেই') place,COUNT(*) orders,COALESCE(SUM(total_amount),0) sales FROM orders WHERE COALESCE(order_status,'') NOT IN ('Cancelled','Returned','Refunded') GROUP BY district ORDER BY sales DESC").fetchall()
            by_division=db.execute("SELECT COALESCE(NULLIF(TRIM(division),''),'ঠিকানা নেই') place,COUNT(*) orders,COALESCE(SUM(total_amount),0) sales FROM orders WHERE COALESCE(order_status,'') NOT IN ('Cancelled','Returned','Refunded') GROUP BY division ORDER BY sales DESC").fetchall()
            body='''<h5 class="fw-bold">মাসভিত্তিক ব্যবসা</h5><div class="table-responsive"><table class="table"><tr><th>Month</th><th>Orders</th><th>Sales ৳</th></tr>{% for r in rows %}<tr><td>{{ r.month }}</td><td>{{ r.orders }}</td><td>৳{{ '%.0f'|format(r.sales) }}</td></tr>{% endfor %}</table></div><h5 class="fw-bold mt-4">সাপ্তাহিক ব্যবসা</h5><div class="table-responsive"><table class="table"><tr><th>Week</th><th>Orders</th><th>Sales ৳</th></tr>{% for r in weekly %}<tr><td>{{ r.week }}</td><td>{{ r.orders }}</td><td>৳{{ '%.0f'|format(r.sales) }}</td></tr>{% endfor %}</table></div><div class="row g-3 mt-2"><div class="col-md-6"><h5 class="fw-bold">জেলা অনুযায়ী ব্যবসা</h5><table class="table"><tr><th>জেলা</th><th>অর্ডার</th><th>বিক্রি</th></tr>{% for r in by_district %}<tr><td>{{ r.place }}</td><td>{{ r.orders }}</td><td>৳{{ '%.0f'|format(r.sales) }}</td></tr>{% endfor %}</table></div><div class="col-md-6"><h5 class="fw-bold">বিভাগ অনুযায়ী ব্যবসা</h5><table class="table"><tr><th>বিভাগ</th><th>অর্ডার</th><th>বিক্রি</th></tr>{% for r in by_division %}<tr><td>{{ r.place }}</td><td>{{ r.orders }}</td><td>৳{{ '%.0f'|format(r.sales) }}</td></tr>{% endfor %}</table></div></div><p class="small text-secondary">Cancelled, Returned ও Refunded অর্ডার বিক্রির হিসাবে ধরা হয়নি। লাভের সঠিক হিসাবের জন্য পণ্যের ক্রয়মূল্য দিতে হবে।</p>'''
        elif section=='categories':
            rows=db.execute('SELECT * FROM categories ORDER BY name COLLATE NOCASE').fetchall()
            product_counts={r['category_id']:r['n'] for r in db.execute('SELECT category_id,COUNT(*) n FROM products WHERE COALESCE(is_active,1)=1 GROUP BY category_id').fetchall()}
            body='''<div class="alert alert-info">নতুন ক্যাটাগরি তৈরি করুন। কোনো ক্যাটাগরি মুছতে চাইলে, তাতে পণ্য থাকলে আগে অন্য ক্যাটাগরিতে সরিয়ে দিন—পণ্য বা অর্ডারের ইতিহাস মুছে যাবে না।</div><form method="post" action="/admin/category/add" class="row g-2 mb-4"><div class="col-md-4"><input class="form-control" name="name" placeholder="ক্যাটাগরির নাম" required></div><div class="col-md-5"><input class="form-control" name="image" placeholder="ক্যাটাগরি ছবির URL (ঐচ্ছিক)"></div><div class="col-md-3"><button class="btn btn-primary w-100">+ ক্যাটাগরি তৈরি করুন</button></div></form><h5 class="fw-bold mb-3">ক্যাটাগরি পরিচালনা ও ডিলিট</h5><div class="row g-3">{% for r in rows %}<div class="col-12 col-md-6 col-xl-4"><div class="border rounded-3 p-3 h-100">{% if r.image %}<img src="{{ r.image }}" alt="{{ r.name }}" style="width:100%;height:110px;object-fit:cover;border-radius:10px">{% endif %}<b class="d-block mt-2">{{ r.name }}</b><small class="text-secondary d-block mb-3">{{ product_counts.get(r.id,0) }}টি পণ্য</small><form method="post" action="/admin/category/delete/{{ r.id }}" onsubmit="return confirm('এই ক্যাটাগরি ডিলিট করবেন? পণ্য থাকলে সেগুলো নির্বাচিত ক্যাটাগরিতে সরানো হবে।')"><label class="form-label small fw-semibold">পণ্য সরানোর ক্যাটাগরি (পণ্য থাকলে বাধ্যতামূলক)</label><select class="form-select form-select-sm mb-2" name="target_category_id"><option value="">-- নির্বাচন করুন --</option>{% for dest in rows if dest.id != r.id %}<option value="{{ dest.id }}">{{ dest.name }}</option>{% endfor %}</select><button class="btn btn-outline-danger btn-sm w-100" type="submit">ক্যাটাগরি ডিলিট</button></form></div></div>{% else %}<div class="col-12 text-center py-4 text-secondary">এখনো কোনো ক্যাটাগরি তৈরি করা হয়নি। উপরের ফর্ম থেকে প্রথম ক্যাটাগরি তৈরি করুন।</div>{% endfor %}</div>'''
        elif section=='discounts':
            rows=db.execute('SELECT id,name,price,old_price,discount_percent FROM products WHERE COALESCE(is_active,1)=1 AND (COALESCE(discount_percent,0)>0 OR COALESCE(old_price,0)>price) ORDER BY discount_percent DESC').fetchall()
            body='''<div class="alert alert-info">পণ্যের ছাড় দিতে Edit খুলে ছাড় (%) ও আগের দাম সেট করুন। কুপন আলাদা ভাবে Coupon Management-এ নিয়ন্ত্রণ করুন।</div><a class="btn btn-primary mb-3" href="/admin/section/products">পণ্য ও ছাড় পরিচালনা</a><div class="table-responsive"><table class="table"><tr><th>পণ্য</th><th>আগের দাম</th><th>বিক্রয় দাম</th><th>ছাড়</th><th></th></tr>{% for r in rows %}<tr><td>{{ r.name }}</td><td>৳{{ r.old_price or r.price }}</td><td>৳{{ r.price }}</td><td>{{ r.discount_percent or 0 }}%</td><td><a class="btn btn-sm btn-outline-primary" href="/admin/product/edit/{{ r.id }}">Edit</a></td></tr>{% else %}<tr><td colspan="5">এখনো কোনো পণ্যে ছাড় নেই।</td></tr>{% endfor %}</table></div>'''
        else: body='<div class="alert alert-info">Owner Profile, যোগাযোগের তথ্য ও নিরাপত্তা সেটিংস Dashboard-এর Settings/Profile অংশে পরিচালনা করুন।</div><a class="btn btn-primary" href="/admin/dashboard">Dashboard Settings</a>'
    return render_template_string(_ADMIN_SECTION_HTML, title=title, body=render_template_string(body,rows=locals().get('rows',[]),product_counts=locals().get('product_counts',{}),sold=locals().get('sold',{}),cat_summary=locals().get('cat_summary',[]),weekly=locals().get('weekly',[]),by_district=locals().get('by_district',[]),by_division=locals().get('by_division',[])))

_ADMIN_SECTION_HTML = r'''<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{{ title }} | Fayez Admin</title><link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/css/bootstrap.min.css" rel="stylesheet"><style>body{background:#f6f9fd;color:#17243b}.wrap{max-width:1250px;margin:35px auto;padding:0 18px}.card{border:1px solid #edf1f7;border-radius:16px;box-shadow:0 5px 18px #29466d08}.form-control,.form-select{min-height:42px;border-radius:10px}</style></head><body><main class="wrap"><div class="d-flex justify-content-between align-items-center mb-4"><div><small class="text-primary fw-bold">FAYEZ ONLINE SHOP · ADMIN</small><h2 class="fw-bold">{{ title }}</h2></div><a href="/admin/dashboard" class="btn btn-primary">← Dashboard</a></div><section class="card p-4">{{ body|safe }}</section></main></body></html>'''


@app.route('/admin/order/delete-cancelled/<int:oid>', methods=['POST'])
@admin_required
def admin_delete_cancelled_order(oid):
    db = get_db()
    order = db.execute('SELECT id, order_id, order_status FROM orders WHERE id=?', (oid,)).fetchone()
    if not order:
        flash('অর্ডারটি পাওয়া যায়নি।', 'warning')
        return redirect(request.referrer or url_for('admin_dashboard'))
    if (order['order_status'] or '').strip().lower() != 'cancelled':
        flash('শুধু Cancelled অর্ডার ডিলিট করা যাবে।', 'danger')
        return redirect(request.referrer or url_for('admin_dashboard'))
    try:
        db.execute('BEGIN')
        db.execute('DELETE FROM order_items WHERE order_id=?', (oid,))
        db.execute("DELETE FROM orders WHERE id=? AND lower(COALESCE(order_status,''))='cancelled'", (oid,))
        db.commit()
        flash(f"Cancelled অর্ডার {order['order_id']} ডিলিট হয়েছে।", 'success')
    except Exception as exc:
        db.rollback()
        flash('অর্ডার ডিলিট করা যায়নি: ' + str(exc), 'danger')
    return redirect(request.referrer or url_for('admin_dashboard'))

@app.route('/admin/order/confirm/<int:oid>', methods=['POST'])
@admin_required
def admin_confirm_order(oid):
    db = get_db()
    db.execute("UPDATE orders SET order_status = 'Confirmed' WHERE id = ?", (oid,))
    db.commit()
    flash('অর্ডার সফলভাবে কনফার্ম করা হয়েছে!', 'success')
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/order/status/<int:oid>', methods=['POST'])
@admin_required
def admin_update_order_status(oid):
    db = get_db()
    status = (request.form.get('status') or '').strip()
    allowed = {'Pending', 'Confirmed', 'Shipped', 'Delivered', 'Cancelled', 'Returned', 'Refunded'}
    if status not in allowed:
        flash('অর্ডারের স্ট্যাটাস সঠিক নয়।', 'danger')
        return redirect(url_for('admin_dashboard'))
    order = db.execute('SELECT id, order_status FROM orders WHERE id=?', (oid,)).fetchone()
    if not order:
        flash('অর্ডারটি পাওয়া যায়নি।', 'warning')
        return redirect(url_for('admin_dashboard'))
    courier = (request.form.get('courier_name') or '').strip()[:120]
    tracking = (request.form.get('tracking_number') or '').strip()[:120]
    shipped_at_sql = ", shipped_at=CASE WHEN ?='Shipped' AND (shipped_at IS NULL OR shipped_at='') THEN CURRENT_TIMESTAMP ELSE shipped_at END"
    db.execute("UPDATE orders SET order_status=?, courier_name=?, tracking_number=?" + shipped_at_sql + " WHERE id=?",
               (status, courier or None, tracking or None, status, oid))
    db.commit()
    if order['order_status'] != status:
        order_customer = db.execute('SELECT customer_id, order_id FROM orders WHERE id=?', (oid,)).fetchone()
        if order_customer and order_customer['customer_id']:
            db.execute("INSERT INTO customer_activity(customer_id,event_type,product_id,detail,created_at) VALUES(?,?,?,?,CURRENT_TIMESTAMP)", (order_customer['customer_id'], 'order_status_changed', None, f"{order_customer['order_id']}: {order['order_status']} → {status}"))
            db.commit()
    flash('অর্ডারের স্ট্যাটাস ও শিপমেন্ট তথ্য আপডেট হয়েছে।', 'success')
    return redirect(url_for('admin_dashboard'))


@app.route('/admin/category/delete/<int:category_id>', methods=['POST'])
@admin_required
def admin_delete_category(category_id):
    db = get_db()
    category = db.execute('SELECT id, name FROM categories WHERE id=?', (category_id,)).fetchone()
    if not category:
        flash('ক্যাটাগরিটি পাওয়া যায়নি।', 'warning')
        return redirect('/admin/section/categories')
    count_row = db.execute('SELECT COUNT(*) AS n FROM products WHERE category_id=?', (category_id,)).fetchone()
    product_count = int(count_row['n'] or 0)
    target_raw = (request.form.get('target_category_id') or '').strip()
    target_id = None
    if product_count:
        try:
            target_id = int(target_raw)
        except (TypeError, ValueError):
            flash(f'এই ক্যাটাগরিতে {product_count}টি পণ্য আছে। ডিলিটের আগে অন্য ক্যাটাগরি নির্বাচন করুন।', 'danger')
            return redirect('/admin/section/categories')
        target = db.execute('SELECT id FROM categories WHERE id=? AND id<>?', (target_id, category_id)).fetchone()
        if not target:
            flash('পণ্য সরানোর জন্য বৈধ অন্য ক্যাটাগরি নির্বাচন করুন।', 'danger')
            return redirect('/admin/section/categories')
    try:
        db.execute('BEGIN')
        if product_count:
            db.execute('UPDATE products SET category_id=? WHERE category_id=?', (target_id, category_id))
        db.execute('DELETE FROM categories WHERE id=?', (category_id,))
        db.commit()
        if product_count:
            flash(f"'{category['name']}' ক্যাটাগরি ডিলিট হয়েছে। {product_count}টি পণ্য নির্বাচিত ক্যাটাগরিতে সরানো হয়েছে।", 'success')
        else:
            flash(f"'{category['name']}' ক্যাটাগরি ডিলিট হয়েছে।", 'success')
    except Exception as exc:
        db.rollback()
        flash('ক্যাটাগরি ডিলিট করা যায়নি। ডেটা অপরিবর্তিত রাখা হয়েছে।', 'danger')
    return redirect('/admin/section/categories')

@app.route('/admin/banner/add', methods=['POST'])
@admin_required
def admin_add_banner():
    db = get_db()
    image_url = _resolve_product_image('banner_file', 'image_url', required=True)
    db.execute('INSERT INTO banners (title, subtitle, image_url, link_url) VALUES (?, ?, ?, ?)',
               (request.form['title'].strip(), request.form['subtitle'].strip(), image_url, request.form['link_url'].strip()))
    db.commit()
    flash('ব্যানার সফলভাবে যোগ হয়েছে!', 'success')
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/banner/del/<int:bid>', methods=['POST'])
@admin_required
def admin_del_banner(bid):
    db = get_db()
    db.execute('DELETE FROM banners WHERE id = ?', (bid,))
    db.commit()
    flash('ব্যানার ডিলিট করা হয়েছে।', 'info')
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/coupon/add', methods=['POST'])
@admin_required
def admin_add_coupon():
    db = get_db()
    try:
        kind = request.form.get('discount_type', 'percent')
        value = float(request.form['discount'])
        if value <= 0 or (kind == 'percent' and value > 100):
            raise ValueError('ছাড়ের পরিমাণ সঠিকভাবে দিন।')
        expires = request.form.get('expires_at') or None
        max_uses = int(request.form['max_uses']) if request.form.get('max_uses') else None
        if max_uses is not None and max_uses < 1:
            raise ValueError('ব্যবহারসীমা কমপক্ষে ১ হতে হবে।')
        db.execute('INSERT INTO coupons (code, discount_percent, discount_type, discount_amount, expires_at, max_uses, used_count, is_active) VALUES (?, ?, ?, ?, ?, ?, 0, 1)',
                   (request.form['code'].strip().upper(), value if kind == 'percent' else 0, kind, value if kind == 'fixed' else 0, expires, max_uses))
        db.commit()
        flash('নতুন কুপন সফলভাবে যোগ হয়েছে!', 'success')
    except Exception as exc:
        db.rollback()
        flash(str(exc) if str(exc) else 'এই কুপন কোডটি ইতোমধ্যে রয়েছে!', 'danger')
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/coupon/toggle/<int:cid>', methods=['POST'])
@admin_required
def admin_toggle_coupon(cid):
    db=get_db(); row=db.execute('SELECT is_active FROM coupons WHERE id=?',(cid,)).fetchone()
    if row:
        db.execute('UPDATE coupons SET is_active=? WHERE id=?',(0 if row['is_active'] else 1,cid)); db.commit()
        flash('কুপনের অবস্থা পরিবর্তন হয়েছে।','success')
    return redirect('/admin/section/coupons')

@app.route('/admin/coupon/delete/<int:cid>', methods=['POST'])
@admin_required
def admin_delete_coupon(cid):
    db=get_db(); db.execute('DELETE FROM coupons WHERE id=?',(cid,)); db.commit()
    flash('কুপন ডিলিট হয়েছে।','info')
    return redirect('/admin/section/coupons')

@app.route('/admin/product/add', methods=['POST'])
@admin_required
def admin_add_product():
    db = get_db()
    try:
        image = _resolve_product_image('image_file', 'image', required=False)
        image2 = _resolve_product_image('image2_file', 'image2')
        image3 = _resolve_product_image('image3_file', 'image3')
        supplied_images = [x for x in (image, image2, image3) if x]
        if len(set(supplied_images)) != len(supplied_images):
            raise ValueError('একই পণ্যে একই ছবি একাধিকবার দেওয়া যাবে না।')
        existing = db.execute('SELECT image,image2,image3 FROM products').fetchall()
        used = {str(row[k]).strip() for row in existing for k in ('image','image2','image3') if row[k]}
        if any(x in used for x in supplied_images):
            raise ValueError('এই ছবিটি আগে অন্য পণ্যে ব্যবহার করা হয়েছে। আলাদা ছবি দিন।')
        selected_category_id = int(request.form['cat'])
        category_allowed = db.execute('SELECT id FROM categories WHERE id=?', (selected_category_id,)).fetchone()
        if not category_allowed:
            raise ValueError('শুধু ওয়েবসাইটে প্রদর্শিত ক্যাটাগরি নির্বাচন করুন।')
        db.execute("INSERT INTO products (name, sku, brand, category_id, price, old_price, discount_percent, stock, description, image, image2, image3, purchase_price, colors, country_of_origin, sizes, unit_type, unit_value) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                   (request.form['name'].strip(), request.form['sku'].strip(), request.form.get('brand','').strip(), selected_category_id, float(request.form['price']),
                    float(request.form.get('old_price') or 0), int(request.form.get('discount') or 0), int(request.form['stock']), request.form.get('desc','').strip(), image, image2, image3, float(request.form.get('purchase_price') or 0), request.form.get('colors','').strip(), request.form.get('country','Bangladesh').strip(), request.form.get('sizes','').strip(), request.form.get('unit_type','').strip(), request.form.get('unit_value','').strip()))
        db.commit()
        flash('পণ্য ও ছবি সফলভাবে যোগ হয়েছে!', 'success')
    except Exception as exc:
        db.rollback()
        flash(str(exc) if str(exc) else 'পণ্য যোগ করা যায়নি। SKU ও তথ্য যাচাই করুন।', 'danger')
    return redirect('/admin/section/products')

@app.route('/admin/product/delete/<int:pid>', methods=['POST'])
@admin_required
def admin_delete_product(pid):
    db=get_db()
    used=db.execute('SELECT COUNT(*) FROM order_items WHERE product_id=?',(pid,)).fetchone()[0]
    if used:
        flash('এই পণ্যের অর্ডার ইতিহাস আছে—হিসাব অক্ষত রাখতে সরাসরি ডিলিট করা হয়নি। স্টক ০ করে নিষ্ক্রিয় রাখুন।','warning')
    else:
        db.execute('DELETE FROM reviews WHERE product_id=?',(pid,)); db.execute('DELETE FROM cart WHERE product_id=?',(pid,)); db.execute('DELETE FROM products WHERE id=?',(pid,)); db.commit()
        flash('পণ্য ডিলিট হয়েছে।','success')
    return redirect(request.referrer or '/admin/section/products')

@app.route('/admin/products/bulk-delete', methods=['POST'])
@admin_required
def admin_bulk_delete_products():
    db=get_db(); ids=[]
    for raw in request.form.getlist('ids'):
        try: ids.append(int(raw))
        except (TypeError,ValueError): pass
    deleted=0; protected=0
    for pid in sorted(set(ids)):
        used=db.execute('SELECT COUNT(*) FROM order_items WHERE product_id=?',(pid,)).fetchone()[0]
        if used: protected+=1; continue
        db.execute('DELETE FROM reviews WHERE product_id=?',(pid,)); db.execute('DELETE FROM cart WHERE product_id=?',(pid,)); db.execute('DELETE FROM products WHERE id=?',(pid,)); deleted+=1
    db.commit()
    flash(f'{deleted}টি পণ্য স্থায়ীভাবে ডিলিট হয়েছে। {protected}টি পণ্য ডিলিট হয়নি—এসব পণ্যের অর্ডার ইতিহাস আছে, তাই হিসাব নষ্ট না করতে রাখা হয়েছে।','warning' if protected else 'success')
    return redirect(request.form.get('return_to') if request.form.get('return_to') in ('/admin/section/products','/admin/section/stock') else '/admin/section/products')

@app.route('/admin/product/edit/<int:pid>', methods=['GET', 'POST'])
@admin_required
def admin_edit_product(pid):
    db = get_db()
    product = db.execute('SELECT * FROM products WHERE id=?', (pid,)).fetchone()
    if not product:
        flash('পণ্যটি পাওয়া যায়নি।', 'warning')
        return redirect(url_for('admin_dashboard'))
    categories = db.execute('SELECT * FROM categories ORDER BY name COLLATE NOCASE').fetchall()
    if request.method == 'POST':
        try:
            images = [_resolve_product_image('image_file', 'image', product['image'], required=True), _resolve_product_image('image2_file', 'image2', product['image2']), _resolve_product_image('image3_file', 'image3', product['image3'])]
            supplied = [x for x in images if x]
            if not images[0]:
                raise ValueError('প্রধান ছবির URL আবশ্যক।')
            if any(not x.startswith(('https://', 'http://')) for x in supplied):
                raise ValueError('ছবির URL অবশ্যই http:// অথবা https:// দিয়ে শুরু হতে হবে।')
            if len(set(supplied)) != len(supplied):
                raise ValueError('একই পণ্যে একই ছবির URL একাধিকবার দেওয়া যাবে না।')
            rows = db.execute('SELECT id,image,image2,image3 FROM products WHERE id<>?', (pid,)).fetchall()
            used = {str(row[k]).strip() for row in rows for k in ('image','image2','image3') if row[k]}
            if any(x in used for x in supplied):
                raise ValueError('এই ছবি অন্য পণ্যে ব্যবহার করা হয়েছে। আলাদা ছবি দিন।')
            db.execute("UPDATE products SET name=?, sku=?, brand=?, category_id=?, price=?, old_price=?, discount_percent=?, stock=?, description=?, image=?, image2=?, image3=?, purchase_price=?, sizes=?, colors=?, unit_type=?, unit_value=? WHERE id=?",
                (request.form['name'].strip(), request.form['sku'].strip(), request.form.get('brand','').strip(), int(request.form['cat']),
                 float(request.form['price']), float(request.form.get('old_price') or 0),
                 int(request.form.get('discount') or 0), int(request.form['stock']),
                 request.form.get('desc','').strip(), images[0], images[1], images[2], float(request.form.get('purchase_price') or product['purchase_price'] or 0), request.form.get('sizes','').strip(), request.form.get('colors','').strip(), request.form.get('unit_type','').strip(), request.form.get('unit_value','').strip(), pid))
            db.commit()
            flash('পণ্যের তথ্য ও ছবিগুলো আপডেট হয়েছে।', 'success')
            return redirect(url_for('admin_dashboard'))
        except Exception as exc:
            flash(str(exc) or 'পণ্য আপডেট করা যায়নি।', 'danger')
    body = '''<div class="container my-5" style="max-width:900px"><div class="card admin-section p-4 border-0 shadow-sm rounded-4"><h3 class="fw-bold mb-4">পণ্য সম্পাদনা</h3>
    <form method="post" enctype="multipart/form-data" class="row g-3">
      <div class="col-md-6"><label class="form-label">পণ্যের নাম</label><input class="form-control" name="name" value="{{ p.name }}" required></div>
      <div class="col-md-6"><label class="form-label">SKU</label><input class="form-control" name="sku" value="{{ p.sku }}" required></div>
      <div class="col-md-6"><label class="form-label">ব্র্যান্ড</label><input class="form-control" name="brand" value="{{ p.brand or '' }}" placeholder="ব্র্যান্ডের নাম"></div>
      <div class="col-md-6"><label class="form-label">ক্যাটাগরি</label><select class="form-select" name="cat">{% for c in categories %}<option value="{{ c.id }}" {% if c.id==p.category_id %}selected{% endif %}>{{ c.name }}</option>{% endfor %}</select></div>
      <div class="col-md-3"><label class="form-label">ক্রয়মূল্য</label><input class="form-control" type="number" step=".01" min="0" name="purchase_price" value="{{ p.purchase_price or 0 }}"></div><div class="col-md-3"><label class="form-label">বিক্রয়মূল্য</label><input class="form-control" type="number" step=".01" min="0" name="price" value="{{ p.price }}" required></div>
      <div class="col-md-3"><label class="form-label">আগের দাম</label><input class="form-control" type="number" step=".01" min="0" name="old_price" value="{{ p.old_price or 0 }}"></div>
      <div class="col-md-3"><label class="form-label">ছাড় %</label><input class="form-control" type="number" min="0" max="100" name="discount" value="{{ p.discount_percent or 0 }}"></div>
      <div class="col-md-3"><label class="form-label">স্টক</label><input class="form-control" type="number" min="0" name="stock" value="{{ p.stock }}" required></div>
      <div class="col-12"><label class="form-label">প্রধান ছবি (বর্তমান ছবি না বদলালে খালি রাখুন)</label><div class="d-flex gap-3 align-items-center flex-wrap"><img src="{{ p.image }}" alt="বর্তমান ছবি" style="width:90px;height:90px;object-fit:contain;border:1px solid #ddd;border-radius:10px"><input class="form-control" style="max-width:420px" type="file" name="image_file" accept="image/*"></div><input class="form-control mt-2" type="url" name="image" placeholder="নতুন ছবির URL (ঐচ্ছিক)"></div>
      <div class="col-md-6"><label class="form-label">দ্বিতীয় ছবি পরিবর্তন (ঐচ্ছিক)</label><input class="form-control" type="file" name="image2_file" accept="image/jpeg,image/png,image/webp,image/gif"><input class="form-control mt-2" type="url" name="image2" placeholder="নতুন URL (ঐচ্ছিক)"><small class="text-muted">খালি রাখলে আগের ছবি থাকবে।</small></div>
      <div class="col-md-6"><label class="form-label">তৃতীয় ছবি পরিবর্তন (ঐচ্ছিক)</label><input class="form-control" type="file" name="image3_file" accept="image/jpeg,image/png,image/webp,image/gif"><input class="form-control mt-2" type="url" name="image3" placeholder="নতুন URL (ঐচ্ছিক)"><small class="text-muted">খালি রাখলে আগের ছবি থাকবে।</small></div>
      <div class="col-md-3"><label class="form-label">পরিমাপের একক</label><select class="form-select" name="unit_type"><option value="" {% if not p.unit_type %}selected{% endif %}>প্রযোজ্য নয়</option>{% for u in ['ml','L','g','kg','pcs','pack','pair','meter'] %}<option value="{{ u }}" {% if p.unit_type==u %}selected{% endif %}>{{ u }}</option>{% endfor %}</select></div><div class="col-md-3"><label class="form-label">পরিমাণ</label><input class="form-control" name="unit_value" value="{{ p.unit_value or '' }}"></div><div class="col-md-3"><label class="form-label">পোশাকের সাইজ</label><input class="form-control" name="sizes" value="{{ p.sizes or '' }}"></div><div class="col-md-3"><label class="form-label">কালার</label><input class="form-control" name="colors" value="{{ p.colors or '' }}"></div><div class="col-12"><label class="form-label">বিবরণ</label><textarea class="form-control" name="desc" rows="4">{{ p.description or '' }}</textarea></div>
      <div class="col-12 d-flex gap-2"><button class="btn btn-primary">পরিবর্তন সেভ করুন</button><a class="btn btn-outline-secondary" href="/admin/dashboard">ফিরে যান</a></div>
    </form></div></div>'''
    return render_template_string(BASE_HTML.replace('{% block content %}{% endblock %}', body), p=product, categories=categories)

@app.route('/admin/profile/update', methods=['POST'])
@admin_required
def admin_profile_update():
    db = get_db()
    name = (request.form.get('display_name') or '').strip()[:100]
    email = (request.form.get('email') or '').strip().lower()[:160]
    phone = (request.form.get('phone') or '').strip()[:30]
    current_password = request.form.get('current_password') or ''
    new_password = request.form.get('new_password') or ''
    if not name or '@' not in email or not phone:
        flash('নাম, সঠিক ইমেইল ও মোবাইল নম্বর দিন।', 'danger')
        return redirect(url_for('admin_dashboard'))
    db.execute("INSERT OR REPLACE INTO owner_profile(id,display_name,email,phone) VALUES(1,?,?,?)", (name,email,phone))
    if new_password:
        admin = db.execute('SELECT * FROM admins WHERE username=?', (session.get('admin_username'),)).fetchone()
        if not admin or not current_password or not check_password_hash(admin['password_hash'], current_password):
            db.rollback(); flash('পাসওয়ার্ড বদলাতে বর্তমান পাসওয়ার্ডটি সঠিকভাবে দিন।', 'danger')
            return redirect(url_for('admin_dashboard'))
        if len(new_password) < 8:
            db.rollback(); flash('নতুন পাসওয়ার্ড কমপক্ষে ৮ অক্ষরের হতে হবে।', 'danger')
            return redirect(url_for('admin_dashboard'))
        db.execute('UPDATE admins SET password_hash=? WHERE id=?', (generate_password_hash(new_password, method='pbkdf2:sha256'), admin['id']))
    db.commit()
    flash('Owner Profile সফলভাবে আপডেট হয়েছে।', 'success')
    return redirect(url_for('admin_dashboard'))


@app.route('/admin/logout')
def admin_logout():
    session.pop('is_admin', None)
    return redirect(url_for('admin_login'))



# =============================================================================
# FAYEZ ONLINE SHOP - SAFE ADDITIVE EXTENSIONS
# These extensions are appended without deleting the existing storefront/routes.
# =============================================================================
import csv
import io
import secrets
import difflib
import re
import time
import shutil
from pathlib import Path
from flask import make_response, abort

# Use a persistent secret in production: export FAYEZ_SECRET_KEY='a-long-random-value'
# Never use Flask debug mode on a public server.
app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE='Lax',
    SESSION_COOKIE_SECURE=os.environ.get('COOKIE_SECURE', '0') == '1',
    MAX_CONTENT_LENGTH=8 * 1024 * 1024,
)

_RATE_BUCKETS = {}
_RATE_WINDOW_SECONDS = 60
_RATE_MAX_REQUESTS = 120

@app.before_request
def _fayez_basic_rate_limit():
    'Small in-process safety limiter; use Redis-backed limits for multi-worker hosting.'
    now = time.time()
    ip = request.headers.get('X-Forwarded-For', request.remote_addr or 'unknown').split(',')[0].strip()
    key = (ip, int(now // _RATE_WINDOW_SECONDS))
    _RATE_BUCKETS[key] = _RATE_BUCKETS.get(key, 0) + 1
    # Keep this in-memory map bounded.
    if len(_RATE_BUCKETS) > 5000:
        for old_key in list(_RATE_BUCKETS)[:2000]:
            _RATE_BUCKETS.pop(old_key, None)
    if _RATE_BUCKETS[key] > _RATE_MAX_REQUESTS:
        abort(429)

@app.after_request
def _fayez_security_headers(response):
    response.headers.setdefault('X-Content-Type-Options', 'nosniff')
    response.headers.setdefault('X-Frame-Options', 'SAMEORIGIN')
    response.headers.setdefault('Referrer-Policy', 'strict-origin-when-cross-origin')
    response.headers.setdefault('Permissions-Policy', 'camera=(), microphone=(), geolocation=()')
    if request.is_secure:
        response.headers.setdefault('Strict-Transport-Security', 'max-age=31536000; includeSubDomains')
    return response


def _fayez_init_extensions():
    'Create additive tables; existing products/customers/orders are not dropped.'
    db = get_db()
    db.executescript('''
        CREATE TABLE IF NOT EXISTS audit_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            actor TEXT NOT NULL,
            action TEXT NOT NULL,
            details TEXT DEFAULT '',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS wishlists (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            customer_id INTEGER NOT NULL,
            product_id INTEGER NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(customer_id, product_id)
        );
        CREATE TABLE IF NOT EXISTS staff_users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            role TEXT NOT NULL CHECK(role IN ('manager','order_manager','inventory_manager','delivery')),
            active INTEGER NOT NULL DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    ''')
    # Safe, additive column migrations.
    columns = {row['name'] for row in db.execute('PRAGMA table_info(coupons)').fetchall()}
    if 'expires_at' not in columns:
        db.execute('ALTER TABLE coupons ADD COLUMN expires_at TEXT')
    if 'is_active' not in columns:
        db.execute('ALTER TABLE coupons ADD COLUMN is_active INTEGER NOT NULL DEFAULT 1')
    db.commit()


def _fayez_log(action, details=''):
    try:
        actor = session.get('admin_username') or session.get('customer_name') or 'system'
        db = get_db()
        db.execute('INSERT INTO audit_logs(actor, action, details) VALUES (?, ?, ?)',
                   (str(actor)[:120], str(action)[:120], str(details)[:1000]))
        db.commit()
    except Exception:
        app.logger.exception('Could not write audit log')


def _fayez_staff_required(*allowed_roles):
    def decorator(fn):
        @wraps(fn)
        def wrapped(*args, **kwargs):
            if not session.get('is_admin'):
                role = session.get('staff_role')
                if not role or (allowed_roles and role not in allowed_roles):
                    flash('এই কাজের অনুমতি নেই।', 'danger')
                    return redirect(url_for('admin_login'))
            return fn(*args, **kwargs)
        return wrapped
    return decorator

@app.route('/health')
def fayez_health():
    try:
        get_db().execute('SELECT 1').fetchone()
        return jsonify({'status': 'ok', 'database': 'connected'})
    except Exception:
        app.logger.exception('Health check failed')
        return jsonify({'status': 'error'}), 503

@app.route('/customer/wishlist')
@customer_required
def fayez_wishlist():
    db = get_db()
    items = db.execute('''SELECT p.* FROM wishlists w JOIN products p ON p.id=w.product_id
                          WHERE w.customer_id=? ORDER BY w.id DESC''',
                       (session['customer_id'],)).fetchall()
    body = '''<div class="container my-5"><h3>আমার Wishlist</h3><div class="row g-3">
    {% for p in items %}<div class="col-md-3"><div class="card h-100 p-2">
    <img src="{{ p.image }}" style="height:160px;object-fit:cover"><h6 class="mt-2">{{ p.name }}</h6>
    <p>৳ {{ '%.2f'|format(p.price) }}</p><a class="btn btn-sm btn-primary" href="/product/{{ p.id }}">দেখুন</a>
    <form method="post" action="/customer/wishlist/remove/{{ p.id }}"><button class="btn btn-sm btn-outline-danger mt-2">সরান</button></form>
    </div></div>{% else %}<p>Wishlist খালি।</p>{% endfor %}</div></div>'''
    return render_template_string(BASE_HTML.replace('{% block content %}{% endblock %}', body), items=items)

@app.route('/customer/wishlist/add/<int:pid>', methods=['POST'])
@customer_required
def fayez_wishlist_add(pid):
    db = get_db()
    if not db.execute('SELECT id FROM products WHERE id=?', (pid,)).fetchone():
        abort(404)
    db.execute('INSERT OR IGNORE INTO wishlists(customer_id, product_id) VALUES (?, ?)',
               (session['customer_id'], pid))
    db.commit()
    _fayez_log('wishlist_add', f'product_id={pid}')
    _fayez_track_customer_event('wishlist_add', pid)
    flash('পণ্য Wishlist-এ যোগ হয়েছে।', 'success')
    return redirect(request.referrer or url_for('shop'))

@app.route('/customer/wishlist/remove/<int:pid>', methods=['POST'])
@customer_required
def fayez_wishlist_remove(pid):
    db = get_db()
    _fayez_track_customer_event('wishlist_remove', pid, 'Wishlist থেকে সরানো হয়েছে')
    db.execute('DELETE FROM wishlists WHERE customer_id=? AND product_id=?',
               (session['customer_id'], pid))
    db.commit()
    return redirect(url_for('fayez_wishlist'))

@app.route('/compare')
def fayez_compare():
    raw = request.args.get('ids', '')
    try:
        ids = list(dict.fromkeys(int(x) for x in raw.split(',') if x.strip().isdigit()))[:4]
    except ValueError:
        ids = []
    products = []
    if ids:
        marks = ','.join('?' for _ in ids)
        products = get_db().execute(f'SELECT * FROM products WHERE id IN ({marks})', ids).fetchall()
    body = '''<div class="container my-5"><h3>পণ্য তুলনা</h3><div class="table-responsive"><table class="table table-bordered">
    <tr><th>বৈশিষ্ট্য</th>{% for p in products %}<th>{{ p.name }}</th>{% endfor %}</tr>
    <tr><th>দাম</th>{% for p in products %}<td>৳ {{ '%.2f'|format(p.price) }}</td>{% endfor %}</tr>
    <tr><th>স্টক</th>{% for p in products %}<td>{{ p.stock }}</td>{% endfor %}</tr>
    <tr><th>SKU</th>{% for p in products %}<td>{{ p.sku }}</td>{% endfor %}</tr>
    </table></div><p class="text-muted">তুলনার জন্য URL-এ ?ids=1,2,3 ব্যবহার করুন।</p></div>'''
    return render_template_string(BASE_HTML.replace('{% block content %}{% endblock %}', body), products=products)

@app.route('/admin/export/orders.csv')
@admin_required
def fayez_export_orders():
    rows = get_db().execute('''SELECT order_id, customer_id, total_amount, delivery_charge,
        discount_amount, payment_method, order_status, created_at FROM orders ORDER BY id DESC''').fetchall()
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['order_id','customer_id','total_amount','delivery_charge','discount_amount',
                     'payment_method','order_status','created_at'])
    for row in rows:
        writer.writerow([row[k] for k in row.keys()])
    response = make_response('\ufeff' + output.getvalue())
    response.headers['Content-Type'] = 'text/csv; charset=utf-8'
    response.headers['Content-Disposition'] = 'attachment; filename=fayez-orders.csv'
    _fayez_log('export_orders_csv', f'rows={len(rows)}')
    return response

@app.route('/admin/audit-logs')
@admin_required
def fayez_audit_logs():
    logs = get_db().execute('SELECT * FROM audit_logs ORDER BY id DESC LIMIT 300').fetchall()
    body = '''<div class="container my-5"><h3>Admin Activity Log</h3><div class="table-responsive"><table class="table table-striped">
    <thead><tr><th>সময়</th><th>Actor</th><th>Action</th><th>Details</th></tr></thead><tbody>
    {% for x in logs %}<tr><td>{{ x.created_at }}</td><td>{{ x.actor }}</td><td>{{ x.action }}</td><td>{{ x.details }}</td></tr>
    {% else %}<tr><td colspan="4">কোনো লগ নেই।</td></tr>{% endfor %}</tbody></table></div></div>'''
    return render_template_string(BASE_HTML.replace('{% block content %}{% endblock %}', body), logs=logs)

@app.route('/admin/backup')
@admin_required
def fayez_backup_database():
    'Create a SQLite backup in a private local backups folder; never expose it publicly.'
    db = get_db()
    backup_dir = Path(app.root_path) / 'private_backups'
    backup_dir.mkdir(mode=0o700, exist_ok=True)
    target = backup_dir / ('fayez-' + datetime.now().strftime('%Y%m%d-%H%M%S') + '.db')
    dest = sqlite3.connect(str(target))
    try:
        db.backup(dest)
    finally:
        dest.close()
    try:
        target.chmod(0o600)
    except OSError:
        pass
    _fayez_log('database_backup', target.name)
    flash('ডেটাবেজ ব্যাকআপ তৈরি হয়েছে (private_backups ফোল্ডারে)।', 'success')
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/low-stock')
@admin_required
def fayez_low_stock():
    products = get_db().execute('SELECT * FROM products WHERE stock <= 5 ORDER BY stock ASC').fetchall()
    body = '''<div class="container my-5"><h3>Low Stock Alert</h3><table class="table"><tr><th>SKU</th><th>পণ্য</th><th>স্টক</th></tr>
    {% for p in products %}<tr><td>{{ p.sku }}</td><td>{{ p.name }}</td><td class="text-danger fw-bold">{{ p.stock }}</td></tr>
    {% else %}<tr><td colspan="3">কম স্টকের পণ্য নেই।</td></tr>{% endfor %}</table></div>'''
    return render_template_string(BASE_HTML.replace('{% block content %}{% endblock %}', body), products=products)

# Add the additive schema after the original init_db has created its existing tables.
_original_init_db = init_db
def init_db():
    _original_init_db()
    with app.app_context():
        _fayez_init_extensions()


# ---- FAYEZ ONLINE SHOP: customer account, address book, returns, notifications ----
def _fayez_extra_schema():
    db = get_db()
    db.executescript('''
    CREATE TABLE IF NOT EXISTS customer_addresses (
      id INTEGER PRIMARY KEY AUTOINCREMENT, customer_id INTEGER NOT NULL,
      label TEXT DEFAULT 'Home', recipient TEXT NOT NULL, phone TEXT NOT NULL,
      division TEXT NOT NULL, district TEXT NOT NULL, upazila TEXT DEFAULT '',
      address TEXT NOT NULL, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    CREATE TABLE IF NOT EXISTS customer_notifications (
      id INTEGER PRIMARY KEY AUTOINCREMENT, customer_id INTEGER NOT NULL,
      message TEXT NOT NULL, is_read INTEGER NOT NULL DEFAULT 0,
      created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    CREATE TABLE IF NOT EXISTS return_requests (
      id INTEGER PRIMARY KEY AUTOINCREMENT, order_id INTEGER NOT NULL,
      customer_id INTEGER NOT NULL, reason TEXT NOT NULL,
      status TEXT NOT NULL DEFAULT 'Pending', created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    CREATE TABLE IF NOT EXISTS login_failures (
      id INTEGER PRIMARY KEY AUTOINCREMENT, identity TEXT NOT NULL,
      failed_at REAL NOT NULL
    );
    CREATE TABLE IF NOT EXISTS pending_registrations (
      email TEXT PRIMARY KEY, name TEXT NOT NULL, phone TEXT, password_hash TEXT NOT NULL,
      otp_hash TEXT NOT NULL, expires_at REAL NOT NULL
    );
    CREATE TABLE IF NOT EXISTS password_reset_otps (
      email TEXT PRIMARY KEY, otp_hash TEXT NOT NULL, expires_at REAL NOT NULL
    );
    ''')
    db.commit()

_old_fayez_init_db = init_db
def init_db():
    _old_fayez_init_db()
    with app.app_context():
        _fayez_extra_schema()
        # Add shipment tracking fields safely; existing customer/order rows are preserved.
        db = get_db()
        order_columns = {row['name'] for row in db.execute('PRAGMA table_info(orders)').fetchall()}
        for column, definition in (('courier_name', 'TEXT'), ('tracking_number', 'TEXT'), ('shipped_at', 'TIMESTAMP'), ('recipient_name', 'TEXT')):
            if column not in order_columns:
                db.execute(f'ALTER TABLE orders ADD COLUMN {column} {definition}')
        db.commit()
        # Create the first owner account only from a private hosting environment variable.
        db = get_db()
        owner_password = (os.environ.get('FAYEZ_ADMIN_PASSWORD') or '').strip()
        owner = db.execute("SELECT id FROM admins WHERE username='fayz'").fetchone()
        if not owner_password and not owner:
            raise RuntimeError('Set FAYEZ_ADMIN_PASSWORD in the hosting environment before first deploy.')
        if owner_password:
            owner_hash = generate_password_hash(owner_password, method='pbkdf2:sha256')
            if owner:
                db.execute('UPDATE admins SET password_hash=? WHERE id=?', (owner_hash, owner['id']))
            else:
                first_admin = db.execute('SELECT id FROM admins ORDER BY id LIMIT 1').fetchone()
                if first_admin:
                    db.execute("UPDATE admins SET username='fayz', password_hash=? WHERE id=?", (owner_hash, first_admin['id']))
                else:
                    db.execute('INSERT INTO admins(username,password_hash) VALUES(?,?)', ('fayz', owner_hash))
        db.commit()
        # Add starter category inventory without deleting or renumbering existing records.
        starter = [
          'Men Clothing','Women Clothing','Kids Clothing','Luxury Watches','Smartphones','Laptops','Tablets',
          'Headphones','Smart Watches','TV & Displays','Cameras & Photography','Computer Parts','Printers',
          'Networking Devices','Home Appliances','Kitchen Tools','Furniture','Home Decor','Bedding','Bath Supplies',
          'Makeup','Fragrances','Skin Care','Hair Styling','Men Grooming','Women Bags','Men Bags','Backpacks',
          'Sportswear','Gym Equipment','Football','Cricket','Toys','Board Games','School Supplies','Office Stationery',
          'Books & E-books','Art Materials','Car Electronics','Motorbike Accessories','Car Care','Garden Tools',
          'Pet Accessories','Pet Food','Packaged Foods','Rice & Pulses','Cooking Essentials','Snacks','Drinks','Organic Products'
        ]
        db=get_db()
        starter_image_map = {
          'Men Clothing':'https://images.unsplash.com/photo-1529139574466-a303027c1d8b?w=600',
          'Women Clothing':'https://images.unsplash.com/photo-1539109136881-3be0616acf4b?w=600',
          'Kids Clothing':'https://images.unsplash.com/photo-1503919005314-30d93d07d823?w=600',
          'Luxury Watches':'https://images.unsplash.com/photo-1523275335684-37898b6baf30?w=600',
          'Premium Accessories':'https://images.unsplash.com/photo-1611652022419-a9419f74343d?w=600',
          'Pet Accessories':'https://images.unsplash.com/photo-1548767797-d8c844163c4c?w=600',
          'Pet Food':'https://images.unsplash.com/photo-1589924691995-400dc9e2628c?w=600',
          'Smartphones':'https://images.unsplash.com/photo-1511707171634-5f897ff02aa9?w=600',
          'Laptops':'https://images.unsplash.com/photo-1496181133206-80ce9b88a853?w=600',
          'Headphones':'https://images.unsplash.com/photo-1505740420928-5e560c06d30e?w=600',
          'Women Bags':'https://images.unsplash.com/photo-1584917865442-de89df76afd3?w=600',
          'Men Bags':'https://images.unsplash.com/photo-1553062407-98eeb64c6a62?w=600',
          'Fragrances':'https://images.unsplash.com/photo-1594035910387-fea47794261f?w=600',
          'Makeup':'https://images.unsplash.com/photo-1596462502278-27bfdc403348?w=600',
          'Books & E-books':'https://images.unsplash.com/photo-1507842217343-583bb7270b66?w=600',
          'Football':'https://images.unsplash.com/photo-1574629810360-7efc6f4f2f2c?w=600',
          'Cricket':'https://images.unsplash.com/photo-1531415074968-036ba1b575da?w=600'
        }
        starter_image_map.update({
          'Tablets':'https://images.unsplash.com/photo-1544244015-0df4b3ffc6b0?w=600',
          'Smart Watches':'https://images.unsplash.com/photo-1544117519-31a4b719223d?w=600',
          'TV & Displays':'https://images.unsplash.com/photo-1593359677879-a4bb92f829d1?w=600',
          'Cameras & Photography':'https://images.unsplash.com/photo-1516035069371-29a1b244cc32?w=600',
          'Computer Parts':'https://images.unsplash.com/photo-1587202372775-e229f172b9d7?w=600',
          'Printers':'https://images.unsplash.com/photo-1612815154858-60aa4c59eaa6?w=600',
          'Networking Devices':'https://images.unsplash.com/photo-1558494949-ef010cbdcc31?w=600',
          'Home Appliances':'https://images.unsplash.com/photo-1556911220-e15b29be8c8f?w=600',
          'Kitchen Tools':'https://images.unsplash.com/photo-1556911220-bff31c812dba?w=600',
          'Furniture':'https://images.unsplash.com/photo-1555041469-a586c61ea9bc?w=600',
          'Home Decor':'https://images.unsplash.com/photo-1616486338812-3dadae4b4ace?w=600',
          'Bedding':'https://images.unsplash.com/photo-1631049307264-da0ec9d70304?w=600',
          'Bath Supplies':'https://images.unsplash.com/photo-1620626011761-996317b8d101?w=600',
          'Skin Care':'https://images.unsplash.com/photo-1601049541289-9b1b7bbbfe19?w=600',
          'Hair Styling':'https://images.unsplash.com/photo-1522337360788-8b13dee7a37e?w=600',
          'Men Grooming':'https://images.unsplash.com/photo-1621607512214-68297480165e?w=600',
          'Personal Care & Grooming':'https://images.unsplash.com/photo-1556229010-6c3f2c9ca5f8?w=600',
          'Women Bags':'https://images.unsplash.com/photo-1584917865442-de89df76afd3?w=600',
          'Men Bags':'https://images.unsplash.com/photo-1553062407-98eeb64c6a62?w=600',
          'Backpacks':'https://images.unsplash.com/photo-1622560480654-d96214fdc887?w=600',
          'Sportswear':'https://images.unsplash.com/photo-1517836357463-d25dfeac3438?w=600',
          'Gym Equipment':'https://images.unsplash.com/photo-1534438327276-14e5300c3a48?w=600',
          'Football':'https://images.unsplash.com/photo-1574629810360-7efc6f4f2f2c?w=600',
          'Cricket':'https://images.unsplash.com/photo-1531415074968-036ba1b575da?w=600',
          'Toys':'https://images.unsplash.com/photo-1566576912321-d58ddd7a6088?w=600',
          'Board Games':'https://images.unsplash.com/photo-1606503153255-59d8b8b821f0?w=600',
          'School Supplies':'https://images.unsplash.com/photo-1453738773917-9c3eff1db985?w=600',
          'Office Stationery':'https://images.unsplash.com/photo-1497215728101-856f4ea42174?w=600',
          'Books & E-books':'https://images.unsplash.com/photo-1507842217343-583bb7270b66?w=600',
          'Art Materials':'https://images.unsplash.com/photo-1513364776144-60967b0f800f?w=600',
          'Car Electronics':'https://images.unsplash.com/photo-1492144534655-ae79c964c9d7?w=600',
          'Motorbike Accessories':'https://images.unsplash.com/photo-1558981806-ec527fa84c39?w=600',
          'Car Care':'https://images.unsplash.com/photo-1607860108855-64acf2078ed9?w=600',
          'Garden Tools':'https://images.unsplash.com/photo-1416879595882-3373a0480b5b?w=600',
          'Pet Accessories':'https://images.unsplash.com/photo-1548767797-d8c844163c4c?w=600',
          'Pet Food':'https://images.unsplash.com/photo-1589924691995-400dc9e2628c?w=600',
          'Packaged Foods':'https://images.unsplash.com/photo-1606787366850-de6330128bfc?w=600',
          'Rice & Pulses':'https://images.unsplash.com/photo-1586201375761-83865001e31c?w=600',
          'Cooking Essentials':'https://images.unsplash.com/photo-1532336414038-cf19250c5757?w=600',
          'Snacks':'https://images.unsplash.com/photo-1621939514649-280e2aa5f2a1?w=600',
          'Drinks':'https://images.unsplash.com/photo-1544145945-f90425340c7e?w=600',
          'Organic Products':'https://images.unsplash.com/photo-1540420773420-3366772f4999?w=600'
        })
        # Do not auto-create generic starter categories; the storefront curated list is authoritative.
        for name in ():
            slug=''.join(ch.lower() if ch.isalnum() else '-' for ch in name).strip('-')
            image=starter_image_map.get(name)
            if image:
                db.execute('INSERT OR IGNORE INTO categories(name,slug,image) VALUES(?,?,?)',(name,slug,image))
                db.execute('UPDATE categories SET image=? WHERE slug=?',(image,slug))
            else:
                db.execute('INSERT OR IGNORE INTO categories(name,slug,image) VALUES(?,?,?)',(name,slug,'https://images.unsplash.com/photo-1542291026-7eec264c27ff?w=600'))
        db.commit()

@app.route('/customer/profile', methods=['GET','POST'])
@customer_required
def fayez_customer_profile():
    db=get_db(); cid=session['customer_id']
    if request.method=='POST':
        name=request.form.get('name','').strip(); phone=request.form.get('phone','').strip()
        if not name or len(name)>120:
            flash('নাম সঠিকভাবে লিখুন।','danger')
        else:
            db.execute('UPDATE customers SET name=?, phone=? WHERE id=?',(name,phone,cid)); db.commit()
            session['customer_name']=name; flash('প্রোফাইল আপডেট হয়েছে।','success')
            return redirect(url_for('fayez_customer_profile'))
    c=db.execute('SELECT * FROM customers WHERE id=?',(cid,)).fetchone()
    body='''<div class="container my-5" style="max-width:650px"><div class="card p-4 shadow-sm"><h3>আমার প্রোফাইল</h3><form method="post"><label>নাম</label><input class="form-control mb-3" name="name" value="{{ c.name }}" required><label>ইমেইল</label><input class="form-control mb-3" value="{{ c.email }}" disabled><label>মোবাইল</label><input class="form-control mb-3" name="phone" value="{{ c.phone or '' }}"><button class="btn btn-primary">পরিবর্তন সংরক্ষণ</button></form></div></div>'''
    return render_template_string(BASE_HTML.replace('{% block content %}{% endblock %}',body),c=c)

@app.route('/customer/addresses', methods=['GET','POST'])
@customer_required
def fayez_customer_addresses():
    db=get_db(); cid=session['customer_id']
    if request.method=='POST':
        vals=[request.form.get(k,'').strip() for k in ('label','recipient','phone','division','district','upazila','address')]
        if all(vals[1:5]) and vals[6]:
            db.execute('INSERT INTO customer_addresses(customer_id,label,recipient,phone,division,district,upazila,address) VALUES(?,?,?,?,?,?,?,?)',(cid,*vals)); db.commit(); flash('ঠিকানা সংরক্ষণ হয়েছে।','success')
        else: flash('প্রয়োজনীয় তথ্য পূরণ করুন।','danger')
        return redirect(url_for('fayez_customer_addresses'))
    rows=db.execute('SELECT * FROM customer_addresses WHERE customer_id=? ORDER BY id DESC',(cid,)).fetchall()
    body='''<div class="container my-5"><h3>সংরক্ষিত ঠিকানা</h3><form method="post" class="card card-body mb-4"><div class="row g-2">{% for k,l in fields %}<div class="col-md-6"><label>{{ l }}</label><input class="form-control" name="{{ k }}" required></div>{% endfor %}</div><button class="btn btn-primary mt-3">ঠিকানা যোগ করুন</button></form>{% for a in rows %}<div class="card card-body mb-2"><b>{{ a.label }} — {{ a.recipient }}</b><div>{{ a.phone }}, {{ a.address }}, {{ a.upazila }}, {{ a.district }}, {{ a.division }}</div></div>{% else %}<p>কোনো ঠিকানা সংরক্ষিত নেই।</p>{% endfor %}</div>'''
    fields=[('label','ঠিকানার ধরন'),('recipient','প্রাপকের নাম'),('phone','মোবাইল'),('division','বিভাগ'),('district','জেলা'),('upazila','উপজেলা'),('address','বিস্তারিত ঠিকানা')]
    return render_template_string(BASE_HTML.replace('{% block content %}{% endblock %}',body),rows=rows,fields=fields)

@app.route('/customer/returns', methods=['GET','POST'])
@customer_required
def fayez_customer_returns():
    db=get_db(); cid=session['customer_id']
    if request.method=='POST':
        oid=request.form.get('order_id','').strip(); reason=request.form.get('reason','').strip()
        order=db.execute('SELECT id FROM orders WHERE order_id=? AND customer_id=?',(oid,cid)).fetchone()
        if order and reason:
            db.execute('INSERT INTO return_requests(order_id,customer_id,reason) VALUES(?,?,?)',(order['id'],cid,reason)); db.commit(); flash('রিটার্ন অনুরোধ জমা হয়েছে।','success')
        else: flash('আপনার অর্ডার আইডি ও কারণ যাচাই করুন।','danger')
        return redirect(url_for('fayez_customer_returns'))
    rows=db.execute('SELECT r.*,o.order_id FROM return_requests r JOIN orders o ON o.id=r.order_id WHERE r.customer_id=? ORDER BY r.id DESC',(cid,)).fetchall()
    body='''<div class="container my-5"><h3>রিটার্ন ও রিফান্ড</h3><form method="post" class="card card-body mb-3"><input class="form-control mb-2" name="order_id" placeholder="অর্ডার আইডি" required><textarea class="form-control mb-2" name="reason" placeholder="রিটার্নের কারণ" required></textarea><button class="btn btn-primary">অনুরোধ পাঠান</button></form>{% for r in rows %}<div class="card card-body mb-2">{{ r.order_id }} — {{ r.reason }} <span class="badge bg-warning">{{ r.status }}</span></div>{% else %}<p>কোনো রিটার্ন অনুরোধ নেই।</p>{% endfor %}</div>'''
    return render_template_string(BASE_HTML.replace('{% block content %}{% endblock %}',body),rows=rows)

@app.route('/customer/notifications')
@customer_required
def fayez_customer_notifications():
    rows=get_db().execute('SELECT * FROM customer_notifications WHERE customer_id=? ORDER BY id DESC LIMIT 100',(session['customer_id'],)).fetchall()
    body='''<div class="container my-5"><h3>নোটিফিকেশন</h3>{% for n in rows %}<div class="alert alert-light border">{{ n.message }} <small class="text-muted">{{ n.created_at }}</small></div>{% else %}<p>নতুন নোটিফিকেশন নেই।</p>{% endfor %}</div>'''
    return render_template_string(BASE_HTML.replace('{% block content %}{% endblock %}',body),rows=rows)

@app.route('/customer/recently-viewed')
def fayez_recently_viewed():
    ids=session.get('recently_viewed',[])
    products=[]
    if ids:
        marks=','.join('?' for _ in ids)
        products=get_db().execute(f'SELECT * FROM products WHERE id IN ({marks})',ids).fetchall()
    body='''<div class="container my-5"><h3>সম্প্রতি দেখা পণ্য</h3><div class="row g-3">{% for p in products %}<div class="col-md-3"><div class="card p-2"><img src="{{ p.image }}" style="height:150px;object-fit:cover"><b>{{ p.name }}</b><p>৳ {{ p.price }}</p><a href="/product/{{ p.id }}" class="btn btn-sm btn-primary">দেখুন</a></div></div>{% else %}<p>এখনো কোনো পণ্য দেখা হয়নি।</p>{% endfor %}</div></div>'''
    return render_template_string(BASE_HTML.replace('{% block content %}{% endblock %}',body),products=products)


@app.route('/support')
def fayez_customer_support():
    body = r'''<style>.support-wrap{max-width:1050px;margin:42px auto;padding:0 16px}.support-hero{background:linear-gradient(120deg,#171d38,#5549b8);border-radius:24px;padding:34px;color:#fff}.support-grid{display:grid;grid-template-columns:repeat(3,1fr);gap:16px;margin-top:20px}.support-card{background:#fff;border:1px solid #e9ebf2;border-radius:18px;padding:22px;color:#20243a}.support-card i{font-size:1.5rem;color:#6558d8;margin-bottom:14px}.support-card a{font-weight:750;text-decoration:none}@media(max-width:700px){.support-wrap{margin:20px auto;padding:0 10px}.support-hero{padding:24px}.support-grid{grid-template-columns:1fr}}</style><main class="support-wrap"><section class="support-hero"><span class="badge bg-white text-dark rounded-pill mb-3">WE ARE HERE TO HELP</span><h1 class="fw-bold">২৪ ঘণ্টা ডেলিভারি ও অর্ডার সাপোর্ট</h1><p class="mb-0 text-white-50">আপনার প্রতিটি কেনাকাটায় আমরা সবসময় পাশে আছি। অর্ডার, পেমেন্ট বা ডেলিভারি—যেকোনো প্রয়োজনে আমাদের সঙ্গে যোগাযোগ করুন।</p></section><section class="support-grid"><div class="support-card"><i class="fa fa-phone d-block"></i><h5 class="fw-bold">ফোন সাপোর্ট</h5><p class="text-secondary">অর্ডার বা ডেলিভারি বিষয়ে সহায়তা পেতে কল করুন।</p><a href="tel:+8801307313063">+880 1307-313063</a></div><div class="support-card"><i class="fa fa-envelope d-block"></i><h5 class="fw-bold">ইমেইল সাপোর্ট</h5><p class="text-secondary">আপনার প্রশ্ন লিখে পাঠান।</p><a href="mailto:fayejislam56@gmail.com">fayejislam56@gmail.com</a></div><div class="support-card"><i class="fa-brands fa-whatsapp d-block"></i><h5 class="fw-bold">WhatsApp</h5><p class="text-secondary">যেকোনো প্রশ্নে WhatsApp-এ মেসেজ করুন।</p><a href="https://wa.me/8801307313063" target="_blank" rel="noopener">WhatsApp-এ চ্যাট করুন</a></div></section><div class="text-center mt-4"><a class="btn btn-outline-primary rounded-pill px-4" href="/track">অর্ডার ট্র্যাক করুন</a></div></main>'''
    return render_template_string(BASE_HTML.replace('{% block content %}{% endblock %}', body))

@app.route('/privacy')
def fayez_privacy():
    return render_template_string(BASE_HTML.replace('{% block content %}{% endblock %}','<div class="container my-5"><h2>Privacy Policy</h2><p>We use account and order information only to operate the store, process orders, prevent fraud and provide support. Contact support for data access or correction requests.</p></div>'))

@app.route('/terms')
def fayez_terms():
    return render_template_string(BASE_HTML.replace('{% block content %}{% endblock %}','<div class="container my-5"><h2>Terms & Conditions</h2><p>Orders are subject to stock confirmation, payment verification and delivery availability. Prices and delivery charges may change before order confirmation.</p></div>'))

@app.route('/refund-policy')
def fayez_refund_policy():
    return render_template_string(BASE_HTML.replace('{% block content %}{% endblock %}','<div class="container my-5"><h2>Return & Refund Policy</h2><p>Return requests are reviewed by the store. Keep order details and product packaging. Refund timing depends on the verified payment method.</p></div>'))



# ---- FAYEZ CATALOGUE EXPANSION: additive, idempotent, customer-safe ----
# Adds at least 20 products per curated category without deleting or replacing
# existing products. Images use the category's existing editorial image when a
# verified individual product packshot is not available. Prices are BDT reference
# estimates except the explicitly listed Himalaya items, which are listing snapshots.
_FAYEZ_CATALOGUE_GROUPS = {
'mens-fashion': ('Men’s Fashion', 650, 'Polo Ralph Lauren', ['Premium Cotton Crew-Neck T-Shirt', 'Premium Cotton Polo T-Shirt','Classic Oxford Shirt','Slim Fit Denim Jeans','Casual Chino Trousers','Full Sleeve Casual Shirt','Premium Panjabi','Zip Hoodie','Crew Neck Sweatshirt','Formal Dress Shirt','Stretch Waist Joggers']),
'womens-fashion': ('Women’s Fashion', 750, 'Aarong', ['Printed Cotton Kurti','Embroidered Three Piece','Georgette Saree','Casual Tunic Top','Linen Long Shirt','Modest Abaya','Palazzo Pants','Pleated Long Skirt','Cotton Leggings','Party Wear Blouse']),
'kids-fashion-new': ('Kids’ Fashion', 450, 'Baby Club', ['Kids Cotton T-Shirt','Printed Boys Polo Shirt','Girls Frock Dress','Baby Romper Suit','Kids Denim Jeans','School Uniform Shirt','Kids Hoodie','Cotton Pajama Set','Girls Leggings','Newborn Bodysuit']),
'shoes-footwear': ('Shoes & Footwear', 950, 'Apex', ['Men Casual Sneakers','Women Walking Shoes','Leather Formal Shoes','Running Sports Shoes','Canvas Slip-On Shoes','Kids School Shoes','Women Flat Sandals','Men Slide Sandals','Classic Loafers','Lightweight Trainers']),
'watches': ('Watches', 1250, 'Casio', ['Classic Analog Watch','Digital Sports Watch','Stainless Steel Watch','Minimalist Leather Watch','Water Resistant Sports Watch','Ladies Fashion Watch','Chronograph Style Watch','Silicone Strap Watch','Kids Digital Watch','Mesh Strap Watch']),
'mobile-phones': ('Mobile Phones', 12500, 'Samsung', ['Galaxy A Series Smartphone','Redmi Note Series Smartphone','realme C Series Smartphone','Infinix Hot Series Smartphone','Tecno Spark Series Smartphone','OPPO A Series Smartphone','vivo Y Series Smartphone','Nokia Feature Phone','Symphony Android Smartphone','OnePlus Nord Series Smartphone']),
'laptops-computers': ('Laptops & Computers', 28000, 'Lenovo', ['IdeaPad Slim Laptop','HP 15 Series Laptop','Dell Inspiron Laptop','ASUS VivoBook Laptop','Acer Aspire Laptop','Lenovo ThinkPad Laptop','All-in-One Desktop PC','Mini Desktop Computer','Refurbished Business Laptop','Portable USB-C Monitor']),
'headphones-speakers': ('Headphones & Speakers', 850, 'JBL', ['Wireless Bluetooth Headphones','True Wireless Earbuds','Wired Studio Headphones','Portable Bluetooth Speaker','Gaming Headset with Mic','Neckband Bluetooth Earphones','USB Desktop Speaker','Noise Isolating Earbuds','Kids Safe Volume Headphones','Party Bluetooth Speaker']),
'three-piece': ('Three-Piece', 950, 'Fayez Fashion', ['Printed Cotton Three-Piece with Dupatta','Embroidered Lawn Three-Piece','Classic Cambric Three-Piece','Digital Print Three-Piece','Cotton Salwar Kameez Three-Piece','Party Wear Embroidered Three-Piece','Georgette Three-Piece with Dupatta','Soft Lawn Three-Piece Suit','Traditional Floral Three-Piece','Premium Pakistani Style Three-Piece']),
'gaming-products': ('Gaming Products', 650, 'Logitech G', ['RGB Mechanical Gaming Keyboard','Gaming Mouse 8000 DPI','Gaming Headset with Microphone','Extended Gaming Mouse Pad','USB Game Controller','RGB Gaming Mouse Pad','Streaming Microphone','Gaming Capture Card','Racing Game Steering Wheel','Gaming Desk LED Light']),
'mobile-accessories': ('Mobile Accessories', 180, 'Anker', ['20W USB-C Fast Charger','10000mAh Power Bank','Tempered Glass Screen Protector','Shockproof Phone Case','USB-C Braided Cable','Car Phone Holder','MagSafe Wireless Charger','Multiport USB-C Hub','Phone Camera Lens Kit','Adjustable Phone Tripod']),
'skincare': ('Skincare', 120, 'Mixed Skincare', ['Nivea Soft Moisturizing Cream','Garnier Vitamin C Face Wash','Simple Kind to Skin Refreshing Face Wash','Cetaphil Gentle Skin Cleanser','Neutrogena Hydro Boost Water Gel','CeraVe Moisturizing Cream','The Ordinary Niacinamide 10% + Zinc 1%','Pond’s Bright Beauty Face Cream','Vaseline Intensive Care Body Lotion','L’Oréal Paris Revitalift Serum']),
'makeup-cosmetics': ('Makeup & Cosmetics', 250, 'Maybelline', ['Fit Me Matte Foundation','Instant Age Rewind Concealer','Super Stay Matte Lipstick','Colossal Kajal Eyeliner','Lash Sensational Mascara','Fit Me Compact Powder','Liquid Blush Makeup','Makeup Setting Spray','Eyeshadow Palette','Makeup Brush Set']),
'perfumes-fragrances': ('Perfumes & Fragrances', 650, 'Ajmal', ['Eau de Parfum for Men 100ml','Floral Eau de Parfum for Women','Fresh Citrus Body Mist','Oud Fragrance Spray','Long Lasting Deodorant Spray','Unisex Perfume 50ml','Pocket Perfume 20ml','Attar Concentrated Perfume Oil','Vanilla Body Mist','Woody Amber Fragrance']),
'hair-care': ('Hair Care', 180, 'L’Oréal', ['Total Repair Shampoo 375ml','Anti Hair Fall Shampoo 340ml','Nourishing Conditioner 180ml','Argan Hair Serum 100ml','Coconut Hair Oil 200ml','Anti Dandruff Shampoo 375ml','Keratin Hair Mask 250ml','Leave-In Hair Cream','Hair Growth Scalp Tonic','Heat Protection Spray']),
'personal-care-grooming': ('Personal Care & Grooming', 120, 'Philips', ['Men’s Beard Trimmer','Rechargeable Hair Clipper','Electric Shaver','Women’s Hair Removal Trimmer','Body Wash 500ml','Herbal Toothpaste 150gm','Soft Toothbrush Pack','Deodorant Roll-On','Hand Wash Refill 200ml','Nail Care Grooming Kit']),
'home-kitchen': ('Home & Kitchen', 250, 'RFL', ['Stainless Steel Water Bottle 1L','Nonstick Frying Pan 24cm','Food Storage Container Set','Cotton Bedsheet Set','Ceramic Dinner Plate Set','Vacuum Flask 1L','Laundry Basket','Kitchen Knife Set','Plastic Storage Rack','Bathroom Towel Set']),
'home-appliances': ('Home Appliances', 1800, 'Walton', ['Rechargeable Table Fan','Electric Room Heater','Digital Rice Cooker','Steam Iron 1200W','Air Cooler Compact','Washing Machine 8kg','LED Table Lamp','Electric Kettle 1.8L','Room Air Purifier','Portable Sewing Machine']),
'kitchen-appliances': ('Kitchen Appliances', 850, 'Philips', ['Electric Blender 1.5L','Hand Mixer 5 Speed','Sandwich Maker','Air Fryer 4L','Coffee Grinder','Electric Kettle 1.7L','Mini Food Chopper','Rice Cooker 1.8L','Juicer Machine','Handheld Milk Frother']),
'furniture-home-decor': ('Furniture & Home Decor', 950, 'Hatil', ['Modern Accent Chair','Compact Study Table','Ergonomic Office Chair','Bedside Table','3-Tier Bookshelf','Wall Mounted Shelf','Decorative Table Lamp','Minimalist Wall Clock','Sofa Cushion Set','Indoor Plant Stand']),
'cleaning-organization': ('Cleaning & Organization', 90, 'Mr. Clean', ['Microfiber Cleaning Cloth Pack','Multipurpose Floor Cleaner 1L','Dishwashing Liquid 500ml','Toilet Cleaner 500ml','Laundry Detergent 1kg','Kitchen Scrub Sponge Pack','Organizing Storage Box','Spray Mop','Dustpan and Brush Set','Garbage Bag Roll']),
'groceries': ('Groceries', 65, 'ACI Pure', ['Miniket Rice 5kg','Aromatic Chinigura Rice 1kg','Masoor Dal 1kg','Soybean Oil 1L','Mustard Oil 500ml','Premium Atta Flour 2kg','Sugar 1kg','Iodized Salt 1kg','Red Lentils 500gm','Chickpeas 1kg']),
'snacks-chocolates': ('Snacks & Chocolates', 35, 'Pran', ['Potato Chips Family Pack','Milk Chocolate Bar 40gm','Cream Biscuit Family Pack','Chocolate Wafer Pack','Salted Peanuts 200gm','Instant Noodles Pack','Butter Cookies Tin','Fruit Jelly Cups','Popcorn Snack Pack','Dark Chocolate Bar']),
'beverages': ('Beverages', 35, 'Coca-Cola', ['Orange Juice 1L','Mango Juice 1L','Lemon Malt Drink','Instant Coffee Jar 100gm','Black Tea Bags 100pcs','Green Tea 25 Bags','Drinking Chocolate 200gm','Mango Drink Pack','Energy Drink Can','Mineral Water 1.5L']),
'organic-natural-food': ('Organic & Natural Food', 120, 'Khaas Food', ['Raw Sundarban Honey 500gm','Organic Chia Seeds 250gm','Natural Dates 500gm','Cold Pressed Coconut Oil','Organic Turmeric Powder 200gm','Black Seed Honey 250gm','Pumpkin Seeds 200gm','Organic Green Tea','Natural Peanut Butter','Flax Seeds 250gm']),
'baby-products': ('Baby Products', 180, 'Pampers', ['Baby Diaper Medium Pack','Newborn Baby Wipes','Baby Gentle Shampoo','Baby Lotion 200ml','Feeding Bottle 250ml','Baby Cotton Vest Set','Baby Bath Towel','Soft Baby Blanket','Baby Powder 100gm','Silicone Feeding Spoon Set']),
'sports-fitness': ('Sports & Fitness', 250, 'Decathlon', ['Yoga Mat 6mm','Adjustable Hand Grip','Skipping Rope','Resistance Band Set','Dumbbell Pair 2kg','Football Size 5','Cricket Bat Kashmir Willow','Sports Water Bottle','Gym Training Gloves','Fitness Foam Roller']),
'books-stationery': ('Books & Stationery', 45, 'Matador', ['A5 Notebook 200 Pages','Ballpoint Pen Pack 10','Gel Pen Set','HB Pencil Pack','Art Sketchbook','Highlighter Set','Geometry Box','Desk Organizer','Scientific Calculator','Watercolor Paint Set']),
'car-bike-accessories': ('Car & Bike Accessories', 180, 'Autobacs', ['Car Phone Holder','Motorcycle Helmet','Car Seat Organizer','LED Headlight Bulb Pair','Bike Mobile Mount','Car Air Freshener','Tyre Pressure Gauge','Car Cleaning Kit','Motorcycle Rain Cover','USB Car Charger']),
'toys-games': ('Toys & Games', 180, 'LEGO', ['Building Blocks Starter Set','Remote Control Toy Car','Doll Play Set','Plush Teddy Bear','Kids Puzzle 100 Pieces','Board Game Family Edition','Toy Train Set','RC Mini Drone Toy','Educational Flash Cards','Kids Art Craft Kit']),
'bags-backpacks': ('Bags & Backpacks', 350, 'American Tourister', ['Laptop Backpack 15.6 Inch','Women Shoulder Handbag','Travel Duffel Bag','Canvas Tote Bag','School Backpack','Crossbody Sling Bag','Compact Wallet','Cabin Travel Trolley','Waterproof Hiking Backpack','Laptop Messenger Bag']),
'gaming-consoles': ('Gaming Consoles', 4500, 'Sony', ['PlayStation 5 Console','Xbox Series S Console','Nintendo Switch Console','Retro Handheld Game Console','Wireless Game Controller','DualSense Controller','Console Cooling Stand','Gaming Console Carry Case','VR Headset','Console Charging Dock']),
'pc-components': ('PC Components', 1500, 'ASUS', ['DDR4 8GB Desktop RAM','1TB NVMe SSD','500GB SATA SSD','650W Power Supply','Micro ATX PC Case','GeForce Graphics Card','B550 Motherboard','CPU Air Cooler','120mm RGB Case Fan','Wi-Fi 6 PCIe Adapter']),
'gaming-chairs-desks': ('Gaming Chairs & Desks', 3500, 'Fantech', ['Ergonomic Gaming Chair','Racing Style Gaming Chair','Height Adjustable Gaming Desk','Large Gaming Desk Mat','Monitor Riser Stand','Gaming Footrest','RGB Desk Shelf','Cable Management Tray','Ergonomic Lumbar Cushion','Dual Monitor Arm']),
}

def _fayez_customer_safe_description(name, category):
    # Never expose marketplace/source labels or seller notes in customer-facing copy.
    return f"{name} — {category} ক্যাটাগরির দৈনন্দিন ব্যবহারের পণ্য। কেনার আগে সাইজ, রং, মডেল, উপাদান ও ওয়ারেন্টি বিক্রেতার সঙ্গে নিশ্চিত করুন।"

def _fayez_seed_large_catalogue():
    """
    Product-photo integrity pass.
    Do not generate fictional products, pack sizes, prices, stock, or category-photo
    substitutes. Keep existing rows for the owner to review, but remove generic
    stock imagery and duplicated product photos. Automatically generated demo
    rows remain in the admin database for manual correction; public listings below
    show only products with an individual image URL.
    """
    db = get_db()
    cols = {r['name'] for r in db.execute('PRAGMA table_info(products)').fetchall()}
    if 'brand' not in cols:
        db.execute("ALTER TABLE products ADD COLUMN brand TEXT DEFAULT ''")
    if 'source_url' not in cols:
        db.execute("ALTER TABLE products ADD COLUMN source_url TEXT DEFAULT ''")
    if 'source_checked_at' not in cols:
        db.execute("ALTER TABLE products ADD COLUMN source_checked_at TEXT DEFAULT ''")

    # These SKU groups were generated as demo/catalogue placeholders by older code.
    # Their image and stock values were not verified against real inventory.
    db.execute("""UPDATE products SET image='', image2='', image3='', stock=0
                  WHERE sku LIKE 'FZ-CAT26-%' OR sku LIKE 'GM-PRO-%'
                     OR sku LIKE 'TL-HW-%' OR sku LIKE 'FZ-DZ-%'""")

    # Remove category/editorial stock photos and all duplicate image URLs.
    rows = db.execute("SELECT id, image, image2, image3 FROM products ORDER BY id").fetchall()
    seen = set()
    for row in rows:
        updates = {}
        for col in ('image', 'image2', 'image3'):
            value = (row[col] or '').strip()
            if not value:
                continue
            lower = value.lower()
            if 'images.unsplash.com' in lower:
                updates[col] = ''
            elif value in seen:
                updates[col] = ''
            else:
                seen.add(value)
        if updates:
            db.execute(
                "UPDATE products SET " + ", ".join(f"{col}=?" for col in updates) + " WHERE id=?",
                (*updates.values(), row['id'])
            )
    db.commit()
    return 0

_previous_fayez_catalog_init_db = init_db
def _fayez_seed_himalaya_catalogue():
    """Add the 52 personal-care/baby-care items listed by Himalaya Wellness Bangladesh.
    Prices are fixed starter retail estimates in BDT, not official supplier quotes.
    Stock remains zero until the owner confirms physical inventory.
    """
    # name, pack, category slug, BDT retail price, product-page slug, image URL
    rows = [
      ('Anti-Dandruff Soothing & Moisturising Shampoo','180ml','hair-care',320,'anti-dandruff-soothing-moisturising-shampoo-180ml'),
      ('Anti-Dandruff Soothing & Moisturising Shampoo','375ml','hair-care',590,'anti-dandruff-soothing-moisturising-shampoo-375ml'),
      ('Anti-Dandruff Soothing & Moisturising Shampoo','80ml','hair-care',170,'anti-dandruff-soothing-moisturising-shampoo-80ml'),
      ('Anti-Hair Fall Shampoo','180ml','hair-care',320,'anti-hair-fall-shampoo-180ml'),
      ('Anti-Hair Fall Shampoo','375ml','hair-care',590,'anti-hair-fall-shampoo-375ml'),
      ('Anti-Hair Fall Shampoo','80ml','hair-care',170,'anti-hair-fall-shampoo-80ml'),
      ('Baby Cream','100ml','baby-products',365,'baby-cream-100ml'),
      ('Baby Cream','50ml','baby-products',220,'baby-cream-50ml'),
      ('Baby Lotion','100ml','baby-products',430,'baby-lotion-100ml'),
      ('Baby Lotion','200ml','baby-products',735,'baby-lotion-200ml'),
      ('Baby Powder','100gm','baby-products',1055,'baby-powder-100gm'),
      ('Fresh Start Oil Clear Face Wash - Blueberry','100ml','skincare',390,'fresh-start-oil-clear-face-wash-blueberry-100ml'),
      ('Fresh Start Oil Clear Face Wash - Blueberry','50ml','skincare',250,'fresh-start-oil-clear-face-wash-blueberry-50ml'),
      ('Fresh Start Oil Clear Face Wash - Lemon','100ml','skincare',390,'fresh-start-oil-clear-face-wash-lemon-100ml'),
      ('Fresh Start Oil Clear Face Wash - Lemon','50ml','skincare',250,'fresh-start-oil-clear-face-wash-lemon-50ml'),
      ('Fresh Start Oil Clear Face Wash - Peach','100ml','skincare',390,'fresh-start-oil-clear-face-wash-peach-100ml'),
      ('Fresh Start Oil Clear Face Wash - Peach','50ml','skincare',250,'fresh-start-oil-clear-face-wash-peach-50ml'),
      ('Fresh Start Oil Clear Face Wash - Strawberry','100ml','skincare',390,'fresh-start-oil-clear-face-wash-strawberry-100ml'),
      ('Fresh Start Oil Clear Face Wash - Strawberry','50ml','skincare',250,'fresh-start-oil-clear-face-wash-strawberry-50ml'),
      ('Gentle Baby Bath','100ml','baby-products',260,'gentle-baby-bath-100ml'),
      ('Gentle Baby Bath','200ml','baby-products',420,'gentle-baby-bath-200ml'),
      ('Gentle Baby Shampoo','100ml','baby-products',260,'gentle-baby-shampoo-100ml'),
      ('Gentle Baby Shampoo','200ml','baby-products',420,'gentle-baby-shampoo-200ml'),
      ('Gentle Baby Shampoo','400ml','baby-products',720,'gentle-baby-shampoo-400ml'),
      ('Gentle Baby Soap','75gm','baby-products',150,'gentle-baby-soap-75gm'),
      ('Intense Oil Clear Lemon Face Wash','100ml','skincare',390,'intense-oil-clear-lemon-face-wash-100ml'),
      ('Intense Oil Clear Lemon Face Wash','50ml','skincare',250,'intense-oil-clear-lemon-face-wash-50ml'),
      ('Moisturising Aloe Vera Face Wash','100ml','skincare',390,'moisturising-aloe-vera-face-wash-100ml'),
      ('Moisturising Aloe Vera Face Wash','50ml','skincare',250,'moisturising-aloe-vera-face-wash-50ml'),
      ('Natural Glow Rose Face Wash','100ml','skincare',390,'natural-glow-rose-face-wash'),
      ('Natural Glow Saffron Face Cream','25gm','skincare',290,'natural-glow-saffron-face-cream-25gm'),
      ('Natural Glow Saffron Face Cream','50gm','skincare',490,'natural-glow-saffron-face-cream-50gm'),
      ('Natural Glow Saffron Face Wash','100ml','skincare',390,'natural-glow-saffron-face-wash-100ml'),
      ('Natural Glow Saffron Face Wash','50ml','skincare',250,'natural-glow-saffron-face-wash-50ml'),
      ('Neem & Turmeric Soap','125gm','personal-care-grooming',210,'neem-turmeric-soap-125gm'),
      ('Neem & Turmeric Soap','75gm','personal-care-grooming',145,'neem-turmeric-soap-75gm'),
      ('Nourishing Skin Cream','50gm','skincare',365,'nourishing-skin-cream-50gm'),
      ('Oil Clear Lemon Face Wash','100ml','skincare',350,'oil-clear-lemon-face-wash-100ml'),
      ('Oil Clear Lemon Face Wash','50ml','skincare',230,'oil-clear-lemon-face-wash-50ml'),
      ('Pimple Clear Neem Face Wash','100ml','skincare',390,'pimple-clear-neem-face-wash-100ml'),
      ('Pimple Clear Neem Face Wash','50ml','skincare',250,'pimple-clear-neem-face-wash-50ml'),
      ('Pollution Detox Charcoal Face Wash','100ml','skincare',420,'pollution-detox-charcoal-face-wash'),
      ('Power Glow Licorice Face Wash','100ml','skincare',420,'power-glow-licorice-face-wash-100ml'),
      ('Power Glow Licorice Face Wash','50ml','skincare',270,'power-glow-licorice-face-wash-50ml'),
      ('Prickly Heat Baby Powder','100gm','baby-products',260,'prickly-heat-baby-powder-100gm'),
      ('Prickly Heat Baby Powder','50gm','baby-products',160,'prickly-heat-baby-powder-50gm'),
      ('Purifying Neem Face Wash','100ml','skincare',350,'purifying-neem-face-wash-100ml'),
      ('Purifying Neem Face Wash','150ml','skincare',470,'purifying-neem-face-wash-150ml'),
      ('Purifying Neem Face Wash','15ml','skincare',70,'purifying-neem-face-wash-15ml'),
      ('Purifying Neem Face Wash','300ml','skincare',850,'purifying-neem-face-wash-300ml'),
      ('Purifying Neem Face Wash','50ml','skincare',230,'purifying-neem-face-wash-50ml'),
      ('Purifying Neem Pack','Neem Pack','skincare',420,'purifying-neem-pack'),
    ]
    # Fetch the actual product pack-shot URL from each matching official Shopify product.
    # The .js endpoint exposes the product's own image list; no category stock photos
    # or one-image-for-everything fallback is used.
    def official_packshot(item):
        name, pack, slug, price, product_slug = item
        endpoint = 'https://himalayawellness.com.bd/products/' + product_slug + '.js'
        try:
            req = urllib.request.Request(endpoint, headers={'User-Agent': 'FayezOnlineShop/1.0'})
            with urllib.request.urlopen(req, timeout=5) as response:
                data = json.loads(response.read().decode('utf-8'))
            title = (data.get('title') or '').strip().casefold()
            expected = (name + (' ' + pack if pack.lower() not in name.lower() else '')).strip().casefold()
            # Shopify titles sometimes omit the size for the one-size product;
            # only accept a close exact title match to avoid wrong product photos.
            if not title or (title != expected and title != name.strip().casefold()):
                return product_slug, ''
            images = data.get('images') or []
            return product_slug, (images[0] if images else '')
        except Exception:
            return product_slug, ''

    with ThreadPoolExecutor(max_workers=8) as pool:
        official_images = dict(pool.map(official_packshot, rows))
    db = get_db()
    added = 0
    for name, pack, slug, price, product_slug in rows:
        sku = 'FZ-HIM26-' + product_slug.upper().replace('-', '')
        official_image = official_images.get(product_slug, '')
        existing = db.execute('SELECT id FROM products WHERE sku=?', (sku,)).fetchone()
        if existing:
            # Refresh only the image field from the exact official product page.
            # If the source cannot verify a pack-shot, clear the old generic category image.
            db.execute('UPDATE products SET image=? WHERE id=?', (official_image, existing['id']))
            continue
        cat = db.execute('SELECT id FROM categories WHERE slug=?', (slug,)).fetchone()
        if not cat:
            continue
        url = 'https://himalayawellness.com.bd/products/' + product_slug
        detail = (f'{name} ({pack}). Himalaya Wellness Bangladesh official catalogue item. '
                  f'Category: {slug.replace("-", " ").title()}. Pack size: {pack}. '
                  'Use according to the product label. Check the original pack for complete ingredients, '
                  'directions, warnings and batch/expiry information. The listed retail price is a '
                  'Fayez Online Shop starter estimate in BDT, not an official Himalaya price quotation; '
                  'confirm supplier price before publishing. Product details and availability may change. '
                  'Official product page: ' + url)
        db.execute('''INSERT INTO products
          (name, sku, category_id, price, old_price, discount_percent, stock, country_of_origin,
           colors, description, image, image2, image3, is_flash_sale, brand, source_url, source_checked_at)
          VALUES (?, ?, ?, ?, NULL, 0, 0, 'India / as labelled on pack', 'As per pack', ?, ?, '', '', 0,
                  'Himalaya', ?, '2026-11-16')''',
          (name + ' - ' + pack, sku, cat['id'], price, detail, official_image, url))
        added += 1
    db.commit()
    return added

_previous_fayez_catalog_init_db = init_db
def init_db():
    _previous_fayez_catalog_init_db()
    with app.app_context():
        added = _fayez_seed_large_catalogue()
        him_added = 0  # User requested: do not add any new Himalaya products.
        db = get_db()
        db.execute("CREATE TABLE IF NOT EXISTS owner_profile (id INTEGER PRIMARY KEY CHECK(id=1), display_name TEXT NOT NULL, email TEXT NOT NULL, phone TEXT NOT NULL)")
        db.execute("INSERT OR IGNORE INTO owner_profile(id,display_name,email,phone) VALUES(1,?,?,?)", ('Fayez', 'fayejislam56@gmail.com', '01307313063'))
        # Owner password is set only through the private FAYEZ_ADMIN_PASSWORD variable.

        if added:
            print(f"Fayez catalogue: added {added} products; existing products preserved.")
        if him_added:
            print(f"Himalaya catalogue: added {him_added} products; existing products preserved.")


# Additional 25 Himalaya personal-care products sourced from an independent
# Bangladesh retailer's live catalogue. Prices are retailer-listed BDT snapshots,
# not official Himalaya MRPs. Product images are fetched only from matching
# individual product pages; never substitute a generic/category image.
_FAYEZ_HIMALAYA_EXTRA25 = [
    ('Aloe & Cucumber Refreshing Body Lotion', 345, 'skincare'),
    ('Aloe & Cucumber Refreshing Serum Body Lotion', 345, 'skincare'),
    ('Cocoa Butter Intensive Serum Body Lotion', 345, 'skincare'),
    ('FootCare Cream', 210, 'personal-care-grooming'),
    ('Himalaya Hydrating Aloe Vera Face Wash', 335, 'skincare'),
    ('Himalaya Moisturizing Aloe Vera Face Gel', 335, 'skincare'),
    ('Himalaya Olive Extra Nourishing Body Lotion', 370, 'skincare'),
    ('Himalaya Olive Extra Nourishing Cream', 910, 'skincare'),
    ('Himalaya Sun Protect+ Ultra-Light Sunscreen', 870, 'skincare'),
    ('Honey & Cream Soap', 115, 'personal-care-grooming'),
    ('Hydra Plump Aloe Face Serum', 1045, 'skincare'),
    ('Moisturizing Aloe Vera Facial Wipes', 420, 'personal-care-grooming'),
    ('Nourishing Face Moisturizing Lotion', 350, 'skincare'),
    ('Protective Sunscreen Lotion', 770, 'skincare'),
    ('Rich Cocoa Butter Body Cream', 1045, 'skincare'),
    ('Age Defying Hand Cream', 695, 'personal-care-grooming'),
    ('Anti Hair Fall Cream', 350, 'hair-care'),
    ('Anti-Dandruff Hair Cream', 350, 'hair-care'),
    ('Anti-Dandruff Hair Oil', 495, 'hair-care'),
    ('Anti-Dandruff Tea Tree Conditioner', 345, 'hair-care'),
    ('Anti-Hair Fall Bhringaraja Conditioner', 345, 'hair-care'),
    ('Anti-Hair Fall Caffeine Shampoo', 1085, 'hair-care'),
    ('Anti-Hair Fall Conditioner', 315, 'hair-care'),
    ('Anti-Hair Fall Hair Oil', 495, 'hair-care'),
    ('Anti-Wrinkle Cream', 945, 'skincare'),
]

def _fayez_himalaya_extra_image(product_name):
    # Find an exact matching retailer product page and its own OpenGraph packshot.
    search_url = 'https://himalaya.bd/?s=' + urllib.parse.quote_plus(product_name) + '&post_type=product'
    headers = {'User-Agent': 'Mozilla/5.0 (compatible; FayezOnlineShop/1.0)'}
    try:
        req = urllib.request.Request(search_url, headers=headers)
        with urllib.request.urlopen(req, timeout=7) as response:
            html = response.read(2_000_000).decode('utf-8', 'ignore')
        # WooCommerce search cards contain links to individual product pages.
        links = re.findall(r'''href=["'](https?://himalaya\.bd/product/[^"'#?]+|/product/[^"'#?]+)["']''', html, re.I)
        candidates = []
        for link in links:
            full = urllib.parse.urljoin('https://himalaya.bd/', link)
            if full not in candidates:
                candidates.append(full)
        # Search result can occasionally redirect directly to the product page.
        if not candidates and '/product/' in search_url:
            candidates.append(search_url)
        wanted = re.sub(r'[^a-z0-9]+', ' ', product_name.casefold()).strip()
        for page_url in candidates[:6]:
            try:
                req = urllib.request.Request(page_url, headers=headers)
                with urllib.request.urlopen(req, timeout=7) as response:
                    page = response.read(1_500_000).decode('utf-8', 'ignore')
                title_m = re.search(r"<meta[^>]+property=[\"\']og:title[\"\'][^>]+content=[\"\']([^\"\']+)", page, re.I)
                if not title_m:
                    title_m = re.search(r'<title[^>]*>(.*?)</title>', page, re.I | re.S)
                title = re.sub(r'<[^>]+>', ' ', title_m.group(1) if title_m else '')
                normalized = re.sub(r'[^a-z0-9]+', ' ', title.casefold()).strip()
                if wanted not in normalized and normalized not in wanted:
                    # tolerate retailer prefix/suffix while requiring most words
                    words = set(wanted.split())
                    if not words or len(words & set(normalized.split())) / len(words) < 0.80:
                        continue
                image_m = re.search(r"<meta[^>]+property=[\"\']og:image[\"\'][^>]+content=[\"\']([^\"\']+)", page, re.I)
                if not image_m:
                    image_m = re.search(r"<meta[^>]+content=[\"\']([^\"\']+)[\"\'][^>]+property=[\"\']og:image[\"\']", page, re.I)
                if image_m:
                    image_url = image_m.group(1).replace('&amp;', '&')
                    if image_url.startswith('https://'):
                        return page_url, image_url
            except Exception:
                continue
    except Exception:
        pass
    return search_url, ''

def _fayez_seed_himalaya_extra25():
    db = get_db()
    total = 0
    # Resolve individual product pages concurrently to keep startup responsive.
    with ThreadPoolExecutor(max_workers=8) as pool:
        resolved = dict(zip((x[0] for x in _FAYEZ_HIMALAYA_EXTRA25), pool.map(_fayez_himalaya_extra_image, (x[0] for x in _FAYEZ_HIMALAYA_EXTRA25))))
    # Existing Himalaya products from the official Bangladesh catalogue are left untouched.
    for name, price, category_slug in _FAYEZ_HIMALAYA_EXTRA25:
        sku = 'FZ-HIMX26-' + re.sub(r'[^A-Z0-9]+', '', name.upper())[:34]
        existing = db.execute('SELECT id, image FROM products WHERE sku=?', (sku,)).fetchone()
        if existing:
            if not (existing['image'] or '').strip():
                page_url, image_url = resolved.get(name, ('', ''))
                if image_url:
                    db.execute('UPDATE products SET image=?, source_url=? WHERE id=?', (image_url, page_url, existing['id']))
            continue
        category = db.execute('SELECT id FROM categories WHERE slug=?', (category_slug,)).fetchone()
        if not category:
            continue
        page_url, image_url = resolved.get(name, ('', ''))
        description = (
            f'{name} — Himalaya personal-care product. Retailer-listed Bangladesh reference price: ৳{price}. '
            'This is an independent retailer price snapshot, not an official Himalaya price quotation; '
            'confirm current supplier price, exact pack size, authenticity and availability before sale. '
            'Check the original package for ingredients, directions, warnings and expiry information.'
        )
        db.execute('''INSERT INTO products
          (name, sku, category_id, price, old_price, discount_percent, stock, country_of_origin,
           colors, description, image, image2, image3, is_flash_sale, brand, source_url, source_checked_at)
          VALUES (?, ?, ?, ?, NULL, 0, 0, 'As labelled on original pack', 'As shown on original pack', ?, ?, '', '', 0,
                  'Himalaya', ?, '2026-11-16')''',
          (name, sku, category['id'], price, description, image_url, page_url))
        total += 1
    db.commit()
    return total

_previous_himalaya_extra_init_db = init_db
def init_db():
    _previous_himalaya_extra_init_db()
    with app.app_context():
        extra_added = 0  # User requested: do not add any new Himalaya products.
        if extra_added:
            print(f'Himalaya additional catalogue: added {extra_added} products.')




# --- Curated Three-Piece catalogue refresh (safe, source-backed import) ---
# Imports only products explicitly listed by the supplied Bangladesh retailers.
# Existing catalogue rows are removed only AFTER at least one real product is fetched.
import html as _html
from html.parser import HTMLParser as _HTMLParser
from urllib.error import URLError as _URLError
from urllib.request import Request as _Request, urlopen as _urlopen

_FAYEZ_THREE_PIECE_SOURCES = [
    ("Daraz Bangladesh", "https://www.daraz.com.bd"),
    ("AjkerDeal", "https://www.ajkerdeal.com"),
    ("Othoba", "https://www.othoba.com"),
    ("PriyoShop", "https://www.priyoshop.com"),
    ("Aarong", "https://www.aarong.com"),
    ("Le Reve", "https://www.lerevecraze.com"),
    ("Yellow", "https://www.yellowclothing.net"),
    ("Rang Bangladesh", "https://www.rang-bd.com"),
    ("Kay Kraft", "https://www.kaykraft.com"),
    ("Sara Lifestyle", "https://www.saralifestyle.com"),
]
_FAYEZ_THREE_TERMS = ("three piece", "three-piece", "threepiece", "3 piece", "3-piece",
                      "ত্রিপিছ", "থ্রিপিস", "থ্রি পিস", "salwar kameez set")
_FAYEZ_NOT_THREE_TERMS = ("two piece", "two-piece", "2 piece", "2-piece", "kurti only",
                          "single kurti", "blouse only", "saree", "শাড়ি", "bra", "panty", "underwear", "sleepwear", "three-point")

class _FayezJSONLDParser(_HTMLParser):
    def __init__(self):
        super().__init__()
        self.in_jsonld = False
        self.parts = []
        self.current = []
        self.meta = {}
        self.links = []
    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag.lower() == "script" and "ld+json" in a.get("type", "").lower():
            self.in_jsonld = True
            self.current = []
        if tag.lower() == "meta":
            key = a.get("property") or a.get("name")
            if key and a.get("content"):
                self.meta[key.lower()] = a["content"]
        if tag.lower() == "a" and a.get("href"):
            self.links.append(a["href"])
    def handle_data(self, data):
        if self.in_jsonld:
            self.current.append(data)
    def handle_endtag(self, tag):
        if tag.lower() == "script" and self.in_jsonld:
            self.parts.append("".join(self.current))
            self.current = []
            self.in_jsonld = False

def _fayez_walk_jsonld(obj):
    if isinstance(obj, list):
        for x in obj:
            yield from _fayez_walk_jsonld(x)
    elif isinstance(obj, dict):
        typ = obj.get("@type", "")
        if isinstance(typ, list):
            typ = " ".join(map(str, typ))
        if "Product" in str(typ):
            yield obj
        for key in ("@graph", "mainEntity", "itemListElement", "offers"):
            if key in obj and isinstance(obj[key], (dict, list)):
                yield from _fayez_walk_jsonld(obj[key])

def _fayez_clean_image(value):
    if isinstance(value, list):
        value = next((x for x in value if isinstance(x, str) and x.startswith("http")), "")
    elif isinstance(value, dict):
        value = value.get("url") or value.get("contentUrl") or ""
    if isinstance(value, str) and value.startswith("//"):
        value = "https:" + value
    return value if isinstance(value, str) and value.startswith(("https://", "http://")) else ""

def _fayez_extract_products(page_url, source_name, html_text, parser):
    found = []
    for raw in parser.parts:
        try:
            data = json.loads(raw.strip().replace("<!--", "").replace("-->", ""))
        except Exception:
            continue
        for product in _fayez_walk_jsonld(data):
            name = _html.unescape(str(product.get("name") or "")).strip()
            low = name.casefold()
            if not name or not any(t in low for t in _FAYEZ_THREE_TERMS):
                continue
            if any(t in low for t in _FAYEZ_NOT_THREE_TERMS):
                continue
            image = _fayez_clean_image(product.get("image"))
            if not image:
                continue
            offers = product.get("offers") or {}
            if isinstance(offers, list):
                offers = offers[0] if offers else {}
            if isinstance(offers, dict) and isinstance(offers.get("offers"), list):
                offers = offers["offers"][0] if offers["offers"] else {}
            try:
                price = float(str((offers or {}).get("price") or product.get("offers", {}).get("price") or "").replace(",", "").replace("৳", "").strip())
            except Exception:
                price = 0
            if price <= 0 or price > 100000:
                continue
            product_url = product.get("url") or page_url
            if isinstance(product_url, str) and product_url.startswith("/"):
                from urllib.parse import urljoin as _urljoin
                product_url = _urljoin(page_url, product_url)
            brand = product.get("brand") or source_name
            if isinstance(brand, dict):
                brand = brand.get("name") or source_name
            found.append({
                "name": name[:240], "price": price, "image": image,
                "url": product_url if isinstance(product_url, str) else page_url,
                "brand": str(brand)[:100], "source": source_name
            })
    # Fallback to OpenGraph on a product page where JSON-LD is absent.
    meta = parser.meta
    title = meta.get("og:title", "")
    low = title.casefold()
    image = _fayez_clean_image(meta.get("og:image", ""))
    if title and image and any(t in low for t in _FAYEZ_THREE_TERMS) and not any(t in low for t in _FAYEZ_NOT_THREE_TERMS):
        try:
            price = float(str(meta.get("product:price:amount") or meta.get("og:price:amount") or "").replace(",", ""))
        except Exception:
            price = 0
        if 0 < price <= 100000:
            found.append({"name": title[:240], "price": price, "image": image,
                          "url": page_url, "brand": source_name, "source": source_name})
    return found

def _fayez_fetch_three_piece_catalogue():
    from urllib.parse import urljoin as _urljoin, urlparse as _urlparse
    collected = {}
    pages_checked = 0
    for source_name, base in _FAYEZ_THREE_PIECE_SOURCES:
        domain = _urlparse(base).netloc
        candidates = [
            base,
            _urljoin(base, "/search?q=three%20piece"),
            _urljoin(base, "/search?query=three%20piece"),
            _urljoin(base, "/collections/three-piece"),
            _urljoin(base, "/collections/three-pieces"),
            _urljoin(base, "/women/three-piece"),
            _urljoin(base, "/women/salwar-kameez"),
            _urljoin(base, "/catalogsearch/result/?q=three+piece"),
        ]
        # Search-indexed, direct retailer product pages verified on the supplied sites.
        if "daraz.com.bd" in domain:
            candidates += [
                "https://www.daraz.com.bd/products/three-piece-i354726911.html",
                "https://www.daraz.com.bd/products/-i1584385235.html",
                "https://www.daraz.com.bd/products/-i1586794018.html",
                "https://www.daraz.com.bd/products/new-three-piece-collection-for-women-3pcs-i524749931.html",
                "https://www.daraz.com.bd/products/three-piece-for-women-i316170341.html",
                "https://www.daraz.com.bd/products/-i1574554463.html",
                "https://www.daraz.com.bd/products/three-piece-i391794858.html",
                "https://www.daraz.com.bd/products/womens-three-piece-collection-new-i315192868.html",
                "https://www.daraz.com.bd/tag/branded-three-piece-for-women/",
                "https://www.daraz.com.bd/tag/three-piece-for-women-s/",
            ]
        if "othoba.com" in domain:
            candidates += [
                "https://othoba.com/three-piece-for-women-281186",
                "https://othoba.com/three-piece-for-women-281184",
            ]
        visited = set()
        for page_url in candidates:
            if page_url in visited or pages_checked >= 65:
                continue
            visited.add(page_url)
            pages_checked += 1
            try:
                req = _Request(page_url, headers={"User-Agent":"Mozilla/5.0 (compatible; FayezShopCatalogue/1.0)", "Accept":"text/html,application/xhtml+xml"})
                with _urlopen(req, timeout=9) as response:
                    if response.status >= 400:
                        continue
                    raw = response.read(2_500_000)
                    charset = response.headers.get_content_charset() or "utf-8"
                text_html = raw.decode(charset, errors="replace")
                parser = _FayezJSONLDParser()
                parser.feed(text_html)
                for item in _fayez_extract_products(page_url, source_name, text_html, parser):
                    key = (item["name"].casefold(), round(item["price"], 2))
                    collected.setdefault(key, item)
                # Follow a small number of relevant product links found on collection/search pages.
                if any(x in page_url.casefold() for x in ("search", "collection", "women", "salwar")) or page_url == base:
                    relevant = []
                    for href in parser.links:
                        target = _urljoin(page_url, href)
                        parsed = _urlparse(target)
                        if parsed.netloc and parsed.netloc.endswith(domain) and any(
                            term in (target + " " + href).casefold() for term in
                            ("three-piece", "three-piece", "threepiece", "3-piece", "3-piece", "salwar", "kameez")
                        ):
                            relevant.append(target)
                    for target in list(dict.fromkeys(relevant))[:5]:
                        if target in visited or pages_checked >= 65:
                            continue
                        visited.add(target)
                        pages_checked += 1
                        try:
                            req2 = _Request(target, headers={"User-Agent":"Mozilla/5.0 (compatible; FayezShopCatalogue/1.0)"})
                            with _urlopen(req2, timeout=7) as response2:
                                raw2 = response2.read(1_500_000)
                                charset2 = response2.headers.get_content_charset() or "utf-8"
                            html2 = raw2.decode(charset2, errors="replace")
                            p2 = _FayezJSONLDParser(); p2.feed(html2)
                            for item in _fayez_extract_products(target, source_name, html2, p2):
                                key = (item["name"].casefold(), round(item["price"], 2))
                                collected.setdefault(key, item)
                        except Exception:
                            continue
            except Exception:
                continue
    return list(collected.values()), pages_checked

_previous_fayez_three_piece_init_db = init_db
def init_db():
    """Initialize local SQLite data without depending on retailer websites.

    Network catalogue imports are intentionally excluded from startup so a slow
    or unavailable supplier site cannot block the storefront. Existing database
    rows are retained by the original additive initialization/migration routine.
    """
    _previous_fayez_three_piece_init_db()
    print("Three-Piece catalogue: automatic online import skipped during startup.")


# Fayez premium visual/category refresh + clearly marked starter catalogue.
_previous_fayez_visual_init_db = init_db
def init_db():
    _previous_fayez_visual_init_db()
    with app.app_context():
        db = get_db()
        db.execute("INSERT OR IGNORE INTO categories(name, slug, image) VALUES(?,?,?)",
                   ('Three-Piece', 'three-piece', 'https://images.unsplash.com/photo-1610030469983-98e550d6193c?w=1000&auto=format&fit=crop&q=90'))
        db.execute("UPDATE categories SET name=?, image=? WHERE slug='three-piece'",
                   ('Three-Piece', 'https://images.unsplash.com/photo-1610030469983-98e550d6193c?w=1000&auto=format&fit=crop&q=90'))
        cat = db.execute("SELECT id FROM categories WHERE slug='three-piece'").fetchone()
        if cat:
            starter_items = [
              ('FZ-TP-PREVIEW-001','Printed Lawn Three-Piece — Design Preview',1290,'https://images.unsplash.com/photo-1610030469983-98e550d6193c?w=900&auto=format&fit=crop&q=85'),
              ('FZ-TP-PREVIEW-002','Embroidered Three-Piece — Design Preview',1890,'https://images.unsplash.com/photo-1583391733956-3750e0ff4e8b?w=900&auto=format&fit=crop&q=85'),
              ('FZ-TP-PREVIEW-003','Traditional Three-Piece — Design Preview',2490,'https://images.unsplash.com/photo-1617627143750-d86bc21e42bb?w=900&auto=format&fit=crop&q=85'),
            ]
            for sku, name, price, image_url in starter_items:
                if not db.execute('SELECT 1 FROM products WHERE sku=?',(sku,)).fetchone():
                    db.execute("""INSERT INTO products
                      (name,sku,category_id,price,old_price,discount_percent,stock,country_of_origin,colors,description,image,image2,image3,is_flash_sale,brand,source_url)
                      VALUES(?,?,?,?,NULL,0,0,'Not verified','As shown',?,?,?,?,0,'Fayez Shop — Preview','')""",
                      (name,sku,cat['id'],price,
                       'ডিজাইন প্রিভিউ মাত্র। কাপড়, সাইজ, সরবরাহকারী, আসল পণ্যের ছবি ও বিক্রয়মূল্য যাচাই না হওয়া পর্যন্ত অর্ডার/স্টক নিশ্চিত নয়।',
                       image_url,'',''))
        mens = db.execute("SELECT id FROM categories WHERE slug='mens-fashion'").fetchone()
        if mens and not db.execute("SELECT 1 FROM products WHERE sku='FZ-TSHIRT-PREVIEW-001'").fetchone():
            db.execute("""INSERT INTO products
              (name,sku,category_id,price,old_price,discount_percent,stock,country_of_origin,colors,description,image,image2,image3,is_flash_sale,brand,source_url)
              VALUES(?,?,?,?,NULL,0,0,'Not verified','Black / White',?,?,?,?,0,'Fayez Shop — Preview','')""",
              ('Premium Cotton Crew-Neck T-Shirt','FZ-TSHIRT-PREVIEW-001',mens['id'],650,
               'ডিজাইন প্রিভিউ মাত্র। ব্র্যান্ড, কাপড় ও সরবরাহকারীর তথ্য যাচাই করা হয়নি; বিক্রির আগে নিশ্চিত করুন।',
               'https://images.unsplash.com/photo-1521572163474-6864f9cf17ab?w=900&auto=format&fit=crop&q=85','',''))
        db.commit()


# Additive Vaseline + Minoxidil catalogue. Existing products/orders/customers are preserved.
_previous_catalogue_init_db = init_db
def init_db():
    _previous_catalogue_init_db()
    with app.app_context():
        db = get_db()
        # Dedicated shelves, without deleting or renaming existing categories.
        db.execute("INSERT OR IGNORE INTO categories(name,slug,image) VALUES(?,?,?)",
                   ('Vaseline Health Care','vaseline-health-care','https://www.rokomari.com/brand/12713'))
        db.execute("INSERT OR IGNORE INTO categories(name,slug,image) VALUES(?,?,?)",
                   ('Minoxidil Hair Care','minoxidil-hair-care','https://medex.com.bd/generics/761/minoxidil/bn'))
        vas_cat = db.execute("SELECT id FROM categories WHERE slug='vaseline-health-care'").fetchone()['id']
        min_cat = db.execute("SELECT id FROM categories WHERE slug='minoxidil-hair-care'").fetchone()['id']
        vaseline = [
          ('Vaseline Original Healing Petroleum Jelly 250ml',879,'FZ-VAS-001','https://www.rokomari.com/brand/12713'),
          ('Vaseline Lip Therapy Rosy Lips 20g',189,'FZ-VAS-002','https://www.rokomari.com/brand/12713'),
          ('Vaseline Lip Therapy Cocoa Butter 20g',279,'FZ-VAS-003','https://www.rokomari.com/brand/12713'),
          ('Vaseline Cocoa Butter Petroleum Jelly 100ml',319,'FZ-VAS-004','https://www.rokomari.com/brand/12713'),
          ('Vaseline Lip Therapy Original 20g',250,'FZ-VAS-005','https://www.rokomari.com/brand/12713'),
          ('Vaseline Blueseal Original Petroleum Jelly 100ml',399,'FZ-VAS-006','https://www.rokomari.com/brand/12713'),
          ('Vaseline Blueseal Original Petroleum Jelly 50ml',239,'FZ-VAS-007','https://www.rokomari.com/brand/12713'),
          ('Vaseline Hair Tonic and Scalp Conditioner 300ml',771,'FZ-VAS-008','https://www.rokomari.com/brand/12713'),
          ('Vaseline Lip Therapy Aloe Vera Stick 4.8g',225,'FZ-VAS-009','https://www.rokomari.com/brand/12713'),
          ('Vaseline Men Cooling 48H Body Cream 400ml',950,'FZ-VAS-010','https://www.rokomari.com/brand/12713'),
          ('Vaseline Lip Care Rosy Lips Stick 4.8g',220,'FZ-VAS-011','https://www.rokomari.com/brand/12713'),
          ('Vaseline Lip Therapy Aloe 20g',272,'FZ-VAS-012','https://www.rokomari.com/brand/12713'),
          ('Vaseline Lip Therapy Jelly 20g',311,'FZ-VAS-013','https://www.rokomari.com/brand/12713'),
          ('Vaseline Blueseal Baby Protective Jelly 50ml',350,'FZ-VAS-014','https://www.rokomari.com/brand/12713'),
          ('Vaseline Blueseal Cocoa Butter Jelly 50ml',269,'FZ-VAS-015','https://www.rokomari.com/brand/12713'),
          ('Vaseline Intensive Care Cocoa Radiant Lotion 200ml',699,'FZ-VAS-016','https://www.rokomari.com/brand/12713'),
          ('Vaseline Intensive Care Cocoa Glow Lotion 400ml',968,'FZ-VAS-017','https://www.rokomari.com/brand/12713'),
          ('Vaseline Intensive Care Deep Moisture Serum Lotion 400ml',1099,'FZ-VAS-018','https://www.rokomari.com/brand/12713'),
          ('Vaseline Advanced Repair Body Lotion 400ml',1490,'FZ-VAS-019','https://www.rokomari.com/brand/12713'),
          ('Vaseline Intensive Care Aloe Soothe Lotion 400ml',1159,'FZ-VAS-020','https://www.rokomari.com/brand/12713'),
        ]
        # Bangladesh-listed Minoxidil brands and strengths; only distinct brand-strength SKUs.
        minoxidil = [
          ('Trugain Minoxidil 2% Scalp Solution 60ml',450,'FZ-MIN-001'),
          ('Trugain Minoxidil 5% Scalp Solution 60ml',550,'FZ-MIN-002'),
          ('Grow Hair Minoxidil 2% Scalp Solution 60ml',500,'FZ-MIN-003'),
          ('Grow Hair Minoxidil 5% Scalp Solution 60ml',600,'FZ-MIN-004'),
          ('Hairgain Minoxidil 2% Scalp Solution 60ml',500,'FZ-MIN-005'),
          ('Hairgain Minoxidil 5% Scalp Solution 60ml',600,'FZ-MIN-006'),
          ('Hairgrow Minoxidil 2% Scalp Solution 60ml',500,'FZ-MIN-007'),
          ('Hairgrow Minoxidil 5% Scalp Solution 60ml',600,'FZ-MIN-008'),
          ('Minoxil Minoxidil 2% Scalp Solution 60ml',500,'FZ-MIN-009'),
          ('Minoxil Minoxidil 5% Scalp Solution 60ml',600,'FZ-MIN-010'),
          ('Regain Minoxidil 2% Scalp Solution 60ml',500,'FZ-MIN-011'),
          ('Regain Minoxidil 5% Scalp Solution 60ml',600,'FZ-MIN-012'),
          ('Regenox Minoxidil 5% Scalp Solution 60ml',600,'FZ-MIN-013'),
          ('Regrow Minoxidil 2% Scalp Solution 60ml',175,'FZ-MIN-014'),
          ('Splendora Minoxidil 2% Scalp Solution 60ml',501.50,'FZ-MIN-015'),
          ('Splendora Minoxidil 5% Scalp Solution 60ml',601.81,'FZ-MIN-016'),
          ('Xenogrow Minoxidil 2% Scalp Solution 60ml',500,'FZ-MIN-017'),
          ('Xenogrow Minoxidil 5% Scalp Solution 60ml',600,'FZ-MIN-018'),
        ]
        # Image URLs point to the product-brand catalogue pages for now; replace with
        # each SKU's direct pack-shot image URL after image-source verification.
        for name,price,sku,src in vaseline:
            db.execute("""INSERT OR IGNORE INTO products
              (name,sku,category_id,price,old_price,discount_percent,stock,country_of_origin,colors,description,image,image2,image3,is_flash_sale,brand,source_url)
              VALUES(?,?,?,?,NULL,0,0,'As listed by retailer','As shown',?,?, '', '',0,'Vaseline',?)""",
              (name,sku,vas_cat,price,'Retailer-listed reference price; verify current price and supplier before sale.',
               'https://images.unsplash.com/photo-1608248543803-ba4f8c70ae0b?w=900&auto=format&fit=crop&q=90',src))
        for name,price,sku in minoxidil:
            db.execute("""INSERT OR IGNORE INTO products
              (name,sku,category_id,price,old_price,discount_percent,stock,country_of_origin,colors,description,image,image2,image3,is_flash_sale,brand,source_url)
              VALUES(?,?,?,?,NULL,0,0,'Bangladesh','60ml bottle',?,?, '', '',0,'Minoxidil',?)""",
              (name,sku,min_cat,price,'Minoxidil is a medicine. Use only with registered physician/pharmacist advice; confirm supplier and current price before sale.',
               'https://medex.com.bd/storage/images/packaging/minoxil-2-scalp-solution-92466802760-i1-7m702bzAnTO4QTLjX47b.jpg',
               'https://medex.com.bd/generics/761/minoxidil/bn'))
        # Never manufacture inventory. Stock changes only when the shop owner enters it.
        db.commit()


# Additive Laavish Daraz furniture catalogue. Existing customer/order data is untouched.
_previous_laavish_init_db = init_db
def init_db():
    _previous_laavish_init_db()
    with app.app_context():
        db = get_db()
        db.execute("INSERT OR IGNORE INTO categories(name,slug,image) VALUES(?,?,?)",
                   ('Laavish Furniture','laavish-furniture','https://images.unsplash.com/photo-1555041469-a586c61ea9bc?w=900&auto=format&fit=crop&q=85'))
        cat = db.execute("SELECT id FROM categories WHERE slug='laavish-furniture'").fetchone()['id']
        # Prices are the Daraz listing prices seen during catalogue preparation; they can change.
        # Product page links are retained as source references. Daraz did not expose stable
        # direct pack-shot URLs in the page results, so image is intentionally blank rather
        # than falsely assigning an unrelated photo to each product.
        items = [
          ('Laavish LED Dressing Table 10 LED Lights',8430,'FZ-LAV-001','https://www.daraz.com.bd/shop/l6jclpbs/?channelSource=pdp&itemId=345556292','ড্রেসিং টেবিল; ১০টি LED লাইট। Daraz স্টোর তালিকার মূল্য।'),
          ('Laavish 2 Door Almira 30in x 6ft x 16in',7890,'FZ-LAV-002','https://www.daraz.com.bd/products/laavish-2-door-almira-length-30inch-height-6ft-depth-16inch-i542590247.html','২-ডোর আলমিরা; ৩০ ইঞ্চি দৈর্ঘ্য, ৬ ফুট উচ্চতা, ১৬ ইঞ্চি গভীরতা; Particle Board.'),
          ('Laavish 2 Door Almira 3ft x 6ft x 1ft',6765,'FZ-LAV-003','https://www.daraz.com.bd/products/laavish-2-door-almira-length-3ft-height-6ft-depth-1ft-i542589251.html','২-ডোর আলমিরা; ৩ ফুট দৈর্ঘ্য, ৬ ফুট উচ্চতা, ১ ফুট গভীরতা।'),
          ('Laavish Classic 3 Door Almira 4ft x 6ft x 16in',14680,'FZ-LAV-004','https://www.daraz.com.bd/products/-i560913793.html','৩-ডোর আলমিরা; ৪ ফুট দৈর্ঘ্য, ৬ ফুট উচ্চতা, ১৬ ইঞ্চি গভীরতা; Particle Board.'),
          ('Laavish Simple 2 Door Almira',5299,'FZ-LAV-005','https://www.daraz.com.bd/products/2-i344845666.html','সিম্পল ২-ডোর আলমিরা; Daraz তালিকার মূল্য।'),
          ('Laavish Computer Study Table Workstation 42/54',4924,'FZ-LAV-006','https://www.daraz.com.bd/products/laavish-4254-i542218847.html','কম্পিউটার/স্টাডি টেবিল ও মাল্টিপারপাস ওয়ার্কস্টেশন; Partex Board.'),
          ('Laavish Bedside Table with Drawer and Bed Box',1397,'FZ-LAV-007','https://www.daraz.com.bd/products/laavish-bed-side-table-bed-box-i367266076.html','বেডসাইড টেবিল; ড্রয়ারসহ; Melamine MDF laminated board.'),
          ('Laavish Bedside Corner Table',1350,'FZ-LAV-008','https://www.daraz.com.bd/products/laavish-bed-side-table-corner-table-i542611236.html','বেডসাইড/কর্নার টেবিল; একাধিক রঙের অপশন তালিকাভুক্ত।'),
          ('Laavish Antique Colour Bedside Table',1490,'FZ-LAV-009','https://www.daraz.com.bd/products/lavish-bed-side-table-antique-colour-i342706597-s1865937084.html','অ্যান্টিক রঙের বেডসাইড টেবিল; Melamine; ১টি ড্রয়ার।'),
          ('Laavish Side Table',1680,'FZ-LAV-010','https://www.daraz.com.bd/products/lavish-side-table-i542584256.html','সাইড টেবিল; Melamine; রঙের বিকল্প তালিকাভুক্ত।'),
          ('Laavish Wall Decoration Shelf 2ft x 2ft',1190,'FZ-LAV-011','https://www.daraz.com.bd/products/2-2-i355301119.html','ওয়াল ডেকোরেশন/শো-পিস শেলফ; ২ ফুট × ২ ফুট; Melamine.'),
        ]
        for name, price, sku, source, description in items:
            exists = db.execute('SELECT 1 FROM products WHERE sku=? OR (name=? AND category_id=?)', (sku,name,cat)).fetchone()
            if exists:
                continue
            db.execute("""INSERT INTO products
              (name,sku,category_id,price,old_price,discount_percent,stock,country_of_origin,colors,description,image,image2,image3,is_flash_sale,brand,source_url)
              VALUES(?,?,?,?,NULL,0,0,'As listed by Daraz','As listed',?,'','','',0,'Laavish',?)""",
              (name,sku,cat,price,description,source))
        db.commit()


# Final user-requested catalogue selection:
# Keep exactly one Vaseline and one Minoxidil catalogue item, preserve all other
# existing products/orders/customers, and leave Himalaya seeding disabled.
_previous_user_catalog_init_db = init_db
def init_db():
    _previous_user_catalog_init_db()
    with app.app_context():
        db = get_db()
        # Make a private SQLite backup before the explicitly requested catalogue cleanup.
        backup_dir = Path(app.root_path) / 'private_backups'
        backup_dir.mkdir(mode=0o700, exist_ok=True)
        backup_path = backup_dir / ('before-catalogue-cleanup-' + datetime.now().strftime('%Y%m%d-%H%M%S') + '.db')
        backup_db = sqlite3.connect(str(backup_path))
        try:
            db.backup(backup_db)
        finally:
            backup_db.close()
        try:
            backup_path.chmod(0o600)
        except OSError:
            pass

        # Retain one representative product from each requested brand.
        # Other records with these importer SKUs are removed; unrelated catalogue rows remain.
        db.execute("DELETE FROM products WHERE sku LIKE 'FZ-VAS-%' AND sku <> 'FZ-VAS-001'")
        db.execute("DELETE FROM products WHERE sku LIKE 'FZ-MIN-%' AND sku <> 'FZ-MIN-001'")
        db.commit()



# Additive Daraz Himalaya catalogue import (verified search listings, 2026-11-16).
# This importer ONLY inserts missing rows. It never updates or deletes existing products.
# Daraz listing prices are snapshots and may change; original image URLs were not
# exposed reliably by the indexed store pages, so image is intentionally left blank.
_FAYEZ_DARAZ_HIMALAYA_VERIFIED = [
    ("Himalaya Cocoa Butter Intensive Body Lotion Pump 400ml", 299, "skincare"),
    ("Himalaya Nourishing Skin Cream 100ml", 192, "skincare"),
    ("Himalaya Cocoa Butter Intensive Body Lotion 200 ml with Nourishing Skin Cream 50 ml", 266, "skincare"),
    ("Himalaya Head To Toe Gentle 2 in 1 Wash - 200ml", 163, "personal-care-grooming"),
    ("Himalaya Clear Complexion Brightening Body Lotion Pump 400ml", 289, "skincare"),
    ("Himalaya Natural Glow Saffron Face Cream 50gm (Get Natural Glow Saffron Face Cream 25gm FREE)", 160, "skincare"),
    ("Himalaya Dark Spot Clearing Turmeric Face Wash 100ml", 124, "skincare"),
    ("Himalaya Gentle Daily Care Natural Protein Shampoo 170ml", 135, "hair-care"),
    ("Himalaya Men Power Bright Licorice Face Wash 100 ml (Buy 1 Get 1 FREE)", 295, "skincare"),
    ("Himalaya Cocoa Butter Intensive Body Lotion Pump 400ml (Buy 1 Get 1 FREE)", 599, "skincare"),
    ("Himalaya Purifying Neem Face Serum 15ml", 199, "skincare"),
    ("Himalaya Moisturizing Aloe vera Face Wash 100ml (Buy 1 Get 1 Free)", 219, "skincare"),
    ("Himalaya Clear Complexion Body Lotion 200ml with Nourishing Skin Cream 50 ml", 281, "skincare"),
    ("Himalaya Brightening Vitamin C Face Wash 100ml Pack Of 3", 303, "skincare"),
    ("Himalaya Brightening Vitamin C Orange Face Wash 100ml (Buy 1 Get 1 Free)", 213, "skincare"),
    ("Himalaya Natural Glow Rose Face Cream 50gm", 111, "skincare"),
    ("Himalaya Brightening Vitamin C Orange Face Serum 30ml", 350, "skincare"),
    ("Himalaya Dark Spot Clearing Turmeric Serum 30ml", 350, "skincare"),
    ("Himalaya Oil Clear Lemon Face Wash 100ml (Buy 1 Get 1 Free)", 199, "skincare"),
    ("Himalaya Anti Hair Fall Bhringaraja Shampoo 170ml (Buy 1 Get 1 FREE)", 270, "hair-care"),
    ("Himalaya Dark Spot Turmeric Face Wash 100ml (Buy 1 Get 1 Free)", 223, "skincare"),
    ("Himalaya Clear Complexion Brightening Body Lotion Pump 400ml (Buy 1 Get 1 FREE)", 599, "skincare"),
    ("Himalaya Men Acne Clear Neem Face Wash 50ml", 98, "skincare"),
    ("Himalaya Dark Spot Clearing Turmeric Gel Cream 40gm", 250, "skincare"),
    ("Himalaya Baby Cream 50gm", 109, "baby-products"),
    ("Himalaya Baby Powder 100gm", 111, "baby-products"),
    ("Himalaya Purifying Neem Clay Stick Mask 30gm", 386, "skincare"),
    ("Himalaya Anti Dandruff Tea Tree Shampoo 170ml (Buy 1 Get 1 FREE)", 265, "hair-care"),
    ("Himalaya Anti Dandruff Shampoo Soothing & Moisturizing 375ml and Anti Hair Fall Shampoo 375ml Combo Pack", 442, "hair-care"),
    ("Himalaya Prickly Heat Powder 100gm", 0, "personal-care-grooming"),
]

def _fayez_add_verified_daraz_himalaya():
    db = get_db()
    added = 0
    source = 'https://www.daraz.com.bd/tag/himalaya-products/'
    source2 = 'https://www.daraz.com.bd/tag/himalaya-items/'
    for index, (name, price, category_slug) in enumerate(_FAYEZ_DARAZ_HIMALAYA_VERIFIED, 1):
        # A zero price means the indexed Daraz snippet did not expose a price;
        # skip it rather than inventing one.
        if not price:
            continue
        sku = 'FZ-DARAZ-HIM26-%03d' % index
        exists = db.execute('SELECT id FROM products WHERE sku=? OR (LOWER(name)=LOWER(?) AND COALESCE(brand,\'\')=\'Himalaya\')', (sku, name)).fetchone()
        if exists:
            continue
        cat = db.execute('SELECT id FROM categories WHERE slug=?', (category_slug,)).fetchone()
        if not cat:
            # Keep import safe if a category was renamed; use an existing skincare category.
            cat = db.execute('SELECT id FROM categories WHERE slug IN (\'skincare\',\'personal-care-grooming\') ORDER BY CASE slug WHEN \'skincare\' THEN 0 ELSE 1 END LIMIT 1').fetchone()
        if not cat:
            continue
        listing = source2 if index >= 25 else source
        description = (
            f'{name}. Daraz Bangladesh indexed listing price snapshot: ৳{price:,} on 2026-11-16. '
            'This is not a guaranteed live price or stock status. Verify current Daraz seller listing, '
            'pack size, authenticity and availability before accepting an order. '
            'Original product image was not reliably available from the indexed listing and must be '
            'added from the matching Daraz product page by the shop owner.'
        )
        db.execute('''INSERT INTO products
          (name, sku, category_id, price, old_price, discount_percent, stock, country_of_origin,
           colors, description, image, image2, image3, is_flash_sale, brand, source_url, source_checked_at)
          VALUES (?, ?, ?, ?, NULL, 0, 0, 'As labelled on original pack', 'As shown on original pack', ?, '', '', '', 0,
                  'Himalaya', ?, '2026-11-16')''',
          (name, sku, cat['id'], price, description, listing))
        added += 1
    db.commit()
    return added

_previous_daraz_himalaya_init_db = init_db
def init_db():
    _previous_daraz_himalaya_init_db()
    with app.app_context():
        count = _fayez_add_verified_daraz_himalaya()
        if count:
            print(f'Daraz Himalaya catalogue: added {count} new products; existing products preserved.')



# Count customer-facing page visits for authenticated customers. No IP/device fingerprinting.
@app.before_request
def _fayez_count_customer_page_visit():
    try:
        if request.method == 'GET' and session.get('customer_id') and request.endpoint not in (None, 'static') and not request.path.startswith('/admin') and not request.path.startswith('/search/suggest'):
            _fayez_track_customer_event('site_visit', None, request.path[:200])
    except Exception:
        pass

# Initialize analytics after the existing additive product/catalogue migrations.
_fayez_init_before_analytics = init_db
def init_db():
    _fayez_init_before_analytics()
    with app.app_context(): _fayez_init_customer_activity()

@app.route('/admin/customers')
@admin_required
def admin_customers():
    db=get_db()
    total=db.execute("SELECT COUNT(*) FROM customers").fetchone()[0]
    active=db.execute("SELECT COUNT(DISTINCT customer_id) FROM customer_activity WHERE date(created_at)=date('now','localtime')").fetchone()[0]
    customers=db.execute("SELECT c.id,c.name,c.email,c.phone,c.is_verified,(SELECT COUNT(*) FROM customer_activity a WHERE a.customer_id=c.id AND a.event_type='login') login_count,(SELECT MAX(created_at) FROM customer_activity a WHERE a.customer_id=c.id) last_activity,(SELECT COUNT(*) FROM orders o WHERE o.customer_id=c.id) order_count FROM customers c ORDER BY c.id DESC").fetchall()
    body="""<div class="container-fluid py-4"><div class="d-flex justify-content-between flex-wrap gap-3 mb-4"><div><small class="text-secondary">CUSTOMER INTELLIGENCE</small><h2 class="fw-bold">Customer Management</h2></div><a href="/admin/dashboard" class="btn btn-outline-dark rounded-pill">← Dashboard</a></div><div class="row g-3 mb-4"><div class="col-md-6"><div class="card border-0 shadow-sm rounded-4 p-4">মোট রেজিস্টার্ড কাস্টমার<div class="display-6 fw-bold">{{ total }}</div></div></div><div class="col-md-6"><div class="card border-0 shadow-sm rounded-4 p-4">আজ সক্রিয় কাস্টমার<div class="display-6 fw-bold text-success">{{ active }}</div></div></div></div><div class="card border-0 shadow-sm rounded-4 p-3"><div class="d-flex justify-content-between flex-wrap gap-2 mb-3"><h5>কাস্টমার তালিকা</h5><input id="customerFilter" class="form-control" style="max-width:320px" placeholder="নাম, ইমেইল বা ফোন খুঁজুন"></div><div class="table-responsive"><table class="table align-middle" id="customerTable"><thead><tr><th>কাস্টমার</th><th>ফোন</th><th>লগইন</th><th>অর্ডার</th><th>সর্বশেষ অ্যাক্টিভিটি</th><th></th></tr></thead><tbody>{% for c in customers %}<tr><td><b>{{ c.name }}</b><div class="small text-secondary">{{ c.email }}</div></td><td>{{ c.phone or '—' }}</td><td>{{ c.login_count }}</td><td>{{ c.order_count }}</td><td>{{ c.last_activity or 'এখনো নেই' }}</td><td><a class="btn btn-sm btn-dark rounded-pill" href="/admin/customer/{{ c.id }}">View Activity</a></td></tr>{% else %}<tr><td colspan="6">কোনো কাস্টমার নেই।</td></tr>{% endfor %}</tbody></table></div></div><p class="small text-secondary mt-3">কাস্টমারের পাসওয়ার্ড বা OTP কখনো দেখানো হয় না।</p></div><script>document.getElementById('customerFilter').addEventListener('input',function(){let q=this.value.toLowerCase();document.querySelectorAll('#customerTable tbody tr').forEach(r=>r.style.display=r.innerText.toLowerCase().includes(q)?'':'none')});</script>"""
    return render_template_string(BASE_HTML.replace('{% block content %}{% endblock %}',body),customers=customers,total=total,active=active)

@app.route('/admin/customer/<int:customer_id>')
@admin_required
def admin_customer_activity(customer_id):
    db=get_db()
    customer=db.execute("SELECT id,name,email,phone,is_verified FROM customers WHERE id=?",(customer_id,)).fetchone()
    if not customer:
        flash('কাস্টমার পাওয়া যায়নি।','warning')
        return redirect(url_for('admin_customers'))
    events=db.execute("SELECT a.*,p.name product_name,p.image product_image,c.name category_name FROM customer_activity a LEFT JOIN products p ON p.id=a.product_id LEFT JOIN categories c ON c.id=p.category_id WHERE a.customer_id=? ORDER BY a.id DESC LIMIT 500",(customer_id,)).fetchall()
    wishlist=db.execute("SELECT p.name,p.price,p.image FROM wishlists w JOIN products p ON p.id=w.product_id WHERE w.customer_id=? ORDER BY w.id DESC",(customer_id,)).fetchall()
    cart=db.execute("SELECT p.name,p.price,p.image,ca.quantity FROM cart ca JOIN products p ON p.id=ca.product_id WHERE ca.customer_id=?",(customer_id,)).fetchall()
    orders=db.execute("SELECT id,order_id,total_amount,order_status,created_at FROM orders WHERE customer_id=? ORDER BY id DESC",(customer_id,)).fetchall()
    counts=db.execute("SELECT event_type,COUNT(*) n FROM customer_activity WHERE customer_id=? GROUP BY event_type",(customer_id,)).fetchall()
    login=db.execute("SELECT COUNT(*) n,MAX(created_at) last_login FROM customer_activity WHERE customer_id=? AND event_type='login'",(customer_id,)).fetchone()
    visits=db.execute("SELECT COUNT(*) FROM customer_activity WHERE customer_id=? AND event_type='site_visit'",(customer_id,)).fetchone()[0]
    total_product_views=db.execute("SELECT COUNT(*) FROM customer_activity WHERE customer_id=? AND event_type='product_view'",(customer_id,)).fetchone()[0]
    product_views=db.execute("SELECT p.id,p.name,p.image,c.name category_name,COUNT(*) views,MAX(a.created_at) last_view FROM customer_activity a JOIN products p ON p.id=a.product_id LEFT JOIN categories c ON c.id=p.category_id WHERE a.customer_id=? AND a.event_type='product_view' GROUP BY p.id,p.name,p.image,c.name ORDER BY views DESC,last_view DESC",(customer_id,)).fetchall()
    categories=db.execute("SELECT COALESCE(c.name,'অন্যান্য') category_name,COUNT(*) views FROM customer_activity a LEFT JOIN products p ON p.id=a.product_id LEFT JOIN categories c ON c.id=p.category_id WHERE a.customer_id=? AND a.event_type='product_view' GROUP BY c.name ORDER BY views DESC",(customer_id,)).fetchall()
    searches=db.execute("SELECT detail,created_at,event_type FROM customer_activity WHERE customer_id=? AND event_type IN ('search','search_no_results') ORDER BY id DESC LIMIT 100",(customer_id,)).fetchall()
    spent=db.execute("SELECT COALESCE(SUM(total_amount),0) FROM orders WHERE customer_id=? AND COALESCE(order_status,'') NOT IN ('Cancelled','Returned','Refunded')",(customer_id,)).fetchone()[0]
    labels={'product_view':'পণ্য দেখা','search':'সার্চ','search_no_results':'সার্চে পণ্য পাওয়া যায়নি','shop_filter':'ক্যাটাগরি/ফিল্টার দেখা','cart_add':'কার্টে যোগ','cart_remove':'কার্ট থেকে সরানো','buy_now':'Buy Now','wishlist_add':'Wishlist-এ যোগ','wishlist_remove':'Wishlist থেকে সরানো','login':'লগইন','order_placed':'অর্ডার করা হয়েছে','order_status_changed':'অর্ডারের স্ট্যাটাস পরিবর্তন','site_visit':'ওয়েবসাইট ভিজিট'}
    body="""<div class='container-fluid py-4'><a href='/admin/customers' class='btn btn-sm btn-outline-secondary mb-3'>← সব কাস্টমার</a><div class='card border-0 shadow-sm rounded-4 p-4 mb-3'><small class='text-secondary'>CUSTOMER PROFILE</small><h2 class='fw-bold mb-1'>{{ customer.name }}</h2><div>{{ customer.email }} · {{ customer.phone or 'ফোন নেই' }}</div><div class='row g-3 mt-2'><div class='col-6 col-md-3'><div class='bg-light rounded-3 p-3'>মোট লগইন <b class='fs-3 d-block'>{{ login.n }}</b></div></div><div class='col-6 col-md-3'><div class='bg-light rounded-3 p-3'>ওয়েবসাইট ভিজিট <b class='fs-3 d-block'>{{ visits }}</b></div></div><div class='col-6 col-md-3'><div class='bg-light rounded-3 p-3'>সর্বশেষ লগইন <b class='d-block'>{{ login.last_login or 'রেকর্ড নেই' }}</b></div></div><div class='col-6 col-md-3'><div class='bg-light rounded-3 p-3'>নেট অর্ডার খরচ <b class='fs-4 d-block'>৳{{ '%.0f'|format(spent) }}</b></div></div></div></div><div class='row g-3'><div class='col-xl-7'><div class='card border-0 shadow-sm rounded-4 p-3 mb-3'><h5>Product View Tracking</h5><p class='small text-secondary'>মোট {{ total_product_views }} বার পণ্য দেখা · {{ product_views|length }}টি আলাদা পণ্য</p>{% for p in product_views %}<div class='d-flex align-items-center gap-3 border-bottom py-2'>{% if p.image %}<img src='{{ p.image }}' style='width:58px;height:58px;object-fit:contain;border-radius:9px;background:#f7f7f9'>{% endif %}<div class='flex-grow-1'><b>{{ p.name }}</b><div class='small text-secondary'>{{ p.category_name or 'অন্যান্য' }} · সর্বশেষ: {{ p.last_view }}</div></div><span class='badge bg-primary'>{{ p.views }} বার</span></div>{% else %}<p>এখনো পণ্য দেখা হয়নি।</p>{% endfor %}</div><div class='card border-0 shadow-sm rounded-4 p-3 mb-3'><h5>Search History</h5>{% for q in searches %}<div class='border-bottom py-2'><b>{{ q.detail }}</b><span class='badge {{ 'bg-danger' if q.event_type=='search_no_results' else 'bg-secondary' }} ms-2'>{{ labels.get(q.event_type,q.event_type) }}</span><small class='text-secondary d-block'>{{ q.created_at }}</small></div>{% else %}<p>সার্চ হিস্ট্রি নেই।</p>{% endfor %}</div><div class='card border-0 shadow-sm rounded-4 p-3'><h5>Activity Timeline</h5>{% for e in events %}<div class='border-bottom py-2'><b>{{ labels.get(e.event_type,e.event_type) }}</b><small class='text-secondary float-end'>{{ e.created_at }}</small>{% if e.product_name %}<div class='d-flex align-items-center gap-2 mt-1'>{% if e.product_image %}<img src='{{ e.product_image }}' style='width:38px;height:38px;object-fit:contain'>{% endif %}<span>{{ e.product_name }} · {{ e.category_name or '' }}</span></div>{% endif %}{% if e.detail %}<small class='text-secondary'>{{ e.detail }}</small>{% endif %}</div>{% else %}<p>এখনো কোনো অ্যাক্টিভিটি রেকর্ড হয়নি।</p>{% endfor %}</div></div><div class='col-xl-5'><div class='card border-0 shadow-sm rounded-4 p-3 mb-3'><h5>কোন ক্যাটাগরি বেশি দেখেছে</h5>{% for c in categories %}<div class='d-flex justify-content-between py-2 border-bottom'><span>{{ c.category_name }}</span><b>{{ c.views }} বার</b></div>{% else %}<p>ক্যাটাগরি ডেটা নেই।</p>{% endfor %}</div><div class='card border-0 shadow-sm rounded-4 p-3 mb-3'><h5>Wishlist</h5>{% for p in wishlist %}<div class='d-flex align-items-center gap-2 py-2'>{% if p.image %}<img src='{{ p.image }}' style='width:42px;height:42px;object-fit:contain'>{% endif %}<span>{{ p.name }} · ৳{{ '%.0f'|format(p.price) }}</span></div>{% else %}<p>Wishlist খালি।</p>{% endfor %}</div><div class='card border-0 shadow-sm rounded-4 p-3 mb-3'><h5>বর্তমান Cart</h5>{% for p in cart %}<div class='d-flex align-items-center gap-2 py-2'>{% if p.image %}<img src='{{ p.image }}' style='width:42px;height:42px;object-fit:contain'>{% endif %}<span>{{ p.name }} × {{ p.quantity }} · ৳{{ '%.0f'|format(p.price*p.quantity) }}</span></div>{% else %}<p>Cart খালি।</p>{% endfor %}</div><div class='card border-0 shadow-sm rounded-4 p-3'><h5>Shopping & Order History</h5>{% for o in orders %}<div class='border-bottom py-2'><b>{{ o.order_id }}</b><span class='badge bg-secondary float-end'>{{ o.order_status }}</span><div>৳{{ '%.0f'|format(o.total_amount) }} · {{ o.created_at }}</div></div>{% else %}<p>কোনো অর্ডার নেই।</p>{% endfor %}</div></div></div><p class='small text-secondary mt-3'>শুধু লগইন অবস্থায় শপিং-সংক্রান্ত পেজ ভিজিট রেকর্ড হয়। পাসওয়ার্ড, OTP, IP বা ব্যক্তিগত মেসেজ সংরক্ষণ করা হয় না।</p></div>"""
    return render_template_string(BASE_HTML.replace('{% block content %}{% endblock %}',body),customer=customer,events=events,wishlist=wishlist,cart=cart,orders=orders,counts=counts,labels=labels,login=login,visits=visits,total_product_views=total_product_views,product_views=product_views,categories=categories,searches=searches,spent=spent)

# Persist manually created categories while keeping auto-seeded extras hidden.
_previous_fayez_category_flag_init = init_db
def init_db():
    _previous_fayez_category_flag_init()
    with app.app_context():
        db = get_db()
        cols = {r['name'] for r in db.execute('PRAGMA table_info(categories)').fetchall()}
        if 'is_custom' not in cols:
            db.execute('ALTER TABLE categories ADD COLUMN is_custom INTEGER NOT NULL DEFAULT 0')
            db.commit()

# Final inventory integrity cleanup: remove the generated Gaming Pro / Hardware demo rows.
# These were fictional placeholders, not supplier-confirmed products or stock.
_previous_fayez_inventory_integrity_init = init_db
def init_db():
    _previous_fayez_inventory_integrity_init()
    with app.app_context():
        db = get_db()
        # Remove dependent non-order references first. Preserve order_items so past orders
        # remain auditable; any placeholder already used in an order is retained.
        fake_rows = db.execute("""
            SELECT id FROM products
            WHERE sku LIKE 'GM-PRO-%' OR sku LIKE 'TL-HW-%'
               OR name LIKE 'Gaming Pro Gear Item #%'
               OR name LIKE 'Heavy Duty Hardware Tool #%'
        """).fetchall()
        for row in fake_rows:
            pid = row['id']
            has_order = db.execute('SELECT 1 FROM order_items WHERE product_id=? LIMIT 1', (pid,)).fetchone()
            if has_order:
                continue
            for table, col in (('cart','product_id'),('wishlists','product_id'),('reviews','product_id'),('customer_activity','product_id')):
                try:
                    db.execute(f'DELETE FROM {table} WHERE {col}=?', (pid,))
                except Exception:
                    pass
            db.execute('DELETE FROM products WHERE id=?', (pid,))
        db.commit()


# Preserve the owner's existing catalogue, categories, customers and order history.
# The previous experimental one-time catalogue reset is disabled.
_previous_catalog_reset_init = init_db
def init_db():
    _previous_catalog_reset_init()


# Owner's final catalogue policy: retain only the approved category sequence through Laavish Furniture.
# Archived products are hidden from customers/admin inventory but their product rows remain for old order/profit history.
_previous_fayez_owner_catalog_policy_init = init_db
def init_db():
    _previous_fayez_owner_catalog_policy_init()
    with app.app_context():
        db = get_db()
        allowed = set(CURATED_CATEGORY_SLUGS)
        rows = db.execute("SELECT id,slug,name FROM categories").fetchall()
        removed_category_ids = []
        for row in rows:
            slug = (row['slug'] or '').strip().lower()
            if slug not in allowed:
                removed_category_ids.append(row['id'])
                db.execute("UPDATE products SET is_active=0, stock=0, category_id=NULL WHERE category_id=?", (row['id'],))
                db.execute("DELETE FROM categories WHERE id=?", (row['id'],))
        # Remove all Vaseline/Minoxidil catalogue entries and all Three-Piece preview products.
        # Product rows are retained inactive so past order items and profit reports remain auditable.
        db.execute("""UPDATE products SET is_active=0, stock=0, category_id=NULL
            WHERE sku LIKE 'FZ-VAS-%' OR sku LIKE 'FZ-MIN-%' OR sku LIKE 'FZ-TP-PREVIEW-%'
               OR LOWER(COALESCE(name,'')) LIKE '%vaseline%'
               OR LOWER(COALESCE(name,'')) LIKE '%minoxidil%'
               OR LOWER(COALESCE(brand,'')) IN ('vaseline','minoxidil')
               OR category_id IN (SELECT id FROM categories WHERE slug IN ('vaseline-health-care','minoxidil-hair-care','three-piece'))""")
        # These two special-purpose categories are not part of the approved category list.
        db.execute("DELETE FROM categories WHERE slug IN ('vaseline-health-care','minoxidil-hair-care')")
        # Remove stale cart entries for products that have just been archived.
        inactive_ids = [r['id'] for r in db.execute('SELECT id FROM products WHERE COALESCE(is_active,1)=0').fetchall()]
        if inactive_ids:
            marks = ','.join('?' for _ in inactive_ids)
            for table in ('cart','wishlists'):
                exists = db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)).fetchone()
                if exists:
                    try:
                        db.execute(f'DELETE FROM {table} WHERE product_id IN ({marks})', inactive_ids)
                    except sqlite3.Error:
                        pass
        db.commit()

@app.route('/admin/category/add', methods=['POST'])
@admin_required
def admin_add_category_owner():
    db = get_db()
    _ensure_category_admin_schema(db)
    name = (request.form.get('name') or request.form.get('category_name') or request.form.get('category') or '').strip()
    image = (request.form.get('image') or request.form.get('category_image') or request.form.get('image_url') or '').strip()
    if not name:
        flash('ক্যাটাগরির নাম লিখুন।', 'danger')
        return redirect('/admin/section/categories')
    if len(name) > 100:
        flash('ক্যাটাগরির নাম ১০০ অক্ষরের মধ্যে রাখুন।', 'danger')
        return redirect('/admin/section/categories')
    if db.execute('SELECT 1 FROM categories WHERE LOWER(TRIM(name))=LOWER(TRIM(?))', (name,)).fetchone():
        flash('এই নামে ক্যাটাগরি আগে থেকেই আছে।', 'warning')
        return redirect('/admin/section/categories')
    base = re.sub(r'[^a-z0-9]+', '-', name.lower()).strip('-') or 'category'
    slug, n = base, 2
    while db.execute('SELECT 1 FROM categories WHERE slug=?', (slug,)).fetchone():
        slug, n = f'{base}-{n}', n + 1
    try:
        db.execute('INSERT INTO categories(name,slug,image) VALUES(?,?,?)', (name,slug,image or None))
        db.commit()
        flash(f'“{name}” ক্যাটাগরি সফলভাবে যোগ হয়েছে।', 'success')
    except sqlite3.IntegrityError:
        db.rollback()
        flash('এই নামে ক্যাটাগরি আগে থেকেই আছে। অন্য নাম ব্যবহার করুন।', 'warning')
    except Exception:
        db.rollback()
        app.logger.exception('Category creation failed')
        flash('ক্যাটাগরি যোগ করা যায়নি। সার্ভারের টার্মিনালে error details দেখুন।', 'danger')
    return redirect('/admin/section/categories')


PREMIUM_ENTERPRISE_CSS = '\n<style id="fayez-premium-enterprise-v1">\n:root{\n  --fz-ink:#172033;--fz-muted:#667085;--fz-navy:#101828;--fz-purple:#6558ed;\n  --fz-purple-dark:#5145cd;--fz-gold:#d9a441;--fz-line:#e8ebf2;\n  --fz-canvas:#f6f7fb;--fz-card:#fff;--fz-radius:18px;\n}\nhtml{scroll-behavior:smooth;scroll-padding-top:90px}\nbody{background:var(--fz-canvas);color:var(--fz-ink);-webkit-font-smoothing:antialiased}\na{transition:color .18s ease,background-color .18s ease}\n::selection{background:rgba(101,88,237,.18);color:var(--fz-ink)}\n:focus-visible{outline:3px solid rgba(101,88,237,.42)!important;outline-offset:2px}\n.navbar.sticky-top{\n  background:rgba(255,255,255,.97)!important;backdrop-filter:blur(16px);\n  border-bottom:1px solid rgba(16,24,40,.08);box-shadow:0 8px 26px rgba(16,24,40,.055)!important\n}\n.navbar-brand{font-weight:900!important;letter-spacing:-.8px;color:var(--fz-navy)!important}\n.navbar-brand i{box-shadow:0 7px 18px rgba(101,88,237,.2)}\n.nav-link{font-weight:650!important;transition:color .18s ease,background .18s ease}\n.nav-link:hover,.nav-link:focus{color:var(--fz-purple)!important}\n.btn{font-weight:650;letter-spacing:-.01em;border-radius:12px;transition:transform .18s ease,box-shadow .18s ease,filter .18s ease}\n.btn-primary{background:linear-gradient(135deg,var(--fz-purple-dark),#8878f7)!important;border:0!important;box-shadow:0 7px 18px rgba(101,88,237,.18)!important}\n.btn-primary:hover{filter:brightness(1.05);transform:translateY(-1px);box-shadow:0 10px 22px rgba(101,88,237,.23)!important}\n.btn-outline-primary{border-color:#c9c4ff;color:var(--fz-purple-dark)}\n.btn-outline-primary:hover{background:var(--fz-purple-dark);border-color:var(--fz-purple-dark)}\n.form-control,.form-select,textarea{\n  border:1px solid #e1e5ee!important;border-radius:12px!important;min-height:44px;\n  box-shadow:none;transition:border-color .18s ease,box-shadow .18s ease\n}\n.form-control:focus,.form-select:focus,textarea:focus{\n  border-color:#958bfa!important;box-shadow:0 0 0 .22rem rgba(101,88,237,.12)!important\n}\n.card,.feature-card,.product-card,.category-box{\n  border:1px solid rgba(16,24,40,.075)!important;border-radius:var(--fz-radius)!important;\n  box-shadow:0 5px 20px rgba(16,24,40,.045)!important\n}\n.card{overflow:hidden}\n.product-card{background:#fff;transition:transform .22s ease,box-shadow .22s ease,border-color .22s ease!important}\n.product-card:hover{transform:translateY(-4px)!important;box-shadow:0 14px 30px rgba(16,24,40,.10)!important;border-color:rgba(101,88,237,.25)!important}\n.category-box:hover,.feature-card:hover{transform:translateY(-3px);box-shadow:0 12px 25px rgba(16,24,40,.085)!important}\n.section-title,h1,h2,h3,h4{color:var(--fz-ink);font-weight:750;letter-spacing:-.035em}\n.text-muted,.text-secondary{color:var(--fz-muted)!important}\n.table{--bs-table-bg:transparent;vertical-align:middle}\n.table thead th{background:#f7f8fc;color:#475467;font-size:.82rem;font-weight:750;white-space:nowrap;border-bottom:1px solid var(--fz-line)}\n.table td,.table th{padding:.8rem .85rem;border-color:var(--fz-line)}\n.table-responsive{border:1px solid var(--fz-line);border-radius:14px;background:#fff}\n.alert{border:1px solid transparent;border-radius:14px}\n.badge{font-weight:700;letter-spacing:.01em}\n.dropdown-menu{border:1px solid var(--fz-line);border-radius:14px;box-shadow:0 14px 35px rgba(16,24,40,.12);padding:.45rem}\n.dropdown-item{border-radius:9px;padding:.55rem .75rem}\n.dropdown-item:active{background:var(--fz-purple)}\nimg{max-width:100%}\nfooter{background:linear-gradient(145deg,#101828,#1c2540)!important}\nfooter a:hover{color:#fff!important}\n@media(max-width:767.98px){\n  body{font-size:15px}\n  .container{padding-left:14px;padding-right:14px}\n  .section-title,h1{font-size:clamp(1.35rem,5vw,1.8rem)}\n  .card,.feature-card{border-radius:15px!important}\n  .btn{min-height:40px}\n  .table td,.table th{padding:.65rem .6rem;font-size:.82rem}\n  footer{padding:38px 0 24px!important;margin-top:38px!important}\n}\n@media(prefers-reduced-motion:reduce){\n  *,*::before,*::after{scroll-behavior:auto!important;animation-duration:.01ms!important;animation-iteration-count:1!important;transition-duration:.01ms!important}\n}\n</style>\n'


# Global visual polish: apply consistently to storefront and standalone admin pages.
# This only changes presentation; it does not alter routes, database records, or forms.
@app.after_request
def _fayez_premium_visual_refresh(response):
    try:
        if response.mimetype == 'text/html':
            html = response.get_data(as_text=True)
            if 'fayez-premium-enterprise-v1' not in html and re.search(r'</head\s*>', html, re.I):
                html = re.sub(r'</head\s*>', lambda match: PREMIUM_ENTERPRISE_CSS + match.group(0), html, count=1, flags=re.I)
                response.set_data(html)
    except Exception:
        app.logger.exception('Premium visual refresh could not be applied to this response')
    return response


if __name__ != '__main__':
    # WSGI hosts import the module instead of executing it as a script.
    init_db()

if __name__ == '__main__':
    init_db()
    print("\n" + "="*60)
    print(" FAYEZ ONLINE SHOP - STARTUP (NETWORK-INDEPENDENT)")
    print(f" Support Email: {SUPPORT_EMAIL}")
    print(f" Hotline/WhatsApp: {HOTLINE_PHONE}")
    print(" Storefront : http://127.0.0.1:5001")
    print(" Admin Login: http://127.0.0.1:5001/admin/login")
    print(" Admin username: fayz (existing password retained)")
    print(" Admin password: [set by owner; stored as a secure hash]")
    print("="*60 + "\n")
    app.run(host=os.environ.get('HOST', '127.0.0.1'), port=int(os.environ.get('PORT', '5001')), debug=os.environ.get('FLASK_DEBUG', '0') == '1')
