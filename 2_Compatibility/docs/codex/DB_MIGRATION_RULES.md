# DB 및 Migration 규칙

## 운영 DB 금지

Codex는 운영 DB에 migrate를 실행하지 않습니다. migration 파일 생성과 dry-run/check만 수행합니다.

## MySQL 호환성

MySQL에서는 TEXT/BLOB 컬럼을 key/index/unique에 넣으려면 key length가 필요합니다. 따라서 index/unique에 들어가는 문자열 필드는 가능한 `CharField(max_length=...)`를 사용합니다.

사례:

```text
0027_factsdashboardgraphcache.py에서 layer_key가 TEXT 계열로 unique key에 포함되어 MySQL 1170 오류 발생
```

방지:

```python
layer_key = models.CharField(max_length=512, blank=True, default="")
```

## sqlmigrate 확인

가능하면 신규 migration에 대해 SQL을 확인합니다.

```powershell
python manage.py sqlmigrate facts 0027
python manage.py sqlmigrate facts 0028
```

DB 접속 문제 시 `config.settings_codex` 대체 가능하지만, MySQL 전용 오류는 SQLite에서 안 잡힐 수 있음을 보고서에 명시합니다.

## 테스트 DB 확인 SQL

```sql
SHOW TABLES LIKE 'facts_dashboard_graph_cache';
SHOW INDEX FROM facts_dashboard_graph_cache;
SHOW TABLES LIKE 'facts_history_summary_cache';
```

실패 잔여 테이블 제거는 테스트 DB 한정입니다. 운영 DB에 DROP TABLE 안내 금지.

## 신규 cache/precompute 모델

대시보드 그래프:

```text
facts_dashboard_graph_cache
```

History 요약:

```text
facts_history_summary_cache
```

migration 반영 후 사전계산 명령과 UI 조회가 실제로 해당 테이블을 hit하는지 확인해야 합니다.
