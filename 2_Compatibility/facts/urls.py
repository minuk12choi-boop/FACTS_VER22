from django.urls import path
from . import views
from . import saml_views

app_name = "facts"

urlpatterns = [
    path("dashboard/", views.dashboard_view, name="dashboard"),
    path("dashboard/data-api/", views.dashboard_data_api, name="dashboard_data_api"),
    path("dashboard/prp-options-api/", views.dashboard_prp_options_api, name="dashboard_prp_options_api"),
    path("dashboard/override-save-api/", views.dashboard_override_save_api, name="dashboard_override_save_api"),
    path("dashboard/override-detail-api/", views.dashboard_override_detail_api, name="dashboard_override_detail_api"),
    path("dashboard/override-member-save-api/", views.dashboard_override_member_save_api, name="dashboard_override_member_save_api"),
    path("dashboard/plan-detail-api/", views.dashboard_plan_detail_api, name="dashboard_plan_detail_api"),
    path("dashboard/plan-save-api/", views.dashboard_plan_save_api, name="dashboard_plan_save_api"),
    path("dashboard/plan-delete-api/", views.dashboard_plan_delete_api, name="dashboard_plan_delete_api"),
    path("dashboard/tip-missing-detail-api/", views.dashboard_tip_missing_detail_api, name="dashboard_tip_missing_detail_api"),
    path("dashboard/tip-missing-save-api/", views.dashboard_tip_missing_save_api, name="dashboard_tip_missing_save_api"),
    path("dashboard/tip-missing-delete-api/", views.dashboard_tip_missing_delete_api, name="dashboard_tip_missing_delete_api"),
    path("dashboard/similar-eqp-api/", views.dashboard_similar_eqp_api, name="dashboard_similar_eqp_api"),
    path("dashboard/bulk-upload-api/", views.dashboard_bulk_upload_api, name="dashboard_bulk_upload_api"),
    path("dashboard/filter-option-api/", views.dashboard_filter_options_api, name="dashboard_filter_options_api"),
    path("dashboard/upload-template/", views.dashboard_upload_template, name="dashboard_upload_template"),
    path("dashboard/prp-export-csv/", views.prp_export_csv, name="prp_export_csv"),
    path("dashboard/prp-export-csv-all/", views.prp_export_csv_all, name="prp_export_csv_all"),
    path("kpi/", views.kpi_view, name="kpi"),
    path("history/", views.history_view, name="history"),
    path("history/options-api/", views.history_options_api, name="history_options_api"),
    path("prevent-tip/", views.prevent_tip_view, name="prevent_tip"),
    path("prevent-tip/data-api/", views.prevent_tip_data_api, name="prevent_tip_data_api"),
    path("prevent-tip/options-api/", views.prevent_tip_options_api, name="prevent_tip_options_api"),
    path("master/", views.master_view, name="master"),
    path("voc/", views.voc_list_view, name="voc"),
    path("voc/new/", views.voc_new_view, name="voc_new"),
    path("voc/<int:post_id>/", views.voc_detail_view, name="voc_detail"),

    path("saml/login/", saml_views.saml_login, name="saml_login"),
    path("saml/acs/", saml_views.saml_acs, name="saml_acs"),
    path("saml/logout/", saml_views.saml_logout, name="saml_logout"),
]
