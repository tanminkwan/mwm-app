-- =============================================================================
-- IDP 로그인 잠금 컬럼 추가 (되돌리기)
--   20261007_add_idp_login_lockout.sql 이 붙인 idp_user 컬럼 2개를 지운다. 값도 함께 없어진다.
--
-- 순서 : ⚠ **구 mwm-idp 로 먼저 바꾼 뒤** 적용한다. 새 앱은 이 컬럼이 없으면 idp_user 조회가 모두 실패한다.
--        다시 실행해도 된다 (IF EXISTS).
--
-- 적용 :
--   docker exec -i mwm-db psql -U <DB 사용자> -d idp \
--       -v ON_ERROR_STOP=1 -f /dev/stdin < docs/sql/20261007_add_idp_login_lockout_rollback.sql
-- =============================================================================

BEGIN;

ALTER TABLE idp_user
    DROP COLUMN IF EXISTS failed_login_count,
    DROP COLUMN IF EXISTS locked_until;

\echo '--- 되돌린 후 (0행이어야 한다)'
SELECT column_name FROM information_schema.columns
 WHERE table_schema = 'public' AND table_name = 'idp_user'
   AND column_name IN ('failed_login_count', 'locked_until');

COMMIT;
