import logging
import hashlib
from .common import (
    Count,
    Counter,
    FactsEditHistory,
    FactsPreventRuleMaster,
    FactsStepPathOverride,
    FactsWipSource,
    StringIO,
    _base_source_queryset,
    _build_path_key,
    _build_step_key,
    _empty_plan_summary,
    _empty_tip_missing_summary,
    _get_tip_threshold_days,
    _make_override_target_list,
    _merge_cham_html,
    _parse_path_members,
    _merge_eqpgroup_html,
    cache,
    csv,
    date,
    datetime,
    defaultdict,
    timedelta,
)
from ..models import FactsHistorySummaryCache
from .bulk_upload import _compact_cham_tokens, _flatten_body_values, _parse_eqpgroup_tokens, _path_signature
from .dashboard_filters import _natural_sort_key, normalize_layer_value
from .kpi import _month_start, _next_month_start, _prev_month_start
from .master import get_action_type_label
from .plan_detail import _as_of_cutoff, _as_of_date, _build_plan_summary_map, _step_group_key
from .tip_missing import calculate_prevent_age_days, _build_tip_missing_summary_map, _row_is_tip_prevented

logger = logging.getLogger(__name__)
TIP_MISSING_ASOF_VERSION = "tip-missing-asof-v4-date-debug-align"
MANUAL_INPUT_ASOF_VERSION = "manual-input-asof-v3-date-debug-align"
PRP_SOURCE_COLUMN_VERSION = "source-columns-eqptype-delaytime-v1"


def _build_step_dataset_cache_key_parts(
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
    resolved_as_of = _as_of_date(as_of_date) or _as_of_date(snap_date) or date.today()
    parts = {
        "snap_date": snap_date,
        "final_always_emergency": "",
        "final_major_minor": "",
        "lineid": lineid,
        "processid": processid,
        "areaname": areaname,
        "layerid": layerid,
        "compat_filter": compat_filter,
        "include_measure": int(bool(include_measure)),
        "include_emergency": int(bool(include_emergency)),
        "exclude_skiprule_100": int(bool(exclude_skiprule_100)),
        "tip_mode": int(bool(tip_mode)),
        "for_prp_table": int(bool(for_prp_table)),
        "as_of_date": resolved_as_of,
        "tip_threshold_days": _get_tip_threshold_days(),
        "source_column_version": PRP_SOURCE_COLUMN_VERSION,
        "tip_missing_asof_version": TIP_MISSING_ASOF_VERSION,
        "manual_input_asof_version": MANUAL_INPUT_ASOF_VERSION,
    }
    return parts


def get_build_step_dataset_debug_info(**kwargs):
    parts = _build_step_dataset_cache_key_parts(**kwargs)
    cache_key = (
        "facts:step-dataset:"
        f"{parts['snap_date']}|{parts['as_of_date']}|{parts['processid']}|{parts['areaname']}|{parts['layerid']}|"
        f"{parts['lineid']}|{parts['compat_filter']}|{parts['include_measure']}|{parts['include_emergency']}|"
        f"{parts['exclude_skiprule_100']}|{parts['tip_mode']}|{parts['for_prp_table']}|"
        f"{parts['tip_threshold_days']}|{parts['source_column_version']}|"
        f"{parts['tip_missing_asof_version']}|{parts['manual_input_asof_version']}"
    )
    return {"cache_key": cache_key, "cache_key_parts": parts}

def get_prevent_rule_rows():
    # prevent_days is ORM alias for DB column threshold_days.
    rows = list(FactsPreventRuleMaster.objects.filter(is_active=True).order_by("sort_order", "prevent_days", "id"))
    if not rows:
        return [type("RuleObj", (), {"id": 0, "sort_order": 0, "prevent_days": 7, "color_code": "#5B8FF9", "is_active": True, "is_current": True})()]
    return rows

def get_current_prevent_rule():
    # is_current is ORM alias for DB column is_selected.
    current = FactsPreventRuleMaster.objects.filter(is_active=True, is_current=True).order_by("sort_order", "prevent_days", "id").first()
    if current:
        return current
    return get_prevent_rule_rows()[0]

def get_prevent_distribution(snap_date, lineid="", processid="", areaname="", include_measure=True, exclude_skiprule_100=False, tip_mode=True):
    rules = get_prevent_rule_rows()
    qs = FactsWipSource.objects.filter(snap_date=snap_date).exclude(tip="").exclude(eventtime__isnull=True)
    if lineid:
        qs = qs.filter(lineid=lineid)
    if processid:
        qs = qs.filter(processid=processid)
    if areaname:
        qs = qs.filter(areaname=areaname)
    if not include_measure:
        qs = qs.exclude(stepseq_type="계측")
    if exclude_skiprule_100:
        qs = qs.exclude(skiprule="100")

    rows = list(qs.order_by("lineid", "processid", "areaname", "stepseq", "recipeid", "tip", "eventtime"))
    labels = [f"{rules[0].prevent_days}일 이하"] + [f"{r.prevent_days}일 이상" for r in rules]
    current_threshold = _get_tip_threshold_days()
    if not rows:
        return {"labels": labels, "datasets": [], "rows": [], "current_threshold": current_threshold, "resolved_snap_date": snap_date.isoformat() if snap_date else ""}

    buckets = Counter()
    detail_rows = []
    # prevent_days is ORM alias for DB column threshold_days.
    min_rule = min(int(r.prevent_days) for r in rules)
    seen = set()

    for row in rows:
        age_days = calculate_prevent_age_days(row.eventtime, as_of_date=snap_date)
        if age_days < min_rule:
            bucket = f"{min_rule}일 이하"
        else:
            bucket = f"{max([int(r.prevent_days) for r in rules if age_days >= int(r.prevent_days)])}일 이상"

        raw_tip = str(row.tip or "").strip()
        tip_text = raw_tip.split(":", 1)[1].strip() if ":" in raw_tip else raw_tip
        member_tokens = [t.strip() for t in tip_text.split(",") if t.strip()] or ([tip_text] if tip_text else [])
        event_str = row.eventtime.strftime("%Y-%m-%d %H:%M:%S") if row.eventtime else ""

        for member in member_tokens:
            key = (row.lineid or "", row.processid or "", row.areaname or "", row.stepseq or "", row.recipeid or "", member)
            if key in seen:
                continue
            seen.add(key)
            buckets[bucket] += 1
            detail_rows.append({
                "lineid": row.lineid or "",
                "processid": row.processid or "",
                "areaname": row.areaname or "",
                "stepseq": row.stepseq or "",
                "recipeid": row.recipeid or "",
                "tip": f"PREVENT: {member}",
                "eventtime": event_str,
                "age_days": age_days,
                "bucket": bucket,
            })

    datasets = []
    for rule in rules:
        label = f"{rule.prevent_days}일 이상"
        datasets.append({
            "label": label,
            "data": [0] + [buckets.get(label, 0) if l == label else 0 for l in [f"{r.prevent_days}일 이상" for r in rules]],
            "backgroundColor": rule.color_code,
        })
    datasets.insert(0, {
        "label": f"{min_rule}일 이하",
        "data": [buckets.get(f"{min_rule}일 이하", 0)] + [0 for _ in rules],
        "backgroundColor": "#FFFFFF",
        "borderColor": "#111111",
        "borderWidth": 1.5,
    })
    return {
        "labels": labels,
        "datasets": datasets,
        "rows": detail_rows,
        "current_threshold": current_threshold,
        "rule_rows": [{"days": r.prevent_days, "color": r.color_code} for r in rules],
        "resolved_snap_date": snap_date.isoformat() if snap_date else "",
    }

def get_history_daily_cards(
    week_dates,
    lineid="",
    processid="",
    include_measure=True,
    include_emergency=True,
    exclude_skiprule_100=True,
):
    cache_key = (
        f"facts:history-cards:{min(week_dates)}|{max(week_dates)}|{lineid}|{processid}|"
        f"{int(bool(include_measure))}|{int(bool(include_emergency))}|{int(bool(exclude_skiprule_100))}|{_get_tip_threshold_days()}"
    )
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    cards = []
    for d in sorted(week_dates):
        rows = build_step_dataset(
            snap_date=d,
            lineid=lineid or None,
            processid=processid or None,
            include_measure=include_measure,
            include_emergency=include_emergency,
            exclude_skiprule_100=exclude_skiprule_100,
            tip_mode=False,
            for_prp_table=True,
        )
        summary = summarize_steps(rows) if rows else {"total_steps": 0, "compat_rate": 0, "single_cnt": 0, "body_cnt": 0, "cham_cnt": 0}
        summary_tip = summarize_steps(rows, use_tip=True) if rows else {"single_cnt": 0, "body_cnt": 0, "cham_cnt": 0}
        dist = get_prevent_distribution(snap_date=d, lineid=lineid, processid=processid)
        prevent_counts = []
        for idx, label in enumerate(dist["labels"]):
            total = sum((ds["data"][idx] if idx < len(ds["data"]) else 0) for ds in dist["datasets"])
            prevent_counts.append({"label": label, "value": total})
        history_qs = FactsEditHistory.objects.filter(snap_date=d)
        if lineid:
            history_qs = history_qs.filter(lineid=lineid)
        if processid:
            history_qs = history_qs.filter(processid=processid)
        cards.append({
            "date": d,
            "summary": summary,
            "tip_single": summary_tip["single_cnt"],
            "tip_body": summary_tip["body_cnt"],
            "tip_cham": summary_tip["cham_cnt"],
            "prevent_counts": prevent_counts,
            "plan_count": sum(1 for r in rows if r.get("has_plan")),
            "tip_missing_count": sum(1 for r in rows if r.get("tip_missing_flag") == "Y"),
            "change_count": history_qs.count(),
            "change_by_action": [
                {
                    "action_type": item["action_type"],
                    "action_type_label": get_action_type_label(item["action_type"]),
                    "cnt": item["cnt"],
                }
                for item in history_qs.values("action_type").annotate(cnt=Count("id")).order_by("action_type")
            ],
        })
    cache.set(cache_key, cards, 60)
    return cards

def classify_compat_type(recipe_value, merged_eqps, body_flag, cham_flag, *, source_has_path=True, tip_has_path=True, tip_mode=False):
    if not source_has_path:
        return "미등록"
    if tip_mode and not tip_has_path:
        return "가능path없음"
    if body_flag == "Y":
        return "body호환"
    if cham_flag == "Y":
        return "cham호환"
    return "단독"

def is_unregistered_compat_type(value):
    return value in ("미등록", "가능path없음")

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
    snap_date = _as_of_date(snap_date) or snap_date
    as_of_date = _as_of_date(as_of_date) or _as_of_date(snap_date)

    debug_info = get_build_step_dataset_debug_info(
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
    resolved_as_of = debug_info["cache_key_parts"]["as_of_date"]
    cache_key = debug_info["cache_key"]
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    threshold_days = _get_tip_threshold_days()
    source_rows = _base_source_queryset(
        snap_date=snap_date,
        processid=processid,
        areaname=areaname,
        layerid=layerid,
        lineid=lineid,
        include_measure=include_measure,
        exclude_skiprule_100=exclude_skiprule_100,
    )

    override_qs = FactsStepPathOverride.objects.filter(snap_date__lte=snap_date, is_active=True)
    if processid:
        override_qs = override_qs.filter(processid=processid)
    if lineid:
        override_qs = override_qs.filter(lineid=lineid)
    override_qs = override_qs.filter(created_at__lte=_as_of_cutoff(resolved_as_of), updated_at__lte=_as_of_cutoff(resolved_as_of))

    overrides = {}
    for o in override_qs:
        key = _build_path_key(o.lineid, o.processid, o.stepseq, o.recipeid, o.path, o.eqpline, o.childeqp)
        overrides[key] = o

    step_map = defaultdict(lambda: {
        "snap_date": snap_date,
        "final_always_emergency": "",
        "final_major_minor": "",
        "lineid": "",
        "processid": "",
        "stepseq": "",
        "recipeid_set": set(),
        "areaname": "",
        "layerid": "",
        "eqptype_values": set(),
        "delaytime_values": set(),
        "skiprule": "",
        "descript": "",
        "stepseq_type": "",
        "eqpgroup_values": set(),
        "cham_values": set(),
        "tip_eqpgroup_values": set(),
        "tip_cham_values": set(),
        "paths": [],
        "tip_values": set(),
        "tip_detail_rows": [],
        "tip_age_days": {},
        "childeqp_values": set(),
        "path_signatures": set(),
        "tip_path_signatures": set(),
    })

    for row in source_rows:
        row_key = _build_step_key(row)
        path_key = _build_path_key(row.lineid, row.processid, row.stepseq, row.recipeid, row.path, row.eqpline, row.childeqp)
        override = overrides.get(path_key)
        final_always_emergency = override.manual_always_emergency if override and override.manual_always_emergency else (row.always_emergency or "")
        final_major_minor = override.manual_major_minor if override and override.manual_major_minor else ""
        if not include_emergency and final_always_emergency == "비상시":
            continue
        calculated_age_days = calculate_prevent_age_days(getattr(row, "eventtime", None), as_of_date=resolved_as_of)
        is_tip_prevented = _row_is_tip_prevented(row, threshold_days, as_of_date=resolved_as_of)
        logger.debug("[PRP_TABLE_PREVENT_AGE] stepseq=%s recipeid=%s path=%s eqpgroup=%s prevent=%s tip=%s eventtime=%s as_of_date=%s threshold_days=%s calculated_age_days=%s is_tip_prevented=%s excluded_from_tip_path=%s",
            row.stepseq or "", row.recipeid or "", row.path or "", row.eqpgroup or "", row.prevent or "", row.tip or "", row.eventtime, resolved_as_of, threshold_days, calculated_age_days, is_tip_prevented, bool(is_tip_prevented))
        final_body_compat = row.body_compat or "N"
        final_cham_compat = row.cham_compat or "N"
        final_body_count = row.body_compat_count or 0
        final_cham_count = row.cham_compat_count or 0

        step_item = step_map[row_key]
        step_item["lineid"] = row.lineid or ""
        step_item["processid"] = row.processid or ""
        step_item["stepseq"] = row.stepseq or ""
        step_item["areaname"] = row.areaname or ""
        step_item["layerid"] = normalize_layer_value(row.layerid)
        if getattr(row, "eqptype", None):
            step_item["eqptype_values"].add(str(row.eqptype).strip())
        if getattr(row, "delaytime", None):
            step_item["delaytime_values"].add(str(row.delaytime).strip())
        step_item["skiprule"] = row.skiprule or ""
        step_item["descript"] = row.descript or ""
        step_item["stepseq_type"] = row.stepseq_type or ""

        if row.recipeid:
            step_item["recipeid_set"].add(str(row.recipeid).upper())
        if row.eqpgroup:
            for token in _parse_eqpgroup_tokens(row.eqpgroup):
                step_item["eqpgroup_values"].add(token)
        if row.tip:
            raw_tip = str(row.tip).strip()
            step_item["tip_values"].add(raw_tip)
            age_days = calculated_age_days
            tip_text = raw_tip.split(":", 1)[1].strip() if ":" in raw_tip else raw_tip
            member_tokens = [t.strip() for t in tip_text.split(",") if t.strip()]
            if not member_tokens and tip_text:
                member_tokens = [tip_text]
            for part in member_tokens:
                prev_age = step_item["tip_age_days"].get(part)
                if prev_age is None or age_days > prev_age:
                    step_item["tip_age_days"][part] = age_days
        if row.childeqp:
            step_item["childeqp_values"].add(str(row.childeqp))
        path_members = _parse_path_members(row.path, row.eqpgroup)
        path_sig = _path_signature(row)
        if path_sig:
            step_item["path_signatures"].add(path_sig)
            if not is_tip_prevented:
                step_item["tip_path_signatures"].add(path_sig)
        for m in path_members:
            body_name = str(m.get("eqp_body_name") or "").strip().upper()
            cham_name = str(m.get("display_name") or "").strip().upper()
            if body_name:
                step_item["eqpgroup_values"].add(body_name)
                if not is_tip_prevented:
                    step_item["tip_eqpgroup_values"].add(body_name)
            if m["has_cham"] and cham_name:
                step_item["cham_values"].add(cham_name)
                if not is_tip_prevented:
                    step_item["tip_cham_values"].add(cham_name)
        step_item["final_always_emergency"] = final_always_emergency or step_item.get("final_always_emergency", "")
        step_item["final_major_minor"] = final_major_minor or step_item.get("final_major_minor", "")
        step_item["paths"].append({
            "lineid": row.lineid or "",
            "recipeid": row.recipeid or "",
            "path": row.path or "",
            "eqpline": row.eqpline or "",
            "childeqp": row.childeqp or "",
            "eqpgroup": row.eqpgroup or "",
            "members": path_members,
            "final_always_emergency": final_always_emergency,
            "final_major_minor": final_major_minor,
            "final_body_compat": final_body_compat,
            "final_cham_compat": final_cham_compat,
            "body_compat_count": final_body_count,
            "cham_compat_count": final_cham_count,
            "body_compat_tip": "N" if is_tip_prevented else (row.body_compat or "N"),
            "cham_compat_tip": "N" if is_tip_prevented else (row.cham_compat or "N"),
            "body_compat_count_tip": 0 if is_tip_prevented else (row.body_compat_count or 0),
            "cham_compat_count_tip": 0 if is_tip_prevented else (row.cham_compat_count or 0),
            "tip": row.tip or "",
        })

    result = []
    step_keys = set(step_map.keys())
    plan_summary_map = _build_plan_summary_map(step_keys, as_of_date=resolved_as_of)
    tip_missing_summary_map = _build_tip_missing_summary_map(snap_date, step_keys, as_of_date=resolved_as_of)

    for _, item in step_map.items():
        lineid_val = item["lineid"]
        processid_val = item["processid"]
        stepseq_val = item["stepseq"]
        step_key = _step_group_key(lineid_val, processid_val, stepseq_val)
        plan_summary = plan_summary_map.get(step_key, _empty_plan_summary())
        tip_missing_summary = tip_missing_summary_map.get(step_key, _empty_tip_missing_summary())
        source_eqps = sorted(_flatten_body_values(item["eqpgroup_values"]))
        source_chams = sorted(item["cham_values"])
        source_eqps_tip = sorted(_flatten_body_values(item["tip_eqpgroup_values"]))
        source_chams_tip = sorted(item["tip_cham_values"])
        manual_eqps = tip_missing_summary["manual_body_list"]
        manual_chams = tip_missing_summary["manual_cham_list"]
        merged_eqps = []
        for x in source_eqps + manual_eqps:
            if x not in merged_eqps:
                merged_eqps.append(x)
        merged_chams = []
        for x in source_chams + manual_chams:
            if x not in merged_chams:
                merged_chams.append(x)
        merged_eqps_tip = []
        for x in source_eqps_tip + manual_eqps:
            if x not in merged_eqps_tip:
                merged_eqps_tip.append(x)
        merged_chams_tip = []
        for x in source_chams_tip + manual_chams:
            if x not in merged_chams_tip:
                merged_chams_tip.append(x)
        recipe_str = ", ".join(sorted(item["recipeid_set"])) if item["recipeid_set"] else ""
        eqptype_str = ", ".join(sorted(x for x in item["eqptype_values"] if x)) if item["eqptype_values"] else ""
        delaytime_str = ", ".join(sorted(x for x in item["delaytime_values"] if x)) if item["delaytime_values"] else ""
        eqpgroup_str = ", ".join(merged_eqps) if merged_eqps else ""
        cham_display = _compact_cham_tokens(merged_chams)
        paths = item["paths"]
        manual_path_count = len(tip_missing_summary.get("manual_path_objects") or [])
        body_path_count = len(merged_eqps)
        source_path_count = len(item.get("path_signatures", set()))
        tip_source_path_count = len(item.get("tip_path_signatures", set()))
        cham_path_count = source_path_count + manual_path_count
        body_compat_count_tip = len(merged_eqps_tip)
        cham_compat_count_tip = tip_source_path_count + manual_path_count
        body_compat_flag = "Y" if body_path_count >= 2 else "N"
        cham_compat_flag = "Y" if cham_path_count >= 2 else "N"
        body_compat_tip = "Y" if body_compat_count_tip >= 2 else "N"
        cham_compat_tip = "Y" if cham_compat_count_tip >= 2 else "N"
 
        # source_has_path는 원천 facts_wip_source path 기준만 사용(수동 TIP미등록 path 제외).
        source_has_path = bool(source_eqps or source_chams or item.get("path_signatures"))
        tip_has_path = bool(source_eqps_tip or source_chams_tip or item.get("tip_path_signatures") or merged_eqps_tip)
        compat_type_base = classify_compat_type(recipe_str, merged_eqps, body_compat_flag, cham_compat_flag, source_has_path=source_has_path, tip_has_path=tip_has_path, tip_mode=False)

        compat_type_tip = classify_compat_type(recipe_str, merged_eqps_tip, body_compat_tip, cham_compat_tip, source_has_path=source_has_path, tip_has_path=tip_has_path, tip_mode=True)

        compat_type = compat_type_base

        if compat_filter != "all":
            if compat_filter == "미등록":
                if compat_type not in ("미등록", "가능path없음"):
                    continue
            elif compat_type != compat_filter:
                continue

        has_always = True if paths else False
        has_major = True if paths else False
        for mp in tip_missing_summary["manual_path_objects"]:
            if mp["always_emergency"] == "상시":
                has_always = True
            if mp["major_minor"] == "주요":
                has_major = True
        override_target_list = _make_override_target_list(paths, tip_missing_summary["manual_path_objects"])
        always_count = sum(1 for x in override_target_list if x.get("has_always"))
        emergency_count = max(len(override_target_list) - always_count, 0)
        major_count = sum(1 for x in override_target_list if x.get("has_major"))
        minor_count = max(len(override_target_list) - major_count, 0)
        tip_parts = []
        has_prevent_prefix = False
        for raw_tip in item["tip_values"]:
            if str(raw_tip or "").strip().upper().startswith("PREVENT:"):
                has_prevent_prefix = True
                break
        for part in sorted(item.get("tip_age_days", {}).keys()):
            tip_parts.append(f"{part}({int(item['tip_age_days'][part])}일↑)")
        row = {
            "snap_date": snap_date,
            "final_always_emergency": "",
            "final_major_minor": "",
            "lineid": lineid_val,
            "processid": processid_val,
            "stepseq": stepseq_val,
            "areaname": item["areaname"],
            "layerid": item["layerid"],
            "eqptype": eqptype_str,
            "delaytime": delaytime_str,
            "skiprule": item["skiprule"],
            "descript": item["descript"],
            "recipeid": recipe_str,
            "stepseq_type": item["stepseq_type"],
            "eqpgroup": eqpgroup_str,
            "cham_display": cham_display,
            "eqpgroup_html": _merge_eqpgroup_html(source_eqps, manual_eqps),
            "cham_html": _merge_cham_html(source_chams, manual_chams),
            "body_compat_flag": body_compat_flag,
            "cham_compat_flag": cham_compat_flag,
            "body_path_count": body_path_count,
            "cham_path_count": cham_path_count,
            "body_compat_count": body_path_count,
            "cham_compat_count": cham_path_count,
            "compat_type": compat_type,
            "compat_type_base": compat_type_base,
            "compat_type_tip": compat_type_tip,
            "body_compat_tip": body_compat_tip,
            "cham_compat_tip": cham_compat_tip,
            "body_compat_count_tip": body_compat_count_tip,
            "cham_compat_count_tip": cham_compat_count_tip,
            "tip": (("PREVENT: " + ", ".join(tip_parts)) if tip_parts and has_prevent_prefix else ", ".join(tip_parts)) if tip_parts else "",
            "childeqp": ", ".join(sorted(item["childeqp_values"])) if item["childeqp_values"] else "",
            "has_always": has_always,
            "has_major": has_major,
            "always_count": always_count,
            "emergency_count": emergency_count,
            "major_count": major_count,
            "minor_count": minor_count,
            "always_summary_text": f"상시:{always_count}, 비상시:{emergency_count}",
            "major_summary_text": f"주요:{major_count}, 비주요:{minor_count}",
            "final_always_emergency": item.get("final_always_emergency", ""),
            "final_major_minor": item.get("final_major_minor", ""),
            "has_plan": plan_summary["has_plan"],
            "plan_flag": plan_summary["plan_flag"],
            "plan_body_names": plan_summary["plan_body_names"],
            "plan_cham_names": plan_summary["plan_cham_names"],
            "plan_due_dates": plan_summary["plan_due_dates"],
            "plan_eval_lot_ids": plan_summary["plan_eval_lot_ids"],
            "plan_eval_stages": plan_summary["plan_eval_stages"],
            "plan_memos": plan_summary["plan_memos"],
            "tip_missing_flag": tip_missing_summary["tip_missing_flag"],
            "tip_missing_always": tip_missing_summary["tip_missing_always"],
            "tip_missing_major": tip_missing_summary["tip_missing_major"],
            "tip_missing_body": tip_missing_summary["tip_missing_body"],
            "tip_missing_cham": tip_missing_summary["tip_missing_cham"],
            "override_target_list": override_target_list,
            "override_target_count": len(override_target_list),
            "is_compatible": (body_compat_flag == "Y" or cham_compat_flag == "Y"),
        }
        result.append(row)

    result.sort(key=lambda x: ((x["lineid"] or ""), (x["processid"] or ""), _natural_sort_key(x["stepseq"])))
    cache.set(cache_key, result, 60)
    return result

def summarize_steps(step_rows, use_tip=False):
    if use_tip:
        calc_rows = [
            r for r in step_rows
            if not is_unregistered_compat_type(r.get("compat_type_tip"))
        ]
        body_key = "body_compat_tip"
        cham_key = "cham_compat_tip"
    else:
        calc_rows = [
            r for r in step_rows
            if not is_unregistered_compat_type(r.get("compat_type_base"))
        ]
        body_key = "body_compat_flag"
        cham_key = "cham_compat_flag"

    total = len(calc_rows)

    single_cnt = sum(1 for r in calc_rows if r[body_key] == "N" and r[cham_key] == "N")
    body_cnt = sum(1 for r in calc_rows if r[body_key] == "Y")
    cham_exclusive_cnt = sum(1 for r in calc_rows if r[cham_key] == "Y" and r[body_key] != "Y")
    compatible = sum(1 for r in calc_rows if r[body_key] == "Y" or r[cham_key] == "Y")

    return {
        "total_steps": total,
        "compatible_steps": compatible,
        "compat_rate": round((compatible / total) * 100, 1) if total else 0.0,
        "body_rate": round((body_cnt / total) * 100, 1) if total else 0.0,
        "cham_rate_cum": round(((body_cnt + cham_exclusive_cnt) / total) * 100, 1) if total else 0.0,
        "single_cnt": single_cnt,
        "body_cnt": body_cnt,
        "cham_cnt": cham_exclusive_cnt,
    }







def _normalize_compat_label(value):
    text = str(value or "").strip().lower()
    if text in ("body호환", "body"):
        return "body"
    if text in ("cham호환", "cham"):
        return "cham"
    if text == "단독":
        return "single"
    if text in ("미등록", "가능path없음"):
        return "unregistered"
    return "other"


def get_prp_export_compat_label(row):
    """엑셀/PRP TABLE의 기본 호환구분 source key(compat_type_base)를 반환한다."""
    return row.get("compat_type_base")


def get_prp_export_tip_compat_label(row):
    """엑셀/PRP TABLE의 TIP고려 호환구분 source key(compat_type_tip)를 반환한다."""
    return row.get("compat_type_tip")


def summarize_prp_rows_base(step_rows):
    rows = list(step_rows or [])
    total = len(rows)
    body = cham = single = unregistered = 0

    for row in rows:
        compat_value = get_prp_export_compat_label(row)
        if compat_value in (None, ""):
            compat_value = row.get("compat_type_base")
        normalized = _normalize_compat_label(compat_value)
        if normalized == "body":
            body += 1
        elif normalized == "cham":
            cham += 1
        elif normalized == "single":
            single += 1
        elif normalized == "unregistered":
            unregistered += 1

    compatible = body + cham
    return {
        "total_steps": total,
        "compatible_steps": compatible,
        "compat_rate": round((compatible / total) * 100, 1) if total else 0.0,
        "body_cnt": body,
        "cham_cnt": cham,
        "single_cnt": single,
        "unregistered_cnt": unregistered,
    }


def summarize_metric_rows_for_condition(step_rows, tip_mode=False):
    """MetricDaily 집계용: condition(t0/t1)에 따라 base 또는 tip 호환구분으로 count."""
    rows = list(step_rows or [])
    total = len(rows)
    body = cham = single = unregistered = 0
    compat_key = "compat_type_tip" if tip_mode else "compat_type_base"

    for row in rows:
        compat_value = row.get(compat_key)
        if compat_value in (None, ""):
            compat_value = row.get("compat_type_base")
        normalized = _normalize_compat_label(compat_value)
        if normalized == "body":
            body += 1
        elif normalized == "cham":
            cham += 1
        elif normalized == "single":
            single += 1
        elif normalized == "unregistered":
            unregistered += 1

    compatible = body + cham
    return {
        "total_steps": total,
        "compatible_steps": compatible,
        "compat_rate": round((compatible / total) * 100, 1) if total else 0.0,
        "body_cnt": body,
        "cham_cnt": cham,
        "single_cnt": single,
        "unregistered_cnt": unregistered,
    }


def summarize_export_rows_for_metric(step_rows):
    """호환 유지: 기존 호출부와의 하위호환을 위해 base 기준 집계 유지."""
    return summarize_metric_rows_for_condition(step_rows, tip_mode=False)

def _scope_hash(lineid, processid, areaname, layer_key):
    raw = f"{(lineid or '').strip()}|{(processid or '').strip()}|{(areaname or '').strip()}|{(layer_key or '').strip()}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()
def _condition_key(include_measure, include_emergency, exclude_skiprule_100, tip_mode):
    return f"m{int(bool(include_measure))}:e{int(bool(include_emergency))}:s{int(bool(exclude_skiprule_100))}:t{int(bool(tip_mode))}"


def _group_metric_rows_by_scope(step_rows):
    grouped = {}
    for row in (step_rows or []):
        lineid = (row.get("lineid") or "").strip()
        processid = (row.get("processid") or "").strip()
        if not lineid or not processid:
            continue

        areaname = (row.get("areaname") or "").strip()
        layer_key = normalize_layer_value(row.get("layerid") or "")
        key = (lineid, processid, areaname, layer_key)
        grouped.setdefault(key, []).append(row)
    return grouped




def build_grouped_metric_rows_for_condition(snap_date, include_measure, include_emergency, exclude_skiprule_100, tip_mode):
    kwargs = {
        "processid": None,
        "areaname": None,
        "layerid": None,
        "lineid": None,
        "include_measure": include_measure,
        "include_emergency": include_emergency,
        "exclude_skiprule_100": exclude_skiprule_100,
        "tip_mode": tip_mode,
        "for_prp_table": True,
    }
    step_rows = build_step_dataset(snap_date=snap_date, **kwargs)
    return _group_metric_rows_by_scope(step_rows)


def _metric_distribution(step_rows, compat_key):
    counts = {"body": 0, "cham": 0, "single": 0, "unregistered": 0, "other": 0}
    for row in (step_rows or []):
        normalized = _normalize_compat_label(row.get(compat_key))
        counts[normalized if normalized in counts else "other"] += 1
    return counts

def _fetch_daily_metric_rows(date_list, common_kwargs):
    from facts.models import FactsDashboardMetricDaily

    lineid = (common_kwargs.get("lineid") or "").strip()
    processid = (common_kwargs.get("processid") or "").strip()
    if not lineid or not processid:
        return {}, list(date_list), 0

    qs = FactsDashboardMetricDaily.objects.filter(
        snap_date__in=date_list,
        lineid=lineid,
        processid=processid,
        include_measure=bool(common_kwargs.get("include_measure")),
        include_emergency=bool(common_kwargs.get("include_emergency")),
        exclude_skiprule_100=bool(common_kwargs.get("exclude_skiprule_100")),
        tip_mode=bool(common_kwargs.get("tip_mode")),
        metric_type="compat",
    )

    qs = qs.exclude(areaname="", layer_key="")

    areaname = (common_kwargs.get("areaname") or "").strip()
    if areaname:
        qs = qs.filter(areaname=areaname)

    layer_values = [normalize_layer_value(x) for x in (common_kwargs.get("layerid") or []) if normalize_layer_value(x)]
    layer_values = sorted(set(layer_values))
    if layer_values:
        if len(layer_values) == 1:
            qs = qs.filter(layer_key=layer_values[0])
        else:
            qs = qs.filter(layer_key__in=layer_values)

    by_date = {}
    rows_read = 0
    for row in qs.iterator():
        rows_read += 1
        acc = by_date.setdefault(row.snap_date, {"total_steps": 0, "compatible_steps": 0, "body_cnt": 0, "cham_cnt": 0})
        acc["total_steps"] += int(row.total_steps or 0)
        acc["compatible_steps"] += int(row.compatible_steps or 0)
        acc["body_cnt"] += int(row.body_cnt or 0)
        acc["cham_cnt"] += int(row.cham_cnt or 0)

    missing = [d for d in date_list if d not in by_date]
    return by_date, missing, rows_read

def _build_or_get_daily_metric(snap_date, common_kwargs, grouped_rows_by_scope=None, debug_scope=False):
    from facts.models import FactsDashboardMetricDaily

    lineid = (common_kwargs.get("lineid") or "").strip()
    processid = (common_kwargs.get("processid") or "").strip()
    areaname = (common_kwargs.get("areaname") or "").strip()
    layer_values = [normalize_layer_value(x) for x in (common_kwargs.get("layerid") or []) if normalize_layer_value(x)]
    layer_key = ",".join(sorted(set(layer_values)))

    if not lineid or not processid:
        return None

    scope_hash = _scope_hash(lineid, processid, areaname, layer_key)
    cond = _condition_key(common_kwargs.get("include_measure"), common_kwargs.get("include_emergency"), common_kwargs.get("exclude_skiprule_100"), common_kwargs.get("tip_mode"))

    logger.info("[METRIC_SCOPE] lineid=%s processid=%s areaname=%s layer_key=%s scope_hash=%s", lineid, processid, areaname, layer_key, scope_hash)

    if grouped_rows_by_scope is None:
        metric_kwargs = dict(common_kwargs)
        metric_kwargs.update({
            "lineid": None,
            "processid": None,
            "areaname": None,
            "layerid": None,
            "for_prp_table": True,
        })
        step_rows = build_step_dataset(snap_date=snap_date, **metric_kwargs)
        grouped_rows_by_scope = _group_metric_rows_by_scope(step_rows)

    step_rows = grouped_rows_by_scope.get((lineid, processid, areaname, layer_key), [])

    tip_mode = bool(common_kwargs.get("tip_mode"))
    summary = summarize_metric_rows_for_condition(step_rows or [], tip_mode=tip_mode)
    if not isinstance(summary, dict):
        raise ValueError(f"invalid summary type for metric build: {type(summary)}")

    total_steps = int(summary.get("total_steps") or 0)
    compatible_steps = int(summary.get("compatible_steps") or 0)
    body_cnt = int(summary.get("body_cnt") or 0)
    cham_cnt = int(summary.get("cham_cnt") or 0)
    single_cnt = int(summary.get("single_cnt") or 0)
    metric_value = summary.get("compat_rate", 0)

    if debug_scope:
        cond_debug = _condition_key(common_kwargs.get("include_measure"), common_kwargs.get("include_emergency"), common_kwargs.get("exclude_skiprule_100"), tip_mode)
        selected_key = "compat_type_tip" if tip_mode else "compat_type_base"
        selected_dist = _metric_distribution(step_rows, selected_key)
        base_dist = _metric_distribution(step_rows, "compat_type_base")
        tip_dist = _metric_distribution(step_rows, "compat_type_tip")
        defaults_payload = {
            "body_cnt": body_cnt,
            "cham_cnt": cham_cnt,
            "single_cnt": single_cnt,
            "compatible_steps": compatible_steps,
            "metric_value": metric_value,
        }
        print(f"[METRIC_DEBUG] cond={cond_debug}")
        print(f"[METRIC_DEBUG] tip_mode={tip_mode}")
        print(f"[METRIC_DEBUG] rows={len(step_rows or [])}")
        print(f"[METRIC_DEBUG] base_distribution={base_dist}")
        print(f"[METRIC_DEBUG] tip_distribution={tip_dist}")
        print(f"[METRIC_DEBUG] selected_key={selected_key}")
        print("[METRIC_DEBUG] selected_summary total={total} body={body} cham={cham} single={single} unregistered={unregistered} compatible={compatible} metric={metric}".format(
            total=total_steps, body=body_cnt, cham=cham_cnt, single=single_cnt, unregistered=int(summary.get("unregistered_cnt") or 0), compatible=compatible_steps, metric=metric_value
        ))
        print("[METRIC_DEBUG] defaults body_cnt={body_cnt} cham_cnt={cham_cnt} single_cnt={single_cnt} compatible_steps={compatible_steps} metric_value={metric_value}".format(**defaults_payload))
        print(f"[METRIC_DEBUG] common_kwargs_tip_mode={common_kwargs.get('tip_mode')} coerced_tip_mode={tip_mode}")
        if cond_debug.endswith(":t1") and selected_key != "compat_type_tip":
            raise ValueError(f"[METRIC_DEBUG] invalid selected_key for t1: {selected_key}")
        if cond_debug.endswith(":t1") and selected_dist != tip_dist:
            raise ValueError(f"[METRIC_DEBUG] selected distribution mismatch for t1: selected={selected_dist} tip={tip_dist}")
        if cond_debug.endswith(":t0") and selected_key != "compat_type_base":
            raise ValueError(f"[METRIC_DEBUG] invalid selected_key for t0: {selected_key}")
        if defaults_payload["body_cnt"] != body_cnt or defaults_payload["cham_cnt"] != cham_cnt or defaults_payload["single_cnt"] != single_cnt or defaults_payload["compatible_steps"] != compatible_steps:
            raise ValueError(f"[METRIC_DEBUG] defaults mismatch: {defaults_payload}")

    try:
        row, _ = FactsDashboardMetricDaily.objects.update_or_create(
        snap_date=snap_date,
        scope_hash=scope_hash,
        condition_key=cond,
        include_measure=bool(common_kwargs.get("include_measure")),
        include_emergency=bool(common_kwargs.get("include_emergency")),
        exclude_skiprule_100=bool(common_kwargs.get("exclude_skiprule_100")),
        tip_mode=bool(common_kwargs.get("tip_mode")),
        metric_type="compat",
        defaults={
            "lineid": lineid,
            "processid": processid,
            "areaname": areaname,
            "layer_key": layer_key,
            "numerator": compatible_steps,
            "denominator": total_steps,
            "total_steps": total_steps,
            "compatible_steps": compatible_steps,
            "body_cnt": body_cnt,
            "cham_cnt": cham_cnt,
            "single_cnt": single_cnt,
            "metric_value": metric_value,
        },
        )
        return row
    except Exception:
        logger.exception("[METRIC_SCOPE_ERROR] snap_date=%s lineid=%s processid=%s areaname=%s layer_key=%s condition_key=%s", snap_date, lineid, processid, areaname, layer_key, cond)
        raise

def get_dashboard_combined_series(
    snap_date,
    processid=None,
    areaname=None,
    layerid=None,
    lineid=None,
    include_measure=True,
    include_emergency=True,
    exclude_skiprule_100=False,
    tip_mode=False,
    target_monthly=None,
):
    import time
    t_metric = time.perf_counter()
    common_kwargs = dict(
        processid=processid,
        areaname=areaname,
        layerid=layerid,
        lineid=lineid,
        include_measure=include_measure,
        include_emergency=include_emergency,
        exclude_skiprule_100=exclude_skiprule_100,
        tip_mode=tip_mode,
    )

    all_needed_dates = []
    def _aggregate_metrics(date_list):
        by_date = {d: prefetched_by_date[d] for d in date_list if d in prefetched_by_date}
        missing = [d for d in date_list if d not in by_date]
        rows = [by_date[d] for d in date_list if d in by_date and by_date[d]["total_steps"] > 0]
        if not rows:
            return None, missing
        total_steps = sum(r["total_steps"] for r in rows)
        compatible = sum(r["compatible_steps"] for r in rows)
        body = sum(r["body_cnt"] for r in rows)
        cham = sum(r["cham_cnt"] for r in rows)
        return {"compat_rate": round((compatible / total_steps) * 100, 1) if total_steps else None, "body_rate": round((body / total_steps) * 100, 1) if total_steps else None, "cham_rate_cum": round(((body + cham) / total_steps) * 100, 1) if total_steps else None}, missing

    monthly_date_lists = []
    weekly_date_lists = []
    daily_dates = []
    month3 = _month_start(snap_date)
    month2 = _prev_month_start(month3)
    month1 = _prev_month_start(month2)

    for month_start in [month1, month2, month3]:
        next_month = _next_month_start(month_start)
        date_list = []
        cur = month_start
        while cur < next_month and cur <= snap_date:
            date_list.append(cur)
            cur += timedelta(days=1)
        all_needed_dates.extend(date_list)
        monthly_date_lists.append((month_start, date_list))

    for i in range(3, -1, -1):
        end_date = snap_date - timedelta(days=7 * i)
        start_date = end_date - timedelta(days=6)
        date_list = []
        cur = start_date
        while cur <= end_date:
            date_list.append(cur)
            cur += timedelta(days=1)
        all_needed_dates.extend(date_list)
        _, week_no, _ = end_date.isocalendar()
        weekly_date_lists.append((week_no, date_list))

    for i in range(6, -1, -1):
        d = snap_date - timedelta(days=i)
        daily_dates.append(d)
        all_needed_dates.append(d)
    all_needed_dates = sorted(set(all_needed_dates))
    prefetched_by_date = {}
    rows_read = 0
    if all_needed_dates:
        prefetched_by_date, _, rows_read = _fetch_daily_metric_rows(all_needed_dates, common_kwargs)
    if not isinstance(prefetched_by_date, dict):
        prefetched_by_date = {}
    logger.info("[DASHBOARD_TIMING] metric_query=%.4fs", time.perf_counter() - t_metric)
    t_series = time.perf_counter()
    labels, total_values, body_values, cham_values, target_values = [], [], [], [], []
    missing_dates = []

    for month_start, date_list in monthly_date_lists:
        labels.append(f"{month_start.month}월")
        s, missing = _aggregate_metrics(date_list)
        missing_dates.extend(missing)
        total_values.append(s["compat_rate"] if s else None)
        body_values.append(s["body_rate"] if s else None)
        cham_values.append(s["cham_rate_cum"] if s else None)
        target_values.append(round(float(target_monthly), 1) if target_monthly is not None else None)

    labels.extend(["", ""])
    total_values.extend([None, None])
    body_values.extend([None, None])
    cham_values.extend([None, None])
    target_values.extend([None, None])

    for week_no, date_list in weekly_date_lists:
        labels.append(f"W{week_no:02d}")
        s, missing = _aggregate_metrics(date_list)
        missing_dates.extend(missing)
        total_values.append(s["compat_rate"] if s else None)
        body_values.append(s["body_rate"] if s else None)
        cham_values.append(s["cham_rate_cum"] if s else None)
        target_values.append(round(float(target_monthly), 1) if target_monthly is not None else None)


    labels.extend(["", ""])
    total_values.extend([None, None])
    body_values.extend([None, None])
    cham_values.extend([None, None])
    target_values.extend([None, None])

    for d in daily_dates:
        labels.append(f"{d.month}/{d.day}")
        s, missing = _aggregate_metrics([d])
        missing_dates.extend(missing)
        total_values.append(s["compat_rate"] if s else None)
        body_values.append(s["body_rate"] if s else None)
        cham_values.append(s["cham_rate_cum"] if s else None)
        target_values.append(round(float(target_monthly), 1) if target_monthly is not None else None)

    missing_sorted = sorted({d for d in missing_dates})
    metric_dates = sorted(prefetched_by_date.keys()) if prefetched_by_date else []
    ignored = [d for d in missing_sorted if metric_dates and d < metric_dates[0]]
    missing_in_range = [d for d in missing_sorted if d not in ignored]
    result = {
        "labels": labels,
        "total_values": total_values,
        "body_values": body_values,
        "cham_values": cham_values,
        "target_values": target_values,
        "missing_dates": [d.isoformat() for d in missing_in_range],
        "rows_read": rows_read,
        "needed_date_min": all_needed_dates[0].isoformat() if all_needed_dates else "",
        "needed_date_max": all_needed_dates[-1].isoformat() if all_needed_dates else "",
        "needed_date_count": len(all_needed_dates),
        "metric_date_min": metric_dates[0].isoformat() if metric_dates else "",
        "metric_date_max": metric_dates[-1].isoformat() if metric_dates else "",
        "missing_dates_count": len(missing_in_range),
        "ignored_out_of_range_dates_count": len(ignored),
        "missing_dates_head": [d.isoformat() for d in missing_in_range[:5]],
        "missing_dates_tail": [d.isoformat() for d in missing_in_range[-5:]],
        "timing_metric_query": time.perf_counter() - t_metric,
        "timing_series_build": time.perf_counter() - t_series,
    }
    logger.info("[DASHBOARD_TIMING] series_build=%.4fs", time.perf_counter() - t_series)
    return result


def rebuild_metric_daily_for_snap_date(snap_date, force_rebuild=False, lineid=None, processid=None, condition_key=None, debug_scope=False):
    snap_date = _as_of_date(snap_date) or snap_date
    from facts.models import FactsDashboardMetricDaily

    lineid_filter = (lineid or "").strip()
    processid_filter = (processid or "").strip()
    condition_key_filter = (condition_key or "").strip()

    if force_rebuild:
        delete_qs = FactsDashboardMetricDaily.objects.filter(snap_date=snap_date)
        if lineid_filter:
            delete_qs = delete_qs.filter(lineid=lineid_filter)
        if processid_filter:
            delete_qs = delete_qs.filter(processid=processid_filter)
        if condition_key_filter:
            delete_qs = delete_qs.filter(condition_key=condition_key_filter)
        delete_qs.delete()

    built = 0
    skipped = 0
    skipped_invalid_scopes = 0
    skipped_aggregate_scopes = 0
    built_atomic_scopes = 0

    atomic_scope_set = set()
    for include_measure in (True, False):
        for include_emergency in (True, False):
            for exclude_skip in (False, True):
                for tip_mode in (False, True):
                    grouped = build_grouped_metric_rows_for_condition(
                        snap_date=snap_date,
                        include_measure=include_measure,
                        include_emergency=include_emergency,
                        exclude_skiprule_100=exclude_skip,
                        tip_mode=tip_mode,
                    )
                    filtered_scope_keys = []
                    for lineid_val, processid_val, areaname_val, layer_val in grouped.keys():
                        if lineid_filter and lineid_val != lineid_filter:
                            continue
                        if processid_filter and processid_val != processid_filter:
                            continue
                        filtered_scope_keys.append((lineid_val, processid_val, areaname_val, layer_val))

                    atomic_scope_set.update(filtered_scope_keys)

                    for lineid_val, processid_val, areaname_val, layer_val in sorted(filtered_scope_keys):
                        common = {
                            "processid": processid_val,
                            "areaname": areaname_val,
                            "layerid": [layer_val] if layer_val else [],
                            "lineid": lineid_val,
                            "include_measure": include_measure,
                            "include_emergency": include_emergency,
                            "exclude_skiprule_100": exclude_skip,
                            "tip_mode": tip_mode,
                        }
                        layer_values = [normalize_layer_value(x) for x in (common.get("layerid") or []) if normalize_layer_value(x)]
                        layer_key = ",".join(sorted(set(layer_values)))
                        scope_hash = _scope_hash(common.get("lineid"), common.get("processid"), common.get("areaname"), layer_key)
                        cond = _condition_key(include_measure, include_emergency, exclude_skip, tip_mode)
                        if condition_key_filter and cond != condition_key_filter:
                            continue
                        exists = FactsDashboardMetricDaily.objects.filter(
                            snap_date=snap_date,
                            scope_hash=scope_hash,
                            condition_key=cond,
                            include_measure=include_measure,
                            include_emergency=include_emergency,
                            exclude_skiprule_100=exclude_skip,
                            tip_mode=tip_mode,
                            metric_type="compat",
                        ).exists()
                        if exists and not force_rebuild:
                            skipped += 1
                            continue
                        row = _build_or_get_daily_metric(snap_date, common, grouped_rows_by_scope=grouped, debug_scope=debug_scope)
                        if row is None:
                            skipped_invalid_scopes += 1
                            continue
                        built += 1

    built_atomic_scopes = len(atomic_scope_set)

    return {
        "built": built,
        "skipped": skipped,
        "scope_count": len(atomic_scope_set),
        "skipped_invalid_scopes": skipped_invalid_scopes,
        "skipped_aggregate_scopes": skipped_aggregate_scopes,
        "built_atomic_scopes": built_atomic_scopes,
    }

def export_prp_csv(step_rows):
    output = StringIO()
    writer = csv.writer(output)

    writer.writerow([
        "기준일",
        "LINE",
        "PRP",
        "AREA",
        "LAYER",
        "STEP",
        "SKIPRULE",
        "EQPTYPE",
        "DELAYTIME",
        "DESCRIPT",
        "RECIPE",
        "EQPGROUP",
        "CHAM정보",
        "TYPE",
        "BODY호환",
        "CHAM호환",
        "BODY수",
        "CHAM수",
        "호환구분",
        "호환확보",
        "상시여부",
        "주요여부",
        "호환계획여부",
        "계획_호환EQPBODY명",
        "계획_호환EQPCHAM명",
        "계획_호환완료계획일",
        "계획_평가LotID",
        "계획_평가단계",
        "계획_비고",
        "TIP미등록 호환Path 여부",
        "미등록TIP호환Path_상시/비상시",
        "미등록TIP호환Path_주요/비주요",
        "미등록TIP호환Path_호환EQPBODY명",
        "미등록TIP호환Path_호환EQPCHAM명",
        "호환구분_TIP고려",
        "호환확보_TIP고려",
        "BODY호환_TIP고려",
        "CHAM호환_TIP고려",
        "BODY호환확보수_TIP고려",
        "CHAM호환확보수_TIP고려",
        "TIP",
        "CHILDEQP",
    ])

    for row in step_rows:
        writer.writerow([
            row["snap_date"],
            row["lineid"],
            row["processid"],
            row["areaname"],
            row["layerid"],
            row["stepseq"],
            row["skiprule"],
            row.get("eqptype") or "",
            row.get("delaytime") or "",
            row["descript"],
            row["recipeid"],
            row["eqpgroup"],
            row["cham_display"],
            row["stepseq_type"],
            row["body_compat_flag"],
            row["cham_compat_flag"],
            row["body_path_count"],
            row["cham_path_count"],
            row["compat_type_base"],
            "Y" if (row["body_compat_flag"] == "Y" or row["cham_compat_flag"] == "Y") else "N",
            "Y" if row["has_always"] else "N",
            "Y" if row["has_major"] else "N",
            "Y" if row["has_plan"] else "N",
            row["plan_body_names"],
            row["plan_cham_names"],
            row["plan_due_dates"],
            row["plan_eval_lot_ids"],
            row["plan_eval_stages"],
            row["plan_memos"],
            row["tip_missing_flag"],
            row["tip_missing_always"],
            row["tip_missing_major"],
            row["tip_missing_body"],
            row["tip_missing_cham"],
            row["compat_type_tip"],
            "Y" if (row["body_compat_tip"] == "Y" or row["cham_compat_tip"] == "Y") else "N",
            row["body_compat_tip"],
            row["cham_compat_tip"],
            row["body_compat_count_tip"],
            row["cham_compat_count_tip"],
            row["tip"],
            row["childeqp"],
        ])

    return output.getvalue()


def get_history_week_options(lineid="", processid=""):
    def _collect_dates(qs, field_name):
        return {
            d
            for d in qs.exclude(**{f"{field_name}__isnull": True}).values_list(field_name, flat=True).distinct()
            if d
        }

    summary_qs = FactsHistorySummaryCache.objects.all()
    wip_qs = FactsWipSource.objects.all()
    edit_qs = FactsEditHistory.objects.all()

    if lineid:
        summary_qs = summary_qs.filter(lineid=lineid)
        wip_qs = wip_qs.filter(lineid=lineid)
        edit_qs = edit_qs.filter(lineid=lineid)
    if processid:
        summary_qs = summary_qs.filter(processid=processid)
        wip_qs = wip_qs.filter(processid=processid)
        edit_qs = edit_qs.filter(processid=processid)

    dates = _collect_dates(summary_qs, "summary_date")
    if not dates:
        dates = _collect_dates(wip_qs, "snap_date")

    if not dates:
        dates = _collect_dates(edit_qs, "snap_date")

    week_set = {f"W{d.isocalendar()[1]:02d}" for d in dates}
    return sorted(week_set)
