from .common import (
    JsonResponse,
    _check_page_permission,
    _ensure_browser_close_session,
    _get_permission_scope_defaults,
    _get_request_department,
    _get_request_login_id,
    _normalize_date_input,
    _parse_bool,
    _record_access_history,
    date,
    login_required,
    render,
    require_GET,
    services,
    cache,
)

@login_required
def prevent_tip_view(request):
    _ensure_browser_close_session(request)
    permission_response = _check_page_permission(request, "prevent_tip", ignore_blank_scope=True)
    if permission_response is not None:
        return permission_response


    _record_access_history(request, 'prevent_tip')
    snap_date = _normalize_date_input(request.GET.get("snap_date")) or date.today()
    scope_response = _check_page_permission(request, "prevent_tip", lineid=(request.GET.get("lineid") or "").strip(), processid=(request.GET.get("processid") or "").strip(), popup=True, ignore_blank_scope=True)
    if scope_response is not None:
        return scope_response
    options = cache.get("facts:prevent:master-options")
    if options is None:
        options = services.get_filter_options_from_option_cache(snap_date=snap_date)
        options = {
            "line_options": options.get("line_options", []),
            "prp_options": options.get("prp_options", []),
            "area_options": options.get("area_options", []),
        }
        cache.set("facts:prevent:master-options", options, 3600)
    current_rule = services.get_current_prevent_rule()
    cfg = services.get_dashboard_config()
    inquiry_contact = cfg.inquiry_contact if hasattr(cfg, "inquiry_contact") else cfg["inquiry_contact"]
    context = {
        "page_title": "PREVENT상태 TIP확인",
        "snap_date": snap_date,
        "line_options": options["line_options"],
        "prp_options": options["prp_options"],
        "area_options": options["area_options"],
        "current_rule": current_rule,
        "include_measure": True,
        "exclude_skiprule_100": True,
        "tip_mode": True,
        "inquiry_contact": inquiry_contact,
    }
    return render(request, "facts/prevent_tip.html", context)

@require_GET
@login_required
def prevent_tip_data_api(request):
    _ensure_browser_close_session(request)
    permission_response = _check_page_permission(request, "prevent_tip", ignore_blank_scope=True)
    if permission_response is not None:
        return permission_response


    username = _get_request_login_id(request)
    dept = _get_request_department(request)
    permission_defaults = _get_permission_scope_defaults("prevent_tip", username, dept)

    snap_date = _normalize_date_input(request.GET.get("snap_date")) or date.today()
    lineid = (request.GET.get("lineid") or permission_defaults["lineid"] or "").strip()
    processid = (request.GET.get("processid") or "").strip()
    areaname = (request.GET.get("areaname") or "").strip()
    include_measure = _parse_bool(request.GET.get("include_measure"), default=True)
    exclude_skiprule_100 = _parse_bool(request.GET.get("exclude_skiprule_100"), default=True)
    tip_mode = _parse_bool(request.GET.get("tip_mode"), default=True)
    payload = services.get_prevent_distribution(
        snap_date=snap_date,
        lineid=lineid,
        processid=processid,
        areaname=areaname,
        include_measure=include_measure,
        exclude_skiprule_100=exclude_skiprule_100,
        tip_mode=tip_mode,
    )
    payload["ok"] = True
    return JsonResponse(payload)


@require_GET
@login_required
def prevent_tip_options_api(request):
    _ensure_browser_close_session(request)
    permission_response = _check_page_permission(request, "prevent_tip", ignore_blank_scope=True)
    if permission_response is not None:
        return permission_response
    snap_date = _normalize_date_input(request.GET.get("snap_date")) or date.today()
    lineid = (request.GET.get("lineid") or "").strip()
    processid = (request.GET.get("processid") or "").strip()
    payload = services.get_line_prp_options(snap_date=snap_date, lineid=lineid, processid=processid)
    if not payload.get("line_options") or not payload.get("prp_options"):
        fallback = services.get_filter_options_from_option_cache(snap_date=snap_date)
        payload["line_options"] = payload.get("line_options") or fallback.get("line_options") or []
        payload["prp_options"] = payload.get("prp_options") or fallback.get("prp_options") or []
    payload["ok"] = True
    return JsonResponse(payload)
