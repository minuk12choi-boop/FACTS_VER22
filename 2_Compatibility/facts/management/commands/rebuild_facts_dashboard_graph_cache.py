from django.core.management.base import BaseCommand
from django.db.utils import OperationalError, ProgrammingError

from facts.models import FactsDashboardGraphCache, FactsFilterCache, FactsFilterOptionCache, FactsWipSource
from facts.view_modules.dashboard import _build_summary_and_chart_payload


class Command(BaseCommand):
    help = "Rebuild FACTS dashboard graph cache rows"

    def add_arguments(self, parser):
        parser.add_argument("--snap-date", type=str, default="", help="YYYY-MM-DD")
        parser.add_argument("--all-existing", action="store_true", help="모든 기존 snap_date 백필")

    def _resolve_snap_dates(self, snap_date, all_existing):
        if snap_date:
            return [snap_date]
        if all_existing:
            try:
                dates = list(
                    FactsWipSource.objects.values_list("snap_date", flat=True).distinct().order_by("snap_date")
                )
            except (OperationalError, ProgrammingError):
                return []
            return [d for d in dates if d]
        try:
            latest = FactsWipSource.objects.order_by("-snap_date").values_list("snap_date", flat=True).first()
        except (OperationalError, ProgrammingError):
            return []
        return [latest] if latest else []

    def _scopes_for_snap_date(self, snap_date):
        scopes = (
            FactsFilterOptionCache.objects.filter(cache_type="dashboard", snap_date=snap_date)
            .values("snap_date", "lineid", "processid", "areaname", "layerid")
            .distinct()
        )
        if scopes.exists():
            return scopes
        return (
            FactsFilterCache.objects.filter(snap_date=snap_date)
            .values("snap_date", "lineid", "processid", "areaname", "layerid")
            .distinct()
        )

    def handle(self, *args, **options):
        snap_date = (options.get("snap_date") or "").strip()
        all_existing = bool(options.get("all_existing"))
        if snap_date and all_existing:
            self.stdout.write(self.style.WARNING("--snap-date 와 --all-existing 동시 사용 시 --snap-date 우선"))
            all_existing = False

        target_dates = self._resolve_snap_dates(snap_date=snap_date, all_existing=all_existing)
        if not target_dates:
            self.stdout.write(self.style.WARNING("대상 snap_date가 없어 그래프 캐시 재빌드를 건너뜁니다."))
            return
        self.stdout.write(f"[GRAPH] total_snap_dates={len(target_dates)}")
        self.stdout.write(f"[GRAPH] snap_dates={','.join(str(d) for d in target_dates)}")

        total_before = FactsDashboardGraphCache.objects.count()
        count = 0
        total = len(target_dates)
        for idx, d in enumerate(target_dates, start=1):
            rows_before = FactsDashboardGraphCache.objects.filter(snap_date=d).count()
            self.stdout.write(f"[GRAPH] {idx}/{total} snap_date={d} start rows_before={rows_before}")
            scopes = self._scopes_for_snap_date(d)
            built_for_date = 0
            for scope in scopes.iterator():
                layer_values = [scope["layerid"]] if scope.get("layerid") else []
                for include_measure in (True, False):
                    for include_emergency in (True, False):
                        for exclude_skip in (False, True):
                            for tip_mode in (False, True):
                                payload = {
                                    "snap_date": scope["snap_date"],
                                    "lineid": scope.get("lineid") or "",
                                    "processid": scope.get("processid") or "",
                                    "areaname": scope.get("areaname") or "",
                                    "layerid": layer_values,
                                    "include_measure": include_measure,
                                    "include_emergency": include_emergency,
                                    "exclude_skiprule_100": exclude_skip,
                                    "tip_mode": tip_mode,
                                }
                                _build_summary_and_chart_payload(payload)
                                count += 1
                                built_for_date += 1
                                if count % 100 == 0:
                                    self.stdout.write(f"built {count} rows...")
            rows_after = FactsDashboardGraphCache.objects.filter(snap_date=d).count()
            self.stdout.write(
                f"[GRAPH] {idx}/{total} snap_date={d} done rows_before={rows_before} rows_after={rows_after} built_payloads={built_for_date}"
            )

        total_after = FactsDashboardGraphCache.objects.count()
        self.stdout.write(f"[GRAPH] total_rows_before={total_before} total_rows_after={total_after}")
        self.stdout.write(self.style.SUCCESS(f"done. built {count} scope-variant payloads"))
