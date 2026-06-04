# 기준정보 페이지 행추가/선택삭제 재점검 및 실제 수정 (main 기준 재작업 요청 반영)

## 1. 재점검 시작 사유
- 이전 작업에서 기준정보(master) 페이지 템플릿 누락으로 원인 확정 및 수정이 불가했음.
- 이번에는 HTML 템플릿 재업로드 이후 상태를 기준으로 다시 점검함.

## 2. 새로 확인된 기준정보 템플릿/JS 파일
- 템플릿: `templates/facts/master.html`
- 뷰/API: `facts/view_modules/master.py` (`master_view`, `bulk_stage_save`, `bulk_line_save` 등 action 분기)
- 정적 JS: master 페이지는 별도 외부 JS가 아니라 `master.html` 하단 inline script에서 버튼 이벤트를 직접 바인딩함.

## 3. 실제 원인
- `templates/facts/master.html`의 부서권한(dept) 행추가 템플릿 문자열 내부에 JS 템플릿 리터럴 구문 오류가 존재.
- 구체적으로, `deptAddRowBtn` 클릭 핸들러에서 새 행 HTML 생성 시 `[...] .map(...
  )` 표현이 `${ ... }` 보간 없이 문자열에 직접 들어가 있어 백틱 파싱이 깨짐.
- 이 구문 오류로 인해 해당 `<script>` 전체 실행이 중단되어, 행추가/선택삭제 이벤트 바인딩이 실패.
- 반면 최종저장은 submit 기반 동작이라 상대적으로 정상 동작하는 것처럼 보일 수 있음.

## 4. 수정한 파일
- `templates/facts/master.html`

## 5. 수정 내용
- 부서권한 행추가 템플릿의 `dept-page-perm-grid` 생성부를 올바른 보간식으로 변경:
  - 기존: `[...] .map(...).join("")` 텍스트가 그대로 들어가던 형태
  - 수정: `${[...].map(...).join("")}` 형태로 보간 처리
- 변경 범위는 해당 문자열 구간 1곳으로 최소화.
- 기존 최종저장 submit/hidden action/post 구조는 변경하지 않음.

## 6. 최종저장 기존 동작 유지 확인
- 템플릿 폼 구조(`method=post`, `action hidden input`, submit 버튼)는 미수정.
- 저장 action 분기(`bulk_*_save`) 로직 파일도 미수정.
- 따라서 최종저장 기존 동작 경로는 유지됨.

## 7. 검증 명령 결과
- `python manage.py check` → 실패 (환경에 django 미설치)
- `python -m compileall config facts` → 성공
- HTML/JS 수동 점검: 수정 구문의 템플릿 리터럴/보간 균형 정상 확인.

## 8. 브라우저 수동 검증 결과
- 본 실행 환경에서는 브라우저 수동검증 미실시.
- 운영 반영 전 브라우저에서 행추가/선택삭제/최종저장 회귀 확인 필요.

## 9. 남은 위험 요소
- master 페이지 script가 inline 단일 블록 구조이므로, 다른 구문 오류가 추가되면 전체 이벤트 바인딩이 다시 중단될 수 있음.
- 권장: 배포 전 해당 페이지 JS lint 또는 최소한 브라우저 콘솔 무에러 확인.
