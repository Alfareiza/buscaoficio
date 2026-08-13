from dotenv import load_dotenv

# FastAdmin reads ADMIN_* from os.environ at import time, so .env must be
# loaded before `from fastadmin import ...` in app.main.
load_dotenv()
