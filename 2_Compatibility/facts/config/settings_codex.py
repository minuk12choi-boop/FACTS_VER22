from .settings import *

DEBUG = True

# Codex에서는 실제 운영 DB 접속 검증을 하지 않기 위한 임시 설정
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "codex_check.sqlite3",
    }
}

# Codex Linux 환경 xmlsec 경로
if "SAML_CONFIG" in globals() and isinstance(SAML_CONFIG, dict):
    SAML_CONFIG["xmlsec_binary"] = "/usr/bin/xmlsec1"
