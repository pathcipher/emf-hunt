# Non-secret dev defaults, loaded automatically by the `flask` CLI (via python-dotenv).
# Lets `flask run` / `flask init-db` work without flags, on port 8000 (prod parity,
# and avoids the macOS AirPlay clash on 5000). Secrets still live in .env.
FLASK_APP=wsgi
FLASK_RUN_PORT=8000
