import logging
import time

from facts.json_safety import _assert_json_serializable, _json_safe_payload
from facts.debug_logging import try_save_feedback_log

from .common import (
    Alignment,
    DataValidation,
    FactsEditHistory,
    FactsDashboardGraphCache,
    FactsEvalStageMaster,
    FactsGuideDocument,
    FactsLineMaster,
    FactsStepPathOverride,
    FactsStepPlan,
    FactsTipMissingCompatPath,
    FactsWipSource,
    Font,
    FormulaRule,
    HttpResponse,
    JsonResponse,
    PatternFill,
    OperationalError,
    ProgrammingError,
    Workbook,
    _check_page_permission,
    _ensure_browser_close_session,
    _ensure_current_day_editable,
    _get_actor,
    _get_permission_scope_defaults,
    _get_request_department,
    _get_request_login_id,
    _normalize_date_input,
    _normalize_upper,
    _parse_bool,
    _plan_to_json,
    _record_access_history,
    _resolve_snap_date,
    _tip_missing_to_json,
    cache,
    csv,
    datetime,
    ensure_csrf_cookie,
    get_column_letter,
    io,
    json,
    load_workbook,
    login_required,
    rebuild_filter_cache_for_step,
    render,
    require_GET,
    require_POST,
    reverse,
    services,
)

_GRAPH_CACHE_TABLE_READY = None
logger = logging.getLogger(__name__)


def _emit_dashboard_console_logs(filters, timing_marks, combined_series, request_mode="unknown", prp_stats=None):
    metric = combined_series if isinstance(combined_series, dict) else {}
    timing_line = (
        "[DASHBOARD_TIMING] "
        f"mode={request_mode} "
        f"snap_date={filters.get('snap_date')} "
        f"lineid={filters.get('lineid') or ''} "
        f"processid={filters.get('processid') or ''} "
        f"parse={timing_marks.get('request_parse', 0):.2f}s "
        f"summary={timing_marks.get('summary_build', 0):.2f}s "
        f"summary_query={timing_marks.get('summary_query', 0):.2f}s "
        f"summary_format={timing_marks.get('summary_format', 0):.2f}s "
        f"summary_total={timing_marks.get('summary_total', 0):.2f}s "
        f"metric_query={timing_marks.get('metric_query', 0):.2f}s "
        f"series={timing_marks.get('series_build', 0):.2f}s "
        f"prp_rows_build={timing_marks.get('prp_rows_build', 0):.2f}s "
        f"build_step_dataset={timing_marks.get('build_step_dataset', 0):.2f}s "
        f"filter={timing_marks.get('prp_filter_apply', 0):.2f}s "
        f"pagination_sort={timing_marks.get('prp_pagination_sort', 0):.2f}s "
        f"serialize={timing_marks.get('prp_serialize', 0):.2f}s "
        f"json={timing_marks.get('json_response_build', 0):.2f}s "
        f"total={timing_marks.get('total', 0):.2f}s"
    )
    metric_line = (
        "[DASHBOARD_METRIC] "
        f"rows_read={int(metric.get('rows_read') or 0):03d} "
        f"missing_dates_count={int(metric.get('missing_dates_count') or len(metric.get('missing_dates') or []))} "
        f"ignored_out_of_range_dates_count={int(metric.get('ignored_out_of_range_dates_count') or 0)}"
    )
    logger.warning(timing_line)
    logger.warning(metric_line)
    if isinstance(prp_stats, dict):
        prp_line = (
            "[DASHBOARD_PRP_TABLE] "
            f"rows={int(prp_stats.get('rows', 0))} "
            f"filtered_rows={int(prp_stats.get('filtered_rows', 0))} "
            f"page_rows={int(prp_stats.get('page_rows', 0))}"
        )
        logger.warning(prp_line)
        print(prp_line)
    print(timing_line)
    print(metric_line)

def _get_dashboard_common_filters(request):
    snap_date = _resolve_snap_date(request)
    username = _get_request_login_id(request)
    dept = _get_request_department(request)
    permission_defaults = _get_permission_scope_defaults("dashboard", username, dept)
    dashboard_cfg = services.get_dashboard_config()

    if hasattr(dashboard_cfg, "default_prp"):
        default_prp = dashboard_cfg.default_prp or "P1SD"
        inquiry_contact = dashboard_cfg.inquiry_contact or "minuk12.choi"
    else:
        default_prp = dashboard_cfg["default_prp"]
        inquiry_contact = dashboard_cfg["inquiry_contact"]

    processid = request.GET.get("processid")
    if processid is None or processid == "":
        processid = permission_defaults["processid"] or default_prp

    if processid == "미설정":
        processid = ""

    areaname = request.GET.get("areaname") or ""
    layer_values = []
    for raw in request.GET.getlist("layerid"):
        for part in str(raw or "").split(","):
            norm = services.normalize_layer_value(part.strip())
            if norm and norm not in layer_values:
                layer_values.append(norm)
    if not layer_values:
        single_layer = services.normalize_layer_value(request.GET.get("layerid") or "")
        if single_layer:
            layer_values = [single_layer]
    lineid = (request.GET.get("lineid") or permission_defaults["lineid"] or "").strip()
    include_measure = _parse_bool(request.GET.get("include_measure"), default=("include_measure" not in request.GET))
    include_emergency = _parse_bool(request.GET.get("include_emergency"), default=("include_emergency" not in request.GET))
    exclude_skiprule_100 = _parse_bool(request.GET.get("exclude_skiprule_100"), default=("exclude_skiprule_100" not in request.GET))
    tip_mode = _parse_bool(request.GET.get("tip_mode"), default=True)

    return {
        "snap_date": snap_date,
        "processid": processid,
        "areaname": areaname,
        "layerid": layer_values,
        "lineid": lineid,
        "include_measure": include_measure,
        "include_emergency": include_emergency,
        "exclude_skiprule_100": exclude_skiprule_100,
        "tip_mode": tip_mode,
        "inquiry_contact": inquiry_contact,
    }

def _get_prp_common_filters(request):
    prp_snap_date = _normalize_date_input(request.GET.get("prp_snap_date") or "")
    if prp_snap_date is None:
        prp_snap_date = services.get_latest_snap_date()

    return {
        "snap_date": prp_snap_date,
        "include_measure": True,
        "include_emergency": True,
        "exclude_skiprule_100": True,
        "tip_mode": True,
    }

def _build_guide_pages_json():
    active_guide = FactsGuideDocument.objects.filter(is_active=True).order_by("-updated_at", "-id").first()
    if not active_guide:
        return []

    pages_payload = []
    for page in active_guide.pages.all().order_by("page_no"):
        static_path = page.image_path or ""
        if static_path:
            pages_payload.append({
                "page_no": page.page_no,
                "image_url": static_path,
            })

    return pages_payload

def _build_dashboard_api_urls_json():
    return {
        "dashboardDataApi": "/facts/dashboard/data-api/",
        "dashboardPrpOptionsApi": "/facts/dashboard/prp-options-api/",
        "dashboardOverrideSaveApi": "/facts/dashboard/override-save-api/",
        "dashboardOverrideDetailApi": "/facts/dashboard/override-detail-api/",
        "dashboardOverrideMemberSaveApi": "/facts/dashboard/override-member-save-api/",
        "dashboardPlanDetailApi": "/facts/dashboard/plan-detail-api/",
        "dashboardPlanSaveApi": "/facts/dashboard/plan-save-api/",
        "dashboardPlanDeleteApi": "/facts/dashboard/plan-delete-api/",
        "dashboardTipMissingDetailApi": "/facts/dashboard/tip-missing-detail-api/",
        "dashboardTipMissingSaveApi": "/facts/dashboard/tip-missing-save-api/",
        "dashboardTipMissingDeleteApi": "/facts/dashboard/tip-missing-delete-api/",
        "dashboardSimilarEqpApi": "/facts/dashboard/similar-eqp-api/",
        "dashboardBulkUploadApi": "/facts/dashboard/bulk-upload-api/",
        "dashboardFilterOptionsApi": reverse("facts:dashboard_filter_options_api"),
        "prpExportCsvApi": "/facts/dashboard/prp-export-csv/",
        "prpExportCsvAllApi": "/facts/dashboard/prp-export-csv-all/",
    }


def _invalidate_dashboard_graph_cache_for_snap_date(snap_date):
    # deprecated: MetricDaily 전환으로 graph cache 무효화는 더 이상 사용하지 않음
    return


def _set_graph_cache_table_ready(value):
    global _GRAPH_CACHE_TABLE_READY
    _GRAPH_CACHE_TABLE_READY = value


def _graph_cache_table_exists():
    global _GRAPH_CACHE_TABLE_READY
    if _GRAPH_CACHE_TABLE_READY is False:
        return False
    try:
        list(FactsDashboardGraphCache.objects.order_by("id").values_list("id", flat=True)[:1])
        _set_graph_cache_table_ready(True)
        return True
    except (ProgrammingError, OperationalError):
        _set_graph_cache_table_ready(False)
        return False



def _build_summary_from_metric_daily(f, include_row_count=False):
    from facts.models import FactsDashboardMetricDaily

    metric_qs = FactsDashboardMetricDaily.objects.filter(
        snap_date=f["snap_date"],
        lineid=(f.get("lineid") or "").strip(),
        processid=(f.get("processid") or "").strip(),
        include_measure=bool(f.get("include_measure")),
        include_emergency=bool(f.get("include_emergency")),
        exclude_skiprule_100=bool(f.get("exclude_skiprule_100")),
        tip_mode=bool(f.get("tip_mode")),
        metric_type="compat",
    ).exclude(areaname="", layer_key="")

    areaname = (f.get("areaname") or "").strip()
    if areaname:
        metric_qs = metric_qs.filter(areaname=areaname)

    layer_values = [services.normalize_layer_value(x) for x in (f.get("layerid") or []) if services.normalize_layer_value(x)]
    layer_values = sorted(set(layer_values))
    if layer_values:
        if len(layer_values) == 1:
            metric_qs = metric_qs.filter(layer_key=layer_values[0])
        else:
            metric_qs = metric_qs.filter(layer_key__in=layer_values)

    from django.db.models import Sum

    query_t0 = time.perf_counter()
    agg = metric_qs.aggregate(
        total_steps_sum=Sum("total_steps"),
        compatible_steps_sum=Sum("compatible_steps"),
        body_cnt_sum=Sum("body_cnt"),
        cham_cnt_sum=Sum("cham_cnt"),
        single_cnt_sum=Sum("single_cnt"),
    )
    timing_query = time.perf_counter() - query_t0
    row_count = metric_qs.count() if include_row_count else None

    format_t0 = time.perf_counter()
    total_steps = int(agg.get("total_steps_sum") or 0)
    compatible_steps = int(agg.get("compatible_steps_sum") or 0)
    body_cnt = int(agg.get("body_cnt_sum") or 0)
    cham_cnt = int(agg.get("cham_cnt_sum") or 0)
    single_cnt = int(agg.get("single_cnt_sum") or 0)

    if total_steps <= 0:
        logger.warning(
            "[DASHBOARD_SUMMARY] source=metric_daily_aggregate rows=%s total_steps=0 compatible_steps=0 missing_scope=True query=%.4fs format=%.4fs",
            "0" if include_row_count else "skipped",
            timing_query,
            time.perf_counter() - format_t0,
        )
        return {
            "total_steps": 0, "compatible_steps": 0, "compat_rate": 0.0,
            "single_cnt": 0, "body_cnt": 0, "cham_cnt": 0, "unregistered_cnt": 0, "missing_scope": True,
        }, {"summary_query": timing_query, "summary_format": time.perf_counter() - format_t0}

    unregistered_cnt = max(0, total_steps - body_cnt - cham_cnt - single_cnt)
    no_path_cnt = 0
    compat_rate = round((compatible_steps / total_steps) * 100, 1) if total_steps else 0.0
    logger.warning(
        "[DASHBOARD_SUMMARY] source=metric_daily_aggregate rows=%s total_steps=%s compatible_steps=%s query=%.4fs format=%.4fs",
        row_count if include_row_count else "skipped", total_steps, compatible_steps, timing_query, time.perf_counter() - format_t0
    )
    return {
        "total_steps": total_steps,
        "compatible_steps": compatible_steps,
        "compat_rate": compat_rate,
        "single_cnt": single_cnt,
        "body_cnt": body_cnt,
        "cham_cnt": cham_cnt,
        "unregistered_cnt": unregistered_cnt,
        "no_path_cnt": no_path_cnt,
    }, {"summary_query": timing_query, "summary_format": time.perf_counter() - format_t0}


COMPAT_SUMMARY_VERSION = "summary-row-compat-v3-no-path"


def _build_summary_from_prp_rows(f):
    """요약카드는 PRP row 분포 기준으로 집계한다.

    tip_mode=True -> compat_type_tip, tip_mode=False -> compat_type_base
    """
    layer_values = [services.normalize_layer_value(x) for x in (f.get("layerid") or []) if services.normalize_layer_value(x)]
    layer_values = sorted(set(layer_values))
    rows = _extract_prp_rows(
        services.build_step_dataset(
            snap_date=f["snap_date"],
            lineid=(f.get("lineid") or "").strip() or None,
            processid=(f.get("processid") or "").strip() or None,
            areaname=(f.get("areaname") or "").strip() or None,
            layerid=layer_values or None,
            include_measure=bool(f.get("include_measure")),
            include_emergency=bool(f.get("include_emergency")),
            exclude_skiprule_100=bool(f.get("exclude_skiprule_100")),
            tip_mode=bool(f.get("tip_mode")),
            for_prp_table=True,
            as_of_date=f["snap_date"],
        ),
        source="summary_prp_rows",
    )
    compat_key = "compat_type_tip" if bool(f.get("tip_mode")) else "compat_type_base"
    body_cnt = cham_cnt = single_cnt = unregistered_cnt = no_path_cnt = 0
    for row in rows:
        compat = str(row.get(compat_key) or "")
        if compat == "body호환":
            body_cnt += 1
        elif compat == "cham호환":
            cham_cnt += 1
        elif compat == "단독":
            single_cnt += 1
        elif compat == "미등록":
            unregistered_cnt += 1
        elif compat == "가능path없음":
            no_path_cnt += 1

    total_steps = len(rows)
    compatible_steps = body_cnt + cham_cnt
    compat_rate = round((compatible_steps / total_steps) * 100, 1) if total_steps else 0.0
    return {
        "total_steps": total_steps,
        "compatible_steps": compatible_steps,
        "compat_rate": compat_rate,
        "single_cnt": single_cnt,
        "body_cnt": body_cnt,
        "cham_cnt": cham_cnt,
        "unregistered_cnt": unregistered_cnt,
        "no_path_cnt": no_path_cnt,
    }

def _build_summary_and_chart_payload(f):
    cache_key = (
        "facts:summary:"
        f"{COMPAT_SUMMARY_VERSION}|{f['snap_date']}|{f['lineid']}|{f['processid']}|{f['areaname']}|{f['layerid']}|"
        f"{int(bool(f['include_measure']))}|{int(bool(f['include_emergency']))}|"
        f"{int(bool(f['exclude_skiprule_100']))}|{int(bool(f['tip_mode']))}"
    )
    cached = cache.get(cache_key)
    if cached is not None:
        logger.info("[dashboard_metric_daily] DJANGO_CACHE_HIT key=%s", cache_key)
        return cached

    try:
        t0 = time.perf_counter()
        summary = _build_summary_from_prp_rows(f)
        summary_timing = {"summary_query": time.perf_counter() - t0, "summary_format": 0}
    except Exception as exc:
        logger.warning("[DASHBOARD_SUMMARY] fallback_used=True reason=%s", exc)
        summary = {
            "total_steps": 0, "compatible_steps": 0, "compat_rate": 0.0,
            "single_cnt": 0, "body_cnt": 0, "cham_cnt": 0, "unregistered_cnt": 0, "missing_scope": True,
        }
        summary_timing = {"summary_query": 0, "summary_format": 0}
    target_monthly = services.get_kpi_target_value(
        processid=f["processid"],
        target_type="monthly",
        snap_date=f["snap_date"],
        areaname=f["areaname"],
        lineid=f["lineid"],
    )
    combined_series = services.get_dashboard_combined_series(
        snap_date=f["snap_date"],
        processid=f["processid"] or None,
        areaname=f["areaname"] or None,
        layerid=f["layerid"] or None,
        lineid=f["lineid"] or None,
        include_measure=f["include_measure"],
        include_emergency=f["include_emergency"],
        exclude_skiprule_100=f["exclude_skiprule_100"],
        tip_mode=f["tip_mode"],
        target_monthly=target_monthly,
    )

    missing_dates = combined_series.get("missing_dates") or []
    if missing_dates:
        logger.warning("[dashboard_metric_daily] missing_dates=%s snap_date=%s", ",".join(missing_dates), f["snap_date"])

    safe_summary = _assert_json_serializable(_json_safe_payload(summary))
    safe_combined_series = _assert_json_serializable(_json_safe_payload(combined_series))
    result = (safe_summary, target_monthly, safe_combined_series, summary_timing)
    cache.set(cache_key, result, 60)
    return result

def _get_prp_request_filters(request):
    username = _get_request_login_id(request)
    dept = _get_request_department(request)
    permission_defaults = _get_permission_scope_defaults("dashboard", username, dept)

    prp_layer_values = []
    for raw in request.GET.getlist("prp_layer"):
        for part in str(raw or "").split(","):
            norm = services.normalize_layer_value(part.strip())
            if norm and norm not in prp_layer_values:
                prp_layer_values.append(norm)
    if not prp_layer_values:
        single_layer = services.normalize_layer_value(request.GET.get("prp_layer") or "")
        if single_layer:
            prp_layer_values = [single_layer]

    return {
        "prp_snap_date": (request.GET.get("prp_snap_date") or request.GET.get("snap_date") or "").strip(),
        "prp_lineid": (request.GET.get("prp_lineid") or permission_defaults["lineid"] or "").strip(),
        "prp_processid": (request.GET.get("prp_processid") or permission_defaults["processid"] or "").strip(),
        "prp_area": (request.GET.get("prp_area") or "").strip(),
        "prp_layer": prp_layer_values,
        "prp_step": (request.GET.get("prp_step") or "").strip(),
        "prp_descript": (request.GET.get("prp_descript") or "").strip(),
        "prp_recipe": (request.GET.get("prp_recipe") or "").strip(),
        "prp_type": (request.GET.get("prp_type") or "").strip(),
        "prp_body_flag": (request.GET.get("prp_body_flag") or "").strip(),
        "prp_cham_flag": (request.GET.get("prp_cham_flag") or "").strip(),
        "prp_compat_type": (request.GET.get("prp_compat_type") or "").strip(),
        "prp_always": (request.GET.get("prp_always") or "").strip(),
        "prp_major": (request.GET.get("prp_major") or "").strip(),
        "prp_plan": (request.GET.get("prp_plan") or "").strip(),
    }

def _validate_prp_filters(prp_filters):
    prp = prp_filters["prp_processid"]
    if not prp:
        return False, "PRP조건은 필수입니다."

    other_values = [
        prp_filters["prp_lineid"],
        prp_filters["prp_area"],
        ",".join(prp_filters["prp_layer"] or []),
        prp_filters["prp_step"],
        prp_filters["prp_descript"],
        prp_filters["prp_recipe"],
        prp_filters["prp_type"],
        prp_filters["prp_body_flag"],
        prp_filters["prp_cham_flag"],
        prp_filters["prp_compat_type"],
        prp_filters["prp_always"],
        prp_filters["prp_major"],
        prp_filters["prp_plan"],
    ]

    if not any(str(v or "").strip() for v in other_values):
        return False, "PRP조건과 그 외 필터 조건 최소 1개 이상 설정 후 조회하십시오."

    return True, ""

def _resolve_prp_snap_date(prp_filters, fallback_snap_date):
    snap_date = _normalize_date_input(prp_filters.get("prp_snap_date"))
    return snap_date or fallback_snap_date

def _row_matches_prp_filters(row, prp_filters, exclude_keys=None):
    exclude_keys = set(exclude_keys or [])

    if "prp_snap_date" not in exclude_keys:
        prp_snap_date = (prp_filters.get("prp_snap_date") or "").strip()
        if prp_snap_date:
            row_snap = row.get("snap_date")
            row_snap_str = row_snap.strftime("%Y-%m-%d") if hasattr(row_snap, "strftime") else str(row_snap or "")
            if row_snap_str != prp_snap_date:
                return False

    if "prp_lineid" not in exclude_keys and prp_filters.get("prp_lineid"):
        if (row.get("lineid") or "") != prp_filters["prp_lineid"]:
            return False

    if "prp_processid" not in exclude_keys and prp_filters.get("prp_processid"):
        if (row.get("processid") or "") != prp_filters["prp_processid"]:
            return False

    if "prp_area" not in exclude_keys and prp_filters.get("prp_area"):
        if (row.get("areaname") or "") != prp_filters["prp_area"]:
            return False

    if "prp_layer" not in exclude_keys and prp_filters.get("prp_layer"):
        if services.normalize_layer_value(row.get("layerid") or "") not in set(prp_filters["prp_layer"] or []):
            return False

    if "prp_step" not in exclude_keys and prp_filters.get("prp_step"):
        if str(row.get("stepseq") or "") != prp_filters["prp_step"]:
            return False

    if "prp_descript" not in exclude_keys and prp_filters.get("prp_descript"):
        if prp_filters["prp_descript"].upper() not in str(row.get("descript") or "").upper():
            return False

    if "prp_recipe" not in exclude_keys and prp_filters.get("prp_recipe"):
        if prp_filters["prp_recipe"].upper() not in str(row.get("recipeid") or "").upper():
            return False

    if "prp_type" not in exclude_keys and prp_filters.get("prp_type"):
        if (row.get("stepseq_type") or "") != prp_filters["prp_type"]:
            return False

    if "prp_body_flag" not in exclude_keys and prp_filters.get("prp_body_flag"):
        if (row.get("body_compat_flag") or "") != prp_filters["prp_body_flag"]:
            return False

    if "prp_cham_flag" not in exclude_keys and prp_filters.get("prp_cham_flag"):
        if (row.get("cham_compat_flag") or "") != prp_filters["prp_cham_flag"]:
            return False

    if "prp_compat_type" not in exclude_keys and prp_filters.get("prp_compat_type"):
        if (row.get("compat_type") or "") != prp_filters["prp_compat_type"]:
            return False

    if "prp_always" not in exclude_keys and prp_filters.get("prp_always"):
        val = "Y" if row.get("has_always") else "N"
        if val != prp_filters["prp_always"]:
            return False

    if "prp_major" not in exclude_keys and prp_filters.get("prp_major"):
        val = "Y" if row.get("has_major") else "N"
        if val != prp_filters["prp_major"]:
            return False

    if "prp_plan" not in exclude_keys and prp_filters.get("prp_plan"):
        val = "Y" if row.get("has_plan") else "N"
        if val != prp_filters["prp_plan"]:
            return False

    return True

def _build_prp_option_values(rows, prp_filters):
    def filtered_rows(exclude_key):
        return [r for r in rows if _row_matches_prp_filters(r, prp_filters, exclude_keys={exclude_key})]

    line_rows = filtered_rows("prp_lineid")
    process_rows = filtered_rows("prp_processid")
    area_rows = filtered_rows("prp_area")
    layer_rows = filtered_rows("prp_layer")
    step_rows = filtered_rows("prp_step")
    type_rows = filtered_rows("prp_type")

    table_line_options = sorted({(r.get("lineid") or "") for r in line_rows if (r.get("lineid") or "")})
    table_prp_options = sorted({(r.get("processid") or "") for r in process_rows if (r.get("processid") or "")})
    table_area_options = sorted({(r.get("areaname") or "") for r in area_rows if (r.get("areaname") or "")})
    table_layer_options = sorted(
        {services.normalize_layer_value(r.get("layerid") or "") for r in layer_rows if services.normalize_layer_value(r.get("layerid") or "")},
        key=lambda x: [float(x)] if str(x).replace(".", "", 1).isdigit() else [x],
    )
    table_step_options = sorted({(r.get("stepseq") or "") for r in step_rows if (r.get("stepseq") or "")})
    table_type_options = sorted({(r.get("stepseq_type") or "") for r in type_rows if (r.get("stepseq_type") or "")})

    return {
        "table_line_options": table_line_options,
        "table_prp_options": table_prp_options,
        "table_area_options": table_area_options,
        "table_layer_options": table_layer_options,
        "table_step_options": table_step_options,
        "table_type_options": table_type_options,
    }

def _apply_prp_filters(rows, prp_filters):
    return [row for row in rows if _row_matches_prp_filters(row, prp_filters)]

def _get_prp_base_rows(f, prp_filters):
    prp_snap_date = _resolve_prp_snap_date(prp_filters, f["snap_date"])
    prp_layer = prp_filters.get("prp_layer") or []
    dataset_layer = prp_layer if prp_layer else None
    dataset_kwargs = {
        "snap_date": prp_snap_date,
        "lineid": (prp_filters.get("prp_lineid") or "").strip() or None,
        "processid": (prp_filters.get("prp_processid") or "").strip() or None,
        "areaname": (prp_filters.get("prp_area") or "").strip() or None,
        "layerid": dataset_layer,
        "include_measure": f["include_measure"],
        "include_emergency": f["include_emergency"],
        "exclude_skiprule_100": f["exclude_skiprule_100"],
        "tip_mode": f["tip_mode"],
        "for_prp_table": True,
    }
    return services.build_step_dataset(
        **dataset_kwargs,
    ), dataset_kwargs



def _extract_prp_rows(value, *, source="unknown"):
    """build_step_dataset 계열 반환값에서 PRP row(list[dict])를 안전 추출한다."""
    rows = None

    if isinstance(value, list):
        if all(isinstance(item, dict) for item in value):
            rows = value
        elif value and isinstance(value[0], list) and all(isinstance(item, dict) for item in value[0]):
            rows = value[0]
    elif isinstance(value, tuple):
        if value and isinstance(value[0], list) and all(isinstance(item, dict) for item in value[0]):
            rows = value[0]
    elif isinstance(value, dict):
        candidate = value.get("rows")
        if isinstance(candidate, list) and all(isinstance(item, dict) for item in candidate):
            rows = candidate

    if rows is None:
        logger.warning("[PRP_EXPORT] invalid row payload source=%s type=%s sample=%s", source, type(value).__name__, repr(value)[:300])
        return []

    invalid_count = sum(1 for item in rows if not isinstance(item, dict))
    if invalid_count:
        logger.warning("[PRP_EXPORT] non-dict rows ignored source=%s total=%s invalid=%s", source, len(rows), invalid_count)

    return [item for item in rows if isinstance(item, dict)]
def _build_override_detail_rows(snap_date, lineid, processid, stepseq):
    step_rows = services.build_step_dataset(
        snap_date=snap_date,
        processid=processid,
        lineid=lineid,
        include_measure=True,
        include_emergency=True,
        exclude_skiprule_100=False,
        tip_mode=False,
        for_prp_table=True,
    )

    target_row = next(
        (
            x for x in step_rows
            if x["processid"] == processid
            and x["stepseq"] == stepseq
            and (x.get("lineid") or "") == (lineid or "")
        ),
        None,
    )
    if not target_row:
        return []

    result = []
    for item in target_row.get("override_target_list", []):
        source_types = item.get("source_types", [])
        source_display_parts = []

        if "SOURCE_PATH" in source_types:
            source_display_parts.append("TIP등록 Path")
        if "TIP_MISSING" in source_types:
            source_display_parts.append("TIP미등록 호환Path")

        result.append({
            "member_key": item.get("member_key", ""),
            "eqp_body_name": item.get("eqp_body_name", ""),
            "eqp_cham_name": item.get("eqp_cham_name", ""),
            "member_display": item.get("display_name", ""),
            "source_display": " / ".join(source_display_parts),
            "current_flag": "Y" if item.get("has_always") else "N",
            "current_major_flag": "Y" if item.get("has_major") else "N",
            "source_types": source_types,
            "path_refs": item.get("path_refs", []),
        })

    return result

@login_required
@ensure_csrf_cookie
def dashboard_view(request):
    _ensure_browser_close_session(request)
    permission_response = _check_page_permission(request, "dashboard", ignore_blank_scope=True)
    if permission_response is not None:
        return permission_response

    _record_access_history(request, 'dashboard')
    f = _get_dashboard_common_filters(request)
    filters = services.get_dashboard_filter_options_from_option_cache(
        snap_date=f["snap_date"],
        lineid=f["lineid"],
        processid=f["processid"],
        areaname=f["areaname"],
    )

    pre_query_state = not (f["lineid"] and f["processid"])

    context = {
        "page_title": "FACTS Dashboard",
        "snap_date": f["snap_date"],
        "filters": filters,
        "selected_lineid": f["lineid"],
        "selected_processid": f["processid"],
        "selected_areaname": f["areaname"],
        "selected_layerids": f["layerid"] or [],
        "include_measure": f["include_measure"],
        "include_emergency": f["include_emergency"],
        "exclude_skiprule_100": f["exclude_skiprule_100"],
        "tip_mode": f["tip_mode"],
        "summary": {
            "compat_rate": None if pre_query_state else 0.0,
            "total_steps": None if pre_query_state else 0,
            "single_cnt": None if pre_query_state else 0,
            "body_cnt": None if pre_query_state else 0,
            "cham_cnt": None if pre_query_state else 0,
        },
        "rows": [],
        "combined_series_json": {
            "labels": [],
            "total_values": [],
            "body_values": [],
            "cham_values": [],
            "target_values": [],
        },
        "guide_pages_json": _build_guide_pages_json(),
        "dashboard_api_urls_json": _build_dashboard_api_urls_json(),
        "target_monthly": None,
        "pre_query_state": pre_query_state,
        "inquiry_contact": f["inquiry_contact"],
        "eval_stages": FactsEvalStageMaster.objects.filter(is_active=True).order_by("sort_order", "stage_code"),
        "table_line_options": [],
        "table_prp_options": [],
    }
    return render(request, "facts/dashboard.html", context)

@require_GET
@login_required
def dashboard_data_api(request):
    try:
        t0 = time.perf_counter()
        combined_series = {}
        summary = {}
        target_monthly = None
        timing_marks = {}
        _ensure_browser_close_session(request)
        permission_response = _check_page_permission(request, "dashboard", ignore_blank_scope=True)
        if permission_response is not None:
            return permission_response

        f = _get_dashboard_common_filters(request)
        scope_response = _check_page_permission(request, "dashboard", lineid=f["lineid"], processid=f["processid"], popup=True)
        if scope_response is not None:
            return scope_response
        prp_f = _get_prp_common_filters(request)
        summary_only = _parse_bool(request.GET.get("summary_only"), default=False)
        prp_only = _parse_bool(request.GET.get("prp_only"), default=False)

        payload = {"ok": True, "summary": {}, "target_monthly": None, "pre_query_state": False, "combined_series": {"labels": [], "total_values": [], "body_values": [], "cham_values": [], "target_values": []}, "rows": [], "table_area_options": [], "table_layer_options": [], "table_step_options": [], "table_type_options": [], "message": ""}

        debug_timing = str(request.GET.get("debug_timing") or "").strip() == "1"
        debug_tip_missing = str(request.GET.get("debug_tip_missing") or "").strip() == "1"
        debug_stepseq = (request.GET.get("debug_stepseq") or "").strip()
        debug_recipeid = (request.GET.get("debug_recipeid") or "").strip()
        request_mode = "unknown"
        prp_stats = None
        f["debug_timing"] = debug_timing
        timing_marks["request_parse"] = time.perf_counter() - t0

        if not prp_only:
            request_mode = "pre_query" if not (f["lineid"] and f["processid"]) else "chart"
            if not (f["lineid"] and f["processid"]):
                payload["message"] = "LINE과 PRP를 모두 선택한 뒤 조회하세요."
                payload["pre_query_state"] = True
                payload["requires_line_prp"] = True
            else:
                t_summary = time.perf_counter()
                summary, target_monthly, combined_series, summary_timing = _build_summary_and_chart_payload(f)
                timing_marks["summary_build"] = time.perf_counter() - t_summary
                timing_marks["summary_query"] = float(summary_timing.get("summary_query") or 0)
                timing_marks["summary_format"] = float(summary_timing.get("summary_format") or 0)
                timing_marks["summary_total"] = timing_marks["summary_query"] + timing_marks["summary_format"]
                payload["summary"] = summary
                payload["target_monthly"] = target_monthly
                payload["combined_series"] = combined_series
                logger.warning("[DASHBOARD_METRIC] rows_read=%s missing_dates_count=%s", combined_series.get("rows_read", 0), len(combined_series.get("missing_dates") or []))

        if summary_only:
            timing_marks["total"] = time.perf_counter() - t0
            _emit_dashboard_console_logs(f, timing_marks, combined_series, request_mode=request_mode)
            return JsonResponse(payload)

        prp_filters = _get_prp_request_filters(request)
        prp_scope_response = _check_page_permission(request, "dashboard", lineid=(prp_filters.get("prp_lineid") or "").strip(), processid=(prp_filters.get("prp_processid") or "").strip(), popup=True)
        if prp_scope_response is not None:
            return prp_scope_response
        has_any_prp_param = any(str(request.GET.get(k) or "").strip() for k in ["prp_lineid", "prp_processid", "prp_area", "prp_layer", "prp_step", "prp_descript", "prp_recipe", "prp_type", "prp_body_flag", "prp_cham_flag", "prp_compat_type", "prp_always", "prp_major", "prp_plan"])
        if not has_any_prp_param:
            timing_marks["total"] = time.perf_counter() - t0
            _emit_dashboard_console_logs(f, timing_marks, combined_series, request_mode=request_mode)
            return JsonResponse(payload)
        request_mode = "prp_table"
        t_prp_rows = time.perf_counter()
        t_dataset = time.perf_counter()
        prp_base_rows_raw, prp_dataset_kwargs = _get_prp_base_rows(prp_f, prp_filters)
        prp_base_rows = _extract_prp_rows(prp_base_rows_raw, source="dashboard_data_api")
        timing_marks["build_step_dataset"] = time.perf_counter() - t_dataset
        payload.update(services.get_prp_filter_options_from_cache(prp_filters=prp_filters, fallback_snap_date=prp_f["snap_date"]))
        timing_marks["prp_rows_build"] = time.perf_counter() - t_prp_rows
        is_valid, msg = _validate_prp_filters(prp_filters)
        if not is_valid:
            payload["message"] = msg
            return JsonResponse(payload)
        t_filter = time.perf_counter()
        filtered_rows = _apply_prp_filters(prp_base_rows, prp_filters)
        if payload.get("summary") is not None:
            tip_counts = {"미등록": 0, "가능path없음": 0, "body호환": 0, "cham호환": 0, "단독": 0}
            for _r in filtered_rows:
                key = str(_r.get("compat_type_tip") or "")
                if key in tip_counts:
                    tip_counts[key] += 1
            payload["summary"]["total_steps"] = len(filtered_rows)
            payload["summary"]["body_cnt"] = tip_counts["body호환"]
            payload["summary"]["cham_cnt"] = tip_counts["cham호환"]
            payload["summary"]["single_cnt"] = tip_counts["단독"]
            payload["summary"]["unregistered_cnt"] = tip_counts["미등록"]
            payload["summary"]["no_path_cnt"] = tip_counts["가능path없음"]
            compatible_steps = tip_counts["body호환"] + tip_counts["cham호환"]
            payload["summary"]["compatible_steps"] = compatible_steps
            total_steps = len(filtered_rows)
            payload["summary"]["compat_rate"] = round((compatible_steps / total_steps) * 100, 1) if total_steps else 0.0
        timing_marks["prp_filter_apply"] = time.perf_counter() - t_filter
        t_serialize = time.perf_counter()
        if isinstance(combined_series, dict):
            timing_marks["series_build"] = combined_series.get("timing_series_build", 0)
            timing_marks["metric_query"] = combined_series.get("timing_metric_query", 0)
        else:
            timing_marks["series_build"] = 0
            timing_marks["metric_query"] = 0
        for row in filtered_rows:
            override_items = row.get("override_target_list", []) or []
            row["override_editable"] = any("TIP_MISSING" in (item.get("source_types") or []) for item in override_items)
            row["override_disabled_reason"] = "" if row["override_editable"] else "TIP등록된 설비는 상시, 주요 설정으로 변경이 불가합니다."
        timing_marks["prp_serialize"] = time.perf_counter() - t_serialize
        prp_stats = {"rows": len(prp_base_rows), "filtered_rows": len(filtered_rows), "page_rows": len(filtered_rows)}
        payload["rows"] = filtered_rows
        debug_prp_table = str(request.GET.get("debug_prp_table") or "").strip() == "1"
        t_json = time.perf_counter()
        response = JsonResponse(payload)
        timing_marks["json_response_build"] = time.perf_counter() - t_json
        timing_marks["total"] = time.perf_counter() - t0
        _emit_dashboard_console_logs(f, timing_marks, combined_series, request_mode=request_mode, prp_stats=prp_stats)
        tip_rows = [r for r in filtered_rows if str(r.get("tip_missing_flag") or "").strip().upper() == "Y"]
        if tip_rows:
            logger.warning("[DASHBOARD_PRP_TIP] tip_missing_rows=%s filtered_rows=%s", len(tip_rows), len(filtered_rows))
        if debug_prp_table:
            debug_focus_step = debug_stepseq or "SD000040"
            focus_row = next((r for r in filtered_rows if str(r.get("stepseq") or "").strip() == debug_focus_step), None)
            sample = [{"stepseq": r.get("stepseq"), "recipeid": r.get("recipeid"), "tip_missing_body": r.get("tip_missing_body"), "tip_missing_cham": r.get("tip_missing_cham")} for r in tip_rows[:20]]
            lines = [
                "source=dashboard_data_api",
                f"request_path={request.path}",
                f"query_string={request.META.get('QUERY_STRING', '')}",
                f"debug_focus_step={debug_focus_step}",
                f"total_rows={len(prp_base_rows)}",
                f"filtered_rows={len(filtered_rows)}",
                f"page_rows={len(filtered_rows)}",
                f"tip_missing_flag_y_count={len(tip_rows)}",
                f"tip_missing_sample_20={sample}",
                f"{debug_focus_step}_included={'Y' if focus_row else 'N'}",
            ]
            dataset_debug_info = services.get_build_step_dataset_debug_info(**prp_dataset_kwargs)
            cache_hit = cache.get(dataset_debug_info["cache_key"]) is not None
            lines.extend([
                f"build_step_dataset_args={dataset_debug_info['cache_key_parts']}",
                f"build_step_dataset_cache_key={dataset_debug_info['cache_key']}",
                f"build_step_dataset_cache_hit={cache_hit}",
                f"request_prp_lineid={prp_filters.get('prp_lineid')}",
                f"request_prp_processid={prp_filters.get('prp_processid')}",
                f"request_prp_area={prp_filters.get('prp_area')}",
                f"request_prp_layer={prp_filters.get('prp_layer')}",
                f"dataset_arg_lineid={prp_dataset_kwargs.get('lineid')}",
                f"dataset_arg_processid={prp_dataset_kwargs.get('processid')}",
                f"dataset_arg_areaname={prp_dataset_kwargs.get('areaname')}",
                f"dataset_arg_layerid={prp_dataset_kwargs.get('layerid')}",
            ])

            warning_pairs = [
                ("prp_lineid", "lineid"),
                ("prp_processid", "processid"),
                ("prp_area", "areaname"),
                ("prp_layer", "layerid"),
            ]
            for req_key, dataset_key in warning_pairs:
                req_value = prp_filters.get(req_key)
                dataset_value = prp_dataset_kwargs.get(dataset_key)
                req_exists = bool(req_value)
                dataset_missing = dataset_value is None or (isinstance(dataset_value, list) and not dataset_value)
                if req_exists and dataset_missing:
                    warning_msg = f"[PRP_TABLE_DEBUG] WARNING {req_key} exists but build_step_dataset {dataset_key} is None"
                    print(warning_msg)
                    lines.append(warning_msg)
            before_row = next((r for r in prp_base_rows if str(r.get("stepseq") or "").strip() == debug_focus_step), None)
            after_row = next((r for r in filtered_rows if str(r.get("stepseq") or "").strip() == debug_focus_step), None)
            lines.extend([
                f"tip_missing_summary_debug_value={before_row.get('tip_missing_body') if before_row else ''}|{before_row.get('tip_missing_cham') if before_row else ''}",
                f"plan_summary_debug_value={before_row.get('plan_body_names') if before_row else ''}|{before_row.get('plan_cham_names') if before_row else ''}",
                f"override_debug_value={before_row.get('final_always_emergency') if before_row else ''}|{before_row.get('final_major_minor') if before_row else ''}",
            ])
            for label, row_obj in [("before_filter", before_row), ("after_filter", after_row), ("response", focus_row)]:
                if row_obj:
                    lines.extend([
                        f"{label}.{debug_focus_step}.tip_missing_flag={row_obj.get('tip_missing_flag')}",
                        f"{label}.{debug_focus_step}.tip_missing_always={row_obj.get('tip_missing_always')}",
                        f"{label}.{debug_focus_step}.tip_missing_major={row_obj.get('tip_missing_major')}",
                        f"{label}.{debug_focus_step}.tip_missing_body={row_obj.get('tip_missing_body')}",
                        f"{label}.{debug_focus_step}.tip_missing_cham={row_obj.get('tip_missing_cham')}",
                        f"{label}.{debug_focus_step}.eqpgroup_html={row_obj.get('eqpgroup_html')}",
                        f"{label}.{debug_focus_step}.cham_html={row_obj.get('cham_html')}",
                    ])
            if focus_row:
                lines.extend([
                    f"{debug_focus_step}.tip_missing_flag={focus_row.get('tip_missing_flag')}",
                    f"{debug_focus_step}.tip_missing_always={focus_row.get('tip_missing_always')}",
                    f"{debug_focus_step}.tip_missing_major={focus_row.get('tip_missing_major')}",
                    f"{debug_focus_step}.tip_missing_body={focus_row.get('tip_missing_body')}",
                    f"{debug_focus_step}.tip_missing_cham={focus_row.get('tip_missing_cham')}",
                    f"{debug_focus_step}.eqpgroup_html={focus_row.get('eqpgroup_html')}",
                    f"{debug_focus_step}.cham_html={focus_row.get('cham_html')}",
                ])
            file_path = try_save_feedback_log('prp_table_response_debug', "\n".join(lines), 'PRP_TABLE_RESPONSE_DEBUG')
            print(f"[PRP_TABLE_RESPONSE_DEBUG] path={file_path}")
        if debug_timing or debug_tip_missing:
            selected_row = None
            if debug_stepseq:
                for rr in filtered_rows:
                    same_step = str(rr.get("stepseq") or "").strip() == debug_stepseq
                    same_recipe = (not debug_recipeid) or (str(rr.get("recipeid") or "").strip() == debug_recipeid)
                    if same_step and same_recipe:
                        selected_row = rr
                        break
            metric_daily_keys = ['needed_date_min', 'needed_date_max', 'needed_date_count', 'metric_date_min', 'metric_date_max', 'rows_read', 'missing_dates_count', 'ignored_out_of_range_dates_count', 'missing_dates_head', 'missing_dates_tail']
            metric_daily_info = {k: combined_series.get(k) for k in metric_daily_keys} if isinstance(combined_series, dict) else {}
            dbg = [
                f"request_path={request.path}",
                f"query_string={request.META.get('QUERY_STRING','')}",
                f"user={getattr(request.user,'username','')}",
                f"filters={f}",
                f"timing={timing_marks}",
                f"metric_daily={metric_daily_info}",
                f"build_step_dataset_called_in_graph=False",
                f"FactsDashboardGraphCache_used=False",
                f"response_payload_size={len(response.content)}",
            ]
            if selected_row:
                dbg.append(f"debug_stepseq={debug_stepseq}")
                dbg.append(f"debug_recipeid={debug_recipeid}")
                tip_missing_values = {k:selected_row.get(k) for k in ['tip_missing_flag','tip_missing_always','tip_missing_major','tip_missing_body','tip_missing_cham']}
                dbg.append(f"tip_missing_values={tip_missing_values}")
                dbg.append(f"eqpgroup_html_has_manual={'manual-path' in str(selected_row.get('eqpgroup_html') or '')}")
                dbg.append(f"cham_html_has_manual={'manual-path' in str(selected_row.get('cham_html') or '')}")
                dbg.append(f"lineid={selected_row.get('lineid')}")
                dbg.append(f"processid={selected_row.get('processid')}")
                dbg.append(f"stepseq={selected_row.get('stepseq')}")
                dbg.append(f"recipeid={selected_row.get('recipeid')}")
                dbg.append(f"eqpgroup={selected_row.get('eqpgroup')}")
                dbg.append(f"eqpgroup_html={selected_row.get('eqpgroup_html')}")
                dbg.append(f"cham_display={selected_row.get('cham_display')}")
                dbg.append(f"cham_html={selected_row.get('cham_html')}")
                dbg.append(f"override_target_list_count={len(selected_row.get('override_target_list') or [])}")
            try_save_feedback_log('dashboard_timing', "\n".join(dbg), 'DASHBOARD_TIMING')
            if debug_tip_missing:
                try_save_feedback_log('prp_table_row_debug', "\n".join(dbg), 'PRP_TABLE_ROW_DEBUG')
        return response
    except Exception:
        logger.exception("[DASHBOARD_DATA_API_ERROR]")
        return JsonResponse({"ok": False, "message": "대시보드 데이터 조회 중 오류가 발생했습니다."}, status=500)
