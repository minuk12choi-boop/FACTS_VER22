from collections import Counter
from datetime import datetime

from django.core.management.base import BaseCommand

from facts.models import FactsDashboardMetricDaily
from facts import services


class Command(BaseCommand):
    help = "Debug dashboard metric consistency against PRP table basis"

    def add_arguments(self, parser):
        parser.add_argument("--snap-date", required=True)
        parser.add_argument("--lineid", required=True)
        parser.add_argument("--processid", required=True)
        parser.add_argument("--condition-key", default="m1:e1:s1:t0")

    def handle(self, *args, **options):
        snap_date = datetime.strptime(options["snap_date"], "%Y-%m-%d").date()
        lineid = options["lineid"].strip()
        processid = options["processid"].strip()
        condition = options["condition_key"].strip()

        flags = {p[0]: (p[-1] == "1") for p in condition.split(":") if p}
        include_measure = flags.get("m", True)
        include_emergency = flags.get("e", True)
        exclude_skip = flags.get("s", False)
        tip_mode = flags.get("t", False)

        grouped = services.build_grouped_metric_rows_for_condition(
            snap_date=snap_date,
            include_measure=include_measure,
            include_emergency=include_emergency,
            exclude_skiprule_100=exclude_skip,
            tip_mode=tip_mode,
        )
        rows = []
        for (lval, pval, _area, _layer), scoped_rows in grouped.items():
            if lval == lineid and pval == processid:
                rows.extend(scoped_rows)

        base_dist = Counter((r.get("compat_type_base") or "") for r in rows)
        tip_dist = Counter((r.get("compat_type_tip") or "") for r in rows)
        export_base_dist = Counter((services.get_prp_export_compat_label(r) or "") for r in rows)
        export_tip_dist = Counter((services.get_prp_export_tip_compat_label(r) or "") for r in rows)
        summary = services.summarize_metric_rows_for_condition(rows, tip_mode=tip_mode)
        expected_compat_key = "compat_type_tip" if tip_mode else "compat_type_base"

        metric = FactsDashboardMetricDaily.objects.filter(
            snap_date=snap_date,
            lineid=lineid,
            processid=processid,
            condition_key=condition,
            include_measure=include_measure,
            include_emergency=include_emergency,
            exclude_skiprule_100=exclude_skip,
            tip_mode=tip_mode,
            metric_type="compat",
        )
        metric_total = sum(int(x.total_steps or 0) for x in metric)
        metric_body = sum(int(x.body_cnt or 0) for x in metric)
        metric_cham = sum(int(x.cham_cnt or 0) for x in metric)
        metric_single = sum(int(x.single_cnt or 0) for x in metric)
        metric_compatible = sum(int(x.compatible_steps or 0) for x in metric)
        metric_rate = round((metric_compatible / metric_total) * 100, 1) if metric_total else 0.0

        graph = services.get_dashboard_combined_series(
            snap_date=snap_date,
            processid=processid,
            areaname=None,
            layerid=None,
            lineid=lineid,
            include_measure=include_measure,
            include_emergency=include_emergency,
            exclude_skiprule_100=exclude_skip,
            tip_mode=tip_mode,
            target_monthly=None,
        )
        day_value = (graph.get("total_values") or [None])[-1]

        self.stdout.write(f"CONDITION {condition}")
        self.stdout.write(f"EXPORT_ROWS count={len(rows)}")
        self.stdout.write(f"BASE_COMPAT distribution={dict(base_dist)}")
        self.stdout.write(f"TIP_COMPAT distribution={dict(tip_dist)}")
        self.stdout.write(f"BASE_TIP_EQUAL rows={sum(1 for r in rows if (r.get('compat_type_base') or '') == (r.get('compat_type_tip') or ''))}")
        if tip_mode and base_dist == tip_dist:
            self.stdout.write("WARNING t1에서 BASE_COMPAT과 TIP_COMPAT 분포가 동일합니다. compat_type_tip 생성 로직을 확인하세요.")
        self.stdout.write(f"EXPORT_BASE_COMPAT distribution={dict(export_base_dist)}")
        self.stdout.write(f"EXPORT_TIP_COMPAT distribution={dict(export_tip_dist)}")
        expected_metric = round((summary['compatible_steps'] / summary['total_steps']) * 100, 1) if summary['total_steps'] else 0.0
        self.stdout.write(f"SUMMARY total={summary['total_steps']} body={summary['body_cnt']} cham={summary['cham_cnt']} single={summary['single_cnt']} missing={summary.get('unregistered_cnt', 0)} compatible={summary['compatible_steps']} metric={expected_metric}")
        self.stdout.write(f"METRIC total={metric_total} body={metric_body} cham={metric_cham} single={metric_single} compatible={metric_compatible} metric={metric_rate}")
        self.stdout.write(f"METRIC_COMPARE expected_metric={expected_metric} stored_metric={metric_rate}")
        self.stdout.write(f"GRAPH day_value={day_value}")
        ok = (
            summary['total_steps'] == metric_total
            and summary['body_cnt'] == metric_body
            and summary['cham_cnt'] == metric_cham
            and summary['single_cnt'] == metric_single
            and summary['compatible_steps'] == metric_compatible
            and expected_metric == metric_rate
        )
        diff_rows = []
        base_tip_diff_rows = []
        metric_compat_for_condition = expected_compat_key
        metric_dist = Counter((row.get(metric_compat_for_condition) or "") for row in rows)
        self.stdout.write(f"METRIC_COMPAT_FOR_CONDITION key={metric_compat_for_condition} distribution={dict(metric_dist)}")
        for row in rows:
            export_base_compat = services.get_prp_export_compat_label(row)
            export_tip_compat = row.get("compat_type_tip")
            metric_compat = row.get(metric_compat_for_condition)
            if (export_base_compat or "") != (row.get("compat_type_base") or ""):
                diff_rows.append({
                    "lineid": row.get("lineid"),
                    "processid": row.get("processid"),
                    "areaname": row.get("areaname"),
                    "layer_key": services.normalize_layer_value(row.get("layerid") or ""),
                    "layerid": row.get("layerid"),
                    "stepseq": row.get("stepseq"),
                    "recipeid": row.get("recipeid"),
                    "eqpgroup": row.get("eqpgroup"),
                    "cham_info": row.get("cham_display"),
                    "export_base_compat": export_base_compat,
                    "export_tip_compat": export_tip_compat,
                    "metric_compat_for_condition": metric_compat,
                    "compat_type": row.get("compat_type"),
                    "compat_type_base": row.get("compat_type_base"),
                    "compat_type_tip": row.get("compat_type_tip"),
                    "body_compat_flag": row.get("body_compat_flag"),
                    "cham_compat_flag": row.get("cham_compat_flag"),
                    "body_path_count": row.get("body_path_count"),
                    "cham_path_count": row.get("cham_path_count"),
                })
            if (row.get("compat_type_base") or "") != (row.get("compat_type_tip") or ""):
                base_tip_diff_rows.append({
                    "lineid": row.get("lineid"),
                    "processid": row.get("processid"),
                    "areaname": row.get("areaname"),
                    "layerid": row.get("layerid"),
                    "stepseq": row.get("stepseq"),
                    "recipeid": row.get("recipeid"),
                    "compat_type": row.get("compat_type"),
                    "compat_type_base": row.get("compat_type_base"),
                    "compat_type_tip": row.get("compat_type_tip"),
                    "body_compat_flag": row.get("body_compat_flag"),
                    "cham_compat_flag": row.get("cham_compat_flag"),
                    "body_compat_tip": row.get("body_compat_tip"),
                    "cham_compat_tip": row.get("cham_compat_tip"),
                    "body_path_count": row.get("body_path_count"),
                    "cham_path_count": row.get("cham_path_count"),
                    "body_compat_count_tip": row.get("body_compat_count_tip"),
                    "cham_compat_count_tip": row.get("cham_compat_count_tip"),
                    "tip": row.get("tip"),
                    "prevent": row.get("prevent"),
                    "eventtime": row.get("eventtime"),
                })
        self.stdout.write(f"DIFF_ROWS count={len(diff_rows)} sample_limit=20")
        for idx, item in enumerate(diff_rows[:20], start=1):
            self.stdout.write(f"DIFF_SAMPLE[{idx}] {item}")
        self.stdout.write(f"BASE_TIP_DIFF_ROWS count={len(base_tip_diff_rows)} sample_limit=20")
        for idx, item in enumerate(base_tip_diff_rows[:20], start=1):
            self.stdout.write(f"BASE_TIP_DIFF_SAMPLE[{idx}] {item}")
        self.stdout.write(f"RESULT {'OK' if ok else 'DIFF'}")
