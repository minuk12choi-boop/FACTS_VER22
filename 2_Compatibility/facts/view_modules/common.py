import csv
import io
import json
import uuid

from datetime import date, datetime, timedelta
from django.core.cache import cache
from django.db.models import Q
from django.db import ProgrammingError, OperationalError
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.templatetags.static import static
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.http import require_GET, require_POST
from django.contrib.auth.decorators import login_required
from django.conf import settings
from django.contrib.auth.views import redirect_to_login
from django.utils.html import escape
from django.urls import reverse

from openpyxl import Workbook, load_workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.worksheet.datavalidation import DataValidation
from openpyxl.formatting.rule import FormulaRule
from openpyxl.utils import get_column_letter

from ..models import *
from .. import services
from ..permissions import (
    _check_page_permission,
    _get_permission_scope_defaults,
    _get_request_department,
    _get_request_login_id,
    _popup_redirect,
)
from ..filter_cache_builder import (
    rebuild_filter_cache_for_scope,
    rebuild_filter_cache_for_step,
)


ACTION_TYPE_LABELS = {
    "override": "스텝수정(상시/비상시 또는 주요/비주요 변경)",
    "plan_add": "호환계획 추가",
    "plan_update": "호환계획 수정",
    "plan_delete": "호환계획 삭제",
    "tip_missing_add": "TIP미등록 호환Path 추가",
    "tip_missing_update": "TIP미등록 호환Path 수정",
    "tip_missing_delete": "TIP미등록 호환Path 삭제",
    "bulk_upload": "엑셀 업로드 반영",
    "dashboard_config_update": "대시보드 기준정보 수정",
    "guide_upload": "사용 가이드 업로드",
    "guide_path_save": "사용 가이드 경로 저장",
    "master_add": "필요평가단계 추가",
    "master_update": "필요평가단계 수정",
    "master_delete": "필요평가단계 삭제",
    "line_master_add": "라인코드 기준정보 추가",
    "line_master_update": "라인코드 기준정보 수정",
    "line_master_delete": "라인코드 기준정보 삭제",
    "kpi_add": "KPI 목표 추가",
    "kpi_update": "KPI 목표 수정/삭제",
    "prevent_rule_add": "PREVENT 기준정보 추가",
    "prevent_rule_update": "PREVENT 기준정보 수정",
    "prevent_rule_delete": "PREVENT 기준정보 삭제",
    "dept_permission_add": "부서권한 기준정보 추가",
    "dept_permission_update": "부서권한 기준정보 수정",
    "dept_permission_delete": "부서권한 기준정보 삭제",
}


def _get_actor(request):
    if hasattr(request, "user") and getattr(request.user, "is_authenticated", False):
        return request.user
    return None


def _ensure_browser_close_session(request):
    try:
        if hasattr(request, "user") and getattr(request.user, "is_authenticated", False):
            request.session.set_expiry(0)
    except Exception:
        pass


def _record_access_history(request, page_code):
    try:
        user = getattr(request, "user", None)
        FactsAccessHistory.objects.create(
            page_code=page_code or "",
            path=(request.path or "")[:500],
            method=(request.method or "GET")[:20],
            username=_get_request_login_id(request),
            sabun=(request.session.get("sso_sabun") or "")[:150],
            department=_get_request_department(request),
            lineid=(request.GET.get("lineid") or request.POST.get("lineid") or "")[:20],
            processid=(request.GET.get("processid") or request.POST.get("processid") or "")[:100],
            snap_date=_resolve_snap_date(request) if (request.GET.get("snap_date") or request.POST.get("snap_date")) else None,
            query_string=(request.META.get("QUERY_STRING") or ""),
            ip_address=(request.META.get("HTTP_X_FORWARDED_FOR", "").split(",")[0].strip() or request.META.get("REMOTE_ADDR") or "")[:100],
        )
    except Exception:
        pass


def _parse_bool(value, default=False):
    if value is None:
        return default
    return str(value).lower() in ("1", "true", "y", "yes", "on")


def _resolve_snap_date(request):
    snap_date_str = request.GET.get("snap_date") or request.POST.get("snap_date")
    if snap_date_str:
        return datetime.strptime(snap_date_str, "%Y-%m-%d").date()
    return services.get_latest_snap_date()


def _normalize_date_input(value):
    if value is None:
        return None

    if hasattr(value, "strftime"):
        try:
            return value.date() if hasattr(value, "date") else value
        except Exception:
            pass

    s = str(value).strip()
    if not s:
        return None

    candidates = [
        "%Y-%m-%d",
        "%Y/%m/%d",
        "%Y.%m.%d",
        "%y-%m-%d",
        "%y/%m/%d",
        "%y.%m.%d",
        "%Y %m %d",
        "%y %m %d",
    ]
    for fmt in candidates:
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    return None


def _normalize_upper(value):
    return str(value or "").strip().upper()


def _parse_week_input(value):
    s = str(value or "").strip().upper()
    if not s:
        return None
    if s.startswith("W"):
        s = s[1:]
    if not s.isdigit():
        return None
    n = int(s)
    if n < 1 or n > 53:
        return None
    return n


def _week_display(value):
    if value in (None, ""):
        return ""
    try:
        n = int(value)
    except (TypeError, ValueError):
        return ""
    if n < 1:
        return ""
    return f"W{n:02d}"


def _plan_to_json(obj):
    return {
        "id": obj.id,
        "lineid": obj.lineid or "",
        "always_emergency": obj.always_emergency or "",
        "major_minor": obj.major_minor or "",
        "eqp_body_name": obj.eqp_body_name or "",
        "eqp_cham_name": obj.eqp_cham_name or "",
        "compatibility_due_date": obj.compatibility_due_date.isoformat() if obj.compatibility_due_date else "",
        "eval_lot_id": obj.eval_lot_id or "",
        "required_eval_stage_id": obj.required_eval_stage_id or "",
        "required_eval_stage_code": obj.required_eval_stage.stage_code if obj.required_eval_stage else "",
        "required_eval_stage_name": obj.required_eval_stage.stage_name if obj.required_eval_stage else "",
        "memo": obj.memo or "",
    }


def _tip_missing_to_json(obj):
    return {
        "id": obj.id,
        "lineid": obj.lineid or "",
        "always_emergency": obj.always_emergency or "",
        "major_minor": obj.major_minor or "",
        "eqp_body_name": obj.eqp_body_name or "",
        "eqp_cham_name": obj.eqp_cham_name or "",
    }


def _ensure_current_day_editable(snap_date):
    if snap_date != date.today():
        return JsonResponse({"ok": False, "message": "현재일로 조회 후 수정바랍니다."}, status=400)
    return None


def _apply_prp_filters(rows, prp_filters):
    return [row for row in rows if _row_matches_prp_filters(row, prp_filters)]


