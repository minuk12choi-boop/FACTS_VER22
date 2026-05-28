# Dashboard / Graph / PRP TABLE 규칙

## 대시보드 필터 종속성

상단 필터와 PRP TABLE 필터 모두 종속성 원칙을 지킵니다.

- line 선택 → 해당 line의 PRP만 표시
- PRP 선택 → 해당 PRP가 존재하는 line만 표시
- area/layer도 가능한 값만 표시
- 선택 순서와 무관하게 동작
- 현재 선택값이 유효하면 유지, 유효하지 않으면 안전 reset

## LAYER 필터

- 전체만 나오면 실패
- 실제 layer 목록 표시
- 복수 선택 가능
- 상단/PRP TABLE 모두 동일한 dropdown+checkbox 컴포넌트
- `1`, `1.0`, `1.00` 정규화 주의

## 그래프 속도

그래프 조회가 2분 이상 걸리면 실패입니다. 원천 raw를 매번 훑지 말고 사전계산/DB cache를 사용합니다.

대상 테이블:

```text
facts_dashboard_graph_cache
```

필수:

- cache table 미존재 시 500 방지
- cache hit 우선
- miss 시 fallback 계산 후 cache 저장
- 일 배치 후 자동 사전계산 연결
- 수동 rebuild 의존 금지

## 그래프 cache key

필터 조건과 정확히 맞아야 합니다.

- snap_date
- lineid
- processid
- areaname
- layer_key
- include_measure
- include_emergency
- exclude_skiprule_100
- tip_mode

cache miss가 반복되면 key mismatch를 의심합니다.

## 호환계획 / 미등록TIP 본문 표시

팝업에 값이 있으면 PRP TABLE 본문에도 값이 있어야 합니다.

호환계획:

- 호환계획 컬럼
- 계획_호환EQPBODY명
- 계획_호환EQPCHAM명 등

미등록TIP:

- 미등록TIP호환Path 컬럼
- EQPGROUP 빨간 글자 path 표시

팝업 O / 테이블 X는 실패입니다.

## 팝업 삭제/수정

팝업 목록에 보이는 행은 삭제/수정 가능한 식별자를 가져야 합니다.

- ID 있으면 ID 우선
- 없으면 natural key fallback
- lineid/processid/stepseq/body/cham/snap_date 기준
- bulk upload row와 web row 모두 처리
