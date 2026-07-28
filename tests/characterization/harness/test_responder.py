from harness.responder import Responder


def test_login_returns_access_token():
    r = Responder()
    st, body = r.respond("POST", "/auth/login", b"{}")
    assert st == 200
    assert body["data"]["access_token"] == "FAKE_DEMO_TOKEN"


def test_single_resource_get_is_existence_404():
    r = Responder()
    assert r.respond("GET", "/fields/os_tasks/workspace", None)[0] == 404
    assert r.respond("GET", "/relations/os_tasks/sprint", None)[0] == 404
    assert r.respond("GET", "/users/abc-123", None)[0] == 404


def test_list_get_returns_empty_data():
    r = Responder()
    assert r.respond("GET", "/items/os_tasks?limit=1", None) == (200, {"data": []})
    assert r.respond("GET", "/users?filter[email][_in]=a,b", None) == (200, {"data": []})


def test_create_ids_are_deterministic_and_echo_payload():
    r = Responder()
    st, body = r.respond("POST", "/items/os_tasks", b'{"x":1}')
    assert st == 200
    assert body["data"]["id"] == "SEED-0001"
    assert body["data"]["x"] == 1
    assert r.respond("POST", "/items/os_tasks", b'{"x":2}')[1]["data"]["id"] == "SEED-0002"


def test_patch_delete_graphql():
    r = Responder()
    assert r.respond("PATCH", "/items/os_tasks/SEED-0001", b'{"a":1}')[0] == 200
    assert r.respond("DELETE", "/items/os_tasks/SEED-0001", None) == (204, None)
    st, body = r.respond("POST", "/graphql", b'{"query":"{ x }"}')
    assert st == 200 and "errors" not in body  # no errors -> retry loops exit


def test_override_wins_over_default():
    r = Responder(
        overrides=[
            (
                lambda m, p, _b: p.startswith("/items/organizations"),
                (200, {"data": [{"id": 1, "name": "Demo Co"}]}),
            )
        ]
    )
    st, body = r.respond("GET", "/items/organizations?x=1", None)
    assert st == 200 and body["data"][0]["id"] == 1
