from .common import (
    ACTION_TYPE_LABELS,
    FactsEditHistory,
    FactsWipSource,
)

def get_action_type_label(action_type, before_json=None, after_json=None):
    label = ACTION_TYPE_LABELS.get(action_type, action_type)
    before = before_json or {}
    after = after_json or {}
    try:
        if action_type == "override":
            if before.get("manual_always_emergency") != after.get("manual_always_emergency"):
                return "상시/비상시 수정"
            if before.get("manual_major_minor") != after.get("manual_major_minor"):
                return "주요/비주요 수정"
        if action_type == "tip_missing_update":
            if before.get("always_emergency") != after.get("always_emergency"):
                return "TIP미등록 호환Path 상시/비상시 수정"
            if before.get("major_minor") != after.get("major_minor"):
                return "TIP미등록 호환Path 주요/비주요 수정"
    except Exception:
        pass
    return label

def get_distinct_master_options(snap_date=None):
    qs = FactsWipSource.objects.all()
    if snap_date:
        qs = qs.filter(snap_date=snap_date)
    return {
        "line_options": list(qs.exclude(lineid__isnull=True).exclude(lineid="").values_list("lineid", flat=True).distinct().order_by("lineid")),
        "prp_options": list(qs.exclude(processid="").values_list("processid", flat=True).distinct().order_by("processid")),
        "area_options": list(qs.exclude(areaname="").values_list("areaname", flat=True).distinct().order_by("areaname")),
    }

def get_history_action_choices(snap_date=None, lineid="", processid=""):
    qs = FactsEditHistory.objects.all()
    if snap_date:
        qs = qs.filter(snap_date=snap_date)
    if lineid:
        qs = qs.filter(lineid=lineid)
    if processid:
        qs = qs.filter(processid=processid)
    values = list(qs.order_by().values_list("action_type", flat=True).distinct())
    values.sort()
    return [(v, get_action_type_label(v)) for v in values]
