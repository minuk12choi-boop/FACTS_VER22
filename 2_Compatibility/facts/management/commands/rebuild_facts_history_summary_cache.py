from datetime import datetime, timedelta

from django.core.management.base import BaseCommand
from django.db.utils import OperationalError, ProgrammingError

from facts.models import FactsEditHistory, FactsHistorySummaryCache, FactsWipSource
from facts.view_modules.history import _get_history_card_cached


class Command(BaseCommand):
    help = "Rebuild FACTS history summary cache table"

    def add_arguments(self, parser):
        parser.add_argument("--snap-date", type=str, default="", help="YYYY-MM-DD")
        parser.add_argument("--days", type=int, default=7)
        parser.add_argument("--all-existing", action="store_true", help="모든 기존 snap_date 백필")
        parser.add_argument("--continue-on-error", action="store_true", help="개별 날짜 실패 시 계속 진행")
        parser.add_argument("--lineid", type=str, default="")
        parser.add_argument("--processid", type=str, default="")
        parser.add_argument("--force-rebuild", action="store_true")

    def _resolve_dates(self, snap_date_raw, all_existing, days):
        if snap_date_raw:
            return [datetime.strptime(snap_date_raw, "%Y-%m-%d").date()]
        if all_existing:
            try:
                dates = list(FactsWipSource.objects.values_list("snap_date", flat=True).distinct().order_by("snap_date"))
                return [d for d in dates if d]
            except (OperationalError, ProgrammingError):
                return []
        from datetime import date
        base_date = date.today()
        return [base_date - timedelta(days=i) for i in range(max(days, 1))]

    def _scope_pairs_for_date(self, target_date, lineid_filter="", processid_filter=""):
        try:
            pairs = {
                (
                    (lineid or "").strip(),
                    (processid or "").strip(),
                )
                for lineid, processid in FactsEditHistory.objects.filter(snap_date=target_date)
                .values_list("lineid", "processid")
                .distinct()
            }
        except (OperationalError, ProgrammingError):
            pairs = set()
        if lineid_filter:
            pairs = {item for item in pairs if item[0] == lineid_filter}
        if processid_filter:
            pairs = {item for item in pairs if item[1] == processid_filter}
        if not lineid_filter and not processid_filter:
            pairs.add(("", ""))
        return sorted(pairs)

    def handle(self, *args, **options):
        snap_date_raw = (options.get("snap_date") or "").strip()
        days = int(options.get("days") or 7)
        all_existing = bool(options.get("all_existing"))
        continue_on_error = bool(options.get("continue_on_error"))
        lineid_filter = (options.get("lineid") or "").strip()
        processid_filter = (options.get("processid") or "").strip()
        force_rebuild = bool(options.get("force_rebuild"))
        if snap_date_raw and all_existing:
            self.stdout.write(self.style.WARNING("--snap-date 와 --all-existing 동시 사용 시 --snap-date 우선"))
            all_existing = False

        target_dates = self._resolve_dates(snap_date_raw=snap_date_raw, all_existing=all_existing, days=days)
        if not target_dates:
            self.stdout.write(self.style.WARNING("대상 snap_date가 없어 이력 캐시 재빌드를 건너뜁니다."))
            return
        self.stdout.write(f"[HISTORY] total_snap_dates={len(target_dates)}")
        self.stdout.write(f"[HISTORY] snap_dates={','.join(str(d) for d in target_dates)}")
        self.stdout.write(f"[HISTORY] lineid={lineid_filter or '*'} processid={processid_filter or '*'} force_rebuild={force_rebuild}")
        total_before = FactsHistorySummaryCache.objects.count()
        built = 0
        total = len(target_dates)
        for idx, d in enumerate(target_dates, start=1):
            rows_before = FactsHistorySummaryCache.objects.filter(summary_date=d).count()
            source_count = FactsEditHistory.objects.filter(snap_date=d).count()
            self.stdout.write(f"[HISTORY] {idx}/{total} snap_date={d} start rows_before={rows_before} source_count={source_count}")
            if force_rebuild:
                delete_qs = FactsHistorySummaryCache.objects.filter(summary_date=d)
                if lineid_filter:
                    delete_qs = delete_qs.filter(lineid=lineid_filter)
                if processid_filter:
                    delete_qs = delete_qs.filter(processid=processid_filter)
                delete_qs.delete()
            try:
                for lineid, processid in self._scope_pairs_for_date(d, lineid_filter=lineid_filter, processid_filter=processid_filter):
                    for include_measure in (True, False):
                        for include_emergency in (True, False):
                            for exclude_skiprule_100 in (False, True):
                                _get_history_card_cached(d, lineid, processid, include_measure, include_emergency, exclude_skiprule_100)
                                built += 1
                rows_after = FactsHistorySummaryCache.objects.filter(summary_date=d).count()
                self.stdout.write(
                    f"[HISTORY] {idx}/{total} snap_date={d} done rows_before={rows_before} rows_after={rows_after} source_count={source_count}"
                )
            except Exception as exc:
                self.stderr.write(self.style.ERROR(f"[HISTORY] {idx}/{total} snap_date={d} failed: {exc}"))
                if continue_on_error:
                    continue
                raise
        total_after = FactsHistorySummaryCache.objects.count()
        self.stdout.write(f"[HISTORY] total_rows_before={total_before} total_rows_after={total_after}")
        self.stdout.write(self.style.SUCCESS(f"done. built {built} history cache rows"))
