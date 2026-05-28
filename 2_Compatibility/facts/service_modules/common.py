import csv
import html
import re
from collections import defaultdict
from datetime import date, datetime, timedelta
from collections import Counter
from difflib import SequenceMatcher
from io import StringIO

from django.core.cache import cache
from django.db.models import Count, Max, Q
import json
from ..models import (
    FactsDashboardConfig,
    FactsEqpModel,
    FactsKpiTarget,
    FactsStepPathOverride,
    FactsStepPlan,
    FactsTipMissingCompatPath,
    FactsWipSource,
    FactsPreventRuleMaster,
    FactsEditHistory,
    FactsFilterCache,
    FactsFilterOptionCache
)

FACTS_ACTION_TYPE_LABELS = {
    "override": "스텝수정",
    "plan_add": "호환계획 추가",
    "plan_update": "호환계획 수정",
    "plan_delete": "호환계획 삭제",
    "tip_missing_add": "TIP미등록 호환Path 추가",
    "tip_missing_update": "TIP미등록 호환Path 수정",
    "tip_missing_delete": "TIP미등록 호환Path 삭제",
    "bulk_upload": "엑셀 업로드 반영",
    "dashboard_config_update": "대시보드 기준정보 수정",
    "guide_upload": "가이드 업로드",
    "guide_path_save": "가이드 경로 저장",
    "master_add": "필요평가단계 추가",
    "master_update": "필요평가단계 수정",
    "master_delete": "필요평가단계 삭제",
    "line_master_add": "라인 기준정보 추가",
    "line_master_update": "라인 기준정보 수정",
    "line_master_delete": "라인 기준정보 삭제",
    "kpi_add": "KPI 추가",
    "kpi_update": "KPI 수정/삭제",
    "prevent_rule_add": "PREVENT 기준정보 추가",
    "prevent_rule_update": "PREVENT 기준정보 수정",
    "prevent_rule_delete": "PREVENT 기준정보 삭제",
    "dept_permission_add": "부서권한 기준정보 추가",
    "dept_permission_update": "부서권한 기준정보 수정",
    "dept_permission_delete": "부서권한 기준정보 삭제",
}

ACTION_TYPE_LABELS = FACTS_ACTION_TYPE_LABELS.copy()


def normalize_layer_value(value):
    from .dashboard_filters import normalize_layer_value as _impl
    return _impl(value)


def _natural_sort_key(value):
    from .dashboard_filters import _natural_sort_key as _impl
    return _impl(value)


def _extract_cham_tokens(raw_values):
    from .bulk_upload import _extract_cham_tokens as _impl
    return _impl(raw_values)


def _compact_cham_tokens(tokens):
    from .bulk_upload import _compact_cham_tokens as _impl
    return _impl(tokens)


def _parse_eqpgroup_tokens(eqpgroup_text):
    from .bulk_upload import _parse_eqpgroup_tokens as _impl
    return _impl(eqpgroup_text)


def _flatten_body_values(values):
    from .bulk_upload import _flatten_body_values as _impl
    return _impl(values)


def _path_signature(row):
    from .bulk_upload import _path_signature as _impl
    return _impl(row)


def classify_compat_type(recipe_value, merged_eqps, body_flag, cham_flag):
    from .dashboard_rows import classify_compat_type as _impl
    return _impl(recipe_value, merged_eqps, body_flag, cham_flag)


def get_current_prevent_rule():
    from .dashboard_rows import get_current_prevent_rule as _impl
    return _impl()


def _as_of_cutoff(as_of_date):
    from .plan_detail import _as_of_cutoff as _impl
    return _impl(as_of_date)


def _as_of_date(value):
    from .plan_detail import _as_of_date as _impl
    return _impl(value)


def summarize_steps(step_rows, use_tip=False):
    from .dashboard_rows import summarize_steps as _impl
    return _impl(step_rows, use_tip=use_tip)


def _base_source_queryset(
    snap_date,
    processid=None,
    areaname=None,
    layerid=None,
    lineid=None,
    include_measure=True,
    exclude_skiprule_100=False,
):
    qs = FactsWipSource.objects.filter(snap_date=snap_date)

    if processid:
        qs = qs.filter(processid=processid)
    if areaname:
        qs = qs.filter(areaname=areaname)
    if lineid:
        qs = qs.filter(lineid=lineid)
    if not include_measure:
        qs = qs.exclude(stepseq_type="계측")
    if exclude_skiprule_100:
        qs = qs.exclude(skiprule="100")

    qs = qs.order_by("lineid", "processid", "stepseq", "recipeid", "path", "id")
    rows = list(qs)

    if layerid:
        if isinstance(layerid, (list, tuple, set)):
            layer_set = {normalize_layer_value(x) for x in layerid if normalize_layer_value(x)}
            if layer_set:
                rows = [r for r in rows if normalize_layer_value(r.layerid) in layer_set]
        else:
            layer_norm = normalize_layer_value(layerid)
            rows = [r for r in rows if normalize_layer_value(r.layerid) == layer_norm]

    return rows


def _build_step_key(row):
    return (row.lineid or "", row.processid or "", row.stepseq or "")


def _build_path_key(lineid, processid, stepseq, recipeid, path, eqpline, childeqp):
    return (
        lineid or "",
        processid or "",
        stepseq or "",
        recipeid or "",
        path or "",
        eqpline or "",
        childeqp or "",
    )


def _get_eqp_model_qs_by_snap_or_latest_load(snap_date):
    snap_qs = FactsEqpModel.objects.filter(snap_date=snap_date)
    if snap_qs.exists():
        return snap_qs

    latest_loaded_at = (
        FactsEqpModel.objects.exclude(loaded_at__isnull=True)
        .aggregate(max_loaded_at=Max("loaded_at"))
        .get("max_loaded_at")
    )
    if latest_loaded_at is None:
        return FactsEqpModel.objects.none()

    latest_load = (
        FactsEqpModel.objects.filter(loaded_at=latest_loaded_at)
        .exclude(load_id__isnull=True)
        .exclude(load_id="")
        .order_by("-id")
        .values("load_id")
        .first()
    )

    if latest_load and latest_load.get("load_id"):
        return FactsEqpModel.objects.filter(load_id=latest_load["load_id"])

    return FactsEqpModel.objects.filter(loaded_at=latest_loaded_at)


def _build_plan_summary(processid, stepseq, lineid=""):
    plan_qs = list(
        FactsStepPlan.objects.filter(
            processid=processid,
            stepseq=stepseq,
            lineid=lineid,
            is_active=True,
        ).select_related("required_eval_stage").order_by("-updated_at", "-id")
    )

    if not plan_qs:
        return {
            "plan_flag": "N",
            "plan_body_names": "",
            "plan_cham_names": "",
            "plan_due_dates": "",
            "plan_eval_lot_ids": "",
            "plan_eval_stages": "",
            "plan_memos": "",
            "has_plan": False,
        }

    def uniq_join(values):
        out = []
        for v in values:
            s = str(v or "").strip()
            if s and s not in out:
                out.append(s)
        return " | ".join(out)

    return {
        "plan_flag": "Y",
        "plan_body_names": uniq_join([x.eqp_body_name for x in plan_qs]),
        "plan_cham_names": uniq_join([x.eqp_cham_name for x in plan_qs]),
        "plan_due_dates": uniq_join([
            x.compatibility_due_date.strftime("%Y-%m-%d") if x.compatibility_due_date else ""
            for x in plan_qs
        ]),
        "plan_eval_lot_ids": uniq_join([x.eval_lot_id for x in plan_qs]),
        "plan_eval_stages": uniq_join([
            x.required_eval_stage.stage_name if x.required_eval_stage else ""
            for x in plan_qs
        ]),
        "plan_memos": uniq_join([x.memo for x in plan_qs]),
        "has_plan": True,
    }


def _build_tip_missing_summary(snap_date, processid, stepseq, lineid=""):
    qs = list(
        FactsTipMissingCompatPath.objects.filter(
            snap_date=snap_date,
            processid=processid,
            stepseq=stepseq,
            lineid=lineid,
            is_active=True,
        ).order_by("-updated_at", "-id")
    )
    if not qs:
        return {
            "tip_missing_flag": "N",
            "tip_missing_always": "",
            "tip_missing_major": "",
            "tip_missing_body": "",
            "tip_missing_cham": "",
            "manual_body_list": [],
            "manual_cham_list": [],
            "manual_path_objects": [],
        }

    def uniq_join(values):
        out = []
        for v in values:
            s = str(v or "").strip().upper()
            if s and s not in out:
                out.append(s)
        return " | ".join(out)

    manual_body_list = []
    manual_cham_list = []
    manual_path_objects = []

    for obj in qs:
        body = str(obj.eqp_body_name or "").strip().upper()
        cham = str(obj.eqp_cham_name or "").strip().upper()

        if body and body not in manual_body_list:
            manual_body_list.append(body)

        cham_token = ""
        if body and cham:
            cham_token = f"{body}-{cham}"
            if cham_token not in manual_cham_list:
                manual_cham_list.append(cham_token)

        manual_path_objects.append({
            "always_emergency": str(obj.always_emergency or "").strip(),
            "major_minor": str(obj.major_minor or "").strip(),
            "body": body,
            "cham": cham,
            "cham_token": cham_token,
        })

    return {
        "tip_missing_flag": "Y",
        "tip_missing_always": uniq_join([x.always_emergency for x in qs]),
        "tip_missing_major": uniq_join([x.major_minor for x in qs]),
        "tip_missing_body": uniq_join([x.eqp_body_name for x in qs]),
        "tip_missing_cham": uniq_join([x.eqp_cham_name for x in qs]),
        "manual_body_list": manual_body_list,
        "manual_cham_list": manual_cham_list,
        "manual_path_objects": manual_path_objects,
    }


def _empty_plan_summary():
    return {
        "plan_flag": "N",
        "plan_body_names": "",
        "plan_cham_names": "",
        "plan_due_dates": "",
        "plan_eval_lot_ids": "",
        "plan_eval_stages": "",
        "plan_memos": "",
        "has_plan": False,
    }


def _empty_tip_missing_summary():
    return {
        "tip_missing_flag": "N",
        "tip_missing_always": "",
        "tip_missing_major": "",
        "tip_missing_body": "",
        "tip_missing_cham": "",
        "manual_body_list": [],
        "manual_cham_list": [],
        "manual_path_objects": [],
    }


def _build_plan_summary_map(step_keys):
    valid_keys = {
        (l or "", p or "", s or "")
        for l, p, s in step_keys
        if (p or "") and (s or "")
    }
    if not valid_keys:
        return {}

    processids = sorted({p for _, p, _ in valid_keys})
    stepseqs = sorted({s for _, _, s in valid_keys})
    lineids = sorted({l for l, _, _ in valid_keys})

    qs = list(
        FactsStepPlan.objects.filter(
            processid__in=processids,
            stepseq__in=stepseqs,
            lineid__in=lineids,
            is_active=True,
        ).select_related("required_eval_stage").order_by("-updated_at", "-id")
    )

    grouped = defaultdict(list)
    for obj in qs:
        key = (obj.lineid or "", obj.processid or "", obj.stepseq or "")
        if key in valid_keys:
            grouped[key].append(obj)

    def uniq_join(values):
        out = []
        for v in values:
            s = str(v or "").strip()
            if s and s not in out:
                out.append(s)
        return " | ".join(out)

    result = {}
    for key, plan_qs in grouped.items():
        result[key] = {
            "plan_flag": "Y",
            "plan_body_names": uniq_join([x.eqp_body_name for x in plan_qs]),
            "plan_cham_names": uniq_join([x.eqp_cham_name for x in plan_qs]),
            "plan_due_dates": uniq_join([
                x.compatibility_due_date.strftime("%Y-%m-%d") if x.compatibility_due_date else ""
                for x in plan_qs
            ]),
            "plan_eval_lot_ids": uniq_join([x.eval_lot_id for x in plan_qs]),
            "plan_eval_stages": uniq_join([
                x.required_eval_stage.stage_name if x.required_eval_stage else ""
                for x in plan_qs
            ]),
            "plan_memos": uniq_join([x.memo for x in plan_qs]),
            "has_plan": True,
        }

    return result


def _build_tip_missing_summary_map(snap_date, step_keys):
    valid_keys = {
        (l or "", p or "", s or "")
        for l, p, s in step_keys
        if (p or "") and (s or "")
    }
    if not valid_keys:
        return {}

    processids = sorted({p for _, p, _ in valid_keys})
    stepseqs = sorted({s for _, _, s in valid_keys})
    lineids = sorted({l for l, _, _ in valid_keys})

    qs = list(
        FactsTipMissingCompatPath.objects.filter(
            snap_date=snap_date,
            processid__in=processids,
            stepseq__in=stepseqs,
            lineid__in=lineids,
            is_active=True,
        ).order_by("-updated_at", "-id")
    )

    grouped = defaultdict(list)
    for obj in qs:
        key = (obj.lineid or "", obj.processid or "", obj.stepseq or "")
        if key in valid_keys:
            grouped[key].append(obj)

    def uniq_join(values):
        out = []
        for v in values:
            s = str(v or "").strip().upper()
            if s and s not in out:
                out.append(s)
        return " | ".join(out)

    result = {}
    for key, items in grouped.items():
        manual_body_list = []
        manual_cham_list = []
        manual_path_objects = []

        for obj in items:
            body = str(obj.eqp_body_name or "").strip().upper()
            cham = str(obj.eqp_cham_name or "").strip().upper()

            if body and body not in manual_body_list:
                manual_body_list.append(body)

            cham_token = ""
            if body and cham:
                cham_token = f"{body}-{cham}"
                if cham_token not in manual_cham_list:
                    manual_cham_list.append(cham_token)

            manual_path_objects.append({
                "always_emergency": str(obj.always_emergency or "").strip(),
                "major_minor": str(obj.major_minor or "").strip(),
                "body": body,
                "cham": cham,
                "cham_token": cham_token,
            })

        result[key] = {
            "tip_missing_flag": "Y",
            "tip_missing_always": uniq_join([x.always_emergency for x in items]),
            "tip_missing_major": uniq_join([x.major_minor for x in items]),
            "tip_missing_body": uniq_join([x.eqp_body_name for x in items]),
            "tip_missing_cham": uniq_join([x.eqp_cham_name for x in items]),
            "manual_body_list": manual_body_list,
            "manual_cham_list": manual_cham_list,
            "manual_path_objects": manual_path_objects,
        }

    return result


def _merge_eqpgroup_html(source_eqps, manual_eqps):
    parts = []
    seen = set()

    def _norm(v):
        s = str(v or "").strip().upper().replace("(", "").replace(")", "")
        if "-" in s:
            s = s.split("-", 1)[0].strip()
        return s

    for s in source_eqps:
        norm = _norm(s)
        if not norm or norm in seen:
            continue
        seen.add(norm)
        parts.append(html.escape(norm))

    for s in manual_eqps:
        norm = _norm(s)
        if not norm or norm in seen:
            continue
        seen.add(norm)
        parts.append(f'<span class="manual-added-text">{html.escape(norm)}</span>')

    return ", ".join(parts) if parts else "-"

def _merge_cham_html(source_chams, manual_chams):
    source_compact = _compact_cham_tokens(source_chams)
    manual_compact = _compact_cham_tokens(manual_chams)

    parts = []
    if source_compact:
        parts.append(html.escape(source_compact))
    if manual_compact:
        parts.append(f'<span class="manual-added-text">{html.escape(manual_compact)}</span>')

    return ", ".join(parts) if parts else "-"


def _parse_path_members(path_text, eqpgroup_text):
    members = []
    cham_tokens = [str(x).strip().upper() for x in _extract_cham_tokens([path_text]) if str(x).strip()]
    seen = set()

    if cham_tokens:
        for tok in cham_tokens:
            m = re.match(r"^([A-Z0-9_]+)-([A-Z0-9_]+)$", tok)
            if m:
                body = m.group(1)
                cham = m.group(2)
                key = f"{body}-{cham}"
                if key in seen:
                    continue
                seen.add(key)
                members.append({
                    "eqp_body_name": body,
                    "eqp_cham_name": cham,
                    "member_key": key,
                    "display_name": key,
                    "has_cham": True,
                })
            else:
                key = tok
                if key in seen:
                    continue
                seen.add(key)
                members.append({
                    "eqp_body_name": tok,
                    "eqp_cham_name": "",
                    "member_key": tok,
                    "display_name": tok,
                    "has_cham": False,
                })
        return members

    eqps = _parse_eqpgroup_tokens(eqpgroup_text)
    for body in eqps:
        if body in seen:
            continue
        seen.add(body)
        members.append({
            "eqp_body_name": body,
            "eqp_cham_name": "",
            "member_key": body,
            "display_name": body,
            "has_cham": False,
        })

    return members


def _make_override_target_list(source_path_items, manual_path_objects):
    target_map = {}

    for p in source_path_items:
        path_ref = {
            "lineid": p["lineid"],
            "recipeid": p["recipeid"],
            "path": p["path"],
            "eqpline": p["eqpline"],
            "childeqp": p["childeqp"],
        }

        for member in p["members"]:
            key = member["member_key"]
            item = target_map.setdefault(
                key,
                {
                    "member_key": key,
                    "eqp_body_name": member["eqp_body_name"],
                    "eqp_cham_name": member["eqp_cham_name"],
                    "display_name": member["display_name"],
                    "has_cham": member["has_cham"],
                    "source_types": set(),
                    "has_always": False,
                    "has_major": False,
                    "path_refs": [],
                    "manual_tip_missing": False,
                    "manual_tip_missing_always": False,
                    "manual_tip_missing_major": False,
                },
            )

            item["source_types"].add("SOURCE_PATH")
            item["has_always"] = True
            item["has_major"] = True
            item["path_refs"].append(path_ref)

    for mp in manual_path_objects:
        body = str(mp.get("body") or "").strip().upper()
        cham = str(mp.get("cham") or "").strip().upper()
        if not body:
            continue

        key = f"{body}-{cham}" if cham else body
        item = target_map.setdefault(
            key,
            {
                "member_key": key,
                "eqp_body_name": body,
                "eqp_cham_name": cham,
                "display_name": key,
                "has_cham": bool(cham),
                "source_types": set(),
                "has_always": False,
                "has_major": False,
                "path_refs": [],
                "manual_tip_missing": False,
                "manual_tip_missing_always": False,
                "manual_tip_missing_major": False,
            },
        )

        item["source_types"].add("TIP_MISSING")
        item["manual_tip_missing"] = True
        if mp.get("always_emergency") == "상시":
            item["has_always"] = True
            item["manual_tip_missing_always"] = True
        if mp.get("major_minor") == "주요":
            item["has_major"] = True
            item["manual_tip_missing_major"] = True

    result = []
    for key in sorted(target_map.keys()):
        item = target_map[key]
        result.append(
            {
                "member_key": item["member_key"],
                "eqp_body_name": item["eqp_body_name"],
                "eqp_cham_name": item["eqp_cham_name"],
                "display_name": item["display_name"],
                "has_cham": item["has_cham"],
                "has_always": item["has_always"],
                "has_major": item["has_major"],
                "manual_tip_missing": item["manual_tip_missing"],
                "manual_tip_missing_always": item["manual_tip_missing_always"],
                "manual_tip_missing_major": item["manual_tip_missing_major"],
                "source_types": sorted(item["source_types"]),
                "path_refs": item["path_refs"],
            }
        )

    return result


def _get_tip_threshold_days():
    rule = get_current_prevent_rule()
    try:
        return int(getattr(rule, "prevent_days", 7) or 7)
    except (TypeError, ValueError):
        return 7


def _row_is_tip_prevented(row, threshold_days):
    """Legacy helper. Main path uses tip_missing._row_is_tip_prevented."""
    from .tip_missing import _row_is_tip_prevented as _impl
    return _impl(row, threshold_days)


def build_step_dataset(
    snap_date,
    processid=None,
    areaname=None,
    layerid=None,
    lineid=None,
    compat_filter="all",
    include_measure=True,
    include_emergency=True,
    exclude_skiprule_100=False,
    tip_mode=False,
    for_prp_table=False,
    as_of_date=None,
):
    from .dashboard_rows import build_step_dataset as _impl

    return _impl(
        snap_date=snap_date,
        processid=processid,
        areaname=areaname,
        layerid=layerid,
        lineid=lineid,
        compat_filter=compat_filter,
        include_measure=include_measure,
        include_emergency=include_emergency,
        exclude_skiprule_100=exclude_skiprule_100,
        tip_mode=tip_mode,
        for_prp_table=for_prp_table,
        as_of_date=as_of_date,
    )
