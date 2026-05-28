# Batch / Precompute / PRP_COMPATIBILITY 규칙

## 목표

대시보드 그래프와 History 요약은 조회 때마다 무겁게 계산하지 않고, 일 배치 후 사전계산된 테이블을 사용합니다.

## 일 배치 맥락

사용자 제공 raw 적재 스크립트는 bigdataquery로 raw data를 만들고 MySQL에 저장한 뒤 마지막에 다음 흐름을 호출합니다.

```python
latest_snap_date = dt.datetime.now().date()
rebuild_filter_cache(snap_date=latest_snap_date)
```

그래프/히스토리 사전계산은 이 뒤에 자동 연결되어야 합니다.

## 파일

- `PRP_COMPATIBILITY.py`: Windows Scheduler 실행 진입점
- `my_def.py`: 공통 함수

## 민감정보

새 파일에 DB 비밀번호를 하드코딩하지 않습니다. Django settings/ORM을 사용합니다.

## DB 저장 위치

`my_def.py`에 pymysql conn이 없어도 Django ORM은 `DJANGO_SETTINGS_MODULE=config.settings`의 `DATABASES['default']`로 저장합니다.

실행 로그에는 다음을 출력하는 것이 좋습니다.

- DJANGO_SETTINGS_MODULE
- DB ENGINE
- DB NAME
- DB HOST

## 필수 명령

```powershell
python PRP_COMPATIBILITY.py --snap-date YYYY-MM-DD
```

기본값은 오늘 날짜입니다.

## 현재 재발 주의 오류

`PRP_COMPATIBILITY.py` 실행 중:

```text
AttributeError: module 'facts.services' has no attribute '_natural_sort_key'
```

원인 후보:

- `services.py` facade에서 `_natural_sort_key` re-export 누락
- `filter_cache_builder.py`가 내부 helper를 `services._natural_sort_key`로 의존

해결 원칙:

- `filter_cache_builder.py`가 필요한 helper를 직접 정의/명시 import하도록 고칩니다.
- 또는 `facts/services.py` facade에서 기존 호환을 위해 `_natural_sort_key`를 re-export합니다.
- F821/import 검증과 실제 `python PRP_COMPATIBILITY.py --snap-date ...` 실행 검증을 반드시 수행합니다.
