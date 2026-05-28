# Filter UI 및 종속성 규칙

## Searchable dropdown

기본은 드롭다운입니다. 드롭다운 내부에서 텍스트 검색이 가능해야 합니다.

금지:

- datalist 의존
- input 따로 select 따로 어색하게 보이는 구조
- option 목록 평문 노출
- startsWith 검색만 지원

필수:

```javascript
optionText.toLowerCase().includes(keyword.toLowerCase())
```

대상:

- Dashboard PRP TABLE PRP
- Dashboard PRP TABLE STEP
- PREVENT PRP
- HISTORY PRP

## Multi layer dropdown

- `select multiple`은 hidden 처리
- 사용자에게는 trigger + panel + checkbox list만 표시
- 기본 상태에서 option 노출 금지
- 전체 선택과 실제 option 목록 혼동 금지

## 성능

- dropdown open 시 서버 호출 금지
- 이미 받은 option은 즉시 표시
- 서버 option refresh는 필요 시 background 처리
- 동일 조건 API 중복 호출 금지
- in-flight guard 사용
- debounce 사용

## PREVENT/HISTORY 필터

대시보드에서 만든 검색형 컴포넌트를 재사용합니다. 버튼식 UI 금지.
