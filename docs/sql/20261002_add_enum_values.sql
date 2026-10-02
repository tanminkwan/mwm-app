-- =============================================================================
-- Enum 값 추가 (적용) — ExtractLog, MQTT, MQTT_FAILED
--   commandclassenum  : ExtractLog          (Log Extractor 명령 유형)
--   targettosendenum  : MQTT                (명령 전달 경로)
--   commandstatusenum : MQTT, MQTT_FAILED   (명령 상태)
--
-- 왜 필요한가 : 이 값들은 alembic migration 에만 있고 SQL 이 없었다. 운영에는 migration 수단이 없으므로
--   손으로 적용한다. 새 앱이 이 값을 쓰면 값이 없는 DB 에서는 명령 생성·상태 저장이 실패한다.
-- 순서 : 새 앱 기동 전. 값만 더하므로 구 앱은 영향이 없다 → 앱을 멈추지 않고 적용해도 된다.
--        다시 실행해도 된다 (IF NOT EXISTS). 이미 있으면 아무 일도 하지 않는다.
--        20260927_drop_kafka_enum_values.sql 보다 먼저든 나중이든 상관없다.
--
-- 적용 :
--   docker exec -i mwm-db psql -U <DB 사용자> -d mw \
--       -v ON_ERROR_STOP=1 -f /dev/stdin < docs/sql/20261002_add_enum_values.sql
--
-- 되돌리기 : 없다. PostgreSQL 은 enum 값을 지우지 못하고, 남겨 둬도 구 앱은 동작한다.
-- =============================================================================

ALTER TYPE commandclassenum  ADD VALUE IF NOT EXISTS 'ExtractLog';
ALTER TYPE targettosendenum  ADD VALUE IF NOT EXISTS 'MQTT';
ALTER TYPE commandstatusenum ADD VALUE IF NOT EXISTS 'MQTT';
ALTER TYPE commandstatusenum ADD VALUE IF NOT EXISTS 'MQTT_FAILED';

-- 확인 : 아래 세 줄에 각각 ExtractLog / MQTT / MQTT, MQTT_FAILED 가 들어 있어야 한다
SELECT t.typname, string_agg(e.enumlabel, ', ' ORDER BY e.enumsortorder) AS labels
  FROM pg_type t JOIN pg_enum e ON e.enumtypid = t.oid
 WHERE t.typname IN ('commandclassenum', 'targettosendenum', 'commandstatusenum')
 GROUP BY t.typname ORDER BY t.typname;
