-- =============================================================================
-- "정기 JOB 목록" 화면의 데이터 권한 부여 (적용)
--   Flask-APScheduler REST API(/scheduler/...) 를 껐다 — 인증 없이 작업을 추가·실행할 수 있었다.
--   화면(MonitorApi.jobSchedulerList)은 이제 /monitor/jobs.json(MonitorApi.jobs_json)을 읽는다.
--   FAB 는 새 권한 can_jobs_json 을 Admin 에만 자동으로 준다. 화면 권한이 있는 역할에 같이 준다.
--
-- 관련 : HOWTO_020 §6
-- 순서 : **새 앱을 기동한 뒤** (권한 항목은 앱이 뜰 때 만들어진다). 다시 실행해도 된다.
--
-- 적용 :
--   docker exec -i mwm-db psql -U <DB 사용자> -d mw \
--       -v ON_ERROR_STOP=1 -f /dev/stdin < docs/sql/20260930_grant_job_list_json.sql
--
-- 리허설 : 파일 끝의 COMMIT 을 ROLLBACK 으로 바꿔 실행한다.
-- =============================================================================

BEGIN;

DO $$
DECLARE
    pv_list integer;
    pv_json integer;
    added   integer;
BEGIN
    SELECT pv.id INTO pv_list FROM ab_permission_view pv
      JOIN ab_permission p ON p.id = pv.permission_id
      JOIN ab_view_menu vm ON vm.id = pv.view_menu_id
     WHERE p.name = 'can_jobSchedulerList' AND vm.name = 'MonitorApi';
    SELECT pv.id INTO pv_json FROM ab_permission_view pv
      JOIN ab_permission p ON p.id = pv.permission_id
      JOIN ab_view_menu vm ON vm.id = pv.view_menu_id
     WHERE p.name = 'can_jobs_json' AND vm.name = 'MonitorApi';
    IF pv_json IS NULL THEN
        RAISE EXCEPTION 'can_jobs_json on MonitorApi 가 없다 — 새 앱을 먼저 기동한다';
    END IF;
    IF pv_list IS NULL THEN
        RAISE NOTICE 'skip: can_jobSchedulerList on MonitorApi 가 없다';
        RETURN;
    END IF;
    -- id 에 기본값이 없다 — FAB 처럼 시퀀스에서 받는다
    INSERT INTO ab_permission_view_role (id, permission_view_id, role_id)
    SELECT nextval('ab_permission_view_role_id_seq'), pv_json, r.role_id FROM ab_permission_view_role r
     WHERE r.permission_view_id = pv_list
       AND NOT EXISTS (SELECT 1 FROM ab_permission_view_role x
                        WHERE x.permission_view_id = pv_json AND x.role_id = r.role_id);
    GET DIAGNOSTICS added = ROW_COUNT;
    RAISE NOTICE 'granted can_jobs_json to % role(s)', added;
END $$;

\echo '--- 적용 후 (두 권한의 역할 목록이 같아야 한다)'
SELECT p.name AS permission, string_agg(r.name, ', ' ORDER BY r.name) AS roles
  FROM ab_permission_view_role pvr
  JOIN ab_role r ON r.id = pvr.role_id
  JOIN ab_permission_view pv ON pv.id = pvr.permission_view_id
  JOIN ab_permission p ON p.id = pv.permission_id
  JOIN ab_view_menu vm ON vm.id = pv.view_menu_id
 WHERE vm.name = 'MonitorApi' AND p.name IN ('can_jobSchedulerList', 'can_jobs_json')
 GROUP BY p.name ORDER BY p.name;

COMMIT;
