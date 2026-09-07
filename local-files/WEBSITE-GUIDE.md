> Path update: this guide was moved during the two-folder reorganisation. Website paths below are relative to `wasmer-app/webpage/`; backend paths are now `wasmer-app/server/`. Private data and tests are under `local-files/`. Use `python local-files/start.py` from the root to start the server. The original guide is retained below for feature reference.

# Wobli website

Start the server from the project folder with `python3 server/app.py`, then open http://127.0.0.1:8082/. Python 3.10+ is required; there are no external packages or build steps. Opening the HTML directly or using a static-only server will not provide the catalogue, admin login or cart API.

## Admin access and products

1. Open **Log in** in the top bar. Use `admin` or its `@dmin` sign-in alias with your existing password. Initial username and generated password are in `../.data/admin-access.txt` (relative to this README). Keep this file private.
2. After signing in, the **Manage shop** tab appears. Change the generated password in **Security**. The initial credential file is not updated when your password changes.
3. Add or select a product. Edit its name, SKU, description, compatible vehicles, category, image, price and availability.
4. Save as **Draft** to keep it private, **Published** to show it, or **Archived** to hide it without deleting it.
5. Published concepts are shown as coming soon. To enable Add to cart, choose **In stock**, set a price and stock greater than zero; or choose **Preorder**, set a price and delivery estimate.

Products support up to 12 PNG, JPEG or WebP images, each up to 5 MB. Select multiple files or add more later. Use Make cover to choose the first image, and Remove to remove an individual image. Shop cards show only the cover image with a 1/N counter, name, availability and price; clicking opens the gallery, full description and Add to cart. Existing single-image products remain supported. Restart the Python server after backend code changes. Pricing is currently CHF. Categories are fixed to the existing shop filters. Your six initial items remain concepts until you configure real products.

## Backend and saved data

- `../server/app.py`: local HTTP server, protected admin API, image uploads and static assets.
- `../server/store.py`: SQLite persistence, password hashing, sessions, product validation and cart calculations.
- `../tests/`: persistence, access control and cart validation tests. Run `python3 -m unittest discover -s tests -v` from the project folder.
- `../.data/shop.sqlite3`: private catalogue and admin/session database.
- `../.data/uploads/`: product image files. Back up this directory and the database together while the server is stopped.

The server listens only on this computer. It does not publish the website. Keep `.data` outside the public website directory and out of source control. Only product images in its uploads folder are served.

## Before a public launch

This is a local implementation, not a production deployment. Production requires a deployment-grade server, HTTPS and Secure cookies, operational backups and monitoring, and a security review. Payment, orders, checkout and inventory reservation are not implemented. Customer accounts work locally; email verification and password recovery are not implemented. Do not treat an account email as proof of ownership. A payment provider must calculate/validate prices and order state on the server; never trust cart totals from the browser.

## Structure

```text
webpage/
├── index.html           Page content and markup
├── wobli_main.original.html  Original reference page (not loaded)
├── styles/
│   ├── main.css                   Theme, navigation, homepage and shared components
│   ├── account.css                Login, registration and password-reset appearance
│   ├── layout.css                 Footer, responsive layout and logo sizing
│   ├── shop.css                   Shop sidebar, cards, popup and floating shortcut
│   ├── commerce.css               Admin editor, product pricing and cart layout
│   └── effects.css                LED sweeps, headlights, brake lights and indicator
├── scripts/
│   ├── commerce-api.js            Shared server API and UI helpers
│   ├── admin.js                   Admin authentication and product editor
│   ├── cart.js                    Browser cart and server-validated totals
│   ├── navigation.js              Switch between page sections
│   ├── shop.js                    Live catalogue, filtering and preorder popup
│   ├── account.js                 Account views and hold-to-show password control
│   ├── effects.js                 Scroll reveals, cursor glow and indicator timing
│   └── forms.js                   Original installation and custom-request demos
└── assets/                        Logo and image files
```

## Common edits

| Change | Where to look |
| --- | --- |
| Page wording, headings, images and form fields | `index.html` |
| Theme colours | `styles/main.css` → `:root` |
| Mouse-following light size and brightness | `styles/main.css` → `.cursor-glow` |
| Logo sizes | `styles/layout.css` → `.brand-logo` and `.hero-logo` |
| Shop spacing, filters and cards | `styles/shop.css` |
| Products, images, stock and pricing | Sign in → Manage shop |
| Preorder introduction text | `index.html` → `preorderDialog` |
| Red panel and button sweep speed | `styles/effects.css` → `sectionLedSweep` animation declarations |
| LED colours | `styles/effects.css` → `--led-core`, `--led-halo`, `--button-led-core`, `--button-led-halo` |
| Headlight and pressed-button appearance | `styles/effects.css` → headlight and brake-light sections |
| Floating Custom Lab button position | `styles/shop.css` → `.lab-shortcut` and its mobile rule |
| Three amber flashes and arrow fade | `styles/effects.css` → `labTurnSignal`, `labArrowReturn` |
| Arrival delay and signal cleanup | `scripts/effects.js` → `signalCustomLab` |

For indicator timing, keep the CSS and JavaScript aligned: three 0.7-second flashes, a 0.5-second pause, then a 0.35-second fade. The current class cleanup runs after 3 seconds.

## Loading order

Stylesheets load in the order listed in the HTML to preserve the existing cascade. Scripts use `defer` and run in their listed order once the page markup is ready. They are plain scripts with shared functions. `commerce-api.js` must load first. Use the backend server for the shop, admin and cart.

Navigation calls the shop's `maybeShowPreorder()` function; shop actions use `openView()` from navigation. All scripts finish initialising before visitors interact with the page.

## Preview limitations

Admin/customer authentication, registration, product storage and private product questions are real local backend features. Password recovery and installation/custom-request forms remain demos. No payments or orders are submitted. Cart IDs and quantities are remembered on the current browser/device; prices and availability are fetched from the server when viewing the cart. Adding an item does not reserve stock. The preorder introduction dismissal is remembered with `wobli-preorder-intro-v1`.

## Product questions and customer accounts

Click **Ask a question** in a product popup. Signed-out visitors see a login requirement and can sign in or register with email, password and confirmation. Successful authentication returns to that product and opens the question form. Cancelling login leaves the product open. Unsaved question text stays in memory while re-authenticating an expired session, but is not retained after a page reload.

Questions (up to 3000 characters) are saved privately with the product ID/name, account identity and timestamp. The admin reads the latest 500 under **Manage shop → Product questions**. No email notification or reply service is connected. Retries of the same request do not create duplicate questions; accounts are limited to ten questions per hour. Customer sessions cannot access the admin endpoints. Customer credentials are hashed and sessions use HttpOnly cookies; registration/sign-in attempts are rate limited.

Restart `python server/app.py` after backend changes. New database tables are created automatically without replacing your existing catalogue. Customer accounts, sessions and questions are stored in the same private SQLite database and should be included in your backup and future privacy/retention policy.

## Customer profile

After customer login, clicking the account name opens **Home**, **Personal details**, and **Settings**. Home has a placeholder for future order history. Personal details are optional: first name, surname, phone, street/house number, additional address, postal code, city and country. These are stored privately in `customer_profiles`, not browser storage, and are not yet connected to checkout.

Email/password changes require the current password, are rate limited and invalidate all customer sessions. The user signs in again afterward. Email changes preserve profile details and update the author email on their saved questions. Duplicate emails are rejected. Email verification and forgotten-password recovery remain unavailable; do not treat these emails as verified identities. New tables are added on server restart without replacing existing data. Customer profiles are not available to the admin-only login.
