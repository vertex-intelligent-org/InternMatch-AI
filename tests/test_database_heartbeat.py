import logging

from app.core.config import settings

HEARTBEAT_SECRET = (
    "test-heartbeat-secret-"
    "0123456789abcdef0123456789abcdef"
)


class FakeCursor:
    def __init__(self, executed):
        self.executed = executed

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def execute(self, statement):
        self.executed.append(statement)

    def fetchone(self):
        return (1,)


class FakeConnection:
    def __init__(self, executed):
        self.executed = executed
        self.autocommit = False
        self.closed = False

    def cursor(self):
        return FakeCursor(self.executed)

    def close(self):
        self.closed = True


def test_heartbeat_rejects_missing_secret(client, monkeypatch):
    monkeypatch.setattr(
        settings,
        "HEARTBEAT_SECRET",
        "",
    )

    response = client.post(
        "/api/v1/internal/database-heartbeat",
        headers={
            "X-Heartbeat-Secret": HEARTBEAT_SECRET,
        },
    )

    assert response.status_code == 503
    assert response.json()["status"] == "unavailable"
    assert response.headers["cache-control"] == "no-store"


def test_heartbeat_rejects_wrong_secret(client, monkeypatch):
    monkeypatch.setattr(
        settings,
        "HEARTBEAT_SECRET",
        HEARTBEAT_SECRET,
    )

    response = client.post(
        "/api/v1/internal/database-heartbeat",
        headers={
            "X-Heartbeat-Secret": "wrong-secret",
        },
    )

    assert response.status_code == 401
    assert response.json()["status"] == "unauthorized"
    assert response.headers["cache-control"] == "no-store"


def test_heartbeat_executes_exactly_select_one(
    client,
    monkeypatch,
):
    monkeypatch.setattr(
        settings,
        "HEARTBEAT_SECRET",
        HEARTBEAT_SECRET,
    )

    executed = []
    connection = FakeConnection(executed)

    captured = {}

    def fake_connect(url, **kwargs):
        captured["url"] = url
        captured["kwargs"] = kwargs
        return connection

    monkeypatch.setattr(
        "app.api.internal.psycopg2.connect",
        fake_connect,
    )

    response = client.post(
        "/api/v1/internal/database-heartbeat",
        headers={
            "X-Heartbeat-Secret": HEARTBEAT_SECRET,
        },
    )

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "database": "connected",
    }

    assert executed == ["SELECT 1"]
    assert captured["kwargs"]["connect_timeout"] == 5
    assert (
        captured["kwargs"]["options"]
        == "-c statement_timeout=5000"
    )
    assert connection.closed is True
    assert response.headers["cache-control"] == "no-store"


def test_heartbeat_returns_503_on_database_failure(
    client,
    monkeypatch,
):
    monkeypatch.setattr(
        settings,
        "HEARTBEAT_SECRET",
        HEARTBEAT_SECRET,
    )

    def failing_connect(*args, **kwargs):
        raise RuntimeError(
            "database connection failed"
        )

    monkeypatch.setattr(
        "app.api.internal.psycopg2.connect",
        failing_connect,
    )

    response = client.post(
        "/api/v1/internal/database-heartbeat",
        headers={
            "X-Heartbeat-Secret": HEARTBEAT_SECRET,
        },
    )

    assert response.status_code == 503
    assert response.json() == {
        "status": "unavailable",
        "database": "unavailable",
    }
    assert response.headers["cache-control"] == "no-store"


def test_heartbeat_failure_does_not_log_secret(
    client,
    monkeypatch,
    caplog,
):
    monkeypatch.setattr(
        settings,
        "HEARTBEAT_SECRET",
        HEARTBEAT_SECRET,
    )

    def failing_connect(*args, **kwargs):
        raise RuntimeError(
            "simulated database failure"
        )

    monkeypatch.setattr(
        "app.api.internal.psycopg2.connect",
        failing_connect,
    )

    with caplog.at_level(
        logging.WARNING,
        logger="internmatch_backend",
    ):
        response = client.post(
            "/api/v1/internal/database-heartbeat",
            headers={
                "X-Heartbeat-Secret": HEARTBEAT_SECRET,
            },
        )

    assert response.status_code == 503
    assert HEARTBEAT_SECRET not in caplog.text
