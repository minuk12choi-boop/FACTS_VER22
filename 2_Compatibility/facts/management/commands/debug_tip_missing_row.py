from django.core.management.base import BaseCommand
from datetime import datetime

from facts.debug_logging import try_save_feedback_log
from facts.service_modules.dashboard_rows import build_step_dataset
from facts.service_modules.tip_missing import _build_tip_missing_summary_map, get_tip_missing_detail_rows_as_of
from facts.service_modules.plan_detail import _step_group_key


class Command(BaseCommand):
    help = "TIP 미등록 PATH 디버그 파일 로그 생성"

    def add_arguments(self, parser):
        parser.add_argument("--snap-date", required=True)
        parser.add_argument("--lineid", required=True)
        parser.add_argument("--processid", required=True)
        parser.add_argument("--stepseq", required=False, default="")
        parser.add_argument("--recipeid", required=False, default="")
        parser.add_argument("--find-mismatch", action="store_true")

    def handle(self, *args, **options):
        snap_date = datetime.strptime(options["snap_date"], "%Y-%m-%d").date()
        lineid = (options["lineid"] or "").strip()
        processid = (options["processid"] or "").strip()
        stepseq = (options["stepseq"] or "").strip()
        recipeid = (options.get("recipeid") or "").strip()
        find_mismatch = bool(options.get("find_mismatch"))

        rows = build_step_dataset(snap_date, lineid=lineid, processid=processid)
        step_keys = {(lineid, processid, str(r.get("stepseq") or "").strip()) for r in rows if str(r.get("stepseq") or "").strip()}
        summary_map = _build_tip_missing_summary_map(snap_date, step_keys, as_of_date=snap_date)

        if find_mismatch:
            mismatch_rows = []
            for row in rows:
                step = str(row.get("stepseq") or "").strip()
                if not step:
                    continue
                key = _step_group_key(lineid, processid, step)
                summary = summary_map.get(key) or {}
                popup_rows = get_tip_missing_detail_rows_as_of(snap_date, lineid, processid, step)
                popup_count = len(popup_rows)
                if popup_count <= 0:
                    continue
                final_flag = str(row.get("tip_missing_flag") or "N")
                if final_flag == "Y":
                    continue
                mismatch_rows.append({
                    "lineid": lineid,
                    "processid": processid,
                    "stepseq": step,
                    "recipeid": str(row.get("recipeid") or ""),
                    "popup_rows_count": popup_count,
                    "final_tip_missing_flag": final_flag,
                    "final_tip_missing_body": str(row.get("tip_missing_body") or ""),
                    "final_tip_missing_cham": str(row.get("tip_missing_cham") or ""),
                    "final_eqpgroup_html_has_manual": "manual-path" in str(row.get("eqpgroup_html") or ""),
                    "final_cham_html_has_manual": "manual-path" in str(row.get("cham_html") or ""),
                    "has_summary_key": bool(summary),
                })
            mismatch_rows = mismatch_rows[:20]
            lines = [
                f"input args=snap_date:{snap_date}, lineid:{lineid}, processid:{processid}, stepseq:{stepseq}, recipeid:{recipeid}, find_mismatch:{find_mismatch}",
                "mode=find-mismatch",
                f"popup/detail source query 조건=snap_date<={snap_date}, lineid={lineid}, processid={processid}, stepseq=each-row",
                f"build_step_dataset rows count={len(rows)}",
                "summary map key 방식=_step_group_key(lineid, processid, stepseq)",
                "row lookup key 방식=_step_group_key(lineid, processid, stepseq)",
                f"mismatch count={len(mismatch_rows)}",
                f"mismatch sample(max20)={mismatch_rows}",
                "원인 추정=key mismatch / recipeid mismatch / as_of_date mismatch / is_active mismatch / render missing",
            ]
            saved = try_save_feedback_log("tip_missing_debug", "\n".join(lines), "TIP_MISSING_DEBUG")
            self.stdout.write(f"mismatch_count={len(mismatch_rows)}")
            self.stdout.write(f"log_path={saved or ''}")
            return

        if not stepseq:
            raise ValueError("--stepseq 또는 --find-mismatch 중 하나는 반드시 필요합니다.")

        detail_rows = get_tip_missing_detail_rows_as_of(snap_date, lineid, processid, stepseq)
        matched = [r for r in rows if str(r.get("stepseq") or "").strip() == stepseq]
        if recipeid:
            matched = [r for r in matched if recipeid in str(r.get("recipeid") or "")]

        lines = [
            f"input args=snap_date:{snap_date}, lineid:{lineid}, processid:{processid}, stepseq:{stepseq}, recipeid:{recipeid}, find_mismatch:{find_mismatch}",
            "mode=single step",
            f"popup/detail API source query 조건=snap_date<={snap_date}, lineid={lineid}, processid={processid}, stepseq={stepseq}",
            f"popup/detail source rows count={len(detail_rows)}",
            f"popup/detail rows 요약={detail_rows[:20]}",
            f"_build_tip_missing_summary_map 호출 조건=step_keys_count={len(step_keys)}, as_of_date={snap_date}",
            f"summary map key={list(summary_map.keys())}",
            f"build_step_dataset rows count={len(rows)}",
            f"build_step_dataset row key filter=(lineid,processid,stepseq)=({lineid},{processid},{stepseq})",
            f"matched row count={len(matched)}",
            "summary map key 방식=_step_group_key(lineid, processid, stepseq)",
            "row lookup key 방식=_step_group_key(lineid, processid, stepseq)",
        ]
        for idx, row in enumerate(matched, start=1):
            lines.extend([
                f"[{idx}] final row tip_missing_flag={row.get('tip_missing_flag')}",
                f"[{idx}] final row tip_missing_always={row.get('tip_missing_always')}",
                f"[{idx}] final row tip_missing_major={row.get('tip_missing_major')}",
                f"[{idx}] final row tip_missing_body={row.get('tip_missing_body')}",
                f"[{idx}] final row tip_missing_cham={row.get('tip_missing_cham')}",
                f"[{idx}] final row eqpgroup_html contains manual body 여부={'manual-path' in str(row.get('eqpgroup_html') or '')}",
                f"[{idx}] final row cham_html contains manual cham 여부={'manual-path' in str(row.get('cham_html') or '')}",
                f"[{idx}] active/history source 조건 비교=snap_date/as_of_date/lineid/processid/stepseq/recipeid 점검 필요",
            ])

        lines.append("snap_date/as_of_date/is_active/lineid/processid/stepseq/recipeid 차이=상세 로그에서 수동 확인")
        try_save_feedback_log("tip_missing_debug", "\n".join(lines), "TIP_MISSING_DEBUG")
