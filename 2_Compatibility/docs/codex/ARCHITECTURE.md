# FACTS 구조 및 분할 원칙

## 현재 목표

거대한 `views.py`, `services.py`, `dashboard.js`를 페이지-기능 단위로 관리 가능한 구조로 분리합니다.

## Python view 구조

권장 구조:

```text
facts/views.py                         # facade: import/re-export만
facts/view_modules/common.py           # 공통 helper만
facts/view_modules/dashboard.py        # dashboard view/API/helper
facts/view_modules/history.py          # 변경이력 view/API/helper
facts/view_modules/prevent_tip.py      # PREVENT TIP page
facts/view_modules/master.py           # 기준정보
facts/view_modules/kpi.py              # KPI
facts/view_modules/voc.py              # VOC
facts/view_modules/legacy.py           # 가능하면 제거, 남기면 re-export 전용
```

금지 구조:

```text
dashboard.py -> legacy.py에서 실제 함수 import
history.py -> legacy.py에서 실제 함수 import
common.py에 dashboard/history/master 업무 로직 대량 배치
```

`common.py`에는 여러 모듈이 공통으로 쓰는 순수 helper만 둡니다.

## Python service 구조

권장 구조:

```text
facts/services.py                              # facade
facts/service_modules/common.py                # normalize/date/key helper
facts/service_modules/dashboard_filters.py     # 필터/option/cache
facts/service_modules/dashboard_rows.py        # PRP TABLE row/summary/export
facts/service_modules/plan_detail.py           # 호환계획 detail/replay/save/delete helper
facts/service_modules/tip_missing.py           # TIP미등록 path detail/replay/save/delete helper
facts/service_modules/bulk_upload.py           # Excel upload/template/parser
facts/service_modules/kpi.py                   # KPI
facts/service_modules/master.py                # 기준정보
facts/service_modules/legacy.py                # 가능하면 제거, 남기면 re-export 전용
```

`services.xxx` 기존 호출은 깨지지 않아야 합니다. facade에서 필요한 함수가 빠지면 런타임 오류가 발생합니다.

## JavaScript 구조

권장 구조:

```text
static/facts/js/dashboard.js                   # entry/facade
static/facts/js/dashboard/state.js             # state/namespace
static/facts/js/dashboard/api.js               # API wrapper
static/facts/js/dashboard/filters.js           # filters/searchable/multi dropdown
static/facts/js/dashboard/chart.js             # chart
static/facts/js/dashboard/prp_table.js         # PRP table rendering/export
static/facts/js/dashboard/modals.js            # plan/tip/override modals
static/facts/js/dashboard/bulk_upload.js       # upload
static/facts/js/dashboard/init.js              # init orchestration only
static/facts/js/searchable_select.js           # 공용 searchable dropdown
```

`init.js`나 `prp_table.js` 하나에 대부분 로직을 몰아넣지 않습니다.

## import 원칙

- `from .common import *` 금지
- 필요한 이름만 명시 import
- `_`로 시작하는 helper는 반드시 명시 import
- `ruff F821` 0개 필수
- `legacy.py` 의존 재도입 금지
