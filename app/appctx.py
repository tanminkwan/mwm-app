"""스케줄러 작업을 앱 컨텍스트 안에서 돌린다.

Flask-SQLAlchemy 3 부터 `db.session` 은 앱 컨텍스트가 있어야 쓸 수 있다. APScheduler 는 작업을
자기 스레드에서 돌리므로 컨텍스트가 없다. 작업은 SQLAlchemyJobStore 에 "모듈:함수" 이름으로
저장되므로, 호출하는 쪽이 아니라 **함수 정의에** 이 데코레이터를 붙인다.
"""
import functools

from flask import has_app_context


def with_app_context(func):
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        if has_app_context():
            return func(*args, **kwargs)
        from app import app
        with app.app_context():
            return func(*args, **kwargs)
    return wrapper
