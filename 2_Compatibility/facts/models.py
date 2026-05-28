from django.conf import settings
from django.db import models


class FactsWipSource(models.Model):
    id = models.BigAutoField(primary_key=True)
    load_id = models.CharField(max_length=64)
    loaded_at = models.DateTimeField()
    snap_date = models.DateField()
    processid = models.CharField(max_length=100, blank=True, default="")
    category = models.CharField(max_length=100, blank=True, default="")
    skiprule = models.CharField(max_length=50, blank=True, default="")
    areaname = models.CharField(max_length=100, blank=True, default="")
    eqptype = models.CharField(max_length=100, blank=True, default="")
    layerid = models.CharField(max_length=100, blank=True, default="")
    lineid = models.CharField(max_length=100, null=True, blank=True, db_column="lineid")
    stepseq_type = models.CharField(max_length=50, blank=True, default="")
    stepseq = models.CharField(max_length=100, blank=True, default="")
    descript = models.CharField(max_length=255, blank=True, default="")
    recipeid = models.CharField(max_length=255, blank=True, default="")
    batch_kind = models.CharField(max_length=100, blank=True, default="")
    eqpgroup = models.TextField(blank=True, default="")
    always_emergency = models.CharField(db_column="상시/비상시", max_length=50, blank=True, default="")
    body_compat = models.CharField(db_column="Body호환", max_length=10, blank=True, default="")
    cham_compat = models.CharField(db_column="Cham호환", max_length=10, blank=True, default="")
    body_compat_count = models.IntegerField(db_column="Body호환확보수", null=True, blank=True)
    cham_compat_count = models.IntegerField(db_column="Cham호환확보수", null=True, blank=True)
    body_compat_tip = models.CharField(db_column="Body호환_TIP고려", max_length=10, blank=True, default="")
    cham_compat_tip = models.CharField(db_column="Cham호환_TIP고려", max_length=10, blank=True, default="")
    body_compat_count_tip = models.IntegerField(db_column="Body호환확보수_TIP고려", null=True, blank=True)
    cham_compat_count_tip = models.IntegerField(db_column="Cham호환확보수_TIP고려", null=True, blank=True)
    prevent = models.TextField(blank=True, default="")
    tip = models.TextField(blank=True, default="")
    path = models.TextField(blank=True, default="")
    eventtime = models.DateTimeField(null=True, blank=True)
    childeqp = models.TextField(blank=True, default="")
    eqpline = models.CharField(max_length=255, blank=True, default="")

    class Meta:
        db_table = "facts_wip_source"
        managed = False


class FactsDashboardConfig(models.Model):
    default_prp = models.CharField(max_length=100, default="P1SD")
    inquiry_contact = models.CharField(max_length=100, default="minuk12.choi")

    class Meta:
        db_table = "facts_dashboard_config"


class FactsEvalStageMaster(models.Model):
    stage_code = models.CharField(max_length=50, unique=True)
    stage_name = models.CharField(max_length=100)
    sort_order = models.IntegerField(default=0)
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = "facts_eval_stage_master"
        ordering = ["sort_order", "stage_code"]
        indexes = [
            models.Index(fields=["is_active", "sort_order", "stage_code"], name="f_eval_act_ord_idx"),
        ]

    def __str__(self):
        return f"{self.stage_code} - {self.stage_name}"


class FactsStepPathOverride(models.Model):
    snap_date = models.DateField()
    lineid = models.CharField(max_length=20, blank=True, default="")
    processid = models.CharField(max_length=100)
    stepseq = models.CharField(max_length=100)
    recipeid = models.CharField(max_length=255, blank=True, default="")
    path = models.TextField(blank=True, default="")
    eqpline = models.CharField(max_length=255, blank=True, default="")
    childeqp = models.TextField(blank=True, default="")
    manual_always_emergency = models.CharField(max_length=50, blank=True, default="")
    manual_major_minor = models.CharField(max_length=50, blank=True, default="")
    is_active = models.BooleanField(default=True)
    created_department = models.CharField(max_length=255, blank=True, default="")
    updated_department = models.CharField(max_length=255, blank=True, default="")
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="facts_path_override_created",
    )
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="facts_path_override_updated",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "facts_step_path_override"
        unique_together = ("snap_date", "lineid", "processid", "stepseq", "recipeid", "path", "eqpline", "childeqp")
        indexes = [
            models.Index(fields=["snap_date", "lineid", "processid", "stepseq", "is_active"], name="fspo_slpsa_idx"),
            models.Index(fields=["snap_date", "lineid", "processid", "stepseq"], name="fspo_slps_idx"),
        ]


class FactsStepPlan(models.Model):
    snap_date = models.DateField(null=True, blank=True)
    lineid = models.CharField(max_length=20, blank=True, default="")
    processid = models.CharField(max_length=100)
    stepseq = models.CharField(max_length=100)
    recipeid = models.CharField(max_length=255, blank=True, default="")
    always_emergency = models.CharField(max_length=50, blank=True, default="")
    major_minor = models.CharField(max_length=50, blank=True, default="")
    eqp_body_name = models.CharField(max_length=255, blank=True, default="")
    eqp_cham_name = models.CharField(max_length=255, blank=True, default="")
    compatibility_due_date = models.DateField(null=True, blank=True)
    eval_lot_id = models.CharField(max_length=255, blank=True, default="")
    required_eval_stage = models.ForeignKey(
        "FactsEvalStageMaster",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="step_plans",
    )
    memo = models.TextField(blank=True, default="")
    is_active = models.BooleanField(default=True)
    created_department = models.CharField(max_length=255, blank=True, default="")
    updated_department = models.CharField(max_length=255, blank=True, default="")
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="facts_step_plan_created",
    )
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="facts_step_plan_updated",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "facts_step_plan"
        indexes = [
            models.Index(fields=["snap_date", "lineid", "processid", "stepseq"], name="fsp_slps_idx"),
            models.Index(fields=["snap_date", "lineid", "processid", "stepseq", "is_active"], name="fsp_slpsa_idx"),
            models.Index(fields=["snap_date", "lineid", "processid", "stepseq", "updated_at"], name="fsp_slpsu_idx"),
            models.Index(fields=["is_active", "updated_at"], name="fsp_au_idx"),
        ]


class FactsTipMissingCompatPath(models.Model):
    snap_date = models.DateField()
    lineid = models.CharField(max_length=20, blank=True, default="")
    processid = models.CharField(max_length=100)
    stepseq = models.CharField(max_length=100)
    recipeid = models.CharField(max_length=255, blank=True, default="")
    always_emergency = models.CharField(max_length=50, blank=True, default="")
    major_minor = models.CharField(max_length=50, blank=True, default="")
    eqp_body_name = models.CharField(max_length=255, blank=True, default="")
    eqp_cham_name = models.CharField(max_length=255, blank=True, default="")
    is_active = models.BooleanField(default=True)
    created_department = models.CharField(max_length=255, blank=True, default="")
    updated_department = models.CharField(max_length=255, blank=True, default="")
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="facts_tip_missing_path_created",
    )
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="facts_tip_missing_path_updated",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "facts_tip_missing_compat_path"
        indexes = [
            models.Index(fields=["snap_date", "lineid", "processid", "stepseq"], name="ftm_slps_idx"),
            models.Index(fields=["snap_date", "lineid", "processid", "stepseq", "is_active"], name="ftm_slpsa_idx"),
            models.Index(fields=["is_active", "updated_at"], name="ftm_au_idx"),
        ]


class FactsKpiTarget(models.Model):
    TARGET_TYPE_CHOICES = (
        ("monthly", "monthly"),
        ("weekly", "weekly"),
    )

    target_type = models.CharField(max_length=20, choices=TARGET_TYPE_CHOICES)
    target_year = models.IntegerField()
    target_month = models.IntegerField(null=True, blank=True)
    target_week = models.IntegerField(null=True, blank=True)
    lineid = models.CharField(max_length=20, blank=True, default="")
    processid = models.CharField(max_length=100)
    areaname = models.CharField(max_length=100, blank=True, default="")
    target_rate = models.DecimalField(max_digits=7, decimal_places=2)
    is_active = models.BooleanField(default=True)
    created_department = models.CharField(max_length=255, blank=True, default="")
    updated_department = models.CharField(max_length=255, blank=True, default="")
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="facts_kpi_created",
    )
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="facts_kpi_updated",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "facts_kpi_target"
        indexes = [
            models.Index(
                fields=["target_type", "target_year", "target_month", "lineid", "processid", "areaname", "is_active"],
                name="fkpi_month_idx",
            ),
            models.Index(
                fields=["target_type", "target_year", "target_week", "lineid", "processid", "areaname", "is_active"],
                name="fkpi_week_idx",
            ),
            models.Index(fields=["is_active", "updated_at"], name="fkpi_au_idx"),
        ]


class FactsEditHistory(models.Model):
    ACTION_CHOICES = (
        ("override", "override"),
        ("plan_add", "plan_add"),
        ("plan_update", "plan_update"),
        ("plan_delete", "plan_delete"),
        ("tip_missing_add", "tip_missing_add"),
        ("tip_missing_update", "tip_missing_update"),
        ("tip_missing_delete", "tip_missing_delete"),
        ("kpi_add", "kpi_add"),
        ("kpi_update", "kpi_update"),
        ("bulk_upload", "bulk_upload"),
        ("master_add", "master_add"),
        ("master_update", "master_update"),
        ("master_delete", "master_delete"),
        ("dashboard_config_update", "dashboard_config_update"),
        ("guide_path_save", "guide_path_save"),
        ("line_master_add", "line_master_add"),
        ("line_master_update", "line_master_update"),
        ("line_master_delete", "line_master_delete"),
        ("prevent_rule_add", "prevent_rule_add"),
        ("prevent_rule_update", "prevent_rule_update"),
        ("prevent_rule_delete", "prevent_rule_delete"),
        ("dept_permission_add", "dept_permission_add"),
        ("dept_permission_update", "dept_permission_update"),
        ("dept_permission_delete", "dept_permission_delete"),
    )

    action_type = models.CharField(max_length=50, choices=ACTION_CHOICES)
    snap_date = models.DateField(null=True, blank=True)
    lineid = models.CharField(max_length=20, blank=True, default="")
    processid = models.CharField(max_length=100, blank=True, default="")
    stepseq = models.CharField(max_length=100, blank=True, default="")
    recipeid = models.CharField(max_length=255, blank=True, default="")
    changed_department = models.CharField(max_length=255, blank=True, default="")
    changed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="facts_edit_history",
    )
    before_json = models.JSONField(default=dict, blank=True)
    after_json = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "facts_edit_history"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["created_at"], name="feh_created_idx"),
            models.Index(fields=["action_type", "created_at"], name="feh_ac_idx"),
            models.Index(fields=["snap_date", "lineid", "processid"], name="feh_slp_idx"),
            
        ]


class FactsLineMaster(models.Model):
    line_id = models.CharField("LINE_ID", max_length=50, unique=True)
    line_name = models.CharField("LINE명", max_length=100, blank=True, default="")
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "facts_line_master"
        verbose_name = "라인코드 기준정보"
        verbose_name_plural = "라인코드 기준정보"
        ordering = ["line_id"]
        indexes = [
            models.Index(fields=["line_id", "is_active"], name="flm_ia_idx"),
        ]

    def __str__(self):
        return f"{self.line_id} - {self.line_name}"


class FactsGuideDocument(models.Model):
    title = models.CharField(max_length=200, default="FACTS 사용 가이드")
    original_filename = models.CharField(max_length=255, blank=True, default="")
    stored_ppt_path = models.CharField(max_length=500, blank=True, default="")
    is_active = models.BooleanField(default=True)
    uploaded_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "facts_guide_document"
        verbose_name = "FACTS 사용 가이드"
        verbose_name_plural = "FACTS 사용 가이드"
        ordering = ["-updated_at", "-id"]
        indexes = [
            models.Index(fields=["is_active", "updated_at"], name="fgd_au_idx"),
        ]

    def __str__(self):
        return self.title


class FactsGuidePage(models.Model):
    guide = models.ForeignKey(
        "FactsGuideDocument",
        on_delete=models.CASCADE,
        related_name="pages",
    )
    page_no = models.PositiveIntegerField()
    image_path = models.CharField(max_length=500)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "facts_guide_page"
        verbose_name = "FACTS 사용 가이드 페이지"
        verbose_name_plural = "FACTS 사용 가이드 페이지"
        ordering = ["page_no"]
        unique_together = [("guide", "page_no")]
        indexes = [
            models.Index(fields=["guide", "page_no"], name="fgp_gp_idx"),
        ]

    def __str__(self):
        return f"{self.guide_id} - {self.page_no}"


class FactsEqpModel(models.Model):
    load_id = models.CharField(max_length=64, blank=True, default="")
    loaded_at = models.DateTimeField(null=True, blank=True)
    snap_date = models.DateField()
    eqp_id = models.CharField(max_length=100)
    area_name = models.CharField(max_length=100, blank=True, default="")
    origin_line_id = models.CharField(max_length=100, blank=True, default="")
    eqp_model = models.CharField(max_length=200, blank=True, default="")

    class Meta:
        db_table = "facts_eqp_model"
        verbose_name = "EQP MODEL"
        verbose_name_plural = "EQP MODEL"
        ordering = ["-snap_date", "eqp_id"]
        indexes = [
            models.Index(fields=["snap_date", "eqp_id"], name="fem_se_idx"),
            models.Index(fields=["snap_date", "eqp_model"], name="fem_sm_idx"),
            models.Index(fields=["snap_date", "origin_line_id"], name="fem_sl_idx"),
        ]

    def __str__(self):
        return f"{self.eqp_id} / {self.eqp_model}"


class FactsPreventRuleMaster(models.Model):
    sort_order = models.IntegerField(default=0)
    prevent_days = models.IntegerField(unique=True, db_column="threshold_days")
    color_code = models.CharField(max_length=20, default="#5B8FF9")
    is_active = models.BooleanField(default=True)
    is_current = models.BooleanField(default=False, db_column="is_selected")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "facts_prevent_rule_master"
        verbose_name = "PREVENT 기준정보"
        verbose_name_plural = "PREVENT 기준정보"
        ordering = ["sort_order", "prevent_days", "id"]
        indexes = [
            models.Index(fields=["is_active", "sort_order", "prevent_days"], name="fprm_aop_idx"),
            models.Index(fields=["is_current", "is_active"], name="fprm_ca_idx"),
        ]

    def __str__(self):
        return f"{self.prevent_days}일"


class FactsDeptPermission(models.Model):
    sort_order = models.IntegerField(default=0)
    can_view = models.BooleanField(default=True)
    can_edit = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    is_readonly = models.BooleanField(default=False)
    dept = models.CharField(max_length=255, default="ALL")
    username = models.CharField(max_length=255, default="ALL")
    page_values = models.JSONField(default=list, blank=True, db_column="pages")
    page_permissions = models.JSONField(default=dict, blank=True)
    line_values = models.JSONField(default=list, blank=True, db_column="lines")
    prp_values = models.JSONField(default=list, blank=True, db_column="prps")
    page_code = models.CharField(max_length=100, default="", blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "facts_dept_access_rule"
        verbose_name = "부서 권한 기준정보"
        verbose_name_plural = "부서 권한 기준정보"
        ordering = ["sort_order", "dept", "id"]
        indexes = [
            models.Index(fields=["dept", "is_active"], name="fdp_da_idx"),
            models.Index(fields=["is_active", "sort_order"], name="fdp_as_idx"),
        ]

    def __str__(self):
        return f"{self.dept} / {self.username} / view={self.can_view} / edit={self.can_edit}"


class FactsAccessHistory(models.Model):
    page_code = models.CharField(max_length=100, blank=True, default="")
    path = models.CharField(max_length=500, blank=True, default="")
    method = models.CharField(max_length=20, blank=True, default="GET")
    username = models.CharField(max_length=150, blank=True, default="")
    sabun = models.CharField(max_length=100, blank=True, default="")
    department = models.CharField(max_length=255, blank=True, default="")
    lineid = models.CharField(max_length=20, blank=True, default="")
    processid = models.CharField(max_length=100, blank=True, default="")
    snap_date = models.DateField(blank=True, null=True)
    query_string = models.TextField(blank=True, default="")
    ip_address = models.CharField(max_length=100, blank=True, default="")
    accessed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "facts_access_history"
        ordering = ["-accessed_at"]
        indexes = [
            models.Index(fields=["page_code", "accessed_at"], name="fah_pa_idx"),
            models.Index(fields=["username", "accessed_at"], name="fah_ua_idx"),
            models.Index(fields=["department", "accessed_at"], name="fah_da_idx"),
        ]


class FactsDepartmentMaster(models.Model):
    department = models.CharField(max_length=255, unique=True)

    class Meta:
        db_table = "facts_department_master"
        verbose_name = "부서 마스터"
        verbose_name_plural = "부서 마스터"
        ordering = ["department", "id"]
        managed = False


class FactsFilterCache(models.Model):
    snap_date = models.DateField(db_index=True)
    lineid = models.CharField(max_length=20, blank=True, default="", db_index=True)
    processid = models.CharField(max_length=100, blank=True, default="", db_index=True)
    areaname = models.CharField(max_length=100, blank=True, default="", db_index=True)
    layerid = models.CharField(max_length=100, blank=True, default="", db_index=True)
    stepseq = models.CharField(max_length=100, blank=True, default="", db_index=True)
    stepseq_type = models.CharField(max_length=50, blank=True, default="", db_index=True)
    descript = models.CharField(max_length=255, blank=True, default="")
    recipeid = models.CharField(max_length=255, blank=True, default="")

    body_flag = models.CharField(max_length=10, blank=True, default="", db_index=True)
    cham_flag = models.CharField(max_length=10, blank=True, default="", db_index=True)
    compat_type = models.CharField(max_length=20, blank=True, default="", db_index=True)
    always_flag = models.CharField(max_length=10, blank=True, default="", db_index=True)
    major_flag = models.CharField(max_length=10, blank=True, default="", db_index=True)
    plan_flag = models.CharField(max_length=10, blank=True, default="", db_index=True)

    built_at = models.DateTimeField()
    updated_at = models.DateTimeField()

    class Meta:
        db_table = "facts_filter_cache"
        constraints = [
            models.UniqueConstraint(
                fields=["snap_date", "lineid", "processid", "stepseq"],
                name="uq_facts_filter_cache_step",
            ),
        ]
        indexes = [
            models.Index(
                fields=["snap_date", "lineid", "processid"],
                name="ffc_snap_line_prp_idx",
            ),
            models.Index(
                fields=["snap_date", "lineid", "processid", "areaname"],
                name="ffc_snap_line_prp_area_idx",
            ),
            models.Index(
                fields=["snap_date", "lineid", "processid", "layerid"],
                name="ffc_snap_line_prp_layer_idx",
            ),
            models.Index(
                fields=["snap_date", "lineid", "processid", "stepseq"],
                name="ffc_snap_line_prp_step_idx",
            ),
            models.Index(
                fields=[
                    "snap_date",
                    "lineid",
                    "processid",
                    "areaname",
                    "layerid",
                    "stepseq_type",
                    "body_flag",
                    "cham_flag",
                    "compat_type",
                    "always_flag",
                    "major_flag",
                    "plan_flag",
                ],
                name="ffc_snap_filters_idx",
            ),
        ]

    def __str__(self):
        return f"{self.snap_date} | {self.lineid} | {self.processid} | {self.stepseq}"
    


class FactsFilterOptionCache(models.Model):
    snap_date = models.DateField(db_index=True)
    cache_type = models.CharField(max_length=30, db_index=True)
    lineid = models.CharField(max_length=20, blank=True, default="", db_index=True)
    processid = models.CharField(max_length=100, blank=True, default="", db_index=True)
    areaname = models.CharField(max_length=100, blank=True, default="", db_index=True)
    layerid = models.CharField(max_length=100, blank=True, default="", db_index=True)
    stepseq_type = models.CharField(max_length=50, blank=True, default="", db_index=True)
    body_flag = models.CharField(max_length=10, blank=True, default="", db_index=True)
    cham_flag = models.CharField(max_length=10, blank=True, default="", db_index=True)
    compat_type = models.CharField(max_length=20, blank=True, default="", db_index=True)
    always_flag = models.CharField(max_length=10, blank=True, default="", db_index=True)
    major_flag = models.CharField(max_length=10, blank=True, default="", db_index=True)
    plan_flag = models.CharField(max_length=10, blank=True, default="", db_index=True)

    line_options_json = models.TextField(blank=True, default="")
    prp_options_json = models.TextField(blank=True, default="")
    area_options_json = models.TextField(blank=True, default="")
    layer_options_json = models.TextField(blank=True, default="")
    step_options_json = models.TextField(blank=True, default="")
    type_options_json = models.TextField(blank=True, default="")

    built_at = models.DateTimeField()
    updated_at = models.DateTimeField()

    class Meta:
        db_table = "facts_filter_option_cache"
        constraints = [
            models.UniqueConstraint(
                fields=[
                    "snap_date",
                    "cache_type",
                    "lineid",
                    "processid",
                    "areaname",
                    "layerid",
                    "stepseq_type",
                    "body_flag",
                    "cham_flag",
                    "compat_type",
                    "always_flag",
                    "major_flag",
                    "plan_flag",
                ],
                name="uq_facts_filter_option_cache_scope",
            ),
        ]


class FactsDashboardGraphCache(models.Model):
    snap_date = models.DateField(db_index=True)
    lineid = models.CharField(max_length=20, blank=True, default="", db_index=True)
    processid = models.CharField(max_length=100, blank=True, default="", db_index=True)
    areaname = models.CharField(max_length=100, blank=True, default="", db_index=True)
    layer_key = models.CharField(max_length=512, blank=True, default="")
    include_measure = models.BooleanField(default=True)
    include_emergency = models.BooleanField(default=True)
    exclude_skiprule_100 = models.BooleanField(default=False)
    tip_mode = models.BooleanField(default=False)
    target_monthly = models.DecimalField(max_digits=7, decimal_places=2, null=True, blank=True)
    summary_json = models.JSONField(default=dict, blank=True)
    combined_series_json = models.JSONField(default=dict, blank=True)
    cache_version = models.CharField(max_length=50, blank=True, default="v1")
    built_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "facts_dashboard_graph_cache"
        constraints = [
            models.UniqueConstraint(
                fields=[
                    "snap_date",
                    "lineid",
                    "processid",
                    "areaname",
                    "layer_key",
                    "include_measure",
                    "include_emergency",
                    "exclude_skiprule_100",
                    "tip_mode",
                ],
                name="uq_facts_dashboard_graph_cache_scope",
            ),
        ]
        indexes = [
            models.Index(
                fields=["snap_date", "lineid", "processid", "areaname"],
                name="fdgc_snap_lpap_idx",
            ),
        ]




class FactsDashboardMetricDaily(models.Model):
    snap_date = models.DateField(db_index=True)
    lineid = models.CharField(max_length=20, blank=True, default="", db_index=True)
    processid = models.CharField(max_length=100, blank=True, default="", db_index=True)
    areaname = models.CharField(max_length=100, blank=True, default="", db_index=True)
    layer_key = models.CharField(max_length=512, blank=True, default="")
    scope_hash = models.CharField(max_length=64, blank=True, default="", db_index=True)
    condition_key = models.CharField(max_length=32, blank=True, default="", db_index=True)
    include_measure = models.BooleanField(default=True)
    include_emergency = models.BooleanField(default=True)
    exclude_skiprule_100 = models.BooleanField(default=False)
    tip_mode = models.BooleanField(default=False)
    metric_type = models.CharField(max_length=20, default="compat", db_index=True)
    metric_value = models.DecimalField(max_digits=8, decimal_places=3, null=True, blank=True)
    numerator = models.IntegerField(default=0)
    denominator = models.IntegerField(default=0)
    total_steps = models.IntegerField(default=0)
    compatible_steps = models.IntegerField(default=0)
    body_cnt = models.IntegerField(default=0)
    cham_cnt = models.IntegerField(default=0)
    single_cnt = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "facts_dashboard_metric_daily"
        constraints = [
            models.UniqueConstraint(
                fields=["snap_date", "scope_hash", "condition_key", "metric_type"],
                name="uq_facts_dashboard_metric_daily_scope",
            ),
        ]
        indexes = [
            models.Index(fields=["snap_date", "scope_hash"], name="fdmd_snap_scope_idx"),
        ]


class FactsVocPost(models.Model):
    title = models.CharField(max_length=255)
    content = models.TextField()
    username = models.CharField(max_length=150, blank=True, default="")
    department = models.CharField(max_length=255, blank=True, default="")
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="facts_voc_posts")
    is_notice = models.BooleanField(default=False)
    official_answer = models.TextField(blank=True, default="")
    official_answer_status = models.ForeignKey(
        "FactsVocAnswerStatusMaster",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="voc_posts",
    )
    official_answer_by = models.CharField(max_length=150, blank=True, default="")
    official_answer_department = models.CharField(max_length=255, blank=True, default="")
    official_answer_at = models.DateTimeField(null=True, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "facts_voc_post"
        ordering = ["-created_at", "-id"]
        indexes = [
            models.Index(fields=["is_active", "is_notice", "created_at"], name="fvp_anc_idx"),
            models.Index(fields=["username", "created_at"], name="fvp_uc_idx"),
        ]

    def __str__(self):
        return f"{self.title} ({self.username})"


class FactsVocComment(models.Model):
    post = models.ForeignKey("FactsVocPost", on_delete=models.CASCADE, related_name="comments")
    username = models.CharField(max_length=150, blank=True, default="")
    department = models.CharField(max_length=255, blank=True, default="")
    content = models.TextField()
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="facts_voc_comments")
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "facts_voc_comment"
        ordering = ["created_at", "id"]
        indexes = [
            models.Index(fields=["post", "is_active", "created_at"], name="fvc_pac_idx"),
            models.Index(fields=["username", "created_at"], name="fvc_uc_idx"),
        ]

    def __str__(self):
        return f"{self.post_id} / {self.username}"


class FactsVocAnswerStatusMaster(models.Model):
    status_name = models.CharField(max_length=100, unique=True)
    sort_order = models.IntegerField(default=0)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "facts_voc_answer_status_master"
        ordering = ["sort_order", "id"]
        indexes = [
            models.Index(fields=["is_active", "sort_order"], name="fvas_as_idx"),
        ]

    def __str__(self):
        return self.status_name


class FactsHistorySummaryCache(models.Model):
    summary_date = models.DateField(db_index=True)
    lineid = models.CharField(max_length=20, blank=True, default="", db_index=True)
    processid = models.CharField(max_length=100, blank=True, default="", db_index=True)
    include_measure = models.BooleanField(default=True)
    include_emergency = models.BooleanField(default=True)
    exclude_skiprule_100 = models.BooleanField(default=False)
    payload_json = models.JSONField(default=dict, blank=True)
    built_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "facts_history_summary_cache"
        constraints = [
            models.UniqueConstraint(
                fields=[
                    "summary_date",
                    "lineid",
                    "processid",
                    "include_measure",
                    "include_emergency",
                    "exclude_skiprule_100",
                ],
                name="uq_facts_history_summary_cache_scope",
            ),
        ]
        indexes = [
            models.Index(fields=["summary_date", "lineid", "processid"], name="fhsc_dlp_idx"),
        ]
