"""로그인 연속 실패 잠금 (brute force 방어). 기본 5회 실패 → 15분 잠금."""
from datetime import timedelta

from app.models import IdpUser, _utcnow

GOOD = "TestPass123!"


def _post(client, password):
    return client.post("/login", data={"username": "testuser", "password": password})


def _user(db):
    return db.session.query(IdpUser).filter_by(username="testuser").one()


def test_locks_after_max_failures_even_with_the_right_password(client, db, sample_user):
    for _ in range(5):
        assert _post(client, "wrong").status_code == 200
    assert _user(db).locked_until > _utcnow()
    resp = _post(client, GOOD)
    assert resp.status_code == 200  # 로그인 안 됨 (redirect 아님)
    assert b"Invalid username or password" in resp.data


def test_fewer_failures_do_not_lock(client, db, sample_user):
    for _ in range(4):
        _post(client, "wrong")
    assert _user(db).locked_until is None
    assert _post(client, GOOD).status_code == 302


def test_success_resets_the_counter(client, db, sample_user):
    for _ in range(4):
        _post(client, "wrong")
    _post(client, GOOD)
    assert _user(db).failed_login_count == 0


def test_lock_expires(client, db, sample_user):
    u = _user(db)
    u.locked_until = _utcnow() - timedelta(seconds=1)
    db.session.commit()
    assert _post(client, GOOD).status_code == 302
    assert _user(db).locked_until is None


def test_attempts_while_locked_do_not_extend_the_lock(client, db, sample_user):
    for _ in range(5):
        _post(client, "wrong")
    until = _user(db).locked_until
    _post(client, "wrong")
    assert _user(db).locked_until == until


def test_limit_and_minutes_come_from_config(app, client, db, sample_user):
    app.config.update(LOGIN_MAX_ATTEMPTS=2, LOGIN_LOCK_MINUTES=1)
    try:
        _post(client, "wrong")
        _post(client, "wrong")
        remaining = _user(db).locked_until - _utcnow()
        assert timedelta(seconds=30) < remaining <= timedelta(minutes=1)
    finally:
        app.config.update(LOGIN_MAX_ATTEMPTS=5, LOGIN_LOCK_MINUTES=15)


def test_zero_turns_the_lock_off(app, client, db, sample_user):
    app.config.update(LOGIN_MAX_ATTEMPTS=0)
    try:
        for _ in range(10):
            _post(client, "wrong")
        assert _user(db).locked_until is None
        assert _post(client, GOOD).status_code == 302
    finally:
        app.config.update(LOGIN_MAX_ATTEMPTS=5)


def test_unknown_user_is_not_counted_or_revealed(client, db, sample_user):
    resp = client.post("/login", data={"username": "nobody", "password": "x"})
    assert resp.status_code == 200
    assert b"Invalid username or password" in resp.data
