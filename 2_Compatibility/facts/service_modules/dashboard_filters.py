from .common import (
    FactsDashboardConfig,
    FactsFilterCache,
    FactsFilterOptionCache,
    FactsWipSource,
    Max,
    json,
    re,
)

def get_dashboard_config():
    obj = FactsDashboardConfig.objects.order_by("id").first()
    if obj:
        return obj
    return {
        "default_prp": "P1SD",
        "inquiry_contact": "minuk12.choi",
    }

def get_latest_snap_date():
    return FactsWipSource.objects.aggregate(max_date=Max("snap_date"))["max_date"]

def get_filter_options(snap_date=None):
    qs = FactsWipSource.objects.all()
    if snap_date:
        qs = qs.filter(snap_date=snap_date)

    areas = list(
        qs.exclude(areaname__isnull=True)
        .exclude(areaname="")
        .values_list("areaname", flat=True)
        .distinct()
    )
    areas = sorted(areas, key=lambda x: str(x))

    raw_layers = list(
        qs.exclude(layerid__isnull=True)
        .exclude(layerid="")
        .values_list("layerid", flat=True)
        .distinct()
    )
    norm_layers = sorted(
        {normalize_layer_value(x) for x in raw_layers if normalize_layer_value(x)},
        key=_natural_sort_key,
    )

    processes = list(
        qs.exclude(processid__isnull=True)
        .exclude(processid="")
        .values_list("processid", flat=True)
        .distinct()
        .order_by("processid")
    )

    lineids = list(
        qs.exclude(lineid__isnull=True)
        .exclude(lineid="")
        .values_list("lineid", flat=True)
        .distinct()
        .order_by("lineid")
    )

    return {
        "areas": areas,
        "layers": norm_layers,
        "processes": processes,
        "lineids": list(lineids),
    }

def get_filter_options_from_cache(
    snap_date=None,
    lineid=None,
    processid=None,
    areaname=None,
    stepseq_type=None,
    **kwargs,
):
    """
    KPI/대시보드/기타 페이지에서 공통으로 쓰는 필터 선택지 조회.
    현재는 FactsFilterCache 기준으로 line/prp/area/layer/step/step_type/skiprule 값을 반환한다.
    """

    from ..models import FactsFilterCache

    qs = FactsFilterCache.objects.all()

    if snap_date:
        qs = qs.filter(snap_date=snap_date)
    if lineid:
        qs = qs.filter(lineid=lineid)
    if processid:
        qs = qs.filter(processid=processid)
    if areaname:
        qs = qs.filter(areaname=areaname)
    if stepseq_type:
        qs = qs.filter(stepseq_type=stepseq_type)

    def _values(field_name):
        return list(
            qs.exclude(**{f"{field_name}__isnull": True})
              .exclude(**{field_name: ""})
              .values_list(field_name, flat=True)
              .distinct()
              .order_by(field_name)
        )

    return {
        "line_options": _values("lineid"),
        "prp_options": _values("processid"),
        "area_options": _values("areaname"),
        "layer_options": _values("layerid"),
        "step_options": _values("stepseq"),
        "step_type_options": _values("stepseq_type"),
    
    }


def get_filter_options_from_option_cache(
    snap_date=None,
    lineid=None,
    processid=None,
    areaname=None,
    stepseq_type=None,
    **kwargs,
):
    # 공용 호출 호환용 alias (PREVENT/HISTORY 등에서 사용)
    return get_filter_options_from_cache(
        snap_date=snap_date,
        lineid=lineid,
        processid=processid,
        areaname=areaname,
        stepseq_type=stepseq_type,
        **kwargs,
    )

def get_dashboard_filter_options_from_cache(lineid="", processid="", areaname="", layer_values=None, snap_date=None):
    snap_date = snap_date or get_latest_snap_date()
    if not snap_date:
        return {
            "lineids": [],
            "processes": [],
            "areas": [],
            "layers": [],
        }

    base_qs = FactsFilterCache.objects.filter(snap_date=snap_date)

    normalized_layers = [normalize_layer_value(x) for x in (layer_values or []) if normalize_layer_value(x)]

    line_qs = base_qs
    if processid:
        line_qs = line_qs.filter(processid=processid)
    if areaname:
        line_qs = line_qs.filter(areaname=areaname)
    if normalized_layers:
        line_qs = line_qs.filter(layerid__in=normalized_layers)

    process_qs = base_qs
    if lineid:
        process_qs = process_qs.filter(lineid=lineid)
    if areaname:
        process_qs = process_qs.filter(areaname=areaname)
    if normalized_layers:
        process_qs = process_qs.filter(layerid__in=normalized_layers)

    area_qs = base_qs
    if lineid:
        area_qs = area_qs.filter(lineid=lineid)
    if processid:
        area_qs = area_qs.filter(processid=processid)
    if normalized_layers:
        area_qs = area_qs.filter(layerid__in=normalized_layers)

    layer_qs = base_qs
    if lineid:
        layer_qs = layer_qs.filter(lineid=lineid)
    if processid:
        layer_qs = layer_qs.filter(processid=processid)
    if areaname:
        layer_qs = layer_qs.filter(areaname=areaname)

    return {
        "lineids": sorted({
            (x or "").strip()
            for x in line_qs.values_list("lineid", flat=True)
            if (x or "").strip()
        }),
        "processes": sorted({
            (x or "").strip()
            for x in process_qs.values_list("processid", flat=True)
            if (x or "").strip()
        }),
        "areas": sorted({
            (x or "").strip()
            for x in area_qs.values_list("areaname", flat=True)
            if (x or "").strip()
        }),
        "layers": sorted(
            {
                normalize_layer_value(x)
                for x in layer_qs.values_list("layerid", flat=True)
                if normalize_layer_value(x)
            },
            key=_natural_sort_key,
        ),
    }

def _apply_prp_cache_filters(qs, prp_filters, exclude_keys=None):
    exclude_keys = set(exclude_keys or [])

    prp_snap_date = (prp_filters.get("prp_snap_date") or "").strip()
    if "prp_snap_date" not in exclude_keys and prp_snap_date:
        qs = qs.filter(snap_date=prp_snap_date)

    if "prp_lineid" not in exclude_keys and prp_filters.get("prp_lineid"):
        qs = qs.filter(lineid=prp_filters["prp_lineid"])

    if "prp_processid" not in exclude_keys and prp_filters.get("prp_processid"):
        qs = qs.filter(processid=prp_filters["prp_processid"])

    if "prp_area" not in exclude_keys and prp_filters.get("prp_area"):
        qs = qs.filter(areaname=prp_filters["prp_area"])

    if "prp_layer" not in exclude_keys and prp_filters.get("prp_layer"):
        layer_values = prp_filters.get("prp_layer") or []
        if isinstance(layer_values, str):
            layer_values = [layer_values]
        layer_values = [normalize_layer_value(x) for x in layer_values if normalize_layer_value(x)]
        if layer_values:
            qs = qs.filter(layerid__in=layer_values)

    if "prp_step" not in exclude_keys and prp_filters.get("prp_step"):
        qs = qs.filter(stepseq=prp_filters["prp_step"])

    if "prp_descript" not in exclude_keys and prp_filters.get("prp_descript"):
        qs = qs.filter(descript__icontains=prp_filters["prp_descript"])

    if "prp_recipe" not in exclude_keys and prp_filters.get("prp_recipe"):
        qs = qs.filter(recipeid__icontains=prp_filters["prp_recipe"])

    if "prp_type" not in exclude_keys and prp_filters.get("prp_type"):
        qs = qs.filter(stepseq_type=prp_filters["prp_type"])

    if "prp_body_flag" not in exclude_keys and prp_filters.get("prp_body_flag"):
        qs = qs.filter(body_flag=prp_filters["prp_body_flag"])

    if "prp_cham_flag" not in exclude_keys and prp_filters.get("prp_cham_flag"):
        qs = qs.filter(cham_flag=prp_filters["prp_cham_flag"])

    if "prp_compat_type" not in exclude_keys and prp_filters.get("prp_compat_type"):
        qs = qs.filter(compat_type=prp_filters["prp_compat_type"])

    if "prp_always" not in exclude_keys and prp_filters.get("prp_always"):
        qs = qs.filter(always_flag=prp_filters["prp_always"])

    if "prp_major" not in exclude_keys and prp_filters.get("prp_major"):
        qs = qs.filter(major_flag=prp_filters["prp_major"])

    if "prp_plan" not in exclude_keys and prp_filters.get("prp_plan"):
        qs = qs.filter(plan_flag=prp_filters["prp_plan"])

    return qs

def get_prp_filter_options_from_cache(prp_filters, fallback_snap_date=None):
    snap_date = (prp_filters.get("prp_snap_date") or "").strip() or (
        fallback_snap_date.strftime("%Y-%m-%d") if hasattr(fallback_snap_date, "strftime") else str(fallback_snap_date or "")
    )

    if not snap_date:
        return {
            "table_line_options": [],
            "table_prp_options": [],
            "table_area_options": [],
            "table_layer_options": [],
            "table_step_options": [],
            "table_descript_options": [],
            "table_recipe_options": [],
            "table_type_options": [],
            "table_body_options": [],
            "table_cham_options": [],
            "table_compat_options": [],
            "table_always_options": [],
            "table_major_options": [],
            "table_plan_options": [],
        }

    base_qs = FactsFilterCache.objects.filter(snap_date=snap_date)

    line_qs = _apply_prp_cache_filters(base_qs, prp_filters, exclude_keys={"prp_lineid"})
    process_qs = _apply_prp_cache_filters(base_qs, prp_filters, exclude_keys={"prp_processid"})
    area_qs = _apply_prp_cache_filters(base_qs, prp_filters, exclude_keys={"prp_area"})
    layer_qs = _apply_prp_cache_filters(base_qs, prp_filters, exclude_keys={"prp_layer"})
    step_qs = _apply_prp_cache_filters(base_qs, prp_filters, exclude_keys={"prp_step"})
    descript_qs = _apply_prp_cache_filters(base_qs, prp_filters, exclude_keys={"prp_descript"})
    recipe_qs = _apply_prp_cache_filters(base_qs, prp_filters, exclude_keys={"prp_recipe"})
    type_qs = _apply_prp_cache_filters(base_qs, prp_filters, exclude_keys={"prp_type"})
    body_qs = _apply_prp_cache_filters(base_qs, prp_filters, exclude_keys={"prp_body_flag"})
    cham_qs = _apply_prp_cache_filters(base_qs, prp_filters, exclude_keys={"prp_cham_flag"})
    compat_qs = _apply_prp_cache_filters(base_qs, prp_filters, exclude_keys={"prp_compat_type"})
    always_qs = _apply_prp_cache_filters(base_qs, prp_filters, exclude_keys={"prp_always"})
    major_qs = _apply_prp_cache_filters(base_qs, prp_filters, exclude_keys={"prp_major"})
    plan_qs = _apply_prp_cache_filters(base_qs, prp_filters, exclude_keys={"prp_plan"})

    return {
        "table_line_options": sorted({
            (x or "").strip()
            for x in line_qs.values_list("lineid", flat=True)
            if (x or "").strip()
        }),
        "table_prp_options": sorted({
            (x or "").strip()
            for x in process_qs.values_list("processid", flat=True)
            if (x or "").strip()
        }),
        "table_area_options": sorted({
            (x or "").strip()
            for x in area_qs.values_list("areaname", flat=True)
            if (x or "").strip()
        }),
        "table_layer_options": sorted(
            {
                normalize_layer_value(x)
                for x in layer_qs.values_list("layerid", flat=True)
                if normalize_layer_value(x)
            },
            key=_natural_sort_key,
        ),
        "table_step_options": sorted({
            (x or "").strip()
            for x in step_qs.values_list("stepseq", flat=True)
            if (x or "").strip()
        }),
        "table_descript_options": sorted({
            (x or "").strip()
            for x in descript_qs.values_list("descript", flat=True)
            if (x or "").strip()
        }),
        "table_recipe_options": sorted({
            (x or "").strip().upper()
            for x in recipe_qs.values_list("recipeid", flat=True)
            if (x or "").strip()
        }),
        "table_type_options": sorted({
            (x or "").strip()
            for x in type_qs.values_list("stepseq_type", flat=True)
            if (x or "").strip()
        }),
        "table_body_options": sorted({(x or "").strip() for x in body_qs.values_list("body_flag", flat=True) if (x or "").strip()}),
        "table_cham_options": sorted({(x or "").strip() for x in cham_qs.values_list("cham_flag", flat=True) if (x or "").strip()}),
        "table_compat_options": sorted({(x or "").strip() for x in compat_qs.values_list("compat_type", flat=True) if (x or "").strip()}),
        "table_always_options": sorted({(x or "").strip() for x in always_qs.values_list("always_flag", flat=True) if (x or "").strip()}),
        "table_major_options": sorted({(x or "").strip() for x in major_qs.values_list("major_flag", flat=True) if (x or "").strip()}),
        "table_plan_options": sorted({(x or "").strip() for x in plan_qs.values_list("plan_flag", flat=True) if (x or "").strip()}),
    }

def get_dashboard_filter_options_from_option_cache(lineid="", processid="", areaname="", layer_values=None, snap_date=None):
    snap_date = snap_date or get_latest_snap_date()
    normalized_layers = [normalize_layer_value(x) for x in (layer_values or []) if normalize_layer_value(x)]
    layer_cache_value = normalized_layers[0] if len(normalized_layers) == 1 else ""
    row = FactsFilterOptionCache.objects.filter(
        snap_date=snap_date,
        cache_type="dashboard",
        lineid=lineid or "",
        processid=processid or "",
        areaname=areaname or "",
        layerid=layer_cache_value,
    ).first()

    if not row:
        return get_dashboard_filter_options_from_cache(
            lineid=lineid,
            processid=processid,
            areaname=areaname,
            layer_values=normalized_layers,
            snap_date=snap_date,
        )

    return {
        "lineids": json.loads(row.line_options_json or "[]"),
        "processes": json.loads(row.prp_options_json or "[]"),
        "areas": json.loads(row.area_options_json or "[]"),
        "layers": json.loads(row.layer_options_json or "[]"),
    }


def get_line_prp_options(snap_date=None, lineid="", processid=""):
    snap_date = snap_date or get_latest_snap_date()
    if not snap_date:
        return {"line_options": [], "prp_options": []}

    lineid = (lineid or "").strip()
    processid = (processid or "").strip()
    base_qs = FactsFilterOptionCache.objects.filter(snap_date=snap_date)

    line_qs = base_qs
    if processid:
        line_qs = line_qs.filter(processid=processid)

    prp_qs = base_qs
    if lineid:
        prp_qs = prp_qs.filter(lineid=lineid)

    line_options = sorted({(x or "").strip() for x in line_qs.values_list("lineid", flat=True) if (x or "").strip()})
    prp_options = sorted({(x or "").strip() for x in prp_qs.values_list("processid", flat=True) if (x or "").strip()})

    if not line_options or not prp_options:
        wip_qs = FactsWipSource.objects.filter(snap_date=snap_date)
        if processid:
            wip_line_qs = wip_qs.filter(processid=processid)
        else:
            wip_line_qs = wip_qs
        if lineid:
            wip_prp_qs = wip_qs.filter(lineid=lineid)
        else:
            wip_prp_qs = wip_qs
        if not line_options:
            line_options = sorted({(x or "").strip() for x in wip_line_qs.values_list("lineid", flat=True) if (x or "").strip()})
        if not prp_options:
            prp_options = sorted({(x or "").strip() for x in wip_prp_qs.values_list("processid", flat=True) if (x or "").strip()})

    return {"line_options": line_options, "prp_options": prp_options}

def get_prp_filter_options_from_option_cache(prp_filters, fallback_snap_date=None):
    snap_date = (prp_filters.get("prp_snap_date") or "").strip() or (
        fallback_snap_date.strftime("%Y-%m-%d") if hasattr(fallback_snap_date, "strftime") else str(fallback_snap_date or "")
    )

    layer_values = prp_filters.get("prp_layer") or []
    if isinstance(layer_values, str):
        layer_values = [layer_values]
    normalized_layers = [normalize_layer_value(x) for x in layer_values if normalize_layer_value(x)]
    layer_cache_value = normalized_layers[0] if len(normalized_layers) == 1 else ""

    row = FactsFilterOptionCache.objects.filter(
        snap_date=snap_date,
        cache_type="prp_table",
        lineid=(prp_filters.get("prp_lineid") or "").strip(),
        processid=(prp_filters.get("prp_processid") or "").strip(),
        areaname=(prp_filters.get("prp_area") or "").strip(),
        layerid=layer_cache_value,
        stepseq_type=(prp_filters.get("prp_type") or "").strip(),
        body_flag=(prp_filters.get("prp_body_flag") or "").strip(),
        cham_flag=(prp_filters.get("prp_cham_flag") or "").strip(),
        compat_type=(prp_filters.get("prp_compat_type") or "").strip(),
        always_flag=(prp_filters.get("prp_always") or "").strip(),
        major_flag=(prp_filters.get("prp_major") or "").strip(),
        plan_flag=(prp_filters.get("prp_plan") or "").strip(),
    ).first()

    if not row:
        return get_prp_filter_options_from_cache(
            prp_filters=prp_filters,
            fallback_snap_date=fallback_snap_date,
        )

    fallback_options = get_prp_filter_options_from_cache(
        prp_filters=prp_filters,
        fallback_snap_date=fallback_snap_date,
    )
    payload = {
        "table_line_options": json.loads(row.line_options_json or "[]"),
        "table_prp_options": json.loads(row.prp_options_json or "[]"),
        "table_area_options": json.loads(row.area_options_json or "[]"),
        "table_layer_options": json.loads(row.layer_options_json or "[]"),
        "table_step_options": json.loads(row.step_options_json or "[]"),
        "table_descript_options": fallback_options.get("table_descript_options", []),
        "table_recipe_options": fallback_options.get("table_recipe_options", []),
        "table_type_options": json.loads(row.type_options_json or "[]"),
        "table_body_options": fallback_options.get("table_body_options", []),
        "table_cham_options": fallback_options.get("table_cham_options", []),
        "table_compat_options": fallback_options.get("table_compat_options", []),
        "table_always_options": fallback_options.get("table_always_options", []),
        "table_major_options": fallback_options.get("table_major_options", []),
        "table_plan_options": fallback_options.get("table_plan_options", []),
    }
    for key, fallback_key in (
        ("table_line_options", "table_line_options"),
        ("table_prp_options", "table_prp_options"),
        ("table_area_options", "table_area_options"),
        ("table_layer_options", "table_layer_options"),
        ("table_step_options", "table_step_options"),
        ("table_type_options", "table_type_options"),
    ):
        if not payload.get(key):
            payload[key] = fallback_options.get(fallback_key, [])
    return payload

def normalize_layer_value(value):
    if value is None:
        return ""

    s = str(value).strip()
    if s == "":
        return ""

    if re.fullmatch(r"\d+", s):
        return f"{int(s)}.0"

    if re.fullmatch(r"\d+\.\d+", s):
        try:
            return f"{float(s):.1f}"
        except ValueError:
            return s

    return s

def _natural_sort_key(value):
    s = normalize_layer_value(value) if value is not None else ""
    if s == "":
        return (float("inf"), "")

    if re.fullmatch(r"\d+(\.\d+)?", s):
        return (0, float(s), s)

    parts = re.split(r"(\d+(?:\.\d+)?)", s)
    result = []
    for part in parts:
        if part == "":
            continue
        if re.fullmatch(r"\d+(\.\d+)?", part):
            result.append((0, float(part)))
        else:
            result.append((1, part))
    return (1, result, s)
