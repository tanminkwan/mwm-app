-- =============================================================================
-- SSL 인증서 파일 테이블 추가 (적용)
--   mw_ssl_cert_file — 화면 "SSL 인증서 파일" 과 1:1. 적용 현황 화면이 이 테이블을 읽는다.
--
-- 관련 : docs/HOWTO_021_ssl_cert_file.md §7
-- 순서 : **이 SQL 먼저 → 새 앱.** 새 테이블이라 구 앱은 영향이 없다 → 앱을 멈추지 않고 적용해도 된다.
--        새 앱을 이 SQL 없이 띄우면 두 화면이 실패한다.
--        다시 실행해도 된다 (IF NOT EXISTS).
--
-- 적용 :
--   docker exec -i mwm-db psql -U <DB 사용자> -d mw \
--       -v ON_ERROR_STOP=1 -f /dev/stdin < docs/sql/20261001_add_mw_ssl_cert_file.sql
--   (테스트 DB 는 conftest 의 create_all 이 만든다)
--
-- 되돌리기 : 20261001_add_mw_ssl_cert_file_rollback.sql (구 앱으로 먼저 바꾼 뒤)
-- 리허설  : 파일 끝의 COMMIT 을 ROLLBACK 으로 바꿔 실행한다.
-- =============================================================================

BEGIN;

DO $$ BEGIN
    CREATE TYPE sslcerttypeenum AS ENUM ('LEAF', 'CA');
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

CREATE TABLE IF NOT EXISTS mw_ssl_cert_file (
    id            SERIAL NOT NULL,
    cert_name     VARCHAR(30) NOT NULL,
    ag_file_id    INTEGER,
    file_name     VARCHAR(50) NOT NULL,
    received_date DATE NOT NULL,
    receiver_name VARCHAR(50) NOT NULL,
    cert_type     sslcerttypeenum NOT NULL,
    subject       VARCHAR(300),
    cn            VARCHAR(200),
    serial        VARCHAR(100),
    issuer        VARCHAR(300),
    notbefore     TIMESTAMP WITHOUT TIME ZONE,
    notafter      TIMESTAMP WITHOUT TIME ZONE,
    user_id       VARCHAR(50) NOT NULL,
    create_on     TIMESTAMP WITHOUT TIME ZONE NOT NULL,
    PRIMARY KEY (id),
    UNIQUE (cert_name),
    FOREIGN KEY (ag_file_id) REFERENCES ag_file (id) ON DELETE SET NULL
);

COMMENT ON TABLE  mw_ssl_cert_file               IS 'SSL 인증서 파일 (HOWTO_021)';
COMMENT ON COLUMN mw_ssl_cert_file.id            IS 'Primary Key';
COMMENT ON COLUMN mw_ssl_cert_file.cert_name     IS '이름 (UTF-8 30byte 이내)';
COMMENT ON COLUMN mw_ssl_cert_file.ag_file_id    IS '원본 파일';
COMMENT ON COLUMN mw_ssl_cert_file.file_name     IS '등록 시점의 파일 이름';
COMMENT ON COLUMN mw_ssl_cert_file.received_date IS '접수일';
COMMENT ON COLUMN mw_ssl_cert_file.receiver_name IS '접수자 이름';
COMMENT ON COLUMN mw_ssl_cert_file.cert_type     IS 'Leaf/중간 CA';
COMMENT ON COLUMN mw_ssl_cert_file.subject       IS '주제';
COMMENT ON COLUMN mw_ssl_cert_file.cn            IS 'CN';
COMMENT ON COLUMN mw_ssl_cert_file.serial        IS '일련번호';
COMMENT ON COLUMN mw_ssl_cert_file.issuer        IS '발급자';
COMMENT ON COLUMN mw_ssl_cert_file.notbefore     IS '유효기간시작';
COMMENT ON COLUMN mw_ssl_cert_file.notafter      IS '유효기간만료';

\echo '--- 적용 후'
\d mw_ssl_cert_file

COMMIT;
