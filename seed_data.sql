-- 기본 시드 데이터 — 새 설치에서 앱이 처음 뜬 뒤 1회 적용한다. 다시 실행해도 된다 (있는 행은 건너뛴다).
--
--   docker exec -i mwm-db psql -U <DB 계정> -d mw -v ON_ERROR_STOP=1 -f /dev/stdin < seed_data.sql
--
-- 테이블은 앱이 기동할 때 만든다 — 그 전에 돌리면 "relation does not exist" 로 멈춘다.
--
-- 코드가 이 행들이 DB 에 있다고 가정한다 (docs/REPORT_seed_data_dependencies.md).
-- 없으면 SSL 인증서 수집·토큰 갱신·권한 동기화·로그 추출 등이 동작하지 않는다.

BEGIN;

-- 명령 유형 — 코드가 command_type_id / command_class 로 찾는다
INSERT INTO ag_command_type (command_type_id, command_type_name, command_class, target_file_path, target_file_name, user_id, create_on)
VALUES
    ('CALL.GET_SSL_CERTI',    'Agent GetSSLCertiInfo 호출',         'ExeAgentFunc',     NULL,               'get_ssl_certi',                 'system', now()),
    ('CALL.SET_PROPERTIES',   'Agent Properties 변경/조회',         'ExeAgentFunc',     NULL,               'set_properties',                'system', now()),
    ('COMMON.READFILE',       '지정 경로 파일 읽기',                 'ReadFullPathFile', NULL,               NULL,                            'system', now()),
    ('EXTRACT.LOG',           'Extract Log',                         'ExtractLog',       NULL,               NULL,                            'system', now()),
    ('SYNC.ROLE_PERMISSIONS', 'Role/Permission 자동 동기화',         'ServerFunc',       NULL,               'sync_role_permissions',         'system', now()),
    ('WAS.REBUILD',           'WAS 전체 재등록 (원문에서)',          'ServerFunc',       NULL,               're_register_all_was_from_text', 'system', now()),
    ('mwagent.download',      'mwagent.jar download',                'DownloadFile',     '.',                'mwagent.jar',                   'system', now()),
    ('sslcertifile.download', 'SSL 인증서 download',                 'DownloadFile',     '<<WEBTOBDIR>>/ssl/', 'mwmanger.jar',                'system', now()),
    ('updateToken',           '만료임박한 Refresh Token Update',     'GetRefreshToken',  NULL,               NULL,                            'system', now())
ON CONFLICT (command_type_id) DO NOTHING;

-- 자동 후처리 — 결과 파일 이름으로 후처리 함수를 고른다 (고유 키가 id 뿐이라 autorun_id 로 존재를 본다)
INSERT INTO ag_autorun_result (autorun_id, autorun_type, target_file_name, command_id, autorun_func, autorun_param, user_id, create_on)
SELECT v.autorun_id, v.autorun_type::autoruntypeenum, v.target_file_name, '', v.autorun_func, '', 'system', now()
  FROM (VALUES
          ('01.domain.xml',     'FILENAME', 'domain.*\.xml',  'update_jeus_domain'),
          ('01.CallConnectSSL', 'FILENAME', 'get_ssl_certi',  'update_connect_ssl_by_api'),
          ('01.gc',             'FILENAME', 'gc_parsed.csv',  'update_gc_parsed_log')
       ) AS v(autorun_id, autorun_type, target_file_name, autorun_func)
 WHERE NOT EXISTS (SELECT 1 FROM ag_autorun_result a WHERE a.autorun_id = v.autorun_id);

\echo '--- 결과'
SELECT 'ag_command_type' AS "table", count(*) AS "rows" FROM ag_command_type
UNION ALL
SELECT 'ag_autorun_result', count(*) FROM ag_autorun_result;

COMMIT;
