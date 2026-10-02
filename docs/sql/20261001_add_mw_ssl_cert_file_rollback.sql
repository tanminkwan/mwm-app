-- =============================================================================
-- SSL 인증서 파일 테이블 추가 (되돌리기)
--   20261001_add_mw_ssl_cert_file.sql 이 만든 테이블과 타입을 지운다. 등록한 인증서 정보도 함께 없어진다.
--   (원본 파일은 ag_file·S3 에 그대로 남는다)
--
-- 관련 : docs/HOWTO_021_ssl_cert_file.md §7
-- 순서 : ⚠ **구 앱으로 먼저 바꾼 뒤** 적용한다. 다시 실행해도 된다 (IF EXISTS).
--
-- 적용 :
--   docker exec -i mwm-db psql -U <DB 사용자> -d mw \
--       -v ON_ERROR_STOP=1 -f /dev/stdin < docs/sql/20261001_add_mw_ssl_cert_file_rollback.sql
-- =============================================================================

BEGIN;

DROP TABLE IF EXISTS mw_ssl_cert_file;
DROP TYPE IF EXISTS sslcerttypeenum;

COMMIT;
