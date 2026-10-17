import os
from datetime import datetime, timedelta, timezone

os.environ["DATABASE_URL"] = "sqlite:///./test.db"

import pytest
from fastapi.testclient import TestClient

from app.database import Base, engine
from app.main import app
from app.ratelimit import AUTH_LIMIT, limiter


@pytest.fixture()
def client():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    limiter.reset()
    return TestClient(app)


def auth_headers(client, email="a@example.com"):
    client.post("/signup", json={"name": "A", "email": email, "password": "secret123"})
    token = client.post("/login", json={"email": email, "password": "secret123"}).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def future(hours=24):
    return (datetime.now(timezone.utc) + timedelta(hours=hours)).isoformat()


def make_class(client, h, slots=2):
    r = client.post("/classes", headers=h, json={
        "name": "Yoga", "dateTime": future(), "instructor": "J", "availableSlots": slots})
    assert r.status_code == 201, r.text
    return r.json()["id"]


def test_signup_duplicate_and_bad_login(client):
    body = {"name": "A", "email": "a@example.com", "password": "secret123"}
    assert client.post("/signup", json=body).status_code == 201
    assert client.post("/signup", json=body).status_code == 409
    assert client.post("/login", json={"email": "a@example.com", "password": "wrong"}).status_code == 401


def test_missing_fields_rejected(client):
    assert client.post("/signup", json={"email": "a@example.com"}).status_code == 422


def test_auth_required(client):
    assert client.post("/classes", json={}).status_code == 401
    assert client.post("/book", json={}).status_code == 401
    assert client.get("/bookings").status_code == 401


def test_list_classes_is_public_and_timezone_converts(client):
    h = auth_headers(client)
    make_class(client, h)
    ist = client.get("/classes").json()[0]["dateTime"]
    assert ist.endswith("+05:30")
    ny = client.get("/classes", params={"tz": "America/New_York"}).json()[0]["dateTime"]
    assert not ny.endswith("+05:30")
    assert client.get("/classes", params={"tz": "Nope/Zone"}).status_code == 400


def test_booking_deducts_and_prevents_overbooking(client):
    h1 = auth_headers(client, "a@example.com")
    h2 = auth_headers(client, "b@example.com")
    h3 = auth_headers(client, "c@example.com")
    cid = make_class(client, h1, slots=2)
    payload = {"class_id": cid, "client_name": "X", "client_email": "x@example.com"}
    assert client.post("/book", headers=h1, json=payload).status_code == 201
    assert client.get("/classes").json()[0]["availableSlots"] == 1
    assert client.post("/book", headers=h1, json=payload).status_code == 409  # duplicate
    assert client.post("/book", headers=h2, json=payload).status_code == 201
    assert client.post("/book", headers=h3, json=payload).status_code == 409  # full
    assert client.get("/classes").json()[0]["availableSlots"] == 0


def test_bookings_only_own(client):
    h1 = auth_headers(client, "a@example.com")
    h2 = auth_headers(client, "b@example.com")
    cid = make_class(client, h1)
    client.post("/book", headers=h1, json={"class_id": cid, "client_name": "X", "client_email": "x@example.com"})
    assert len(client.get("/bookings", headers=h1).json()) == 1
    assert client.get("/bookings", headers=h2).json() == []


def test_book_unknown_class(client):
    h = auth_headers(client)
    r = client.post("/book", headers=h, json={"class_id": 999, "client_name": "X", "client_email": "x@example.com"})
    assert r.status_code == 404


def test_refresh(client):
    client.post("/signup", json={"name": "A", "email": "a@example.com", "password": "secret123"})
    tokens = client.post("/login", json={"email": "a@example.com", "password": "secret123"}).json()
    assert client.post("/refresh", json={"refresh_token": tokens["refresh_token"]}).status_code == 200
    assert client.post("/refresh", json={"refresh_token": tokens["access_token"]}).status_code == 401


def test_blank_names_rejected(client):
    assert client.post("/signup", json={"name": "   ", "email": "a@example.com", "password": "secret123"}).status_code == 422


def test_past_class_rejected(client):
    h = auth_headers(client)
    r = client.post("/classes", headers=h, json={
        "name": "Old", "dateTime": "2020-01-01T10:00:00Z", "instructor": "J", "availableSlots": 5})
    assert r.status_code == 422


def test_invalid_and_malformed_tokens(client):
    assert client.get("/bookings", headers={"Authorization": "Bearer garbage"}).status_code == 401
    assert client.get("/bookings", headers={"Authorization": "Basic abc"}).status_code == 401


def test_negative_slots_rejected(client):
    h = auth_headers(client)
    r = client.post("/classes", headers=h, json={
        "name": "Y", "dateTime": future(), "instructor": "J", "availableSlots": -1})
    assert r.status_code == 422


def test_login_rate_limited(client):
    body = {"email": "a@example.com", "password": "wrong-pass"}
    codes = [client.post("/login", json=body).status_code for _ in range(AUTH_LIMIT + 1)]
    assert codes[:AUTH_LIMIT] == [401] * AUTH_LIMIT
    assert codes[-1] == 429
    r = client.post("/login", json=body)
    assert r.status_code == 429 and int(r.headers["Retry-After"]) >= 1
    assert client.get("/classes").status_code == 200  # general bucket unaffected


def test_class_pagination_and_filters(client):
    h = auth_headers(client)
    for i, (n, ins, hrs) in enumerate([("Yoga", "John Doe", 24), ("HIIT", "Jane Smith", 48),
                                       ("Yoga Flow", "John Doe", 72), ("Zumba", "100%_Pro", 96)]):
        r = client.post("/classes", headers=h, json={
            "name": n, "dateTime": future(hrs), "instructor": ins, "availableSlots": 5})
        assert r.status_code == 201

    r = client.get("/classes", params={"limit": 2})
    assert [c["name"] for c in r.json()] == ["Yoga", "HIIT"]
    assert r.headers["X-Total-Count"] == "4"
    r = client.get("/classes", params={"limit": 2, "offset": 2})
    assert [c["name"] for c in r.json()] == ["Yoga Flow", "Zumba"]
    assert client.get("/classes", params={"offset": 10}).json() == []

    r = client.get("/classes", params={"instructor": "john"})
    assert len(r.json()) == 2 and r.headers["X-Total-Count"] == "2"
    assert len(client.get("/classes", params={"name": "yoga"}).json()) == 2
    assert len(client.get("/classes", params={"instructor": "%"}).json()) == 1  # literal match
    assert client.get("/classes", params={"name": "nothing"}).json() == []

    lo = (datetime.now(timezone.utc) + timedelta(hours=40)).isoformat()
    hi = (datetime.now(timezone.utc) + timedelta(hours=80)).isoformat()
    r = client.get("/classes", params={"from": lo, "to": hi})
    assert [c["name"] for c in r.json()] == ["HIIT", "Yoga Flow"]
    assert client.get("/classes", params={"from": hi, "to": lo}).status_code == 422


def test_pagination_validation(client):
    assert client.get("/classes", params={"limit": 0}).status_code == 422
    assert client.get("/classes", params={"limit": 101}).status_code == 422
    assert client.get("/classes", params={"offset": -1}).status_code == 422
