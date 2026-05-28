# FACTS Codex Harness

이 파일은 Codex가 FACTS 저장소에서 작업할 때 가장 먼저 읽어야 하는 목차입니다. 자세한 규칙은 `docs/codex/` 아래 문서를 참조합니다.

## 반드시 지킬 원칙

1. FACTS는 사내 실제 서비스 중인 Django WEB입니다. 기존 기능, 기존 URL, 권한, SSO, 팝업, 업로드/다운로드, 계산 결과 의미를 훼손하지 않습니다.
2. 요청사항을 절대 임의로 skip하지 않습니다. 막히면 보고서 최상단에 `미완료 / 차단 사유 / 필요 확인사항`을 명시합니다.
3. `다음 단계에서 처리`, `추후 개선 가능`, `이번 범위 외`라는 식으로 임의 판단하지 않습니다.
4. 운영 `config/settings.py`는 명시 요청 없이는 수정하지 않습니다.
5. 운영 DB에 migrate를 실행하지 않습니다. migration 파일 생성과 검증까지만 수행합니다.
6. 백업 파일(`.bak`, `_old`, `_backup`)을 만들지 않습니다.
7. 사내 PC 검증 안내에 `git pull`을 기본 명령으로 넣지 않습니다. 사용자는 Codex 결과물을 직접 받아 적용합니다.
8. 결과 보고와 Codex 작업 설명은 한국어로 작성합니다.

## 문서 맵

- `docs/codex/PROJECT_RULES.md`: 프로젝트 고정 원칙
- `docs/codex/ARCHITECTURE.md`: 구조와 분할 원칙
- `docs/codex/VALIDATION_RULES.md`: 검증 명령과 실패 처리
- `docs/codex/DB_MIGRATION_RULES.md`: DB/migration 규칙
- `docs/codex/UI_STATIC_RULES.md`: UI, static, WhiteNoise 규칙
- `docs/codex/DASHBOARD_RULES.md`: 대시보드/그래프/PRP TABLE 규칙
- `docs/codex/FILTER_RULES.md`: 필터 종속성 및 검색형 드롭다운 규칙
- `docs/codex/BULK_UPLOAD_RULES.md`: Excel bulk upload 규칙
- `docs/codex/VOC_RULES.md`: VOC 게시판 규칙
- `docs/codex/BATCH_PRECOMPUTE_RULES.md`: Windows Scheduler, PRP_COMPATIBILITY, 사전계산 규칙
- `docs/codex/KNOWN_ISSUES.md`: 현재 미해결/재발 주의 이슈
- `docs/codex/WORK_LOG_RULES.md`: feedback_log 작성 규칙
- `docs/codex/PROMPT_TEMPLATE.md`: Codex 작업 프롬프트 템플릿

Codex는 작업 전 해당 작업과 관련 있는 문서만 읽고, 작업 후 검증 로그와 변경 요약을 남깁니다.
