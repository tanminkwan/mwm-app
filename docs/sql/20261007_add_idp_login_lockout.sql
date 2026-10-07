-- =============================================================================
-- IDP 로그인 잠금 컬럼 추가 (적용)
--   idp_user 에 연속 실패 횟수(failed_login_count)와 잠금 해제 시각(locked_until)을 붙인다.
--
-- 순서 : **이 SQL 먼저 → 새 mwm-idp.** 구 앱은 이 컬럼을 모르므로 그대로 동작한다.
--        새 앱을 이 SQL 없이 띄우면 idp_user 조회가 모두 실패한다 (로그인 불가).
--        다시 실행해도 된다 (IF NOT EXISTS).
--
-- 적용 (IDP DB 이름은 idp) :
--   docker exec -i mwm-db psql -U <DB 사용자> -d idp \
--       -v ON_ERROR_STOP=1 -f /dev/stdin < docs/sql/20261007_add_idp_login_lockout.sql
--
-- 되돌리기 : 20261007_add_idp_login_lockout_rollback.sql (구 앱으로 먼저 바꾼 뒤)
-- 리허설  : 파일 끝의 COMMIT 을 ROLLBACK 으로 바꿔 실행한다.
-- =============================================================================

BEGIN;

ALTER TABLE idp_user
    ADD COLUMN IF NOT EXISTS failed_login_count INTEGER NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS locked_until       TIMESTAMP WITHOUT TIME ZONE;

COMMENT ON COLUMN idp_user.failed_login_count IS '연속 로그인 실패 횟수. 성공하거나 잠기면 0';
COMMENT ON COLUMN idp_user.locked_until IS '이 시각(UTC)까지 로그인 잠금. NULL = 잠기지 않음';

\echo '--- 적용 후'
SELECT column_name, data_type, is_nullable, column_default
  FROM information_schema.columns
 WHERE table_schema = 'public' AND table_name = 'idp_user'
   AND column_name IN ('failed_login_count', 'locked_until')
 ORDER BY ordinal_position;

COMMIT;
