def build_step_jump_chain(
    df_steptip: pd.DataFrame,
    df_path: pd.DataFrame,
) -> pd.DataFrame:
    """
    df_steptip + df_path 기준으로 processid별 'step 체인'만 남긴다.

    핵심:
    - raw row 기준이 아니라 processid + stepseq 기준으로 step을 먼저 유일화
    - 정렬 후 가장 앞 step부터 시작
    - 현재 step의 to_step_seq 와 같은 stepseq를 가진 뒤쪽 step으로 점프
    - 그 체인에 포함된 stepseq만 원본 df_steptip에서 남김

    Returns
    -------
    pd.DataFrame
        원본 df_steptip 기준 컬럼 + to_step_seq
        단, 체인에 포함된 stepseq들만 남긴 결과
    """

    required_steptip = {"processid", "stepseq"}
    required_path = {"proc_id", "step_seq", "to_step_seq"}

    missing_steptip = required_steptip - set(df_steptip.columns)
    missing_path = required_path - set(df_path.columns)

    if missing_steptip:
        raise ValueError(f"df_steptip에 필요한 컬럼이 없습니다: {sorted(missing_steptip)}")
    if missing_path:
        raise ValueError(f"df_path에 필요한 컬럼이 없습니다: {sorted(missing_path)}")

    steptip = df_steptip.copy()
    path = df_path.copy()

    # 문자열 안전화
    steptip["processid"] = steptip["processid"].astype(str)
    steptip["stepseq"] = steptip["stepseq"].astype(str)

    path["proc_id"] = path["proc_id"].astype(str)
    path["step_seq"] = path["step_seq"].astype(str)

    # to_step_seq는 NaN 보존
    path["to_step_seq"] = path["to_step_seq"].where(path["to_step_seq"].notna(), pd.NA)

    # 1) left join
    df = steptip.merge(
        path[["proc_id", "step_seq", "to_step_seq"]],
        how="left",
        left_on=["processid", "stepseq"],
        right_on=["proc_id", "step_seq"],
    )

    # 2) 공백 제거 비교용
    df["stepseq_clean"] = (
        df["stepseq"]
        .astype(str)
        .str.replace(" ", "", regex=False)
        .str.upper()
    )

    df["to_step_seq_clean"] = df["to_step_seq"].astype("string")
    df["to_step_seq_clean"] = df["to_step_seq_clean"].str.replace(" ", "", regex=False).str.upper()
    df.loc[df["to_step_seq"].isna(), "to_step_seq_clean"] = pd.NA

    # 자연정렬 키
    def sort_key(x: str):
        if pd.isna(x):
            return ("", float("inf"), "")

        s = str(x).replace(" ", "").upper()

        m = re.match(r"^([A-Z]*)(\d+)([A-Z]*)$", s)
        if m:
            return (m.group(1), int(m.group(2)), m.group(3))

        nums = re.findall(r"\d+", s)
        if nums:
            num = int(nums[0])
            prefix = re.sub(r"\d.*$", "", s)
            suffix_match = re.search(r"\d+([A-Z]*)$", s)
            suffix = suffix_match.group(1) if suffix_match else ""
            return (prefix, num, suffix)

        return (s, float("inf"), "")

    # 3) step 단위 유일화
    # 같은 processid + stepseq 에 대해 to_step_seq는 df_path 기준으로 사실상 1개여야 하므로 first 사용
    step_level = (
        df.groupby(["processid", "stepseq_clean"], as_index=False)
          .agg(
              stepseq=("stepseq", "first"),
              to_step_seq=("to_step_seq", "first"),
              to_step_seq_clean=("to_step_seq_clean", "first"),
          )
    )

    keys = step_level["stepseq"].map(sort_key)
    step_level["__p"] = keys.map(lambda x: x[0])
    step_level["__n"] = keys.map(lambda x: x[1])
    step_level["__s"] = keys.map(lambda x: x[2])

    step_level = step_level.sort_values(
        by=["processid", "__p", "__n", "__s", "stepseq_clean"],
        kind="mergesort"
    ).reset_index(drop=True)

    # 4) processid별 점프 체인 생성
    kept_pairs = []

    for processid, g in step_level.groupby("processid", sort=False):
        g = g.reset_index(drop=True)

        if g.empty:
            continue

        # stepseq_clean -> 정렬상 위치
        step_pos = {g.at[i, "stepseq_clean"]: i for i in range(len(g))}

        # 시작점: 정렬상 첫 step
        cur_pos = 0
        visited = set()

        while True:
            if cur_pos in visited:
                break

            visited.add(cur_pos)
            kept_pairs.append((processid, g.at[cur_pos, "stepseq_clean"]))

            target = g.at[cur_pos, "to_step_seq_clean"]

            if pd.isna(target) or target == "":
                break

            next_pos = step_pos.get(target)

            # 다음 target step이 없거나, 현재보다 앞/같은 위치면 종료
            if next_pos is None or next_pos <= cur_pos:
                break

            cur_pos = next_pos

    kept_df = pd.DataFrame(kept_pairs, columns=["processid", "stepseq_clean"]).drop_duplicates()

    # 5) 원본 row(df_steptip join 결과)에서 살아남은 stepseq만 남김
    out = df.merge(
        kept_df,
        how="inner",
        on=["processid", "stepseq_clean"]
    ).copy()

    # 정렬 보기 좋게
    out["__sort_tuple"] = out["stepseq"].map(sort_key)
    out["__p"] = out["__sort_tuple"].map(lambda x: x[0])
    out["__n"] = out["__sort_tuple"].map(lambda x: x[1])
    out["__s"] = out["__sort_tuple"].map(lambda x: x[2])

    out = out.sort_values(
        by=["processid", "__p", "__n", "__s", "stepseq_clean"],
        kind="mergesort"
    ).reset_index(drop=True)

    out = out[df_steptip.columns.tolist()].copy()

    return out



def build_b_table_from_a(
    df_final: pd.DataFrame,
    days_threshold: int = 30,
    now_ts=None,
) -> pd.DataFrame:
    """
    a(df_final) 테이블을 b 테이블 형태로 변환한다.

    입력 a 컬럼
    ----------
    [
        processid, category, skiprule, areaname, eqptype, layerid, lineid,
        stepseq_type, stepseq, descript, recipeid, batch_kind,
        eqpcham, eqpid, chamberid, prevent, type_body, type_cham,
        eventtime, childeqp, eqpline
    ]

    출력 b 컬럼
    ----------
    [
        processid, category, skiprule, areaname, eqptype, layerid, lineid,
        stepseq_type, stepseq, descript, recipeid, batch_kind,
        eqpgroup, 상시/비상시,
        Body호환, Cham호환,
        Body호환확보수, Cham호환확보수,
        Body호환_TIP고려, Cham호환_TIP고려,
        Body호환확보수_TIP고려, Cham호환확보수_TIP고려,
        prevent, tip, path, eventtime, childeqp, eqpline
    ]
    """

    required_cols = [
        "processid", "category", "skiprule", "areaname", "eqptype", "layerid", "lineid",
        "stepseq_type", "stepseq", "descript", "recipeid", "batch_kind",
        "eqpcham", "eqpid", "chamberid", "prevent", "type_body", "type_cham",
        "eventtime", "childeqp", "eqpline",
    ]
    missing = [c for c in required_cols if c not in df_final.columns]
    if missing:
        raise ValueError(f"필수 컬럼 누락: {missing}")

    if now_ts is None:
        now_ts = pd.Timestamp.now()
    else:
        now_ts = pd.Timestamp(now_ts)

    df = df_final.copy()

    # ------------------------------------------------------------------
    # 공통 전처리
    # ------------------------------------------------------------------
    def blank_to_nan(x):
        if pd.isna(x):
            return np.nan
        s = str(x).strip()
        return s if s else np.nan

    text_cols = [
        "processid", "category", "skiprule", "areaname", "eqptype", "layerid", "lineid",
        "stepseq_type", "stepseq", "descript", "recipeid", "batch_kind",
        "eqpcham", "eqpid", "chamberid", "prevent", "type_body", "type_cham",
        "childeqp", "eqpline",
    ]
    for c in text_cols:
        df[c] = df[c].map(blank_to_nan)

    df["skiprule"] = df["skiprule"].map(lambda x: np.nan if x is False else x)
    df["eventtime"] = pd.to_datetime(df["eventtime"], errors="coerce")

    # null -> DOING
    df["prevent_logic"] = df["prevent"].fillna("DOING")
    df["type_body_logic"] = df["type_body"].fillna("DOING")
    df["type_cham_logic"] = df["type_cham"].fillna("DOING")

    # 내부 정렬용
    df["_sort_eqpcham"] = df["eqpcham"].map(lambda x: "" if pd.isna(x) else str(x).strip())

    # ------------------------------------------------------------------
    # 유틸
    # ------------------------------------------------------------------
    def unique_keep_order(values):
        out = []
        seen = set()
        for v in values:
            if pd.isna(v):
                continue
            sv = str(v).strip()
            if not sv:
                continue
            if sv not in seen:
                seen.add(sv)
                out.append(sv)
        return out

    def unique_concat_by_frame_order(frame: pd.DataFrame, value_col: str, sep="_"):
        vals = unique_keep_order(frame[value_col].tolist())
        return sep.join(vals) if vals else np.nan

    def unique_concat_sorted(values_or_series, sep="_"):
        if isinstance(values_or_series, pd.Series):
            values = values_or_series.dropna().astype(str).tolist()
        else:
            values = [str(v) for v in values_or_series if pd.notna(v)]
        vals = sorted(set(values))
        return sep.join(vals) if vals else np.nan

    def unique_concat_sorted_eqpline(values_or_series, sep="_"):
        if isinstance(values_or_series, pd.Series):
            values = values_or_series.tolist()
        else:
            values = list(values_or_series)

        vals = unique_keep_order(values)
        if not vals:
            return np.nan

        vals_no_pfr1 = sorted([v for v in vals if v != "PFR1"])
        vals_sorted = (["PFR1"] if "PFR1" in vals else []) + vals_no_pfr1
        return sep.join(vals_sorted)

    def unique_concat_text(values, sep=", "):
        vals = []
        seen = set()
        for v in values:
            if pd.isna(v):
                continue
            sv = str(v).strip()
            if not sv:
                continue
            if sv not in seen:
                seen.add(sv)
                vals.append(sv)
        return sep.join(vals) if vals else np.nan

    def distinct_non_null(series: pd.Series):
        return sorted(set([str(x).strip() for x in series.dropna() if str(x).strip() != ""]))

    def first_non_null(series: pd.Series):
        for v in series:
            if pd.notna(v):
                return v
        return np.nan

    def non_empty_subsets_keep_order(tokens):
        out = []
        for r in range(1, len(tokens) + 1):
            out.extend(combinations(tokens, r))
        return out

    def format_path(stage_combo):
        return " | ".join([f"({', '.join(stage)})" for stage in stage_combo])

    def path_sort_key(stage_combo):
        total_cnt = sum(len(stage) for stage in stage_combo)
        stage_lens = tuple(len(stage) for stage in stage_combo)
        stage_text = tuple(",".join(stage) for stage in stage_combo)
        return (total_cnt, stage_lens, stage_text)

    def parse_eqpline_tokens(v):
        if pd.isna(v):
            return []
        return [x.strip() for x in str(v).split("_") if x.strip()]

    def is_p_line(v: str) -> bool:
        return str(v).startswith("P")

    def min_eqpcham_in_rows(frame: pd.DataFrame):
        vals = [str(v).strip() for v in frame["eqpcham"].dropna().tolist() if str(v).strip()]
        return min(vals) if vals else np.nan

    def calc_group_eventtime(g: pd.DataFrame):
        evt_prevent = g.loc[g["prevent_logic"] == "PREVENT", "eventtime"].dropna()
        if not evt_prevent.empty:
            return evt_prevent.max()
        evt_all = g["eventtime"].dropna()
        return evt_all.max() if not evt_all.empty else pd.NaT

    def parse_path_stages(path_str: str):
        """
        '(A, B) | (C)' -> [['A', 'B'], ['C']]
        '(EQ1-1)'      -> [['EQ1-1']]
        """
        if pd.isna(path_str):
            return []

        s = str(path_str).strip()
        if not s or s.startswith("ERROR:"):
            return []

        matches = re.findall(r"\((.*?)\)", s)
        out = []
        for m in matches:
            tokens = [x.strip() for x in m.split(",") if x.strip()]
            out.append(tokens)
        return out

    def union_stage_candidates_from_paths(path_series: pd.Series):
        """
        동일 body(eqpid) 그룹의 여러 path를 보고 stage index별 후보 chamber 집합 복원
        예:
        (A) | (C)
        (B) | (C)
        (A, B) | (C)
        -> stage1 = {A, B}, stage2 = {C}
        """
        stage_sets = []
        unique_paths = []
        seen = set()

        for p in path_series.dropna().astype(str):
            p = p.strip()
            if not p or p.startswith("ERROR:"):
                continue
            if p not in seen:
                seen.add(p)
                unique_paths.append(p)

        for p in unique_paths:
            stages = parse_path_stages(p)
            for i, stage_tokens in enumerate(stages):
                if i >= len(stage_sets):
                    stage_sets.append(set())
                stage_sets[i].update(stage_tokens)

        return stage_sets

    def make_error_message(keys, expr, existing_chambers, reason):
        key_names = ["lineid", "processid", "stepseq", "recipeid", "eqpid"]
        key_txt = ", ".join([f"{k}={v}" for k, v in zip(key_names, keys)])
        chamber_txt = ", ".join(existing_chambers) if existing_chambers else "없음"
        expr_txt = expr if pd.notna(expr) else "NULL"
        return f"ERROR: {reason} [group: {key_txt}] [childeqp: {expr_txt}] [available eqpcham: {chamber_txt}]"

    def make_error_row(template_row: pd.Series, eqpgroup_val, eqpline_val, eventtime_val, path_error_msg, sort_eqpcham_val):
        row = {
            "processid": template_row["processid"],
            "category": template_row["category"],
            "skiprule": template_row["skiprule"],
            "areaname": template_row["areaname"],
            "eqptype": template_row["eqptype"],
            "layerid": template_row["layerid"],
            "lineid": template_row["lineid"],
            "stepseq_type": template_row["stepseq_type"],
            "stepseq": template_row["stepseq"],
            "descript": template_row["descript"],
            "recipeid": template_row["recipeid"],
            "batch_kind": template_row["batch_kind"],
            "eqpid": template_row["eqpid"],
            "eqpgroup": eqpgroup_val,
            "eqpline": eqpline_val,
            "path": path_error_msg,
            "prevent": "ERROR",
            "tip": np.nan,
            "eventtime": eventtime_val,
            "childeqp": template_row["childeqp"],
            "_sort_eqpcham_final": sort_eqpcham_val,
        }
        return pd.DataFrame([row])

    # ------------------------------------------------------------------
    # eqpgroup 사전 계산
    # 기준: (lineid, processid, stepseq, recipeid)
    # ------------------------------------------------------------------
    metric_group_cols = ["lineid", "processid", "stepseq", "recipeid"]
    eqpgroup_map = {}

    for gkeys, g in df.groupby(metric_group_cols, sort=False, dropna=False):
        g_sorted = g.sort_values(by=["_sort_eqpcham", "eqpid"], kind="mergesort", na_position="last")
        eqpgroup_map[gkeys] = unique_concat_by_frame_order(g_sorted, "eqpid", sep="_")

    # ------------------------------------------------------------------
    # path 생성 단계
    # path group: (lineid, processid, stepseq, recipeid, eqpid)
    # ------------------------------------------------------------------
    path_group_cols = ["lineid", "processid", "stepseq", "recipeid", "eqpid"]
    path_rows = []

    for keys, g in df.groupby(path_group_cols, sort=False, dropna=False):
        g = g.copy().sort_values(by=["_sort_eqpcham"], kind="mergesort", na_position="last").reset_index(drop=True)
        template = g.iloc[0]

        lineid_val, processid_val, stepseq_val, recipeid_val, eqpid_val = keys
        eqpgroup_val = eqpgroup_map.get((lineid_val, processid_val, stepseq_val, recipeid_val), np.nan)
        group_eventtime = calc_group_eventtime(g)
        eqpline_val = unique_concat_sorted_eqpline(g["eqpline"], sep="_")

        chamber_groups = {}
        for cham, sub in g.groupby("eqpcham", sort=False, dropna=False):
            if pd.isna(cham):
                continue
            chamber_groups[cham] = sub.copy().sort_values(by=["_sort_eqpcham"], kind="mergesort", na_position="last")

        existing_chambers = list(chamber_groups.keys())
        child_vals = unique_keep_order(g["childeqp"].tolist())

        # chamber / stage / path 상태판단
        def get_chamber_prevent(sub: pd.DataFrame):
            vals = sub["prevent_logic"].dropna().astype(str).tolist()
            if "DOING" in vals:
                return "DOING"
            if "PREVENT" in vals:
                return "PREVENT"
            return "미등록"

        def get_stage_prevent(stage_subset, chamber_group_map):
            chamber_results = []
            for cham in stage_subset:
                sub = chamber_group_map.get(cham)
                if sub is None or sub.empty:
                    chamber_results.append("미등록")
                else:
                    chamber_results.append(get_chamber_prevent(sub))

            if "DOING" in chamber_results:
                return "DOING"
            if "PREVENT" in chamber_results:
                return "PREVENT"
            return "미등록"

        def get_path_prevent(stage_combo, chamber_group_map):
            stage_results = [get_stage_prevent(stage_subset, chamber_group_map) for stage_subset in stage_combo]
            if all(x == "DOING" for x in stage_results):
                return "DOING"
            if "PREVENT" in stage_results:
                return "PREVENT"
            return "미등록"

        def collect_selected_rows(stage_combo, chamber_group_map):
            selected = []
            seen = set()
            for stage_subset in stage_combo:
                for cham in stage_subset:
                    if cham in seen:
                        continue
                    seen.add(cham)
                    sub = chamber_group_map.get(cham)
                    if sub is not None and not sub.empty:
                        selected.append(sub)

            if selected:
                out = pd.concat(selected, ignore_index=True)
                out = out.sort_values(by=["_sort_eqpcham"], kind="mergesort", na_position="last").reset_index(drop=True)
                return out
            return pd.DataFrame(columns=g.columns)

        def build_tip_from_selected_rows(selected_rows: pd.DataFrame, final_prevent_value):
            if final_prevent_value != "PREVENT":
                return np.nan
            if selected_rows.empty:
                return np.nan

            body_prevent_rows = selected_rows[selected_rows["type_body_logic"] == "PREVENT"]
            if not body_prevent_rows.empty:
                targets = unique_concat_text(body_prevent_rows["eqpid"].tolist(), sep=", ")
                return f"PREVENT: {targets}" if pd.notna(targets) else "PREVENT"

            cham_prevent_rows = selected_rows[selected_rows["type_cham_logic"] == "PREVENT"]
            if not cham_prevent_rows.empty:
                targets = unique_concat_text(cham_prevent_rows["eqpcham"].tolist(), sep=", ")
                return f"PREVENT: {targets}" if pd.notna(targets) else "PREVENT"

            return np.nan

        # childeqp 없음
        if len(child_vals) == 0:
            for cham, sub in chamber_groups.items():
                final_prevent_value = get_chamber_prevent(sub)
                final_tip = build_tip_from_selected_rows(sub, final_prevent_value)
                sort_eqpcham_val = min_eqpcham_in_rows(sub)
                eventtime_val = calc_group_eventtime(sub)

                row = {
                    "processid": template["processid"],
                    "category": template["category"],
                    "skiprule": template["skiprule"],
                    "areaname": template["areaname"],
                    "eqptype": template["eqptype"],
                    "layerid": template["layerid"],
                    "lineid": template["lineid"],
                    "stepseq_type": template["stepseq_type"],
                    "stepseq": template["stepseq"],
                    "descript": template["descript"],
                    "recipeid": template["recipeid"],
                    "batch_kind": template["batch_kind"],
                    "eqpid": template["eqpid"],
                    "eqpgroup": eqpgroup_val,
                    "eqpline": unique_concat_sorted_eqpline(sub["eqpline"], sep="_"),
                    "path": f"({cham})",
                    "prevent": final_prevent_value,
                    "tip": final_tip,
                    "eventtime": eventtime_val,
                    "childeqp": first_non_null(sub["childeqp"]),
                    "_sort_eqpcham_final": sort_eqpcham_val,
                }
                path_rows.append(row)
            continue

        # childeqp 여러 개 -> 에러
        if len(child_vals) > 1:
            path_error_msg = make_error_message(
                keys=keys,
                expr=" || ".join(child_vals),
                existing_chambers=existing_chambers,
                reason=f"동일 path group 내 childeqp 값이 여러 개 존재함 ({len(child_vals)}개)",
            )
            path_rows.append(
                make_error_row(
                    template_row=template,
                    eqpgroup_val=eqpgroup_val,
                    eqpline_val=eqpline_val,
                    eventtime_val=group_eventtime,
                    path_error_msg=path_error_msg,
                    sort_eqpcham_val=min_eqpcham_in_rows(g),
                ).iloc[0].to_dict()
            )
            continue

        # childeqp 1개 -> path 생성
        expr = child_vals[0]

        try:
            raw_stages = [s.strip() for s in str(expr).split(":") if s.strip()]
            if not raw_stages:
                raise ValueError("childeqp 구문 해석 결과 stage가 비어 있음")

            stage_available_subsets = []
            parsed_stage_info = []

            for stage in raw_stages:
                raw_tokens = [t.strip() for t in stage.split(";") if t.strip()]
                if not raw_tokens:
                    raise ValueError(f"stage '{stage}' 에 유효한 토큰이 없음")

                available_tokens = [t for t in raw_tokens if t in existing_chambers]
                missing_tokens = [t for t in raw_tokens if t not in existing_chambers]

                parsed_stage_info.append({
                    "stage_expr": stage,
                    "raw_tokens": raw_tokens,
                    "available_tokens": available_tokens,
                    "missing_tokens": missing_tokens,
                })

                if len(available_tokens) == 0:
                    raise ValueError(f"stage '{stage}' 의 모든 토큰이 현재 그룹 eqpcham에 없음")

                stage_available_subsets.append(non_empty_subsets_keep_order(available_tokens))

            path_combos = list(product(*stage_available_subsets))
            if not path_combos:
                raise ValueError("생성 가능한 path 조합이 없음")

            uniq_combo_map = {}
            for combo in path_combos:
                key = tuple(tuple(x) for x in combo)
                if key not in uniq_combo_map:
                    uniq_combo_map[key] = combo

            uniq_combos = list(uniq_combo_map.values())
            uniq_combos.sort(key=path_sort_key)

            generated_any = False

            for combo in uniq_combos:
                selected_rows = collect_selected_rows(combo, chamber_groups)
                final_prevent_value = get_path_prevent(combo, chamber_groups)
                final_tip = build_tip_from_selected_rows(selected_rows, final_prevent_value)
                sort_eqpcham_val = min_eqpcham_in_rows(selected_rows)
                eventtime_val = calc_group_eventtime(selected_rows) if not selected_rows.empty else group_eventtime
                eqpline_combo_val = (
                    unique_concat_sorted_eqpline(selected_rows["eqpline"], sep="_")
                    if not selected_rows.empty else eqpline_val
                )

                row = {
                    "processid": template["processid"],
                    "category": template["category"],
                    "skiprule": template["skiprule"],
                    "areaname": template["areaname"],
                    "eqptype": template["eqptype"],
                    "layerid": template["layerid"],
                    "lineid": template["lineid"],
                    "stepseq_type": template["stepseq_type"],
                    "stepseq": template["stepseq"],
                    "descript": template["descript"],
                    "recipeid": template["recipeid"],
                    "batch_kind": template["batch_kind"],
                    "eqpid": template["eqpid"],
                    "eqpgroup": eqpgroup_val,
                    "eqpline": eqpline_combo_val,
                    "path": format_path(combo),
                    "prevent": final_prevent_value,
                    "tip": final_tip,
                    "eventtime": eventtime_val,
                    "childeqp": template["childeqp"],
                    "_sort_eqpcham_final": sort_eqpcham_val,
                }
                path_rows.append(row)
                generated_any = True

            if not generated_any:
                stage_debug = " / ".join(
                    [f"{x['stage_expr']} -> available={x['available_tokens']} missing={x['missing_tokens']}" for x in parsed_stage_info]
                )
                path_error_msg = make_error_message(
                    keys=keys,
                    expr=expr,
                    existing_chambers=existing_chambers,
                    reason=f"path 생성 결과 0건. stage 해석: {stage_debug}",
                )
                path_rows.append(
                    make_error_row(
                        template_row=template,
                        eqpgroup_val=eqpgroup_val,
                        eqpline_val=eqpline_val,
                        eventtime_val=group_eventtime,
                        path_error_msg=path_error_msg,
                        sort_eqpcham_val=min_eqpcham_in_rows(g),
                    ).iloc[0].to_dict()
                )

        except Exception as e:
            path_error_msg = make_error_message(
                keys=keys,
                expr=expr,
                existing_chambers=existing_chambers,
                reason=str(e),
            )
            path_rows.append(
                make_error_row(
                    template_row=template,
                    eqpgroup_val=eqpgroup_val,
                    eqpline_val=eqpline_val,
                    eventtime_val=group_eventtime,
                    path_error_msg=path_error_msg,
                    sort_eqpcham_val=min_eqpcham_in_rows(g),
                ).iloc[0].to_dict()
            )

    df_path = pd.DataFrame(path_rows)

    if df_path.empty:
        final_cols = [
            "processid", "category", "skiprule", "areaname", "eqptype", "layerid", "lineid",
            "stepseq_type", "stepseq", "descript", "recipeid", "batch_kind",
            "eqpgroup", "상시/비상시",
            "Body호환", "Cham호환",
            "Body호환확보수", "Cham호환확보수",
            "Body호환_TIP고려", "Cham호환_TIP고려",
            "Body호환확보수_TIP고려", "Cham호환확보수_TIP고려",
            "prevent", "tip", "path", "eventtime", "childeqp", "eqpline",
        ]
        return pd.DataFrame(columns=final_cols)

    # ------------------------------------------------------------------
    # 집계 단계 - 참조함수 기준
    # 기준: (lineid, processid, stepseq, recipeid)
    # ------------------------------------------------------------------
    group_metric_map = {}

    # body별 path에서 stage 후보 복원
    body_stage_sets_map = {}
    body_group_cols = ["lineid", "processid", "stepseq", "recipeid", "eqpid"]

    for gkeys, g in df_path.groupby(metric_group_cols, sort=False, dropna=False):
        for eqpid_val, bg in g.groupby("eqpid", sort=False, dropna=False):
            if pd.isna(eqpid_val):
                continue
            body_stage_sets_map[(gkeys[0], gkeys[1], gkeys[2], gkeys[3], eqpid_val)] = union_stage_candidates_from_paths(bg["path"])

    def get_body_stage_sets(lineid, processid, stepseq, recipeid, eqpid):
        return body_stage_sets_map.get((lineid, processid, stepseq, recipeid, eqpid), [])

    # raw 기준 body block
    body_block_map = {}
    for keys, sub in df.groupby(body_group_cols, sort=False, dropna=False):
        body_block_map[keys] = bool((sub["type_body_logic"] == "PREVENT").any())

    # raw 기준 chamber 상태
    chamber_status_map = {}
    for keys, sub in df.groupby(metric_group_cols + ["eqpcham"], sort=False, dropna=False):
        lineid, processid, stepseq, recipeid, eqpcham = keys

        eqpid_vals = distinct_non_null(sub["eqpid"])
        eqpid_val = eqpid_vals[0] if eqpid_vals else np.nan

        body_block = body_block_map.get((lineid, processid, stepseq, recipeid, eqpid_val), False)
        cham_block = bool((sub["type_cham_logic"] == "PREVENT").any())
        has_doing = bool((sub["prevent_logic"] == "DOING").any())
        has_prevent = bool((sub["prevent_logic"] == "PREVENT").any())

        if body_block:
            status = "BLOCK_BODY"
        elif cham_block:
            status = "BLOCK_CHAM"
        elif has_doing:
            status = "DOING"
        elif has_prevent:
            status = "PREVENT"
        else:
            status = "미등록"

        chamber_status_map[keys] = {
            "eqpid": eqpid_val,
            "status": status,
        }

    def is_chamber_currently_usable(lineid, processid, stepseq, recipeid, eqpcham):
        info = chamber_status_map.get((lineid, processid, stepseq, recipeid, eqpcham))
        if info is None:
            return False
        return info["status"] == "DOING"

    def get_current_stage_counts(lineid, processid, stepseq, recipeid, eqpid):
        """
        TIP 고려 시 해당 body의 stage별 사용 가능 chamber 수.
        - body 자체가 PREVENT면 모든 stage 0
        - stage 구조가 있으면 각 stage별 DOING chamber 수
        - stage 구조가 없으면 fallback으로 body 내 DOING chamber 존재 여부 1/0
        """
        body_block = body_block_map.get((lineid, processid, stepseq, recipeid, eqpid), False)
        stage_sets = get_body_stage_sets(lineid, processid, stepseq, recipeid, eqpid)

        if body_block:
            if stage_sets:
                return [0] * len(stage_sets)
            return [0]

        if stage_sets:
            counts = []
            for stage_set in stage_sets:
                doing_cnt = sum(
                    1
                    for cham in stage_set
                    if is_chamber_currently_usable(lineid, processid, stepseq, recipeid, cham)
                )
                counts.append(doing_cnt)
            return counts

        sub = df[
            (df["lineid"] == lineid) &
            (df["processid"] == processid) &
            (df["stepseq"] == stepseq) &
            (df["recipeid"] == recipeid) &
            (df["eqpid"] == eqpid)
        ]
        if sub.empty:
            return [0]

        usable_any = False
        for eqpcham in distinct_non_null(sub["eqpcham"]):
            if is_chamber_currently_usable(lineid, processid, stepseq, recipeid, eqpcham):
                usable_any = True
                break

        return [1 if usable_any else 0]

    def is_body_currently_usable(lineid, processid, stepseq, recipeid, eqpid):
        current_stage_counts = get_current_stage_counts(lineid, processid, stepseq, recipeid, eqpid)
        if not current_stage_counts:
            return False
        return min(current_stage_counts) >= 1

    for gkeys, g in df_path.groupby(metric_group_cols, sort=False, dropna=False):
        lineid, processid, stepseq, recipeid = gkeys
        eqpid_vals = distinct_non_null(g["eqpid"])
        n_body = len(eqpid_vals)

        # base: Body 확보수
        if n_body == 0:
            body_count_base = 0
        else:
            body_count_base = n_body

        # base: Cham 확보수
        if n_body == 0:
            cham_count_base = 0
        else:
            cham_count_base = 0
            for eqpid_val in eqpid_vals:
                stage_sets = get_body_stage_sets(lineid, processid, stepseq, recipeid, eqpid_val)

                if len(stage_sets) == 0:
                    stage_counts = [1]
                else:
                    stage_counts = [len(s) if len(s) > 0 else 1 for s in stage_sets]

                cham_count_base += min(stage_counts) if stage_counts else 1

        # TIP 고려: Body 확보수
        if n_body == 0:
            body_count_tip = 0
        else:
            usable_bodies = [
                eq for eq in eqpid_vals
                if is_body_currently_usable(lineid, processid, stepseq, recipeid, eq)
            ]
            body_count_tip = len(usable_bodies)

        # TIP 고려: Cham 확보수
        if n_body == 0:
            cham_count_tip = 0
        else:
            cham_count_tip = 0
            for eqpid_val in eqpid_vals:
                current_stage_counts = get_current_stage_counts(lineid, processid, stepseq, recipeid, eqpid_val)
                cham_count_tip += min(current_stage_counts) if current_stage_counts else 0

        # 정책 반영
        if n_body == 0:
            body_count_base = 0
            cham_count_base = 0
        else:
            if body_count_base < 1:
                body_count_base = 1
            if cham_count_base < 1:
                cham_count_base = 1

        # Y/N 판정
        body_flag_base = "Y" if body_count_base >= 2 else "N"
        cham_flag_base = "Y" if cham_count_base >= 2 else "N"
        body_flag_tip = "Y" if body_count_tip >= 2 else "N"
        cham_flag_tip = "Y" if cham_count_tip >= 2 else "N"

        group_union_lines = set()
        for v in g["eqpline"].tolist():
            group_union_lines.update(parse_eqpline_tokens(v))

        group_metric_map[gkeys] = {
            "Body호환": body_flag_base,
            "Cham호환": cham_flag_base,
            "Body호환확보수": int(body_count_base),
            "Cham호환확보수": int(cham_count_base),
            "Body호환_TIP고려": body_flag_tip,
            "Cham호환_TIP고려": cham_flag_tip,
            "Body호환확보수_TIP고려": int(body_count_tip),
            "Cham호환확보수_TIP고려": int(cham_count_tip),
            "_group_union_lines": group_union_lines,
        }

    # ------------------------------------------------------------------
    # row-level 상시/비상시 계산
    # ------------------------------------------------------------------
    def classify_normal_emergency(row):
        gkey = (row["lineid"], row["processid"], row["stepseq"], row["recipeid"])
        ginfo = group_metric_map[gkey]

        if ginfo["Body호환"] == "N" and ginfo["Cham호환"] == "N":
            return np.nan

        if row["prevent"] == "PREVENT" and pd.notna(row["eventtime"]):
            elapsed_days = (now_ts - pd.Timestamp(row["eventtime"])).days
            if elapsed_days >= days_threshold:
                return "비상시"

        group_union_lines = ginfo["_group_union_lines"]
        row_lines = set(parse_eqpline_tokens(row["eqpline"]))

        if len(row_lines) == 0:
            return "비상시"

        if len(group_union_lines) >= 1 and all(is_p_line(x) for x in group_union_lines):
            return "상시"

        if len(group_union_lines) <= 1:
            return "상시"

        if "PFR1" in row_lines:
            return "상시"

        return "비상시"

    metric_values = []
    for _, row in df_path.iterrows():
        gkey = (row["lineid"], row["processid"], row["stepseq"], row["recipeid"])
        metric_values.append(group_metric_map[gkey])

    df_path["Body호환"] = [m["Body호환"] for m in metric_values]
    df_path["Cham호환"] = [m["Cham호환"] for m in metric_values]
    df_path["Body호환확보수"] = [m["Body호환확보수"] for m in metric_values]
    df_path["Cham호환확보수"] = [m["Cham호환확보수"] for m in metric_values]
    df_path["Body호환_TIP고려"] = [m["Body호환_TIP고려"] for m in metric_values]
    df_path["Cham호환_TIP고려"] = [m["Cham호환_TIP고려"] for m in metric_values]
    df_path["Body호환확보수_TIP고려"] = [m["Body호환확보수_TIP고려"] for m in metric_values]
    df_path["Cham호환확보수_TIP고려"] = [m["Cham호환확보수_TIP고려"] for m in metric_values]

    df_path["상시/비상시"] = df_path.apply(classify_normal_emergency, axis=1)

    df_path.loc[
        (df_path["Body호환"] == "N") & (df_path["Cham호환"] == "N"),
        "상시/비상시"
    ] = np.nan

    # ------------------------------------------------------------------
    # 최종 정렬
    # ------------------------------------------------------------------
    df_path = df_path.sort_values(
        by=["processid", "stepseq", "_sort_eqpcham_final"],
        ascending=[True, True, True],
        kind="mergesort",
        na_position="last",
    ).reset_index(drop=True)

    # ------------------------------------------------------------------
    # 최종 컬럼 순서
    # ------------------------------------------------------------------
    final_cols = [
        "processid",
        "category",
        "skiprule",
        "areaname",
        "eqptype",
        "layerid",
        "lineid",
        "stepseq_type",
        "stepseq",
        "descript",
        "recipeid",
        "batch_kind",
        "eqpgroup",
        "상시/비상시",
        "Body호환",
        "Cham호환",
        "Body호환확보수",
        "Cham호환확보수",
        "Body호환_TIP고려",
        "Cham호환_TIP고려",
        "Body호환확보수_TIP고려",
        "Cham호환확보수_TIP고려",
        "prevent",
        "tip",
        "path",
        "eventtime",
        "childeqp",
        "eqpline",
    ]

    for c in final_cols:
        if c not in df_path.columns:
            df_path[c] = np.nan

    return df_path[final_cols].copy()


def setup_django_for_batch(settings_module="config.settings"):
    import importlib
    import sys
    import django

    base_dir = os.path.dirname(os.path.abspath(__file__))
    if base_dir not in sys.path:
        sys.path.insert(0, base_dir)

    os.environ["DJANGO_SETTINGS_MODULE"] = settings_module

    if "config" in sys.modules:
        del sys.modules["config"]

    config_module = importlib.import_module("config")
    print("django config module path =", getattr(config_module, "__file__", "namespace package"))
    django.setup()

    from django.conf import settings

    db = settings.DATABASES.get("default", {})
    print(f"[BATCH] DJANGO_SETTINGS_MODULE={settings_module}")
    print(f"[BATCH] DB ENGINE={db.get('ENGINE', '')}")
    print(f"[BATCH] DB NAME={db.get('NAME', '')}")
    print(f"[BATCH] DB HOST={db.get('HOST', '')}")
    if settings_module == "config.settings_codex":
        print("[BATCH][WARNING] config.settings_codex 사용 중입니다. 운영/사내 배치는 config.settings 사용을 권장합니다.")


def run_postload_precompute(snap_date=None, all_existing=False):
    from django.core.management import call_command

    if all_existing:
        print("[BATCH] 전체 existing 데이터 사전계산을 실행합니다.")
        call_command("rebuild_facts_dashboard_graph_cache", all_existing=True)
        call_command("rebuild_facts_history_summary_cache", all_existing=True)
        return

    if snap_date is None:
        raise ValueError("snap_date 또는 all_existing=True 중 하나가 필요합니다.")

    snap_date_str = str(snap_date)
    print(f"[BATCH] snap_date={snap_date_str} 사전계산을 실행합니다.")
    call_command("rebuild_facts_dashboard_graph_cache", snap_date=snap_date_str)
    call_command("rebuild_facts_history_summary_cache", snap_date=snap_date_str)
