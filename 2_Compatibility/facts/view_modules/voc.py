from .common import (
    FactsAccessHistory,
    FactsVocAnswerStatusMaster,
    FactsVocComment,
    FactsVocPost,
    OperationalError,
    ProgrammingError,
    _check_page_permission,
    _ensure_browser_close_session,
    _get_actor,
    _get_request_department,
    _get_request_login_id,
    _popup_redirect,
    _record_access_history,
    get_object_or_404,
    login_required,
    redirect,
    render,
    services,
)


def _render_voc_table_missing(request, inquiry_contact, page_title="VOC 게시판"):
    return render(
        request,
        "facts/voc_list.html",
        {
            "page_title": page_title,
            "posts": [],
            "inquiry_contact": inquiry_contact,
            "table_missing_message": "VOC 게시판 테이블이 아직 생성되지 않았습니다. 테스트 DB에서 migration 적용이 필요합니다.",
            "filter_type": "all",
            "filter_status": "all",
            "filter_answer_status": "",
            "answer_status_options": [],
            "is_voc_admin": False,
        },
    )


def _resolve_login_and_department_for_voc(request):
    username = (_get_request_login_id(request) or "").strip()
    department = (_get_request_department(request) or "").strip()

    if not username:
        username = (request.session.get("sso_login_id") or "").strip()
    if not department:
        department = (request.session.get("sso_dept_name") or "").strip()

    if not department and username:
        latest = FactsAccessHistory.objects.filter(username=username).order_by("-accessed_at", "-id").first()
        if latest:
            department = (latest.department or "").strip()
    return username, department


def _is_voc_admin(request):
    user = getattr(request, "user", None)
    if bool(user and user.is_authenticated and (user.is_staff or user.is_superuser)):
        return True
    return _check_page_permission(request, "voc", require_edit=True, ignore_blank_scope=True) is None


@login_required
def voc_list_view(request):
    _ensure_browser_close_session(request)
    permission_response = _check_page_permission(request, "voc", ignore_blank_scope=True)
    if permission_response is not None:
        return permission_response
    _record_access_history(request, "voc")

    cfg = services.get_dashboard_config()
    inquiry_contact = cfg.inquiry_contact if hasattr(cfg, "inquiry_contact") else cfg["inquiry_contact"]
    filter_tab = (request.GET.get("tab") or "all").strip()
    filter_status = (request.GET.get("status") or "all").strip()
    is_admin = _is_voc_admin(request)

    try:
        posts = FactsVocPost.objects.filter(is_active=True).select_related("official_answer_status")
        if filter_tab == "notice":
            posts = posts.filter(is_notice=True)
        elif filter_tab == "general":
            posts = posts.filter(is_notice=False)

        if filter_status == "answered":
            posts = posts.exclude(official_answer_status__isnull=True)
        elif filter_status == "pending":
            posts = posts.filter(official_answer_status__isnull=True)
        elif filter_status.isdigit():
            posts = posts.filter(official_answer_status_id=int(filter_status))

        posts = posts.order_by("-is_notice", "-created_at", "-id")
        answer_status_options = list(FactsVocAnswerStatusMaster.objects.order_by("sort_order", "id").values("id", "status_name", "is_active"))
    except (ProgrammingError, OperationalError):
        return _render_voc_table_missing(request, inquiry_contact)

    return render(
        request,
        "facts/voc_list.html",
        {
            "page_title": "VOC 게시판",
            "posts": posts,
            "inquiry_contact": inquiry_contact,
            "filter_tab": filter_tab,
            "filter_status": filter_status,
            "answer_status_options": answer_status_options,
            "is_voc_admin": is_admin,
        },
    )


@login_required
def voc_new_view(request):
    _ensure_browser_close_session(request)
    _record_access_history(request, "voc")
    permission_response = _check_page_permission(request, "voc", ignore_blank_scope=True)
    if permission_response is not None:
        return permission_response

    username, department = _resolve_login_and_department_for_voc(request)
    is_admin = _is_voc_admin(request)
    answer_status_options = list(FactsVocAnswerStatusMaster.objects.filter(is_active=True).order_by("sort_order", "id"))
    edit_id = (request.GET.get("edit_id") or request.POST.get("edit_id") or "").strip()
    try:
        post = get_object_or_404(FactsVocPost, id=edit_id, is_active=True) if edit_id else None
    except (ProgrammingError, OperationalError):
        cfg = services.get_dashboard_config()
        inquiry_contact = cfg.inquiry_contact if hasattr(cfg, "inquiry_contact") else cfg["inquiry_contact"]
        return _render_voc_table_missing(request, inquiry_contact, page_title="VOC 작성")

    if post and post.username != username and not is_admin:
        edit_permission = _check_page_permission(request, "voc", require_edit=True, popup=True, ignore_blank_scope=True)
        if edit_permission is not None:
            return edit_permission

    if request.method == "POST":
        title = (request.POST.get("title") or "").strip()
        content = (request.POST.get("content") or "").strip()
        requested_notice = request.POST.get("is_notice") == "1"
        if requested_notice and not is_admin:
            return _popup_redirect("공지사항 등록 권한이 없습니다.", "/facts/voc/new/")
        is_notice = bool(is_admin and requested_notice)
        if not title or not content:
            return _popup_redirect("제목/내용은 필수입니다.", "/facts/voc/new/")
        if post:
            post.title = title
            post.content = content
            post.department = department
            post.is_notice = is_notice if is_admin else post.is_notice
            post.save(update_fields=["title", "content", "department", "is_notice", "updated_at"])
            return redirect("facts:voc_detail", post_id=post.id)
        try:
            new_post = FactsVocPost.objects.create(
                title=title,
                content=content,
                username=username,
                department=department,
                created_by=_get_actor(request),
                is_notice=is_notice,
                is_active=True,
            )
        except (ProgrammingError, OperationalError):
            cfg = services.get_dashboard_config()
            inquiry_contact = cfg.inquiry_contact if hasattr(cfg, "inquiry_contact") else cfg["inquiry_contact"]
            return _render_voc_table_missing(request, inquiry_contact, page_title="VOC 작성")
        return redirect("facts:voc_detail", post_id=new_post.id)

    cfg = services.get_dashboard_config()
    inquiry_contact = cfg.inquiry_contact if hasattr(cfg, "inquiry_contact") else cfg["inquiry_contact"]
    return render(
        request,
        "facts/voc_form.html",
        {
            "page_title": "VOC 작성",
            "post": post,
            "inquiry_contact": inquiry_contact,
            "is_voc_admin": is_admin,
            "answer_status_options": answer_status_options,
        },
    )


@login_required
def voc_detail_view(request, post_id):
    _ensure_browser_close_session(request)
    permission_response = _check_page_permission(request, "voc", ignore_blank_scope=True)
    if permission_response is not None:
        return permission_response
    _record_access_history(request, "voc")

    try:
        post = get_object_or_404(FactsVocPost.objects.select_related("official_answer_status"), id=post_id, is_active=True)
    except (ProgrammingError, OperationalError):
        cfg = services.get_dashboard_config()
        inquiry_contact = cfg.inquiry_contact if hasattr(cfg, "inquiry_contact") else cfg["inquiry_contact"]
        return _render_voc_table_missing(request, inquiry_contact, page_title="VOC 상세")

    username, department = _resolve_login_and_department_for_voc(request)
    is_admin = _is_voc_admin(request)
    can_edit = post.username == username or is_admin
    can_manage_all_comments = bool(is_admin)

    if request.method == "POST":
        action = (request.POST.get("action") or "").strip()

        if action == "delete":
            if not can_edit:
                return _popup_redirect("삭제 권한이 없습니다.", f"/facts/voc/{post.id}/")
            post.is_active = False
            post.save(update_fields=["is_active", "updated_at"])
            return redirect("facts:voc")

        if action == "add_comment":
            content = (request.POST.get("comment_content") or "").strip()
            if not content:
                return _popup_redirect("댓글 내용을 입력하세요.", f"/facts/voc/{post.id}/")
            try:
                FactsVocComment.objects.create(
                    post=post,
                    username=username,
                    department=department,
                    content=content,
                    created_by=_get_actor(request),
                    is_active=True,
                )
            except (ProgrammingError, OperationalError):
                pass
            return redirect("facts:voc_detail", post_id=post.id)

        if action == "edit_comment":
            comment_id = (request.POST.get("comment_id") or "").strip()
            content = (request.POST.get("comment_content") or "").strip()
            target = FactsVocComment.objects.filter(id=comment_id, post=post, is_active=True).first()
            if target is None:
                return _popup_redirect("댓글을 찾을 수 없습니다.", f"/facts/voc/{post.id}/")
            can_manage = can_manage_all_comments or (target.username == username)
            if not can_manage:
                return _popup_redirect("댓글 수정 권한이 없습니다.", f"/facts/voc/{post.id}/")
            if not content:
                return _popup_redirect("댓글 내용을 입력하세요.", f"/facts/voc/{post.id}/")
            target.content = content
            target.department = department
            target.save(update_fields=["content", "department", "updated_at"])
            return redirect("facts:voc_detail", post_id=post.id)

        if action == "delete_comment":
            comment_id = (request.POST.get("comment_id") or "").strip()
            target = FactsVocComment.objects.filter(id=comment_id, post=post, is_active=True).first()
            if target is None:
                return _popup_redirect("댓글을 찾을 수 없습니다.", f"/facts/voc/{post.id}/")
            can_manage = can_manage_all_comments or (target.username == username)
            if not can_manage:
                return _popup_redirect("댓글 삭제 권한이 없습니다.", f"/facts/voc/{post.id}/")
            target.is_active = False
            target.save(update_fields=["is_active", "updated_at"])
            return redirect("facts:voc_detail", post_id=post.id)

        if action == "save_official_answer":
            if not is_admin:
                return _popup_redirect("공식답변 작성 권한이 없습니다.", f"/facts/voc/{post.id}/")
            answer = (request.POST.get("official_answer") or "").strip()
            status_id = (request.POST.get("official_answer_status_id") or "").strip()
            post.official_answer = answer
            if answer:
                post.official_answer_status = FactsVocAnswerStatusMaster.objects.filter(id=status_id).first()
                if post.official_answer_status is None:
                    post.official_answer_status = FactsVocAnswerStatusMaster.objects.filter(status_name="답변 확인").first()
            else:
                post.official_answer_status = None
            if answer:
                from django.utils import timezone

                post.official_answer_by = username
                post.official_answer_department = department
                post.official_answer_at = timezone.now()
            else:
                post.official_answer_by = ""
                post.official_answer_department = ""
                post.official_answer_at = None
            post.save(
                update_fields=[
                    "official_answer",
                    "official_answer_status",
                    "official_answer_by",
                    "official_answer_department",
                    "official_answer_at",
                    "updated_at",
                ]
            )
            return redirect("facts:voc_detail", post_id=post.id)

    try:
        comments = list(FactsVocComment.objects.filter(post=post, is_active=True).order_by("created_at", "id"))
    except (ProgrammingError, OperationalError):
        comments = []
    for c in comments:
        c.can_manage = bool(can_manage_all_comments or (c.username == username))

    cfg = services.get_dashboard_config()
    inquiry_contact = cfg.inquiry_contact if hasattr(cfg, "inquiry_contact") else cfg["inquiry_contact"]
    return render(
        request,
        "facts/voc_detail.html",
        {
            "page_title": "VOC 상세",
            "post": post,
            "comments": comments,
            "can_edit": can_edit,
            "can_delete": can_edit,
            "is_voc_admin": is_admin,
            "can_manage_all_comments": can_manage_all_comments,
            "is_answered": bool((post.official_answer or "").strip()),
            "answer_status_options": list(FactsVocAnswerStatusMaster.objects.filter(is_active=True).order_by("sort_order", "id")),
            "inquiry_contact": inquiry_contact,
        },
    )
