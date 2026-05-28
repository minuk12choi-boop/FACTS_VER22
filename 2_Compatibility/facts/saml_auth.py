from urllib.parse import urlsplit

from django.conf import settings
from onelogin.saml2.auth import OneLogin_Saml2_Auth


def prepare_django_request(request):
    external_base = settings.SAML_PUBLIC_BASE_URL.rstrip("/")
    external_url = f"{external_base}{request.path}"
    parsed = urlsplit(external_url)

    return {
        "https": "on" if parsed.scheme == "https" else "off",
        "http_host": parsed.netloc,
        "server_port": str(parsed.port or ("443" if parsed.scheme == "https" else "80")),
        "script_name": request.path,
        "get_data": request.GET.copy(),
        "post_data": request.POST.copy(),
        "query_string": request.META.get("QUERY_STRING", ""),
    }


def init_saml_auth(request):
    req = prepare_django_request(request)
    return OneLogin_Saml2_Auth(
        req,
        custom_base_path=str(settings.SAML_AUTH_ROOT),
    )
