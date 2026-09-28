import os

from app import app

# 개발용 진입점이다. 운영은 gunicorn(supervisord.conf)으로 뜬다.
# Werkzeug 디버거는 브라우저에서 임의 코드를 실행하게 해 주므로 기본은 끈다. 켜려면 MWM_DEV_DEBUG=1
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080, debug=os.environ.get("MWM_DEV_DEBUG") == "1")
