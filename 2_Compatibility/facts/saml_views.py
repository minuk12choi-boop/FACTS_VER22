from django.conf import settings
from django.contrib.auth import get_user_model, login, logout
from django.http import HttpResponse
from django.shortcuts import redirect
from django.urls import reverse
from django.views.decorators.csrf import csrf_exempt

from .saml_auth import init_saml_auth

User = get_user_model()


def _pick_first(values):
    if isinstance(values, (list, tuple)):
        return values[0] if values else ""
    return values or ""


def saml_login(request):
    auth = init_saml_auth(request)
    next_url = request.GET.get("next") or reverse("facts:dashboard")
    return_to = f"{settings.SAML_PUBLIC_BASE_URL.rstrip('/')}{next_url}"
    login_url = auth.login(return_to=return_to)

    html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8">
        <title>SSO Redirect</title>
        <meta http-equiv="refresh" content="0;url={login_url}">
        <script>
            window.location.replace("{login_url}");
        </script>
    </head>
    <body>
        <a href="{login_url}">SSO 로그인 페이지로 이동</a>
    </body>
    </html>
    """
    return HttpResponse(html)


@csrf_exempt
def saml_acs(request):
    auth = init_saml_auth(request)
    auth.process_response()
    errors = auth.get_errors()
    reason = auth.get_last_error_reason()

    if errors:
        return HttpResponse(
            "SAML ACS 처리 오류\n"
            f"errors = {errors}\n"
            f"reason = {reason}\n"
            f"post_keys = {list(request.POST.keys())}\n",
            status=400,
            content_type="text/plain; charset=utf-8",
        )

    if not auth.is_authenticated():
        return HttpResponse(
            "SAML 인증 실패: 인증되지 않은 응답입니다.",
            status=401,
            content_type="text/plain; charset=utf-8",
        )

    attrs = auth.get_attributes()
    name_id = auth.get_nameid()

    request.session["samlUserdata"] = attrs
    request.session["samlNameId"] = name_id
    request.session["samlSessionIndex"] = auth.get_session_index()

    username = (
        _pick_first(attrs.get("http://schemas.sec.com/2018/05/identity/claims/LoginId"))
        or _pick_first(attrs.get("http://schemas.xmlsoap.org/ws/2005/05/identity/claims/name"))
        or _pick_first(attrs.get("http://schemas.xmlsoap.org/ws/2005/05/identity/claims/upn"))
        or _pick_first(attrs.get("name"))
        or _pick_first(attrs.get("UserID"))
        or name_id
    )

    employee_no = _pick_first(
        attrs.get("http://schemas.sec.com/2018/05/identity/claims/Sabun")
    )

    display_name = _pick_first(
        attrs.get("http://schemas.sec.com/2018/05/identity/claims/Username")
    )

    dept_name = (
        _pick_first(attrs.get("http://schemas.sec.com/2018/05/identity/claims/DeptName"))
        or _pick_first(attrs.get("http://schemas.sec.com/2018/05/identity/clims/DeptName"))
        or _pick_first(attrs.get("DeptName"))
    )

    if not username:
        return HttpResponse(
            "SAML 인증 성공했지만 username claim이 없습니다.\n"
            f"name_id = {name_id}\n"
            f"attrs = {attrs}\n",
            status=400,
            content_type="text/plain; charset=utf-8",
        )

    if "\\" in username:
        username = username.split("\\")[-1]

    user, created = User.objects.get_or_create(username=username)

    updated = False

    if display_name and user.first_name != display_name:
        user.first_name = display_name
        updated = True

    # 일단 email은 응답에 없으므로 건드리지 않음

    if created or updated:
        user.save()

    request.session["sso_login_id"] = username
    request.session["sso_sabun"] = employee_no
    request.session["sso_username"] = display_name
    request.session["sso_dept_name"] = dept_name

    user.backend = "django.contrib.auth.backends.ModelBackend"
    login(request, user)

    relay_state = request.POST.get("RelayState")
    if relay_state and relay_state.startswith("http"):
        return redirect(relay_state)

    if relay_state and relay_state.startswith("/"):
        return redirect(relay_state)

    return redirect("facts:dashboard")


def saml_logout(request):
    logout(request)
    return redirect("facts:dashboard")
