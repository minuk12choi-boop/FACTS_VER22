import argparse
import datetime as dt
import importlib
import os
import sys
import time
from contextlib import contextmanager

pd = None
bdq = None
getData = None
append_df_to_mysql = None
append_df_to_mysql_eqpmodel = None
build_steptip_path = None
build_df_compatibility_summary = None
build_step_jump_chain = None
build_b_table_from_a = None


@contextmanager
def timer(name: str):
    t0 = time.perf_counter()
    yield
    dt_sec = time.perf_counter() - t0
    print(f"[TIMER] {name}: {dt_sec:,.2f} sec")


def setup_django_for_batch(settings_module="config.settings"):
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


def _ensure_raw_dependencies():
    global pd, bdq, getData
    global append_df_to_mysql, append_df_to_mysql_eqpmodel
    global build_steptip_path, build_df_compatibility_summary, build_step_jump_chain, build_b_table_from_a
    if (
        pd is not None and bdq is not None and getData is not None
        and append_df_to_mysql is not None and append_df_to_mysql_eqpmodel is not None
        and build_steptip_path is not None and build_df_compatibility_summary is not None
        and build_step_jump_chain is not None and build_b_table_from_a is not None
    ):
        return
    import pandas as _pd
    import bigdataquery as _bdq
    from bigdataquery import getData as _get_data
    from my_def import (
        append_df_to_mysql as _append_df_to_mysql,
        append_df_to_mysql_eqpmodel as _append_df_to_mysql_eqpmodel,
        build_b_table_from_a as _build_b_table_from_a,
        build_df_compatibility_summary as _build_df_compatibility_summary,
        build_step_jump_chain as _build_step_jump_chain,
        build_steptip_path as _build_steptip_path,
    )

    pd = _pd
    bdq = _bdq
    getData = _get_data
    append_df_to_mysql = _append_df_to_mysql
    append_df_to_mysql_eqpmodel = _append_df_to_mysql_eqpmodel
    build_b_table_from_a = _build_b_table_from_a
    build_df_compatibility_summary = _build_df_compatibility_summary
    build_step_jump_chain = _build_step_jump_chain
    build_steptip_path = _build_steptip_path


def smicdc_merge():

    my_convert_type = True
    my_verbose = True

    steptip = """
                 WITH
                t as (SELECT DISTINCT
                                        t.process, 
                                        t.step, 
                                        t.ppid, 
                                        t.eqpid, 
                                        (case when t.chamberid in ('-', 'MAIN') then 'MAIN' else chamberid end) as chamberid, 
                        (case 
                        when t.type='DOING' then 'DOING' 
                        when t.type='PREVENT' AND IFNULL(t.checkcount,0)=0 then 'PREVENT' 
                        when t.type='PREVENT' AND IFNULL(t.tkin_count,0)>=IFNULL(checkcount,0) then 'PREVENT' 
                        when t.type='PREVENT' AND IFNULL(t.tkin_count,0)<IFNULL(checkcount,0) then 'DOING' 
                        end) as prevent,
                                        (case when t.chamberid is not null and t.chamberid not in ('MAIN', '-') then concat(t.eqpid,'-',chamberid) else t.eqpid end) as ee,
                        t.eventtime
                FROM mos_kh_smi.smicdc_p3nrd_trackinprevent t
                WHERE process in ('P13X', 'P14B', 'P15R', 'P18L', 'P18R', 'P18T', 'P19Z', 'P1SA', 'P1SC', 'P1SD', 'P1SF', 'P1SK', 'P1SP', 'P1SS', 'P1SU', 'P1SV')
                ),

                tt as (SELECT
                    t.*,
                    (count(case when t.prevent = 'DOING' then t.prevent end) OVER (PARTITION BY t.process, t.step, t.ppid, t.ee)) as C,
                    (count(t.ee) over (partition by t.process, t.step, t.ppid, t.ee)) as CC,
                    (max(t.eventtime) over (partition by t.process, t.step, t.ppid, t.ee, t.prevent)) as M
                        FROM t),

                ttt as (SELECT 
                * 
                FROM tt
                WHERE tt.cc>1 and tt.c>0 and tt.prevent='DOING' and tt.m=tt.eventtime
                    OR tt.cc>1 and tt.c=0 and tt.m=tt.eventtime
                    OR tt.cc=1),

                te as (SELECT 
                                        ttt.process, 
                                        ttt.step, 
                                        ttt.ppid, 
                                        ttt.ee,
                                        ttt.eqpid, 
                                        ttt.chamberid, 
                            ttt.prevent,
                        ttt.eventtime,
                                        e.batch_kind,
                                        e.origin_line_id as eqp_line,
                                        e.eqp_type
                                    FROM ttt
                                    LEFT JOIN (SELECT DISTINCT
                                                eqp_id,
                                                batch_kind,
                                                origin_line_id,
                                                eqp_type
                                                FROM fab.m_mi_equipment where line_id = 'PFR1') e
                                        ON ttt.ee = e.eqp_id
                                    ORDER BY process, step, ppid, ee),

                tee as (SELECT                     
                                    a.process,
                                    a.step,
                                    a.ppid,
                                    IFNULL(case when ifnull(a.batch_kind, '-') in ('BATCH_FURNACE', 'BATCH_WET') then a.eqpid else b.ee end, a.eqpid) as eqpcham,
                                    a.eqpid,
                                    IFNULL(case when ifnull(a.batch_kind, '-') in ('BATCH_FURNACE', 'BATCH_WET') then NULL else b.chamberid end, NULL) as chamberid,
                                    a.batch_kind,
                                    (case 
                        when a.prevent='PREVENT' or b.prevent='PREVENT' then 'PREVENT'
                                    else 'DOING' end) as prevent,   
                                    a.prevent as type_body,
                                    b.prevent as type_cham,          
                        IFNULL(case when ifnull(a.batch_kind, '-') in ('BATCH_FURNACE', 'BATCH_WET') then a.eventtime else b.eventtime end, a.eventtime) as eventtime,
                                    IFNULL(a.eqp_line, b.eqp_line) as eqpline,
                                    IFNULL(a.eqp_type, b.eqp_type) as eqptype
                                FROM (SELECT * FROM te WHERE chamberid in ('MAIN', '-') or chamberid is null) a
                                LEFT JOIN (SELECT * FROM te WHERE chamberid not in ('MAIN', '-') and chamberid is not null) b
                                    ON a.process = b.process
                                        AND a.step = b.step
                                        AND a.ppid = b.ppid
                                        AND a.eqpid = b.eqpid),

                s as (
                                    SELECT  
                                        s.processid,
                                        s.category,
                                        s.skiprule,
                                        s.subarea as areaname,
                                        s.eqptype,
                                        s.layerid,
                                        CASE WHEN SUBSTRING(s.stepseq, 3) REGEXP '[^0-9]' THEN '기타' ELSE '메인' END AS stepseq_type,
                                        s.stepseq,
                                        s.descript,
                                        s.recipeid,
                                        
                                        s.delaytime,
                                        s.n2_delay_time_mins,
                                        k.lotid_ld as ff,
                                        k.descript as tt
                                    FROM mos_kh_smi.smicdc_p3nrd_step s
                                    LEFT JOIN (SELECT skiprule, lotid_ld, descript FROM mos_kh_smi.smicdc_p3nrd_skiprule) k
                                    ON s.skiprule = k.skiprule
                                    WHERE s.revstate = 'Active'
                                        AND s.processid in ('P13X', 'P14B', 'P15R', 'P18L', 'P18R', 'P18T', 'P19Z', 'P1SA', 'P1SC', 'P1SD', 'P1SF', 'P1SK', 'P1SP', 'P1SS', 'P1SU', 'P1SV')
                                    ORDER BY s.processid, s.stepseq
                                ),
              
                t0 as (SELECT 
                                s.processid,
                                s.category,
                                s.skiprule,
                                s.areaname,
                                s.eqptype,
                                s.layerid,
                        (case when s.eqptype<>'MMETAL' and substr(s.eqptype,1,1)='M' then '계측' else '메인' end) as stepseq_type,
                                s.stepseq,
                                s.descript,
                                s.recipeid,
                                
                                s.delaytime,
                                tee.eqpcham,
                                tee.eqpid,
                                tee.chamberid,
                                tee.batch_kind,
                                tee.prevent,
                                tee.type_body,
                                tee.type_cham,

                    tee.eventtime,
                                tee.eqpline
                                FROM (SELECT * FROM s /* WHERE stepseq_type = '메인' */)s
                                LEFT JOIN tee
                                ON s.processid = tee.process
                            AND s.stepseq = tee.step
                                    AND s.recipeid = tee.ppid),

                se as (SELECT 
                                DISTINCT
                                name as eqp,
                                ppid,
                                childeqp
                            FROM mos_kh_smi.smicdc_p3nrd_eqpcapability
                            WHERE revstate = 'Active'
                                AND INSTR(childeqp, ':')>0),

                t1 as (SELECT 
                    t0.*,
                    se.childeqp
                FROM t0
                LEFT JOIN se
                ON t0.eqpid = se.eqp
                AND t0.recipeid = se.ppid),

                t2 as (SELECT 
                                t1.processid,
                                t1.category,
                                t1.skiprule,
                                t1.areaname,
                                t1.eqptype,
                                t1.layerid,
                                t1.stepseq_type,
                                t1.stepseq,
                                t1.descript,
                                t1.recipeid,
                                t1.delaytime,
                                t1.eqpcham,
                                t1.eqpid,
                                t1.chamberid,
                                t1.batch_kind,
                                t1.prevent,
                                t1.type_body,
                                t1.type_cham,

                    t1.eventtime,
                                t1.eqpline,

                        se.childeqp
                FROM (SELECT * FROM t1 WHERE childeqp IS NULL) t1
                LEFT JOIN (SELECT * FROM se WHERE ppid = '-') se
                ON t1.eqpid = se.eqp),

                u as (SELECT * FROM t1
                UNION ALL
                SELECT * FROM t2 WHERE childeqp IS NOT NULL),

                u1 as (SELECT
                    u.* ,
                    (count(stepseq) over (partition by stepseq, eqpcham)) as C,
                    (count(childeqp) over (partition by stepseq, eqpcham)) as CC
                    FROM u)

                SELECT
                DISTINCT
                processid,	
                category,
                skiprule,
                areaname,
                eqptype,
                layerid,
                'PFR1' AS lineid,
                stepseq_type,
                stepseq,
                descript,
                recipeid,
                delaytime,

                eqpcham,
                eqpid,
                chamberid,
                batch_kind,
                prevent,
                type_body,
                type_cham,
                eventtime,
                eqpline,
                childeqp	
                FROM u1
                WHERE C=1
                    OR C>1 AND CC>0 AND childeqp IS NOT NULL
                    OR C>1 AND CC=0
                """

    path = """
            SELECT 
            proc_id,
            step_seq,
            to_step_seq
            FROM mos_kh_smi.smicdc_p3nrd_mc_prp_path 
            WHERE proc_id in ('P13X', 'P14B', 'P15R', 'P18L', 'P18R', 'P18T', 'P19Z', 'P1SA', 'P1SC', 'P1SD', 'P1SF', 'P1SK', 'P1SP', 'P1SS', 'P1SU', 'P1SV')
	            AND rev_status_code = "Active"
            """

    ############## get data
    with timer("getData: steptip"):
        df_steptip = getData(
                            param = steptip,
                            # user_name = 'minuk12.choi',
                            convert_type = my_convert_type,
                            verbose = my_verbose
                            )
        
    with timer("getData: path"):
        df_path = getData(
                            param = path,
                            # user_name = 'minuk12.choi',
                            convert_type = my_convert_type,
                            verbose = my_verbose
                            )

    with timer("build_step_jump_chain"):
        df_steptippath = build_step_jump_chain(df_steptip, df_path)   

    with timer("build_steptip_path"):
        df_raw = build_steptip_path(df_steptippath)   

    with timer("build_df_compatibility_summary"):
        df_final = build_df_compatibility_summary(
            df_raw=df_raw,
            df_steptip=df_steptip,
            days_threshold=30
        )

    # file_path = "check_result.xlsx"
    # safe_path = get_unique_filename(file_path)

    # t_excel_start = time.perf_counter()

    # # 데이터프레임 저장
    # df_final.to_excel(
    #     safe_path, 
    #     index=False, 
    #     engine="openpyxl")
    
    # t_excel_end = time.perf_counter()
    
    # print(f"파일이 저장되었습니다: {safe_path}")
    # print(f"파일이 저장시간: {t_excel_end-t_excel_start:.2f} sec")

    return df_final

def smicdc_merge2():

    my_convert_type = True
    my_verbose = True

    equipment = """
                WITH
                    e as (SELECT 
                    eqp_id,
                    case 
                    when substr(eqp_id, 1,1) = 'P' then 'PHOTO'  
                    when substr(eqp_id, 1,1) = 'E' then 'ETCH'  
                    when substr(eqp_id, 1,1) = 'M' then 'METRO'  
                    when substr(eqp_id, 1,1) = 'I' then 'IMP'  
                    when substr(eqp_id, 1,1) = 'D' then 'DIFF'  
                    when substr(eqp_id, 1,1) = 'C' then 'CMP'  
                    when substr(eqp_id, 1,1) = 'T' then 'CVD'  
                    when substr(eqp_id, 1,1) = 'S' then 'METAL'  
                    when substr(eqp_id, 1,1) = 'W' then 'CLN'  
                    when substr(eqp_id, 1,1) = 'F' then 'IMP'
                    end AS area_name,
                    origin_line_id,
                    eqp_model,
                    last_update_date,
                    MAX(last_update_date) OVER (PARTITION BY eqp_id) as maxdate
                    FROM mos_kh_smi.smimes_mi_equipment
                    WHERE tool_kind = 'EQP'
                        AND NVL(eqp_model, '-') <> '-'
                        AND SUBSTR(origin_line_id,1,1) <> 'X'
                    )

                    SELECT 
                    DISTINCT 
                    eqp_id,
                    area_name,
                    origin_line_id,
                    eqp_model
                    FROM e 
                    WHERE area_name IS NOT NULL
                        AND maxdate = last_update_date
                """

    ############## get data
    with timer("getData: equipment"):
        df_equipment = getData(
                            param = equipment,
                            # user_name = 'minuk12.choi',
                            convert_type = my_convert_type,
                            verbose = my_verbose
                            )
        
    return df_equipment


def smicdc_merge3():

    my_convert_type = True
    my_verbose = True

    steptip2 = """
 WITH
        t as (SELECT DISTINCT
                t.process, 
                t.step, 
                t.ppid, 
                t.eqpid, 
                (case when t.chamberid in ('-', 'MAIN') then 'MAIN' else chamberid end) as chamberid, 
                (case 
                when t.type='DOING' then 'DOING' 
                when t.type='PREVENT' then 'PREVENT'
                end) as prevent,
                (case when t.chamberid is not null and t.chamberid not in ('MAIN', '-') then concat(t.eqpid,'-',chamberid) else t.eqpid end) as ee,
                t.updated as eventtime
            FROM fab.n_nrd_trackinprevent t
            WHERE process in ('416GIGA3L_D0APVC', '416GIGA3L_D0APVP', '416GIGA3L_D0AP2C', '416GIGA3L_D0AP2P', '416GIGA3L_D0AP2R', '416GIGA3L_D0APVH', '416GIGA3L_D0AP2H', 'K4A2', '416GIGA3L_D0APVV', '416GIGA5A_D0AREV', '416GIGA0A_BMV0A', '4NDR5D_P3DFINTEG', '41TERA5I_HVFIN', '416GIGA5J_HUV1T', '416GIGA5J_HUV1B', 'K44H', '416GIGA5Q_GUVC', '4NAR3A_VSDRAM_C', '4NAR3A_VSDRAM_S', 'KGVB', '4NAR3A_VSDRAM_H', '416GIGA0J_VTCH', '416GIGA25A_VCTA', '4_2310_MO106', '416GIGA5L_FEOSC', '416GIGA6C_FECHL', 'KNYS', 'KNYR', 'KLWZ', 'KZMW', 'KZMX', 'KZ4M', 'KZ4U', 'KZ32', 'KZFR', 'KKM4', '41GIGA3L_SOMNGV', '4128GIGA8K_TVSL', '4LEDOS5G_PV3BOT', 'K4FC', 'K4A6', 'K42A', 'K4FE', 'K4A1', 'PBVV', 'K42S', 'K44J', 'K44K', 'K44L', 'K78J', 'P18R', 'P19T', 'KYH2', 'KZFO', '4PKG2E_LED_BOT', 'KOZA', 'KOKA', '4_2506_AA182', '4_2301_MO058', '4_2204_MM197', '416GIGA2L_NTSV4', '4_1906_DD064', '4_2006_MC103', '4_2603_AM100', '2GAB_CAPM3M', '4_2003_MM088', '2GAB_CAPA3M')
            ),

        tn as (SELECT DISTINCT
            (nvl((case when process<>'-' then 'process' end),'')||nvl((case when step<>'-' then 'step' end),'')||nvl((case when ppid<>'-' then 'ppid' end),'')) as j,
                t.process, 
                t.step, 
                t.ppid, 
                t.eqpid, 
                (case when t.chamberid in ('-', 'MAIN') then 'MAIN' else chamberid end) as chamberid, 
                t.type as prevent,
                (case when t.chamberid is not null and t.chamberid not in ('MAIN', '-') then concat(t.eqpid,'-',chamberid) else t.eqpid end) as eqpcham,
                t.eventtime
            FROM fab.n_nrd_trackinprevent t
            WHERE ((t.process = '-' or t.process is null) or (t.step='-' or t.step is null) or (t.eqpid = '-' or t.eqpid is null) or (t.ppid='-' or t.ppid is null)) and t.type = 'PREVENT'
            ),

        tt as (SELECT
                t.*,
                (count(case when t.prevent = 'DOING' then t.prevent end) OVER (PARTITION BY t.process, t.step, t.ppid, t.ee)) as C,
                (count(t.ee) over (partition by t.process, t.step, t.ppid, t.ee)) as CC,
                (max(t.eventtime) over (partition by t.process, t.step, t.ppid, t.ee, t.prevent)) as M
            FROM t),

        ttt as (SELECT 
                * 
            FROM tt
            WHERE tt.cc>1 and tt.c>0 and tt.prevent='DOING' and tt.m=tt.eventtime
                OR tt.cc>1 and tt.c=0 and tt.m=tt.eventtime
                OR tt.cc=1),

        er as (SELECT      
            eqp_id,
            batch_kind,
            origin_line_id,      
            eqp_parent_id,
            eqp_type,
            (case when count(case when tool_kind='CHAMBER' then eqp_parent_id end) over (partition by eqp_parent_id)>=1 then 'CHAM설비' end) as cc
        FROM fab.m_mi_equipment where line_id = 'KFR4'),

        te as (SELECT 
                ttt.process, 
                ttt.step, 
                ttt.ppid, 
                ttt.ee,
                ttt.eqpid, 
                ttt.chamberid, 
                ttt.prevent,
                ttt.eventtime,
                e.batch_kind,
                e.origin_line_id as eqp_line,
                e.eqp_type
            FROM ttt
            LEFT JOIN (SELECT DISTINCT
                        eqp_id,
                        batch_kind,
                        origin_line_id,
                        eqp_type
                        FROM er) e
            ON ttt.ee = e.eqp_id
            ORDER BY process, step, ppid, ee),

        tee as (SELECT                     
                a.process,
                a.step,
                a.ppid,
                IFNULL(case when ifnull(a.batch_kind, '-') in ('BATCH_FURNACE', 'BATCH_WET') then a.eqpid else b.ee end, a.eqpid) as eqpcham,
                a.eqpid,
                IFNULL(case when ifnull(a.batch_kind, '-') in ('BATCH_FURNACE', 'BATCH_WET') then NULL else b.chamberid end, NULL) as chamberid,
                a.batch_kind,
                (case 
                when a.prevent='PREVENT' or b.prevent='PREVENT' then 'PREVENT'
                else 'DOING' end) as prevent,   
                a.prevent as type_body,
                b.prevent as type_cham,          
                IFNULL(case when ifnull(a.batch_kind, '-') in ('BATCH_FURNACE', 'BATCH_WET') then a.eventtime else b.eventtime end, a.eventtime) as eventtime,
                IFNULL(a.eqp_line, b.eqp_line) as eqpline,
                IFNULL(a.eqp_type, b.eqp_type) as eqptype
            FROM (SELECT * FROM te WHERE chamberid in ('MAIN', '-') or chamberid is null) a
            LEFT JOIN (SELECT * FROM te WHERE chamberid not in ('MAIN', '-') and chamberid is not null) b
            ON a.process = b.process
                AND a.step = b.step
                AND a.ppid = b.ppid
                AND a.eqpid = b.eqpid),

        s as (select
                s.processid,
                s.stepseq,
                s.layerid,
                s.skiprule,
                s.descript,
                s.areaname,
                s.eqptype,
                s.recipeid,
                s.delaytime,
                s.eqpgroup as eqpgroup_raw,
                e.eqp_id
        from (select * from mos_kh_smi.smicdc_nrd_step where substr(descript,1,2) not in ('SP', 'SE', 'SC')) s, 
            (select processid, stepseq from mos_kh_smi.smicdc_nrd_steprule where rulename in ('ECN') and rulestatus is null and lotid is null) sr
        LEFT JOIN (select 
                    eqp_group_name, 
                    eqp_id 
                    from mos_kh_smi.smicdc_nrd_mc_eqp_group_list 
                    where instr(eqp_id, 'OFF')=0 
                    order by eqp_group_name, eqp_id) e
        on s.eqpgroup = e.eqp_group_name

        where s.processid = sr.processid
            and s.stepseq = sr.stepseq
            and s.revstate = 'Active'
            and s.processid in ('416GIGA3L_D0APVC', '416GIGA3L_D0APVP', '416GIGA3L_D0AP2C', '416GIGA3L_D0AP2P', '416GIGA3L_D0AP2R', '416GIGA3L_D0APVH', '416GIGA3L_D0AP2H', 'K4A2', '416GIGA3L_D0APVV', '416GIGA5A_D0AREV', '416GIGA0A_BMV0A', '4NDR5D_P3DFINTEG', '41TERA5I_HVFIN', '416GIGA5J_HUV1T', '416GIGA5J_HUV1B', 'K44H', '416GIGA5Q_GUVC', '4NAR3A_VSDRAM_C', '4NAR3A_VSDRAM_S', 'KGVB', '4NAR3A_VSDRAM_H', '416GIGA0J_VTCH', '416GIGA25A_VCTA', '4_2310_MO106', '416GIGA5L_FEOSC', '416GIGA6C_FECHL', 'KNYS', 'KNYR', 'KLWZ', 'KZMW', 'KZMX', 'KZ4M', 'KZ4U', 'KZ32', 'KZFR', 'KKM4', '41GIGA3L_SOMNGV', '4128GIGA8K_TVSL', '4LEDOS5G_PV3BOT', 'K4FC', 'K4A6', 'K42A', 'K4FE', 'K4A1', 'PBVV', 'K42S', 'K44J', 'K44K', 'K44L', 'K78J', 'P18R', 'P19T', 'KYH2', 'KZFO', '4PKG2E_LED_BOT', 'KOZA', 'KOKA', '4_2506_AA182', '4_2301_MO058', '4_2204_MM197', '416GIGA2L_NTSV4', '4_1906_DD064', '4_2006_MC103', '4_2603_AM100', '2GAB_CAPM3M', '4_2003_MM088', '2GAB_CAPA3M')
        order by s.stepseq),

        t0 as (SELECT 
                s.processid,                           
                s.skiprule,
                s.areaname,
                s.eqptype,
                s.layerid,
                (case when s.eqptype<>'MMETAL' and substr(s.eqptype,1,1)='M' then '계측' else '메인' end) as stepseq_type,
                s.stepseq,
                s.descript,
                s.recipeid,
	     s.delaytime,
                s.eqpgroup_raw,
                tee.eqpcham,
                nvl(tee.eqpid, s.eqp_id) as eqpid,
                tee.chamberid,
                tee.batch_kind,
                tee.prevent,
                tee.type_body,
                tee.type_cham,
                tee.eventtime,
                tee.eqpline
            FROM s  
            LEFT JOIN tee
            ON s.processid = tee.process
                AND s.stepseq = tee.step
                AND s.recipeid = tee.ppid
                AND  s.eqp_id = tee.eqpid),

        t1 as (select 
                t0.processid,                           
                t0.skiprule,
                t0.areaname,
                t0.eqptype,
                t0.layerid,
                t0.stepseq_type,
                t0.stepseq,
                t0.descript,
                t0.recipeid,
                t0.delaytime,
                t0.eqpgroup_raw,
                nvl(tee.eqpcham, t0.eqpid) as eqpcham,
                nvl(tee.eqpid, t0.eqpid) as eqpid,
                tee.chamberid,
                tee.batch_kind,
                tee.prevent,
                tee.type_body,
                tee.type_cham,
                tee.eventtime,
                tee.eqpline            
            from (select * from t0 where prevent is null) t0
            LEFT JOIN tee
            on t0.processid = tee.process
                AND t0.stepseq = tee.step
                AND t0.recipeid = tee.ppid),

        t2 as (select * from t1 
            union all
                select * from t0 where prevent is not null),

        t3 as (select
                t2.processid,                           
                t2.skiprule,
                t2.areaname,
                t2.eqptype,
                t2.layerid,
                t2.stepseq_type,
                t2.stepseq,
                t2.descript,
                t2.recipeid,
                t2.delaytime,
                t2.eqpgroup_raw,
                t2.eqpcham,
                t2.eqpid,
                t2.chamberid,
                t2.batch_kind,
                nvl(tn.prevent, t2.prevent) as prevent,
                nvl(case when tn.chamberid = 'MAIN' then tn.prevent end, t2.type_body) as type_body,
                nvl(case when tn.chamberid <> 'MAIN' then tn.prevent end, t2.type_cham) as type_cham,
                t2.eventtime,
                t2.eqpline
        from t2
        left join (select * from tn where j='ppid') tn
        on t2.recipeid = tn.ppid
            and t2.eqpcham = tn.eqpcham),

        t4 as (select
                t3.processid,                           
                t3.skiprule,
                t3.areaname,
                t3.eqptype,
                t3.layerid,
                t3.stepseq_type,
                t3.stepseq,
                t3.descript,
                t3.recipeid,
                t3.delaytime,
                
                t3.eqpgroup_raw,
                t3.eqpcham,
                t3.eqpid,
                t3.chamberid,
                t3.batch_kind,
                nvl(tn.prevent, t3.prevent) as prevent,
                nvl(case when tn.chamberid = 'MAIN' then tn.prevent end, t3.type_body) as type_body,
                nvl(case when tn.chamberid <> 'MAIN' then tn.prevent end, t3.type_cham) as type_cham,
                t3.eventtime,
                t3.eqpline
        from t3
        left join (select * from tn where j='process') tn
        on t3.processid = tn.process
            and t3.eqpcham = tn.eqpcham),

        t5 as (select
                t4.processid,                           
                t4.skiprule,
                t4.areaname,
                t4.eqptype,
                t4.layerid,
                t4.stepseq_type,
                t4.stepseq,
                t4.descript,
                t4.recipeid,
                t4.delaytime,
                
                t4.eqpgroup_raw,
                t4.eqpcham,
                t4.eqpid,
                t4.chamberid,
                t4.batch_kind,
                nvl(tn.prevent, t4.prevent) as prevent,
                nvl(case when tn.chamberid = 'MAIN' then tn.prevent end, t4.type_body) as type_body,
                nvl(case when tn.chamberid <> 'MAIN' then tn.prevent end, t4.type_cham) as type_cham,
                t4.eventtime,
                t4.eqpline
        from t4
        left join (select * from tn where j='step') tn
        on t4.stepseq = tn.step
            and t4.eqpcham = tn.eqpcham),

        t6 as (select	
                t5.processid,                           	
                t5.skiprule,	
                t5.areaname,	
                t5.eqptype,	
                t5.layerid,	
                t5.stepseq_type,	
                t5.stepseq,	
                t5.descript,	
                t5.recipeid,	
                t5.delaytime,
                
                t5.eqpgroup_raw,	
                t5.eqpcham,	
                t5.eqpid,	
                t5.chamberid,	
                t5.batch_kind,	
                nvl(tn.prevent, t5.prevent) as prevent,	
                nvl(case when tn.chamberid = 'MAIN' then tn.prevent end, t5.type_body) as type_body,
                nvl(case when tn.chamberid <> 'MAIN' then tn.prevent end, t5.type_cham) as type_cham,	
                t5.eventtime,	
                t5.eqpline	
        from t5	
        left join (select * from tn where j='processppid') tn	
        on t5.recipeid = tn.ppid	
            and t5.processid = tn.process
            and t5.eqpcham = tn.eqpcham),

        t7 as (select	
                t6.processid,                           	
                t6.skiprule,	
                t6.areaname,	
                t6.eqptype,	
                t6.layerid,	
                t6.stepseq_type,	
                t6.stepseq,	
                t6.descript,	
                t6.recipeid,
                t6.delaytime,
                
                t6.eqpgroup_raw,	
                t6.eqpcham,	
                t6.eqpid,	
                t6.chamberid,	
                t6.batch_kind,	
                nvl(tn.prevent, t6.prevent) as prevent,	
                nvl(case when tn.chamberid = 'MAIN' then tn.prevent end, t6.type_body) as type_body,
                nvl(case when tn.chamberid <> 'MAIN' then tn.prevent end, t6.type_cham) as type_cham,
                t6.eventtime,	
                t6.eqpline	
        from t6	
        left join (select * from tn where j='processstep') tn	
        on t6.stepseq = tn.step	
            and t6.processid = tn.process
            and t6.eqpcham = tn.eqpcham),

        t8 as (select	
                t7.processid,                           	
                t7.skiprule,	
                t7.areaname,	
                t7.eqptype,	
                t7.layerid,	
                t7.stepseq_type,	
                t7.stepseq,	
                t7.descript,	
                t7.recipeid,
                t7.delaytime,
                
                t7.eqpgroup_raw,	
                t7.eqpcham,	
                t7.eqpid,	
                t7.chamberid,	
                t7.batch_kind,	
                nvl(tn.prevent, t7.prevent) as prevent,	
                nvl(case when tn.chamberid = 'MAIN' then tn.prevent end, t7.type_body) as type_body,
                nvl(case when tn.chamberid <> 'MAIN' then tn.prevent end, t7.type_cham) as type_cham,	
                t7.eventtime,	
                t7.eqpline	
        from t7	
        left join (select * from tn where j='stepppid') tn	
        on t7.recipeid = tn.ppid	
            and t7.stepseq = tn.step
            and t7.eqpcham = tn.eqpcham),

        t9 as (select 
                t8.processid,                           	
                t8.skiprule as category,	
                t8.skiprule as skiprule,
                (case 
            when substr(eqpcham,1,1)='M' then 'METRO'
            when substr(eqpcham,1,1)='P' then 'PHOTO'
            when substr(eqpcham,1,1)='E' then 'ETCH'
            when substr(eqpcham,1,1)='S' then 'METAL'
            when substr(eqpcham,1,1)='T' then 'CVD'
            when substr(eqpcham,1,1)='W' then 'CLN'
            when substr(eqpcham,1,1)='D' then 'DIFF'
            when substr(eqpcham,1,1)='I' then 'IMP'
            when substr(eqpcham,1,1)='F' then 'IMP'
                end) as areaname,	
                t8.eqptype,	
                t8.layerid,	
                "KFR4" as lineid,
                t8.stepseq_type,
                t8.stepseq,	
                t8.descript,	
                t8.recipeid,	
                t8.delaytime,
                
                nvl(t8.batch_kind, e.batch_kind) as batch_kind,
                t8.eqpcham,	
                t8.eqpid,	
                t8.chamberid,	
                t8.prevent,	
                t8.type_body,
                t8.type_cham,	
                t8.eventtime,	
                nvl(t8.eqpline, e.origin_line_id) as eqpline
        from t8
        LEFT JOIN (SELECT DISTINCT
                        eqp_id,
                        batch_kind,
                        origin_line_id
                        FROM fab.m_mi_equipment where line_id = 'KFR4') e
        ON t8.eqpcham = e.eqp_id),

        ce as (SELECT DISTINCT
            name as eqp,
            ppid,
            childeqp
                FROM MOS_KH_SMI.SMICDC_NRD_EQPCAPABILITY
            where revstate = 'Active'
            
            and status = 'Available'),

        t10 as (select
                processid,                           	
                category,	
                skiprule,
                areaname,	
                eqptype,	
                layerid,	
                lineid,
                stepseq_type,
                stepseq,	
                descript,	
                recipeid,	
                delaytime,
                batch_kind,
                eqpcham,	
                eqpid,	
                chamberid,	
                prevent,	
                type_body,
                type_cham,	
                eventtime,	
            childeqp,
                eqpline
        from t9
        left join (select * from ce where ppid<>'-') ce
        on t9.eqpid = ce.eqp
            and t9.recipeid = ce.ppid),

        t11 as (select 
                processid,                           	
                category,	
                skiprule,
                areaname,	
                eqptype,	
                layerid,	
                lineid,
                stepseq_type,
                stepseq,	
                descript,	
                recipeid,	
                delaytime,
                batch_kind,
                eqpcham,	
                eqpid,	
                chamberid,	
                prevent,	
                type_body,
                type_cham,	
                eventtime,	
            nvl(t10.childeqp, ce.childeqp) as childeqp,
                eqpline
        from t10
        left join (select * from ce where ppid = '-') ce
        on t10.eqpid = ce.eqp)

        select
                processid,                           	
                category,	
                skiprule,
                areaname,	
                eqptype,	
                layerid,	
                lineid,
                stepseq_type,
                stepseq,	
                descript,	
                recipeid,	
                delaytime,
                batch_kind,
                eqpcham,	
                eqpid,	
                chamberid,	
                nvl(t11.prevent, case when er.cc is not null then '미등록' end) as prevent,	
                type_body,
                type_cham,	
                eventtime,	
                (case when instr(childeqp,':')>0 then childeqp else null end) as childeqp,
                eqpline
        from t11
        left join (select distinct eqp_parent_id, cc from er where cc is not null and substr(eqp_parent_id,1,1)<>'P') er
        on t11.eqpid = er.eqp_parent_id
            """

    ############## get data
    with timer("getData: steptip2"):
        df_steptip2 = getData(
                            param = steptip2,
                            # user_name = 'minuk12.choi',
                            convert_type = my_convert_type,
                            verbose = my_verbose
                            )

    with timer("build_b_table_from_a"):
        df_final2 = build_b_table_from_a(
            df_final=df_steptip2,            
            days_threshold=30
        )


    return df_final2


def smicdc_merge4():

    my_convert_type = True
    my_verbose = True

    steptip3 = """
with
                t as (SELECT DISTINCT
                                        t.process, 
                                        t.step, 
                                        t.ppid, 
                                        t.eqpid, 
                                        (case when t.chamberid in ('-', 'MAIN') then 'MAIN' else chamberid end) as chamberid, 
                        (case 
                        when t.type='DOING' then 'DOING' 
                        when t.type='PREVENT' AND IFNULL(t.checkcount,0)=0 then 'PREVENT' 
                        when t.type='PREVENT' AND IFNULL(t.tkin_count,0)>=IFNULL(checkcount,0) then 'PREVENT' 
                        when t.type='PREVENT' AND IFNULL(t.tkin_count,0)<IFNULL(checkcount,0) then 'DOING' 
                        end) as prevent,
                                        (case when t.chamberid is not null and t.chamberid not in ('MAIN', '-') then concat(t.eqpid,'-',chamberid) else t.eqpid end) as ee,
                        t.eventtime
                FROM mos_kh_smi.smicdc_nrdk_trackinprevent t
                WHERE process in ('K72A', '416GIGA3L_D0AP2P', '416GIGA3L_D0AP2C', 'K75F', 'K75U', 'K76L', 'K76R', 'K78E', 'K78F', 'K78K', 'K7A1', 'K4A2', 'K7B8', 'PPCR', '7_2508_FE280', '7_2508_FE281', '7_2508_FE282', '7_2508_FE279', '7_2511_FE288', 'K7FE', '7_2508_MC280', 'K4A2', 'K7B8', 'PPCR', '7_2508_FE280', '7_2508_FE281', '7_2508_FE282', '7_2508_FE279', '7_2511_FE288', 'K7FE', '7_2508_MC280')
                ),

                tt as (SELECT
                    t.*,
                    (count(case when t.prevent = 'DOING' then t.prevent end) OVER (PARTITION BY t.process, t.step, t.ppid, t.ee)) as C,
                    (count(t.ee) over (partition by t.process, t.step, t.ppid, t.ee)) as CC,
                    (max(t.eventtime) over (partition by t.process, t.step, t.ppid, t.ee, t.prevent)) as M
                        FROM t),

                ttt as (SELECT 
                * 
                FROM tt
                WHERE tt.cc>1 and tt.c>0 and tt.prevent='DOING' and tt.m=tt.eventtime
                    OR tt.cc>1 and tt.c=0 and tt.m=tt.eventtime
                    OR tt.cc=1),

                te as (SELECT 
                                        ttt.process, 
                                        ttt.step, 
                                        ttt.ppid, 
                                        ttt.ee,
                                        ttt.eqpid, 
                                        ttt.chamberid, 
                            ttt.prevent,
                        ttt.eventtime,
                                        e.batch_kind,
                                        e.origin_line_id as eqp_line,
                                        e.eqp_type
                                    FROM ttt
                                    LEFT JOIN (SELECT DISTINCT
                                                eqp_id,
                                                batch_kind,
                                                origin_line_id,
                                                eqp_type
                                                FROM fab.m_mi_equipment where line_id = 'KFR7') e
                                        ON ttt.ee = e.eqp_id
                                    ORDER BY process, step, ppid, ee),

                tee as (SELECT                     
                                    a.process,
                                    a.step,
                                    a.ppid,
                                    IFNULL(case when ifnull(a.batch_kind, '-') in ('BATCH_FURNACE', 'BATCH_WET') then a.eqpid else b.ee end, a.eqpid) as eqpcham,
                                    a.eqpid,
                                    IFNULL(case when ifnull(a.batch_kind, '-') in ('BATCH_FURNACE', 'BATCH_WET') then NULL else b.chamberid end, NULL) as chamberid,
                                    a.batch_kind,
                                    (case 
                        when a.prevent='PREVENT' or b.prevent='PREVENT' then 'PREVENT'
                                    else 'DOING' end) as prevent,   
                                    a.prevent as type_body,
                                    b.prevent as type_cham,          
                        IFNULL(case when ifnull(a.batch_kind, '-') in ('BATCH_FURNACE', 'BATCH_WET') then a.eventtime else b.eventtime end, a.eventtime) as eventtime,
                                    IFNULL(a.eqp_line, b.eqp_line) as eqpline,
                                    IFNULL(a.eqp_type, b.eqp_type) as eqptype
                                FROM (SELECT * FROM te WHERE chamberid in ('MAIN', '-') or chamberid is null) a
                                LEFT JOIN (SELECT * FROM te WHERE chamberid not in ('MAIN', '-') and chamberid is not null) b
                                    ON a.process = b.process
                                        AND a.step = b.step
                                        AND a.ppid = b.ppid
                                        AND a.eqpid = b.eqpid),

s as (select
s.processid,
s.category,
s.step_level as skiprule,
s.eqptype,
s.layerid,
(case when s.eqptype<>'MMETAL' and substr(s.eqptype,1,1)='M' then '계측' else '메인' end) as stepseq_type,
s.stepseq,
s.descript,
s.recipeid,
s.delaytime,
NULL as n2_delay_time_mins,
s.eqpgroup as eqpgroup_raw,
e.eqp_id
from mos_kh_smi.smicdc_nrdk_ecn_step s
left join (select eqp_group_name, eqp_id from mos_kh_smi.smicdc_nrdk_mc_eqp_group_list where eqp_group_name<>'JSORTE' or eqp_group_name='JSORTE' and (substr(eqp_id,1,1)<>'I' and eqp_id<>'JSORTE') order by eqp_group_name, eqp_id) e
on s.eqpgroup = e.eqp_group_name
where s.processid in ('K72A', '416GIGA3L_D0AP2P', '416GIGA3L_D0AP2C', 'K75F', 'K75U', 'K76L', 'K76R', 'K78E', 'K78F', 'K78K', 'K7A1', 'K4A2', 'K7B8', 'PPCR', '7_2508_FE280', '7_2508_FE281', '7_2508_FE282', '7_2508_FE279', '7_2511_FE288', 'K7FE', '7_2508_MC280', 'K4A2', 'K7B8', 'PPCR', '7_2508_FE280', '7_2508_FE281', '7_2508_FE282', '7_2508_FE279', '7_2511_FE288', 'K7FE', '7_2508_MC280')
),

t0 as (select
s.processid,
s.category,
s.skiprule,
s.eqptype,
s.layerid,
s.stepseq_type,
s.stepseq,
s.descript,
s.recipeid,
s.delaytime,
s.eqpgroup_raw,
nvl(tee.eqpcham, s.eqp_id) as eqpcham,
nvl(tee.eqpid, s.eqp_id) as eqpid,
tee.chamberid,
tee.batch_kind,
tee.prevent,
tee.type_body,
tee.type_cham,
tee.eventtime,
tee.eqpline
from s
left join tee
on s.processid = tee.process
	and s.stepseq = tee.step
	and s.recipeid = tee.ppid),

t1 as (select 
t0.processid,
t0.category,
t0.skiprule,
t0.eqptype,
t0.layerid,
t0.stepseq_type,
t0.stepseq,
t0.descript,
t0.recipeid,
t0.delaytime,
t0.eqpgroup_raw,
t0.eqpcham,
t0.eqpid,
t0.chamberid,
nvl(t0.batch_kind, e.batch_kind) as batch_kind,
t0.prevent,
t0.type_body,
t0.type_cham,
t0.eventtime,
nvl(t0.eqpline, e.origin_line_id) as eqpline
from t0
left join (select eqp_id, batch_kind, eqp_type, origin_line_id from fab.m_mi_equipment where line_id = 'KFR7') e
on t0.eqpcham = e.eqp_id),

t2 as (select
t1.processid,
t1.category,
t1.skiprule,
(case 
            when substr(t1.eqpcham,1,1)='M' then 'METRO'
            when substr(t1.eqpcham,1,1)='P' then 'PHOTO'
            when substr(t1.eqpcham,1,1)='E' then 'ETCH'
            when substr(t1.eqpcham,1,1)='S' then 'METAL'
            when substr(t1.eqpcham,1,1)='T' then 'CVD'
            when substr(t1.eqpcham,1,1)='W' then 'CLN'
            when substr(t1.eqpcham,1,1)='D' then 'DIFF'
            when substr(t1.eqpcham,1,1)='I' then 'IMP'
            when substr(t1.eqpcham,1,1)='F' then 'IMP'
                end) as areaname,	
t1.eqptype,
t1.layerid,
'KFR7' as lineid,
t1.stepseq_type,
t1.stepseq,
t1.descript,
t1.recipeid,
t1.delaytime,
t1.eqpcham,
t1.eqpid,
t1.chamberid,
t1.batch_kind,
nvl(t1.prevent, '미등록') as prevent,
t1.type_body,
t1.type_cham,
t1.eventtime,
t1.eqpline
from t1),

        ce as (SELECT DISTINCT
            name as eqp,
            ppid,
            childeqp
                FROM MOS_KH_SMI.SMICDC_NRDK_EQPCAPABILITY
            where revstate = 'Active'
            
            and status = 'Available'),

        t10 as (select
                processid,                           	
                category,	
                skiprule,
                areaname,	
                eqptype,	
                layerid,	
                lineid,
                stepseq_type,
                stepseq,	
                descript,	
                recipeid,	
                delaytime,

                batch_kind,
                eqpcham,	
                eqpid,	
                chamberid,	
                prevent,	
                type_body,
                type_cham,	
                eventtime,	
            childeqp,
                eqpline
        from t2
        left join (select * from ce where ppid<>'-') ce
        on t2.eqpid = ce.eqp
            and t2.recipeid = ce.ppid),

       t11 as (select 
                processid,                           	
                category,	
                skiprule,
                areaname,	
                eqptype,	
                layerid,	
                lineid,
                stepseq_type,
                stepseq,	
                descript,	
                recipeid,	
                delaytime,

                batch_kind,
                eqpcham,	
                eqpid,	
                chamberid,	
                prevent,	
                type_body,
                type_cham,	
                eventtime,	
            nvl(t10.childeqp, ce.childeqp) as childeqp,
                eqpline
        from t10
        left join (select * from ce where ppid = '-') ce
        on t10.eqpid = ce.eqp),

        er as (SELECT      
            eqp_id,
            batch_kind,
            origin_line_id,      
            eqp_parent_id,
            eqp_type,
            (case when count(case when tool_kind='CHAMBER' then eqp_parent_id end) over (partition by eqp_parent_id)>=1 then 'CHAM설비' end) as cc
        FROM fab.m_mi_equipment where line_id = 'KFR7')

        select
                processid,                           	
                category,	
                skiprule,
                areaname,	
                eqptype,	
                layerid,	
                lineid,
                stepseq_type,
                stepseq,	
                descript,	
                recipeid,
                delaytime,
	
                batch_kind,
                eqpcham,	
                eqpid,	
                chamberid,	
                nvl(t11.prevent, case when er.cc is not null then '미등록' end) as prevent,	
                type_body,
                type_cham,	
                eventtime,	
                (case when instr(childeqp,':')>0 then childeqp else null end) as childeqp,
                eqpline
        from t11
        left join (select distinct eqp_parent_id, cc from er where cc is not null and substr(eqp_parent_id,1,1)<>'P') er
        on t11.eqpid = er.eqp_parent_id
            """

    ############## get data
    with timer("getData: steptip3"):
        df_steptip3 = getData(
                            param = steptip3,
                            # user_name = 'minuk12.choi',
                            convert_type = my_convert_type,
                            verbose = my_verbose
                            )

    with timer("build_b_table_from_a"):
        df_final3 = build_b_table_from_a(
            df_final=df_steptip3,            
            days_threshold=30
        )


    return df_final3


def smicdc_merge5():

    my_convert_type = True
    my_verbose = True

    steptip4 = """
with
                t as (SELECT DISTINCT
                                        t.process, 
                                        t.step, 
                                        t.ppid, 
                                        t.eqpid, 
                                        (case when t.chamberid in ('-', 'MAIN') then 'MAIN' else chamberid end) as chamberid, 
                        (case 
                        when t.type='DOING' then 'DOING' 
                        when t.type='PREVENT' AND IFNULL(t.checkcount,0)=0 then 'PREVENT' 
                        when t.type='PREVENT' AND IFNULL(t.tkin_count,0)>=IFNULL(checkcount,0) then 'PREVENT' 
                        when t.type='PREVENT' AND IFNULL(t.tkin_count,0)<IFNULL(checkcount,0) then 'DOING' 
                        end) as prevent,
                                        (case when t.chamberid is not null and t.chamberid not in ('MAIN', '-') then concat(t.eqpid,'-',chamberid) else t.eqpid end) as ee,
                        t.eventtime
                FROM mos_kh_smi.smicdc_p3nrd_trackinprevent t
                WHERE process in ('K42V', 'K42S', 'PBVV', 'K44H', 'K4B1', 'K4B2', 'K4B3', 'K4B4')
                ),

                tt as (SELECT
                    t.*,
                    (count(case when t.prevent = 'DOING' then t.prevent end) OVER (PARTITION BY t.process, t.step, t.ppid, t.ee)) as C,
                    (count(t.ee) over (partition by t.process, t.step, t.ppid, t.ee)) as CC,
                    (max(t.eventtime) over (partition by t.process, t.step, t.ppid, t.ee, t.prevent)) as M
                        FROM t),

                ttt as (SELECT 
                * 
                FROM tt
                WHERE tt.cc>1 and tt.c>0 and tt.prevent='DOING' and tt.m=tt.eventtime
                    OR tt.cc>1 and tt.c=0 and tt.m=tt.eventtime
                    OR tt.cc=1),

                te as (SELECT 
                                        ttt.process, 
                                        ttt.step, 
                                        ttt.ppid, 
                                        ttt.ee,
                                        ttt.eqpid, 
                                        ttt.chamberid, 
                            ttt.prevent,
                        ttt.eventtime,
                                        e.batch_kind,
                                        e.origin_line_id as eqp_line
                                    FROM ttt
                                    LEFT JOIN (SELECT DISTINCT
                                                eqp_id,
                                                batch_kind,
                                                origin_line_id
                                                FROM fab.m_mi_equipment where line_id = 'PFR1') e
                                        ON ttt.ee = e.eqp_id
                                    ORDER BY process, step, ppid, ee),

                tee as (SELECT                     
                                    a.process,
                                    a.step,
                                    a.ppid,
                                    IFNULL(case when ifnull(a.batch_kind, '-') in ('BATCH_FURNACE', 'BATCH_WET') then a.eqpid else b.ee end, a.eqpid) as eqpcham,
                                    a.eqpid,
                                    IFNULL(case when ifnull(a.batch_kind, '-') in ('BATCH_FURNACE', 'BATCH_WET') then NULL else b.chamberid end, NULL) as chamberid,
                                    a.batch_kind,
                                    (case 
                        when a.prevent='PREVENT' or b.prevent='PREVENT' then 'PREVENT'
                                    else 'DOING' end) as prevent,   
                                    a.prevent as type_body,
                                    b.prevent as type_cham,          
                        IFNULL(case when ifnull(a.batch_kind, '-') in ('BATCH_FURNACE', 'BATCH_WET') then a.eventtime else b.eventtime end, a.eventtime) as eventtime,
                                    IFNULL(a.eqp_line, b.eqp_line) as eqpline
                                FROM (SELECT * FROM te WHERE chamberid in ('MAIN', '-') or chamberid is null) a
                                LEFT JOIN (SELECT * FROM te WHERE chamberid not in ('MAIN', '-') and chamberid is not null) b
                                    ON a.process = b.process
                                        AND a.step = b.step
                                        AND a.ppid = b.ppid
                                        AND a.eqpid = b.eqpid),

s as (select
s.processid,
s.category,
s.step_level as skiprule,
s.eqptype,
s.layerid,
(case when s.eqptype<>'MMETAL' and substr(s.eqptype,1,1)='M' then '계측' else '메인' end) as stepseq_type,
s.stepseq,
s.descript,
s.recipeid,
s.delaytime,
NULL as n2_delay_time_mins,
s.eqpgroup as eqpgroup_raw,
e.eqp_id
from mos_kh_smi.smicdc_p3nrd_ecn_step s
left join (select eqp_group_name, eqp_id from mos_kh_smi.smicdc_p3nrd_mc_eqp_group_list where eqp_group_name<>'JSORTE' or eqp_group_name='JSORTE' and (substr(eqp_id,1,1)<>'I' and eqp_id<>'JSORTE') order by eqp_group_name, eqp_id) e
on s.eqpgroup = e.eqp_group_name
where s.processid in ('K42V', 'K42S', 'PBVV', 'K44H', 'K4B1', 'K4B2', 'K4B3', 'K4B4')
),

t0 as (select
s.processid,
s.category,
s.skiprule,
s.eqptype,
s.layerid,
s.stepseq_type,
s.stepseq,
s.descript,
s.recipeid,
s.delaytime,
s.eqpgroup_raw,
nvl(tee.eqpcham, s.eqp_id) as eqpcham,
nvl(tee.eqpid, s.eqp_id) as eqpid,
tee.chamberid,
tee.batch_kind,
tee.prevent,
tee.type_body,
tee.type_cham,
tee.eventtime,
tee.eqpline
from s
left join tee
on s.processid = tee.process
	and s.stepseq = tee.step
	and s.recipeid = tee.ppid),

t1 as (select 
t0.processid,
t0.category,
t0.skiprule,
t0.eqptype,
t0.layerid,
t0.stepseq_type,
t0.stepseq,
t0.descript,
t0.recipeid,
t0.delaytime,
t0.eqpgroup_raw,
t0.eqpcham,
t0.eqpid,
t0.chamberid,
nvl(t0.batch_kind, e.batch_kind) as batch_kind,
t0.prevent,
t0.type_body,
t0.type_cham,
t0.eventtime,
nvl(t0.eqpline, e.origin_line_id) as eqpline
from t0
left join (select eqp_id, batch_kind, origin_line_id from fab.m_mi_equipment where line_id = 'PFR1') e
on t0.eqpcham = e.eqp_id),

t2 as (select
t1.processid,
t1.category,
t1.skiprule,
(case 
            when substr(t1.eqpcham,1,1)='M' then 'METRO'
            when substr(t1.eqpcham,1,1)='P' then 'PHOTO'
            when substr(t1.eqpcham,1,1)='E' then 'ETCH'
            when substr(t1.eqpcham,1,1)='S' then 'METAL'
            when substr(t1.eqpcham,1,1)='T' then 'CVD'
            when substr(t1.eqpcham,1,1)='W' then 'CLN'
            when substr(t1.eqpcham,1,1)='D' then 'DIFF'
            when substr(t1.eqpcham,1,1)='I' then 'IMP'
            when substr(t1.eqpcham,1,1)='F' then 'IMP'
                end) as areaname,	
t1.eqptype,
t1.layerid,
'PFR1' as lineid,
t1.stepseq_type,
t1.stepseq,
t1.descript,
t1.recipeid,
t1.delaytime,
t1.eqpcham,
t1.eqpid,
t1.chamberid,
t1.batch_kind,
nvl(t1.prevent, '미등록') as prevent,
t1.type_body,
t1.type_cham,
t1.eventtime,
t1.eqpline
from t1),

        ce as (SELECT DISTINCT
            name as eqp,
            ppid,
            childeqp
                FROM MOS_KH_SMI.SMICDC_P3NRD_EQPCAPABILITY
            where revstate = 'Active'
            
            and status = 'Available'),

        t10 as (select
                processid,                           	
                category,	
                skiprule,
                areaname,	
                eqptype,	
                layerid,	
                lineid,
                stepseq_type,
                stepseq,	
                descript,	
                recipeid,	
                delaytime,
                batch_kind,
                eqpcham,	
                eqpid,	
                chamberid,	
                prevent,	
                type_body,
                type_cham,	
                eventtime,	
            childeqp,
                eqpline
        from t2
        left join (select * from ce where ppid<>'-') ce
        on t2.eqpid = ce.eqp
            and t2.recipeid = ce.ppid),

       t11 as (select 
                processid,                           	
                category,	
                skiprule,
                areaname,	
                eqptype,	
                layerid,	
                lineid,
                stepseq_type,
                stepseq,	
                descript,	
                recipeid,	
                delaytime,
                batch_kind,
                eqpcham,	
                eqpid,	
                chamberid,	
                prevent,	
                type_body,
                type_cham,	
                eventtime,	
            nvl(t10.childeqp, ce.childeqp) as childeqp,
                eqpline
        from t10
        left join (select * from ce where ppid = '-') ce
        on t10.eqpid = ce.eqp),

        er as (SELECT      
            eqp_id,
            batch_kind,
            origin_line_id,      
            eqp_parent_id,
            (case when count(case when tool_kind='CHAMBER' then eqp_parent_id end) over (partition by eqp_parent_id)>=1 then 'CHAM설비' end) as cc
        FROM fab.m_mi_equipment where line_id = 'PFR1')

        select distinct
                processid,                           	
                category,	
                skiprule,
                areaname,	
                eqptype,	
                layerid,	
                lineid,
                stepseq_type,
                stepseq,	
                descript,	
                recipeid,	
                delaytime,
                batch_kind,
                eqpcham,	
                eqpid,	
                chamberid,	
                nvl(t11.prevent, case when er.cc is not null then '미등록' end) as prevent,	
                type_body,
                type_cham,	
                eventtime,	
                (case when instr(childeqp,':')>0 then childeqp else null end) as childeqp,
                eqpline
        from t11
        left join (select distinct eqp_parent_id, cc from er where cc is not null and substr(eqp_parent_id,1,1)<>'P') er
        on t11.eqpid = er.eqp_parent_id
            """

    ############## get data
    with timer("getData: steptip4"):
        df_steptip4 = getData(
                            param = steptip4,
                            # user_name = 'minuk12.choi',
                            convert_type = my_convert_type,
                            verbose = my_verbose
                            )

    with timer("build_b_table_from_a"):
        df_final4 = build_b_table_from_a(
            df_final=df_steptip4,            
            days_threshold=30
        )


    return df_final4



def _parse_args():
    parser = argparse.ArgumentParser(description="FACTS raw 적재 + 필터/요약 사전계산 배치")
    parser.add_argument("--settings", default="config.settings", help="Django settings module (기본: config.settings)")
    parser.add_argument("--snap-date", default="", help="YYYY-MM-DD")
    parser.add_argument("--all-existing", action="store_true", help="전체 existing snap_date 사전계산")
    parser.add_argument("--load-raw", action="store_true", help="(호환) raw 적재 실행 플래그. 기본 실행은 raw 적재 포함")
    parser.add_argument("--skip-raw-load", action="store_true", help="원본(raw) 적재를 건너뛰고 cache만 실행")
    parser.add_argument("--only-raw-load", action="store_true", help="원본(raw) 적재만 실행하고 cache는 건너뜀")
    parser.add_argument("--only-cache", action="store_true", help="cache만 실행(--skip-raw-load와 동일)")
    parser.add_argument("--continue-on-error", action="store_true", help="개별 snap_date 실패 시 다음 날짜 계속")
    parser.add_argument("--force-rebuild", action="store_true", help="해당 snap_date 캐시를 강제 재생성")
    parser.add_argument("--lineid", default="", help="선택적 LINE 필터")
    parser.add_argument("--processid", default="", help="선택적 PRP 필터")
    parser.add_argument("--condition-key", default="", help="선택적 MetricDaily condition_key 필터")
    return parser.parse_args()


def _resolve_target_snap_date(snap_date_raw):
    if snap_date_raw:
        return dt.datetime.strptime(snap_date_raw, "%Y-%m-%d").date()

    from facts.models import FactsWipSource

    latest = (
        FactsWipSource.objects
        .exclude(snap_date__isnull=True)
        .order_by("-snap_date")
        .values_list("snap_date", flat=True)
        .first()
    )

    if latest:
        print(f"[BATCH] default_snap_date_source=facts_wip_source.latest snap_date={latest}")
        return latest

    fallback = dt.date.today()
    print(f"[BATCH] default_snap_date_source=today fallback snap_date={fallback}")
    return fallback


def _run_raw_load(conn):
    _ensure_raw_dependencies()

    print("[RAW] PFR1 facts_wip_source load start")
    df_pfr1 = smicdc_merge()
    append_result = append_df_to_mysql(df_pfr1, conn)
    pfr1_rows = append_result if isinstance(append_result, int) else len(df_pfr1)
    print(f"[RAW] PFR1 facts_wip_source load done rows={pfr1_rows}")

    print("[RAW] facts_eqp_model load start")
    df_eqpmodel = smicdc_merge2()
    append_eqp_result = append_df_to_mysql_eqpmodel(df_eqpmodel, conn)
    eqp_rows = append_eqp_result if isinstance(append_eqp_result, int) else len(df_eqpmodel)
    print(f"[RAW] facts_eqp_model load done rows={eqp_rows}")

    print("[RAW] KFR4 facts_wip_source load start")
    df_kfr4 = smicdc_merge3()
    append_kfr4_result = append_df_to_mysql(df_kfr4, conn)
    kfr4_rows = append_kfr4_result if isinstance(append_kfr4_result, int) else len(df_kfr4)
    print(f"[RAW] KFR4 facts_wip_source load done rows={kfr4_rows}")

    print("[RAW] KFR7 facts_wip_source load start")
    df_kfr7 = smicdc_merge4()
    append_kfr7_result = append_df_to_mysql(df_kfr7, conn)
    kfr7_rows = append_kfr7_result if isinstance(append_kfr7_result, int) else len(df_kfr7)
    print(f"[RAW] KFR7 facts_wip_source load done rows={kfr7_rows}")

    print("[RAW] PFR1_rndplan facts_wip_source load start")
    df_pfr12 = smicdc_merge5()
    append_pfr12_result = append_df_to_mysql(df_pfr12, conn)
    pfr12_rows = append_pfr12_result if isinstance(append_pfr12_result, int) else len(df_pfr12)
    print(f"[RAW] pfr12 facts_wip_source load done rows={pfr12_rows}")


def _resolve_all_snap_dates():
    from django.db.utils import OperationalError, ProgrammingError
    from facts.models import FactsWipSource

    try:
        dates = list(
            FactsWipSource.objects
            .values_list("snap_date", flat=True)
            .distinct()
            .order_by("snap_date")
        )
    except (OperationalError, ProgrammingError):
        return []

    return [d for d in dates if d is not None]


def _run_cache_for_snap_date(
    snap_date,
    index,
    total,
    continue_on_error=False,
    force_rebuild=False,
    lineid="",
    processid="",
    condition_key="",
):
    from django.core.management import call_command
    from django.db.utils import OperationalError, ProgrammingError
    from facts.filter_cache_builder import rebuild_filter_cache
    from facts.models import FactsDashboardMetricDaily, FactsHistorySummaryCache, FactsEditHistory

    try:
        graph_before = FactsDashboardMetricDaily.objects.filter(snap_date=snap_date).count()
    except (OperationalError, ProgrammingError):
        graph_before = 0

    try:
        history_before = FactsHistorySummaryCache.objects.filter(summary_date=snap_date).count()
    except (OperationalError, ProgrammingError):
        history_before = 0

    try:
        source_count = FactsEditHistory.objects.filter(snap_date=snap_date).count()
    except (OperationalError, ProgrammingError):
        source_count = 0

    try:
        print(f"[FILTER] {index}/{total} snap_date={snap_date} start")
        rebuild_filter_cache(snap_date=snap_date, run_post_cache_builders=False)
        print(f"[FILTER] {index}/{total} snap_date={snap_date} done")

        print(f"[METRIC] {index}/{total} snap_date={snap_date} start rows_before={graph_before}")
        call_command(
            "rebuild_facts_dashboard_metric_daily",
            snap_date=str(snap_date),
            force_rebuild=force_rebuild,
            lineid=lineid or "",
            processid=processid or "",
            condition_key=condition_key or "",
        )

        try:
            graph_after = FactsDashboardMetricDaily.objects.filter(snap_date=snap_date).count()
        except (OperationalError, ProgrammingError):
            graph_after = 0

        print(
            f"[METRIC] {index}/{total} snap_date={snap_date} done "
            f"rows_before={graph_before} rows_after={graph_after}"
        )

        print(
            f"[HISTORY] {index}/{total} snap_date={snap_date} start "
            f"rows_before={history_before} source_count={source_count}"
        )
        call_command(
            "rebuild_facts_history_summary_cache",
            snap_date=str(snap_date),
            continue_on_error=continue_on_error,
            lineid=lineid or "",
            processid=processid or "",
            force_rebuild=force_rebuild,
        )

        try:
            history_after = FactsHistorySummaryCache.objects.filter(summary_date=snap_date).count()
        except (OperationalError, ProgrammingError):
            history_after = 0

        print(
            f"[HISTORY] {index}/{total} snap_date={snap_date} done "
            f"rows_before={history_before} rows_after={history_after} source_count={source_count}"
        )

    except Exception as exc:
        print(f"[BATCH] {index}/{total} snap_date={snap_date} failed: {exc}")
        if continue_on_error:
            return
        raise


def main():
    args = _parse_args()

    if args.only_raw_load and args.only_cache:
        raise ValueError("--only-raw-load 와 --only-cache 는 함께 사용할 수 없습니다.")
    if args.only_raw_load and args.skip_raw_load:
        raise ValueError("--only-raw-load 와 --skip-raw-load 는 함께 사용할 수 없습니다.")
    if args.all_existing and args.snap_date:
        raise ValueError("--all-existing 과 --snap-date 는 함께 사용할 수 없습니다.")

    setup_django_for_batch(settings_module=args.settings)

    from django.db.utils import OperationalError, ProgrammingError
    from facts.models import FactsDashboardMetricDaily, FactsHistorySummaryCache

    do_raw = True
    do_cache = True

    if args.only_raw_load:
        do_raw, do_cache = True, False
    elif args.only_cache or args.skip_raw_load:
        do_raw, do_cache = False, True
    elif args.load_raw:
        do_raw, do_cache = True, True

    print(f"[BATCH] do_raw_load={do_raw} do_cache_rebuild={do_cache}")
    print(
        f"[BATCH] lineid={(args.lineid or '').strip() or '*'} "
        f"processid={(args.processid or '').strip() or '*'} "
        f"condition_key={(args.condition_key or '').strip() or '*'}"
    )

    try:
        graph_total_before = FactsDashboardMetricDaily.objects.count()
    except (OperationalError, ProgrammingError):
        graph_total_before = 0

    try:
        history_total_before = FactsHistorySummaryCache.objects.count()
    except (OperationalError, ProgrammingError):
        history_total_before = 0

    if do_raw:
        import pymysql

        conn = pymysql.connect(
            host="12.81.64.130",
            user="minuk12.choi",
            passwd="Test1234!@",
            port=3306,
            db="app_db",
            charset="utf8mb4",
        )
        try:
            with timer("raw_load"):
                _run_raw_load(conn)
        finally:
            conn.close()

    if args.all_existing:
        snap_dates = _resolve_all_snap_dates()
        print("[BATCH] mode=all-existing")
    else:
        single = _resolve_target_snap_date(args.snap_date)
        snap_dates = [single]
        print("[BATCH] mode=single-date")

    print(f"[BATCH] total_snap_dates={len(snap_dates)}")
    print(f"[BATCH] snap_dates={','.join(str(d) for d in snap_dates)}")

    if not args.all_existing and snap_dates:
        print(f"[BATCH] target_snap_date={snap_dates[0]}")

    if not snap_dates:
        print("[BATCH] 대상 snap_date 없음. 안전 종료합니다.")
        return

    if do_cache:
        total = len(snap_dates)
        for idx, snap_date in enumerate(snap_dates, start=1):
            _run_cache_for_snap_date(
                snap_date=snap_date,
                index=idx,
                total=total,
                continue_on_error=args.continue_on_error,
                force_rebuild=args.force_rebuild,
                lineid=(args.lineid or "").strip(),
                processid=(args.processid or "").strip(),
                condition_key=(args.condition_key or "").strip(),
            )

    try:
        graph_total_after = FactsDashboardMetricDaily.objects.count()
    except (OperationalError, ProgrammingError):
        graph_total_after = 0

    try:
        history_total_after = FactsHistorySummaryCache.objects.count()
    except (OperationalError, ProgrammingError):
        history_total_after = 0

    print(
        f"[BATCH] dashboard_metric_daily "
        f"total_rows_before={graph_total_before} total_rows_after={graph_total_after}"
    )
    print(
        f"[BATCH] history_summary_cache "
        f"total_rows_before={history_total_before} total_rows_after={history_total_after}"
    )
    print("[BATCH] 완료")


if __name__ == "__main__":
    main()
