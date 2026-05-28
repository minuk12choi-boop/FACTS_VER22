"""이 파일은 my_def.py와 my_def_origin.py의 기능 합집합 병합본이다. 기존 파일을 대체하지 않으며, PRP_COMPATIBILITY_merge.py에서 사용한다."""

import os
import pandas as pd
import numpy as np
from itertools import combinations, product
import re
import time
from contextlib import contextmanager
from bisect import bisect_left, bisect_right
from typing import Optional
import pymysql
import datetime


@contextmanager
def timer(name: str):
    t0 = time.perf_counter()
    yield
    dt = time.perf_counter() - t0
    print(f"[TIMER] {name}: {dt:,.2f} sec")


def get_unique_filename(filepath):
    if not os.path.exists(filepath):
        return filepath
    
    base, ext = os.path.splitext(filepath)
    i = 1
    while True:
        new_path = f"{base}_{i}{ext}"
        if not os.path.exists(new_path):
            return new_path
        i += 1


def build_steptip_path(df_steptip: pd.DataFrame) -> pd.DataFrame:
    required_cols = [
        "processid", "category", "skiprule", "areaname", "eqptype", "layerid",
        "stepseq_type", "stepseq", "descript", "recipeid", "eqpcham", "eqpid",
        "chamberid", "batch_kind", "prevent", "type_body", "type_cham",
        "eventtime", "eqpline", "childeqp"
    ]
    missing = [c for c in required_cols if c not in df_steptip.columns]
    if missing:
        raise ValueError(f"필수 컬럼 누락: {missing}")

    df = df_steptip.copy()
    original_cols = df.columns.tolist()

    # path 생성 그룹
    path_group_cols = ["processid", "stepseq", "eqpid"]

    # eqpgroup 계산 그룹
    eqpgroup_group_cols = ["processid", "stepseq", "recipeid"]

    # --------------------------------------------------
    # 전처리
    # --------------------------------------------------
    str_cols = ["eqpcham", "eqpid", "eqpline", "childeqp", "prevent", "type_body", "type_cham"]
    for c in str_cols:
        df[c] = df[c].replace(r"^\s*$", np.nan, regex=True)

    df["eventtime"] = pd.to_datetime(df["eventtime"], errors="coerce")

    def norm(x):
        if pd.isna(x):
            return np.nan
        s = str(x).strip()
        return s if s else np.nan

    df["eqpcham_norm"] = df["eqpcham"].map(norm)
    df["eqpid_norm"] = df["eqpid"].map(norm)
    df["eqpline_norm"] = df["eqpline"].map(norm)
    df["prevent_norm"] = df["prevent"].map(norm)
    df["type_body_norm"] = df["type_body"].map(norm)
    df["type_cham_norm"] = df["type_cham"].map(norm)
    df["childeqp_norm"] = df["childeqp"].map(norm)

    # --------------------------------------------------
    # 유틸
    # --------------------------------------------------
    def unique_keep_order(values):
        out = []
        seen = set()
        for v in values:
            if pd.isna(v):
                continue
            sv = str(v)
            if sv not in seen:
                seen.add(sv)
                out.append(sv)
        return out

    def unique_concat(values_or_series, sep="_"):
        if isinstance(values_or_series, pd.Series):
            values = values_or_series.tolist()
        else:
            values = list(values_or_series)
        vals = unique_keep_order(values)
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

    def calc_group_eventtime(g: pd.DataFrame):
        evt_prevent = g.loc[g["prevent_norm"] == "PREVENT", "eventtime"].dropna()
        if not evt_prevent.empty:
            return evt_prevent.max()

        evt_all = g["eventtime"].dropna()
        return evt_all.max() if not evt_all.empty else pd.NaT

    def build_chamber_groups(g: pd.DataFrame):
        out = {}
        for cham, sub in g.groupby("eqpcham_norm", sort=False, dropna=False):
            if pd.isna(cham):
                continue
            out[cham] = sub.copy()
        return out

    # --------------------------------------------------
    # eqpgroup 사전 계산
    # eqpgroup = uniqueconcatenate(eqpid) over (processid, stepseq, recipeid)
    # eqpid 오름차순 정렬
    # --------------------------------------------------
    eqpgroup_map = {}
    for eq_keys, sub in df.groupby(eqpgroup_group_cols, sort=False, dropna=False):
        eqpgroup_map[eq_keys] = unique_concat_sorted(sub["eqpid_norm"], sep="_")

    def get_eqpgroup_value(processid, stepseq, recipeid):
        return eqpgroup_map.get((processid, stepseq, recipeid), np.nan)

    # --------------------------------------------------
    # prevent 계산 로직
    # --------------------------------------------------
    def get_chamber_prevent(sub: pd.DataFrame):
        """
        같은 chamber에 row가 여러 개일 수 있으므로 chamber 단위 상태 요약

        우선순위:
        - DOING 하나라도 있으면 DOING
        - 아니고 PREVENT 하나라도 있으면 PREVENT
        - 둘 다 없으면 미등록
        """
        vals = sub["prevent_norm"].dropna().astype(str).tolist()

        if "DOING" in vals:
            return "DOING"
        if "PREVENT" in vals:
            return "PREVENT"
        return "미등록"

    def get_stage_prevent(stage_subset, chamber_groups):
        """
        ; = OR
        - 하나라도 DOING이면 stage는 DOING
        - DOING 없고 PREVENT가 있으면 PREVENT
        - 그 외는 미등록
        """
        chamber_results = []

        for cham in stage_subset:
            sub = chamber_groups.get(cham)
            if sub is None or sub.empty:
                chamber_results.append("미등록")
            else:
                chamber_results.append(get_chamber_prevent(sub))

        if "DOING" in chamber_results:
            return "DOING"
        if "PREVENT" in chamber_results:
            return "PREVENT"
        return "미등록"

    def get_path_prevent(stage_combo, chamber_groups):
        """
        : = AND
        - 모든 stage가 DOING이면 DOING
        - 아니고 하나라도 PREVENT면 PREVENT
        - 그 외는 미등록
        """
        stage_results = [get_stage_prevent(stage_subset, chamber_groups) for stage_subset in stage_combo]

        if all(x == "DOING" for x in stage_results):
            return "DOING"
        if "PREVENT" in stage_results:
            return "PREVENT"
        return "미등록"

    def collect_selected_rows(stage_combo, chamber_groups):
        selected = []
        seen = set()

        for stage_subset in stage_combo:
            for cham in stage_subset:
                if cham in seen:
                    continue
                seen.add(cham)
                sub = chamber_groups.get(cham)
                if sub is not None and not sub.empty:
                    selected.append(sub)

        if selected:
            return pd.concat(selected, ignore_index=True)
        return pd.DataFrame(columns=df.columns)

    def build_tip_from_selected_rows(selected_rows: pd.DataFrame, final_prevent_value):
        """
        tip 생성 규칙
        - prevent != PREVENT 이면 NaN
        - type_body='PREVENT' 우선 -> PREVENT: eqpid
        - 없으면 type_cham='PREVENT' -> PREVENT: eqpcham
        """
        if final_prevent_value != "PREVENT":
            return np.nan

        if selected_rows.empty:
            return np.nan

        body_prevent_rows = selected_rows[selected_rows["type_body_norm"] == "PREVENT"]
        if not body_prevent_rows.empty:
            targets = unique_concat_text(body_prevent_rows["eqpid_norm"].tolist(), sep=", ")
            return f"PREVENT: {targets}" if pd.notna(targets) else "PREVENT"

        cham_prevent_rows = selected_rows[selected_rows["type_cham_norm"] == "PREVENT"]
        if not cham_prevent_rows.empty:
            targets = unique_concat_text(cham_prevent_rows["eqpcham_norm"].tolist(), sep=", ")
            return f"PREVENT: {targets}" if pd.notna(targets) else "PREVENT"

        return np.nan

    def make_error_message(keys, expr, existing_chambers, reason):
        key_txt = ", ".join([f"{k}={v}" for k, v in zip(path_group_cols, keys)])
        chamber_txt = ", ".join(existing_chambers) if existing_chambers else "없음"
        expr_txt = expr if pd.notna(expr) else "NULL"
        return f"ERROR: {reason} [group: {key_txt}] [childeqp: {expr_txt}] [available eqpcham: {chamber_txt}]"

    def make_error_row(template_row: pd.Series, eqpgroup_val, eqpline_val, eventtime_val, path_error_msg):
        row = template_row.copy()
        row["eqpgroup"] = eqpgroup_val
        row["eqpline"] = eqpline_val
        row["eventtime"] = eventtime_val
        row["path"] = path_error_msg
        row["prevent"] = "ERROR"
        row["tip"] = np.nan
        row["path_error"] = path_error_msg
        return pd.DataFrame([row])

    # --------------------------------------------------
    # 메인 처리
    # --------------------------------------------------
    result_frames = []

    for keys, g in df.groupby(path_group_cols, sort=False, dropna=False):
        g = g.copy()
        template = g.iloc[0].copy()

        processid_val = template["processid"]
        stepseq_val = template["stepseq"]
        recipeid_val = template["recipeid"]

        eqpgroup_val = get_eqpgroup_value(processid_val, stepseq_val, recipeid_val)
        eqpline_val = unique_concat_sorted_eqpline(g["eqpline_norm"], sep="_")
        group_eventtime = calc_group_eventtime(g)

        chamber_groups = build_chamber_groups(g)
        existing_chambers = list(chamber_groups.keys())
        child_vals = unique_keep_order(g["childeqp_norm"].dropna().tolist())

        # --------------------------------------------------
        # childeqp 없음
        # --------------------------------------------------
        if len(child_vals) == 0:
            out = g.copy()
            out["eqpgroup"] = eqpgroup_val
            out["eqpline"] = eqpline_val
            out["eventtime"] = group_eventtime
            out["path_error"] = np.nan
            out["path"] = out["eqpcham_norm"].apply(lambda x: f"({x})" if pd.notna(x) else np.nan)

            prevents = []
            tips = []

            for _, r in out.iterrows():
                eqpcham_val = r["eqpcham_norm"]
                sub = chamber_groups.get(eqpcham_val)

                if sub is None or sub.empty:
                    final_prevent_value = "미등록"
                    tip = np.nan
                else:
                    final_prevent_value = get_chamber_prevent(sub)
                    tip = build_tip_from_selected_rows(sub, final_prevent_value)

                prevents.append(final_prevent_value)
                tips.append(tip)

            out["prevent"] = prevents
            out["tip"] = tips
            result_frames.append(out)
            continue

        # --------------------------------------------------
        # childeqp 여러 개 -> 에러
        # --------------------------------------------------
        if len(child_vals) > 1:
            path_error_msg = make_error_message(
                keys=keys,
                expr=" || ".join(child_vals),
                existing_chambers=existing_chambers,
                reason=f"동일 path group 내 childeqp 값이 여러 개 존재함 ({len(child_vals)}개)"
            )
            result_frames.append(
                make_error_row(template, eqpgroup_val, eqpline_val, group_eventtime, path_error_msg)
            )
            continue

        # --------------------------------------------------
        # childeqp 1개 -> path 생성
        # --------------------------------------------------
        expr = child_vals[0]

        try:
            raw_stages = [s.strip() for s in expr.split(":") if s.strip()]
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

                stage_available_subsets.append(
                    non_empty_subsets_keep_order(available_tokens)
                )

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

            generated_rows = []

            for combo in uniq_combos:
                selected_rows = collect_selected_rows(combo, chamber_groups)
                final_prevent_value = get_path_prevent(combo, chamber_groups)
                final_tip = build_tip_from_selected_rows(selected_rows, final_prevent_value)

                new_row = template.copy()
                new_row["eqpgroup"] = eqpgroup_val
                new_row["eqpline"] = eqpline_val
                new_row["eventtime"] = group_eventtime
                new_row["path"] = format_path(combo)
                new_row["path_error"] = np.nan
                new_row["prevent"] = final_prevent_value
                new_row["tip"] = final_tip

                generated_rows.append(new_row)

            if generated_rows:
                result_frames.append(pd.DataFrame(generated_rows))
            else:
                stage_debug = " / ".join(
                    [f"{x['stage_expr']} -> available={x['available_tokens']} missing={x['missing_tokens']}" for x in parsed_stage_info]
                )
                path_error_msg = make_error_message(
                    keys=keys,
                    expr=expr,
                    existing_chambers=existing_chambers,
                    reason=f"path 생성 결과 0건. stage 해석: {stage_debug}"
                )
                result_frames.append(
                    make_error_row(template, eqpgroup_val, eqpline_val, group_eventtime, path_error_msg)
                )

        except Exception as e:
            path_error_msg = make_error_message(
                keys=keys,
                expr=expr,
                existing_chambers=existing_chambers,
                reason=str(e)
            )
            result_frames.append(
                make_error_row(template, eqpgroup_val, eqpline_val, group_eventtime, path_error_msg)
            )

    result = pd.concat(result_frames, ignore_index=True)

    # --------------------------------------------------
    # 정렬
    # --------------------------------------------------
    result["_sort_eqpcham"] = result["eqpcham"].map(norm)

    result = result.sort_values(
        by=["processid", "stepseq", "_sort_eqpcham"],
        ascending=[True, True, True],
        kind="mergesort",
        na_position="last"
    ).reset_index(drop=True)

    # --------------------------------------------------
    # 내부 보조 컬럼 제거
    # --------------------------------------------------
    drop_cols_internal = [
        "eqpcham_norm", "eqpid_norm", "eqpline_norm",
        "prevent_norm", "type_body_norm", "type_cham_norm", "childeqp_norm",
        "_sort_eqpcham"
    ]
    result = result.drop(columns=drop_cols_internal, errors="ignore")

    # --------------------------------------------------
    # 최종 출력 컬럼 정리
    # --------------------------------------------------
    excluded_cols = {"eqpcham", "chamberid", "type_body", "type_cham"}

    base_cols = [c for c in original_cols if c not in excluded_cols]
    extra_cols = [c for c in ["eqpgroup", "path", "tip", "path_error"] if c not in base_cols]

    for c in extra_cols:
        if c not in result.columns:
            result[c] = np.nan

    final_cols = base_cols + extra_cols
    result = result[final_cols]

    return result


def build_df_compatibility_summary(
    df_raw: pd.DataFrame,
    df_steptip: pd.DataFrame,
    days_threshold: int = 30,
    now_ts=None,
) -> pd.DataFrame:
    """
    df_raw(build_steptip_path 결과) + df_steptip(raw 상태 테이블)를 함께 사용하여
    호환/확보수/상시비상시 컬럼을 생성한다.

    Parameters
    ----------
    df_raw : pd.DataFrame
        build_steptip_path 결과 테이블
    df_steptip : pd.DataFrame
        원본 steptip 테이블
    days_threshold : int, default 30
        PREVENT가 이 일수 이상 지속되면 비상시로 간주
    now_ts : str | pd.Timestamp | None
        기준 시각. None이면 현재 시각 사용
    """

    # --------------------------------------------------
    # 필수 컬럼 체크
    # --------------------------------------------------
    required_raw_cols = [
        "processid", "category", "skiprule", "areaname", "eqptype", "layerid",
        "stepseq_type", "stepseq", "descript", "recipeid", "batch_kind",
        "eqpgroup", "prevent", "tip", "path", "eventtime", "childeqp",
        "eqpline", "eqpid"
    ]
    missing_raw = [c for c in required_raw_cols if c not in df_raw.columns]
    if missing_raw:
        raise ValueError(f"df_raw 필수 컬럼 누락: {missing_raw}")

    required_tip_cols = [
        "processid", "stepseq", "recipeid", "eqpid", "eqpcham",
        "prevent", "type_body", "type_cham", "eventtime"
    ]
    missing_tip = [c for c in required_tip_cols if c not in df_steptip.columns]
    if missing_tip:
        raise ValueError(f"df_steptip 필수 컬럼 누락: {missing_tip}")

    if now_ts is None:
        now_ts = pd.Timestamp.now()
    else:
        now_ts = pd.Timestamp(now_ts)

    df = df_raw.copy()
    tip_src = df_steptip.copy()

    # --------------------------------------------------
    # 전처리
    # --------------------------------------------------
    def norm(x):
        if pd.isna(x):
            return np.nan
        s = str(x).strip()
        return s if s else np.nan

    for c in ["eqpid", "prevent", "path", "eqpline", "childeqp"]:
        df[c] = df[c].map(norm)

    for c in ["eqpid", "eqpcham", "prevent", "type_body", "type_cham"]:
        tip_src[c] = tip_src[c].map(norm)

    df["eventtime"] = pd.to_datetime(df["eventtime"], errors="coerce")
    tip_src["eventtime"] = pd.to_datetime(tip_src["eventtime"], errors="coerce")

    group_cols = ["processid", "stepseq", "recipeid"]
    body_group_cols = ["processid", "stepseq", "recipeid", "eqpid"]

    # --------------------------------------------------
    # 유틸
    # --------------------------------------------------
    def distinct_non_null(series: pd.Series):
        return sorted(set([str(x) for x in series.dropna()]))

    def split_eqpline_tokens(v):
        if pd.isna(v):
            return []
        return [x.strip() for x in str(v).split("_") if x.strip()]

    def is_p_line(v: str) -> bool:
        return str(v).startswith("P")

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
        동일 body(eqpid) 그룹의 여러 path를 보고
        stage index별 후보 chamber 집합을 복원

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
            if p not in seen and not p.startswith("ERROR:"):
                seen.add(p)
                unique_paths.append(p)

        for p in unique_paths:
            stages = parse_path_stages(p)
            for i, stage_tokens in enumerate(stages):
                if i >= len(stage_sets):
                    stage_sets.append(set())
                stage_sets[i].update(stage_tokens)

        return stage_sets

    # --------------------------------------------------
    # df_steptip 기반 current 상태 lookup
    # --------------------------------------------------
    body_block_map = {}
    for keys, sub in tip_src.groupby(body_group_cols, sort=False, dropna=False):
        body_block_map[keys] = bool((sub["type_body"] == "PREVENT").any())

    chamber_status_map = {}
    for keys, sub in tip_src.groupby(group_cols + ["eqpcham"], sort=False, dropna=False):
        processid, stepseq, recipeid, eqpcham = keys

        eqpid_vals = distinct_non_null(sub["eqpid"])
        eqpid_val = eqpid_vals[0] if eqpid_vals else np.nan

        body_block = body_block_map.get((processid, stepseq, recipeid, eqpid_val), False)
        cham_block = bool((sub["type_cham"] == "PREVENT").any())
        has_doing = bool((sub["prevent"] == "DOING").any())
        has_prevent = bool((sub["prevent"] == "PREVENT").any())

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

    def is_chamber_currently_usable(processid, stepseq, recipeid, eqpcham):
        info = chamber_status_map.get((processid, stepseq, recipeid, eqpcham))
        if info is None:
            return False
        return info["status"] == "DOING"

    # body별 stage 후보맵을 먼저 만들어 둠
    body_stage_sets_map = {}

    for gkeys, g in df.groupby(group_cols, sort=False, dropna=False):
        for eqpid_val, bg in g.groupby("eqpid", sort=False, dropna=False):
            if pd.isna(eqpid_val):
                continue
            body_stage_sets_map[(gkeys[0], gkeys[1], gkeys[2], eqpid_val)] = union_stage_candidates_from_paths(bg["path"])

    def get_body_stage_sets(processid, stepseq, recipeid, eqpid):
        return body_stage_sets_map.get((processid, stepseq, recipeid, eqpid), [])

    def get_current_stage_counts(processid, stepseq, recipeid, eqpid):
        """
        TIP 고려 시 해당 body의 stage별 사용 가능 chamber 수를 반환.
        규칙:
        - body 자체가 PREVENT면 모든 stage 0
        - stage 구조가 있으면 각 stage별 DOING chamber 수
        - stage 구조가 없으면 fallback으로 body 내 DOING chamber 존재 여부를 1/0 처리
        """
        body_block = body_block_map.get((processid, stepseq, recipeid, eqpid), False)
        if body_block:
            stage_sets = get_body_stage_sets(processid, stepseq, recipeid, eqpid)
            if stage_sets:
                return [0] * len(stage_sets)
            return [0]

        stage_sets = get_body_stage_sets(processid, stepseq, recipeid, eqpid)

        if stage_sets:
            counts = []
            for stage_set in stage_sets:
                doing_cnt = sum(
                    1
                    for cham in stage_set
                    if is_chamber_currently_usable(processid, stepseq, recipeid, cham)
                )
                counts.append(doing_cnt)
            return counts

        # fallback: path stage를 복원 못하면 body 내 DOING chamber 존재 여부로만 판단
        sub = tip_src[
            (tip_src["processid"] == processid) &
            (tip_src["stepseq"] == stepseq) &
            (tip_src["recipeid"] == recipeid) &
            (tip_src["eqpid"] == eqpid)
        ]
        if sub.empty:
            return [0]

        usable_any = False
        for eqpcham in distinct_non_null(sub["eqpcham"]):
            if is_chamber_currently_usable(processid, stepseq, recipeid, eqpcham):
                usable_any = True
                break

        return [1 if usable_any else 0]

    def is_body_currently_usable(processid, stepseq, recipeid, eqpid):
        """
        body 사용 가능 조건:
        각 stage마다 최소 1개 이상의 사용 가능한 chamber가 있어야 함.
        """
        current_stage_counts = get_current_stage_counts(processid, stepseq, recipeid, eqpid)
        if not current_stage_counts:
            return False
        return min(current_stage_counts) >= 1

    # --------------------------------------------------
    # 그룹별 구조 계산
    # --------------------------------------------------
    group_metric_map = {}

    for gkeys, g in df.groupby(group_cols, sort=False, dropna=False):
        processid, stepseq, recipeid = gkeys
        eqpid_vals = distinct_non_null(g["eqpid"])
        n_body = len(eqpid_vals)

        # ---------- base: Body 확보수 ----------
        if n_body == 0:
            body_count_base = 0
        else:
            body_count_base = n_body

        # ---------- base: Cham 확보수 ----------
        body_stage_count_map = {}
        if n_body == 0:
            cham_count_base = 0
        else:
            cham_count_base = 0
            for eqpid_val, bg in g.groupby("eqpid", sort=False, dropna=False):
                if pd.isna(eqpid_val):
                    continue

                stage_sets = get_body_stage_sets(processid, stepseq, recipeid, eqpid_val)

                if len(stage_sets) == 0:
                    stage_counts = [1]
                else:
                    stage_counts = [len(s) if len(s) > 0 else 1 for s in stage_sets]

                body_stage_count_map[eqpid_val] = stage_counts
                cham_count_base += min(stage_counts) if stage_counts else 1

        # ---------- TIP 고려: Body 확보수 ----------
        if n_body == 0:
            body_count_tip = 0
        else:
            usable_bodies = [
                eq for eq in eqpid_vals
                if is_body_currently_usable(processid, stepseq, recipeid, eq)
            ]
            body_count_tip = len(usable_bodies)

        # ---------- TIP 고려: Cham 확보수 ----------
        if n_body == 0:
            cham_count_tip = 0
        else:
            cham_count_tip = 0
            for eqpid_val in eqpid_vals:
                current_stage_counts = get_current_stage_counts(processid, stepseq, recipeid, eqpid_val)
                cham_count_tip += min(current_stage_counts) if current_stage_counts else 0

        # ---------- 정책 반영 ----------
        # 단독일 땐 body/cham 확보수는 1, 미등록이면 0
        if n_body == 0:
            body_count_base = 0
            cham_count_base = 0
        else:
            if body_count_base < 1:
                body_count_base = 1
            if cham_count_base < 1:
                cham_count_base = 1

        # ---------- Y/N 판정은 확보수 기준 ----------
        body_flag_base = "Y" if body_count_base >= 2 else "N"
        cham_flag_base = "Y" if cham_count_base >= 2 else "N"
        body_flag_tip = "Y" if body_count_tip >= 2 else "N"
        cham_flag_tip = "Y" if cham_count_tip >= 2 else "N"

        # ---------- 상시/비상시 계산용 그룹 라인 ----------
        group_union_lines = set()
        for v in g["eqpline"]:
            group_union_lines.update(split_eqpline_tokens(v))

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

    # --------------------------------------------------
    # row-level 상시/비상시 계산
    # --------------------------------------------------
    def classify_normal_emergency(row):
        ginfo = group_metric_map[(row["processid"], row["stepseq"], row["recipeid"])]

        # 호환이 아닐 때는 빈값
        if ginfo["Body호환"] == "N" and ginfo["Cham호환"] == "N":
            return np.nan

        # 오래된 PREVENT면 비상시
        if row["prevent"] == "PREVENT" and pd.notna(row["eventtime"]):
            elapsed_days = (now_ts - row["eventtime"]).days
            if elapsed_days >= days_threshold:
                return "비상시"

        group_union_lines = ginfo["_group_union_lines"]
        row_lines = set(split_eqpline_tokens(row["eqpline"]))

        if len(row_lines) == 0:
            return "비상시"

        # 전부 P% 라인이면 상시
        if len(group_union_lines) >= 1 and all(is_p_line(x) for x in group_union_lines):
            return "상시"

        # 라인 종류 1개면 상시
        if len(group_union_lines) <= 1:
            return "상시"

        # 혼재 라인이면 PFR1만 상시, 나머지는 비상시
        if "PFR1" in row_lines:
            return "상시"

        return "비상시"

    # --------------------------------------------------
    # 결과 컬럼 주입
    # --------------------------------------------------
    body_flag_base_list = []
    cham_flag_base_list = []
    body_cnt_base_list = []
    cham_cnt_base_list = []
    body_flag_tip_list = []
    cham_flag_tip_list = []
    body_cnt_tip_list = []
    cham_cnt_tip_list = []

    for _, row in df.iterrows():
        ginfo = group_metric_map[(row["processid"], row["stepseq"], row["recipeid"])]
        body_flag_base_list.append(ginfo["Body호환"])
        cham_flag_base_list.append(ginfo["Cham호환"])
        body_cnt_base_list.append(ginfo["Body호환확보수"])
        cham_cnt_base_list.append(ginfo["Cham호환확보수"])
        body_flag_tip_list.append(ginfo["Body호환_TIP고려"])
        cham_flag_tip_list.append(ginfo["Cham호환_TIP고려"])
        body_cnt_tip_list.append(ginfo["Body호환확보수_TIP고려"])
        cham_cnt_tip_list.append(ginfo["Cham호환확보수_TIP고려"])

    df["Body호환"] = body_flag_base_list
    df["Cham호환"] = cham_flag_base_list
    df["Body호환확보수"] = body_cnt_base_list
    df["Cham호환확보수"] = cham_cnt_base_list
    df["Body호환_TIP고려"] = body_flag_tip_list
    df["Cham호환_TIP고려"] = cham_flag_tip_list
    df["Body호환확보수_TIP고려"] = body_cnt_tip_list
    df["Cham호환확보수_TIP고려"] = cham_cnt_tip_list
    df["상시/비상시"] = df.apply(classify_normal_emergency, axis=1)

    # 호환이 아닐 때는 상시/비상시 빈값
    df.loc[
        (df["Body호환"] == "N") & (df["Cham호환"] == "N"),
        "상시/비상시"
    ] = np.nan

    # --------------------------------------------------
    # 최종 컬럼 순서
    # --------------------------------------------------
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

    return df[final_cols].copy()


def append_df_to_mysql(df_final, conn):
    load_id = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    loaded_at = datetime.datetime.now()
    snap_date = loaded_at.date()

    df = df_final.copy()

    # 적재 관리 컬럼 추가
    df["load_id"] = load_id
    df["loaded_at"] = loaded_at
    df["snap_date"] = snap_date

    # eventtime 안전 처리
    if "eventtime" in df.columns:
        df["eventtime"] = pd.to_datetime(df["eventtime"], errors="coerce")
        df["eventtime"] = df["eventtime"].astype(object)
        df.loc[df["eventtime"].isna(), "eventtime"] = None

    # 전체 컬럼 NaN/NaT -> None 처리
    df = df.astype(object)
    df = df.where(pd.notnull(df), None)

    columns = list(df.columns)
    col_sql = ", ".join([f"`{col}`" for col in columns])
    val_sql = ", ".join(["%s"] * len(columns))

    sql_motion = f"""
        INSERT INTO facts_wip_source ({col_sql})
        VALUES ({val_sql})
    """

    data = [tuple(row) for row in df.to_numpy()]

    try:
        with conn.cursor() as curs:
            curs.executemany(sql_motion, data)
        conn.commit()
        print(f"적재 완료 / rows={len(df)} / load_id={load_id}")

    except Exception as e:
        conn.rollback()
        print("적재 실패")
        print(e)
        raise



def append_df_to_mysql_eqpmodel(df_equipment, conn):
    load_id = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    loaded_at = datetime.datetime.now()
    snap_date = loaded_at.date()

    df = df_equipment.copy()

    # 적재 관리 컬럼 추가
    df["load_id"] = load_id
    df["loaded_at"] = loaded_at
    df["snap_date"] = snap_date

    # 전체 컬럼 NaN/NaT -> None 처리
    df = df.astype(object)
    df = df.where(pd.notnull(df), None)

    columns = list(df.columns)
    col_sql = ", ".join([f"`{col}`" for col in columns])
    val_sql = ", ".join(["%s"] * len(columns))

    sql_motion = f"""
        INSERT INTO facts_eqp_model ({col_sql})
        VALUES ({val_sql})
    """

    data = [tuple(row) for row in df.to_numpy()]

    try:
        with conn.cursor() as curs:
            curs.executemany(sql_motion, data)
        conn.commit()
        print(f"적재 완료 / rows={len(df)} / load_id={load_id}")

    except Exception as e:
        conn.rollback()
        print("적재 실패")
        print(e)
        raise
