"""Profile POS on an explicitly isolated, migrated crm_pos_scale_test database.

Set TEST_DATABASE_URL; run with --seed for reproducible synthetic scale data.
This command never truncates or deletes records and refuses other database names.
"""

import argparse
import asyncio
import json
import logging
import math
import os
import time
from io import BytesIO
from pathlib import Path
from urllib.parse import urlsplit

import jdatetime
from httpx import ASGITransport, AsyncClient
from openpyxl import load_workbook
from sqlalchemy import select, text
from sqlalchemy.dialects import postgresql

from app.core import dates
from app.core.config import Settings
from app.core.db import Database
from app.core.excel import workbook_bytes
from app.core.security import access_token
from app.features.pos.productivity import productivity_query
from app.main import create_app
from app.models import User


async def seed(database):
    async with database.engine.begin() as c:
        await c.execute(
            text("""INSERT INTO cities (id,name) VALUES
            (md5('pos-scale-city')::uuid,'Synthetic Scale City') ON CONFLICT DO NOTHING""")
        )
        await c.execute(
            text("""INSERT INTO branches (id,city_id,code,name)
            SELECT md5('pos-scale-branch-'||i)::uuid,md5('pos-scale-city')::uuid,
                'SCALE-'||lpad(i::text,3,'0'),'Synthetic Branch '||i
            FROM generate_series(0,49) i ON CONFLICT DO NOTHING""")
        )
        await c.execute(
            text("""INSERT INTO users
            (id,first_name,last_name,mobile,password_hash,role,must_change_password)
            VALUES (md5('pos-scale-supervisor')::uuid,'Synthetic','Supervisor','09140000000',
                'unusable-synthetic-hash','supervisor',false) ON CONFLICT DO NOTHING""")
        )
        for role, prefix in [("branch_manager", "09120000"), ("employee", "09130000")]:
            await c.execute(
                text("""INSERT INTO users
                (id,branch_id,first_name,last_name,mobile,password_hash,role,must_change_password)
                SELECT md5(:role||'-pos-scale-'||i)::uuid,md5('pos-scale-branch-'||i)::uuid,
                'Synthetic','Staff '||i,:prefix||lpad(i::text,3,'0'),
                'unusable-synthetic-hash',:role,false
                FROM generate_series(0,49) i ON CONFLICT DO NOTHING"""),
                {"role": role, "prefix": prefix},
            )
        await c.execute(
            text("""INSERT INTO pos_devices
            (id,device_number,owner_name,address,branch_id,source)
            SELECT md5('pos-scale-device-'||i)::uuid,'SCALE-'||lpad(i::text,6,'0'),
                'Synthetic Owner','Synthetic scale address',
                md5('pos-scale-branch-'||(i%50))::uuid,'manual'
            FROM generate_series(1,50000) i ON CONFLICT DO NOTHING""")
        )
    current = jdatetime.date.fromgregorian(date=dates.today())
    last = current.year * 12 + current.month - 2
    for offset in range(40):
        index = last - offset
        start, end = dates.month_bounds(index // 12, index % 12 + 1)
        async with database.engine.begin() as c:
            count = await c.scalar(
                text("SELECT count(*) FROM pos_monthly_transactions WHERE from_date=:start"),
                {"start": start},
            )
            if count == 50000:
                continue
            if count:
                raise RuntimeError("Unexpected partial scale period; inspect the isolated database")
            await c.execute(
                text("""INSERT INTO pos_monthly_transactions
                (id,pos_device_id,from_date,to_date,transaction_amount,transaction_count,source)
                SELECT md5('pos-scale-tx-'||:period||'-'||i)::uuid,
                    md5('pos-scale-device-'||i)::uuid,
                    :start,:end,((i%15)*100000000)+10000000,(i%1000),'manual'
                FROM generate_series(1,50000) i"""),
                {"period": str(index), "start": start, "end": end},
            )
        if offset % 5 == 0:
            print(f"Seeded {offset + 1}/40 periods", flush=True)
    start, end = dates.month_bounds(last // 12, last % 12 + 1)
    async with database.engine.begin() as c:
        await c.execute(
            text("""INSERT INTO pos_visits
            (id,pos_device_id,branch_id,selected_by,selected_at,status,
             assigned_to,assigned_by,assigned_at,result,visited_at,completed_at,
             cancelled_at,cancelled_by,cancel_reason,due_date,
             snapshot_from_date,snapshot_to_date,snapshot_amount,snapshot_count,snapshot_no_data,
             snapshot_performance,snapshot_lower_threshold,snapshot_upper_threshold,
             snapshot_policy_version,snapshot_unit,snapshot_method)
            SELECT md5('pos-scale-visit-'||i)::uuid,md5('pos-scale-device-'||i)::uuid,
                md5('pos-scale-branch-'||(i%50))::uuid,md5('pos-scale-supervisor')::uuid,now(),
                CASE i%4 WHEN 0 THEN 'pending_assignment' WHEN 1 THEN 'assigned'
                    WHEN 2 THEN 'completed' ELSE 'cancelled' END,
                CASE WHEN i%4 IN (1,2) THEN md5('employee-pos-scale-'||(i%50))::uuid END,
                CASE WHEN i%4 IN (1,2) THEN md5('branch_manager-pos-scale-'||(i%50))::uuid END,
                CASE WHEN i%4 IN (1,2) THEN now() END,
                CASE WHEN i%4=2 THEN 'visited' END,
                CASE WHEN i%4=2 THEN now() END,CASE WHEN i%4=2 THEN now() END,
                CASE WHEN i%4=3 THEN now() END,
                CASE WHEN i%4=3 THEN md5('pos-scale-supervisor')::uuid END,
                CASE WHEN i%4=3 THEN 'Synthetic scale cancellation' END,current_date-1,
                :start,:end,100000000,10,false,'low',200000000,1000000000,1,'rials','period_total_amount'
            FROM generate_series(1,50000) i ON CONFLICT DO NOTHING"""),
            {"start": start, "end": end},
        )
    async with database.engine.connect() as c:
        c = await c.execution_options(isolation_level="AUTOCOMMIT")
        await c.execute(text("VACUUM ANALYZE pos_monthly_transactions"))
        await c.execute(text("VACUUM ANALYZE pos_devices"))
        await c.execute(text("VACUUM ANALYZE pos_visits"))


async def main(args):
    url = os.environ["TEST_DATABASE_URL"]
    if urlsplit(url).path != "/crm_pos_scale_test":
        raise SystemExit("Refusing any database except crm_pos_scale_test")
    database = Database(url)
    settings = Settings(
        _env_file=None,
        database_url=url,
        jwt_secret="profile-test-jwt-" * 4,
        csrf_secret="profile-test-csrf-" * 4,
        sms_digest_secret="profile-test-sms-" * 4,
        import_storage_dir=Path("/tmp/crm-pos-scale-imports"),
    )
    try:
        if args.seed:
            await seed(database)
        async with database.sessions() as session:
            actors = {
                role: await session.scalar(
                    select(User).where(User.role == role).order_by(User.mobile).limit(1)
                )
                for role in ("supervisor", "branch_manager", "employee")
            }
            counts = dict(
                (
                    await session.execute(
                        text("""SELECT 'terminals',count(*) FROM pos_devices
                UNION ALL SELECT 'summaries',count(*) FROM pos_monthly_transactions
                UNION ALL SELECT 'visits',count(*) FROM pos_visits""")
                    )
                ).all()
            )
        assert counts == {"terminals": 50000, "summaries": 2000000, "visits": 50000}, counts
        app = create_app(settings)
        await app.state.database.close()
        app.state.database = database
        logging.getLogger("crm.requests").setLevel(logging.ERROR)
        measurements = {}
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            for role in ("supervisor", "branch_manager", "employee"):
                headers = {"Authorization": "Bearer " + access_token(settings, actors[role])}
                endpoints = ["/api/v1/pos/reports/summary"]
                if role != "employee":
                    endpoints.insert(0, "/api/v1/pos/productivity")
                    endpoints.insert(1, "/api/v1/pos/productivity?performance=low")
                for endpoint in endpoints:
                    times = []
                    for i in range(args.runs + 2):
                        t = time.perf_counter()
                        response = await client.get(endpoint, headers=headers)
                        elapsed = (time.perf_counter() - t) * 1000
                        assert response.status_code == 200, response.text
                        if i >= 2:
                            times.append(elapsed)
                    measurements[role + " " + endpoint] = {
                        "p95_ms": round(sorted(times)[math.ceil(0.95 * len(times)) - 1], 2),
                        "min_ms": round(min(times), 2),
                        "runs": len(times),
                    }
                    print(role, endpoint, measurements[role + " " + endpoint], flush=True)
            headers = {"Authorization": "Bearer " + access_token(settings, actors["supervisor"])}
            content = workbook_bytes(
                ["device_number", "branch_code", "owner_name", "address"],
                [
                    [f"SCALE-{i:06}", f"SCALE-{i % 50:03}", "Synthetic Owner", "Synthetic address"]
                    for i in range(1, 5001)
                ],
            )
            t = time.perf_counter()
            response = await client.post(
                "/api/v1/pos/imports/devices",
                headers=headers,
                files={"file": ("synthetic.xlsx", content)},
            )
            assert response.status_code == 200 and response.json()["skipped"] == 5000, response.text
            measurements["5000_row_registry_import_ms"] = round((time.perf_counter() - t) * 1000, 2)
            t = time.perf_counter()
            response = await client.get("/api/v1/pos/devices/export", headers=headers)
            assert response.status_code == 200
            measurements["50000_row_export_ms"] = round((time.perf_counter() - t) * 1000, 2)
            workbook = load_workbook(BytesIO(response.content), read_only=True)
            assert sum(1 for _ in workbook.active.rows) == 50001
            workbook.close()
        start, end = dates.period_range()
        query = productivity_query(actors["supervisor"], start, end).subquery()
        statement = (
            select(query)
            .order_by(
                query.c.transaction_amount.asc().nulls_last(),
                query.c.device_number,
                query.c.pos_device_id,
            )
            .limit(20)
        )
        sql = str(
            statement.compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True})
        )
        async with database.engine.connect() as c:
            plan = await c.scalar(text("EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) " + sql))
        if isinstance(plan, str):
            plan = json.loads(plan)
        output = {"counts": counts, "measurements": measurements, "ranking_plan": plan}
        Path(args.output).write_text(json.dumps(output, indent=2, default=str) + "\n")
        print("Wrote", args.output, flush=True)
    finally:
        await database.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed", action="store_true")
    parser.add_argument("--runs", type=int, default=12)
    parser.add_argument("--output", default="/tmp/pos-profile.json")
    asyncio.run(main(parser.parse_args()))
