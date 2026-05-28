from django.contrib import admin

from .models import (
    FactsDashboardConfig,
    FactsEditHistory,
    FactsEvalStageMaster,
    FactsKpiTarget,
    
    FactsStepPathOverride,
    FactsStepPlan,
    FactsWipSource,
)


@admin.register(FactsWipSource)
class FactsWipSourceAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "snap_date",
        "processid",
        "stepseq",
        "recipeid",
        "areaname",
        "layerid",
        "stepseq_type",
        "eqpgroup",
        "always_emergency",
        "body_compat",
        "cham_compat",
        "loaded_at",
    )
    search_fields = (
        "processid",
        "stepseq",
        "recipeid",
        "areaname",
        "layerid",
        "descript",
        "eqpgroup",
        "path",
        "childeqp",
    )
    list_filter = (
        "snap_date",
        "areaname",
        "stepseq_type",
        "always_emergency",
        "body_compat",
        "cham_compat",
    )
    ordering = ("-snap_date", "processid", "stepseq", "recipeid")
    readonly_fields = [f.name for f in FactsWipSource._meta.fields]

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(FactsDashboardConfig)
class FactDashboardConfigAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "default_prp",
        "inquiry_contact",
    )
    search_fields = (
        "default_prp",
        "inquiry_contact",
    )


@admin.register(FactsEvalStageMaster)
class FactEvalStageMasterAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "stage_code",
        "stage_name",
        "sort_order",
        "is_active",
    )
    search_fields = (
        "stage_code",
        "stage_name",
    )
    list_filter = (
        "is_active",
    )
    ordering = ("sort_order", "stage_code")


@admin.register(FactsStepPathOverride)
class FactStepPathOverrideAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "snap_date",
        "processid",
        "stepseq",
        "recipeid",
        "manual_always_emergency",
        "manual_major_minor",
        "is_active",
        "updated_at",
    )
    search_fields = (
        "processid",
        "stepseq",
        "recipeid",
        "path",
        "eqpline",
        "childeqp",
    )
    list_filter = (
        "snap_date",
        "manual_always_emergency",
        "manual_major_minor",
        "is_active",
    )
    ordering = ("-snap_date", "processid", "stepseq", "recipeid")




@admin.register(FactsStepPlan)
class FactStepPlanAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "processid",
        "stepseq",
        "always_emergency",
        "major_minor",
        "eqp_body_name",
        "eqp_cham_name",
        "compatibility_due_date",
        "eval_lot_id",
        "required_eval_stage",
        "is_active",
        "updated_at",
    )
    search_fields = (
        "processid",
        "stepseq",
        "recipeid",
        "eqp_body_name",
        "eqp_cham_name",
        "eval_lot_id",
        "memo",
    )
    list_filter = (
        "always_emergency",
        "major_minor",
        "is_active",
        "required_eval_stage",
    )
    ordering = ("-updated_at", "processid", "stepseq")


@admin.register(FactsKpiTarget)
class FactKpiTargetAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "target_type",
        "target_year",
        "target_month",
        "target_week",
        "processid",
        "areaname",
        "target_rate",
        "is_active",
        "updated_at",
    )
    search_fields = (
        "processid",
        "areaname",
    )
    list_filter = (
        "target_type",
        "target_year",
        "target_month",
        "target_week",
        "is_active",
    )
    ordering = ("-target_year", "-target_month", "-target_week", "processid", "areaname")


@admin.register(FactsEditHistory)
class FactEditHistoryAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "action_type",
        "snap_date",
        "processid",
        "stepseq",
        "recipeid",
        "changed_by",
        "created_at",
    )
    search_fields = (
        "processid",
        "stepseq",
        "recipeid",
        "action_type",
    )
    list_filter = (
        "action_type",
        "snap_date",
        "created_at",
    )
    ordering = ("-created_at",)
