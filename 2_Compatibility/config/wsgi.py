import os
from pathlib import Path

from django.core.wsgi import get_wsgi_application
from whitenoise import WhiteNoise

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

application = get_wsgi_application()

# Waitress/WSGI 실행에서도 FACTS 정적 파일이 누락되지 않도록
# WhiteNoise를 WSGI 레이어에서 한 번 더 감싼다.
BASE_DIR = Path(__file__).resolve().parent.parent
application = WhiteNoise(application, root=str(BASE_DIR / "staticfiles"), prefix="static/")
application.add_files(str(BASE_DIR / "static"), prefix="static/")
