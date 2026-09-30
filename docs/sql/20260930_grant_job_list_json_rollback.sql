-- =============================================================================
-- "정기 JOB 목록" 화면의 데이터 권한 부여 (되돌리기)
--   20260930_grant_job_list_json.sql 이 준 can_jobs_json 을 Admin 을 뺀 역할에서 거둔다.
--   구 앱으로 되돌릴 때만 쓴다 (구 앱에는 이 권한이 없다 — 남겨 둬도 동작에는 영향이 없다).
-- =============================================================================

BEGIN;

DELETE FROM ab_permission_view_role pvr
 USING ab_permission_view pv, ab_permission p, ab_view_menu vm, ab_role r
 WHERE pvr.permission_view_id = pv.id AND pv.permission_id = p.id AND pv.view_menu_id = vm.id
   AND pvr.role_id = r.id
   AND p.name = 'can_jobs_json' AND vm.name = 'MonitorApi' AND r.name <> 'Admin';

COMMIT;
