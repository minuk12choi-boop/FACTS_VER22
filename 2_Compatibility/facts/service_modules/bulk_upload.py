from .common import (
    SequenceMatcher,
    _get_eqp_model_qs_by_snap_or_latest_load,
    _parse_path_members,
    defaultdict,
    re,
)

def _extract_cham_tokens(raw_values):
    tokens = []
    for raw in raw_values:
        if raw is None:
            continue

        text = str(raw).strip()
        if not text:
            continue

        bracket_tokens = re.findall(r"\(([A-Za-z0-9_]+-[A-Za-z0-9_]+)\)", text)
        if bracket_tokens:
            tokens.extend(bracket_tokens)
            continue

        for part in [x.strip() for x in text.split(",") if str(x).strip()]:
            tokens.append(part)

    return tokens

def _compact_cham_tokens(tokens):
    grouped = defaultdict(list)
    passthrough = []

    for token in tokens:
        s = str(token or "").strip().upper()
        if not s:
            continue

        m = re.match(r"^([A-Z0-9_]+)-([A-Z0-9_]+)$", s)
        if not m:
            passthrough.append(s)
            continue

        body = m.group(1)
        cham = m.group(2)
        if cham not in grouped[body]:
            grouped[body].append(cham)

    result = []
    for body in sorted(grouped.keys()):
        suffixes = grouped[body]
        if len(suffixes) == 1:
            result.append(f"{body}-{suffixes[0]}")
        else:
            result.append(f"{body}-" + ";".join(suffixes))

    for p in passthrough:
        if p not in result:
            result.append(p)

    return ", ".join(result)

def _parse_eqpgroup_tokens(eqpgroup_text):
    if not eqpgroup_text:
        return []

    raw = str(eqpgroup_text).strip().upper()
    if raw == "":
        return []

    normalized = raw.replace("(", "").replace(")", "")
    normalized = normalized.replace(",", "_").replace(";", "_").replace(":", "_")
    parts = [x.strip() for x in normalized.split("_") if str(x).strip()]

    tokens = []
    for part in parts:
        s = str(part or "").strip().upper()
        if not s:
            continue
        if "-" in s:
            s = s.split("-", 1)[0].strip()
        if s and s not in tokens:
            tokens.append(s)
    return tokens

def _flatten_body_values(values):
    tokens = []
    for raw in values:
        for token in _parse_eqpgroup_tokens(raw):
            if token and token not in tokens:
                tokens.append(token)
    return tokens

def _normalize_path_text(path_text):
    raw = str(path_text or "").strip().upper()
    if not raw:
        return ""
    members = _parse_path_members(raw, "")
    parts = []
    for m in members:
        body = str(m.get("eqp_body_name") or "").strip().upper()
        cham = str(m.get("eqp_cham_name") or "").strip().upper()
        token = f"{body}-{cham}" if body and cham else body
        if token and token not in parts:
            parts.append(token)
    return ", ".join(parts)

def _parse_childeqp_groups(childeqp_text):
    text = str(childeqp_text or "").strip().upper()
    if not text:
        return []
    groups = []
    for group_text in [g.strip() for g in text.split(';') if g.strip()]:
        members = []
        for member in [m.strip() for m in group_text.split(':') if m.strip()]:
            body = member.split('-', 1)[0].strip()
            if body and body not in members:
                members.append(body)
        if members:
            groups.append(tuple(members))
    return groups

def _path_signature(row):
    path_text = _normalize_path_text(getattr(row, "path", "") or "")
    if path_text:
        return path_text
    groups = _parse_childeqp_groups(getattr(row, "childeqp", "") or "")
    if groups:
        return tuple(groups)
    path_members = _parse_path_members(getattr(row, "path", ""), getattr(row, "eqpgroup", ""))
    bodies = []
    for m in path_members:
        body = str(m.get("eqp_body_name") or "").strip().upper()
        if body and body not in bodies:
            bodies.append(body)
    return ", ".join(bodies)

def _normalize_model_text(value):
    s = str(value or "").strip().upper()
    s = re.sub(r"[\s\-_\/]", "", s)
    return s

def _common_prefix_len(a, b):
    n = min(len(a), len(b))
    cnt = 0
    for i in range(n):
        if a[i] == b[i]:
            cnt += 1
        else:
            break
    return cnt

def _model_similarity_score(base_model, candidate_model):
    base_raw = str(base_model or "").strip().upper()
    cand_raw = str(candidate_model or "").strip().upper()

    if not base_raw or not cand_raw:
        return 0.0
    if base_raw == cand_raw:
        return 1.0

    base_norm = _normalize_model_text(base_raw)
    cand_norm = _normalize_model_text(cand_raw)
    if not base_norm or not cand_norm:
        return 0.0

    if base_norm == cand_norm:
        return 0.98

    prefix_len = _common_prefix_len(base_norm, cand_norm)
    seq_score = SequenceMatcher(None, base_norm, cand_norm).ratio()

    if prefix_len >= 6 and seq_score >= 0.82:
        return max(seq_score, 0.90)
    if prefix_len >= 4 and seq_score >= 0.80:
        return max(seq_score, 0.84)
    if seq_score >= 0.92:
        return seq_score
    if seq_score >= 0.82:
        return seq_score

    return 0.0

def get_similar_model_eqp_candidates(snap_date, processid, stepseq, include_current=False):
    from .dashboard_rows import build_step_dataset

    step_rows = build_step_dataset(
        snap_date=snap_date,
        processid=processid,
        include_measure=True,
        include_emergency=True,
        exclude_skiprule_100=False,
        tip_mode=False,
        for_prp_table=True,
    )

    target_row = next(
        (
            row
            for row in step_rows
            if row["processid"] == processid
            and row["stepseq"] == stepseq
        ),
        None,
    )
    if not target_row:
        return {"base_eqps": [], "base_models": [], "recommendations": []}

    base_eqps = _parse_eqpgroup_tokens(target_row.get("eqpgroup", ""))
    if not base_eqps:
        return {"base_eqps": [], "base_models": [], "recommendations": []}

    eqp_model_qs = _get_eqp_model_qs_by_snap_or_latest_load(snap_date)

    base_model_rows = list(
        eqp_model_qs.filter(
            eqp_id__in=base_eqps,
        ).values("eqp_id", "origin_line_id", "eqp_model")
    )

    base_models = []
    for row in base_model_rows:
        eqp_model = str(row["eqp_model"] or "").strip()
        if eqp_model and eqp_model not in base_models:
            base_models.append(eqp_model)

    if not base_models:
        return {"base_eqps": base_eqps, "base_models": [], "recommendations": []}

    all_candidates = list(
        eqp_model_qs
        .exclude(eqp_model__isnull=True)
        .exclude(eqp_model="")
        .values("eqp_id", "origin_line_id", "eqp_model")
    )

    rec_map = {}
    for cand in all_candidates:
        eqp_id = str(cand["eqp_id"] or "").upper()
        if not eqp_id:
            continue
        if (not include_current) and eqp_id in base_eqps:
            continue

        cand_model = str(cand["eqp_model"] or "").strip()
        if not cand_model:
            continue

        best_score = 0.0
        best_base_model = ""
        for bm in base_models:
            score = _model_similarity_score(bm, cand_model)
            if score > best_score:
                best_score = score
                best_base_model = bm

        if best_score <= 0:
            continue

        base_norm = _normalize_model_text(best_base_model)
        cand_norm = _normalize_model_text(cand_model)

        if best_score >= 0.999:
            match_type = "완전일치"
        elif base_norm == cand_norm:
            match_type = "정규화일치"
        elif best_score >= 0.90:
            match_type = "강유사"
        elif best_score >= 0.82:
            match_type = "유사"
        else:
            continue

        item = {
            "eqp_id": eqp_id,
            "origin_line_id": str(cand["origin_line_id"] or ""),
            "eqp_model": cand_model,
            "match_type": match_type,
            "match_score": round(best_score, 4),
            "matched_base_model": best_base_model,
        }

        prev = rec_map.get(eqp_id)
        if prev is None or item["match_score"] > prev["match_score"]:
            rec_map[eqp_id] = item

    recommendations = list(rec_map.values())
    recommendations.sort(
        key=lambda x: (
            {"완전일치": 0, "정규화일치": 1, "강유사": 2, "유사": 3}.get(x["match_type"], 9),
            -x["match_score"],
            x["eqp_id"],
        )
    )

    return {
        "base_eqps": base_eqps,
        "base_models": base_models,
        "recommendations": recommendations,
    }
