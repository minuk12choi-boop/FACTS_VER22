from .common import (
    FactsEditHistory,
    FactsKpiTarget,
    FactsWipSource,
    _check_page_permission,
    _ensure_browser_close_session,
    _get_actor,
    _parse_week_input,
    _record_access_history,
    _week_display,
    get_object_or_404,
    login_required,
    redirect,
    render,
    services,
)

@login_required
def kpi_view(request):
    _ensure_browser_close_session(request)
    permission_response = _check_page_permission(request, "kpi", require_edit=(request.method == "POST"))
    if permission_response is not None:
        return permission_response


    _record_access_history(request, 'kpi')

    actor = _get_actor(request)

    if request.method == "POST":
        action = request.POST.get("action")

        if action == "bulk_save":
            total_rows = int(request.POST.get("total_rows", "0") or 0)

            for i in range(total_rows):
                row_id = (request.POST.get(f"row_id_{i}") or "").strip()
                is_new = (request.POST.get(f"row_is_new_{i}") or "").strip() == "1"
                is_checked = (request.POST.get(f"row_checked_{i}") or "").strip() == "1"
                delete_flag = (request.POST.get(f"row_delete_flag_{i}") or "").strip() == "1"
                target_type = (request.POST.get(f"row_target_type_{i}") or "").strip()
                target_year = (request.POST.get(f"row_target_year_{i}") or "").strip()
                target_month = (request.POST.get(f"row_target_month_{i}") or "").strip()
                row_target_week_raw = request.POST.get(f"row_target_week_{i}") or ""
                target_week = _parse_week_input(row_target_week_raw)
                lineid = (request.POST.get(f"row_lineid_{i}") or "").strip()
                processid = (request.POST.get(f"row_processid_{i}") or "").strip()
                areaname = (request.POST.get(f"row_areaname_{i}") or "").strip()
                target_rate = (request.POST.get(f"row_target_rate_{i}") or "").strip()                                                                                                                                  

                if is_new:
                    if target_type == "monthly":
                        if not (target_year and target_month and processid and target_rate):
                            continue
                    elif target_type == "weekly":
                        if not (target_year and target_month and target_week and processid and target_rate):
                            continue
                    else:
                        continue

                    obj = FactsKpiTarget.objects.create(
                        target_type=target_type,
                        target_year=int(target_year),
                        target_month=int(target_month) if target_month else None,
                        target_week=target_week,
                        lineid=lineid,
                        processid=processid,
                        areaname=areaname,
                        target_rate=target_rate,
                        created_by=actor,
                        updated_by=actor,
                        is_active=True,
                    )

                    FactsEditHistory.objects.create(
                        action_type="kpi_add",
                        changed_by=actor,
                        processid=obj.processid,
                        before_json={},
                        after_json={
                            "id": obj.id,
                            "target_type": obj.target_type,
                            "target_year": obj.target_year,
                            "target_month": obj.target_month,
                            "target_week": obj.target_week,
                            "processid": obj.processid,
                            "areaname": obj.areaname,
                            "target_rate": str(obj.target_rate),
                        },
                    )
                    continue

                if not row_id:
                    continue

                obj = get_object_or_404(FactsKpiTarget, id=row_id, is_active=True)

                if delete_flag and is_checked:
                    before_json = {
                        "target_type": obj.target_type,
                        "target_year": obj.target_year,
                        "target_month": obj.target_month,
                        "target_week": obj.target_week,
                        "lineid": obj.lineid,
                        "processid": obj.processid,
                        "areaname": obj.areaname,
                        "target_rate": str(obj.target_rate),
                    }

                    obj.is_active = False
                    obj.updated_by = actor
                    obj.save()

                    FactsEditHistory.objects.create(
                        action_type="kpi_update",
                        changed_by=actor,
                        processid=obj.processid,
                        before_json=before_json,
                        after_json={"deleted": True, "id": obj.id},
                    )
                    continue

                if is_checked:
                    if target_type == "monthly":
                        if not (target_year and target_month and processid and target_rate):
                            continue
                    elif target_type == "weekly":
                        if not (target_year and target_month and target_week and processid and target_rate):
                            continue
                    else:
                        continue

                    before_json = {
                        "target_type": obj.target_type,
                        "target_year": obj.target_year,
                        "target_month": obj.target_month,
                        "target_week": obj.target_week,
                        "lineid": obj.lineid,
                        "processid": obj.processid,
                        "areaname": obj.areaname,
                        "target_rate": str(obj.target_rate),
                    }

                    obj.target_type = target_type
                    obj.target_year = int(target_year) if target_year else obj.target_year
                    obj.target_month = int(target_month) if target_month else None
                    obj.target_week = target_week
                    obj.lineid = lineid
                    obj.processid = processid
                    obj.areaname = areaname
                    obj.target_rate = target_rate if target_rate else obj.target_rate
                    obj.updated_by = actor
                    obj.save()

                    FactsEditHistory.objects.create(
                        action_type="kpi_update",
                        changed_by=actor,
                        processid=obj.processid,
                        before_json=before_json,
                        after_json={
                            "id": obj.id,
                            "target_type": obj.target_type,
                            "target_year": obj.target_year,
                            "target_month": obj.target_month,
                            "target_week": obj.target_week,
                            "processid": obj.processid,
                            "areaname": obj.areaname,
                            "target_rate": str(obj.target_rate),
                        },
                    )

            return redirect("facts:kpi")

    rows = list(
        FactsKpiTarget.objects.filter(is_active=True).order_by(
            "-target_year", "-target_month", "-target_week", "lineid", "processid", "areaname"
        )
    )
    for row in rows:
        row.target_week_display = _week_display(row.target_week)

    cfg = services.get_dashboard_config()
    inquiry_contact = cfg.inquiry_contact if hasattr(cfg, "inquiry_contact") else cfg["inquiry_contact"]

    line_rows = list(
        FactsWipSource.objects.exclude(lineid__isnull=True)
        .exclude(lineid="")
        .values_list("lineid", flat=True)
        .distinct()
        .order_by("lineid")
    )

    context = {
        "page_title": "KPI 관리",
        "rows": rows,
        "filters": services.get_filter_options_from_cache(
            snap_date=services.get_latest_snap_date()
        ),
        "line_rows": line_rows,
        "inquiry_contact": inquiry_contact,
    }
    return render(request, "facts/kpi.html", context)
