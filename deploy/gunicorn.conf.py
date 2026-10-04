"""Linux VPS entry point; only the reverse proxy can reach this socket."""
from pathlib import Path

chdir = str(Path(__file__).resolve().parent.parent / 'web_portal')
bind = '127.0.0.1:8000'
# The existing OTP IP limiter uses in-process cache; keep one shared process.
workers = 1
worker_class = 'gthread'
threads = 4
timeout = 60
accesslog = '-'
errorlog = '-'
capture_output = True
