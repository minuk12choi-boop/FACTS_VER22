import json
from datetime import date, datetime
from decimal import Decimal

from django.db.models import Model, QuerySet


def _json_safe_value(value):
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, QuerySet):
        return [_json_safe_value(item) for item in value]
    if isinstance(value, Model):
        return str(value)
    if isinstance(value, dict):
        return {str(key): _json_safe_value(val) for key, val in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_json_safe_value(item) for item in value]
    return str(value)


def _json_safe_payload(payload):
    return _json_safe_value(payload)


def _assert_json_serializable(payload):
    json.dumps(payload, ensure_ascii=False)
    return payload
