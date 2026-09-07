# Wobli — application source for hosting

This folder contains only the website and Python backend source. No private database, passwords, customer records, virtual environment, artwork sources or tests are included.

**Not yet ready for a live Wasmer shop.** The requested file separation is complete; it is not a database migration or tested Wasmer deployment. Uploading this folder as a static website will not make login, products, profiles or questions work.

## Contents

- `webpage/index.html`: main page.
- `webpage/assets/`: images used by the website.
- `webpage/styles/` and `webpage/scripts/`: styling and browser code.
- `server/app.py`: Python HTTP/API server.
- `server/store.py`: SQLite data and authentication logic.

Only `webpage/` is public content. Do not expose `server/` as a static directory. Product uploads live in private runtime storage and are served through the application; existing local uploads are deliberately excluded here.

## Wasmer deployment work still required

1. Adapt the local SQLite backend to storage suitable for Wasmer. Wasmer's shared volumes currently support concurrent writers and are explicitly not recommended for databases. Do not put the live SQLite file on a shared volume or bundle customer data in the package.
2. Select the Wasmer app owner/name and Python runtime, then create `wasmer.toml` and `app.yaml` from the official Python template. These account-specific configuration files have not been created; the Wasmer CLI is not installed here.
3. Adapt server bind address/port, exact allowed Host/Origin values and HTTPS Secure cookies for the real Wasmer domain. Current code intentionally accepts only local hosts and HTTP origins.
4. Configure private credentials, persistent product-image storage and database backups. Migrate only the approved data through a private process. Set `WOBLI_DATA_DIR` only to appropriate private storage; that setting alone does not make SQLite safe on Wasmer.
5. Test SQLite replacement, password hashing support, sessions, uploads and all account flows in the chosen runtime before publishing.

Nothing has been uploaded or published.

Official documentation:
- https://docs.wasmer.io/edge/guides/python/
- https://docs.wasmer.io/edge/learn/volumes/

## Local preview

From the parent project folder: `python3 local-files/start.py`.
Open http://127.0.0.1:8082/. The launcher uses `local-files/.data` so private files stay outside this upload-source folder.
