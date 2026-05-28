# VOC 게시판 규칙

## 기본 기능

- SSO login 사용자 글 작성
- 목록/작성/상세
- 작성자 userid, department 표시
- `_check_page_permission(request, "voc", ...)`
- `_record_access_history(request, "voc")`
- 사이드바 위치: MAIN > 변경 이력 확인 아래

## 댓글

`FactsVocComment` 사용.

- post FK
- username
- department
- content
- created_at
- is_active

## 공식답변

관리자만 작성 가능. 현재 기본 기준은 `is_staff` 또는 `is_superuser`입니다. 프로젝트 권한체계상 voc edit 연동이 적합하면 명확히 판단 근거를 보고합니다.

## 공식답변 상태

상태 master는 기준정보에서 관리 가능해야 합니다.

기본값:

- 답변 확인
- 적용 검토
- 적용 예정
- 적용 완료

공식답변 상태가 없으면 VOC 목록 상태는 `확인대기`입니다.

상태 badge는 시각적으로 강조하고, 목록 컬럼은 가운데 정렬합니다.

## 공지사항

- 관리자만 작성 가능
- 목록 최상단
- 공지끼리는 최신순
- 일반 사용자가 POST 조작해도 서버에서 무시

## VOC 테이블 미존재 처리

migration 적용 전에도 500으로 죽지 않고 안내 메시지를 표시합니다.
