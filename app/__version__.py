"""Fallback app version for local/dev runs.

The authoritative version is computed by **GitVersion** from git history +
Conventional Commits (see `GitVersion.yml`) and injected into the image as the
`APP_VERSION` env var at build time — that's what the footer shows in CI builds.

This constant is only the fallback used when `APP_VERSION` isn't set (e.g. a
local `flask run` or a plain `docker build` without the build-arg). Bumping it
is optional; GitVersion drives real release numbers.
"""
__version__ = "0.1.0"
