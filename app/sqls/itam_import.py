"""ITAM 엑셀 업로드 — 헤더(한글 라벨) → 모델 컬럼 대응 (WS-4-6).

고객사 쪽 담당자 컬럼은 `cust_p_mngr` / `cust_s_mngr` 이고 라벨은 `고객담당자(정/부)` 다.
예전 양식의 엑셀은 담당자 헤더 앞에 기관명이 붙어 있으므로, 정확히 일치하는 헤더가 없으면
ITO 가 아닌 `…담당자(정)` / `…담당자(부)` 헤더를 고객 담당자로 받는다.
"""

WAS_COLUMNS = {
    '구성번호': 'config_id',
    '구성명': 'config_name',
    '설치호스트명': 'host_id',
    '업무시스템': 'biz_system',
    '업무팀': 'biz_team',
    'OS대표IP (GW기준)': 'gw_ip',
    '서비스IP': 'service_ip',
    '운용환경': 'run_env',
    '구성상태': 'config_status',
    '설치계정명': 'install_user',
    'JEUS버전': 'jeus_version',
    'OS종류': 'os_type',
    'OS버전': 'os_ver',
    '도메인명': 'domain_name',
    'BASE포트': 'base_port',
    'JAVA버전': 'java_version',
    '내장WEB 사용여부': 'embed_web_yn',
    '내장WEB 노드포트': 'embed_web_port',
    '내장WEB SSL사용여부': 'embed_web_ssl_yn',
    'WAS SSL사용여부': 'was_ssl_yn',
    'OS커널': 'os_kernel',
    'CPU (Core)': 'cpu_core',
    'MEM (GB)': 'mem_gb',
    '하드웨어네임': 'hw_name',
    '하드웨어그룹': 'hw_group',
    '담당팀': 'dept_team',
    '고객담당자(정)': 'cust_p_mngr',
    '고객담당자(부)': 'cust_s_mngr',
    'ITO담당자(정)': 'ito_p_mngr',
    'ITO담당자(부)': 'ito_s_mngr'
}

WEB_COLUMNS = {
    '구성번호': 'config_id',
    '구성명': 'config_name',
    '설치호스트명': 'host_id',
    '업무시스템': 'biz_system',
    '업무팀': 'biz_team',
    'OS대표IP (GW기준)': 'gw_ip',
    '서비스IP': 'service_ip',
    '운용환경': 'run_env',
    '구성상태': 'config_status',
    '설치계정명': 'install_user',
    'Webtob버전': 'webtob_version',
    'OS종류': 'os_type',
    'OS버전': 'os_ver',
    '노드포트': 'node_port',
    'SSL사용여부': 'ssl_yn',
    'EV인증서여부': 'ev_cert_yn',
    'WEB서버위치': 'server_loc',
    'OS커널': 'os_kernel',
    'CPU (Core)': 'cpu_core',
    'MEM (GB)': 'mem_gb',
    '하드웨어네임': 'hw_name',
    '하드웨어그룹': 'hw_group',
    '담당팀': 'dept_team',
    '고객담당자(정)': 'cust_p_mngr',
    '고객담당자(부)': 'cust_s_mngr',
    'ITO담당자(정)': 'ito_p_mngr',
    'ITO담당자(부)': 'ito_s_mngr'
}

_FALLBACK = (('담당자(정)', 'cust_p_mngr'), ('담당자(부)', 'cust_s_mngr'))


def resolve_columns(headers, mapping):
    """엑셀 헤더 목록 → {헤더: 컬럼}. 모르는 헤더는 뺀다."""
    headers = [str(h) for h in headers]
    result = {h: mapping[h] for h in headers if h in mapping}
    taken = set(result.values())
    for suffix, column in _FALLBACK:
        if column in taken:
            continue
        for h in headers:
            if h not in result and h.endswith(suffix) and not h.upper().startswith('ITO'):
                result[h] = column
                taken.add(column)
                break
    return result
