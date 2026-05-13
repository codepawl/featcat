"""Celery task package — distributed background jobs for featcat (T1.5).

Optional ``[tasks]`` extra:

    uv pip install -e '.[tasks]'  # adds celery[redis] + flower

Importing this package without celery installed raises ImportError lazily
(only when :mod:`featcat.tasks.app` is actually imported), so unrelated
code paths (CLI, server) keep working without the extra.
"""
