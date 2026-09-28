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

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
