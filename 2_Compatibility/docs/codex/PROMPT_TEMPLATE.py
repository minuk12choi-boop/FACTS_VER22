# Codex Prompt Template

```text
현재 브랜치 <branch>의 후속 수정 작업이다.

절대 main에 merge하지 마라.
운영 config/settings.py는 건드리지 마라.
운영 DB에 직접 migrate 실행하지 마라.
기존 기능, 기존 URL, 기존 권한체계, 기존 팝업, 기존 업로드/다운로드, 기존 대시보드 계산 로직의 의미는 모두 유지하라.
백업용 파일(.bak, _old, _backup 등)을 만들지 마라.
결과 보고는 반드시 한국어로 작성하라.
사내 PC 검증 안내에 git pull을 넣지 마라.

요청사항을 절대 임의로 skip하지 마라.
막히면 보고서 최상단에 미완료/차단 사유/필요 확인사항을 적어라.
일부만 하고 완료한 것처럼 말하지 마라.

이번 작업 목적:
1. ...
2. ...

수정 요구:
...

검증:
python manage.py check
python -m compileall config facts PRP_COMPATIBILITY.py my_def.py
python manage.py collectstatic --noinput
python manage.py makemigrations --check --dry-run
python -m ruff check facts --select F821
DJANGO_SETTINGS_MODULE=config.settings python -c "import django; django.setup(); import facts.views; import facts.services; print('django setup/import ok')"

최종 보고서 필수:
1. 요청사항별 처리 상태표
2. 미완료/부분완료 사유
3. 수정 파일 목록
4. 신규 migration 목록
5. 검증 결과
6. 테스트 DB migration 명령
7. 운영 반영 전 수동 테스트 항목
```
