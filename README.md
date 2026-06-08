# Pathcipher@EMF

A mobile-first puzzle-hunt webapp for EMF Camp 2026, built with Flask.

Teams progress through puzzles one at a time via magic-link login (no passwords).
The first user to log in becomes an admin and can author puzzles, set answers, and
watch every team's progress.

## Quick start

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

cp .env.example .env
# set a strong SECRET_KEY:
python -c "import secrets; print(secrets.token_hex(32))"   # paste into .env

flask init-db        # create the database tables
flask seed-demo      # optional: a few fake demo puzzles (incl. a GPS one)
flask run --debug    # http://localhost:8000
```

> `.flaskenv` sets `FLASK_APP=wsgi` and the dev port to **8000**, so the `flask`
> commands work without flags. Both dev and Docker use 8000.

In development `EMAIL_BACKEND=console`, so the magic-link login URL is **printed to
the server log** — copy it from the terminal to "receive" the email. The first email
you log in with becomes the admin.

## Run with Docker

The image runs the app under gunicorn as a non-root user; the SQLite database lives on a
named volume so it survives restarts.

### Development

```bash
cp .env.example .env        # set a strong SECRET_KEY (see above)
docker compose up --build   # http://localhost:8000
```

- The magic-link emails print to the log — `docker compose logs -f web`.
- Seed demo puzzles on first boot by setting `SEED_DEMO=1` in the `.env`.
- Test the image: `docker compose run --rm web pytest -q`

### Production with Traefik and Let's Encrypt

Use `docker-compose.prod.yml` for production. It includes Traefik, an auto-configuring
reverse proxy with built-in Let's Encrypt SSL.

```bash
cp .env.example .env

# Set in .env:
# - SECRET_KEY: strong random string (see Quick start)
# - APP_DOMAIN: your domain (e.g., emf-hunt.example.com)
# - ACME_EMAIL: for Let's Encrypt renewal notices (e.g., admin@example.com)
# - EMAIL_BACKEND: set to "api" and configure EMAIL_API_URL / EMAIL_API_KEY

docker compose -f docker-compose.prod.yml up -d
```

Traefik will:
- Automatically obtain and renew TLS certificates from Let's Encrypt
- Redirect HTTP → HTTPS
- Route traffic to the Flask app
- Store certificates on a persistent volume

The app is available at `https://YOUR_APP_DOMAIN`. Ensure:
- Your DNS points to the server's public IP
- Ports **80** and **443** are open (Let's Encrypt requires HTTP-01 challenge)

SQLite is fine for camp-scale traffic; for heavier load, point `DATABASE_URL` at Postgres.

### Published image (GHCR)

Pushes to `main` (and `v*` tags) run the test suite, then build and publish the image to
the GitHub Container Registry via
[`.github/workflows/docker-publish.yml`](.github/workflows/docker-publish.yml):

```bash
docker run -p 8000:8000 --env-file .env ghcr.io/<owner>/emf-hunt:latest
```

Authentication uses the built-in `GITHUB_TOKEN` — no extra secrets to configure. Pull
requests build the image (to catch breakage) but do not publish. The package starts out
private; make it public in the repo's **Packages** settings if you want unauthenticated pulls.

## Security model

This repo is safe to make public. None of the sensitive material lives in code:

- **No passwords.** Login is a single-use, time-limited, hashed magic-link token.
- **No secrets in the repo.** `SECRET_KEY`, the database URL, and email-provider
  credentials all come from `.env` (gitignored).
- **No puzzle answers in the repo.** Answers live only in the database (`*.db`,
  gitignored), edited through the admin UI.
- **Trust boundary.** Puzzle content is a *trusted admin authoring surface* — admins
  may write arbitrary HTML/JS (some puzzles use the browser Geolocation API), so puzzle
  HTML is rendered as-is. Every **player-supplied** value (email, team name, submitted
  answer) is escaped/parameterized and never rendered raw. Protect admin accounts
  accordingly.
- SQL injection is avoided via the SQLAlchemy ORM; CSRF tokens guard every form;
  magic-link and answer submissions are rate-limited.

> Geolocation puzzles require a **secure context**: GPS only works over HTTPS (or
> `localhost`). Serve production over TLS.

## Email in production

Choose an email backend:

- **`EMAIL_BACKEND=ses`** — AWS SES (Simple Email Service). Free tier: 62,000 emails/month
  (effectively unlimited for a weekend event). Requires AWS credentials (see `.env.example`).
  Cost: ~$0.10 per 1,000 emails after free tier.

- **`EMAIL_BACKEND=api`** — other transactional email providers (Mailgun, Postmark, Resend,
  SendGrid, etc.). The backend interface lives in [`app/email.py`](app/email.py) — adapt
  the request shape to your provider.

## Dynamic puzzle content

Puzzles can fetch content from a remote handler URL for time-based or dynamic content (e.g.,
puzzles that change based on the current time or pull data from an external source).

**Setup:**
1. Create a separate service that accepts HTTP GET requests with query params:
   - `puzzle_id` (int)
   - `team_id` (int)
   - `at` (ISO 8601 timestamp)
   - Returns HTML content

2. In the admin UI, when editing a puzzle, set the **Handler URL** field to your service
   endpoint (e.g., `https://puzzles.internal/api/puzzle/time-based`).

3. When a puzzle with a handler URL is viewed, the app fetches content from that URL
   instead of using the stored HTML. Responses are cached for `PUZZLE_CONTENT_CACHE_SECONDS`
   (default 60) to reduce load.

**Example handler** (simplified Python):
```python
@app.get("/api/puzzle/<name>")
def dynamic_puzzle(name: str):
    puzzle_id = request.args.get("puzzle_id")
    team_id = request.args.get("team_id")
    at = request.args.get("at")  # ISO timestamp
    # Generate or fetch content based on time, team, etc.
    return f"<p>Current time: {at}</p>..."
```

The handler URL is optional. Puzzles without a handler URL use the static HTML content
stored in the admin UI.

## Layout

```
app/
  __init__.py     app factory, security headers, CLI commands
  extensions.py   db / login / csrf / limiter
  models.py       User, Team, Puzzle, Solve, Submission, LoginToken
  security.py     magic tokens, answer normalization, admin_required
  email.py        pluggable email backends (console | ses | api)
  auth/  teams/  puzzles/  admin/    blueprints
  templates/  static/
config.py         env-driven configuration
wsgi.py           entrypoint
tests/            pytest suite
```

## Tests

```bash
pytest
```

## AI disclaimer

This project was built with significant assistance from an AI coding agent
(Anthropic's Claude, via Claude Code). All code is human-reviewed before use, but treat it
as you would any contribution: read it before you rely on it, and give the security-sensitive
paths — magic-link auth, the admin trust boundary, and answer handling — an extra look prior
to running a live event.
