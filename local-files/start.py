"""Start the local shop using its private data outside the upload folder."""
import os
from pathlib import Path
import runpy
import sys

LOCAL = Path(__file__).resolve().parent
SERVER = LOCAL.parent / 'wasmer-app' / 'server'
VENV_PYTHON = LOCAL / '.venv' / 'bin' / 'python'

# Keep `python3 start.py` reliable: use the project's dependencies whenever the
# command was launched with a system Python instead of the local environment.
if sys.prefix == sys.base_prefix and VENV_PYTHON.is_file():
    os.execv(str(VENV_PYTHON), [str(VENV_PYTHON), str(Path(__file__).resolve()), *sys.argv[1:]])

env_file=LOCAL/'.env'
if env_file.is_file():
    for line in env_file.read_text().splitlines():
        line=line.strip()
        if not line or line.startswith('#') or '=' not in line: continue
        key,value=line.split('=',1)
        if key.strip() == 'PUBLIC_ORIGIN':
            key=key.strip();value=value.strip()
            if not os.environ.get(key): os.environ[key]=value
os.environ['WOBLI_DATA_DIR'] = str(LOCAL / '.data')
sys.dont_write_bytecode = True
sys.path.insert(0, str(SERVER))
runpy.run_path(str(SERVER / 'app.py'), run_name='__main__')
