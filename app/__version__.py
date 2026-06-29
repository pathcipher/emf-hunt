"""Single source of truth for the app's semantic version (https://semver.org).

Bump this when cutting a release and tag the repo `vX.Y.Z` to match; CI then
publishes a matching `ghcr.io/<owner>/emf-hunt:X.Y.Z` image from the tag.

MAJOR.MINOR.PATCH:
- MAJOR — incompatible changes (e.g. data model / deploy steps that need action).
- MINOR — new functionality, backwards-compatible.
- PATCH — backwards-compatible fixes only.
"""
__version__ = "0.1.0"
