-- =============================================================================
-- Agent MQTT 수신 상태 컬럼 추가 (되돌리기)
--   20260929_add_agent_mqtt_status.sql 이 붙인 ag_agent 컬럼 6개를 지운다. 값도 함께 없어진다.
--
-- 관련 : docs/HOWTO_019_agent_mqtt_status.md §6
-- 순서 : ⚠ **구 앱으로 먼저 바꾼 뒤** 적용한다. 새 앱은 이 컬럼이 없으면 ag_agent 조회가 모두 실패한다.
--        다시 실행해도 된다 (IF EXISTS).
--
-- 적용 :
--   docker exec -i mwm-db psql -U <DB 사용자> -d mw \
--       -v ON_ERROR_STOP=1 -f /dev/stdin < docs/sql/20260929_add_agent_mqtt_status_rollback.sql
-- =============================================================================

BEGIN;

ALTER TABLE ag_agent
    DROP COLUMN IF EXISTS mqtt_state,
    DROP COLUMN IF EXISTS mqtt_since,
    DROP COLUMN IF EXISTS mqtt_events,
    DROP COLUMN IF EXISTS mqtt_last_msg,
    DROP COLUMN IF EXISTS mqtt_reason,
    DROP COLUMN IF EXISTS mqtt_raw;

\echo '--- 되돌린 후 (0행이어야 한다)'
SELECT column_name FROM information_schema.columns
 WHERE table_schema = 'public' AND table_name = 'ag_agent' AND column_name LIKE 'mqtt\_%';

COMMIT;
