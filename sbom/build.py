"""SBOM(CycloneDX 1.6)과 THIRD_PARTY_LICENSES.md 를 만든다 (HOWTO_020).

generate.sh 가 이미지에서 뽑은 원자료(cyclonedx-py·pip-licenses 결과)를 받아
- sbom/mwm-app.cdx.json : 본 앱 Python 패키지 + app/static 의 vendored JS/CSS (static-assets.json)
- sbom/mwm-idp.cdx.json : IdP Python 패키지
- THIRD_PARTY_LICENSES.md : 위 전부의 라이선스 표와 검토 필요 항목
을 쓴다. 표준 라이브러리만 쓴다.

    python3 sbom/build.py <원자료 디렉터리> <앱 버전>
    python3 sbom/build.py --check      # app/static 목록 검사만 (CI lint job)
"""
import fnmatch
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SBOM = ROOT / 'sbom'

# 이 식에 걸리면 THIRD_PARTY_LICENSES.md 의 '검토 필요' 로 뺀다.
# LGPL 은 수정 없이 import 해서 쓰는 한 보통 문제가 없지만, 판단은 조직 규정을 따르므로 함께 적는다.
REVIEW = re.compile(r'\b(A?GPL|LGPL|SSPL|BUSL|EUPL|CC-BY-NC|Commercial|Proprietary|LicenseRef|UNKNOWN)', re.I)
# 둘 중 고르는 라이선스(OR)는 허용 쪽을 고를 수 있으면 검토 대상이 아니다
PERMISSIVE = re.compile(r'^(MIT|MIT-0|BSD-[23]-Clause|0BSD|Apache-2\.0|ISC|PSF-2\.0|Zlib|Unlicense|CC0-1\.0|MPL-2\.0)$')


def load(path):
    with open(path, encoding='utf-8') as f:
        return json.load(f)


def needs_review(expr):
    if not expr:
        return True
    if ' OR ' in expr and any(PERMISSIVE.match(p.strip(' ()')) for p in expr.split(' OR ')):
        return False
    return bool(REVIEW.search(expr))


def component_license(comp):
    """CycloneDX component 의 라이선스를 문자열 하나로."""
    names = []
    for lic in comp.get('licenses', []):
        if 'expression' in lic:
            names.append(lic['expression'])
        else:
            one = lic.get('license', {})
            names.append((one.get('id') or one.get('name') or '').replace('License :: OSI Approved :: ', ''))
    return ' AND '.join(n for n in names if n)


def python_bom(raw_dir, image, name, version):
    """cyclonedx-py 결과에 루트 컴포넌트를 붙이고, 빠진 라이선스를 pip-licenses 로 채운다."""
    bom = load(raw_dir / f'{image}.cdx.json')
    pip_licenses = {x['Name'].lower(): x['License'] for x in load(raw_dir / f'{image}.licenses.json')}
    for comp in bom['components']:
        if not comp.get('licenses') and comp['name'].lower() in pip_licenses:
            comp['licenses'] = [{'license': {'name': pip_licenses[comp['name'].lower()],
                                             'acknowledgement': 'declared'}}]
    bom['metadata']['component'] = {
        'type': 'application', 'bom-ref': name, 'name': name, 'version': version,
        'licenses': [{'license': {'id': 'MIT'}}],
        'externalReferences': [{'type': 'vcs', 'url': 'https://github.com/tanminkwan/mwm-app'}],
    }
    return bom


def static_components():
    """static-assets.json → CycloneDX components. app/static 의 모든 파일이 어딘가에 속하는지 검사한다."""
    inv = load(SBOM / 'static-assets.json')
    tracked = sorted(str(p.relative_to(ROOT)) for p in (ROOT / 'app/static').rglob('*') if p.is_file())
    owned = set(inv['first_party'])
    comps = []
    for c in inv['components']:
        files = sorted({f for pat in c['files'] for f in tracked if fnmatch.fnmatch(f, pat)})
        if not files:
            sys.exit(f"static-assets.json: '{c['name']}' 의 files 가 아무 파일과도 맞지 않는다")
        owned.update(files)
        version = c['version'] or 'unknown'
        props = [{'name': 'mwm:file', 'value': f} for f in files]
        if c.get('note'):
            props.append({'name': 'mwm:note', 'value': c['note']})
        if c.get('review'):
            props.append({'name': 'mwm:license-review', 'value': c['review']})
        if not c['version']:
            props.append({'name': 'mwm:version-unknown', 'value': 'true'})
        comp = {
            'type': 'library', 'bom-ref': f"static:{c['name']}@{version}",
            'name': c['name'], 'version': version,
            'licenses': [{'expression': c['license']}],
            'externalReferences': [{'type': 'website', 'url': c['url']}],
            'properties': props,
        }
        if c['version']:
            comp['purl'] = f"pkg:npm/{c['purl_name'].replace('@', '%40')}@{c['version']}"
        comps.append(comp)
    orphans = [f for f in tracked if f not in owned]
    if orphans:
        sys.exit('static-assets.json 에 없는 app/static 파일:\n  ' + '\n  '.join(orphans))
    return comps


def write_json(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + '\n', encoding='utf-8')


def table(rows):
    out = ['| 이름 | 버전 | 라이선스 |', '| :--- | :--- | :--- |']
    out += [f'| {n} | {v} | {l or "(없음)"} |' for n, v, l in rows]
    return '\n'.join(out)


def main(raw_dir, version):
    raw_dir = Path(raw_dir)
    app = python_bom(raw_dir, 'mwm-app', 'mwm-app', version)
    idp = python_bom(raw_dir, 'mwm-idp', 'mwm-idp', version)
    static = static_components()
    app['components'] = sorted(app['components'], key=lambda c: c['name'].lower()) + static
    write_json(SBOM / 'mwm-app.cdx.json', app)
    write_json(SBOM / 'mwm-idp.cdx.json', idp)

    def rows(comps):
        return sorted(((c['name'], c['version'], component_license(c)) for c in comps), key=lambda r: r[0].lower())

    py_app = [c for c in app['components'] if not c['bom-ref'].startswith('static:')]
    review = [('본 앱 Python', *r) for r in rows(py_app) if needs_review(r[2])]
    review += [('IdP Python', *r) for r in rows(idp['components']) if needs_review(r[2])]
    notes = {c['name']: next((p['value'] for p in c['properties'] if p['name'] == 'mwm:license-review'), '')
             for c in static}
    review += [('app/static', *r) for r in rows(static) if needs_review(r[2])]

    md = [
        '# Third-party licenses',
        '',
        f'`sbom/build.py` 가 만든다 — 손으로 고치지 않는다 (HOWTO_020). 앱 버전 `{version}`.',
        '기계가 읽는 목록(CycloneDX 1.6 SBOM)은 `sbom/mwm-app.cdx.json`·`sbom/mwm-idp.cdx.json` 이다.',
        '',
        '이 프로젝트 자체는 [MIT](LICENSE) 다. 아래는 함께 설치·배포되는 외부 구성요소다.',
        'Python 패키지는 운영 이미지(`mwm-app`·`mwm-idp`)에 실제로 설치된 것을 그대로 뽑았다 (pip·setuptools 포함).',
        '`app/static` 의 JS/CSS 는 저장소에 넣어 둔 파일이라 `sbom/static-assets.json` 에 손으로 적는다 — 버전을 확인하지 못한 것은 `unknown`.',
        '',
        '## 검토 필요',
        '',
        'GPL·LGPL·상용·미확인 라이선스. "A OR B" 처럼 허용 라이선스를 고를 수 있는 것은 뺐다.',
        '',
        '| 구분 | 이름 | 버전 | 라이선스 | 메모 |',
        '| :--- | :--- | :--- | :--- | :--- |',
    ]
    md += [f'| {g} | {n} | {v} | {l or "(없음)"} | {notes.get(n, "")} |' for g, n, v, l in review] or ['| - | 없음 | | | |']
    md += ['', f'## 본 앱 Python 패키지 ({len(py_app)})', '', table(rows(py_app)),
           '', f'## IdP Python 패키지 ({len(idp["components"])})', '', table(rows(idp['components'])),
           '', f'## app/static — vendored JS/CSS ({len(static)})', '', table(rows(static)), '']
    (ROOT / 'THIRD_PARTY_LICENSES.md').write_text('\n'.join(md), encoding='utf-8')

    print(f'mwm-app: Python {len(py_app)} + static {len(static)} / mwm-idp: Python {len(idp["components"])}')
    print(f'검토 필요 {len(review)}건:')
    for g, n, v, l in review:
        print(f'  [{g}] {n} {v}: {l}')


if __name__ == '__main__':
    if sys.argv[1:] == ['--check']:
        print(f'static-assets.json: 외부 구성요소 {len(static_components())}개, app/static 파일 전부 목록에 있음')
        sys.exit(0)
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    main(sys.argv[1], sys.argv[2])
