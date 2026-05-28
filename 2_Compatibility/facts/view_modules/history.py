@login_required
def dashboard_override_save_api(request):
    _ensure_browser_close_session(request)

    payload = json.loads(request.body.decode("utf-8"))
    snap_date = datetime.strptime(payload["snap_date"], "%Y-%m-%d").date()
    date_block_response = _ensure_current_day_editable(snap_date)
    if date_block_response is not None:
        return date_block_response
    date_block_response = _ensure_current_day_editable(snap_date)
    if date_block_response is not None:
        return date_block_response
    lineid = (payload.get("lineid") or "").strip()
    items = payload.get("items", [])
    first_processid = (items[0].get("processid") if items else "") or ""
    permission_response = _check_page_permission(request, "dashboard", lineid=lineid, processid=first_processid, require_edit=True, popup=True)
    if permission_response is not None:
        return permission_response
    field_type = payload["field_type"]
    value = payload["value"]
    actor = _get_actor(request)

    for item in items:
        processid = item["processid"]
        stepseq = item["stepseq"]

        source_rows = FactsWipSource.objects.filter(
            snap_date=snap_date,
            lineid=lineid,
            processid=processid,
            stepseq=stepseq,
        )
        if not source_rows.exists():
            return JsonResponse(
                {"ok": False, "message": "호환Path가 있어야 변경 가능합니다."},
                status=400,
            )

        for src in source_rows:
            obj, _ = FactsStepPathOverride.objects.get_or_create(
                snap_date=snap_date,
                lineid=src.lineid or "",
                processid=src.processid,
                stepseq=src.stepseq,
                recipeid=src.recipeid or "",
                path=src.path or "",
                eqpline=src.eqpline or "",
                childeqp=src.childeqp or "",
                defaults={"created_by": actor},
            )

            before_json = {
                "lineid": obj.lineid or "",
                "manual_always_emergency": obj.manual_always_emergency,
                "manual_major_minor": obj.manual_major_minor,
            }


            if field_type == "always_emergency":
                obj.manual_always_emergency = value
            elif field_type == "major_minor":
                obj.manual_major_minor = value

            obj.updated_by = actor
            obj.is_active = True
            obj.save()

            FactsEditHistory.objects.create(
                action_type="override",
                snap_date=snap_date,
                lineid=src.lineid or "",
                processid=src.processid,
                stepseq=src.stepseq,
                recipeid=src.recipeid or "",
                changed_by=actor,
                before_json=before_json,
                after_json={
                    "lineid": obj.lineid or "",
                    "manual_always_emergency": obj.manual_always_emergency,
                    "manual_major_minor": obj.manual_major_minor,
                },
            )

    rebuild_targets = {
            (
                snap_date,
                (item.get("lineid") or lineid or "").strip(),
                (item.get("processid") or "").strip(),
                (item.get("stepseq") or "").strip(),
            )
            for item in items
            if (item.get("processid") or "").strip() and (item.get("stepseq") or "").strip()
        }

    for target_snap_date, target_lineid, target_processid, target_stepseq in rebuild_targets:
        rebuild_filter_cache_for_step(
            snap_date=target_snap_date,
            lineid=target_lineid,
            processid=target_processid,
            stepseq=target_stepseq,
            )


    _invalidate_dashboard_graph_cache_for_snap_date(snap_date)
    cache.clear()
    return JsonResponse({"ok": True})

@require_GET
@login_required
def dashboard_override_detail_api(request):
    _ensure_browser_close_session(request)
    permission_response = _check_page_permission(request, "dashboard", ignore_blank_scope=True)
    if permission_response is not None:
        return permission_response

    
    snap_date_str = request.GET.get("snap_date", "").strip()
    lineid = request.GET.get("lineid", "").strip()
    processid = request.GET.get("processid", "").strip()
    stepseq = request.GET.get("stepseq", "").strip()

    if not snap_date_str:
        return JsonResponse({"ok": False, "message": "기준일이 없습니다."}, status=400)
    if not processid or not stepseq:
        return JsonResponse({"ok": False, "message": "processid 또는 stepseq가 없습니다."}, status=400)

    scope_response = _check_page_permission(request, "dashboard", lineid=lineid, processid=processid, popup=True)
    if scope_response is not None:
        return scope_response

    snap_date = datetime.strptime(snap_date_str, "%Y-%m-%d").date()
    rows = _build_override_detail_rows(snap_date, lineid, processid, stepseq)

    return JsonResponse({
        "ok": True,
        "rows": rows,
    })

@require_POST
@login_required
def dashboard_override_member_save_api(request):
    _ensure_browser_close_session(request)

    payload = json.loads(request.body.decode("utf-8"))
    snap_date = datetime.strptime(payload["snap_date"], "%Y-%m-%d").date()
    date_block_response = _ensure_current_day_editable(snap_date)
    if date_block_response is not None:
        return date_block_response
    lineid = (payload.get("lineid") or "").strip()
    processid = (payload.get("processid") or "").strip()
    permission_response = _check_page_permission(request, "dashboard", lineid=lineid, processid=processid, require_edit=True, popup=True)
    if permission_response is not None:
        return permission_response
    stepseq = (payload.get("stepseq") or "").strip()
    field_type = (payload.get("field_type") or "").strip()
    member_items = payload.get("member_items", [])
    actor = _get_actor(request)


    if not processid or not stepseq or field_type not in ("always_emergency", "major_minor"):
        return JsonResponse({"ok": False, "message": "필수값이 부족합니다."}, status=400)

    for item in member_items:
        selected_flag = (item.get("selected_flag") or "N").strip().upper()
        eqp_body_name = _normalize_upper(item.get("eqp_body_name"))
        eqp_cham_name = _normalize_upper(item.get("eqp_cham_name"))
        source_types = item.get("source_types") or []
        path_refs = item.get("path_refs") or []

        if field_type == "always_emergency":
            target_value = "상시" if selected_flag == "Y" else "비상시"
        else:
            target_value = "주요" if selected_flag == "Y" else "비주요"

        if "SOURCE_PATH" in source_types:
            for ref in path_refs:
                recipeid = ref.get("recipeid") or ""
                path = ref.get("path") or ""
                eqpline = ref.get("eqpline") or ""
                childeqp = ref.get("childeqp") or ""

                src = FactsWipSource.objects.filter(
                    snap_date=snap_date,
                    lineid=lineid,
                    processid=processid,
                    stepseq=stepseq,
                    recipeid=recipeid,
                    path=path,
                    eqpline=eqpline,
                    childeqp=childeqp,
                ).first()
                if not src:
                    continue

                obj, _ = FactsStepPathOverride.objects.get_or_create(
                    snap_date=snap_date,
                    lineid=lineid,
                    processid=processid,
                    stepseq=stepseq,
                    recipeid=recipeid,
                    path=path,
                    eqpline=eqpline,
                    childeqp=childeqp,
                    defaults={"created_by": actor},
                )

                before_json = {
                    "lineid": obj.lineid or "",
                    "manual_always_emergency": obj.manual_always_emergency,
                    "manual_major_minor": obj.manual_major_minor,
                    "member_key": item.get("member_key") or "",
                }

                if field_type == "always_emergency":
                    obj.manual_always_emergency = target_value
                else:
                    obj.manual_major_minor = target_value

                obj.updated_by = actor
                obj.is_active = True
                obj.save()

                FactsEditHistory.objects.create(
                    action_type="override",
                    snap_date=snap_date,
                    lineid=lineid,
                    processid=processid,
                    stepseq=stepseq,
                    recipeid=recipeid,
                    changed_by=actor,
                    before_json=before_json,
                    after_json={
                        "lineid": obj.lineid or "",
                        "manual_always_emergency": obj.manual_always_emergency,
                        "manual_major_minor": obj.manual_major_minor,
                        "member_key": item.get("member_key") or "",
                    },
                )

        if "TIP_MISSING" in source_types and eqp_body_name:
            manual_qs = FactsTipMissingCompatPath.objects.filter(
                snap_date=snap_date,
                lineid=lineid,
                processid=processid,
                stepseq=stepseq,
                eqp_body_name=eqp_body_name,
                eqp_cham_name=eqp_cham_name,
                is_active=True,
            )

            for obj in manual_qs:
                before_json = _tip_missing_to_json(obj)

                if field_type == "always_emergency":
                    obj.always_emergency = target_value
                else:
                    obj.major_minor = target_value

                obj.updated_by = actor
                obj.save()

                FactsEditHistory.objects.create(
                    action_type="tip_missing_update",
                    snap_date=snap_date,
                    lineid=lineid,
                    processid=processid,
                    stepseq=stepseq,
                    recipeid=obj.recipeid or "",
                    changed_by=actor,
                    before_json=before_json,
                    after_json=_tip_missing_to_json(obj),
                )

    rebuild_filter_cache_for_step(
            snap_date=snap_date,
            lineid=lineid,
            processid=processid,
            stepseq=stepseq,
        )

    _invalidate_dashboard_graph_cache_for_snap_date(snap_date)
    cache.clear()
    return JsonResponse({"ok": True})

@require_GET
@login_required
def dashboard_plan_detail_api(request):
    _ensure_browser_close_session(request)
    permission_response = _check_page_permission(request, "dashboard", ignore_blank_scope=True)
    if permission_response is not None:
        return permission_response

    snap_date_str = request.GET.get("snap_date", "").strip()
    lineid = request.GET.get("lineid", "").strip()
    processid = request.GET.get("processid", "").strip()
    stepseq = request.GET.get("stepseq", "").strip()

    if not snap_date_str:
        return JsonResponse({"ok": False, "message": "기준일이 없습니다."}, status=400)

    scope_response = _check_page_permission(request, "dashboard", lineid=lineid, processid=processid, popup=True)
    if scope_response is not None:
        return scope_response

    snap_date = datetime.strptime(snap_date_str, "%Y-%m-%d").date()
    rows = services.get_plan_detail_rows_as_of(snap_date, lineid, processid, stepseq)
    if str(request.GET.get("debug_prp_table") or "").strip() == "1":
        summary_map = services._build_plan_summary_map([(lineid, processid, stepseq)], as_of_date=snap_date)
        summary_rows = summary_map.get(services._step_group_key(lineid, processid, stepseq), {})
        detail_keys = {(str(r.get("lineid") or lineid), str(r.get("processid") or processid), str(r.get("stepseq") or stepseq), str(r.get("eqp_body_name") or ""), str(r.get("eqp_cham_name") or ""), str(r.get("always_emergency") or ""), str(r.get("major_minor") or ""), "plan", str(r.get("plan_id") or r.get("id") or "")) for r in rows}
        lines = [
            f"plan_detail_rows={rows}",
            f"plan_summary_rows={summary_rows}",
            f"detail-only rows={sorted(detail_keys)}",
            "payload_type=plan",
        ]
        try_save_feedback_log("prp_table_plan_detail_debug", "\n".join(lines), "PRP_TABLE_PLAN_DETAIL_DEBUG")

    return JsonResponse({
        "ok": True,
        "rows": rows,
    })

@require_POST
@login_required
def dashboard_plan_save_api(request):
    _ensure_browser_close_session(request)

    payload = json.loads(request.body.decode("utf-8"))
    items = payload.get("items", [])
    actor = _get_actor(request)
    snap_date_str = (payload.get("snap_date") or "").strip()
    snap_date = datetime.strptime(snap_date_str, "%Y-%m-%d").date() if snap_date_str else None
    date_block_response = _ensure_current_day_editable(snap_date)
    if date_block_response is not None:
        return date_block_response
    lineid = (payload.get("lineid") or "").strip()
    first_processid = (items[0].get("processid") if items else "") or ""
    permission_response = _check_page_permission(request, "dashboard", lineid=lineid, processid=first_processid, require_edit=True, popup=True)
    if permission_response is not None:
        return permission_response

    always_emergency = (payload.get("always_emergency") or "").strip()
    major_minor = (payload.get("major_minor") or "").strip()
    eqp_body_name = _normalize_upper(payload.get("eqp_body_name"))
    eqp_cham_name = _normalize_upper(payload.get("eqp_cham_name"))
    compatibility_due_date = _normalize_date_input(payload.get("compatibility_due_date"))
    eval_lot_id = _normalize_upper(payload.get("eval_lot_id"))
    required_eval_stage_id = payload.get("required_eval_stage_id") or None
    memo = (payload.get("memo") or "").strip()
    plan_id = payload.get("plan_id")
    original_eqp_body_name = _normalize_upper(payload.get("original_eqp_body_name"))
    original_eqp_cham_name = _normalize_upper(payload.get("original_eqp_cham_name"))

    stage_obj = None
    if required_eval_stage_id:
        stage_obj = FactsEvalStageMaster.objects.filter(
            id=required_eval_stage_id,
            is_active=True,
        ).first()

    if not eqp_body_name:
        return JsonResponse({"ok": False, "message": "호환EQPBODY명은 필수기재입니다."}, status=400)
    if not items:
        return JsonResponse({"ok": False, "message": "대상 step이 없습니다."}, status=400)

    for item in items:
        item_lineid = (item.get("lineid") or lineid or "").strip()
        processid = item["processid"]
        stepseq = item["stepseq"]

        if plan_id:
            obj = FactsStepPlan.objects.filter(
                id=plan_id,
                lineid=item_lineid,
                processid=processid,
                stepseq=stepseq,
                is_active=True,
            ).first()
            if not obj and original_eqp_body_name:
                obj = FactsStepPlan.objects.filter(
                    lineid=item_lineid,
                    processid=processid,
                    stepseq=stepseq,
                    eqp_body_name=original_eqp_body_name,
                    eqp_cham_name=original_eqp_cham_name,
                    is_active=True,
                ).order_by("-updated_at", "-id").first()
            if not obj:
                return JsonResponse({"ok": False, "message": "수정 대상 계획이 없습니다."}, status=404)

            before_json = _plan_to_json(obj)
            obj.always_emergency = always_emergency
            obj.major_minor = major_minor
            obj.eqp_body_name = eqp_body_name
            obj.eqp_cham_name = eqp_cham_name
            obj.compatibility_due_date = compatibility_due_date
            obj.eval_lot_id = eval_lot_id
            obj.required_eval_stage = stage_obj
            obj.memo = memo
            obj.updated_by = actor
            obj.save()

            FactsEditHistory.objects.create(
                action_type="plan_update",
                snap_date=snap_date,
                lineid=item_lineid,
                processid=processid,
                stepseq=stepseq,
                recipeid=obj.recipeid or "",
                changed_by=actor,
                before_json=before_json,
                after_json=_plan_to_json(obj),
            )
        else:
            obj = FactsStepPlan.objects.create(
                lineid=item_lineid,
                processid=processid,
                stepseq=stepseq,
                recipeid="",
                always_emergency=always_emergency,
                major_minor=major_minor,
                eqp_body_name=eqp_body_name,
                eqp_cham_name=eqp_cham_name,
                compatibility_due_date=compatibility_due_date,
                eval_lot_id=eval_lot_id,
                required_eval_stage=stage_obj,
                memo=memo,
                is_active=True,
                created_by=actor,
                updated_by=actor,
            )

            FactsEditHistory.objects.create(
                action_type="plan_add",
                snap_date=snap_date,
                lineid=item_lineid,
                processid=processid,
                stepseq=stepseq,
                recipeid="",
                changed_by=actor,
                before_json={},
                after_json=_plan_to_json(obj),
            )

    rebuild_targets = {
            (
                snap_date,
                (item.get("lineid") or lineid or "").strip(),
                (item.get("processid") or "").strip(),
                (item.get("stepseq") or "").strip(),
            )
            for item in items
            if (item.get("processid") or "").strip() and (item.get("stepseq") or "").strip()
        }

    for target_snap_date, target_lineid, target_processid, target_stepseq in rebuild_targets:
        rebuild_filter_cache_for_step(
            snap_date=target_snap_date,
            lineid=target_lineid,
            processid=target_processid,
            stepseq=target_stepseq,
        )

    _invalidate_dashboard_graph_cache_for_snap_date(snap_date)
    cache.clear()
    return JsonResponse({"ok": True})

@require_POST
@login_required
def dashboard_plan_delete_api(request):
    _ensure_browser_close_session(request)

    payload = json.loads(request.body.decode("utf-8"))
    plan_id = payload.get("plan_id")
    actor = _get_actor(request)
    snap_date_str = (payload.get("snap_date") or "").strip()
    snap_date = datetime.strptime(snap_date_str, "%Y-%m-%d").date() if snap_date_str else None
    date_block_response = _ensure_current_day_editable(snap_date)
    if date_block_response is not None:
        return date_block_response
    lineid = (payload.get("lineid") or "").strip()
    processid = (payload.get("processid") or "").strip()
    stepseq = (payload.get("stepseq") or "").strip()
    original_eqp_body_name = _normalize_upper(payload.get("original_eqp_body_name"))
    original_eqp_cham_name = _normalize_upper(payload.get("original_eqp_cham_name"))

    permission_response = _check_page_permission(
        request,
        "dashboard",
        lineid=lineid,
        processid=processid,
        require_edit=True,
        popup=True,
    )
    if permission_response is not None:
        return permission_response

    if not plan_id:
        return JsonResponse({"ok": False, "message": "삭제 대상 ID가 없습니다.", "received_id": plan_id, "expected_field": "plan_id"}, status=400)

    obj = FactsStepPlan.objects.filter(id=plan_id, lineid=lineid, is_active=True).first()
    if not obj and processid and stepseq and original_eqp_body_name:
        obj = FactsStepPlan.objects.filter(
            lineid=lineid,
            processid=processid,
            stepseq=stepseq,
            eqp_body_name=original_eqp_body_name,
            eqp_cham_name=original_eqp_cham_name,
            is_active=True,
        ).order_by("-updated_at", "-id").first()
    if not obj and processid and stepseq:
        candidates = FactsStepPlan.objects.filter(
            lineid=lineid,
            processid=processid,
            stepseq=stepseq,
            is_active=True,
        ).order_by("-updated_at", "-id")
        if candidates.count() == 1:
            obj = candidates.first()
    if not obj:
        return JsonResponse({"ok": False, "message": "이미 삭제된 항목입니다.", "received_id": plan_id, "expected_field": "plan_id"}, status=200)

    before_json = _plan_to_json(obj)
    obj.is_active = False
    obj.updated_by = actor
    obj.save()

    FactsEditHistory.objects.create(
        action_type="plan_delete",
        snap_date=snap_date,
        lineid=lineid,
        processid=obj.processid,
        stepseq=obj.stepseq,
        recipeid=obj.recipeid or "",
        changed_by=actor,
        before_json=before_json,
        after_json={"deleted": True, "id": obj.id},
    )

    rebuild_filter_cache_for_step(
            snap_date=snap_date,
            lineid=lineid,
            processid=obj.processid,
            stepseq=obj.stepseq,
        )

    _invalidate_dashboard_graph_cache_for_snap_date(snap_date)
    cache.clear()
    return JsonResponse({"ok": True})

@require_GET
@login_required
def dashboard_tip_missing_detail_api(request):
    _ensure_browser_close_session(request)
    permission_response = _check_page_permission(request, "dashboard", ignore_blank_scope=True)
    if permission_response is not None:
        return permission_response


    snap_date_str = request.GET.get("snap_date", "").strip()
    lineid = request.GET.get("lineid", "").strip()
    processid = request.GET.get("processid", "").strip()
    stepseq = request.GET.get("stepseq", "").strip()

    if not snap_date_str:
        return JsonResponse({"ok": False, "message": "기준일이 없습니다."}, status=400)

    scope_response = _check_page_permission(request, "dashboard", lineid=lineid, processid=processid, popup=True)
    if scope_response is not None:
        return scope_response

    snap_date = datetime.strptime(snap_date_str, "%Y-%m-%d").date()
    rows = services.get_tip_missing_detail_rows_as_of(snap_date, lineid, processid, stepseq)
    if str(request.GET.get("debug_prp_table") or "").strip() == "1":
        summary_map = services._build_tip_missing_summary_map(snap_date, [(lineid, processid, stepseq)], as_of_date=snap_date)
        summary_rows = summary_map.get(services._step_group_key(lineid, processid, stepseq), {})
        detail_keys = {(str(r.get("lineid") or lineid), str(processid), str(stepseq), str(r.get("eqp_body_name") or ""), str(r.get("eqp_cham_name") or ""), str(r.get("always_emergency") or ""), str(r.get("major_minor") or ""), "tip_missing", str(r.get("tip_missing_id") or r.get("id") or "")) for r in rows}
        lines = [
            f"tip_missing_detail_rows={rows}",
            f"tip_missing_summary_rows={summary_rows}",
            f"detail-only rows={sorted(detail_keys)}",
            "payload_type=tip_missing",
        ]
        try_save_feedback_log("prp_table_tip_detail_debug", "\n".join(lines), "PRP_TABLE_TIP_DETAIL_DEBUG")

    return JsonResponse({
        "ok": True,
        "rows": rows,
    })

@require_POST
@login_required
def dashboard_tip_missing_save_api(request):
    _ensure_browser_close_session(request)

    payload = json.loads(request.body.decode("utf-8"))
    snap_date = datetime.strptime(payload["snap_date"], "%Y-%m-%d").date()
    date_block_response = _ensure_current_day_editable(snap_date)
    if date_block_response is not None:
        return date_block_response
    items = payload.get("items", [])
    actor = _get_actor(request)
    lineid = (payload.get("lineid") or "").strip()
    first_processid = (items[0].get("processid") if items else "") or ""
    permission_response = _check_page_permission(request, "dashboard", lineid=lineid, processid=first_processid, require_edit=True, popup=True)
    if permission_response is not None:
        return permission_response

    always_emergency = (payload.get("always_emergency") or "").strip()
    major_minor = (payload.get("major_minor") or "").strip()
    eqp_body_name = _normalize_upper(payload.get("eqp_body_name"))
    eqp_cham_name = _normalize_upper(payload.get("eqp_cham_name"))
    tip_missing_id = payload.get("tip_missing_id")

    if not always_emergency:
        return JsonResponse({"ok": False, "message": "상시/비상시는 필수기재입니다."}, status=400)
    if not major_minor:
        return JsonResponse({"ok": False, "message": "주요/비주요는 필수기재입니다."}, status=400)
    if not eqp_body_name:
        return JsonResponse({"ok": False, "message": "호환EQPBODY명은 필수기재입니다."}, status=400)
    if not items:
        return JsonResponse({"ok": False, "message": "대상 step이 없습니다."}, status=400)

    for item in items:
        item_lineid = (item.get("lineid") or lineid or "").strip()
        processid = item["processid"]
        stepseq = item["stepseq"]

        if tip_missing_id:
            obj = FactsTipMissingCompatPath.objects.filter(
                id=tip_missing_id,
                lineid=item_lineid,
                processid=processid,
                stepseq=stepseq,
                is_active=True,
            ).first()
            if not obj:
                return JsonResponse({"ok": False, "message": "수정 대상 미등록TIP호환Path가 없습니다."}, status=404)

            before_json = _tip_missing_to_json(obj)
            obj.always_emergency = always_emergency
            obj.major_minor = major_minor
            obj.eqp_body_name = eqp_body_name
            obj.eqp_cham_name = eqp_cham_name
            obj.updated_by = actor
            obj.save()

            FactsEditHistory.objects.create(
                action_type="tip_missing_update",
                snap_date=snap_date,
                lineid=item_lineid,
                processid=processid,
                stepseq=stepseq,
                recipeid=obj.recipeid or "",
                changed_by=actor,
                before_json=before_json,
                after_json=_tip_missing_to_json(obj),
            )
        else:
            obj = FactsTipMissingCompatPath.objects.create(
                snap_date=snap_date,
                lineid=item_lineid,
                processid=processid,
                stepseq=stepseq,
                recipeid="",
                always_emergency=always_emergency,
                major_minor=major_minor,
                eqp_body_name=eqp_body_name,
                eqp_cham_name=eqp_cham_name,
                is_active=True,
                created_by=actor,
                updated_by=actor,
            )

            FactsEditHistory.objects.create(
                action_type="tip_missing_add",
                snap_date=snap_date,
                lineid=item_lineid,
                processid=processid,
                stepseq=stepseq,
                recipeid="",
                changed_by=actor,
                before_json={},
                after_json=_tip_missing_to_json(obj),
            )

    rebuild_targets = {
            (
                snap_date,
                (item.get("lineid") or lineid or "").strip(),
                (item.get("processid") or "").strip(),
                (item.get("stepseq") or "").strip(),
            )
            for item in items
            if (item.get("processid") or "").strip() and (item.get("stepseq") or "").strip()
        }

    for target_snap_date, target_lineid, target_processid, target_stepseq in rebuild_targets:
        rebuild_filter_cache_for_step(
            snap_date=target_snap_date,
            lineid=target_lineid,
            processid=target_processid,
            stepseq=target_stepseq,
        )

    _invalidate_dashboard_graph_cache_for_snap_date(snap_date)
    cache.clear()
    return JsonResponse({"ok": True})

@require_POST
@login_required
def dashboard_tip_missing_delete_api(request):
    _ensure_browser_close_session(request)

    payload = json.loads(request.body.decode("utf-8"))
    tip_missing_id = payload.get("tip_missing_id")
    actor = _get_actor(request)
    snap_date_str = (payload.get("snap_date") or "").strip()
    snap_date = datetime.strptime(snap_date_str, "%Y-%m-%d").date() if snap_date_str else None
    date_block_response = _ensure_current_day_editable(snap_date)
    if date_block_response is not None:
        return date_block_response
    lineid = (payload.get("lineid") or "").strip()
    processid = (payload.get("processid") or "").strip()

    permission_response = _check_page_permission(
        request,
        "dashboard",
        lineid=lineid,
        processid=processid,
        require_edit=True,
        popup=True,
    )
    if permission_response is not None:
        return permission_response

    if not tip_missing_id:
        return JsonResponse({"ok": False, "message": "삭제 대상 ID가 없습니다.", "received_id": tip_missing_id, "expected_field": "tip_missing_id"}, status=400)

    obj = FactsTipMissingCompatPath.objects.filter(id=tip_missing_id, lineid=lineid, is_active=True).first()
    if not obj:
        return JsonResponse({"ok": False, "message": "이미 삭제된 항목입니다.", "received_id": tip_missing_id, "expected_field": "tip_missing_id"}, status=200)

    before_json = _tip_missing_to_json(obj)
    obj.is_active = False
    obj.updated_by = actor
    obj.save()

    FactsEditHistory.objects.create(
        action_type="tip_missing_delete",
        snap_date=obj.snap_date,
        lineid=lineid,
        processid=obj.processid,
        stepseq=obj.stepseq,
        recipeid=obj.recipeid or "",
        changed_by=actor,
        before_json=before_json,
        after_json={"deleted": True, "id": obj.id},
    )

    rebuild_filter_cache_for_step(
            snap_date=obj.snap_date,
            lineid=lineid,
            processid=obj.processid,
            stepseq=obj.stepseq,
        )

    _invalidate_dashboard_graph_cache_for_snap_date(obj.snap_date)
    cache.clear()
    return JsonResponse({"ok": True})

@require_GET
@login_required
def dashboard_similar_eqp_api(request):
    _ensure_browser_close_session(request)
    permission_response = _check_page_permission(request, "dashboard", ignore_blank_scope=True)
    if permission_response is not None:
        return permission_response

    snap_date_str = request.GET.get("snap_date", "").strip()
    lineid = request.GET.get("lineid", "").strip()
    processid = request.GET.get("processid", "").strip()
    stepseq = request.GET.get("stepseq", "").strip()

    if not snap_date_str:
        return JsonResponse({"ok": False, "message": "기준일이 없습니다."}, status=400)
    if not processid or not stepseq:
        return JsonResponse({"ok": False, "message": "processid 또는 stepseq가 없습니다."}, status=400)

    scope_response = _check_page_permission(request, "dashboard", lineid=lineid, processid=processid, popup=True)
    if scope_response is not None:
        return scope_response

    snap_date = datetime.strptime(snap_date_str, "%Y-%m-%d").date()

    result = services.get_similar_model_eqp_candidates(
        snap_date=snap_date,
        processid=processid,
        stepseq=stepseq,
        include_current=False,
    )

    rows = []
    for row in result["recommendations"]:
        origin_line_id = row.get("origin_line_id", "")
        line_obj = FactsLineMaster.objects.filter(line_id=origin_line_id, is_active=True).first()

        if line_obj and line_obj.line_name:
            display_location = f"{line_obj.line_name}({line_obj.line_id})"
        else:
            display_location = origin_line_id

        rows.append({
            "eqp_id": row.get("eqp_id", ""),
            "origin_line_id": display_location,
            "eqp_model": row.get("eqp_model", ""),
            "match_type": row.get("match_type", ""),
            "match_score": row.get("match_score", ""),
            "matched_base_model": row.get("matched_base_model", ""),
        })

    return JsonResponse({
        "ok": True,
        "base_eqps": result["base_eqps"],
        "base_models": result["base_models"],
        "rows": rows,
        "notice": "해당 추천은 GPM 등록된 EQP_MODEL을 기준으로 합니다.",
    })

def _is_invalid_single_cham_value(value):
    s = str(value or "").strip().upper()
    if not s:
        return False
    if any(sep in s for sep in [":", ";", ","]):
        return True
    if len(s) > 1:
        return True
    return False

@require_POST
@login_required
def dashboard_bulk_upload_api(request):
    _ensure_browser_close_session(request)

    upload = request.FILES.get("file")
    snap_date_str = request.POST.get("snap_date")
    request_lineid = (request.POST.get("lineid") or "").strip()
    request_processid = (request.POST.get("processid") or request.POST.get("prp_processid") or "").strip()
    actor = _get_actor(request)

    # 최초 진입 권한검사는 빈 scope 허용
    permission_response = _check_page_permission(
        request,
        "dashboard",
        lineid=request_lineid,
        processid=request_processid,
        require_edit=True,
        popup=True,
        ignore_blank_scope=True,
    )
    if permission_response is not None:
        return permission_response

    if not upload or not snap_date_str:
        return JsonResponse({"ok": False, "message": "파일과 기준일이 필요합니다."}, status=400)

    snap_date = datetime.strptime(snap_date_str, "%Y-%m-%d").date()
    name = upload.name.lower()
    rows = []

    if name.endswith(".csv"):
        content = upload.read().decode("utf-8-sig")
        reader = csv.DictReader(io.StringIO(content))
        for row_no, row in enumerate(reader, start=2):
            item = dict(row)
            item["__rownum__"] = row_no
            rows.append(item)
    elif name.endswith(".xlsx"):
        wb = load_workbook(upload, data_only=True)
        ws = wb["FACTS_UPLOAD_TEMPLATE"] if "FACTS_UPLOAD_TEMPLATE" in wb.sheetnames else wb.active
        header = [str(c.value).strip() if c.value is not None else "" for c in ws[1]]

        for excel_row_no, row in enumerate(ws.iter_rows(min_row=2, values_only=True), start=2):
            item = {}
            for idx, key in enumerate(header):
                item[key] = row[idx] if idx < len(row) else None
            item["__rownum__"] = excel_row_no
            rows.append(item)
    else:
        return JsonResponse({"ok": False, "message": "csv 또는 xlsx만 업로드 가능합니다."}, status=400)

    stage_map = {
        s.stage_code: s
        for s in FactsEvalStageMaster.objects.filter(is_active=True)
    }

    seen_plan_keys = set()
    seen_tip_missing_keys = set()

    plan_created = 0
    plan_updated = 0
    plan_deleted = 0
    tip_created = 0
    tip_updated = 0
    tip_deleted = 0
    skipped_duplicate_in_file = 0
    skipped_invalid_cham = 0
    skipped_permission_denied = 0
    skipped_missing_required = 0
    skipped_invalid_action = 0

    rebuild_scope_targets = set()

    for r in rows:
        row_lineid = _normalize_upper(r.get("LINE")) or _normalize_upper(request_lineid)
        row_processid = _normalize_upper(r.get("PROCESSID"))
        row_stepseq = _normalize_upper(r.get("STEPSEQ"))

        plan_always = str(r.get("호환계획_상시/비상시") or "").strip()
        plan_major = str(r.get("호환계획_주요/비주요") or "").strip()
        plan_body = _normalize_upper(r.get("호환계획_호환EQPBODY명"))
        plan_cham = _normalize_upper(r.get("호환계획_호환EQPCHAM명"))
        plan_due = _normalize_date_input(r.get("호환계획_호환완료계획일"))
        eval_lot_id = _normalize_upper(r.get("호환계획_평가LotID"))
        stage_code = _normalize_upper(r.get("호환계획_평가단계"))
        memo = str(r.get("호환계획_비고") or "").strip()
        plan_action = _normalize_upper(r.get("호환계획_ACTION")) or "UPSERT"
        plan_id = str(r.get("호환계획_ID") or "").strip()

        tip_missing_always = str(r.get("미등록TIP호환Path_상시/비상시") or "").strip()
        tip_missing_major = str(r.get("미등록TIP호환Path_주요/비주요") or "").strip()
        tip_missing_body = _normalize_upper(r.get("미등록TIP호환Path_호환EQPBODY명"))
        tip_missing_cham = _normalize_upper(r.get("미등록TIP호환Path_호환EQPCHAM명"))
        tip_action = _normalize_upper(r.get("미등록TIP호환Path_ACTION")) or "UPSERT"
        tip_id = str(r.get("미등록TIP호환Path_ID") or "").strip()

        if not row_lineid or not row_processid or not row_stepseq:
            skipped_missing_required += 1
            continue

        row_permission_response = _check_page_permission(
            request,
            "dashboard",
            lineid=row_lineid,
            processid=row_processid,
            require_edit=True,
            popup=True,
        )
        if row_permission_response is not None:
            skipped_permission_denied += 1
            continue

        rebuild_scope_targets.add((snap_date, row_lineid, row_processid, row_stepseq))

        plan_cham_invalid = (plan_action == "UPSERT") and _is_invalid_single_cham_value(plan_cham)
        tip_cham_invalid = (tip_action == "UPSERT") and _is_invalid_single_cham_value(tip_missing_cham)

        if plan_cham_invalid or tip_cham_invalid:
            skipped_invalid_cham += 1
            continue

        if plan_action not in {"UPSERT", "DELETE"} or tip_action not in {"UPSERT", "DELETE"}:
            skipped_invalid_action += 1
            continue

        if plan_body or plan_id:
            plan_key = (plan_action, plan_id, row_lineid, row_processid, row_stepseq, plan_body, plan_cham)
            if plan_key in seen_plan_keys:
                skipped_duplicate_in_file += 1
            else:
                seen_plan_keys.add(plan_key)
                stage_obj = stage_map.get(stage_code) if stage_code else None

                existing_qs = FactsStepPlan.objects.filter(
                    lineid=row_lineid,
                    processid=row_processid,
                    stepseq=row_stepseq,
                    is_active=True,
                )
                if plan_id:
                    existing_qs = existing_qs.filter(id=plan_id)
                else:
                    existing_qs = existing_qs.filter(eqp_body_name=plan_body, eqp_cham_name=plan_cham)
                existing_qs = existing_qs.order_by("-updated_at", "-id")
                obj = existing_qs.first()

                if plan_action == "DELETE":
                    if obj:
                        before_json = _plan_to_json(obj)
                        obj.is_active = False
                        obj.updated_by = actor
                        obj.save(update_fields=["is_active", "updated_by", "updated_at"])
                        FactsEditHistory.objects.create(
                            action_type="plan_delete",
                            snap_date=snap_date,
                            lineid=row_lineid,
                            processid=row_processid,
                            stepseq=row_stepseq,
                            recipeid=obj.recipeid or "",
                            changed_by=actor,
                            before_json=before_json,
                            after_json={"id": obj.id, "is_active": False},
                        )
                        plan_deleted += 1
                elif obj:
                    before_json = _plan_to_json(obj)
                    existing_qs.exclude(id=obj.id).update(is_active=False, updated_by=actor)
                    obj.always_emergency = plan_always
                    obj.major_minor = plan_major
                    obj.compatibility_due_date = plan_due
                    obj.eval_lot_id = eval_lot_id
                    obj.required_eval_stage = stage_obj
                    obj.memo = memo
                    obj.updated_by = actor
                    obj.save()
                    FactsEditHistory.objects.create(
                        action_type="plan_update",
                        snap_date=snap_date,
                        lineid=row_lineid,
                        processid=row_processid,
                        stepseq=row_stepseq,
                        recipeid=obj.recipeid or "",
                        changed_by=actor,
                        before_json=before_json,
                        after_json=_plan_to_json(obj),
                    )
                    plan_updated += 1
                else:
                    obj = FactsStepPlan.objects.create(
                        lineid=row_lineid, processid=row_processid, stepseq=row_stepseq, recipeid="",
                        always_emergency=plan_always, major_minor=plan_major, eqp_body_name=plan_body,
                        eqp_cham_name=plan_cham, compatibility_due_date=plan_due, eval_lot_id=eval_lot_id,
                        required_eval_stage=stage_obj, memo=memo, is_active=True, created_by=actor, updated_by=actor,
                    )
                    FactsEditHistory.objects.create(
                        action_type="plan_add", snap_date=snap_date, lineid=row_lineid, processid=row_processid,
                        stepseq=row_stepseq, recipeid="", changed_by=actor, before_json={}, after_json=_plan_to_json(obj),
                    )
                    plan_created += 1

        if tip_missing_body or tip_id:
            tip_key = (tip_action, tip_id, snap_date, row_lineid, row_processid, row_stepseq, tip_missing_body, tip_missing_cham)
            if tip_key in seen_tip_missing_keys:
                skipped_duplicate_in_file += 1
            else:
                seen_tip_missing_keys.add(tip_key)

                existing_tip_qs = FactsTipMissingCompatPath.objects.filter(
                    snap_date=snap_date,
                    lineid=row_lineid,
                    processid=row_processid,
                    stepseq=row_stepseq,
                    is_active=True,
                )
                if tip_id:
                    existing_tip_qs = existing_tip_qs.filter(id=tip_id)
                else:
                    existing_tip_qs = existing_tip_qs.filter(eqp_body_name=tip_missing_body, eqp_cham_name=tip_missing_cham)
                existing_tip_qs = existing_tip_qs.order_by("-updated_at", "-id")

                obj2 = existing_tip_qs.first()
                if tip_action == "DELETE":
                    if obj2:
                        before_json = _tip_missing_to_json(obj2)
                        obj2.is_active = False
                        obj2.updated_by = actor
                        obj2.save(update_fields=["is_active", "updated_by", "updated_at"])
                        FactsEditHistory.objects.create(
                            action_type="tip_missing_delete",
                            snap_date=snap_date,
                            lineid=row_lineid,
                            processid=row_processid,
                            stepseq=row_stepseq,
                            recipeid=obj2.recipeid or "",
                            changed_by=actor,
                            before_json=before_json,
                            after_json={"id": obj2.id, "is_active": False},
                        )
                        tip_deleted += 1
                elif obj2:
                    before_json = _tip_missing_to_json(obj2)

                    existing_tip_qs.exclude(id=obj2.id).update(
                        is_active=False,
                        updated_by=actor,
                    )

                    obj2.always_emergency = tip_missing_always
                    obj2.major_minor = tip_missing_major
                    obj2.updated_by = actor
                    obj2.save()

                    FactsEditHistory.objects.create(
                        action_type="tip_missing_update",
                        snap_date=snap_date,
                        lineid=row_lineid,
                        processid=row_processid,
                        stepseq=row_stepseq,
                        recipeid=obj2.recipeid or "",
                        changed_by=actor,
                        before_json=before_json,
                        after_json=_tip_missing_to_json(obj2),
                    )
                    tip_updated += 1
                else:
                    obj2 = FactsTipMissingCompatPath.objects.create(
                        snap_date=snap_date,
                        lineid=row_lineid,
                        processid=row_processid,
                        stepseq=row_stepseq,
                        recipeid="",
                        always_emergency=tip_missing_always,
                        major_minor=tip_missing_major,
                        eqp_body_name=tip_missing_body,
                        eqp_cham_name=tip_missing_cham,
                        is_active=True,
                        created_by=actor,
                        updated_by=actor,
                    )

                    FactsEditHistory.objects.create(
                        action_type="tip_missing_add",
                        snap_date=snap_date,
                        lineid=row_lineid,
                        processid=row_processid,
                        stepseq=row_stepseq,
                        recipeid="",
                        changed_by=actor,
                        before_json={},
                        after_json=_tip_missing_to_json(obj2),
                    )
                    tip_created += 1

    for target_snap_date, target_lineid, target_processid, target_stepseq in rebuild_scope_targets:
        rebuild_filter_cache_for_step(
            snap_date=target_snap_date,
            lineid=target_lineid,
            processid=target_processid,
            stepseq=target_stepseq,
        )

    _invalidate_dashboard_graph_cache_for_snap_date(snap_date)
    cache.clear()

    return JsonResponse({
        "ok": True,
        "message": (
            f"업로드 완료. "
            f"호환계획 신규 {plan_created}건, 수정 {plan_updated}건, 삭제 {plan_deleted}건, "
            f"TIP미등록 호환Path 신규 {tip_created}건, 수정 {tip_updated}건, 삭제 {tip_deleted}건, "
            f"동일 파일 내 중복으로 스킵 {skipped_duplicate_in_file}건, "
            f"ACTION 값 오류로 스킵 {skipped_invalid_action}건, "
            f"CHAM 입력 오류로 스킵 {skipped_invalid_cham}건, "
            f"필수값 누락으로 스킵 {skipped_missing_required}건, "
            f"권한 부족으로 스킵 {skipped_permission_denied}건"
        ),
    })
