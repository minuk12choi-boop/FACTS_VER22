# Bulk Upload 규칙

## 유지할 기능

Excel bulk upload는 신규등록뿐 아니라 기존값 수정/삭제를 지원해야 합니다.

컬럼:

- 호환계획_ACTION: UPSERT / DELETE
- 호환계획_ID
- 미등록TIP호환Path_ACTION: UPSERT / DELETE
- 미등록TIP호환Path_ID

## 매칭 기준

- ID가 있으면 ID 우선
- ID가 없으면 natural key fallback
- natural key 예: snap_date, lineid, processid, stepseq, eqp_body_name, eqp_cham_name

## 이력

bulk upload가 단일 `bulk_upload` 이력으로만 남아 detail replay에서 누락되면 안 됩니다.

필요 action:

- plan_add
- plan_update
- plan_delete
- tip_missing_add
- tip_missing_update
- tip_missing_delete

## 팝업 정합성

bulk upload로 등록/수정된 값은 PRP TABLE 팝업과 본문 summary 양쪽에 보여야 합니다.
