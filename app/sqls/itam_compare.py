"""
ITAM 대사(Compare) 로직
- ITAM 기준 대사 (it_was, it_web → mw_was, mw_web)
- 미들웨어관리소 기준 대사 (mw_was, mw_web → it_was, it_web)
"""
from app import db
from sqlalchemy import func, and_, or_
from datetime import datetime, timedelta
import logging

from app.models.itam import (
    ItWas, ItWeb,
    ItItamWasCompare, ItItamWebCompare,
    ItLeebalsoWasCompare, ItLeebalsoWebCompare
)
from app.models.was import MwWas, MwWeb, MwWasHttpListener, MwServer
from app.models.agent import AgAgent
from app.models.common import LocationEnum, YnEnum, BuiltEnum

log = logging.getLogger(__name__)

# ============================================================
# 데이터 변환 유틸
# ============================================================

RUN_ENV_TO_LOCATION = {
    "운영": "PROD",
    "이관": "TEST",
    "개발": "DEV",
    "DR":   "DR",
}

LOCATION_TO_RUN_ENV = {v: k for k, v in RUN_ENV_TO_LOCATION.items()}


def run_env_to_location(run_env):
    """ITAM run_env를 LocationEnum name으로 변환"""
    return RUN_ENV_TO_LOCATION.get(run_env)


def location_to_run_env(location_name):
    """LocationEnum name을 ITAM run_env로 변환"""
    return LOCATION_TO_RUN_ENV.get(location_name)


def _ssl_yn_matches(itam_ssl_yn, leebalso_ssl_yn):
    """ITAM ssl_yn('Y'/'N')과 미들웨어관리소 ssl_yn('YES'/'NO') 비교"""
    if itam_ssl_yn == 'Y' and leebalso_ssl_yn == 'YES':
        return True
    if itam_ssl_yn != 'Y' and leebalso_ssl_yn != 'YES':
        return True
    return False


def _is_agent_inactive(agent_id):
    """Agent 비활성화 여부 (last_checked_date가 5분 이상 경과)"""
    if not agent_id:
        return False  # Agent 없음은 별도 오류로 처리

    agent = db.session.query(AgAgent).filter(
        AgAgent.agent_id == agent_id
    ).first()

    if not agent or not agent.last_checked_date:
        return True

    gap = datetime.now() - agent.last_checked_date
    return gap > timedelta(minutes=5)


def _get_valid_host_ids():
    """사용중인 서버의 host_id 집합"""
    rows = db.session.query(MwServer.host_id).filter(
        MwServer.use_yn == YnEnum.YES
    ).all()
    return {r.host_id for r in rows}


def _clean_port(port_str):
    """포트 문자열 정리 (Excel에서 float으로 읽힌 '15843.0' → '15843')"""
    if not port_str:
        return None
    port_str = str(port_str).strip()
    if port_str.endswith('.0'):
        port_str = port_str[:-2]
    return port_str


def _get_cleaned_was_id(was_id):
    """미들웨어관리소 was_id에서 특정 접미사(_dev, _test, _A, _L, _N) 제거"""
    if not was_id:
        return was_id
    suffixes = ['_dev', '_test', '_A', '_L', '_N']
    for suffix in suffixes:
        if was_id.endswith(suffix):
            return was_id[:-len(suffix)]
    return was_id


# ============================================================
# 1-1. ITAM WAS 기준 대사
# ============================================================

def _get_itam_was_filtered():
    """ITAM WAS 필터링 + 그룹핑 결과 반환
    
    Returns:
        list of dict: 그룹핑된 대표 레코드 목록
        각 dict는 {config_id, host_id, run_env, domain_name, config_name,
                   install_user, was_ssl_yn, os_type} 포함
    """
    records = db.session.query(ItWas).filter(
        ItWas.config_status != '불용',
        ItWas.run_env.in_(['운영', '이관', '개발']),
        ~ItWas.config_name.like('%(S)%'),
        ~ItWas.install_user.like('tmax%')
    ).order_by(ItWas.run_env, ItWas.domain_name, ItWas.host_id).all()

    # (run_env, domain_name)으로 그룹핑, host_id 알파벳순 첫번째가 대표
    grouped = {}
    for rec in records:
        key = (rec.run_env, rec.domain_name)
        if key not in grouped:
            grouped[key] = rec  # 이미 host_id 순으로 정렬됨

    return list(grouped.values())


def compare_itam_was(config_id=None):
    """ITAM WAS 기준 대사 실행
    
    Args:
        config_id: 특정 config_id만 대사 (None이면 전체)
    
    Returns:
        list of ItItamWasCompare
    """
    results = []
    valid_hosts = _get_valid_host_ids()

    if config_id:
        records = db.session.query(ItWas).filter(
            ItWas.config_id == config_id
        ).all()
    else:
        records = _get_itam_was_filtered()

    for rec in records:
        # 1) hostname 미등록
        if rec.host_id and str(rec.host_id).lower() not in valid_hosts:
            results.append(ItItamWasCompare(
                config_id=rec.config_id,
                error_type='hostname 미등록',
                error_content=f'host_id={rec.host_id}가 mw_server(use_yn=YES)에 미등록'
            ))
            continue  # hostname이 없으면 이후 비교 불가

        # LocationEnum 변환
        location_name = run_env_to_location(rec.run_env)
        if not location_name:
            results.append(ItItamWasCompare(
                config_id=rec.config_id,
                error_type='WAS 미등록',
                error_content=f'run_env={rec.run_env}에 대응하는 landscape 없음'
            ))
            continue

        # 2) WAS 미등록 (host_id + cleaned was_id 비교)
        # 서버(host_id)를 조건에 포함하여, 서버가 다르면 조회되지 않게 함 (미등록 처리)
        mw_was_rec = db.session.query(MwWas).filter(
            MwWas.landscape == LocationEnum[location_name],
            MwWas.located_host_id == (str(rec.host_id).lower() if rec.host_id else None),
            or_(
                MwWas.was_id == rec.domain_name,
                MwWas.was_id == rec.domain_name + '_dev',
                MwWas.was_id == rec.domain_name + '_test',
                MwWas.was_id == rec.domain_name + '_A',
                MwWas.was_id == rec.domain_name + '_L',
                MwWas.was_id == rec.domain_name + '_N'
            )
        ).first()

        if not mw_was_rec:
            results.append(ItItamWasCompare(
                config_id=rec.config_id,
                error_type='WAS 미등록',
                error_content=f'domain_name={rec.domain_name}, host_id={rec.host_id}, run_env={rec.run_env} 가 mw_was에 미등록'
            ))
            continue

        # 3) WAS SSL 불일치
        has_ssl_listener = db.session.query(MwWasHttpListener).filter(
            MwWasHttpListener.was_id == mw_was_rec.was_id,
            MwWasHttpListener.ssl_yn == YnEnum.YES
        ).first() is not None

        expected_ssl = 'Y' if has_ssl_listener else 'N'
        actual_ssl = rec.was_ssl_yn if rec.was_ssl_yn else 'N'
        if actual_ssl != expected_ssl:
            results.append(ItItamWasCompare(
                config_id=rec.config_id,
                error_type='WAS SSL 불일치',
                error_content=f'ITAM was_ssl_yn={actual_ssl}, 미들웨어관리소 SSL listener 존재={has_ssl_listener} (기대값={expected_ssl})'
            ))

        # 4) Agent 없음
        if not mw_was_rec.agent_id or mw_was_rec.agent_id.strip() == '':
            results.append(ItItamWasCompare(
                config_id=rec.config_id,
                error_type='Agent 없음',
                error_content=f'mw_was.was_id={mw_was_rec.was_id}에 agent_id 미설정'
            ))
        else:
            # 5) Agent 비활성화
            if _is_agent_inactive(mw_was_rec.agent_id):
                results.append(ItItamWasCompare(
                    config_id=rec.config_id,
                    error_type='Agent 비활성화',
                    error_content=f'agent_id={mw_was_rec.agent_id}의 last_checked_date가 5분 이상 경과'
                ))

    return results


# ============================================================
# 1-2. ITAM 내장WEB 기준 대사
# ============================================================

def compare_itam_embed_web(config_id=None):
    """ITAM 내장WEB 기준 대사 실행
    
    Args:
        config_id: 특정 config_id만 대사 (None이면 전체)
    
    Returns:
        list of ItItamWasCompare (it_was 기반이므로 같은 테이블)
    """
    results = []

    if config_id:
        records = db.session.query(ItWas).filter(
            ItWas.config_id == config_id,
            ItWas.embed_web_yn == 'Y'
        ).all()
    else:
        records = db.session.query(ItWas).filter(
            ItWas.config_status != '불용',
            ItWas.run_env.in_(['운영', '이관', '개발']),
            ~ItWas.config_name.like('%(S)%'),
            ItWas.embed_web_yn == 'Y'
        ).all()

    for rec in records:
        # 1) 내장 WEB 미등록 (host_id + domain_name으로 매핑, 포트 비교 제외)
        mw_web_rec = db.session.query(MwWeb).join(MwWeb.mw_was).filter(
            MwWeb.host_id == (str(rec.host_id).lower() if rec.host_id else None),
            MwWeb.built_type == BuiltEnum.Internal,
            or_(
                MwWas.was_id == rec.domain_name,
                MwWas.was_id == rec.domain_name + '_dev',
                MwWas.was_id == rec.domain_name + '_test',
                MwWas.was_id == rec.domain_name + '_A',
                MwWas.was_id == rec.domain_name + '_L',
                MwWas.was_id == rec.domain_name + '_N'
            )
        ).first()

        if not mw_web_rec:
            results.append(ItItamWasCompare(
                config_id=rec.config_id,
                error_type='내장 WEB 미등록',
                error_content=f'host_id={rec.host_id}, domain_name={rec.domain_name}에 대응하는 내장형 mw_web 없음'
            ))
            continue

        # 2) 내장 WEB SSL 여부 불일치
        leebalso_ssl = mw_web_rec.t__ssl_yn()  # 'YES' or 'NO'
        itam_ssl = rec.embed_web_ssl_yn if rec.embed_web_ssl_yn else 'N'
        if not _ssl_yn_matches(itam_ssl, leebalso_ssl):
            results.append(ItItamWasCompare(
                config_id=rec.config_id,
                error_type='내장 WEB SSL 여부 불일치',
                error_content=f'ITAM embed_web_ssl_yn={itam_ssl}, 미들웨어관리소 ssl_yn={leebalso_ssl}'
            ))

        # 3) 운용환경 불일치
        location_name = run_env_to_location(rec.run_env)
        if location_name and mw_web_rec.landscape:
            if mw_web_rec.landscape.name != location_name:
                results.append(ItItamWasCompare(
                    config_id=rec.config_id,
                    error_type='운용환경 불일치',
                    error_content=f'ITAM run_env={rec.run_env}({location_name}), 미들웨어관리소 landscape={mw_web_rec.landscape.name}'
                ))

        # 4) 내장 웹 구분 이상
        if mw_web_rec.built_type != BuiltEnum.Internal:
            built_val = mw_web_rec.built_type.value if mw_web_rec.built_type else 'None'
            results.append(ItItamWasCompare(
                config_id=rec.config_id,
                error_type='내장 웹 구분 이상',
                error_content=f'mw_web.built_type={built_val} (기대값=내장)'
            ))

        # 5) WAS Domain 이상
        # 5) WAS Domain 이상
        parent_was_id = mw_web_rec.mw_was[0].was_id if mw_web_rec.mw_was else ""
        if rec.domain_name != _get_cleaned_was_id(parent_was_id):
            results.append(ItItamWasCompare(
                config_id=rec.config_id,
                error_type='WAS Domain 이상',
                error_content=f'ITAM domain_name={rec.domain_name}, 미들웨어관리소 WAS={parent_was_id}'
            ))

    return results


# ============================================================
# 1-3. ITAM WEB 기준 대사
# ============================================================

def compare_itam_web(config_id=None):
    """ITAM WEB 기준 대사 실행
    
    Args:
        config_id: 특정 config_id만 대사 (None이면 전체)
    
    Returns:
        list of ItItamWebCompare
    """
    results = []
    valid_hosts = _get_valid_host_ids()

    if config_id:
        records = db.session.query(ItWeb).filter(
            ItWeb.config_id == config_id
        ).all()
    else:
        records = db.session.query(ItWeb).filter(
            ItWeb.config_status != '불용',
            ItWeb.run_env.in_(['운영', '이관', '개발']),
            ~ItWeb.config_name.like('%(S)%')
        ).all()

    for rec in records:
        # 1) hostname 미등록
        if rec.host_id and str(rec.host_id).lower() not in valid_hosts:
            results.append(ItItamWebCompare(
                config_id=rec.config_id,
                error_type='hostname 미등록',
                error_content=f'host_id={rec.host_id}가 mw_server(use_yn=YES)에 미등록'
            ))
            continue

        port_str = _clean_port(rec.node_port)
        if not port_str:
            continue
        try:
            port_int = int(port_str)
        except (ValueError, TypeError):
            results.append(ItItamWebCompare(
                config_id=rec.config_id,
                error_type='WEB 미등록',
                error_content=f'node_port={port_str}가 유효하지 않음'
            ))
            continue

        # 2) WEB 미등록
        mw_web_rec = db.session.query(MwWeb).filter(
            MwWeb.host_id == (str(rec.host_id).lower() if rec.host_id else None),
            MwWeb.port == port_int
        ).first()

        if not mw_web_rec:
            results.append(ItItamWebCompare(
                config_id=rec.config_id,
                error_type='WEB 미등록',
                error_content=f'host_id={rec.host_id}, node_port={port_str}가 mw_web에 미등록'
            ))
            continue

        # 3) WEB SSL 여부 불일치
        leebalso_ssl = mw_web_rec.t__ssl_yn()  # 'YES' or 'NO'
        itam_ssl = rec.ssl_yn if rec.ssl_yn else 'N'
        if not _ssl_yn_matches(itam_ssl, leebalso_ssl):
            results.append(ItItamWebCompare(
                config_id=rec.config_id,
                error_type='WEB SSL 여부 불일치',
                error_content=f'ITAM ssl_yn={itam_ssl}, 미들웨어관리소 ssl_yn={leebalso_ssl}'
            ))

        # 4) 운용환경 불일치
        location_name = run_env_to_location(rec.run_env)
        if location_name and mw_web_rec.landscape:
            if mw_web_rec.landscape.name != location_name:
                results.append(ItItamWebCompare(
                    config_id=rec.config_id,
                    error_type='운용환경 불일치',
                    error_content=f'ITAM run_env={rec.run_env}({location_name}), 미들웨어관리소 landscape={mw_web_rec.landscape.name}'
                ))

        # 5) Agent 없음
        if not mw_web_rec.agent_id or mw_web_rec.agent_id.strip() == '':
            results.append(ItItamWebCompare(
                config_id=rec.config_id,
                error_type='Agent 없음',
                error_content=f'mw_web host_id={mw_web_rec.host_id}, port={mw_web_rec.port}에 agent_id 미설정'
            ))
        else:
            # 6) Agent 비활성화
            if _is_agent_inactive(mw_web_rec.agent_id):
                results.append(ItItamWebCompare(
                    config_id=rec.config_id,
                    error_type='Agent 비활성화',
                    error_content=f'agent_id={mw_web_rec.agent_id}의 last_checked_date가 5분 이상 경과'
                ))

    return results


# ============================================================
# 2-1. 미들웨어관리소 WAS 기준 대사
# ============================================================

def compare_leebalso_was(was_id=None):
    """미들웨어관리소 WAS 기준 대사 실행
    
    Args:
        was_id: mw_was.id (None이면 전체)
    
    Returns:
        list of ItLeebalsoWasCompare
    """
    results = []

    if was_id:
        records = db.session.query(MwWas).filter(MwWas.id == was_id).all()
    else:
        records = db.session.query(MwWas).filter(
            MwWas.use_yn == YnEnum.YES
        ).all()

    for rec in records:
        # ITAM 미등록 체크
        if not rec.landscape:
            results.append(ItLeebalsoWasCompare(
                leebalso_id=rec.id,
                error_type='ITAM 미등록',
                error_content=f'was_id={rec.was_id}의 landscape가 미설정'
            ))
            continue

        run_env = location_to_run_env(rec.landscape.name)
        if not run_env:
            results.append(ItLeebalsoWasCompare(
                leebalso_id=rec.id,
                error_type='ITAM 미등록',
                error_content=f'was_id={rec.was_id}, landscape={rec.landscape.name}에 대응하는 run_env 없음'
            ))
            continue

        # ITAM 미등록 체크 (host_id + cleaned was_id 비교, 불용 제외)
        itam_exists = db.session.query(ItWas).filter(
            func.lower(ItWas.host_id) == str(rec.located_host_id).lower(),
            ItWas.domain_name == _get_cleaned_was_id(rec.was_id),
            ItWas.run_env == run_env,
            ItWas.config_status != '불용'
        ).first()

        if not itam_exists:
            results.append(ItLeebalsoWasCompare(
                leebalso_id=rec.id,
                error_type='ITAM 미등록',
                error_content=f'host_id={rec.located_host_id}, was_id={rec.was_id} (cleaned={_get_cleaned_was_id(rec.was_id)}), landscape={rec.landscape.name}({run_env})가 it_was에 미등록 또는 불용 상태'
            ))

    return results


# ============================================================
# 2-2. 미들웨어관리소 내장WEB 기준 대사
# ============================================================

def compare_leebalso_embed_web(web_id=None):
    """미들웨어관리소 내장WEB 기준 대사 실행
    
    Args:
        web_id: mw_web.id (None이면 전체)
    
    Returns:
        list of ItLeebalsoWebCompare
    """
    results = []

    if web_id:
        records = db.session.query(MwWeb).filter(MwWeb.id == web_id).all()
    else:
        records = db.session.query(MwWeb).filter(
            MwWeb.use_yn == YnEnum.YES,
            MwWeb.built_type == BuiltEnum.Internal
        ).all()

    for rec in records:
        # ITAM 미등록 체크 (host_id + cleaned was_id 비교, 포트/불용 제외)
        parent_was_id = rec.mw_was[0].was_id if rec.mw_was else ""
        itam_exists = db.session.query(ItWas).filter(
            func.lower(ItWas.host_id) == str(rec.host_id).lower(), 
            ItWas.domain_name == _get_cleaned_was_id(parent_was_id),
            ItWas.embed_web_yn == 'Y',
            ItWas.config_status != '불용'
        ).first()

        if not itam_exists:
            results.append(ItLeebalsoWebCompare(
                leebalso_id=rec.id,
                error_type='ITAM 미등록',
                error_content=f'host_id={rec.host_id}, 미들웨어관리소 WAS={parent_was_id} 가 it_was(embed_web)에 미등록 또는 불용 상태'
            ))

    return results


# ============================================================
# 2-3. 미들웨어관리소 WEB 기준 대사
# ============================================================

def compare_leebalso_web(web_id=None):
    """미들웨어관리소 WEB(외장) 기준 대사 실행
    
    Args:
        web_id: mw_web.id (None이면 전체)
    
    Returns:
        list of ItLeebalsoWebCompare
    """
    results = []

    if web_id:
        records = db.session.query(MwWeb).filter(MwWeb.id == web_id).all()
    else:
        records = db.session.query(MwWeb).filter(
            MwWeb.use_yn == YnEnum.YES,
            MwWeb.built_type != BuiltEnum.Internal
        ).all()

    for rec in records:
        # ITAM 미등록 체크 (불용 제외)
        itam_exists = db.session.query(ItWeb).filter(
            func.lower(ItWeb.host_id) == str(rec.host_id).lower(), # rec는 미들웨어관리소지만 안전을 위해 lower
            ItWeb.node_port == str(rec.port),
            ItWeb.config_status != '불용'
        ).first()

        if not itam_exists:
            results.append(ItLeebalsoWebCompare(
                leebalso_id=rec.id,
                error_type='ITAM 미등록',
                error_content=f'host_id={rec.host_id}, port={rec.port}(외장)가 it_web에 미등록 또는 불용 상태'
            ))

    return results


# ============================================================
# 일괄 대사 실행
# ============================================================

def run_all_compare():
    """6가지 대사를 모두 실행하고 결과를 DB에 저장
    
    Returns:
        dict: 각 대사 유형별 결과 건수
    """
    try:
        # 1. 기존 대사 결과 전체 삭제
        db.session.query(ItItamWasCompare).delete()
        db.session.query(ItItamWebCompare).delete()
        db.session.query(ItLeebalsoWasCompare).delete()
        db.session.query(ItLeebalsoWebCompare).delete()

        # 2. 대사 실행
        itam_was_results = compare_itam_was()
        itam_embed_web_results = compare_itam_embed_web()
        itam_web_results = compare_itam_web()
        leebalso_was_results = compare_leebalso_was()
        leebalso_embed_web_results = compare_leebalso_embed_web()
        leebalso_web_results = compare_leebalso_web()

        # 3. 결과 저장
        for r in itam_was_results:
            db.session.add(r)
        for r in itam_embed_web_results:
            db.session.add(r)
        for r in itam_web_results:
            db.session.add(r)
        for r in leebalso_was_results:
            db.session.add(r)
        for r in leebalso_embed_web_results:
            db.session.add(r)
        for r in leebalso_web_results:
            db.session.add(r)

        db.session.commit()

        summary = {
            'itam_was': len(itam_was_results),
            'itam_embed_web': len(itam_embed_web_results),
            'itam_web': len(itam_web_results),
            'leebalso_was': len(leebalso_was_results),
            'leebalso_embed_web': len(leebalso_embed_web_results),
            'leebalso_web': len(leebalso_web_results),
            'total': (len(itam_was_results) + len(itam_embed_web_results)
                     + len(itam_web_results) + len(leebalso_was_results)
                     + len(leebalso_embed_web_results) + len(leebalso_web_results))
        }
        log.info(f"ITAM 대사 완료: {summary}")
        return summary

    except Exception as e:
        db.session.rollback()
        log.error(f"ITAM 대사 실행 중 오류: {str(e)}")
        raise


# ============================================================
# 단건 대사 실행
# ============================================================

def compare_single_itam_was(config_id):
    """특정 ITAM WAS config_id에 대한 대사 실행 (WAS + 내장WEB)"""
    try:
        # 기존 결과 삭제
        db.session.query(ItItamWasCompare).filter(
            ItItamWasCompare.config_id == config_id
        ).delete()

        # 대사 실행
        was_results = compare_itam_was(config_id=config_id)
        embed_results = compare_itam_embed_web(config_id=config_id)

        for r in was_results + embed_results:
            db.session.add(r)

        db.session.commit()
        return len(was_results) + len(embed_results)

    except Exception as e:
        db.session.rollback()
        log.error(f"단건 ITAM WAS 대사 오류 (config_id={config_id}): {str(e)}")
        raise


def compare_single_itam_web(config_id):
    """특정 ITAM WEB config_id에 대한 대사 실행"""
    try:
        db.session.query(ItItamWebCompare).filter(
            ItItamWebCompare.config_id == config_id
        ).delete()

        results = compare_itam_web(config_id=config_id)

        for r in results:
            db.session.add(r)

        db.session.commit()
        return len(results)

    except Exception as e:
        db.session.rollback()
        log.error(f"단건 ITAM WEB 대사 오류 (config_id={config_id}): {str(e)}")
        raise


def compare_single_leebalso_was(was_id):
    """특정 미들웨어관리소 WAS id에 대한 대사 실행"""
    try:
        db.session.query(ItLeebalsoWasCompare).filter(
            ItLeebalsoWasCompare.leebalso_id == was_id
        ).delete()

        results = compare_leebalso_was(was_id=was_id)

        for r in results:
            db.session.add(r)

        db.session.commit()
        return len(results)

    except Exception as e:
        db.session.rollback()
        log.error(f"단건 미들웨어관리소 WAS 대사 오류 (was_id={was_id}): {str(e)}")
        raise


def compare_single_leebalso_web(web_id):
    """특정 미들웨어관리소 WEB id에 대한 대사 실행"""
    try:
        db.session.query(ItLeebalsoWebCompare).filter(
            ItLeebalsoWebCompare.leebalso_id == web_id
        ).delete()

        # 내장/외장 판별
        mw_web_rec = db.session.query(MwWeb).filter(MwWeb.id == web_id).first()
        if not mw_web_rec:
            db.session.commit()
            return 0

        if mw_web_rec.built_type == BuiltEnum.Internal:
            results = compare_leebalso_embed_web(web_id=web_id)
        else:
            results = compare_leebalso_web(web_id=web_id)

        for r in results:
            db.session.add(r)

        db.session.commit()
        return len(results)

    except Exception as e:
        db.session.rollback()
        log.error(f"단건 미들웨어관리소 WEB 대사 오류 (web_id={web_id}): {str(e)}")
        raise
