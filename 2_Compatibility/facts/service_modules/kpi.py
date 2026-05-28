from .common import (
    FactsKpiTarget,
    Q,
    cache,
    date,
    summarize_steps,
)

def get_kpi_target_value(processid, target_type, snap_date, areaname="", lineid=""):
    if not processid:
        return None

    if target_type == "monthly":
        qs = FactsKpiTarget.objects.filter(
            is_active=True,
            target_type="monthly",
            target_year=snap_date.year,
            target_month=snap_date.month,
            processid=processid,
        )
        if lineid:
            qs = qs.filter(lineid=lineid)
        qs = _filter_kpi_area(qs, areaname)
        obj = qs.order_by("-updated_at").first()
        return float(obj.target_rate) if obj else None

    iso_year, iso_week, _ = snap_date.isocalendar()
    qs = FactsKpiTarget.objects.filter(
        is_active=True,
        target_type="weekly",
        target_year=iso_year,
        target_week=iso_week,
        processid=processid,
    )
    if lineid:
        qs = qs.filter(lineid=lineid)
    qs = _filter_kpi_area(qs, areaname)
    obj = qs.order_by("-updated_at").first()
    return float(obj.target_rate) if obj else None

def _filter_kpi_area(qs, areaname=""):
    area_filter = (areaname or "").strip()
    if area_filter:
        return qs.filter(areaname=area_filter)
    return qs.filter(Q(areaname="") | Q(areaname__isnull=True))

def _month_start(d):
    return date(d.year, d.month, 1)

def _next_month_start(d):
    return date(d.year + (1 if d.month == 12 else 0), 1 if d.month == 12 else d.month + 1, 1)

def _prev_month_start(d):
    return date(d.year - 1, 12, 1) if d.month == 1 else date(d.year, d.month - 1, 1)

def _get_daily_summary_cached(snap_date, **kwargs):
    cache_key = (
        "facts:daily-summary:"
        f"{snap_date}|{kwargs.get('lineid')}|{kwargs.get('processid')}|{kwargs.get('areaname')}|{kwargs.get('layerid')}|"
        f"{int(bool(kwargs.get('include_measure')))}|{int(bool(kwargs.get('include_emergency')))}|"
        f"{int(bool(kwargs.get('exclude_skiprule_100')))}|{int(bool(kwargs.get('tip_mode')))}"
    )
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    from .dashboard_rows import build_step_dataset

    rows = build_step_dataset(snap_date=snap_date, **kwargs)
    if not rows:
        cache.set(cache_key, None, 300)
        return None

    summary = summarize_steps(rows, use_tip=bool(kwargs.get("tip_mode")))
    cache.set(cache_key, summary, 300)
    return summary

def _summary_for_dates(date_list, **kwargs):
    total_cnt = 0
    body_cnt = 0
    cham_exclusive_cnt = 0
    compatible_cnt = 0

    for d in date_list:
        summary = _get_daily_summary_cached(d, **kwargs)
        if not summary:
            continue

        total_cnt += summary["total_steps"]
        body_cnt += summary["body_cnt"]
        cham_exclusive_cnt += summary["cham_cnt"]
        compatible_cnt += summary["compatible_steps"]

    if total_cnt == 0:
        return None

    return {
        "total_rate": round((compatible_cnt / total_cnt) * 100, 1),
        "body_rate": round((body_cnt / total_cnt) * 100, 1),
        "cham_rate_cum": round(((body_cnt + cham_exclusive_cnt) / total_cnt) * 100, 1),
    }
