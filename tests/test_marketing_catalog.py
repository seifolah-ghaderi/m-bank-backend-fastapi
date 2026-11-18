async def test_catalog_scope_and_normalization(api):
    client = api.client
    supervisor = api.headers["supervisor"]
    employee = api.headers["employee"]
    url = "/api/v1/occupations"
    assert (await client.post(url, headers=employee, json={"name": "Clerk"})).status_code == 403
    first = await client.post(url, headers=supervisor, json={"name": " كاتب  ۲ "})
    assert first.status_code == 201, first.text
    assert first.json()["name"] == "کاتب 2"
    assert (await client.post(url, headers=supervisor, json={"name": "کاتب 2"})).status_code == 409
    changed = await client.patch(
        url + "/" + first.json()["id"], headers=supervisor, json={"is_active": False}
    )
    assert changed.status_code == 200
    assert (await client.get(url, headers=employee, params={"include_inactive": True})).json()[
        "total"
    ] == 0
    assert (await client.get(url, headers=supervisor, params={"include_inactive": True})).json()[
        "total"
    ] >= 1


async def test_product_validation(api):
    client = api.client
    headers = api.headers["supervisor"]
    url = "/api/v1/banking-products"
    product = {"name": "Deposit", "code": " d-۰۱ ", "score_value": -1}
    assert (await client.post(url, headers=headers, json=product)).status_code == 422
    product["score_value"] = 0
    created = await client.post(url, headers=headers, json=product)
    assert created.status_code == 201, created.text
    assert created.json()["code"] == "D-01"
    assert (await client.post(url, headers=headers, json=product)).status_code == 409
