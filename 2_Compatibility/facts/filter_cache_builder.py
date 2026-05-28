from collections import defaultdict
from django.db import transaction
from django.utils import timezone
from django.core.management import call_command

from .models import FactsFilterCache, FactsFilterOptionCache
from . import services
from .service_modules.dashboard_filters import _natural_sort_key, normalize_layer_value

import json


DASHBOARD_KEY_FIELDS = ("lineid", "processid", "areaname")
PRP_PRIMARY_KEY_FIELDS = ("lineid", "processid", "areaname", "layerid", "stepseq_type")
PRP_SECONDARY_KEY_FIELDS = (
    "body_flag",
    "cham_flag",
    "compat_type",
    "always_flag",
    "major_flag",
    "plan_flag",
)
PRP_ALL_KEY_FIELDS = PRP_PRIMARY_KEY_FIELDS + PRP_SECONDARY_KEY_FIELDS

OPTION_VALUE_FIELDS = ("lineid", "processid", "areaname", "layerid", "stepseq", "stepseq_type")


def _normalize_cache_text(value):
    if value is None:
        return ""
    return str(value).strip()


def _normalize_layer_text(value):
    return normalize_layer_value(value)


def _yn_from_bool(value):
    return "Y" if bool(value) else "N"


def _build_cache_rows(step_rows, snap_date):
    now_dt = timezone.now()
    cache_rows = []

    for row in step_rows:
        cache_rows.append(
            FactsFilterCache(
                snap_date=snap_date,
                lineid=_normalize_cache_text(row.get("lineid")),
                processid=_normalize_cache_text(row.get("processid")),
                areaname=_normalize_cache_text(row.get("areaname")),
                layerid=_normalize_layer_text(row.get("layerid")),
                stepseq=_normalize_cache_text(row.get("stepseq")),
                stepseq_type=_normalize_cache_text(row.get("stepseq_type")),
                descript=_normalize_cache_text(row.get("descript")),
                recipeid=_normalize_cache_text(row.get("recipeid")),
                body_flag=_normalize_cache_text(row.get("body_compat_flag")),
                cham_flag=_normalize_cache_text(row.get("cham_compat_flag")),
                compat_type=_normalize_cache_text(row.get("compat_type")),
                always_flag=_yn_from_bool(row.get("has_always")),
                major_flag=_yn_from_bool(row.get("has_major")),
                plan_flag=_normalize_cache_text(row.get("plan_flag")),
                built_at=now_dt,
                updated_at=now_dt,
            )
        )

    return cache_rows


def rebuild_filter_cache(snap_date, lineid=None, processid=None, run_post_cache_builders=True):
    step_rows = services.build_step_dataset(
        snap_date=snap_date,
        processid=processid or None,
        areaname=None,
        layerid=None,
        lineid=lineid or None,
        compat_filter="all",
        include_measure=True,
        include_emergency=True,
        exclude_skiprule_100=False,
        tip_mode=False,
        for_prp_table=True,
    )

    delete_qs = FactsFilterCache.objects.filter(snap_date=snap_date)
    if lineid:
        delete_qs = delete_qs.filter(lineid=lineid)
    if processid:
        delete_qs = delete_qs.filter(processid=processid)

    cache_rows = _build_cache_rows(step_rows, snap_date)

    with transaction.atomic():
        delete_qs.delete()
        if cache_rows:
            FactsFilterCache.objects.bulk_create(cache_rows, batch_size=1000)

    rebuild_filter_option_cache(snap_date=snap_date, cache_type="dashboard")
    rebuild_filter_option_cache(snap_date=snap_date, cache_type="prp_table")
    if run_post_cache_builders:
        try:
            call_command("rebuild_facts_dashboard_graph_cache", snap_date=str(snap_date))
            call_command("rebuild_facts_history_summary_cache", snap_date=str(snap_date), days=7)
        except Exception:
            # 그래프 캐시 테이블 미구성/초기환경에서도 필터 캐시 재빌드는 계속 진행
            pass

    return len(cache_rows)


def rebuild_filter_cache_for_scope(snap_date, lineid, processid):
    return rebuild_filter_cache(
        snap_date=snap_date,
        lineid=lineid,
        processid=processid,
    )


def rebuild_filter_cache_for_step(snap_date, lineid, processid, stepseq):
    step_rows = services.build_step_dataset(
        snap_date=snap_date,
        processid=processid or None,
        areaname=None,
        layerid=None,
        lineid=lineid or None,
        compat_filter="all",
        include_measure=True,
        include_emergency=True,
        exclude_skiprule_100=False,
        tip_mode=False,
        for_prp_table=True,
    )

    target_stepseq = _normalize_cache_text(stepseq)
    filtered_rows = [
        row for row in step_rows
        if _normalize_cache_text(row.get("stepseq")) == target_stepseq
    ]

    delete_qs = FactsFilterCache.objects.filter(
        snap_date=snap_date,
        lineid=lineid or "",
        processid=processid or "",
        stepseq=target_stepseq,
    )

    cache_rows = _build_cache_rows(filtered_rows, snap_date)

    with transaction.atomic():
        delete_qs.delete()
        if cache_rows:
            FactsFilterCache.objects.bulk_create(cache_rows, batch_size=1000)

    return len(cache_rows)


def _sorted_text_values_from_set(values):
    return sorted(v for v in values if v)


def _sorted_layer_values_from_set(values):
    normalized = {normalize_layer_value(v) for v in values if normalize_layer_value(v)}
    return sorted(normalized, key=_natural_sort_key)


def _empty_option_bucket():
    return {
        "lineid": set(),
        "processid": set(),
        "areaname": set(),
        "layerid": set(),
        "stepseq": set(),
        "stepseq_type": set(),
    }


def _normalized_cache_value_row(row):
    return {
        "lineid": _normalize_cache_text(row.get("lineid")),
        "processid": _normalize_cache_text(row.get("processid")),
        "areaname": _normalize_cache_text(row.get("areaname")),
        "layerid": _normalize_layer_text(row.get("layerid")),
        "stepseq": _normalize_cache_text(row.get("stepseq")),
        "stepseq_type": _normalize_cache_text(row.get("stepseq_type")),
        "body_flag": _normalize_cache_text(row.get("body_flag")),
        "cham_flag": _normalize_cache_text(row.get("cham_flag")),
        "compat_type": _normalize_cache_text(row.get("compat_type")),
        "always_flag": _normalize_cache_text(row.get("always_flag")),
        "major_flag": _normalize_cache_text(row.get("major_flag")),
        "plan_flag": _normalize_cache_text(row.get("plan_flag")),
    }


def _add_row_to_bucket(bucket, row):
    bucket["lineid"].add(row["lineid"])
    bucket["processid"].add(row["processid"])
    bucket["areaname"].add(row["areaname"])
    bucket["layerid"].add(row["layerid"])
    bucket["stepseq"].add(row["stepseq"])
    bucket["stepseq_type"].add(row["stepseq_type"])


def _dashboard_state_keys(row):
    values = [row[field] for field in DASHBOARD_KEY_FIELDS]

    for mask in range(1 << len(DASHBOARD_KEY_FIELDS)):
        key = []
        for idx, value in enumerate(values):
            key.append(value if (mask & (1 << idx)) else "")
        yield tuple(key)


def _prp_state_keys(row):
    values = [row[field] for field in PRP_ALL_KEY_FIELDS]
    total = len(values)

    for prefix_len in range(total + 1):
        key = []
        for idx, value in enumerate(values):
            key.append(value if idx < prefix_len else "")
        yield tuple(key)


def _load_base_cache_rows(snap_date):
    raw_rows = FactsFilterCache.objects.filter(snap_date=snap_date).values(
        "lineid",
        "processid",
        "areaname",
        "layerid",
        "stepseq",
        "stepseq_type",
        "body_flag",
        "cham_flag",
        "compat_type",
        "always_flag",
        "major_flag",
        "plan_flag",
    )
    return [_normalized_cache_value_row(row) for row in raw_rows]


def _bulk_insert_option_rows(rows):
    if not rows:
        return

    FactsFilterOptionCache.objects.bulk_create(rows, batch_size=1000)


def rebuild_filter_option_cache(snap_date, cache_type="prp_table"):
    now_dt = timezone.now()
    base_rows = _load_base_cache_rows(snap_date)

    FactsFilterOptionCache.objects.filter(
        snap_date=snap_date,
        cache_type=cache_type,
    ).delete()

    if not base_rows:
        return 0

    if cache_type == "dashboard":
        option_map = defaultdict(_empty_option_bucket)

        for row in base_rows:
            for state_key in _dashboard_state_keys(row):
                bucket = option_map[state_key]
                _add_row_to_bucket(bucket, row)

        rows = []
        for state_key, bucket in option_map.items():
            lineid, processid, areaname = state_key
            rows.append(
                FactsFilterOptionCache(
                    snap_date=snap_date,
                    cache_type="dashboard",
                    lineid=lineid,
                    processid=processid,
                    areaname=areaname,
                    line_options_json=json.dumps(
                        _sorted_text_values_from_set(bucket["lineid"]),
                        ensure_ascii=False,
                    ),
                    prp_options_json=json.dumps(
                        _sorted_text_values_from_set(bucket["processid"]),
                        ensure_ascii=False,
                    ),
                    area_options_json=json.dumps(
                        _sorted_text_values_from_set(bucket["areaname"]),
                        ensure_ascii=False,
                    ),
                    layer_options_json=json.dumps(
                        _sorted_layer_values_from_set(bucket["layerid"]),
                        ensure_ascii=False,
                    ),
                    built_at=now_dt,
                    updated_at=now_dt,
                )
            )

        _bulk_insert_option_rows(rows)
        return len(rows)

    option_map = defaultdict(_empty_option_bucket)

    for row in base_rows:
        for state_key in _prp_state_keys(row):
            bucket = option_map[state_key]
            _add_row_to_bucket(bucket, row)

    rows = []
    for state_key, bucket in option_map.items():
        (
            lineid,
            processid,
            areaname,
            layerid,
            stepseq_type,
            body_flag,
            cham_flag,
            compat_type,
            always_flag,
            major_flag,
            plan_flag,
        ) = state_key

        rows.append(
            FactsFilterOptionCache(
                snap_date=snap_date,
                cache_type="prp_table",
                lineid=lineid,
                processid=processid,
                areaname=areaname,
                layerid=layerid,
                stepseq_type=stepseq_type,
                body_flag=body_flag,
                cham_flag=cham_flag,
                compat_type=compat_type,
                always_flag=always_flag,
                major_flag=major_flag,
                plan_flag=plan_flag,
                line_options_json=json.dumps(
                    _sorted_text_values_from_set(bucket["lineid"]),
                    ensure_ascii=False,
                ),
                prp_options_json=json.dumps(
                    _sorted_text_values_from_set(bucket["processid"]),
                    ensure_ascii=False,
                ),
                area_options_json=json.dumps(
                    _sorted_text_values_from_set(bucket["areaname"]),
                    ensure_ascii=False,
                ),
                layer_options_json=json.dumps(
                    _sorted_layer_values_from_set(bucket["layerid"]),
                    ensure_ascii=False,
                ),
                step_options_json=json.dumps(
                    _sorted_text_values_from_set(bucket["stepseq"]),
                    ensure_ascii=False,
                ),
                type_options_json=json.dumps(
                    _sorted_text_values_from_set(bucket["stepseq_type"]),
                    ensure_ascii=False,
                ),
                built_at=now_dt,
                updated_at=now_dt,
            )
        )

    _bulk_insert_option_rows(rows)
    return len(rows)
