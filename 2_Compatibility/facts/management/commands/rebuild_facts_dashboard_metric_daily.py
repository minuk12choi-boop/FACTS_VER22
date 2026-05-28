from django.core.management.base import BaseCommand
from django.db.utils import OperationalError, ProgrammingError

from facts.models import FactsDashboardMetricDaily, FactsWipSource
from facts.service_modules.dashboard_rows import rebuild_metric_daily_for_snap_date


class Command(BaseCommand):
    help = "Rebuild FACTS dashboard metric daily rows"

    def add_arguments(self, parser):
        parser.add_argument("--snap-date", type=str, default="", help="YYYY-MM-DD")
        parser.add_argument("--all-existing", action="store_true")
        parser.add_argument("--force-rebuild", action="store_true")
        parser.add_argument("--lineid", type=str, default="")
        parser.add_argument("--processid", type=str, default="")
        parser.add_argument("--condition-key", type=str, default="")
        parser.add_argument("--debug-scope", action="store_true")

    def _resolve_dates(self, snap_date, all_existing):
        if snap_date:
            return [snap_date]
        if all_existing:
            try:
                dates = list(FactsWipSource.objects.values_list("snap_date", flat=True).distinct().order_by("snap_date"))
            except (OperationalError, ProgrammingError):
                return []
            return [d for d in dates if d]
        try:
            latest = FactsWipSource.objects.order_by("-snap_date").values_list("snap_date", flat=True).first()
        except (OperationalError, ProgrammingError):
            return []
        return [latest] if latest else []

    def handle(self, *args, **options):
        snap_date = (options.get("snap_date") or "").strip()
        all_existing = bool(options.get("all_existing"))
        force_rebuild = bool(options.get("force_rebuild"))
        lineid = (options.get("lineid") or "").strip()
        processid = (options.get("processid") or "").strip()
        condition_key = (options.get("condition_key") or "").strip()
        debug_scope = bool(options.get("debug_scope"))
        target_dates = self._resolve_dates(snap_date, all_existing)
        if not target_dates:
            self.stdout.write(self.style.WARNING("대상 snap_date가 없어 metric daily 재빌드를 건너뜁니다."))
            return
        total_before = FactsDashboardMetricDaily.objects.count()
        self.stdout.write(f"[METRIC] total_snap_dates={len(target_dates)}")
        self.stdout.write(f"[METRIC] force_rebuild={force_rebuild}")
        self.stdout.write(f"[METRIC] lineid={lineid or '*'} processid={processid or '*'} condition_key={condition_key or '*'}")
        self.stdout.write(f"[METRIC] debug_scope={debug_scope}")
        for idx, d in enumerate(target_dates, start=1):
            before_qs = FactsDashboardMetricDaily.objects.filter(snap_date=d)
            if lineid:
                before_qs = before_qs.filter(lineid=lineid)
            if processid:
                before_qs = before_qs.filter(processid=processid)
            if condition_key:
                before_qs = before_qs.filter(condition_key=condition_key)
            before = before_qs.count()
            result = rebuild_metric_daily_for_snap_date(
                d,
                force_rebuild=force_rebuild,
                lineid=lineid or None,
                processid=processid or None,
                condition_key=condition_key or None,
                debug_scope=debug_scope,
            )
            after_qs = FactsDashboardMetricDaily.objects.filter(snap_date=d)
            if lineid:
                after_qs = after_qs.filter(lineid=lineid)
            if processid:
                after_qs = after_qs.filter(processid=processid)
            if condition_key:
                after_qs = after_qs.filter(condition_key=condition_key)
            after = after_qs.count()
            self.stdout.write(f"[METRIC] {idx}/{len(target_dates)} snap_date={d} rows_before={before} rows_after={after} built={result['built']} skipped={result['skipped']} skipped_invalid_scopes={result.get('skipped_invalid_scopes', 0)} scopes={result['scope_count']} skipped_aggregate_scopes={result.get('skipped_aggregate_scopes', 0)} built_atomic_scopes={result.get('built_atomic_scopes', 0)}")
        total_after = FactsDashboardMetricDaily.objects.count()
        self.stdout.write(f"[METRIC] total_rows_before={total_before} total_rows_after={total_after}")
