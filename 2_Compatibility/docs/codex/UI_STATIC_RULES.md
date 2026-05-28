# UI / Static / WhiteNoise 규칙

## 기본 원칙

- `base.html`의 레이아웃 wrapper를 깨지 않습니다.
- `{% load static %}` 누락 금지
- static 경로 하드코딩 금지: `{% static '...' %}` 사용
- CSS/JS가 404면 UI가 텍스트 세로 나열처럼 무너집니다.

## base.html 핵심 구조

```html
<div class="facts-app">
  <aside class="facts-sidebar">...</aside>
  <main class="facts-main">
    <div class="facts-main-scroll">
      {% block content %}{% endblock %}
    </div>
  </main>
</div>
```

## static 검증

```powershell
python manage.py findstatic facts/css/facts.css --verbosity 2
python manage.py findstatic facts/js/searchable_select.js --verbosity 2
python manage.py findstatic facts/js/dashboard.js --verbosity 2
python manage.py collectstatic --noinput
```

Waitress 실행 후:

```powershell
Invoke-WebRequest -Uri http://127.0.0.1:8001/static/facts/css/facts.css -UseBasicParsing
Invoke-WebRequest -Uri http://127.0.0.1:8001/static/facts/js/dashboard.js -UseBasicParsing
```

StatusCode 200이어야 합니다.

## Dropdown UI 규칙

- option 값이 화면에 펼쳐져 보이면 실패
- native multiple select 그대로 노출 금지
- datalist 의존 금지
- panel 기본 hidden
- 검색은 `includes` 기반
- 중복 이벤트 바인딩 방지
- input/textarea focus 시 loading overlay 금지

## SSO 버튼

초기 로그인 화면의 SSO login 버튼은 유지되어야 합니다. `templates/admin/login.html` 또는 기존 로그인 템플릿 변경 시 반드시 확인합니다.
