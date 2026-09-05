# Vercel ASGI entry point for the buscaoficio-back project.
#
# Vercel's Python runtime (@vercel/python) treats every .py file under api/
# as a serverless function. When the runtime detects an ASGI-compatible object
# named `app`, it calls it as the ASGI handler — no adapter (Mangum, etc.)
# is needed.
#
# All requests are rewritten here via vercel.json.
# NullPool is already set in app/database.py — critical for serverless since
# there is no persistent process to hold connections between invocations.
from app.main import app  # noqa: F401
