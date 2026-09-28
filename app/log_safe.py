"""로그에 넣는 외부 값의 줄바꿈을 이스케이프한다 (CodeQL py/log-injection).

요청·설정 파일에서 온 값에 CR/LF 가 있으면 가짜 로그 줄을 만들 수 있다.

    logging.info(f"User created: {log_safe(username)}")
"""


def log_safe(value):
    return str(value).replace('\r', '\\r').replace('\n', '\\n')
