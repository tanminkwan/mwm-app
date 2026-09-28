import os
from datetime import datetime
from app import create_app

app = create_app()

def init_idp(app):
    with app.app_context():
        # Initial user sync
        try:
            from app.repositories.user_repo import UserRepository
            from app.services.sync_service import SyncService
            user_repo = UserRepository()
            svc = SyncService(user_repo)
            
            app.logger.info("Starting initial IDP user synchronization...")
            for source in svc.get_sync_sources():
                svc.sync_users(source)
            app.logger.info("Completed initial IDP user synchronization.")
        except Exception as e:
            app.logger.error(f"Initial IDP sync failed: {e}")

# Run initialization exactly once when app loads
init_idp(app)

# 개발용 실행이다. 운영은 gunicorn 이 app.run:app 을 import 한다 (이 블록은 타지 않는다).
# Werkzeug 디버거는 브라우저에서 임의 코드를 실행하게 해 주므로 기본은 끈다. 켜려면 MWM_DEV_DEBUG=1
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=os.environ.get("MWM_DEV_DEBUG") == "1")
