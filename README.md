# FACTS

FACTS(Fab Compatibility Tracking System)

반도체 FAB 공정의 PRP/STEP 기준 호환율을 조회하고,
사용자 수기 입력(상시/비상시, 주요/비주요, 호환 path, 호환 계획, KPI 목표)을
원천 데이터와 결합하여 대시보드로 보여주는 Django 프로젝트입니다.

## 실행 방법

```bash
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
python manage.py makemigrations facts
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

## FACTS 프로젝트 파일 구조와 역할
### 1. 파일별 의의
#### models.py

DB 테이블 구조를 정의하는 파일입니다.
어떤 데이터를 저장할지, 컬럼명과 타입은 무엇인지, 테이블 간 관계는 어떻게 되는지를 관리합니다.

이 프로젝트에서는 예를 들어 아래와 같은 성격의 데이터를 담는 기준이 됩니다.

원천 스냅샷 데이터
사용자 입력값
기준정보
변경 이력

즉, 데이터의 저장 구조를 정하는 파일입니다.

#### urls.py

앱 내부 URL 라우팅 파일입니다.
사용자가 특정 주소로 들어왔을 때 어떤 view가 실행될지 연결합니다.

예시:

/dashboard/ → 대시보드 화면
/master/ → 기준정보 관리 화면
/history/ → 이력 조회 화면
/kpi/ → KPI 화면

즉, 앱 내부의 주소와 처리 기능을 연결하는 파일입니다.

#### services.py = 계산/비즈니스 로직 담당 (Logic Engine)

호환율 계산
확보수 계산
TIP 반영 로직
집계 / 그룹핑 / 가공

👉 즉, “진짜 계산하는 부분”

pandas 연산
groupby
merge
계산 로직
조건 분기
TIP 반영
확보수 계산
KPI 계산

build_df_compatibility_summary
TIP 반영 로직
Body/Cham 확보수 계산
groupby 집계
기간별 집계

화면 처리와 분리해야 하는 계산/가공 로직을 모아두는 파일입니다.
복잡한 집계, KPI 계산, 데이터 정제, 공통 조회 로직 등을 이쪽으로 분리합니다.

이 파일이 필요한 이유는 views.py가 너무 비대해지는 것을 막기 위해서입니다.

예시:

호환율 계산
확보수 계산
기간별 집계
대시보드용 데이터 구조 생성
이력 데이터 가공

즉, 실제 업무 로직과 데이터 가공 로직을 담당하는 파일입니다.

#### views.py = 입출력 담당 (Controller)

👉 “이 코드가 없어도 화면은 뜨냐?”

YES → views.py
NO (계산 결과 없으면 의미 없음) → services.py

요청 받는다 (필터, 날짜 등)
어떤 서비스 호출할지 결정한다
결과를 HTML 또는 JSON으로 변환한다

👉 즉, “조립 + 전달” 역할

request.GET / POST 처리
파라미터 파싱
어떤 서비스 쓸지 선택
render / JsonResponse

snap_date 받기
include_measure 체크
필터 값 처리
어떤 서비스 호출할지 결정
결과를 HTML/JSON으로 넘기기

사용자 요청을 실제로 받아 처리하는 파일입니다.
브라우저에서 요청이 들어오면 views.py가 실행되어 데이터를 조회하고, HTML을 렌더링하거나 JSON을 반환합니다.

예시:

대시보드 페이지 열기
조회 버튼 처리
저장 요청 처리
AJAX(Asynchronous JavaScript and XML, 새로고침 없이 서버와 통신하는 방식) 응답 반환

즉, 요청과 응답을 직접 처리하는 중심 파일입니다.

#### settings.py

프로젝트 전역 설정 파일입니다.
Django(장고, Python 웹 프레임워크) 프로젝트 전체 동작 환경을 정의합니다.

주요 설정 예시:

설치 앱 목록
DB 연결 정보
템플릿 경로
정적 파일 경로
언어/시간대
보안 설정

즉, 프로젝트 전체의 실행 환경을 정하는 파일입니다.

#### root_urls.py

프로젝트 최상위 URL 설정 파일입니다.
앱별 urls.py를 상위에서 묶어 전체 사이트 주소 체계를 구성합니다.

예시:

/admin/
/facts/
/

일반적으로 Django 기본 구조에서는 프로젝트의 urls.py가 이 역할을 합니다.
여기서는 이를 별도로 root_urls.py로 관리하는 개념으로 보면 됩니다.

즉, 프로젝트 전체 URL의 진입점 역할을 하는 파일입니다.

#### dashboard.js - 화면 동작

“어떻게 동작할지”

포함 내용:

조회 버튼 클릭 이벤트
필터 값 읽기
서버 요청 (AJAX: 새로고침 없이 데이터 요청)
응답 데이터 화면 반영
테이블 갱신
차트 업데이트

👉 즉, 사용자 행동에 대한 반응

대시보드 화면 전용 프론트엔드 스크립트 파일입니다.
화면에서 사용자 액션이 발생했을 때 동작을 처리합니다.

예시:

필터값 읽기
조회 버튼 클릭 이벤트 처리
AJAX 요청 전송
응답 데이터를 표/카드/차트에 반영
화면 일부 동적 갱신

즉, 대시보드 화면의 동작을 담당하는 파일입니다.

#### facts.css

프로젝트 화면 스타일 파일입니다.
색상, 간격, 카드 디자인, 표 레이아웃, 버튼 스타일 등을 정의합니다.

이 프로젝트에서는 특히 다음 역할이 중요합니다.

블루톤 UI 통일
카드형 대시보드 스타일
테이블 가독성 확보
공통 화면 일관성 유지

즉, 프로젝트의 시각적 표현을 담당하는 파일입니다.

#### dashboard.html - 화면구조

“무엇을 보여줄지”

포함 내용:

필터 UI (날짜, 체크박스 등)
KPI 카드 영역
테이블 영역
차트 영역
버튼 (조회, 저장 등)

👉 즉, 눈에 보이는 모든 구조

대시보드 메인 화면 템플릿입니다.
사용자가 핵심적으로 보는 대표 화면입니다.

일반적으로 아래 요소가 포함됩니다.

조회 필터
KPI 카드
차트
데이터 테이블
상세 영역

즉, 현재 상태를 한눈에 보여주는 메인 화면 파일입니다.

#### base.html

공통 레이아웃의 기본 뼈대 템플릿입니다.
여러 페이지가 이 파일을 상속해서 공통 구조를 재사용합니다.

보통 들어가는 내용:

<head> 공통 영역
CSS/JS 연결
상단 메뉴
공통 컨테이너
block 영역 정의

즉, 여러 화면이 공통으로 사용하는 기본 레이아웃 파일입니다.

#### master.html

기준정보 또는 마스터 데이터 관리 화면 템플릿입니다.
운영자가 직접 관리하는 설정성 데이터 입력/수정 화면에 해당합니다.

예시:

기준정보 관리
규칙 관리
주요설비 관리
옵션값 관리

즉, 운영 기준 데이터를 관리하는 화면 파일입니다.

#### history.html

이력 조회 화면 템플릿입니다.
누가 언제 무엇을 바꿨는지, 저장 내역이 어떻게 누적되었는지 확인하는 화면입니다.

예시:

사용자 입력 변경 이력
설정 변경 이력
저장 시점별 이력 조회

즉, 변경 내역을 추적하는 화면 파일입니다.

#### kpi.html

핵심 지표 전용 화면 템플릿입니다.
대시보드보다 지표 중심으로 더 집중해서 보는 화면입니다.

예시:

호환율 요약
확보수 추이
상시/비상시 비중
기간별 비교

즉, 핵심 수치를 집중적으로 보여주는 화면 파일입니다.

### 2. 파일 간 연결 구조
#### 전체 흐름 요약

사용자가 브라우저에서 페이지를 열거나 버튼을 누르면,
URL이 views.py로 연결되고,
views.py는 필요 시 services.py를 호출해 데이터를 가공한 뒤,
models.py를 통해 DB와 데이터를 주고받고,
최종적으로 *.html 템플릿을 렌더링하거나 JSON을 반환합니다.
브라우저에서는 dashboard.js가 이를 받아 화면 동작을 처리하고,
facts.css가 최종 UI 스타일을 입힙니다.

흐름도
[사용자 브라우저]
        |
        v
[root_urls.py]
        |
        v
[앱 urls.py]
        |
        v
[views.py]
   |         \
   |          \ 
   v           v
[services.py] [models.py]
   |             |
   |             v
   |          [DB]
   |
   v
[views.py가 결과 조합]
        |
        +-----------------------------+
        |                             |
        v                             v
[HTML 렌더링]                    [JSON 응답]
        |                             |
        v                             v
[dashboard.html /                [dashboard.js가
 master.html /                    AJAX 응답 처리]
 history.html /
 kpi.html]
        |
        v
[base.html 상속 구조]
        |
        v
[facts.css 적용]
        |
        v
[최종 사용자 화면]

### 3. 화면 렌더링 기준 상세 흐름
#### 3-1. 일반 페이지 렌더링 흐름

예: /dashboard/ 접속

1. 사용자가 /dashboard/ 접속
2. root_urls.py가 앱 urls.py로 전달
3. urls.py가 dashboard view로 연결
4. views.py가 필요한 데이터 조회
5. 필요하면 services.py에서 집계/가공 수행
6. models.py를 통해 DB 데이터 조회
7. views.py가 dashboard.html에 context 전달
8. dashboard.html이 base.html을 상속하여 렌더링
9. facts.css가 스타일 적용
10. 브라우저에 최종 화면 표시

### 3-2. AJAX 조회 흐름

예: 대시보드 필터 변경 후 조회 버튼 클릭

1. 사용자가 dashboard 화면에서 조회 버튼 클릭
2. dashboard.js가 필터값 수집
3. dashboard.js가 views.py의 API URL로 AJAX 요청 전송
4. views.py가 요청 파라미터 수신
5. 필요 시 services.py에서 데이터 계산/집계
6. models.py를 통해 DB 조회
7. views.py가 JSON 응답 반환
8. dashboard.js가 응답을 받아 카드/표/차트 갱신
9. facts.css가 적용된 상태로 사용자 화면에 반영

### 4. 파일 관계를 한 줄로 정리하면
settings.py : 프로젝트 실행 환경 정의
root_urls.py : 프로젝트 전체 URL 진입점
urls.py : 앱 내부 URL 연결
views.py : 요청/응답 처리
services.py : 계산/가공 로직 분리
models.py : DB 구조 및 데이터 접근 기준
*.html : 사용자에게 보여줄 화면
dashboard.js : 화면 동작 처리
facts.css : 화면 디자인 적용

### 5. 추천 이해 방식

이 프로젝트를 이해할 때는 아래 순서로 보면 됩니다.

1. settings.py
2. root_urls.py
3. urls.py
4. views.py
5. services.py
6. models.py
7. templates(html)
8. static(js, css)

이 순서가 좋은 이유는 다음과 같습니다.

먼저 프로젝트가 어떤 환경에서 도는지 본다.
그다음 URL이 어디로 들어오는지 본다.
그 요청을 누가 처리하는지 본다.
처리 과정에서 어떤 서비스 로직을 쓰는지 본다.
어떤 데이터를 읽고 쓰는지 본다.
마지막으로 화면이 어떻게 보이고 움직이는지 본다.

### 6. 실무 관점에서의 핵심 구분
views.py와 services.py의 차이

많이 헷갈리는 부분인데, 기준은 단순합니다.

views.py

브라우저 요청을 받아서 응답을 돌려주는 역할

services.py

그 응답을 만들기 위해 필요한 계산, 가공, 집계 역할

즉,

views.py는 제어
services.py는 실제 로직

입니다.

base.html과 개별 html의 차이
base.html

공통 틀

dashboard.html, master.html, history.html, kpi.html

개별 페이지 내용

즉,

base.html은 레이아웃 뼈대
나머지 html은 페이지 본문

입니다.

root_urls.py와 urls.py의 차이
root_urls.py

프로젝트 전체 입구

urls.py

앱 내부 세부 연결

즉,

root_urls.py는 대문
urls.py는 방 배치도

입니다.

### 7. 최종 요약

이 구조는 아래 원칙으로 이해하면 됩니다.

데이터 구조: models.py
주소 연결: root_urls.py, urls.py
요청 처리: views.py
업무 로직: services.py
전역 설정: settings.py
화면 뼈대: base.html
개별 화면: dashboard.html, master.html, history.html, kpi.html
화면 동작: dashboard.js
화면 디자인: facts.css

즉, 이 프로젝트는

“사용자 요청 → URL 연결 → View 처리 → Service 계산 → Model/DB 조회 → Template 렌더링 또는 JSON 반환 → JS 동적 반영 → CSS 스타일 적용”

흐름으로 움직입니다.

오류 정보
Activity ID: 6bc058f3-56fc-4b5e-f64a-00400200009c
Error details: MSIS7007: 요청된 신뢰 당사자 트러스트 'https://12.81.64.130:8000/facts/dashboard/'이(가) 지정되지 않았거나 지원되지 않습니다. 신뢰 당사자 트러스트가 지정되지 않은 경우 신뢰 당사자 트러스트에 대한 액세스 권한이 없을 수 있습니다. 자세한 내용은 관리자에게 문의하십시오.
Node name: ff5bd528-2980-449c-b0c5-21120aa8579c
Error time: Mon, 06 Apr 2026 08:01:29 GMT
Cookie: enabled
User agent string: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/146.0.0.0 Safari/537.36





if os.getenv("IS_PROD") == "TRUE": 
    # prod
    IDP_CONFIG = {
        'Idp.EntityID': 'https://'+prodIDP+'/adfs/oauth2/authorize/',
        'Idp.SignoutUrl': 'https://'+prodIDP+'/adfs/ls/?wa=wsignoutcleanup1.0',
        'Idp.': prodClientID,
        'CertFile_ClientIDPath': os.getcwd() + '/cert/',
        'CertFile_Name': prodCer,
        'SP.RedirectUrl': prodEndpoint,
    }
else:
    # dev
    IDP_CONFIG = {
        'Idp.EntityID': 'https://'+devIDP+'/adfs/oauth2/authorize/',
        'Idp.SignoutUrl': 'https://'+devIDP+'/adfs/ls/?wa=wsignoutcleanup1.0',
        'Idp.ClientID': devClientID,
        'CertFile_Path': os.getcwd() + '/cert/',
        'CertFile_Name': devCer,
        'SP.RedirectUrl': devEndpoint,
    }




    #---------------------------------------------------


    {% extends "base.html" %}

{% block content %}

{% if isLoad %}
  <a href="{% url 'sso' %}" class="btn btn-primary">Login</a>
{% endif %}

{% if isError %}
  {{ Error_MSG }}
{% endif %}

<br /><br />

{% if Claims %}
  <table class="table table-striped">
      <thead>
        <tr>
          <th>Key</th>
          <th>Values</th>
        </tr>
      </thead>
      <tbody>
        {% for k, v in Claims.items %}
          <tr>
            <td>{{ k }}</td>
            <td>{{ v }}</td>
          </tr>
        {% endfor %}
      </tbody>
  </table>
  <a href="{% url 'slo' %}" class="btn btn-danger">Logout</a>
{% endif %}

{% endblock %}
