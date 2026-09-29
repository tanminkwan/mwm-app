-- =============================================================================
-- Agent MQTT 수신 상태 컬럼 추가 (적용)
--   ag_agent 에 X-Mqtt-Status 헤더 값을 담을 컬럼 6개를 붙인다.
--   mqtt_state 가 NULL 이면 MQTT 비대상이다.
--
-- 관련 : docs/HOWTO_019_agent_mqtt_status.md §6
-- 순서 : **이 SQL 먼저 → 새 앱.** 컬럼이 모두 NULL 허용·기본값 없음이라
--        구 앱은 그대로 동작한다 → 앱을 멈추지 않고 적용해도 된다 (잠금은 순간이다).
--        새 앱을 이 SQL 없이 띄우면 ag_agent 조회가 모두 실패한다.
--        다시 실행해도 된다 (IF NOT EXISTS).
--
-- 적용 :
--   docker exec -i mwm-db psql -U <DB 사용자> -d mw \
--       -v ON_ERROR_STOP=1 -f /dev/stdin < docs/sql/20260929_add_agent_mqtt_status.sql
--   (테스트 DB 가 있으면 -d mw_test 로 한 번 더)
--
-- 되돌리기 : 20260929_add_agent_mqtt_status_rollback.sql (구 앱으로 먼저 바꾼 뒤)
-- 리허설  : 파일 끝의 COMMIT 을 ROLLBACK 으로 바꿔 실행한다.
-- =============================================================================

BEGIN;

ALTER TABLE ag_agent
    ADD COLUMN IF NOT EXISTS mqtt_state    VARCHAR(20),
    ADD COLUMN IF NOT EXISTS mqtt_since    TIMESTAMP WITHOUT TIME ZONE,
    ADD COLUMN IF NOT EXISTS mqtt_events   INTEGER,
    ADD COLUMN IF NOT EXISTS mqtt_last_msg TIMESTAMP WITHOUT TIME ZONE,
    ADD COLUMN IF NOT EXISTS mqtt_reason   VARCHAR(120),
    ADD COLUMN IF NOT EXISTS mqtt_raw      VARCHAR(300);

COMMENT ON COLUMN ag_agent.mqtt_state IS 'MQTT 수신 상태 (X-Mqtt-Status). NULL = MQTT 비대상';

\echo '--- 적용 후'
SELECT column_name, data_type, character_maximum_length AS len, is_nullable
  FROM information_schema.columns
 WHERE table_schema = 'public' AND table_name = 'ag_agent' AND column_name LIKE 'mqtt\_%'
 ORDER BY ordinal_position;

COMMIT;
