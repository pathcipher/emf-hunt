# Changelog

All notable changes to this project are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).
The running version is shown in the site footer and defined in
[`app/__version__.py`](app/__version__.py).

## [Unreleased]

## [0.1.0] - 2026-06-11

### Added
- Magic-link authentication (passwordless, single-use, expiring, hashed tokens);
  first user becomes admin.
- Team-based progression with two modes: **sequential** (one puzzle at a time) and
  **parallel** (all published puzzles open at once, filterable by user-visible tags),
  toggleable at runtime from Mission Control.
- Player flow: view puzzle, submit answer (multiple accepted answers), auto-advance,
  customisable success page.
- Admin tools: puzzle authoring (HTML editor + per-puzzle image uploads), live
  submissions feed, team management, per-puzzle solve reset, player deletion, solve
  stats, puzzle preview, customisable favicon/logo.
- Dynamic puzzle content via remote handler URLs.
- Anti-abuse: Cloudflare Turnstile on login + SES complaint/bounce suppression webhook
  with an admin-managed blocklist.
- Docker image, dev/prod compose (Traefik + Let's Encrypt + Watchtower), GitHub Actions
  build & publish to GHCR.

[Unreleased]: https://github.com/pathcipher/emf-hunt/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/pathcipher/emf-hunt/releases/tag/v0.1.0
