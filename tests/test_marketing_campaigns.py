import asyncio

from app.core import dates
from app.core.security import access_token
from app.models import User


async def create_lead(api, number=1, branch=0):
    response = await api.client.post(
        "/api/v1/leads",
        headers=api.headers["supervisor"],
        json={
            "branch_id": str(api.branches[branch].id),
            "city_id": str(api.city.id),
            "first_name": "Sara",
            "last_name": "Razi",
            "mobile": f"091233340{number:02}",
            "address": "Test address",
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


async def create_campaign(api, leads, *, include_customers=False, activate=False):
    headers = api.headers["supervisor"]
    response = await api.client.post(
        "/api/v1/campaigns",
        headers=headers,
        json={
            "title": "Branch marketing",
            "start_date": "1405/08/20",
            "end_date": "1405/09/20",
            "include_customers": include_customers,
        },
    )
    assert response.status_code == 201, response.text
    url = "/api/v1/campaigns/" + response.json()["id"]
    selected = await api.client.post(
        url + "/selection", headers=headers, json={"lead_ids": [item["id"] for item in leads]}
    )
    assert selected.status_code == 200, selected.text
    if activate:
        response = await api.client.post(url + "/activate", headers=headers)
        assert response.status_code == 200, response.text
    return url


async def work_urls(api, campaign, role="employee"):
    result = await api.client.get(campaign + "/leads", headers=api.headers[role])
    assert result.status_code == 200, result.text
    return [campaign + "/leads/" + row["id"] for row in result.json()["items"]]


async def make_employee(api, key="second"):
    async with api.database.sessions.begin() as session:
        employee = User(
            first_name="Another",
            last_name="Employee",
            mobile="09120009988",
            password_hash=api.users["employee"].password_hash,
            role="employee",
            branch_id=api.branches[0].id,
            must_change_password=False,
        )
        session.add(employee)
    api.headers[key] = {"Authorization": "Bearer " + access_token(api.settings, employee)}
    return employee


async def add_attempt(api, url, employee="employee", **payload):
    payload = {"visit_date": dates.format_date(dates.today()), "result": "interested"} | payload
    return await api.client.post(url + "/visits", headers=api.headers[employee], json=payload)


async def test_campaign_reservation_survives_completion_until_close(api):
    client, headers = api.client, api.headers
    lead = await create_lead(api)
    one = await create_campaign(api, [lead], activate=True)
    two = await create_campaign(api, [lead])
    preview = await client.get(
        two + "/selection/preview", headers=headers["supervisor"], params={"q": "sara razi"}
    )
    assert preview.json()["total"] == 1
    selection = await client.post(
        two + "/selection", headers=headers["supervisor"], json={"filters": {"q": "sara"}}
    )
    assert selection.json() == {"added": 0, "removed": 0}
    (work,) = await work_urls(api, one)
    assert (await client.post(work + "/pick", headers=headers["employee"])).status_code == 200
    assert (await add_attempt(api, work)).status_code == 201
    assert (await client.post(work + "/complete", headers=headers["employee"])).status_code == 200
    failed = await client.post(two + "/activate", headers=headers["supervisor"])
    assert failed.status_code == 409
    assert failed.json()["error"]["details"]["lead_ids"] == [lead["id"]]
    assert (await client.get(two, headers=headers["supervisor"])).json()["status"] == "draft"
    assert (await client.post(one + "/close", headers=headers["supervisor"])).status_code == 200
    assert (await client.post(two + "/activate", headers=headers["supervisor"])).status_code == 200


async def test_campaign_pick_quota_isolation_and_reassign(api):
    client, headers = api.client, api.headers
    second = await make_employee(api)
    campaign = await create_campaign(
        api, [await create_lead(api, i) for i in (1, 2)], activate=True
    )
    one, two = await work_urls(api, campaign)
    responses = await asyncio.gather(
        client.post(one + "/pick", headers=headers["employee"]),
        client.post(two + "/pick", headers=headers["employee"]),
    )
    assert sorted(response.status_code for response in responses) == [200, 409]
    assert (
        next(r for r in responses if r.status_code == 409).json()["error"]["code"]
        == "quota_reached"
    )
    picked, unpicked = (one, two) if responses[0].status_code == 200 else (two, one)
    assert (await client.post(unpicked + "/pick", headers=headers["other"])).status_code == 404
    assert await work_urls(api, campaign, "second") == [unpicked]
    assert (await client.post(unpicked + "/pick", headers=headers["second"])).status_code == 200
    caps = f"{campaign}/branches/{api.branches[0].id}/capacity"
    assert (await client.get(caps, headers=headers["employee"])).json()["items"][0][
        "picked_count"
    ] == 1
    moved = await client.post(
        picked + "/reassign", headers=headers["manager"], json={"employee_id": str(second.id)}
    )
    assert moved.status_code == 200, moved.text
    assert await work_urls(api, campaign) == []
    assert (await client.get(caps, headers=headers["second"])).json()["items"][0][
        "picked_count"
    ] == 2
    override = await client.patch(
        caps + f"/{second.id}",
        headers=headers["manager"],
        json={"quota": 5, "reason": "Shared workload"},
    )
    assert override.json()["quota"] == 5


async def test_pick_race_and_zero_staff(api):
    client, headers = api.client, api.headers
    await make_employee(api)
    async with api.database.sessions.begin() as session:
        (await session.get(User, api.users["other"].id)).is_active = False
    campaign = await create_campaign(api, [await create_lead(api), await create_lead(api, 2, 1)])
    activation = await client.post(campaign + "/activate", headers=headers["supervisor"])
    assert activation.json()["branches_without_staff"] == [str(api.branches[1].id)]
    (item,) = await work_urls(api, campaign)
    picks = await asyncio.gather(
        *(client.post(item + "/pick", headers=headers[key]) for key in ("employee", "second"))
    )
    assert sorted(r.status_code for r in picks) == [200, 409]
    assert (
        next(r for r in picks if r.status_code == 409).json()["error"]["code"] == "lead_unavailable"
    )


async def test_repeat_visit_history_keeps_original_author(api):
    client, headers = api.client, api.headers
    second = await make_employee(api)
    campaign = await create_campaign(api, [await create_lead(api)], activate=True)
    (item,) = await work_urls(api, campaign)
    assert (await client.post(item + "/pick", headers=headers["employee"])).status_code == 200
    first = await add_attempt(api, item, description="Original")
    assert first.status_code == 201, first.text
    api.clock.advance(minutes=1)
    await client.post(
        item + "/reassign", headers=headers["manager"], json={"employee_id": str(second.id)}
    )
    assert (await add_attempt(api, item)).status_code == 404
    second_attempt = await add_attempt(api, item, "second", result="no_response")
    assert second_attempt.status_code == 201, second_attempt.text
    assert first.json()["id"] == second_attempt.json()["id"]
    assert first.json()["created_at"] == second_attempt.json()["created_at"]
    history = (await client.get(item + "/visits", headers=headers["second"])).json()
    assert history["visit"]["result"] == "no_response"
    attempts = history["attempts"]["items"]
    assert [row["employee_id"] for row in attempts] == [
        str(api.users["employee"].id),
        str(second.id),
    ]
    assert attempts[0]["description"] == "Original"
    await client.post(item + "/complete", headers=headers["second"])
    assert (await add_attempt(api, item, "second")).status_code == 409
