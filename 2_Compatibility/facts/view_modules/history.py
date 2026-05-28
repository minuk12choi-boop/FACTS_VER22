from facts.debug_logging import try_save_feedback_log
from facts.json_safety import _assert_json_serializable, _json_safe_payload
import time

from .common import (
    FactsHistorySummaryCache,
    FactsEditHistory,
    _check_page_permission,
    _ensure_browser_close_session,
    _normalize_date_input,
    _parse_bool,
    _parse_week_input,
    _record_access_history,
    _week_display,
    date,
    login_required,
    render,
    services,
    timedelta,
    cache,
    JsonResponse,
    require_GET,
)


def _history_cache_key_dict(summary_date, lineid, processid, include_measure, include_emergency, exclude_skiprule_100):
    return {
        "summary_date": summary_date,
        "lineid": lineid or "",
        "processid": processid or "",
        "include_measure": bool(include_measure),
        "include_emergency": bool(include_emergency),
        "exclude_skiprule_100": bool(exclude_skiprule_100),
    }


def _get_history_card_cached(summary_date, lineid, processid, include_measure, include_emergency, exclude_skiprule_100):
    key_kwargs = _history_cache_key_dict(summary_date, lineid, processid, include_measure, include_emergency, exclude_skiprule_100)
    row = FactsHistorySummaryCache.objects.filter(**key_kwargs).first()
    if row:
        return row.payload_json or {}
    cards = services.get_history_daily_cards(
        week_dates=[summary_date],
        lineid=lineid,
        processid=processid,
        include_measure=include_measure,
        include_emergency=include_emergency,
        exclude_skiprule_100=exclude_skiprule_100,
    )
    payload = cards[0] if cards else {}
    safe_payload = _assert_json_serializable(_json_safe_payload(payload))
    FactsHistorySummaryCache.objects.update_or_create(
        **key_kwargs,
        defaults={"payload_json": safe_payload},
    )
    return safe_payload

def _make_history_label_rows(rows):
    for row in rows:
        row.action_type_label = services.get_action_type_label(row.action_type, row.before_json, row.after_json)
    return rows

@login_required
def history_view(request):
    _ensure_browser_close_session(request)
    permission_response = _check_page_permission(request, "history", ignore_blank_scope=True)
    if permission_response is not None:
        return permission_response


    _record_access_history(request, 'history')
    base_snap_date = _normalize_date_input(request.GET.get("snap_date")) or services.get_latest_snap_date() or date.today()
    raw_snap_date = _normalize_date_input(request.GET.get("raw_snap_date")) or base_snap_date
    week_raw = (request.GET.get("week") or "").strip()
    lineid = request.GET.get("lineid") or ""
    processid = request.GET.get("processid") or ""
    action_type = request.GET.get("action_type") or ""
    scope_response = _check_page_permission(request, "history", lineid=(lineid or "").strip(), processid=(processid or "").strip(), popup=True, ignore_blank_scope=True)
    if scope_response is not None:
        return scope_response
    include_measure = _parse_bool(request.GET.get("include_measure"), default=("include_measure" not in request.GET))
    include_emergency = _parse_bool(request.GET.get("include_emergency"), default=("include_emergency" not in request.GET))
    exclude_skiprule_100 = _parse_bool(request.GET.get("exclude_skiprule_100"), default=("exclude_skiprule_100" not in request.GET))

    timing_total_start = time.perf_counter()
    debug_timing = str(request.GET.get("debug_timing") or "").strip() == "1"
    timing_map = {}
    timing_options_start = time.perf_counter()
    week_options = services.get_history_week_options()
    fallback_latest_week = _week_display(base_snap_date.isocalendar()[1])
    latest_week = week_options[-1] if week_options else fallback_latest_week
    timing_map["filter_option_build"] = time.perf_counter() - timing_options_start

    selected_week = week_raw or latest_week
    if selected_week not in week_options and week_options:
        selected_week = latest_week

    missing_msgs = []
    if request.GET.get("_search") == "1":
        if not processid.strip():
            missing_msgs.append("PRP를 선택한 뒤 조회하세요.")
        if not selected_week.strip():
            missing_msgs.append("주차를 선택한 뒤 조회하세요.")
        if missing_msgs:
            return services._popup_redirect("\n".join(missing_msgs), "/facts/history/?" + request.META.get("QUERY_STRING", ""))

    should_query = bool(processid.strip() and selected_week.strip())

    week_no = _parse_week_input(selected_week)
    iso_year, current_week, _ = base_snap_date.isocalendar()
    target_week = week_no or current_week

    try:
        monday = date.fromisocalendar(iso_year, target_week, 1)
    except ValueError:
        monday = base_snap_date - timedelta(days=base_snap_date.isoweekday() - 1)
        target_week = current_week
    week_dates = [monday + timedelta(days=i) for i in range(7)]

    cards = []
    today_val = date.today()
    timing_query_start = time.perf_counter()
    if should_query:
        for d in week_dates:
            if d < today_val:
                card = _get_history_card_cached(
                summary_date=d,
                lineid=lineid,
                processid=processid,
                include_measure=include_measure,
                include_emergency=include_emergency,
                exclude_skiprule_100=exclude_skiprule_100,
            )
                if card:
                    cards.append(card)
            else:
                realtime = services.get_history_daily_cards(
                week_dates=[d],
                lineid=lineid,
                processid=processid,
                include_measure=include_measure,
                include_emergency=include_emergency,
                exclude_skiprule_100=exclude_skiprule_100,
            )
                if realtime:
                    cards.append(realtime[0])
        timing_map["query_block"] = time.perf_counter() - timing_query_start
    else:
        timing_map["query_skipped"] = True

    base_qs = FactsEditHistory.objects.select_related("changed_by").all() if should_query else FactsEditHistory.objects.none()
    if lineid:
        base_qs = base_qs.filter(lineid=lineid)
    if processid:
        base_qs = base_qs.filter(processid=processid)
    if raw_snap_date:
        base_qs = base_qs.filter(snap_date=raw_snap_date)
    else:
        base_qs = base_qs.filter(snap_date__gte=min(week_dates), snap_date__lte=max(week_dates))

    action_option_values = list(base_qs.values_list("action_type", flat=True).distinct().order_by("action_type"))
    action_choices = [(v, services.get_action_type_label(v)) for v in action_option_values]

    qs = base_qs
    if action_type:
        qs = qs.filter(action_type=action_type)
    rows = list(qs.order_by("-created_at")[:500])
    _make_history_label_rows(rows)

    cfg = services.get_dashboard_config()
    inquiry_contact = cfg.inquiry_contact if hasattr(cfg, "inquiry_contact") else cfg["inquiry_contact"]
    options = cache.get("facts:history:master-options")
    if options is None:
        options = services.get_distinct_master_options(None)
        cache.set("facts:history:master-options", options, 3600)

    context = {
        "pre_query_state": not should_query,
        "page_title": "변경 이력 확인",
        "rows": rows,
        "cards": cards,
        "action_choices": action_choices,
        "selected_snap_date": base_snap_date.isoformat(),
        "selected_raw_snap_date": raw_snap_date.isoformat() if raw_snap_date else "",
        "selected_week": selected_week,
        "selected_lineid": lineid,
        "selected_processid": processid,
        "selected_action_type": action_type,
        "include_measure": include_measure,
        "include_emergency": include_emergency,
        "exclude_skiprule_100": exclude_skiprule_100,
        "week_options": week_options,
        "line_options": options["line_options"],
        "prp_options": options["prp_options"],
        "inquiry_contact": inquiry_contact,
    }
    total_elapsed = time.perf_counter() - timing_total_start
    timing_map["total_view"] = total_elapsed
    response = render(request, "facts/history.html", context)
    if debug_timing:
        info = [
            f"request_path={request.path}",
            f"query_string={request.META.get('QUERY_STRING','')}",
            f"selected_filters=lineid:{lineid}, processid:{processid}, selected_week:{selected_week}, should_query:{should_query}",
            f"timing={timing_map}",
            f"query_skipped={not should_query}",
            f"get_history_daily_cards_called={should_query}",
            f"FactsEditHistory_annotate_count_called={should_query}",
            f"FactsHistorySummaryCache_payload_called={should_query}",
            f"build_step_dataset_called={False}",
            f"context_size_keys={len(context.keys())}",
            f"render_suspect={total_elapsed > 3.0}",
            f"base_layout_context_processor_suspect={total_elapsed > 3.0 and not should_query}",
        ]
        try_save_feedback_log('history_timing', "\n".join(info), 'HISTORY_TIMING')
    print(f"[HISTORY_TIMING] total={total_elapsed:.4f}s")
    return response


@require_GET
@login_required
def history_options_api(request):
    _ensure_browser_close_session(request)
    permission_response = _check_page_permission(request, "history", ignore_blank_scope=True)
    if permission_response is not None:
        return permission_response
    snap_date = _normalize_date_input(request.GET.get("snap_date")) or services.get_latest_snap_date() or date.today()
    lineid = (request.GET.get("lineid") or "").strip()
    processid = (request.GET.get("processid") or "").strip()
    payload = services.get_line_prp_options(snap_date=snap_date, lineid=lineid, processid=processid)
    payload["ok"] = True
    return JsonResponse(payload)
