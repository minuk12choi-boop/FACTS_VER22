from datetime import datetime
from pathlib import Path

from django.core.cache import cache
from django.core.management.base import BaseCommand

from facts.models import FactsEditHistory, FactsTipMissingCompatPath, FactsWipSource
from facts.service_modules.dashboard_rows import build_step_dataset, get_build_step_dataset_debug_info
from facts.service_modules.plan_detail import _as_of_cutoff, _as_of_date, _step_group_key
from facts.service_modules.tip_missing import _classify_bulk_payload_type, _history_payload_matches_tip_missing, _tip_missing_path_identity


class Command(BaseCommand):
    help = "PRP TABLE row 생성/렌더 디버그 로그 파일 생성"

    def add_arguments(self, parser):
        parser.add_argument("--snap-date", required=True)
        parser.add_argument("--lineid", required=True)
        parser.add_argument("--processid", required=True)
        parser.add_argument("--stepseq", default="")
        parser.add_argument("--recipeid", default="")
        parser.add_argument("--find-tip-missing", action="store_true")
        parser.add_argument("--show-sources", action="store_true")
        parser.add_argument("--no-include-measure", action="store_true")
        parser.add_argument("--no-include-emergency", action="store_true")
        parser.add_argument("--include-skiprule-100", action="store_true")
        parser.add_argument("--no-tip-mode", action="store_true")
        parser.add_argument("--as-of-date", default="")

    def handle(self, *args, **options):
        snap_date = datetime.strptime(options["snap_date"], "%Y-%m-%d").date()
        lineid = (options["lineid"] or "").strip()
        processid = (options["processid"] or "").strip()
        stepseq = (options.get("stepseq") or "").strip()
        recipeid = (options.get("recipeid") or "").strip()
        find_tip_missing = bool(options.get("find_tip_missing"))
        show_sources = bool(options.get("show_sources"))

        include_measure = not bool(options.get("no_include_measure"))
        include_emergency = not bool(options.get("no_include_emergency"))
        exclude_skiprule_100 = not bool(options.get("include_skiprule_100"))
        tip_mode = not bool(options.get("no_tip_mode"))
        as_of_date_opt = (options.get("as_of_date") or "").strip()
        as_of_date = datetime.strptime(as_of_date_opt, "%Y-%m-%d").date() if as_of_date_opt else snap_date

        dataset_kwargs = {
            "snap_date": snap_date,
            "lineid": lineid,
            "processid": processid,
            "areaname": None,
            "layerid": None,
            "compat_filter": "all",
            "include_measure": include_measure,
            "include_emergency": include_emergency,
            "exclude_skiprule_100": exclude_skiprule_100,
            "tip_mode": tip_mode,
            "for_prp_table": True,
            "as_of_date": as_of_date,
        }
        debug_info = get_build_step_dataset_debug_info(**dataset_kwargs)
        rows = build_step_dataset(**dataset_kwargs)
        lines = [
            "source=debug_command",
            f"input args=snap_date:{snap_date}, lineid:{lineid}, processid:{processid}, stepseq:{stepseq}, recipeid:{recipeid}, find_tip_missing:{find_tip_missing}",
            f"target_snap_date={snap_date}",
            f"build_step_dataset_args={debug_info['cache_key_parts']}",
            f"build_step_dataset_cache_key={debug_info['cache_key']}",
            f"build_step_dataset_cache_hit={cache.get(debug_info['cache_key']) is not None}",
            f"build_step_dataset rows count={len(rows)}",
            f"tip_missing_summary_func_module={_classify_bulk_payload_type.__module__}",
            f"tip_missing_summary_func_file={Path(__import__('facts.service_modules.tip_missing', fromlist=['x']).__file__).resolve()}",
            f"plan_summary_func_module={_as_of_cutoff.__module__}",
            f"plan_summary_func_file={Path(__import__('facts.service_modules.plan_detail', fromlist=['x']).__file__).resolve()}",
            "row key format=_step_group_key(lineid, processid, stepseq)",
        ]

        if find_tip_missing:
            samples = [r for r in rows if str(r.get("tip_missing_flag") or "N") == "Y"][:20]
            lines.append(f"tip_missing_sample_count={len(samples)}")
            for idx, row in enumerate(samples, start=1):
                lines.extend(self._row_lines(idx, row, lineid, processid))
        else:
            if not stepseq:
                raise ValueError("--find-tip-missing 미사용 시 --stepseq는 필수입니다.")
            matched = [r for r in rows if str(r.get("stepseq") or "").strip() == stepseq]
            if recipeid:
                matched = [r for r in matched if recipeid in str(r.get("recipeid") or "")]
            lines.append(f"matched row count={len(matched)}")
            for idx, row in enumerate(matched, start=1):
                lines.extend(self._row_lines(idx, row, lineid, processid))
                if show_sources:
                    lines.extend(self._show_sources_lines(snap_date, lineid, processid, str(row.get("stepseq") or "").strip(), row))

        log_dir = Path("feedback_log")
        log_dir.mkdir(parents=True, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        out_path = log_dir / f"prp_table_row_debug_{ts}.txt"
        out_path.write_text("\n".join(lines), encoding="utf-8")
        self.stdout.write(str(out_path))

    def _show_sources_lines(self, snap_date, lineid, processid, stepseq, row):
        cutoff = _as_of_cutoff(snap_date)
        key = _step_group_key(lineid, processid, stepseq)
        source_exists = FactsWipSource.objects.filter(
            snap_date=snap_date, lineid=lineid, processid=processid, stepseq=stepseq
        ).exists()
        supported_actions = {"tip_missing_add", "tip_missing_update", "tip_missing_delete", "plan_add", "plan_update", "plan_delete", "override", "bulk_upload"}
        tip_missing_actions = {"tip_missing_add", "tip_missing_update", "tip_missing_delete", "bulk_upload"}

        lines = [
            f"target_snap_date={snap_date}",
            f"source_step_exists={source_exists}",
            f"plan_summary={row.get('plan_summary')}",
            f"tip_missing_summary={{'body': {row.get('tip_missing_body')}, 'cham': {row.get('tip_missing_cham')}}}",
            f"override_manual_always_emergency={row.get('final_always_emergency')}",
            f"override_manual_major_minor={row.get('final_major_minor')}",
            f"debug_step_key={key}",
        ]

        candidates = []
        active_qs = FactsTipMissingCompatPath.objects.filter(
            lineid=lineid, processid=processid, stepseq=stepseq, snap_date__lte=snap_date
        ).order_by("snap_date", "id")
        for obj in active_qs:
            excluded_reason = ""
            if obj.snap_date and obj.snap_date > snap_date:
                excluded_reason = "snap_date_after_target"
            elif not obj.is_active:
                excluded_reason = "inactive"
            elif cutoff is not None and obj.created_at and obj.created_at > cutoff:
                excluded_reason = "created_after_cutoff"
            elif cutoff is not None and obj.updated_at and obj.updated_at > cutoff:
                excluded_reason = "updated_after_cutoff"
            elif not source_exists:
                excluded_reason = "source_step_missing"
            candidates.append(self._candidate_row("active", obj, "", excluded_reason))

        history_qs = FactsEditHistory.objects.filter(
            lineid=lineid,
            processid=processid,
            stepseq=stepseq,
            action_type__in=list(supported_actions),
            created_at__lte=cutoff,
        ).order_by("created_at", "id")
        for h in history_qs:
            payload_after = h.after_json or {}
            payload_before = h.before_json or {}
            payload = payload_after or payload_before or {}
            payload_type = "override" if h.action_type == "override" else "unknown"
            if h.action_type in {"plan_add", "plan_update", "plan_delete"}:
                payload_type = "plan"
            elif h.action_type in {"tip_missing_add", "tip_missing_update", "tip_missing_delete"}:
                payload_type = "tip_missing"
            elif h.action_type == "bulk_upload":
                payload_type = _classify_bulk_payload_type(payload_before, payload_after)

            excluded_reason = ""
            if h.action_type not in supported_actions:
                excluded_reason = "action_type_not_supported"
            elif h.action_type in {"plan_add", "plan_update", "plan_delete"}:
                excluded_reason = "not_tip_missing_action"
            elif h.action_type == "bulk_upload" and payload_type == "plan":
                excluded_reason = "bulk_payload_type_plan"
            elif h.action_type == "bulk_upload" and payload_type == "unknown":
                excluded_reason = "bulk_payload_type_unknown"
            elif h.action_type in tip_missing_actions and h.action_type != "tip_missing_delete" and not _history_payload_matches_tip_missing(payload):
                excluded_reason = "not_tip_missing_payload"
            elif _as_of_date(h.snap_date) and _as_of_date(h.snap_date) > snap_date:
                excluded_reason = "future_effective_snap"
            elif h.lineid != lineid:
                excluded_reason = "lineid_mismatch"
            elif h.processid != processid:
                excluded_reason = "processid_mismatch"
            elif h.stepseq != stepseq:
                excluded_reason = "stepseq_mismatch"
            elif not source_exists:
                excluded_reason = "source_step_missing"
            candidates.append(self._candidate_row("history", h, h.action_type, excluded_reason, payload=payload, payload_type=payload_type))

        included = [c for c in candidates if not c["excluded_reason"]]
        excluded = [c for c in candidates if c["excluded_reason"]]

        active_candidates = [x for x in candidates if x["source"] == "active"]
        history_candidates = [x for x in candidates if x["source"] == "history"]

        lines.append("active candidate rows:")
        for c in active_candidates:
            lines.append(self._fmt_candidate(c))
        lines.append("history candidate rows:")
        for c in history_candidates:
            lines.append(self._fmt_candidate(c))
        lines.append("included rows:")
        for c in included:
            lines.append(self._fmt_candidate(c))
        lines.append("excluded rows:")
        for c in excluded:
            lines.append(self._fmt_candidate(c))
        active_keys = [c["path_identity_key"] for c in active_candidates if c.get("path_identity_key")]
        history_keys = [c["path_identity_key"] for c in history_candidates if c.get("path_identity_key")]
        lines.append(f"active_candidate_path_identity_keys={active_keys}")
        lines.append(f"history_candidate_path_identity_keys={history_keys}")

        replay_state = {}
        removed_keys = []
        for c in active_candidates:
            if not c["excluded_reason"] and c.get("path_identity_key"):
                replay_state[c["path_identity_key"]] = c
        for c in history_candidates:
            if c["excluded_reason"]:
                continue
            action_type = str(c.get("action_type") or "").strip()
            is_delete = action_type == "tip_missing_delete" or (
                action_type == "bulk_upload" and str(c.get("is_active") or "").strip().lower() in {"0", "false", "n", "no"}
            )
            before_key = c.get("before_path_identity_key")
            after_key = c.get("path_identity_key")
            if is_delete:
                delete_key = before_key or after_key
                if action_type == "bulk_upload":
                    c["excluded_reason"] = c.get("excluded_reason") or "bulk_payload_inactive_delete"
                if delete_key and delete_key in replay_state:
                    replay_state.pop(delete_key, None)
                    removed_keys.append(delete_key)
                elif not delete_key:
                    c["skipped_reason"] = "delete_identity_missing"
                continue
            if action_type == "tip_missing_update" and before_key and after_key and before_key != after_key:
                if before_key in replay_state:
                    replay_state.pop(before_key, None)
                    removed_keys.append(before_key)
            if after_key:
                replay_state[after_key] = c
            elif before_key:
                replay_state.pop(before_key, None)
            else:
                c["skipped_reason"] = "identity_missing"
        lines.append(f"replay_survived_path_identity_keys={list(replay_state.keys())}")
        lines.append(f"replay_removed_path_identity_keys={removed_keys}")

        final_body_list = [x.strip() for x in str(row.get("tip_missing_body") or "").split(" | ") if x.strip()]
        final_cham_list = [x.strip() for x in str(row.get("tip_missing_cham") or "").split(" | ") if x.strip()]
        lines.append(f"final_manual_body_list={final_body_list}")
        lines.append(f"final_manual_cham_list={final_cham_list}")
        lines.append(f"final_manual_path_objects_count={len(replay_state)}")
        lines.append(f"final_manual_path_objects_detail={[replay_state[k] for k in replay_state]}")
        if len(set(active_keys)) > 1 and len(final_body_list) <= 1:
            lines.append("WARNING: multiple active tip-missing rows collapsed to one summary entry")
        lines.append("excluded_reason_reference=future_effective_snap,inactive,deleted_before_target,key_mismatch,source_step_missing,action_type_not_supported,snap_date_after_target,created_after_cutoff,updated_after_cutoff,lineid_mismatch,processid_mismatch,stepseq_mismatch,delete_identity_missing,identity_missing")
        return lines

    def _candidate_row(self, source, obj, action_type, excluded_reason, payload=None, payload_type="unknown"):
        payload = payload or {}
        lineid = str(payload.get("lineid") or getattr(obj, "lineid", "") or "")
        processid = str(payload.get("processid") or getattr(obj, "processid", "") or "")
        stepseq = str(payload.get("stepseq") or getattr(obj, "stepseq", "") or "")
        step_key = _step_group_key(lineid, processid, stepseq)
        fallback_id = getattr(obj, "id", None)
        after_payload = payload if source == "history" else {
            "id": getattr(obj, "id", ""),
            "recipeid": getattr(obj, "recipeid", ""),
            "always_emergency": getattr(obj, "always_emergency", ""),
            "major_minor": getattr(obj, "major_minor", ""),
            "eqp_body_name": getattr(obj, "eqp_body_name", ""),
            "eqp_cham_name": getattr(obj, "eqp_cham_name", ""),
        }
        before_payload = (getattr(obj, "before_json", {}) or {}) if source == "history" else after_payload
        return {
            "source": source,
            "history_id": getattr(obj, "id", "") if source == "history" else "",
            "id": getattr(obj, "id", ""),
            "snap_date": getattr(obj, "snap_date", ""),
            "lineid": lineid,
            "processid": processid,
            "stepseq": stepseq,
            "recipeid": str(payload.get("recipeid") or getattr(obj, "recipeid", "") or ""),
            "is_active": payload.get("is_active", getattr(obj, "is_active", "")),
            "action_type": action_type,
            "always_emergency": str(payload.get("always_emergency") or getattr(obj, "always_emergency", "") or ""),
            "major_minor": str(payload.get("major_minor") or getattr(obj, "major_minor", "") or ""),
            "eqp_body_name": str(payload.get("eqp_body_name") or getattr(obj, "eqp_body_name", "") or ""),
            "eqp_cham_name": str(payload.get("eqp_cham_name") or getattr(obj, "eqp_cham_name", "") or ""),
            "created_at": getattr(obj, "created_at", ""),
            "updated_at": getattr(obj, "updated_at", ""),
            "included": not bool(excluded_reason),
            "excluded_reason": excluded_reason,
            "payload_type": payload_type,
            "path_identity_key": str(_tip_missing_path_identity(step_key, after_payload, fallback_id=fallback_id)) if after_payload else "",
            "before_path_identity_key": str(_tip_missing_path_identity(step_key, before_payload, fallback_id=fallback_id)) if before_payload else "",
        }

    def _fmt_candidate(self, c):
        return (
            f"- source={c['source']} history_id={c.get('history_id', '')} id={c['id']} snap_date={c['snap_date']} lineid={c['lineid']} processid={c['processid']} "
            f"stepseq={c['stepseq']} recipeid={c['recipeid']} is_active={c['is_active']} action_type={c['action_type']} "
            f"always_emergency={c['always_emergency']} major_minor={c['major_minor']} eqp_body_name={c['eqp_body_name']} "
            f"eqp_cham_name={c['eqp_cham_name']} created_at={c['created_at']} updated_at={c['updated_at']} included={c['included']} excluded_reason={c['excluded_reason']} "
            f"payload_type={c.get('payload_type','unknown')} path_identity_key={c.get('path_identity_key', '')} before_path_identity_key={c.get('before_path_identity_key', '')} skipped_reason={c.get('skipped_reason', '')}"
        )

    def _row_lines(self, idx, row, lineid, processid):
        step = str(row.get("stepseq") or "").strip()
        key = _step_group_key(lineid, processid, step)
        override_cnt = len(row.get("override_target_list") or [])
        eqpgroup_html = str(row.get("eqpgroup_html") or "")
        cham_html = str(row.get("cham_html") or "")
        tip_missing_body = str(row.get("tip_missing_body") or "")
        tip_missing_cham = str(row.get("tip_missing_cham") or "")
        has_manual_body = ("manual-added-text" in eqpgroup_html) or (tip_missing_body and tip_missing_body in eqpgroup_html)
        has_manual_cham = ("manual-added-text" in cham_html) or (tip_missing_cham and tip_missing_cham in cham_html)
        return [
            f"[{idx}] key={key}",
            f"[{idx}] stepseq={step}",
            f"[{idx}] recipeid={row.get('recipeid')}",
            f"[{idx}] tip_missing_flag={row.get('tip_missing_flag')}",
            f"[{idx}] tip_missing_always={row.get('tip_missing_always')}",
            f"[{idx}] tip_missing_major={row.get('tip_missing_major')}",
            f"[{idx}] tip_missing_body={row.get('tip_missing_body')}",
            f"[{idx}] tip_missing_cham={row.get('tip_missing_cham')}",
            f"[{idx}] eqpgroup={row.get('eqpgroup')}",
            f"[{idx}] eqpgroup_html={eqpgroup_html}",
            f"[{idx}] cham_display={row.get('cham_display')}",
            f"[{idx}] cham_html={cham_html}",
            f"[{idx}] override_target_list_count={override_cnt}",
            f"[{idx}] has_manual_body_in_eqpgroup_html={has_manual_body}",
            f"[{idx}] has_manual_cham_in_cham_html={has_manual_cham}",
        ]
