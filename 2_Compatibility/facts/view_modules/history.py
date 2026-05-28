@require_GET
@login_required
def dashboard_upload_template(request):
    _ensure_browser_close_session(request)
    permission_response = _check_page_permission(request, "dashboard", ignore_blank_scope=True)
    if permission_response is not None:
        return permission_response

    wb = Workbook()
    ws = wb.active
    ws.title = "FACTS_UPLOAD_TEMPLATE"

    headers = [
        "LINE",
        "PROCESSID",
        "STEPSEQ",
        "호환계획_ACTION",
        "호환계획_ID",
        "호환계획_상시/비상시",
        "호환계획_주요/비주요",
        "호환계획_호환EQPBODY명",
        "호환계획_호환EQPCHAM명",
        "호환계획_호환완료계획일",
        "호환계획_평가LotID",
        "호환계획_평가단계",
        "호환계획_비고",
        "미등록TIP호환Path_ACTION",
        "미등록TIP호환Path_ID",
        "미등록TIP호환Path_상시/비상시",
        "미등록TIP호환Path_주요/비주요",
        "미등록TIP호환Path_호환EQPBODY명",
        "미등록TIP호환Path_호환EQPCHAM명",
    ]
    ws.append(headers)

    ws.append([
        "PFR1",
        "P1SD",
        "SD00000000",
        "UPSERT",
        "",
        "상시",
        "주요",
        "WSOD701",
        "F(*하나의 행엔 하나의 CHAM만 입력해주세요.)",
        "2026-04-13",
        "LOT123456",
        "",
        "계획 예시",
        "UPSERT",
        "",
        "상시",
        "주요",
        "WSOD702",
        "1(*하나의 행엔 하나의 CHAM만 입력해주세요.)",
    ])

    for cell in ws[1]:
        cell.font = Font(bold=True)
        cell.alignment = Alignment(horizontal="center", vertical="center")

    header_map = {name: idx + 1 for idx, name in enumerate(headers)}

    widths = {
        "A": 14,
        "B": 16, "C": 16, "D": 16, "E": 14, "F": 25, "G": 25,
        "H": 25, "I": 30, "J": 25, "K": 18, "L": 16, "M": 24,
        "N": 16, "O": 14, "P": 30, "Q": 30, "R": 34, "S": 34,
    }
    for col, width in widths.items():
        ws.column_dimensions[col].width = width

    ws.freeze_panes = "A2"

    dv_always = DataValidation(type="list", formula1='"상시,비상시"', allow_blank=True)
    dv_major = DataValidation(type="list", formula1='"주요,비주요"', allow_blank=True)
    dv_action = DataValidation(type="list", formula1='"UPSERT,DELETE"', allow_blank=True)

    stage_codes = list(
        FactsEvalStageMaster.objects.filter(is_active=True)
        .order_by("sort_order", "stage_code")
        .values_list("stage_code", flat=True)
    )
    stage_formula = '"' + ",".join(stage_codes) + '"' if stage_codes else '""'
    dv_stage = DataValidation(type="list", formula1=stage_formula, allow_blank=True)

    dv_date = DataValidation(
        type="date",
        operator="between",
        formula1="DATE(2020,1,1)",
        formula2="DATE(2099,12,31)",
        allow_blank=True,
    )
    dv_date.error = "날짜는 엑셀 날짜 형식으로 입력하십시오. 예: 2026-04-13"
    dv_date.prompt = "호환완료계획일은 날짜 형식으로 입력"

    ws.add_data_validation(dv_always)
    ws.add_data_validation(dv_major)
    ws.add_data_validation(dv_action)
    ws.add_data_validation(dv_stage)
    ws.add_data_validation(dv_date)

    dv_action.add("D2:D5000")
    dv_always.add("F2:F5000")
    dv_major.add("G2:G5000")
    dv_stage.add("L2:L5000")
    dv_date.add("J2:J5000")
    dv_action.add("N2:N5000")
    dv_always.add("P2:P5000")
    dv_major.add("Q2:Q5000")

    for row_idx in range(2, 5001):
        ws[f"J{row_idx}"].number_format = "yyyy-mm-dd"

    red_fill = PatternFill(
        fill_type="solid",
        start_color="FFC7CE",
        end_color="FFC7CE",
    )

    line_col = get_column_letter(header_map["LINE"])
    process_col = get_column_letter(header_map["PROCESSID"])
    step_col = get_column_letter(header_map["STEPSEQ"])
    plan_body_col = get_column_letter(header_map["호환계획_호환EQPBODY명"])
    plan_cham_col = get_column_letter(header_map["호환계획_호환EQPCHAM명"])
    tip_body_col = get_column_letter(header_map["미등록TIP호환Path_호환EQPBODY명"])
    tip_cham_col = get_column_letter(header_map["미등록TIP호환Path_호환EQPCHAM명"])

    # -------------------------------------------------
    # 숨김 helper 컬럼
    # AA: 호환계획 중복 key
    # AB: TIP미등록 중복 key
    # AC: 호환EQPCHAM명 유효성
    # AD: 미등록TIP호환Path_호환EQPCHAM명 유효성
    # -------------------------------------------------
    helper_cols = {
        "plan_dup_key": "AA",
        "tip_dup_key": "AB",
        "plan_cham_invalid": "AC",
        "tip_cham_invalid": "AD",
    }

    ws["AA1"] = "PLAN_DUP_KEY"
    ws["AB1"] = "TIP_DUP_KEY"
    ws["AC1"] = "PLAN_CHAM_INVALID"
    ws["AD1"] = "TIP_CHAM_INVALID"

    for row_idx in range(2, 5001):
        # CHAM이 비어 있으면 BODY까지만 key로 생성
        ws[f"AA{row_idx}"] = (
            f'=IF(TRIM(${plan_body_col}{row_idx})="", "", '
            f'UPPER(TRIM(${line_col}{row_idx}))&"|"&'
            f'UPPER(TRIM(${process_col}{row_idx}))&"|"&'
            f'UPPER(TRIM(${step_col}{row_idx}))&"|"&'
            f'UPPER(TRIM(${plan_body_col}{row_idx}))&"|"&'
            f'UPPER(TRIM(${plan_cham_col}{row_idx})))'
        )

        ws[f"AB{row_idx}"] = (
            f'=IF(TRIM(${tip_body_col}{row_idx})="", "", '
            f'UPPER(TRIM(${line_col}{row_idx}))&"|"&'
            f'UPPER(TRIM(${process_col}{row_idx}))&"|"&'
            f'UPPER(TRIM(${step_col}{row_idx}))&"|"&'
            f'UPPER(TRIM(${tip_body_col}{row_idx}))&"|"&'
            f'UPPER(TRIM(${tip_cham_col}{row_idx})))'
        )

        ws[f"AC{row_idx}"] = (
            f'=IF(TRIM(${plan_cham_col}{row_idx})="", FALSE, '
            f'OR(ISNUMBER(SEARCH(":",${plan_cham_col}{row_idx})),'
            f'ISNUMBER(SEARCH(";",${plan_cham_col}{row_idx})),'
            f'ISNUMBER(SEARCH(",",${plan_cham_col}{row_idx})),'
            f'LEN(TRIM(${plan_cham_col}{row_idx}))>1))'
        )

        ws[f"AD{row_idx}"] = (
            f'=IF(TRIM(${tip_cham_col}{row_idx})="", FALSE, '
            f'OR(ISNUMBER(SEARCH(":",${tip_cham_col}{row_idx})),'
            f'ISNUMBER(SEARCH(";",${tip_cham_col}{row_idx})),'
            f'ISNUMBER(SEARCH(",",${tip_cham_col}{row_idx})),'
            f'LEN(TRIM(${tip_cham_col}{row_idx}))>1))'
        )

    # helper 컬럼 숨김
    for col in ["AA", "AB", "AC", "AD"]:
        ws.column_dimensions[col].hidden = True

    # -------------------------------------------------
    # 조건부서식
    # -------------------------------------------------

    # 1) 호환계획 중복 경고 (BODY만 있어도 key 생성되므로 잡힘)
    ws.conditional_formatting.add(
        f"{plan_body_col}2:{plan_cham_col}5000",
        FormulaRule(
            formula=['=AND($AA2<>"",COUNTIF($AA:$AA,$AA2)>1)'],
            fill=red_fill,
        ),
    )

    # 2) TIP미등록 중복 경고
    ws.conditional_formatting.add(
        f"{tip_body_col}2:{tip_cham_col}5000",
        FormulaRule(
            formula=['=AND($AB2<>"",COUNTIF($AB:$AB,$AB2)>1)'],
            fill=red_fill,
        ),
    )

    # 3) STEPSEQ 소문자 경고
    ws.conditional_formatting.add(
        f"{step_col}2:{step_col}5000",
        FormulaRule(
            formula=[f'=AND(${step_col}2<>"",EXACT(${step_col}2,UPPER(${step_col}2))=FALSE)'],
            fill=red_fill,
        ),
    )

    # 4) 호환EQPCHAM명 다중입력/1글자초과 경고
    ws.conditional_formatting.add(
        f"{plan_cham_col}2:{plan_cham_col}5000",
        FormulaRule(
            formula=['=$AC2=TRUE'],
            fill=red_fill,
        ),
    )

    # 5) 미등록TIP호환Path_호환EQPCHAM명 다중입력/1글자초과 경고
    ws.conditional_formatting.add(
        f"{tip_cham_col}2:{tip_cham_col}5000",
        FormulaRule(
            formula=['=$AD2=TRUE'],
            fill=red_fill,
        ),
    )

    guide_ws = wb.create_sheet("작성 참고")
    guide_ws["A1"] = "FACTS 엑셀 업로드 작성 참고"
    guide_ws["A1"].font = Font(bold=True, size=13)

    guide_rows = [
        "1. 업로드는 FACTS_UPLOAD_TEMPLATE 시트만 읽습니다.",
        "2. 동일 파일 내에서 같은 설비가 중복되면 행번호가 더 작은 행만 반영됩니다.",
        "3. ACTION은 UPSERT/DELETE 중 선택합니다. 기본값은 UPSERT입니다.",
        "4. *_ID 값이 있으면 ID 기준으로 수정/삭제하고, 없으면 자연키(line/process/step/body/cham) 기준으로 처리합니다.",
        "5. 같은 설비가 기존 DB에 이미 있으면 새 업로드 값으로 덮어씌웁니다.",
        "6. LINE컬럼은 필수입니다.",
        "7. 중복 경고 기준",
        "   - 호환계획: PROCESSID + STEPSEQ + 호환계획_호환EQPBODY명 + 호환계획_호환EQPCHAM명",
        "   - TIP미등록: PROCESSID + STEPSEQ + 미등록TIP호환Path_호환EQPBODY명 + 미등록TIP호환Path_호환EQPCHAM명",
        "8. CHAM명은 비어 있을 수 있으며, 비어 있어도 BODY 기준으로 중복 경고가 동작합니다.",
        "9. PROCESSID, STEPSEQ, 호환계획_호환EQPBODY명, 호환계획_호환EQPCHAM명, 호환계획_평가LotID, 미등록TIP호환Path_호환EQPBODY명, 미등록TIP호환Path_호환EQPCHAM명은 업로드 시 서버에서 영문자를 무조건 대문자로 변환합니다.",
        "10. 하나의 행에는 하나의 CHAM단위까지만 기입 가능합니다. 하나 이상의 CHAM 기입(예시: 3:4, 3;4, 3,4 등) 된 행은 업데이트가 안됩니다.",
        "11. 호환계획_호환EQPCHAM명, 미등록TIP호환Path_호환EQPCHAM명 컬럼에 다중 CHAM 형식 또는 1글자 초과가 입력되면 빨간색 warning으로 표시됩니다.",
        "12. STEPSEQ에 소문자가 입력되면 빨간색 warning으로 표시됩니다.",
    ]

    for idx, text in enumerate(guide_rows, start=3):
        guide_ws[f"A{idx}"] = text

    guide_ws.column_dimensions["A"].width = 140

    wb.calculation.calcMode = "auto"
    wb.calculation.fullCalcOnLoad = True
    wb.calculation.forceFullCalc = True
    
    output = io.BytesIO()
    wb.save(output)
    output.seek(0)

    response = HttpResponse(
        output.read(),
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
    response["Content-Disposition"] = 'attachment; filename="facts_upload_template.xlsx"'
    return response

@require_GET
@login_required
def prp_export_csv(request):
    _ensure_browser_close_session(request)
    permission_response = _check_page_permission(request, "dashboard", ignore_blank_scope=True)
    if permission_response is not None:
        return permission_response

    prp_f = _get_prp_common_filters(request)
    prp_filters = _get_prp_request_filters(request)

    is_valid, msg = _validate_prp_filters(prp_filters)
    if not is_valid:
        return HttpResponse(msg, content_type="text/plain; charset=utf-8", status=400)

    prp_base_rows = _get_prp_base_rows(prp_f, prp_filters)
    prp_rows = _extract_prp_rows(prp_base_rows, source="prp_export_csv")
    step_rows = _apply_prp_filters(prp_rows, prp_filters)
    csv_text = services.export_prp_csv(step_rows)
    written_row_count = len(step_rows)
    written_counts_by_processid = {}
    for row in step_rows:
        processid = str((row or {}).get("processid") or "").strip()
        if not processid:
            continue
        written_counts_by_processid[processid] = written_counts_by_processid.get(processid, 0) + 1
    response = HttpResponse(csv_text, content_type="text/csv; charset=utf-8-sig")
    response["Content-Disposition"] = 'attachment; filename="facts_prp_table_filtered.csv"'
    return response

@require_GET
@login_required
def prp_export_csv_all(request):
    _ensure_browser_close_session(request)
    permission_response = _check_page_permission(request, "dashboard", ignore_blank_scope=True)
    if permission_response is not None:
        return permission_response

    prp_f = _get_prp_common_filters(request)
    prp_filters = _get_prp_request_filters(request)
    prp_lineid = (prp_filters.get("prp_lineid") or "").strip()
    raw_get_prp_processid = request.GET.get("prp_processid")
    raw_getlist_prp_processid = request.GET.getlist("prp_processid")

    selected_prps = []
    seen_prps = set()
    for raw_value in raw_getlist_prp_processid:
        for part in str(raw_value or "").split(","):
            norm = part.strip()
            if norm and norm not in seen_prps:
                selected_prps.append(norm)
                seen_prps.add(norm)

    prp_processid = (prp_filters.get("prp_processid") or "").strip()
    if prp_processid and prp_processid not in seen_prps:
        selected_prps.append(prp_processid)
        seen_prps.add(prp_processid)

    if not prp_lineid:
        return HttpResponse("LINE과 PRP를 선택한 뒤 조회 후 다운로드하세요.", content_type="text/plain; charset=utf-8", status=400)
    if not selected_prps:
        return HttpResponse("PRP조건은 필수입니다.", content_type="text/plain; charset=utf-8", status=400)
    if len(selected_prps) > 20:
        return HttpResponse("선택 PRP 다운로드는 최대 20개까지 가능합니다.", content_type="text/plain; charset=utf-8", status=400)

    selected_set = {str(v or "").strip() for v in selected_prps if str(v or "").strip()}
    prp_snap_date = prp_f.get("snap_date")
    prp_area = (prp_filters.get("prp_areaname") or "").strip() or None
    prp_layer = (prp_filters.get("prp_layerid") or "").strip() or None

    merged_rows = []
    dedupe_seen = set()
    per_prp_build_kwargs = []
    per_prp_row_count_before_filter = {}

    for prp_code in selected_prps:
        dataset_kwargs = {
            "snap_date": prp_snap_date,
            "lineid": prp_lineid or None,
            "processid": prp_code,
            "areaname": prp_area,
            "layerid": prp_layer,
            "include_measure": prp_f["include_measure"],
            "include_emergency": prp_f["include_emergency"],
            "exclude_skiprule_100": prp_f["exclude_skiprule_100"],
            "tip_mode": prp_f["tip_mode"],
            "for_prp_table": True,
        }
        per_prp_build_kwargs.append(dict(dataset_kwargs))
        rows_for_prp = _extract_prp_rows(
            services.build_step_dataset(**dataset_kwargs),
            source=f"prp_export_csv_all:{prp_code}",
        )
        per_prp_row_count_before_filter[prp_code] = len(rows_for_prp)

        for row in rows_for_prp:
            if not isinstance(row, dict):
                continue
            row_key = (
                str(row.get("lineid") or "").strip(),
                str(row.get("processid") or "").strip(),
                str(row.get("stepseq") or "").strip(),
                str(row.get("recipeid") or "").strip(),
                str(row.get("areaname") or "").strip(),
                str(row.get("layerid") or "").strip(),
            )
            if row_key in dedupe_seen:
                continue
            dedupe_seen.add(row_key)
            merged_rows.append(row)

    rows_before_prp_filter = len(merged_rows)
    step_rows = [
        r for r in merged_rows
        if isinstance(r, dict) and (str(r.get("processid") or "").strip() in selected_set)
    ]
    rows_after_prp_filter = len(step_rows)
    selected_counts = {
        prp_code: sum(1 for row in step_rows if isinstance(row, dict) and str(row.get("processid") or "").strip() == prp_code)
        for prp_code in selected_prps
    }
    debug_payload = {
        "raw_get_prp_processid": raw_get_prp_processid,
        "raw_getlist_prp_processid": raw_getlist_prp_processid,
        "selected_prps": selected_prps,
        "selected_set": sorted(selected_set),
        "per_prp_build_kwargs": per_prp_build_kwargs,
        "per_prp_row_count_before_filter": per_prp_row_count_before_filter,
        "merged_rows_count": rows_before_prp_filter,
        "rows_after_prp_filter": rows_after_prp_filter,
        "selected_counts": selected_counts,
    }
    logger.warning(
        "[PRP_EXPORT_ALL] raw_get_prp_processid=%s raw_getlist_prp_processid=%s selected_prps=%s selected_set=%s per_prp_build_kwargs=%s per_prp_row_count_before_filter=%s merged_rows_count=%s rows_after_prp_filter=%s selected_counts=%s",
        raw_get_prp_processid,
        raw_getlist_prp_processid,
        selected_prps,
        sorted(selected_set),
        per_prp_build_kwargs,
        per_prp_row_count_before_filter,
        rows_before_prp_filter,
        rows_after_prp_filter,
        selected_counts,
    )
    csv_text = services.export_prp_csv(step_rows)
    written_row_count = len(step_rows)
    written_counts_by_processid = {}
    for row in step_rows:
        processid = str((row or {}).get("processid") or "").strip()
        if not processid:
            continue
        written_counts_by_processid[processid] = written_counts_by_processid.get(processid, 0) + 1
    debug_payload["written_row_count"] = written_row_count
    debug_payload["written_counts_by_processid"] = written_counts_by_processid
    mismatch_processids = [
        prp_code
        for prp_code in selected_prps
        if int(selected_counts.get(prp_code) or 0) != int(written_counts_by_processid.get(prp_code) or 0)
    ]
    if mismatch_processids:
        logger.warning(
            "[PRP_EXPORT_ALL] selected_counts/written_counts mismatch processids=%s selected_counts=%s written_counts_by_processid=%s",
            mismatch_processids,
            selected_counts,
            written_counts_by_processid,
        )
    logger.warning("[PRP_EXPORT_DEBUG] %s", debug_payload)
    print(f"[PRP_EXPORT_DEBUG] {debug_payload}")
    debug_text = "\n".join([
        f"selected_prps={selected_prps}",
        f"selected_set={sorted(selected_set)}",
        f"per_prp_build_kwargs={per_prp_build_kwargs}",
        f"per_prp_row_count_before_filter={per_prp_row_count_before_filter}",
        f"merged_rows_count={rows_before_prp_filter}",
        f"rows_after_prp_filter={rows_after_prp_filter}",
        f"selected_counts={selected_counts}",
        f"written_row_count={written_row_count}",
        f"written_counts_by_processid={written_counts_by_processid}",
    ])
    try_save_feedback_log(
        f"prp_export_debug_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
        debug_text,
        "PRP_EXPORT_DEBUG",
    )
    response = HttpResponse(csv_text, content_type="text/csv; charset=utf-8-sig")
    snap_text = (prp_f.get("snap_date").strftime("%Y%m%d") if hasattr(prp_f.get("snap_date"), "strftime") else "unknown")
    if len(selected_prps) == 1:
        response["Content-Disposition"] = f'attachment; filename="facts_prp_table_all_{selected_prps[0]}.csv"'
    else:
        response["Content-Disposition"] = f'attachment; filename="FACTS_PRP_SELECTED_{snap_text}_{len(selected_prps)}PRP.csv"'
    return response

@require_GET
@login_required
def dashboard_prp_options_api(request):
    _ensure_browser_close_session(request)
    permission_response = _check_page_permission(request, "dashboard", ignore_blank_scope=True)
    if permission_response is not None:
        return permission_response

    prp_f = _get_prp_common_filters(request)
    prp_filters = _get_prp_request_filters(request)

    payload = services.get_prp_filter_options_from_option_cache(
        prp_filters=prp_filters,
        fallback_snap_date=prp_f["snap_date"],
    )
    required_keys = [
        "line_options",
        "prp_options",
        "area_options",
        "layer_options",
        "table_line_options",
        "table_prp_options",
        "table_area_options",
        "table_layer_options",
        "table_step_options",
        "table_descript_options",
        "table_recipe_options",
        "table_type_options",
        "table_body_options",
        "table_cham_options",
        "table_compat_options",
        "table_always_options",
        "table_major_options",
        "table_plan_options",
    ]
    for key in required_keys:
        payload.setdefault(key, [])
    payload["line_options"] = payload.get("line_options") or payload.get("table_line_options") or []
    payload["prp_options"] = payload.get("prp_options") or payload.get("table_prp_options") or []
    payload["area_options"] = payload.get("area_options") or payload.get("table_area_options") or []
    payload["layer_options"] = payload.get("layer_options") or payload.get("table_layer_options") or []
    payload["ok"] = True
    return JsonResponse(payload)

@require_GET
@login_required
def dashboard_filter_options_api(request):
    _ensure_browser_close_session(request)
    permission_response = _check_page_permission(request, "dashboard", ignore_blank_scope=True)
    if permission_response is not None:
        return permission_response

    f = _get_dashboard_common_filters(request)
    payload = services.get_dashboard_filter_options_from_option_cache(
        snap_date=f["snap_date"],
        lineid=f["lineid"],
        processid=f["processid"],
        areaname=f["areaname"],
        layer_values=f["layerid"],
    )
    payload["ok"] = True
    return JsonResponse(payload)
