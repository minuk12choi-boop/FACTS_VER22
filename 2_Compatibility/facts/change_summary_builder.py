from collections import defaultdict

def rebuild_change_summary(conn, snap_date):
    snap_date = str(snap_date)
    with conn.cursor() as cursor:
        cursor.execute("DELETE FROM facts_change_summary WHERE snap_date = %s", (snap_date,))
        cursor.execute(
            '''
            SELECT IFNULL(processid,''), IFNULL(lineid,''), IFNULL(action_type,''), COUNT(*)
            FROM facts_edit_history
            WHERE DATE(created_at) = %s
            GROUP BY IFNULL(processid,''), IFNULL(lineid,''), IFNULL(action_type,'')
            ''',
            (snap_date,),
        )
        rows = cursor.fetchall()

        grouped = defaultdict(lambda: {"step": 0, "web": 0, "calc": 0})
        for processid, lineid, action_type, cnt in rows:
            key = (processid or "", lineid or "")
            if action_type in ("plan_add","plan_update","plan_delete","tip_missing_add","tip_missing_update","tip_missing_delete","override","prevent_rule_add","prevent_rule_update","prevent_rule_delete"):
                grouped[key]["web"] += int(cnt)
            elif str(action_type).endswith("_add") or str(action_type).endswith("_delete"):
                grouped[key]["step"] += int(cnt)
            else:
                grouped[key]["calc"] += int(cnt)

        for (processid, lineid), vals in grouped.items():
            total = vals["step"] + vals["web"] + vals["calc"]
            parts = []
            if vals["step"]:
                parts.append(f"STEP {vals['step']}건")
            if vals["web"]:
                parts.append(f"WEB {vals['web']}건")
            if vals["calc"]:
                parts.append(f"CALC {vals['calc']}건")
            cursor.execute(
                '''
                INSERT INTO facts_change_summary
                (snap_date, processid, lineid, areaname, layerid, step_change_cnt, web_change_cnt, calc_change_cnt, total_change_cnt, summary_text)
                VALUES (%s,%s,%s,'','',%s,%s,%s,%s,%s)
                ''',
                (snap_date, processid, lineid, vals["step"], vals["web"], vals["calc"], total, "\n".join(parts)),
            )
    conn.commit()
