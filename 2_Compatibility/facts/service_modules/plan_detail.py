from .common import (
    FactsEditHistory,
    FactsStepPlan,
    date,
    datetime,
    defaultdict,
)
from django.utils import timezone
from .dashboard_filters import _natural_sort_key



def _build_plan_alive_state_map(snap_date, step_keys, as_of_date=None):
    resolved_as_of = _as_of_date(as_of_date) or _as_of_date(snap_date)
    if resolved_as_of is None:
        return {}, {}
    valid_keys = {_step_group_key(l,p,s) for l,p,s in step_keys if str(p or '').strip() and str(s or '').strip()}
    if not valid_keys:
        return {}, {}
    cutoff = _as_of_cutoff(resolved_as_of)
    processids = sorted({p for _,p,_ in valid_keys if p})
    stepseqs = sorted({s for _,_,s in valid_keys if s})
    lineids = sorted({l for l,_,_ in valid_keys})
    state_by_step = defaultdict(dict)
    excluded_by_delete = defaultdict(list)

    history_qs = FactsEditHistory.objects.filter(
        action_type__in=["plan_add","plan_update","plan_delete","bulk_upload"],
        created_at__lte=cutoff, processid__in=processids, stepseq__in=stepseqs, lineid__in=lineids
    ).order_by('created_at','id')

    for row in history_qs:
        payload_after = row.after_json or {}
        payload_before = row.before_json or {}
        effective_snap = _as_of_date(row.snap_date)
        if effective_snap and effective_snap > resolved_as_of:
            continue
        if row.action_type == 'bulk_upload' and _classify_history_payload_type(payload_before, payload_after) != 'plan':
            continue
        step_key = _step_group_key(row.lineid, row.processid, row.stepseq)
        if step_key not in valid_keys:
            continue
        is_delete = row.action_type == 'plan_delete' or (row.action_type=='bulk_upload' and str(payload_after.get('is_active','1')).strip().lower() in {'0','false','n','no'})
        payload = payload_before if is_delete else payload_after
        if not _history_payload_matches_plan(payload):
            continue
        before_key = _history_item_key(row, payload_before)
        after_key = _history_item_key(row, payload_after)
        if is_delete:
            deleted = state_by_step[step_key].pop(before_key, None)
            if deleted:
                excluded_by_delete[step_key].append(deleted)
            continue
        if row.action_type == 'plan_update' and before_key != after_key:
            state_by_step[step_key].pop(before_key, None)
        plan_id = payload_after.get('id') or payload_before.get('id') or ''
        state_by_step[step_key][after_key] = {
            'id': plan_id, 'plan_id': plan_id, 'history_id': row.id,
            'lineid': str(payload_after.get('lineid') or row.lineid or '').strip(),
            'processid': str(row.processid or '').strip(), 'stepseq': str(row.stepseq or '').strip(),
            'always_emergency': str(payload_after.get('always_emergency') or '').strip(),
            'major_minor': str(payload_after.get('major_minor') or '').strip(),
            'eqp_body_name': str(payload_after.get('eqp_body_name') or '').strip(),
            'eqp_cham_name': str(payload_after.get('eqp_cham_name') or '').strip(),
            'compatibility_due_date': str(payload_after.get('compatibility_due_date') or '').strip(),
            'eval_lot_id': str(payload_after.get('eval_lot_id') or '').strip(),
            'required_eval_stage_id': payload_after.get('required_eval_stage_id') or '',
            'required_eval_stage_code': str(payload_after.get('required_eval_stage_code') or '').strip(),
            'required_eval_stage_name': str(payload_after.get('required_eval_stage_name') or '').strip(),
            'memo': str(payload_after.get('memo') or '').strip(),
            'source_type': 'history',
        }

    return state_by_step, excluded_by_delete

def get_plan_detail_rows_as_of(snap_date, lineid, processid, stepseq):
    snap_date = _as_of_date(snap_date)
    if snap_date is None:
        return []
    step_key = _step_group_key(lineid, processid, stepseq)
    state_by_step, _ = _build_plan_alive_state_map(snap_date, [(lineid, processid, stepseq)], as_of_date=snap_date)
    rows = list((state_by_step.get(step_key) or {}).values())
    rows.sort(key=lambda x: (_natural_sort_key(x.get('eqp_body_name') or ''), _natural_sort_key(x.get('eqp_cham_name') or ''), str(x.get('plan_id') or x.get('id') or '')))
    return rows



def _classify_history_payload_type(payload_before, payload_after):
    before = payload_before or {}
    after = payload_after or {}
    keys = {str(k) for k in list(before.keys()) + list(after.keys())}
    plan_keys = {
        "compatibility_due_date", "eval_lot_id", "required_eval_stage_id", "required_eval_stage_code", "required_eval_stage_name", "memo",
        "plan_body_names", "plan_cham_names", "plan_due_dates", "plan_eval_lot_ids", "plan_eval_stages", "plan_memos",
    }
    tip_keys = {"always_emergency", "major_minor", "eqp_body_name", "eqp_cham_name", "tip_missing_id", "path_id", "target_id"}
    if any(k.startswith('plan_') for k in keys) or any(k in plan_keys for k in keys):
        return "plan"
    if any(k in tip_keys for k in keys):
        return "tip_missing"
    return "unknown"
def _history_payload_matches_plan(payload):
    payload = payload or {}
    plan_keys = ["compatibility_due_date", "eval_lot_id", "required_eval_stage_id", "required_eval_stage_code", "required_eval_stage_name", "memo"]
    return any(k in payload for k in plan_keys)

def _build_plan_summary_map(step_keys, as_of_date=None):
    resolved_as_of = _as_of_date(as_of_date)
    if resolved_as_of is None:
        return {}
    valid_keys = {
        _step_group_key(l, p, s)
        for l, p, s in step_keys
        if (str(p or "").strip() and str(s or "").strip())
    }
    if not valid_keys:
        return {}

    cutoff = _as_of_cutoff(resolved_as_of)
    processids = sorted({p for _, p, _ in valid_keys if p})
    stepseqs = sorted({s for _, _, s in valid_keys if s})
    lineids = sorted({l for l, _, _ in valid_keys})

    result = {}
    history_seen_keys = set()

    state_by_step, _ = _build_plan_alive_state_map(resolved_as_of, list(valid_keys), as_of_date=resolved_as_of)
    for k,v in state_by_step.items():
        if v:
            history_seen_keys.add(k)
            items = list(v.values())
            result[k] = {
                "plan_flag": "Y",
                "plan_body_names": _uniq_join([x["eqp_body_name"].upper() for x in items], upper=False),
                "plan_cham_names": _uniq_join([x["eqp_cham_name"].upper() for x in items], upper=False),
                "plan_due_dates": _uniq_join([x["compatibility_due_date"] for x in items], upper=False),
                "plan_eval_lot_ids": _uniq_join([x["eval_lot_id"] for x in items], upper=False),
                "plan_eval_stages": _uniq_join([x["required_eval_stage_name"] for x in items], upper=False),
                "plan_memos": _uniq_join([x["memo"] for x in items], upper=False),
                "has_plan": True,
            }

    if cutoff is not None:
        history_qs = FactsEditHistory.objects.filter(
            action_type__in=["plan_add", "plan_update", "plan_delete", "bulk_upload"],
            created_at__lte=cutoff,
            processid__in=processids,
            stepseq__in=stepseqs,
            lineid__in=lineids,
        ).order_by("created_at", "id")

        state_by_step = defaultdict(dict)

        for row in history_qs:
            payload_after = row.after_json or {}
            payload_before = row.before_json or {}
            effective_snap = _as_of_date(row.snap_date)
            if effective_snap and resolved_as_of and effective_snap > resolved_as_of:
                continue
            bulk_payload_type = "plan"
            if row.action_type == "bulk_upload":
                bulk_payload_type = _classify_history_payload_type(payload_before, payload_after)
                if bulk_payload_type != "plan":
                    continue
            payload = payload_after if row.action_type != "plan_delete" else payload_before

            if not _history_payload_matches_plan(payload):
                continue

            step_key = _step_group_key(row.lineid, row.processid, row.stepseq)
            if step_key not in valid_keys:
                continue

            history_seen_keys.add(step_key)

            before_key = _history_item_key(row, payload_before)
            after_key = _history_item_key(row, payload_after)

            if row.action_type == "plan_delete":
                state_by_step[step_key].pop(before_key, None)
            else:
                if row.action_type == "plan_update" and before_key != after_key:
                    state_by_step[step_key].pop(before_key, None)

                state_by_step[step_key][after_key] = {
                    "eqp_body_name": str(payload_after.get("eqp_body_name") or "").strip().upper(),
                    "eqp_cham_name": str(payload_after.get("eqp_cham_name") or "").strip().upper(),
                    "compatibility_due_date": str(payload_after.get("compatibility_due_date") or "").strip(),
                    "eval_lot_id": str(payload_after.get("eval_lot_id") or "").strip(),
                    "required_eval_stage_name": str(payload_after.get("required_eval_stage_name") or "").strip(),
                    "memo": str(payload_after.get("memo") or "").strip(),
                }

    fallback_keys = valid_keys - history_seen_keys
    if fallback_keys:
        qs = FactsStepPlan.objects.filter(
            processid__in=[p for _, p, _ in fallback_keys],
            stepseq__in=[s for _, _, s in fallback_keys],
            lineid__in=[l for l, _, _ in fallback_keys],
            is_active=True,
        ).select_related("required_eval_stage").order_by("-updated_at", "-id")

        if cutoff is not None:
            qs = qs.filter(created_at__lte=cutoff, updated_at__lte=cutoff)

        grouped = defaultdict(list)
        for obj in qs:
            key = _step_group_key(obj.lineid, obj.processid, obj.stepseq)
            if key in fallback_keys:
                grouped[key].append(obj)

        for key, plan_qs in grouped.items():
            result[key] = {
                "plan_flag": "Y",
                "plan_body_names": _uniq_join([x.eqp_body_name for x in plan_qs]),
                "plan_cham_names": _uniq_join([x.eqp_cham_name for x in plan_qs]),
                "plan_due_dates": _uniq_join([
                    x.compatibility_due_date.strftime("%Y-%m-%d") if x.compatibility_due_date else ""
                    for x in plan_qs
                ]),
                "plan_eval_lot_ids": _uniq_join([x.eval_lot_id for x in plan_qs]),
                "plan_eval_stages": _uniq_join([
                    x.required_eval_stage.stage_name if x.required_eval_stage else ""
                    for x in plan_qs
                ]),
                "plan_memos": _uniq_join([x.memo for x in plan_qs]),
                "has_plan": True,
            }

    unresolved_keys = valid_keys - set(result.keys())
    if unresolved_keys:
        qs = FactsStepPlan.objects.filter(
            processid__in=[p for _, p, _ in unresolved_keys],
            stepseq__in=[s for _, _, s in unresolved_keys],
            lineid__in=[l for l, _, _ in unresolved_keys],
            is_active=True,
        ).select_related("required_eval_stage").order_by("-updated_at", "-id")
        if cutoff is not None:
            qs = qs.filter(created_at__lte=cutoff, updated_at__lte=cutoff)
        grouped = defaultdict(list)
        for obj in qs:
            key = _step_group_key(obj.lineid, obj.processid, obj.stepseq)
            if key in unresolved_keys:
                grouped[key].append(obj)
        for key, plan_qs in grouped.items():
            result[key] = {
                "plan_flag": "Y",
                "plan_body_names": _uniq_join([x.eqp_body_name for x in plan_qs]),
                "plan_cham_names": _uniq_join([x.eqp_cham_name for x in plan_qs]),
                "plan_due_dates": _uniq_join([
                    x.compatibility_due_date.strftime("%Y-%m-%d") if x.compatibility_due_date else ""
                    for x in plan_qs
                ]),
                "plan_eval_lot_ids": _uniq_join([x.eval_lot_id for x in plan_qs]),
                "plan_eval_stages": _uniq_join([
                    x.required_eval_stage.stage_name if x.required_eval_stage else ""
                    for x in plan_qs
                ]),
                "plan_memos": _uniq_join([x.memo for x in plan_qs]),
                "has_plan": True,
            }

    return result

def _history_item_key(row, payload):
    data = payload or {}
    obj_id = _history_payload_object_id(data)
    if obj_id is not None:
        return ("id", obj_id)
    body = str(data.get("eqp_body_name") or "").strip().upper()
    cham = str(data.get("eqp_cham_name") or "").strip().upper()
    recipeid = _history_item_recipeid(row, data)
    return ("value", body, cham, recipeid)

def _history_payload_object_id(payload):
    payload = payload or {}
    obj_id = payload.get("id")
    try:
        if obj_id in (None, ""):
            return None
        return int(obj_id)
    except (TypeError, ValueError):
        return None

def _history_item_recipeid(row, payload):
    return str((payload or {}).get("recipeid") or getattr(row, "recipeid", "") or "").strip().upper()

def _as_of_cutoff(as_of_date):
    as_of = _as_of_date(as_of_date)
    if as_of is None:
        return None
    naive_cutoff = datetime.combine(as_of, datetime.max.time())
    if timezone.is_naive(naive_cutoff):
        return timezone.make_aware(naive_cutoff, timezone.get_current_timezone())
    return naive_cutoff

def _as_of_date(value):
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    s = str(value).strip()
    if not s:
        return None
    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%Y.%m.%d", "%Y%m%d"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    return None

def _step_group_key(lineid, processid, stepseq):
    return ((lineid or "").strip(), (processid or "").strip(), (stepseq or "").strip())

def _uniq_join(values, upper=False):
    out = []
    for v in values:
        s = str(v or "").strip()
        if upper:
            s = s.upper()
        if s and s not in out:
            out.append(s)
    return " | ".join(out)
