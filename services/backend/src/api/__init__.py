"""HTTP API package.

Uvicorn entry is ``src.api.app:app``. This package does not import ``app`` or
``create_app`` so submodules such as ``google_oauth`` can load without opening
``{JOBS_ROOT}/migrator.sqlite`` (pytest-xdist collection must stay lock-free).
"""
