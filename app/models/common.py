from flask import g
import enum
import uuid
from datetime import datetime

class LocationEnum(enum.Enum):
    PROD = 'PROD'
    TEST = 'TEST'
    DEV  = 'DEV'
    DR   = 'DR'

class OSEnum(enum.Enum):
    AIX     = 'AIX'
    LINUX   = 'LINUX'
    WINDOWS = 'WINDOWS'
    HPUX    = 'HP-UX'
    ETC     = 'ETC'
    LINUX_REDHAT   = 'LINUX-REDHAT'
    LINUX_ORACLE   = 'LINUX-ORACLE'
    LINUX_ROCKY   = 'LINUX-ROCKY'
    LINUX_CENTOS   = 'LINUX-CENTOS'
    LINUX_SOMANSAOS   = 'LINUX-SOMANSAOS'
    LINUX_OPENSUSE   = 'LINUX-OPENSUSE'
    LINUX_DEBIAN   = 'LINUX-DEBIAN'
    LINUX_UBUNTU   = 'LINUX-UBUNTU'
    SUNOS = 'SUNOS'

class YnEnum(enum.Enum):
    YES = 'YES'
    NO  = 'NO'

class RunEnum(enum.Enum):
    ACTIVE   = 'ACTIVE'
    STANDBY  = 'STANDBY'
    STANDALONE = 'Stand Alone'

class RuningTypeEnum(enum.Enum):
    AA   = 'A-A'
    AS   = 'A-S'
    SA   = 'StandAlone'

class SvrTypeEnum(enum.Enum):
    HTML     = 'HTML'
    JSV      = 'JSV'
    CGI      = 'CGI'
    SSI      = 'SSI'

class ApmEnum(enum.Enum):
    PHAROS   = 'PHAROS'
    JENNIFER = 'JENNIFER'
    NONE     = 'NONE'

class BuiltEnum(enum.Enum):
    External  = '외장'
    Internal  = '내장'
    Isolated  = '분리'

class WebconnEnum(enum.Enum):
    WEBTOB  = 'WEBTOB'
    HTTP    = 'HTTP'

class WarEnum(enum.Enum):
    WAR       = 'WAR'
    EAR       = 'EAR'
    JAR       = 'JAR'
    COMPONENT = 'COMPONENT'
    EXPLODED  = 'EXPLODED'
    
class EncodingEnum(enum.Enum):
    UTF_8  = 'UTF-8'
    EUC_KR = 'EUC-KR'
    UTF_16 = 'UTF-16'
    ANSI   = 'ANSI'
    CP949  = 'CP949'

class PeriodicTypeEnum(enum.Enum):
    IMMEDIATE = '즉시작업'
    ONETIME   = '1회성작업'
    PERIODIC  = '주기작업'

class AgentTypeEnum(enum.Enum):
    JAVAAGENT = 'Java Agent(JAVA8)'
    JAVAAGENT6 = 'Java Agent(JAVA6)'
    JAVAAGENT7 = 'Java Agent(JAVA7)'
    JAVAAGENT8_5 = 'Java Agent(JEUS8.5)'
    JAVAAGENT8_o = 'Java Agent(JEUS8.o)'
    WHEREAMI  = 'WhereAmI'
    SHIFTSIS  = 'Shift Sisters'


class SslCertTypeEnum(enum.Enum):
    LEAF = 'Leaf'
    CA = '중간 CA'


class AgentSubTypeEnum(enum.Enum):
    WIN_JEUS8  = 'WINDOWS & JEUS8'
    WIN_JEUS7  = 'WINDOWS & JEUS7'
    WIN_JEUS6  = 'WINDOWS & JEUS6'
    UNIX_JEUS6 = 'UNIX & JEUS6'
    UNIX_JEUS8 = 'UNIX & JEUS8'
    ETC        = 'ETC'

class CommandClassEnum(enum.Enum):
    ServerFunc     = '[서버내부기능]'
    ReadPlainFile  = '파일 Read'
    ReadFullPathFile = '파일 Read(파일 이름 후 지정)'
    ExeScript      = '프로그램 실행'
    ExeText        = '명령어 실행'
    ExeShell       = 'Shell 실행'
    ExeAgentFunc   = 'Agent기능 실행'
    DownloadFile   = 'File Download'
    UploadFile     = 'File Upload'
    GetRefreshToken= 'Update인증Token'
    ExtractLog     = 'Log Extractor'

class CommandStatusEnum(enum.Enum):
    CREATE     = 'Command 생성'
    SENDED     = 'Command 전달'
    COMPLITED  = 'Result 수신'
    FAILED     = 'Error 수신'
    MQTT       = 'MQTT로 전달'
    MQTT_FAILED = 'MQTT 전달 실패'

class TargetToSendEnum(enum.Enum):
    SERVER     = 'MW Server'
    # MQTT 선택 시 실행구분(periodic_type)은 IMMEDIATE 로 강제된다.
    # SERVER_N_MQTT 는 도입하지 않는다 - status 를 CREATE 로 두고 발행까지 하면
    # Agent 가 push 와 polling 으로 같은 명령을 2회 실행할 수 있다.
    MQTT       = 'MQTT (실시간)'

class WasInstanceStatusEnum(enum.Enum):
    RUNNING    = 'RUNNING'
    STANDBY    = 'STANDBY'
    SHUTDOWN   = 'SHUTDOWN'
    FAILED     = 'FAILED'

class AutorunTypeEnum(enum.Enum):
    COMMAND     = 'Command ID'
    FILENAME    = 'File명 또는 기능명'

"""
class AutorunFuncEnum(enum.Enum):
    updateJeusDomain = 'WAS 정보 등록'
    updateHttpm      = 'WEB 정보 등록'
    updateWebMain    = 'JEUS6 WEBMain 등록'
    updateWasStatus  = 'WAS 상태 등록'
    updateUrlRewrite = 'URL Rewrite 등록'
    readOutFile      = 'Shell실행 후 out 파일 읽기'
    readCIDOutFile   = 'Shell실행 후 out.CID 파일 읽기'
    updateConnectSSL = '(out파일)connectSSL 정보 등록'
    updateConnectSSLByAPI = 'connectSSL 정보 등록'
    update_file_SSL_byAPI = 'fileSSL 정보 등록'
    updateFileSSL    = '(out파일)fileSSL 정보 등록'
    restartMWAgent   = 'MWAgent 재시작'
    updateJeusLicenseInfo = 'Jeus License 정보 등록'
    updateWebtobLicenseInfo = 'Webtob License 정보 등록'
    updateJeusProperties = 'jeus.properties 파일 등록'
    updateWebtobVersion = 'webtob version 정보 등록'
    updateWebtobMonitor = 'webtob monitoring(si) 결과 등록'
    updateFilteredInfo = 'OS Find 명령 수행 결과 등록'
"""

class ResultStatusEnum(enum.Enum):
    FAILED     = 'Command수행실패'
    CREATE     = 'Result 생성'
    ERROR      = '업무반영중ERROR'
    NOCHANGE   = '변경없음'
    COMPLITED  = '업무반영완료'

class IntervalTypeEnum(enum.Enum):
    minutes    = 'minutes(분)'
    hours      = 'hours(시간)'
    days       = 'days(일)'

def get_user():
    try:
        from flask import has_request_context, g
        if has_request_context():
            # Check for various app types (e.g. Superset, FAB, or plain Flask)
            user = getattr(g, 'user', None)
            if user and hasattr(user, 'username'):
                return user.username
            if user and isinstance(user, str):
                return user
    except Exception:
        pass
    return 'batch'

def get_group():
    try:
        from flask import has_request_context
        if has_request_context() and g and hasattr(g, 'user') and g.user:
            return next((r.name for r in g.user.roles if '_role' in r.name),'')
    except Exception:
        pass
    return ''

def get_groups():
    try:
        from flask import has_request_context
        if has_request_context() and g and hasattr(g, 'user') and g.user:
            return [r.name for r in g.user.roles if '_role' in r.name]
    except Exception:
        pass
    return []

def get_date():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

def get_uuid():
    return str(uuid.uuid4())[-12:]

def getJsonButton(category, param, title):
    return '<button id="json-button" onclick="getJson(\''+ category +'\', \''+ param +'\');">'+ title +'</button>'

def getHtmlButton(table_name, column_name, tcolumn_name, key, title):
    return '<button id="html-button" onclick="getHtml(\''+ table_name +'\', \''+ column_name +'\', \''+ tcolumn_name +'\', \''+ key +'\');">'+ title +'</button>'

def getDiagramButton(category, param, title):
    return '<button id="dia-button" onclick="getChart(\''+ category +'\', \''+ param +'\');">'+ title +'</button>'

def getColoredText(obj):

    color_map = dict(
        BuiltEnum = {'External':'black', 'Internal':'green', 'Isolated':'blue'},
        ApmEnum = {'JENNIFER':'brown', 'PHAROS':'green', 'NONE':'white'},
        OSEnum = {'LINUX':'#966F33', 'AIX':'#0000A0', 'WINDOWS':'#357EC7', 'HPUX':'green'},
        LocationEnum = {'PROD':'red', 'DR':'brown', 'DEV':'blue', 'TEST':'green'},
        CommandStatusEnum = {'CREATE':'blue', 'SENDED':'brown', 'FAILED':'red', 'COMPLITED':'green','MQTT':'brown','MQTT_FAILED':'red'},
        ResultStatusEnum = {'CREATE':'blue', 'FAILED':'red', 'ERROR':'red', 'NOCHANGE':'#808080', 'COMPLITED':'green'}
    )
    try:
        color = color_map[obj.__class__.__name__][obj.name]
        text = '<p style="color:' + color + ';">' + obj.value + '</p>'
    except KeyError:
        text = '<p style="color:black;">' +  'Null' if obj is None else obj.value + '</p>'
    return text

def isNotNull(obj):
    
    if obj:
        text = '<p style="background-color:#E3E4FA;text-align:center"><b>YES</b></p>'
    else:
        text = '<p style="color:#B6B6B4;text-align:center">NO</P>'
    
    return text

def getTagValueWithType(ut_tag, tagtype):
    tag = getTagWithType(ut_tag, tagtype)
    result = tag.replace(tagtype+'-','')
    return result

def getTagWithType(ut_tag, tagtype):
    return next((t.tag for t in ut_tag if t.tag.startswith(tagtype)),'')