from django.http import HttpResponse, JsonResponse
from django.utils.html import escape

from .models import FactsDeptPermission


def _get_request_login_id(request):
    return (request.session.get("sso_login_id") or getattr(getattr(request, "user", None), "username", "") or "").strip()


def _get_request_department(request):
    return (request.session.get("sso_dept_name") or "").strip()


def _normalize_permission_values(values):
    result = []
    for value in values or []:
        normalized = str(value or "").strip()
        if normalized:
            result.append(normalized)
    return result


def _normalize_rule_identity(value, default="ALL"):
    normalized = str(value or "").strip()
    return normalized or default


def _matches_identity(rule_value, current_value):
    rule_normalized = _normalize_rule_identity(rule_value)
    current_normalized = str(current_value or "").strip()
    if rule_normalized == "ALL":
        return True
    return bool(current_normalized) and rule_normalized == current_normalized


def _get_effective_permission_rules(username, dept):
    rules = list(FactsDeptPermission.objects.filter(is_active=True))
    if not rules:
        return []

    normalized_username = str(username or "").strip()
    normalized_dept = str(dept or "").strip()

    matched_rules = []
    for rule in rules:
        rule_user = _normalize_rule_identity(getattr(rule, "username", "ALL"))
        rule_dept = _normalize_rule_identity(getattr(rule, "dept", "ALL"))

        if not _matches_identity(rule_user, normalized_username):
            continue
        if not _matches_identity(rule_dept, normalized_dept):
            continue

        matched_rules.append(rule)

    return matched_rules


def _permission_rule_sort_key(rule, username, dept, lineid="", processid=""):
    rule_dept = _normalize_rule_identity(getattr(rule, "dept", "ALL"))
    rule_user = _normalize_rule_identity(getattr(rule, "username", "ALL"))
    normalized_username = str(username or "").strip()
    normalized_dept = str(dept or "").strip()
    line_values = _normalize_permission_values(rule.line_values)
    prp_values = _normalize_permission_values(rule.prp_values)

    return (
        1 if normalized_username and rule_user != "ALL" and rule_user == normalized_username else 0,
        1 if normalized_dept and rule_dept != "ALL" and rule_dept == normalized_dept else 0,
        1 if lineid and line_values and "ALL" not in line_values and lineid in line_values else 0,
        1 if processid and prp_values and "ALL" not in prp_values and processid in prp_values else 0,
        1 if line_values and "ALL" not in line_values else 0,
        1 if prp_values and "ALL" not in prp_values else 0,
        1 if rule.can_edit else 0,
        -rule.id,
    )


def _match_permission_rule(page_code, username, dept, lineid="", processid="", ignore_blank_scope=False):
    rules = _get_effective_permission_rules(username, dept)
    if not rules:
        return None

    def match_multi(values, current, ignore_blank=False):
        vals = _normalize_permission_values(values)
        if not vals or "ALL" in vals:
            return True
        current_value = (current or "").strip()
        if ignore_blank and current_value == "":
            return True
        return current_value in vals

    candidates = []
    for rule in rules:
        if not match_multi(rule.page_values, page_code):
            continue
        if not match_multi(rule.line_values, lineid, ignore_blank=ignore_blank_scope):
            continue
        if not match_multi(rule.prp_values, processid, ignore_blank=ignore_blank_scope):
            continue
        candidates.append((_permission_rule_sort_key(rule, username, dept, lineid=lineid, processid=processid), rule))

    if not candidates:
        return None

    candidates.sort(reverse=True, key=lambda x: x[0])
    return candidates[0][1]


def _resolve_page_permission(rule, page_code):
    perms = getattr(rule, "page_permissions", None) or {}
    page_perm = perms.get(page_code) if isinstance(perms, dict) else None
    if isinstance(page_perm, dict):
        can_view = bool(page_perm.get("can_view"))
        can_edit = bool(page_perm.get("can_edit"))
        if can_edit:
            can_view = True
        if not can_view:
            can_edit = False
        return can_view, can_edit
    return bool(rule.can_view), bool(rule.can_edit)


def _get_permission_scope_defaults(page_code, username, dept):
    rule = _match_permission_rule(page_code, username, dept, ignore_blank_scope=True)
    if rule is None:
        return {"lineid": "", "processid": ""}

    line_values = [x for x in _normalize_permission_values(rule.line_values) if x != "ALL"]
    prp_values = [x for x in _normalize_permission_values(rule.prp_values) if x != "ALL"]

    return {
        "lineid": line_values[0] if line_values else "",
        "processid": prp_values[0] if prp_values else "",
    }


def _permission_required_response(request=None, message="권한이 없습니다. minuk12.choi에게 권한 신청 부탁드립니다."):
    safe_message = escape(str(message))
    sso_login_url = "/facts/saml/login/?next=/facts/dashboard/"
    admin_login_url = "/admin/login/?next=/facts/dashboard/"
    dashboard_url = "/facts/dashboard/"

    is_ajax = False
    if request is not None:
        accept = request.headers.get("Accept") or ""
        xrw = request.headers.get("X-Requested-With") or ""
        content_type = request.content_type or ""
        path = request.path or ""
        is_ajax = (
            xrw == "XMLHttpRequest"
            or "application/json" in accept
            or "application/json" in content_type
            or path.endswith("-api/")
            or "/data-api/" in path
            or "/save-api/" in path
            or "/delete-api/" in path
            or "/detail-api/" in path
            or "/options-api/" in path
            or "/similar-eqp-api/" in path
            or "/bulk-upload-api/" in path
        )

    if is_ajax:
        return JsonResponse(
            {
                "ok": False,
                "permission_denied": True,
                "message": str(message),
                "admin_login_url": admin_login_url,
                "sso_login_url": sso_login_url,
                "dashboard_url": dashboard_url,
            },
            status=403,
        )

    html = f"""
<!doctype html>
<html lang="ko">
<head>
    <meta charset="utf-8">
    <title>FACTS의 메시지</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <style>
        * {{ box-sizing: border-box; }}
        html, body {{
            margin: 0;
            width: 100%;
            height: 100%;
            font-family: Arial, "Malgun Gothic", sans-serif;
            background: rgba(16, 35, 58, 0.18);
        }}
        .wrap {{
            position: fixed;
            inset: 0;
            display: flex;
            align-items: center;
            justify-content: center;
            padding: 20px;
        }}
        .modal {{
            width: 520px;
            max-width: 96vw;
            background: #ffffff;
            border-radius: 16px;
            box-shadow: 0 18px 40px rgba(18, 53, 94, 0.20);
            overflow: hidden;
        }}
        .header {{
            padding: 16px 18px 10px;
            font-size: 20px;
            font-weight: 800;
            color: #12385f;
            border-bottom: 1px solid #e7eef6;
        }}
        .body {{
            padding: 22px 18px 18px;
            font-size: 14px;
            color: #26496d;
            line-height: 1.7;
            word-break: keep-all;
        }}
        .footer {{
            padding: 0 18px 18px;
            display: flex;
            gap: 10px;
            justify-content: flex-end;
            flex-wrap: wrap;
        }}
        .btn {{
            border: none;
            border-radius: 10px;
            padding: 10px 16px;
            color: #fff;
            font-weight: 700;
            cursor: pointer;
            text-decoration: none;
            display: inline-flex;
            align-items: center;
            justify-content: center;
            min-width: 120px;
        }}
        .btn-admin {{ background: #12385f; }}
        .btn-sso {{ background: #0f5da0; }}
        .btn-dashboard {{ background: #6b7c93; }}
    </style>
</head>
<body>
    <div class="wrap">
        <div class="modal" role="dialog" aria-modal="true" aria-labelledby="modal-title">
            <div class="header" id="modal-title">FACTS의 메시지</div>
            <div class="body">
                {safe_message}
                <br><br>
                진행할 작업을 선택해 주세요.
            </div>
            <div class="footer">
                <a class="btn btn-admin" href="{admin_login_url}">관리자 로그인</a>
                <a class="btn btn-sso" href="{sso_login_url}">SSO 로그인</a>
                <a class="btn btn-dashboard" href="{dashboard_url}">대시보드로 돌아가기</a>
            </div>
        </div>
    </div>
</body>
</html>
"""
    return HttpResponse(html, content_type="text/html; charset=utf-8")


def _popup_redirect(message, url="/facts/master/"):
    safe_message = escape(str(message))
    safe_url = str(url).replace("\\", "\\\\").replace("'", "\\'")

    html = f"""
<!doctype html>
<html lang="ko">
<head>
    <meta charset="utf-8">
    <title>FACTS의 메시지</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <style>
        * {{ box-sizing: border-box; }}
        html, body {{
            margin: 0;
            width: 100%;
            height: 100%;
            font-family: Arial, "Malgun Gothic", sans-serif;
            background: rgba(16, 35, 58, 0.18);
        }}
        .wrap {{
            position: fixed;
            inset: 0;
            display: flex;
            align-items: center;
            justify-content: center;
            padding: 20px;
        }}
        .modal {{
            width: 460px;
            max-width: 96vw;
            background: #ffffff;
            border-radius: 16px;
            box-shadow: 0 18px 40px rgba(18, 53, 94, 0.20);
            overflow: hidden;
        }}
        .header {{
            padding: 16px 18px 10px;
            font-size: 20px;
            font-weight: 800;
            color: #12385f;
            border-bottom: 1px solid #e7eef6;
        }}
        .body {{
            padding: 22px 18px 18px;
            font-size: 14px;
            color: #26496d;
            line-height: 1.7;
            word-break: keep-all;
        }}
        .footer {{
            padding: 0 18px 18px;
            display: flex;
            justify-content: flex-end;
        }}
        .btn {{
            border: none;
            border-radius: 10px;
            padding: 10px 16px;
            background: #0f5da0;
            color: #fff;
            font-weight: 700;
            cursor: pointer;
        }}
    </style>
</head>
<body>
    <div class="wrap">
        <div class="modal" role="dialog" aria-modal="true" aria-labelledby="modal-title">
            <div class="header" id="modal-title">FACTS의 메시지</div>
            <div class="body">{safe_message}</div>
            <div class="footer">
                <button class="btn" id="moveBtn">확인</button>
            </div>
        </div>
    </div>
    <script>
        (function () {{
            const go = function () {{
                window.location.replace('{safe_url}');
            }};
            document.getElementById('moveBtn').addEventListener('click', go);
            window.addEventListener('keydown', function (e) {{
                if (e.key === 'Enter' || e.key === 'Escape') {{
                    e.preventDefault();
                    go();
                }}
            }});
        }})();
    </script>
</body>
</html>
"""
    return HttpResponse(html, content_type="text/html; charset=utf-8")


def _check_page_permission(request, page_code, lineid="", processid="", require_edit=False, popup=False, ignore_blank_scope=False):
    user = getattr(request, "user", None)

    if not user or not user.is_authenticated:
        return _permission_required_response(request, "로그인이 필요합니다. 관리자 로그인 또는 SSO 로그인 후 다시 시도해 주세요.")

    if user.is_staff or user.is_superuser:
        return None

    username = _get_request_login_id(request)
    dept = _get_request_department(request)
    rule = _match_permission_rule(page_code, username, dept, lineid=lineid, processid=processid, ignore_blank_scope=ignore_blank_scope)

    if rule is None:
        if popup:
            if request is not None:
                accept = request.headers.get("Accept") or ""
                xrw = request.headers.get("X-Requested-With") or ""
                content_type = request.content_type or ""
                path = request.path or ""
                is_ajax = (
                    xrw == "XMLHttpRequest"
                    or "application/json" in accept
                    or "application/json" in content_type
                    or path.endswith("-api/")
                    or "/data-api/" in path
                    or "/save-api/" in path
                    or "/delete-api/" in path
                    or "/detail-api/" in path
                    or "/options-api/" in path
                    or "/similar-eqp-api/" in path
                    or "/bulk-upload-api/" in path
                )
                if is_ajax:
                    return _permission_required_response(request, "권한이 없습니다. minuk12.choi에게 문의 부탁드립니다.")
            return _popup_redirect("권한이 없습니다. minuk12.choi에게 문의 부탁드립니다.", "/facts/dashboard/")
        return _permission_required_response(request, "권한이 없습니다. minuk12.choi에게 권한 신청 부탁드립니다.")

    page_can_view, page_can_edit = _resolve_page_permission(rule, page_code)
    if require_edit:
        if not page_can_edit:
            if popup:
                if request is not None:
                    accept = request.headers.get("Accept") or ""
                    xrw = request.headers.get("X-Requested-With") or ""
                    content_type = request.content_type or ""
                    path = request.path or ""
                    is_ajax = (
                        xrw == "XMLHttpRequest"
                        or "application/json" in accept
                        or "application/json" in content_type
                        or path.endswith("-api/")
                        or "/data-api/" in path
                        or "/save-api/" in path
                        or "/delete-api/" in path
                        or "/detail-api/" in path
                        or "/options-api/" in path
                        or "/similar-eqp-api/" in path
                        or "/bulk-upload-api/" in path
                    )
                    if is_ajax:
                        return _permission_required_response(request, "권한이 없습니다. minuk12.choi에게 문의 부탁드립니다.")
                return _popup_redirect("권한이 없습니다. minuk12.choi에게 문의 부탁드립니다.", "/facts/dashboard/")
            return _permission_required_response(request, "수정 권한이 없습니다. minuk12.choi에게 권한 신청 부탁드립니다.")
    else:
        if not page_can_view:
            if popup:
                if request is not None:
                    accept = request.headers.get("Accept") or ""
                    xrw = request.headers.get("X-Requested-With") or ""
                    content_type = request.content_type or ""
                    path = request.path or ""
                    is_ajax = (
                        xrw == "XMLHttpRequest"
                        or "application/json" in accept
                        or "application/json" in content_type
                        or path.endswith("-api/")
                        or "/data-api/" in path
                        or "/save-api/" in path
                        or "/delete-api/" in path
                        or "/detail-api/" in path
                        or "/options-api/" in path
                        or "/similar-eqp-api/" in path
                        or "/bulk-upload-api/" in path
                    )
                    if is_ajax:
                        return _permission_required_response(request, "권한이 없습니다. minuk12.choi에게 문의 부탁드립니다.")
                return _popup_redirect("권한이 없습니다. minuk12.choi에게 문의 부탁드립니다.", "/facts/dashboard/")
            return _permission_required_response(request, "조회 권한이 없습니다. minuk12.choi에게 권한 신청 부탁드립니다.")

    return None


def _require_admin_page(request):
    user = getattr(request, "user", None)
    if not user or not user.is_authenticated:
        return _permission_required_response(request, "관리자 권한이 필요한 페이지입니다. 관리자 로그인 또는 SSO 로그인 후 다시 시도해 주세요.")
    if user.is_staff or user.is_superuser:
        return None
    return _permission_required_response(request, "관리자 권한이 없습니다. 관리자 로그인 또는 SSO 로그인 후 다시 시도해 주세요.")
