from dotenv import load_dotenv

from .sentry import init_sentry

# FastAdmin reads ADMIN_* from os.environ at import time, so .env must be
# loaded before `from fastadmin import ...` in app.main.
load_dotenv()

# Must run before app.config builds Settings(): an invalid env var raises
# there, at import time, and that crash reaches Sentry only if the SDK is
# already initialized.
init_sentry()
