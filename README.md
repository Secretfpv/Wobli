# Wobli

The project is divided into two folders:

- **wasmer-app/** — website assets and backend source intended for hosting. Read its README before uploading: Wasmer deployment still needs database/runtime configuration.
- **local-files/** — private data, virtual environment, tests, original artwork, business documents and backups. Never upload this folder.

Install the local environment and all dependencies from this project folder:

```sh
./setup.sh
```

Then start the website:

```sh
python3 local-files/start.py
```

Open http://127.0.0.1:8082/.

Python dependencies are kept in the single top-level `requirements.txt` file. The launcher automatically uses `local-files/.venv`, so manual activation is optional. Nothing has been published.

Target for the page structure:

                    wobli.ch
                          │
                        HTTPS
                          │
                          ▼
                ┌──────────────────┐
                │      WASMER      │
                │                  │
                │ HTML / CSS / JS  │
                │                  │
                │ Python backend   │
                └────────┬─────────┘
                         │
              ┌──────────┼───────────┐
              │          │           │
              ▼          ▼           ▼
          Database     Payment   Email
                                    SMTP
              │          │           │
              ▼          ▼           ▼
           Orders     Payments     Emails
          Customers              confirmations
          Products
# Wobli
