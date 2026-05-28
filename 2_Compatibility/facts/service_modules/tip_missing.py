from datetime import timezone as dt_timezone
from .common import (
    FactsEditHistory,
    FactsTipMissingCompatPath,
    datetime,
    defaultdict,
)
from django.utils import timezone
from .dashboard_filters import _natural_sort_key
from .plan_detail import _as_of_cutoff, _as_of_date, _history_item_key, _step_group_key, _uniq_join

def get_tip_missing_detail_rows_as_of(snap_date, lineid, processid, stepseq):
    snap_date = _as_of_date(snap_date)
    if snap_date is None:
        return []
    cutoff = _as_of_cutoff(snap_date)
    rows = []

    history_qs = FactsEditHistory.objects.filter(
        action_type__in=["tip_missing_add", "tip_missing_update", "tip_missing_delete", "bulk_upload"],
        snap_date__lte=snap_date,
        created_at__lte=cutoff,
        lineid=lineid,
        processid=processid,
        stepseq=stepseq,
    ).order_by("created_at", "id")

    state = {}
    for row in history_qs:
        payload_after = row.after_json or {}
        payload_before = row.before_json or {}
        bulk_payload_type = classify_history_payload_type(payload_before, payload_after) if row.action_type == "bulk_upload" else "tip_missing"
        if row.action_type == "bulk_upload" and bulk_payload_type != "tip_missing":
            continue
        is_delete = row.action_type == "tip_missing_delete" or (
            row.action_type == "bulk_upload"
            and str(payload_after.get("is_active", "1")).strip().lower() in {"0", "false", "n", "no"}
        )
        payload = payload_after if not is_delete else payload_before
        if not _history_payload_matches_tip_missing(payload):
            continue
        effective_snap = _as_of_date(row.snap_date)
        if effective_snap and effective_snap > snap_date:
            continue
        before_key = _history_item_key(row, payload_before)
        after_key = _history_item_key(row, payload_after)
        if is_delete:
            state.pop(before_key, None)
            continue
        if row.action_type == "tip_missing_update" and before_key != after_key:
            state.pop(before_key, None)
        tip_id = payload_after.get("id") or payload_before.get("id") or payload_after.get("tip_missing_id") or payload_before.get("tip_missing_id") or ""
        state[after_key] = {
            "id": tip_id,
            "tip_missing_id": tip_id,
            "history_id": row.id,
            "lineid": str(payload_after.get("lineid") or row.lineid or "").strip(),
            "always_emergency": str(payload_after.get("always_emergency") or "").strip(),
            "major_minor": str(payload_after.get("major_minor") or "").strip(),
            "eqp_body_name": str(payload_after.get("eqp_body_name") or "").strip(),
            "eqp_cham_name": str(payload_after.get("eqp_cham_name") or "").strip(),
        }

    if state:
        rows = list(state.values())
    else:
        qs = FactsTipMissingCompatPath.objects.filter(
            snap_date__lte=snap_date,
            lineid=lineid,
            processid=processid,
            stepseq=stepseq,
            is_active=True,
        )
        if cutoff is not None:
            qs = qs.filter(created_at__lte=cutoff, updated_at__lte=cutoff)
        rows = [{
            "id": obj.id,
            "tip_missing_id": obj.id,
            "history_id": "",
            "lineid": obj.lineid or "",
            "always_emergency": obj.always_emergency or "",
            "major_minor": obj.major_minor or "",
            "eqp_body_name": obj.eqp_body_name or "",
            "eqp_cham_name": obj.eqp_cham_name or "",
        } for obj in qs.order_by("-snap_date", "-updated_at", "-id")]

    rows.sort(key=lambda x: (_natural_sort_key(x.get("eqp_body_name") or ""), _natural_sort_key(x.get("eqp_cham_name") or ""), str(x.get("id") or "")), reverse=False)
    return rows

def _history_payload_matches_tip_missing(payload):
    payload = payload or {}
    return any(k in payload for k in ["always_emergency", "major_minor", "eqp_body_name", "eqp_cham_name"])


def classify_history_payload_type(payload_before, payload_after):
    before = payload_before or {}
    after = payload_after or {}
    keys = {str(k) for k in list(before.keys()) + list(after.keys())}

    tip_keys = {
        "always_emergency", "major_minor", "eqp_body_name", "eqp_cham_name",
        "tip_missing_flag", "tip_missing_body", "tip_missing_cham", "tip_missing_always", "tip_missing_major",
        "tip_missing_id", "path_id", "target_id",
    }
    plan_keys = {
        "compatibility_due_date", "eval_lot_id", "required_eval_stage_id", "required_eval_stage_code", "required_eval_stage_name", "memo",
        "plan_body_names", "plan_cham_names", "plan_due_dates", "plan_eval_lot_ids", "plan_eval_stages", "plan_memos",
    }
    if any(k.startswith('plan_') for k in keys) or any(k in plan_keys for k in keys):
        return "plan"
    if any(k in tip_keys for k in keys):
        return "tip_missing"
    return "unknown"


def _tip_missing_path_identity(step_key, payload, fallback_id=None):
    payload = payload or {}
    row_id = payload.get("id") or payload.get("tip_missing_id") or payload.get("target_id") or payload.get("path_id")
    if row_id not in (None, ""):
        return ("id", str(row_id))

    lineid, processid, stepseq = step_key
    lineid_value = str(payload.get("lineid") or lineid or "").strip().upper()
    processid_value = str(payload.get("processid") or processid or "").strip().upper()
    stepseq_value = str(payload.get("stepseq") or stepseq or "").strip().upper()
    recipeid = str(payload.get("recipeid") or "").strip().upper()
    body = str(payload.get("eqp_body_name") or "").strip().upper()
    cham = str(payload.get("eqp_cham_name") or "").strip().upper()
    always = str(payload.get("always_emergency") or "").strip().upper()
    major = str(payload.get("major_minor") or "").strip().upper()
    natural_key = (lineid_value, processid_value, stepseq_value, recipeid, body, cham, always, major)
    if any(natural_key):
        return ("natural",) + natural_key
    if fallback_id not in (None, ""):
        return ("fallback", str(fallback_id))
    return ("unknown",)

def _build_tip_missing_summary_map(snap_date, step_keys, as_of_date=None):
    snap_date = _as_of_date(snap_date)
    if snap_date is None:
        return {}
    resolved_as_of = _as_of_date(as_of_date) or snap_date
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

    state_by_step = defaultdict(dict)

    base_qs = FactsTipMissingCompatPath.objects.filter(
        snap_date__lte=snap_date,
        processid__in=processids,
        stepseq__in=stepseqs,
        lineid__in=lineids,
        is_active=True,
    ).order_by("snap_date", "created_at", "updated_at", "id")
    if cutoff is not None:
        base_qs = base_qs.filter(created_at__lte=cutoff, updated_at__lte=cutoff)

    for obj in base_qs:
        step_key = _step_group_key(obj.lineid, obj.processid, obj.stepseq)
        if step_key not in valid_keys:
            continue
        payload = {
            "id": obj.id,
            "recipeid": obj.recipeid,
            "always_emergency": str(obj.always_emergency or "").strip(),
            "major_minor": str(obj.major_minor or "").strip(),
            "eqp_body_name": str(obj.eqp_body_name or "").strip().upper(),
            "eqp_cham_name": str(obj.eqp_cham_name or "").strip().upper(),
        }
        item_key = _tip_missing_path_identity(step_key, payload, fallback_id=obj.id)
        state_by_step[step_key][item_key] = payload

    if cutoff is not None:
        history_qs = FactsEditHistory.objects.filter(
            action_type__in=["tip_missing_add", "tip_missing_update", "tip_missing_delete", "bulk_upload"],
            snap_date__lte=snap_date,
            created_at__lte=cutoff,
            processid__in=processids,
            stepseq__in=stepseqs,
            lineid__in=lineids,
        ).order_by("created_at", "id")

        for row in history_qs:
            payload_after = row.after_json or {}
            payload_before = row.before_json or {}
            bulk_payload_type = classify_history_payload_type(payload_before, payload_after) if row.action_type == "bulk_upload" else "tip_missing"
            if row.action_type == "bulk_upload" and bulk_payload_type != "tip_missing":
                continue
            if row.action_type in {"plan_add", "plan_update", "plan_delete"}:
                continue
            is_delete = row.action_type == "tip_missing_delete" or (
                row.action_type == "bulk_upload"
                and str(payload_after.get("is_active", "1")).strip().lower() in {"0", "false", "n", "no"}
            )
            payload = payload_after if not is_delete else payload_before
            if row.action_type == "tip_missing_delete":
                payload = payload_before or payload_after
            if row.action_type != "tip_missing_delete" and not _history_payload_matches_tip_missing(payload):
                continue
            effective_snap = _as_of_date(row.snap_date)
            if effective_snap and effective_snap > snap_date:
                continue

            step_key = _step_group_key(row.lineid, row.processid, row.stepseq)
            if step_key not in valid_keys:
                continue

            before_key = _tip_missing_path_identity(step_key, payload_before, fallback_id=row.id) if payload_before else None
            after_key = _tip_missing_path_identity(step_key, payload_after, fallback_id=row.id) if payload_after else None

            if is_delete:
                delete_key = before_key or after_key
                if delete_key:
                    state_by_step[step_key].pop(delete_key, None)
                continue

            if not after_key and before_key:
                state_by_step[step_key].pop(before_key, None)
                continue
            if row.action_type == "tip_missing_update" and before_key and after_key and before_key != after_key:
                state_by_step[step_key].pop(before_key, None)
            if not after_key:
                continue

            tip_id = payload_after.get("id") or payload_before.get("id") or payload_after.get("tip_missing_id") or payload_before.get("tip_missing_id") or ""
            state_by_step[step_key][after_key] = {
                "id": tip_id,
                "tip_missing_id": tip_id,
                "history_id": row.id,
                "recipeid": str(payload_after.get("recipeid") or "").strip(),
                "always_emergency": str(payload_after.get("always_emergency") or "").strip(),
                "major_minor": str(payload_after.get("major_minor") or "").strip(),
                "eqp_body_name": str(payload_after.get("eqp_body_name") or "").strip().upper(),
                "eqp_cham_name": str(payload_after.get("eqp_cham_name") or "").strip().upper(),
            }

    result = {}
    for key, items_dict in state_by_step.items():
        if not items_dict:
            continue
        items = list(items_dict.values())

        manual_body_list = []
        manual_cham_list = []
        manual_path_objects = []

        for data in items:
            body = data.get("eqp_body_name") or ""
            cham = data.get("eqp_cham_name") or ""
            if body and body not in manual_body_list:
                manual_body_list.append(body)
            cham_token = f"{body}-{cham}" if body and cham else ""
            if cham_token and cham_token not in manual_cham_list:
                manual_cham_list.append(cham_token)
            manual_path_objects.append({
                "tip_missing_id": data.get("id") or "",
                "history_id": data.get("history_id") or "",
                "always_emergency": data.get("always_emergency") or "",
                "major_minor": data.get("major_minor") or "",
                "body": body,
                "cham": cham,
                "eqp_body_name": body,
                "eqp_cham_name": cham,
                "cham_token": cham_token,
            })

        result[key] = {
            "tip_missing_flag": "Y",
            "tip_missing_always": _uniq_join([x.get("always_emergency") for x in items]),
            "tip_missing_major": _uniq_join([x.get("major_minor") for x in items]),
            "tip_missing_body": _uniq_join([x.get("eqp_body_name") for x in items]),
            "tip_missing_cham": _uniq_join([x.get("eqp_cham_name") for x in items]),
            "manual_body_list": manual_body_list,
            "manual_cham_list": manual_cham_list,
            "manual_path_objects": manual_path_objects,
        }

    return result

def _normalize_dt_for_compare(value):
    if not value:
        return None
    if timezone.is_naive(value):
        return timezone.make_aware(value, timezone.get_current_timezone())
    return value.astimezone(dt_timezone.utc)


def calculate_prevent_age_days(eventtime, as_of_date=None):
    if not eventtime:
        return 0

    cutoff_dt = _as_of_cutoff(as_of_date) or timezone.now()
    cutoff_norm = _normalize_dt_for_compare(cutoff_dt)
    event_norm = _normalize_dt_for_compare(eventtime)
    if not cutoff_norm or not event_norm:
        return 0

    age_days = (cutoff_norm - event_norm).days
    return max(int(age_days), 0)


def _row_is_tip_prevented(row, threshold_days, as_of_date=None):
    tip_value = str(getattr(row, "tip", "") or "").strip().upper()
    prevent_value = str(getattr(row, "prevent", "") or "").strip().upper()
    is_prevent_marked = prevent_value == "PREVENT" or tip_value.startswith("PREVENT")
    if not is_prevent_marked:
        return False

    eventtime = getattr(row, "eventtime", None)
    if not eventtime:
        return False

    try:
        threshold_days = int(threshold_days)
    except (TypeError, ValueError):
        threshold_days = 7
    if threshold_days <= 0:
        threshold_days = 7

    age_days = calculate_prevent_age_days(eventtime, as_of_date=as_of_date)
    return age_days >= threshold_days


# backward compatibility for existing debug/management imports
def _classify_bulk_payload_type(payload_before, payload_after):
    return classify_history_payload_type(payload_before, payload_after)
