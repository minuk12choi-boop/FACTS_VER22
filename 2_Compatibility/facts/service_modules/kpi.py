
    labels.extend(["", ""])
    total_values.extend([None, None])
    body_values.extend([None, None])
    cham_values.extend([None, None])
    target_values.extend([None, None])

    for d in daily_dates:
        labels.append(f"{d.month}/{d.day}")
        s, missing = _aggregate_metrics([d])
        missing_dates.extend(missing)
        total_values.append(s["compat_rate"] if s else None)
        body_values.append(s["body_rate"] if s else None)
        cham_values.append(s["cham_rate_cum"] if s else None)
        target_values.append(round(float(target_monthly), 1) if target_monthly is not None else None)

    missing_sorted = sorted({d for d in missing_dates})
    metric_dates = sorted(prefetched_by_date.keys()) if prefetched_by_date else []
    ignored = [d for d in missing_sorted if metric_dates and d < metric_dates[0]]
    missing_in_range = [d for d in missing_sorted if d not in ignored]
    result = {
        "labels": labels,
        "total_values": total_values,
        "body_values": body_values,
        "cham_values": cham_values,
        "target_values": target_values,
        "missing_dates": [d.isoformat() for d in missing_in_range],
        "rows_read": rows_read,
        "needed_date_min": all_needed_dates[0].isoformat() if all_needed_dates else "",
        "needed_date_max": all_needed_dates[-1].isoformat() if all_needed_dates else "",
        "needed_date_count": len(all_needed_dates),
        "metric_date_min": metric_dates[0].isoformat() if metric_dates else "",
        "metric_date_max": metric_dates[-1].isoformat() if metric_dates else "",
        "missing_dates_count": len(missing_in_range),
        "ignored_out_of_range_dates_count": len(ignored),
        "missing_dates_head": [d.isoformat() for d in missing_in_range[:5]],
        "missing_dates_tail": [d.isoformat() for d in missing_in_range[-5:]],
        "timing_metric_query": time.perf_counter() - t_metric,
        "timing_series_build": time.perf_counter() - t_series,
    }
    logger.info("[DASHBOARD_TIMING] series_build=%.4fs", time.perf_counter() - t_series)
    return result


def rebuild_metric_daily_for_snap_date(snap_date, force_rebuild=False, lineid=None, processid=None, condition_key=None, debug_scope=False):
    snap_date = _as_of_date(snap_date) or snap_date
    from facts.models import FactsDashboardMetricDaily

    lineid_filter = (lineid or "").strip()
    processid_filter = (processid or "").strip()
    condition_key_filter = (condition_key or "").strip()

    if force_rebuild:
        delete_qs = FactsDashboardMetricDaily.objects.filter(snap_date=snap_date)
        if lineid_filter:
            delete_qs = delete_qs.filter(lineid=lineid_filter)
        if processid_filter:
            delete_qs = delete_qs.filter(processid=processid_filter)
        if condition_key_filter:
            delete_qs = delete_qs.filter(condition_key=condition_key_filter)
        delete_qs.delete()

    built = 0
    skipped = 0
    skipped_invalid_scopes = 0
    skipped_aggregate_scopes = 0
    built_atomic_scopes = 0

    atomic_scope_set = set()
    for include_measure in (True, False):
        for include_emergency in (True, False):
            for exclude_skip in (False, True):
                for tip_mode in (False, True):
                    grouped = build_grouped_metric_rows_for_condition(
                        snap_date=snap_date,
                        include_measure=include_measure,
                        include_emergency=include_emergency,
                        exclude_skiprule_100=exclude_skip,
                        tip_mode=tip_mode,
                    )
                    filtered_scope_keys = []
                    for lineid_val, processid_val, areaname_val, layer_val in grouped.keys():
                        if lineid_filter and lineid_val != lineid_filter:
                            continue
                        if processid_filter and processid_val != processid_filter:
                            continue
                        filtered_scope_keys.append((lineid_val, processid_val, areaname_val, layer_val))

                    atomic_scope_set.update(filtered_scope_keys)

                    for lineid_val, processid_val, areaname_val, layer_val in sorted(filtered_scope_keys):
                        common = {
                            "processid": processid_val,
                            "areaname": areaname_val,
                            "layerid": [layer_val] if layer_val else [],
                            "lineid": lineid_val,
                            "include_measure": include_measure,
                            "include_emergency": include_emergency,
                            "exclude_skiprule_100": exclude_skip,
                            "tip_mode": tip_mode,
                        }
                        layer_values = [normalize_layer_value(x) for x in (common.get("layerid") or []) if normalize_layer_value(x)]
                        layer_key = ",".join(sorted(set(layer_values)))
                        scope_hash = _scope_hash(common.get("lineid"), common.get("processid"), common.get("areaname"), layer_key)
                        cond = _condition_key(include_measure, include_emergency, exclude_skip, tip_mode)
                        if condition_key_filter and cond != condition_key_filter:
                            continue
                        exists = FactsDashboardMetricDaily.objects.filter(
                            snap_date=snap_date,
                            scope_hash=scope_hash,
                            condition_key=cond,
                            include_measure=include_measure,
                            include_emergency=include_emergency,
                            exclude_skiprule_100=exclude_skip,
                            tip_mode=tip_mode,
                            metric_type="compat",
                        ).exists()
                        if exists and not force_rebuild:
                            skipped += 1
                            continue
                        row = _build_or_get_daily_metric(snap_date, common, grouped_rows_by_scope=grouped, debug_scope=debug_scope)
                        if row is None:
                            skipped_invalid_scopes += 1
                            continue
                        built += 1

    built_atomic_scopes = len(atomic_scope_set)

    return {
        "built": built,
        "skipped": skipped,
        "scope_count": len(atomic_scope_set),
        "skipped_invalid_scopes": skipped_invalid_scopes,
        "skipped_aggregate_scopes": skipped_aggregate_scopes,
        "built_atomic_scopes": built_atomic_scopes,
    }

def export_prp_csv(step_rows):
    output = StringIO()
    writer = csv.writer(output)

    writer.writerow([
        "기준일",
        "LINE",
        "PRP",
        "AREA",
        "LAYER",
        "STEP",
        "SKIPRULE",
        "DESCRIPT",
        "RECIPE",
        "EQPGROUP",
        "CHAM정보",
        "TYPE",
        "BODY호환",
        "CHAM호환",
        "BODY수",
        "CHAM수",
        "호환구분",
        "호환확보",
        "상시여부",
        "주요여부",
        "호환계획여부",
        "계획_호환EQPBODY명",
        "계획_호환EQPCHAM명",
        "계획_호환완료계획일",
        "계획_평가LotID",
        "계획_평가단계",
        "계획_비고",
        "TIP미등록 호환Path 여부",
        "미등록TIP호환Path_상시/비상시",
        "미등록TIP호환Path_주요/비주요",
        "미등록TIP호환Path_호환EQPBODY명",
        "미등록TIP호환Path_호환EQPCHAM명",
        "호환구분_TIP고려",
        "호환확보_TIP고려",
        "BODY호환_TIP고려",
        "CHAM호환_TIP고려",
        "BODY호환확보수_TIP고려",
        "CHAM호환확보수_TIP고려",
        "TIP",
        "CHILDEQP",
    ])

    for row in step_rows:
        writer.writerow([
            row["snap_date"],
            row["lineid"],
            row["processid"],
            row["areaname"],
            row["layerid"],
            row["stepseq"],
            row["skiprule"],
            row["descript"],
            row["recipeid"],
            row["eqpgroup"],
            row["cham_display"],
            row["stepseq_type"],
            row["body_compat_flag"],
            row["cham_compat_flag"],
            row["body_path_count"],
            row["cham_path_count"],
            row["compat_type_base"],
            "Y" if (row["body_compat_flag"] == "Y" or row["cham_compat_flag"] == "Y") else "N",
            "Y" if row["has_always"] else "N",
            "Y" if row["has_major"] else "N",
            "Y" if row["has_plan"] else "N",
            row["plan_body_names"],
            row["plan_cham_names"],
            row["plan_due_dates"],
            row["plan_eval_lot_ids"],
            row["plan_eval_stages"],
            row["plan_memos"],
            row["tip_missing_flag"],
            row["tip_missing_always"],
            row["tip_missing_major"],
            row["tip_missing_body"],
            row["tip_missing_cham"],
            row["compat_type_tip"],
            "Y" if (row["body_compat_tip"] == "Y" or row["cham_compat_tip"] == "Y") else "N",
            row["body_compat_tip"],
            row["cham_compat_tip"],
            row["body_compat_count_tip"],
            row["cham_compat_count_tip"],
            row["tip"],
            row["childeqp"],
        ])

    return output.getvalue()


def get_history_week_options(lineid="", processid=""):
    def _collect_dates(qs, field_name):
        return {
            d
            for d in qs.exclude(**{f"{field_name}__isnull": True}).values_list(field_name, flat=True).distinct()
            if d
        }

    summary_qs = FactsHistorySummaryCache.objects.all()
    wip_qs = FactsWipSource.objects.all()
    edit_qs = FactsEditHistory.objects.all()

    if lineid:
        summary_qs = summary_qs.filter(lineid=lineid)
        wip_qs = wip_qs.filter(lineid=lineid)
        edit_qs = edit_qs.filter(lineid=lineid)
    if processid:
        summary_qs = summary_qs.filter(processid=processid)
        wip_qs = wip_qs.filter(processid=processid)
        edit_qs = edit_qs.filter(processid=processid)

    dates = _collect_dates(summary_qs, "summary_date")
    if not dates:
        dates = _collect_dates(wip_qs, "snap_date")

    if not dates:
        dates = _collect_dates(edit_qs, "snap_date")

    week_set = {f"W{d.isocalendar()[1]:02d}" for d in dates}
    return sorted(week_set)
