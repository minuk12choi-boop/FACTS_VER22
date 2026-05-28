from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("facts/", include(("facts.urls", "facts"), namespace="facts")),
]
