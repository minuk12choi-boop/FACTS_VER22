# 검증 규칙

## 기본 검증

작업 후 가능한 한 아래 명령을 실행합니다.

```powershell
python manage.py check
python -m compileall config facts PRP_COMPATIBILITY.py my_def.py
python manage.py collectstatic --noinput
python manage.py makemigrations --check --dry-run
python -m ruff check facts --select F821
```

Django import 검증:

```powershell
$env:DJANGO_SETTINGS_MODULE="config.settings"
python -c "import django; django.setup(); import facts.views; import facts.services; print('django setup/import ok')"
```

DB 접속 문제로 실패하면 `config.settings_codex`로 대체합니다.

```powershell
$env:DJANGO_SETTINGS_MODULE="config.settings_codex"
python -c "import django; django.setup(); import facts.views; import facts.services; print('django setup/import ok')"
```

## F821 필수

`F821`은 정의되지 않은 이름입니다. 반드시 0개여야 합니다.

## import 검증 주의

`python -c "import facts.views"`만 단독 실행하면 settings 미설정 오류가 납니다. 반드시 `DJANGO_SETTINGS_MODULE`과 `django.setup()`을 포함합니다.

## 검증 실패 보고

실패한 명령은 숨기지 않습니다. 정확한 실패 사유를 보고합니다.

형식:

```text
실패 명령:
실패 사유:
코드 문제 여부:
대체 검증:
```

## run 검증 안내

사내 PC 검증 안내에 `git pull`을 넣지 않습니다.

기본 검증 예:

```powershell
cd D:\PERSONAL_SPACE\SW\python\2_Compatibility_copy_copy
python manage.py check
python -m compileall config facts PRP_COMPATIBILITY.py my_def.py
python manage.py collectstatic --noinput
python manage.py showmigrations facts
python -m waitress --listen=0.0.0.0:8001 config.wsgi:application
```
