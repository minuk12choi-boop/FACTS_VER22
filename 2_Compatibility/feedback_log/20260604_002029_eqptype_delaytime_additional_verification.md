# EQPTYPE / DELAYTIME 추가 검증 로그

## 미완료 / 차단 사유 / 필요 확인사항

- **운영 DB `facts_wip_source.delaytime` 실제 컬럼 존재 여부는 Codex 컨테이너에서 최종 확인하지 못했습니다.**
  - 차단 사유: 현재 컨테이너에는 Django/MySQL 드라이버가 없고, 패키지 설치 시도는 사내 패키지 터널 `403 Forbidden`으로 실패했습니다.
  - 추가 차단 사유: 운영 DB 호스트 `12.81.64.130:3306` TCP 접속은 `Network is unreachable`로 실패했습니다.
  - 필요 확인사항: 운영/사내 PC에서 아래 PowerShell SQL 확인 명령 또는 MySQL 클라이언트로 `INFORMATION_SCHEMA.COLUMNS`를 조회해 `delaytime` 컬럼 존재 여부를 확인해야 합니다.
- 운영 DB migration은 실행하지 않았습니다.

## 작업 목적

사용자 요청에 따라 EQPTYPE/DELAYTIME 반영 완료 판정 전 다음 항목을 추가 검증했습니다.

1. `facts_wip_source` 실제 DB 컬럼 `delaytime` 존재 여부
2. `my_def.py` `append_df_to_mysql()` INSERT 대상 컬럼에 `eqptype`, `delaytime` 포함 여부
3. PRP TABLE API 응답 샘플 row에 `eqptype`, `delaytime` 포함 여부
4. 다운로드 CSV/엑셀 header에 `EQPTYPE`, `DELAYTIME` 포함 여부
5. Windows PowerShell 기준 검증 명령 정리

## 수정 파일

- 없음: 코드 로직은 변경하지 않았습니다.

## 삭제 파일

- 없음

## 신규 파일

- `feedback_log/20260604_002029_eqptype_delaytime_additional_verification.md`

## migration 파일

- 신규 migration 파일 없음
- 현재 저장소에는 `facts/migrations/` 디렉터리가 없습니다.
- `FactsWipSource` 모델은 `managed = False`이므로 Django migration으로 `facts_wip_source` 스키마 변경이 자동 생성/반영되는 구조가 아닙니다.
- 따라서 `delaytime`이 운영 DB에 없다면, 운영 DBA/담당자가 승인한 DDL 반영이 별도로 필요합니다.
- Codex는 운영 DB migration/DDL을 실행하지 않았습니다.

## 코드 기준 검증 결과

| 번호 | 요청사항 | 상태 | 근거 | 남은 확인 |
| --- | --- | --- | --- | --- |
| 1 | `facts_wip_source` 실제 DB 컬럼 `delaytime` 존재 확인 | 부분완료 | 모델에는 `delaytime` 필드가 있으나 `managed = False`라 migration 대상이 아닙니다. DB 접속은 컨테이너 네트워크/의존성 문제로 실패했습니다. | 운영/사내 PC에서 `INFORMATION_SCHEMA.COLUMNS` 조회 필요 |
| 2 | `append_df_to_mysql()` 실제 INSERT SQL에 `eqptype`, `delaytime` 포함 | 완료 | `final_cols`에 `eqptype`, `delaytime`이 있고, `append_df_to_mysql()`은 `columns = list(df.columns)`로 INSERT 컬럼 목록을 생성합니다. | DB 실제 컬럼 존재 필요 |
| 3 | PRP TABLE API 응답 샘플 row에 `eqptype`, `delaytime` 포함 | 완료(코드 기준) | `build_step_dataset()`이 row dict에 `"eqptype"`, `"delaytime"` key를 넣고, dashboard API가 `payload["rows"] = filtered_rows`로 반환합니다. | 실제 운영 데이터 API 호출로 샘플 JSON 확인 권장 |
| 4 | 다운로드 CSV/엑셀 header에 `EQPTYPE`, `DELAYTIME` 포함 | 부분완료(코드 기준) | PRP TABLE 다운로드 엔드포인트는 CSV를 생성하며, `export_prp_csv()` header에 `EQPTYPE`, `DELAYTIME`이 있고 row writer도 `row.get("eqptype")`, `row.get("delaytime")`을 씁니다. 현재 코드에서 PRP TABLE `.xlsx` 다운로드 엔드포인트는 확인되지 않았고, 별도 `.xlsx`는 업로드 템플릿입니다. | 실제 CSV 다운로드 파일 열람 확인 권장 |
| 5 | Windows PowerShell 검증 명령 정리 | 완료 | 아래 PowerShell 섹션에 정리했습니다. | 사내 PC에서 실행 필요 |

## 검증 명령과 결과

### 컨테이너 실행 결과

```bash
cd 2_Compatibility && python manage.py makemigrations --check --dry-run
```

- 결과: 실패
- 사유: `ModuleNotFoundError: No module named 'django'`
- 코드 문제 여부: 환경 의존성 문제로 판단

```bash
cd 2_Compatibility && python manage.py check
```

- 결과: 실패
- 사유: `ModuleNotFoundError: No module named 'django'`
- 코드 문제 여부: 환경 의존성 문제로 판단

```bash
cd 2_Compatibility && python PRP_COMPATIBILITY_REV.py --only-cache --force-rebuild
```

- 결과: 실패
- 사유: `PRP_COMPATIBILITY_REV.py` 파일이 현재 저장소에 없음
- 코드 문제 여부: 요청 명령의 파일명과 저장소 파일명이 불일치합니다. 현재 존재 파일은 `PRP_COMPATIBILITY.py`입니다.

```bash
python -m pip install 'Django>=5.2,<6' pymysql -q
```

- 결과: 실패
- 사유: 패키지 인덱스 터널 `403 Forbidden`
- 코드 문제 여부: 환경 네트워크/패키지 접근 문제

```bash
python - <<'PY'
import socket
host='12.81.64.130'; port=3306
s=socket.socket(); s.settimeout(5)
try:
    s.connect((host,port)); print('tcp_connect_ok')
    print(s.recv(64))
except Exception as e:
    print(type(e).__name__, e)
finally:
    s.close()
PY
```

- 결과: 실패
- 사유: `OSError [Errno 101] Network is unreachable`
- 코드 문제 여부: 컨테이너 네트워크에서 운영 DB 접근 불가

```bash
cd 2_Compatibility && python - <<'PY'
from pathlib import Path
checks = []
text = Path('my_def.py').read_text(encoding='utf-8')
checks.append(('my_def final_cols eqptype', '"eqptype"' in text[text.index('final_cols = ['):text.index('def append_df_to_mysql')]))
checks.append(('my_def final_cols delaytime', '"delaytime"' in text[text.index('final_cols = ['):text.index('def append_df_to_mysql')]))
seg = text[text.index('def append_df_to_mysql'):text.index('def append_df_to_mysql_eqpmodel')]
checks.append(('append uses df columns in INSERT', 'columns = list(df.columns)' in seg and 'INSERT INTO facts_wip_source ({col_sql})' in seg))

dash = Path('facts/service_modules/dashboard_rows.py').read_text(encoding='utf-8')
checks.append(('dataset collects eqptype', 'step_item["eqptype_values"]' in dash))
checks.append(('dataset collects delaytime', 'step_item["delaytime_values"]' in dash))
checks.append(('response row eqptype key', '"eqptype": eqptype_str' in dash))
checks.append(('response row delaytime key', '"delaytime": delaytime_str' in dash))
checks.append(('csv header EQPTYPE', '"EQPTYPE"' in dash))
checks.append(('csv header DELAYTIME', '"DELAYTIME"' in dash))
checks.append(('csv writes row eqptype', 'row.get("eqptype") or ""' in dash))
checks.append(('csv writes row delaytime', 'row.get("delaytime") or ""' in dash))
for name, ok in checks:
    print(f'{"PASS" if ok else "FAIL"}: {name}')
if not all(ok for _, ok in checks):
    raise SystemExit(1)
PY
```

- 결과: 성공
- 사유: 코드 기준 `eqptype`, `delaytime` 경로 확인 완료

## Windows PowerShell 기준 검증 명령

> 운영 DB migration/DDL은 사용자 승인 없이 실행하지 마십시오. 아래 명령은 코드 검증 및 조회 중심입니다.

```powershell
cd D:\PERSONAL_SPACE\SW\python\2_Compatibility_copy_copy
python manage.py makemigrations --check --dry-run
python manage.py check
python PRP_COMPATIBILITY_REV.py --only-cache --force-rebuild
```

### 운영 DB 컬럼 조회 PowerShell 예시

Django shell에서 조회할 경우:

```powershell
cd D:\PERSONAL_SPACE\SW\python\2_Compatibility_copy_copy
python manage.py shell -c "from django.db import connection; cur=connection.cursor(); cur.execute(\"SELECT COLUMN_NAME, COLUMN_TYPE, IS_NULLABLE, COLUMN_DEFAULT FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'facts_wip_source' AND COLUMN_NAME IN ('eqptype','delaytime') ORDER BY FIELD(COLUMN_NAME,'eqptype','delaytime')\"); print(cur.fetchall())"
```

기대 결과:

- `eqptype`, `delaytime` 두 row가 모두 출력되어야 합니다.
- `delaytime` row가 없으면 운영 DB에 컬럼 추가가 필요합니다.
- 이 확인 명령은 조회만 수행하며 migration/DDL이 아닙니다.

## 사용자 수동 테스트 항목

1. 사내 PC에서 위 PowerShell 명령 3개 실행
2. 운영 DB 컬럼 조회에서 `delaytime` 존재 확인
3. 대시보드 PRP TABLE API 호출 후 응답 `rows[0].eqptype`, `rows[0].delaytime` 확인
4. PRP TABLE CSV 다운로드 후 header에 `EQPTYPE`, `DELAYTIME`이 있는지 확인
5. UI에서 Excel 형식 다운로드가 별도로 노출되어 있다면 해당 엔드포인트/파일도 추가 확인
