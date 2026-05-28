# Known Issues / 재발 주의

## 1. PRP_COMPATIBILITY 실행 오류

실제 PC 로그:

```text
AttributeError: module 'facts.services' has no attribute '_natural_sort_key'
```

발생 위치:

```text
facts/filter_cache_builder.py
_sorted_layer_values_from_set
return sorted(normalized, key=services._natural_sort_key)
```

해결 필요:

- `services.py` facade에 `_natural_sort_key`가 노출되는지 확인
- `filter_cache_builder.py`가 `services._natural_sort_key`에 의존하지 않게 수정 가능
- PRP_COMPATIBILITY 실행 검증 필수

## 2. 그래프 캐시 2분 이상

사전계산 테이블이 있어도 cache hit가 안 되면 계속 느립니다.

확인:

- cache table 존재
- PRP_COMPATIBILITY 실행 후 row 생성 여부
- dashboard data-api가 cache hit하는지
- layer_key/filter key mismatch 여부

## 3. LAYER 전체만 표시

PRP TABLE LAYER가 전체만 나오면 실패입니다.

확인:

- 서버 JSON layer options 포함 여부
- JS가 options를 버리는지
- id/name 충돌
- layerid normalize mismatch

## 4. 팝업 O / 본문 X

호환계획/미등록TIP이 팝업에 있는데 PRP TABLE 본문에 없으면 실패입니다.

확인:

- detail API key와 summary map key 일치
- row build에 summary map 전달 여부
- JS render에서 값 누락 여부
- EQPGROUP red span safe 렌더링 여부

## 5. SSO login 버튼 누락

로그인 템플릿 수정 시 SSO login 버튼이 사라질 수 있습니다. 반드시 확인합니다.

## 6. Migration MySQL 1170

TEXT/BLOB 컬럼을 key/index에 넣지 않습니다. `CharField(max_length=...)` 사용.
