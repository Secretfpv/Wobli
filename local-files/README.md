# Local files — do not upload this folder

- `.data/`: SQLite database and private admin-access file.
- `.venv/`: Python virtual environment created by the top-level `setup.sh` file.
- `tests/`: automated backend tests, now pointing to `../wasmer-app/server`.
- `WEBSITE-GUIDE.md`: detailed feature/editing guide (see updated path notes at the top).
- `start.py`: starts the local website while keeping data outside the upload folder.

First-time setup, from the parent project folder:

```sh
./setup.sh
```

Start the website:

```sh
python3 local-files/start.py
```

Tests, from the parent project folder:

```sh
PYTHONDONTWRITEBYTECODE=1 python -m unittest discover -s local-files/tests -v
```

The website code is now in `wasmer-app/webpage/`; the backend code is in `wasmer-app/server/`. Restart the server after backend edits. Private credentials are in `.data/admin-access.txt` in this folder. Preserve database and uploads together when backing up, with the server stopped.
