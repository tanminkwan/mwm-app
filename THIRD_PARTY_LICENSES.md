# Third-party licenses

`sbom/build.py` 가 만든다 — 손으로 고치지 않는다 (HOWTO_020). 앱 버전 `20261001.004`.
기계가 읽는 목록(CycloneDX 1.6 SBOM)은 `sbom/mwm-app.cdx.json`·`sbom/mwm-idp.cdx.json` 이다.

이 프로젝트 자체는 [MIT](LICENSE) 다. 아래는 함께 설치·배포되는 외부 구성요소다.
Python 패키지는 운영 이미지(`mwm-app`·`mwm-idp`)에 실제로 설치된 것을 그대로 뽑았다 (pip·setuptools 포함).
`app/static` 의 JS/CSS 는 저장소에 넣어 둔 파일이라 `sbom/static-assets.json` 에 손으로 적는다 — 버전을 확인하지 못한 것은 `unknown`.

## 검토 필요

GPL·LGPL·상용·미확인 라이선스. "A OR B" 처럼 허용 라이선스를 고를 수 있는 것은 뺐다.

| 구분 | 이름 | 버전 | 라이선스 | 메모 |
| :--- | :--- | :--- | :--- | :--- |
| 본 앱 Python | cssutils | 2.15.0 | LGPL-3.0-or-later |  |
| 본 앱 Python | encutils | 1.0.0 | LGPL-3.0-or-later |  |
| 본 앱 Python | psycopg2-binary | 2.9.13 | GNU Library or Lesser General Public License (LGPL) |  |
| IdP Python | psycopg2-binary | 2.9.13 | GNU Library or Lesser General Public License (LGPL) |  |

## 본 앱 Python 패키지 (94)

| 이름 | 버전 | 라이선스 |
| :--- | :--- | :--- |
| alembic | 1.19.2 | MIT |
| apispec | 6.10.0 | MIT |
| APScheduler | 3.11.3 | MIT |
| attrs | 23.2.0 | MIT |
| Authlib | 1.8.0 | BSD-3-Clause AND BSD License |
| babel | 2.18.0 | BSD-3-Clause AND BSD License |
| blinker | 1.9.0 | MIT |
| boto3 | 1.43.102 | Apache-2.0 |
| botocore | 1.43.102 | Apache-2.0 |
| cachetools | 7.2.1 | MIT |
| certifi | 2026.7.22 | MPL-2.0 AND Mozilla Public License 2.0 (MPL 2.0) |
| cffi | 2.1.1 | MIT-0 |
| chardet | 7.6.0 | 0BSD |
| charset-normalizer | 3.5.1 | MIT |
| click | 8.5.0 | BSD-3-Clause |
| colorama | 0.4.6 | BSD License |
| croniter | 6.2.4 | MIT |
| cryptography | 50.0.1 | Apache-2.0 OR BSD-3-Clause |
| cssselect | 1.5.0 | BSD-3-Clause |
| cssutils | 2.15.0 | LGPL-3.0-or-later |
| deepdiff | 8.6.2 | MIT |
| Deprecated | 1.3.1 | MIT |
| dnspython | 2.8.0 | ISC |
| email-validator | 2.3.0 | Unlicense |
| encutils | 1.0.0 | LGPL-3.0-or-later |
| et_xmlfile | 2.0.0 | MIT |
| Flask | 3.1.3 | BSD-3-Clause |
| flask-appbuilder | 5.2.3 | BSD License |
| Flask-APScheduler | 1.13.1 | Apache 2.0 |
| flask-babel | 4.0.0 | BSD-3-Clause AND BSD License |
| Flask-JWT-Extended | 4.7.4 | MIT |
| Flask-Limiter | 3.8.0 | MIT |
| Flask-Login | 0.6.3 | MIT |
| Flask-Migrate | 4.1.0 | MIT |
| Flask-SQLAlchemy | 3.0.5 | BSD License |
| Flask-WTF | 1.3.0 | BSD License |
| greenlet | 3.5.6 | MIT AND PSF-2.0 |
| gunicorn | 22.0.0 | MIT |
| idna | 3.20 | BSD-3-Clause |
| importlib_resources | 6.4.0 | Apache Software License |
| itsdangerous | 2.2.0 | BSD License |
| Jinja2 | 3.1.6 | BSD License |
| jmespath | 1.1.0 | MIT |
| joserfc | 1.7.5 | BSD-3-Clause AND BSD License |
| jsonschema | 4.26.0 | MIT |
| jsonschema-specifications | 2023.12.1 | MIT |
| limits | 3.13.0 | MIT |
| lxml | 6.1.3 | BSD-3-Clause |
| Mako | 1.4.3 | MIT |
| Markdown | 3.11 | BSD-3-Clause |
| markdown-it-py | 3.0.0 | MIT |
| MarkupSafe | 2.1.5 | BSD-3-Clause AND BSD License |
| marshmallow | 3.26.2 | MIT |
| marshmallow-sqlalchemy | 0.28.2 | MIT |
| mdurl | 0.1.2 | MIT |
| more-itertools | 11.1.0 | MIT |
| numpy | 2.5.3 | BSD-3-Clause AND 0BSD AND MIT AND Zlib AND CC0-1.0 |
| openpyxl | 3.1.5 | MIT |
| ordered-set | 4.1.0 | MIT |
| orderly-set | 5.5.0 | MIT |
| packaging | 24.2 | Apache Software License AND BSD License |
| paho-mqtt | 2.1.0 | EPL-2.0 OR BSD-3-Clause |
| pandas | 2.2.2 | BSD License |
| pip | 26.2.1 | MIT |
| premailer | 3.10.0 | Python-2.0 |
| prison | 0.2.1 | MIT |
| psycopg2-binary | 2.9.13 | GNU Library or Lesser General Public License (LGPL) |
| pycparser | 3.0 | BSD-3-Clause |
| Pygments | 2.21.0 | BSD-2-Clause |
| PyJWT | 2.15.0 | MIT |
| python-dateutil | 2.9.0.post0 | Apache Software License AND BSD License |
| python-dotenv | 1.2.3 | BSD-3-Clause |
| pytz | 2024.1 | MIT |
| PyYAML | 6.0.3 | MIT |
| redis | 8.1.0 | MIT |
| referencing | 0.37.0 | MIT |
| requests | 2.34.2 | Apache-2.0 AND Apache Software License |
| rich | 13.7.1 | MIT |
| rpds-py | 2026.6.3 | MIT |
| s3transfer | 0.19.2 | Apache Software License |
| setuptools | 84.0.0 | MIT |
| six | 1.17.0 | MIT |
| SQLAlchemy | 1.4.54 | MIT |
| SQLAlchemy-Utils | 0.42.1 | BSD-3-Clause |
| typing_extensions | 4.16.0 | PSF-2.0 |
| tzdata | 2024.1 | Apache-2.0 AND Apache Software License |
| tzlocal | 5.4.4 | MIT |
| urllib3 | 2.8.0 | MIT |
| Werkzeug | 3.1.9 | BSD-3-Clause |
| wheel | 0.48.0 | MIT |
| wrapt | 1.16.0 | BSD License |
| WTForms | 3.2.2 | BSD License |
| xlsxwriter | 3.2.9 | BSD-2-Clause AND BSD License |
| xmltodict | 1.0.4 | MIT |

## IdP Python 패키지 (27)

| 이름 | 버전 | 라이선스 |
| :--- | :--- | :--- |
| Authlib | 1.8.0 | BSD-3-Clause AND BSD License |
| bcrypt | 5.0.0 | Apache-2.0 AND Apache Software License |
| blinker | 1.9.0 | MIT |
| cffi | 2.1.1 | MIT-0 |
| click | 8.5.0 | BSD-3-Clause |
| cryptography | 50.0.1 | Apache-2.0 OR BSD-3-Clause |
| Flask | 3.1.3 | BSD-3-Clause |
| Flask-Login | 0.6.3 | MIT |
| Flask-SQLAlchemy | 3.0.5 | BSD License |
| Flask-WTF | 1.3.0 | BSD License |
| greenlet | 3.5.6 | MIT AND PSF-2.0 |
| gunicorn | 26.2.0 | MIT |
| itsdangerous | 2.2.0 | BSD License |
| Jinja2 | 3.1.6 | BSD License |
| joserfc | 1.7.5 | BSD-3-Clause AND BSD License |
| MarkupSafe | 3.0.4 | BSD-3-Clause |
| packaging | 26.3 | Apache-2.0 OR BSD-2-Clause |
| pip | 26.2.1 | MIT |
| psycopg2-binary | 2.9.13 | GNU Library or Lesser General Public License (LGPL) |
| pycparser | 3.0 | BSD-3-Clause |
| PyJWT | 2.15.0 | MIT |
| python-dotenv | 1.2.3 | BSD-3-Clause |
| setuptools | 84.0.0 | MIT |
| SQLAlchemy | 1.4.54 | MIT |
| Werkzeug | 3.1.9 | BSD-3-Clause |
| wheel | 0.48.0 | MIT |
| WTForms | 3.2.2 | BSD License |

## app/static — vendored JS/CSS (24)

| 이름 | 버전 | 라이선스 |
| :--- | :--- | :--- |
| bPopup | 0.11.0 | MIT |
| diff2html | unknown | MIT |
| DOMPurify | 3.4.16 | MPL-2.0 OR Apache-2.0 |
| DOMPurify (mermaid 내장) | 3.4.12 | MPL-2.0 OR Apache-2.0 |
| DOMPurify (TOAST UI Editor 내장) | 3.4.16 | MPL-2.0 OR Apache-2.0 |
| free jqGrid | 4.15.5 | MIT |
| jQuery UI | 1.14.1 | MIT |
| jquery.flowchart | unknown | MIT |
| jquery.gridly | 1.3.0 | MIT |
| jquery.json-viewer | unknown | MIT |
| jsdiff | unknown | BSD-3-Clause |
| mermaid | 11.17.2 | MIT |
| Moment.js | 2.31.0 | MIT |
| Prism | unknown | MIT |
| SheetJS Community Edition | 0.20.3 | Apache-2.0 |
| Summernote | 0.9.1 | MIT |
| TOAST UI Chart | 4.6.1 | MIT |
| TOAST UI Color Picker | 2.2.8 | MIT |
| TOAST UI Editor | 3.2.2 | MIT |
| TOAST UI Editor Plugin Chart | 3.0.1 | MIT |
| TOAST UI Editor Plugin Code Syntax Highlight | 3.0.0 | MIT |
| TOAST UI Editor Plugin Color Syntax | 3.0.3 | MIT |
| TOAST UI Editor Plugin Table Merged Cell | 3.0.2 | MIT |
| TOAST UI Editor Plugin UML | 3.0.1 | MIT |
