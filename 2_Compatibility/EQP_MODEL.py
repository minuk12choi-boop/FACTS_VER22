from bigdataquery import *
import bigdataquery as bdq
import pandas as pd
import pymysql
from datetime import datetime
from my_def_prp import *


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
                        AND NVL(eqp_model, '-') <> '-')

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
        

#     file_path = "check_result.xlsx"
#     safe_path = get_unique_filename(file_path)

#     t_excel_start = time.perf_counter()

#     # 데이터프레임 저장
#     df_final.to_excel(
#         safe_path, 
#         index=False, 
#         engine="openpyxl")
    
#     t_excel_end = time.perf_counter()
    
#     print(f"파일이 저장되었습니다: {safe_path}")
#     print(f"파일이 저장시간: {t_excel_end-t_excel_start:.2f} sec")

    return df_equipment

conn = pymysql.connect(
    host = '12.81.64.130',
    user = 'minuk12.choi',
    passwd = 'Test1234!@',
    port = 3306,
    db = 'app_db',
    charset = 'utf8mb4'
    )


append_df_to_mysql_eqpmodel(smicdc_merge2(), conn)

conn.close()
