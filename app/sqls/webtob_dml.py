from app.models.common import get_user
from app.models.common import get_user
from abc import ABC, abstractmethod
import ast
import logging
import re
from flask import g
from app import appbuilder, db
from datetime import datetime
from sqlalchemy import select, delete, null, text, tuple_
from sqlalchemy.dialects.postgresql import insert
from app.models.was import MwServer, MwWas, MwWasInstance, MwWeb, MwWebVhost, MwWasHttpListener\
    , MwWasWebtobConnector, MwWebReverseproxy, MwDatasource, MwApplication, MwWebUri, MwWebServer\
    , MwWebDomain, MwWebSsl
from app.sqls.was import get_landscape
from .relationship import update_was_web_relation, get_web_servers
from app.api.errors import internal_error_message
from app.log_safe import log_safe

class WebtobHttpm(ABC):

    def __init__(self, host_id, httpm, raw_data, sys_user="", domain_id="", agent_id=""):
        self.host_id   = host_id
        self.port      = 0
        self.httpm     = httpm
        self.raw_data  = raw_data        
        self.sys_user  = sys_user
        self.agent_id  = agent_id
        self.landscape = ''
        self.dependent_was_id = domain_id
        self.node      = {}
        self.ssl       = []
        self.proxy_ssl = []
        self.vhosts    = []
        self.servers   = []
        self.server_groups = []
        self.reverse_proxy = []
        self.uris      = []
        self.logging   = []
        self.errordocument = []
        self.ext       = []
        self.tcpgw     = []
        self.mw_web_id = None
        
        self._setSubGroup()

    @abstractmethod
    def _setSubGroup(self):
        
        self.node = self.httpm['NODE'][0] if self.httpm.get('NODE') and len(self.httpm['NODE']) > 0 else {}
        self.ssl       = self.httpm['SSL'] if self.httpm.get('SSL') else []
        self.proxy_ssl = self.httpm['PROXY_SSL'] if self.httpm.get('PROXY_SSL') else []
        self.vhosts    = self.httpm['VHOST'] if self.httpm.get('VHOST') else []
        self.servers   = self.httpm['SERVER'] if self.httpm.get('SERVER') else []
        self.server_groups = self.httpm['SVRGROUP']\
                             if self.httpm.get('SVRGROUP') else []
        self.reverse_proxy = self.httpm['REVERSE_PROXY']\
                             if self.httpm.get('REVERSE_PROXY') else []
        self.uris      = self.httpm['URI'] if self.httpm.get('URI') else []
        self.logging   = self.httpm['LOGGING'] if self.httpm.get('LOGGING') else []
        self.errordocument = self.httpm['ERRORDOCUMENT']\
                             if self.httpm.get('ERRORDOCUMENT') else []
        self.ext       = self.httpm['EXT'] if self.httpm.get('EXT') else []
        self.tcpgw     = self.httpm['TCPGW'] if self.httpm.get('TCPGW') else []        

    def upsertWebtobHttpm(self):

        if not self.node:
             return -1, "Invalid configuration: NODE section not found in http.m text."

        # 
        self.landscape = get_landscape(self.host_id)

        if self.landscape is None:
            error_msg = f"Host '{self.host_id}' not found in MwServer. Please register the server first."
            logging.error(f"mwm upsertWebtobHttpm Error: {log_safe(error_msg)}")
            return -10, error_msg

        try:
            # Upsert mw_web
            _, insert_dict, update_dict = self.__getDictOfWeb()

            # Protection for Isolated status
            rec = db.session.query(MwWeb).filter(MwWeb.host_id == self.host_id, MwWeb.port == self.port).first()
            if rec and rec.built_type and rec.built_type.name == 'Isolated' and update_dict.get('built_type') == 'External':
                del update_dict['built_type']

            stmt = insert(MwWeb).values(insert_dict)    
            do_update_stmt = stmt.on_conflict_do_update(
                index_elements=['host_id', 'port'],
                set_=update_dict
            ).returning(MwWeb.id)
            rtn = db.session.execute(do_update_stmt)

            self.mw_web_id = next(rec[0] for rec in rtn)
            
            # Upsert mw_web_server
            _, insert_array, update_array \
                = self.__getArrayDictOfWebServer()

            svr_id_list = []
            for insert_dict, update_dict in zip(insert_array, update_array):
                svr_id_list.append(insert_dict['svr_id'])
                stmt = insert(MwWebServer).values(insert_dict)    
                do_update_stmt = stmt.on_conflict_do_update(
                    index_elements=['mw_web_id', 'svr_id'],
                    set_=update_dict
                )
                db.session.execute(do_update_stmt)
            
            # 현재 설정에 없는 서버 정보는 삭제 처리
            delete_stmt = delete(MwWebServer).where(
                    (MwWebServer.mw_web_id == self.mw_web_id),
                    ~MwWebServer.svr_id.in_(svr_id_list)
            )
            db.session.execute(delete_stmt)
            
            db.session.flush()
            logging.info(f"mwm: Upserted web servers for web_id={self.mw_web_id}. Starting relation update.")

            # WAS 커넥터 물리 연결 및 WAS-WEB 관계 갱신
            update_was_web_relation(web_id=self.mw_web_id)

            # Upsert mw_web_uri
            _, insert_array, update_array \
                = self.__getArrayDictOfWebUri()

            uri_id_list = []
            for insert_dict, update_dict in zip(insert_array, update_array):
                uri_id_list.append(insert_dict['uri_id'])
                stmt = insert(MwWebUri).values(insert_dict)    
                do_update_stmt = stmt.on_conflict_do_update(
                    index_elements=['mw_web_id', 'uri_id'],
                    set_=update_dict
                )
                db.session.execute(do_update_stmt)

            # 현재 설정에 없는 URI 정보는 삭제 처리
            delete_stmt = delete(MwWebUri).where(
                    (MwWebUri.mw_web_id == self.mw_web_id),
                    ~MwWebUri.uri_id.in_(uri_id_list)
            )
            db.session.execute(delete_stmt)

            # Upsert mw_web_reverseproxy
            _, insert_array, update_array \
                = self.__getArrayDictOfWebReverseproxy()

            rp_id_list = []
            for insert_dict, update_dict in zip(insert_array, update_array):
                rp_id_list.append(insert_dict['reverseproxy_id'])
                stmt = insert(MwWebReverseproxy).values(insert_dict)    
                do_update_stmt = stmt.on_conflict_do_update(
                    index_elements=['mw_web_id', 'reverseproxy_id'],
                    set_=update_dict
                )
                db.session.execute(do_update_stmt)

            # 현재 설정에 없는 Reverse Proxy 정보는 삭제 처리
            delete_stmt = delete(MwWebReverseproxy).where(
                    (MwWebReverseproxy.mw_web_id == self.mw_web_id),
                    ~MwWebReverseproxy.reverseproxy_id.in_(rp_id_list)
            )
            db.session.execute(delete_stmt)

            # Upsert mw_web_vhost
            _, insert_array, update_array \
                = self.__getArrayDictOfWebVhost()

            vhost_id_list = []

            for insert_dict, update_dict in zip(insert_array, update_array):

                vhost_id_list.append(insert_dict['vhost_id'])

                stmt = insert(MwWebVhost).values(insert_dict)
                do_update_stmt = stmt.on_conflict_do_update(
                    index_elements=['mw_web_id', 'vhost_id'],
                    set_=update_dict
                )            
                db.session.execute(do_update_stmt)

            delete_stmt = delete(MwWebVhost).where(
                    (MwWebVhost.mw_web_id==self.mw_web_id) ,
                    ~MwWebVhost.vhost_id.in_(vhost_id_list)
            )
            logging.info(f"mwm MwWebVhost delete_stmt : {delete_stmt}")
            db.session.execute(delete_stmt)

            # insert/delete assoc_webserver_vhost
            self.__updateWebserver_Vhost()

            # insert/delete assoc_webserver_vhost
            self.__updateWeburi_Webserver()

            # insert/delete assoc_weburi_vhost
            self.__updateWeburi_Vhost()

            # insert/delete assoc_webreverseproxy_vhost
            self.__updateWebreverseproxy_Vhost()

            # insert/update MwWebSsl
            self.__updateSslInfo()

            # insert/update MwWebDomain
            self.__updateDomainNameInfo()

            return 1, 'OK'

        except Exception:
            db.session.rollback()
            return -1, internal_error_message("mwm upsertWebtobHttpm Exception")

    def __getDictOfWeb(self):

        update_dict, port = self._getDataOfWeb()
        update_dict.update(
            web_text = self.raw_data
        )

        insert_dict = update_dict.copy()
        insert_dict.update(
            host_id = self.host_id,
            port    = port
            )

        return 1, insert_dict, update_dict

    @abstractmethod
    def _getDataOfWeb(self):

        self.port = int(self.node['PORT'].split(',')[0])

        if self.node.get('LOGGING'):
            acc_dir = next((c['FILENAME'] for c in self.logging if self.node['LOGGING']==c['NAME']), null())
        else:
            acc_dir = null()

        update_dict = dict(
            jsv_port       = self.node.get('JSVPORT', 0),
            node_name      = self.node['NAME'],
            web_home       = self.node['WEBTOBDIR'] \
                            if self.node.get('WEBTOBDIR') else null(),
            doc_dir       = self.node['DOCROOT'] \
                            if self.node.get('DOCROOT') else null(),
            hth_count      = self.node['HTH'] \
                            if self.node.get('HTH') else null(),
            service_port   = self.node['PORT'] \
                            if self.node.get('PORT') else null(),
            landscape      = self.landscape,
            acc_dir        = acc_dir,
            ssl_object     = self.ssl ,
            proxy_ssl_object     = self.proxy_ssl ,
            logging_object       = self.logging ,
            errordocument_object = self.errordocument ,
            ext_object           = self.ext ,
            tcpgw_object         = self.tcpgw ,
            httpm_object         = self.httpm ,
            agent_id             = self.agent_id,
            user_id              = get_user(),
            create_on            = datetime.now()
        )

        if self.sys_user:
            update_dict['sys_user'] = self.sys_user

        web_home = update_dict.get('web_home', '')
        if web_home and 'webserver' in web_home:
            update_dict['built_type'] = 'Internal'

        return update_dict, self.port

    def __getArrayDictOfWebServer(self):

        update_array = []
        insert_array = []
        update_dict = {}
        insert_dict = {}
        
        for server in self.servers:

            update_dict, svr_id = self._getDataOfWebServer(server)

            insert_dict = update_dict.copy()
            insert_dict.update(
                        mw_web_id = self.mw_web_id,
                        svr_id    = svr_id
                        )

            update_array.append(update_dict)
            insert_array.append(insert_dict)        

        return 1, insert_array, update_array

    @abstractmethod
    def _getDataOfWebServer(self, server):

        svr_id = server['NAME']

        if server.get('REQUESTLEVELPING'):
            request_level_ping_yn = 'YES' if server['REQUESTLEVELPING'] in ['y','Y']\
                                    else 'NO'
        else:
            request_level_ping_yn = null()

        svr_type = next( sg['SVRTYPE'] for sg in self.server_groups if sg['NAME']==server['SVGNAME']).upper()

        update_dict = dict(
            max_proc_count  = server['MAXPROC'] if server.get('MAXPROC') else null(),
            min_proc_count  = server['MINPROC'] if server.get('MINPROC') else null(),
            svr_type        = svr_type,
            request_level_ping_yn = request_level_ping_yn,
            user_id         = get_user(),
            create_on       = datetime.now()
        )

        return update_dict, svr_id

    def __getArrayDictOfWebUri(self):

        update_array = []
        insert_array = []
        update_dict = {}
        insert_dict = {}
        
        for uri in self.uris:

            update_dict, uri_id = self._getDataOfWebUri(uri)

            insert_dict = update_dict.copy()
            insert_dict.update(
                        mw_web_id = self.mw_web_id,
                        uri_id    = uri_id
                        )

            update_array.append(update_dict)
            insert_array.append(insert_dict)        

        return 1, insert_array, update_array

    @abstractmethod
    def _getDataOfWebUri(self, uri):

        uri_id = uri['NAME']

        update_dict = dict(
            svr_type        = uri['SVRTYPE'] if uri.get('SVRTYPE') else null(),
            uri             = uri['URI'],
            user_id         = get_user(),
            create_on       = datetime.now()
        )

        return update_dict, uri_id

    def __getArrayDictOfWebReverseproxy(self):

        update_array = []
        insert_array = []
        update_dict = {}
        insert_dict = {}
        
        for rp in self.reverse_proxy:

            update_dict, reverseproxy_id = self._getDataOfWebReverseproxy(rp)

            insert_dict = update_dict.copy()
            insert_dict.update(
                        mw_web_id       = self.mw_web_id,
                        reverseproxy_id = reverseproxy_id
                        )

            update_array.append(update_dict)
            insert_array.append(insert_dict)        

        return 1, insert_array, update_array

    @abstractmethod
    def _getDataOfWebReverseproxy(self, rp):

        reverseproxy_id = rp['NAME']

        if rp.get('PROXYSSLFLAG'):
            ssl_yn = 'YES' if rp['PROXYSSLFLAG'] in ['y','Y'] else 'NO'
        else:
            ssl_yn = 'NO'

        update_dict = dict(
            context_path      = rp['PATHPREFIX'],
            target_ip_address = rp['SERVERADDRESS'].split(':')[0]\
                             if rp['SERVERADDRESS'].find(':') else rp['SERVERADDRESS'],
            target_port       = rp['SERVERADDRESS'].split(':')[1]\
                             if rp['SERVERADDRESS'].find(':') else null(),
            target_context_path  = rp['SERVERPATHPREFIX'],
            max_connection_count = rp['MAXWEBSOCKETCONNECTIONS']\
                             if rp.get('MAXWEBSOCKETCONNECTIONS') else null(),
            ssl_yn          = ssl_yn,
            user_id         = get_user(),
            create_on       = datetime.now()
        )

        return update_dict, reverseproxy_id

    def __getArrayDictOfWebVhost(self):

        update_array = []
        insert_array = []
        update_dict  = {}
        insert_dict  = {}
        
        for vhost in self.vhosts:

            update_dict, vhost_id = self._getDataOfWebVhost(vhost)

            insert_dict = update_dict.copy()
            insert_dict.update(
                        mw_web_id = self.mw_web_id,
                        vhost_id = vhost_id
                        )

            update_array.append(update_dict)
            insert_array.append(insert_dict)        

        return 1, insert_array, update_array

    @abstractmethod
    def _getDataOfWebVhost(self, vhost):

        vhost_id = vhost['NAME']

        if vhost.get('SSLFLAG'):
            ssl_yn = 'YES' if vhost['SSLFLAG'] in ['y','Y'] else 'NO'
            ssl_name = vhost['SSLNAME'] if vhost['SSLFLAG'] in ['y','Y'] else null()
        else:
            ssl_yn = 'NO'
            ssl_name = null()


        if vhost.get('URLREWRITE'):
            urlrewrite_yn = 'YES' if vhost['URLREWRITE'] in ['y','Y'] else 'NO'
            urlrewrite_config = vhost['URLREWRITECONFIG']

            if '${WEBTOBDIR}' in urlrewrite_config:
                urlrewrite_config = urlrewrite_config.replace('${WEBTOBDIR}', self.node['WEBTOBDIR'])
    
        else:
            urlrewrite_yn = 'NO'
            urlrewrite_config = null()

        if vhost.get('LOGGING'):
            # Logging 이 두개 이상일 경우
            if isinstance(vhost['LOGGING'], list):
                tmp = []
                for logging in vhost['LOGGING']:
                    tmp.append(next( c['FILENAME'] for c in self.logging if logging==c['NAME']))
                acc_dir = ','.join(tmp)
            else:
                acc_dir = next( c['FILENAME'] for c in self.logging if vhost['LOGGING']==c['NAME'])
        else:
            acc_dir = null()

        update_dict = dict(
            web_ports    = vhost['PORT'] if vhost.get('PORT') else null(),
            domain_name = ','.join(vhost['HOSTNAME']) if vhost.get('HOSTNAME') else null(),
            host_alias  = ','.join(vhost['HOSTALIAS']) if vhost.get('HOSTALIAS') else null(),
            doc_dir     = vhost['DOCROOT'] if vhost.get('DOCROOT') else null(),
            acc_dir     = acc_dir,
            ssl_yn      = ssl_yn,
            ssl_name    = ssl_name,
            urlrewrite_yn = urlrewrite_yn,
            urlrewrite_config = urlrewrite_config,
            user_id     = get_user(),
            create_on   = datetime.now()
        )

        return update_dict, vhost_id

    def __updateWebserver_Vhost(self):

        for vhost in self.vhosts:

            svr_ids, vhost_id\
                 = self._getDataOfWebserver_Vhost(vhost)

            if not svr_ids:
                continue

            vhost_rec = db.session.query(MwWebVhost)\
                    .filter(MwWebVhost.mw_web_id==self.mw_web_id\
                        , MwWebVhost.vhost_id==vhost_id).first()

            server_recs = db.session.query(MwWebServer)\
                    .filter(MwWebServer.mw_web_id==self.mw_web_id\
                        , MwWebServer.svr_id.in_(svr_ids)).all()

            vhost_rec.mw_web_server = server_recs

        return 1

    @abstractmethod
    def _getDataOfWebserver_Vhost(self, vhost):

        svgs = []    
        [ svgs.append(g['NAME']) for g in self.server_groups\
                 if g.get('VHOSTNAME') and vhost['NAME'] in g['VHOSTNAME']]
        
        if not svgs:
            return [], ""

        svr_ids = [ s['NAME'] for s in self.servers if s['SVGNAME'] in svgs ]

        vhost_id = vhost['NAME']

        return svr_ids, vhost_id

    def __updateWeburi_Webserver(self):

        for uri in self.uris:

            svr_ids = []
            if uri.get('LBSVGNAME'):
                svr_ids = [s['NAME'] for s in self.servers if s.get('SVGNAME') and s['SVGNAME'] == uri['LBSVGNAME']]
            elif uri.get('SVRNAME'):
                svr_ids = [uri['SVRNAME']]
            elif uri.get('VHOSTNAME'):

                vhosts = uri['VHOSTNAME']
                logging.info(f"__updateWeburi_Webserver uri vhosts : {uri['NAME']} {vhosts}")

                for v in vhosts:
                    svgs = []
                    [ svgs.append(g['NAME']) for g in self.server_groups\
                        if g.get('VHOSTNAME') and v in g['VHOSTNAME']]
                    
                    if svgs:
                        svr_ids += [ s['NAME'] for s in self.servers if s['SVGNAME'] in svgs ]
                svr_ids = list(set(svr_ids))
                logging.info(f"__updateWeburi_Webserver svr_ids : {svr_ids}")

            else:
                continue

            uri_rec = db.session.query(MwWebUri)\
                    .filter(MwWebUri.mw_web_id==self.mw_web_id\
                        , MwWebUri.uri_id==uri['NAME']).first()

            webserver_recs = db.session.query(MwWebServer)\
                    .filter(MwWebServer.mw_web_id==self.mw_web_id\
                        , MwWebServer.svr_id.in_(svr_ids)).all()

            uri_rec.mw_web_server = webserver_recs

        return 1

    def __updateWeburi_Vhost(self):

        for vhost in self.vhosts:

            uri_ids, vhost_id\
                 = self._getDataOfWeburi_Vhost(vhost)

            if not uri_ids:
                continue

            vhost_rec = db.session.query(MwWebVhost)\
                    .filter(MwWebVhost.mw_web_id==self.mw_web_id\
                        , MwWebVhost.vhost_id==vhost_id).first()

            uri_recs = db.session.query(MwWebUri)\
                    .filter(MwWebUri.mw_web_id==self.mw_web_id\
                        , MwWebUri.uri_id.in_(uri_ids)).all()

            vhost_rec.mw_web_uri = uri_recs

        return 1

    @abstractmethod
    def _getDataOfWeburi_Vhost(self, vhost):

        vhost_id = vhost['NAME']
        uri_ids = [ u['NAME'] for u in self.uris\
                 if u.get('VHOSTNAME') and vhost_id in u['VHOSTNAME']]

        return uri_ids, vhost_id

    def __updateWebreverseproxy_Vhost(self):

        for vhost in self.vhosts:

            reverseproxy_ids, vhost_id\
                 = self._getDataOfWebreverseproxy_Vhost(vhost)

            if not reverseproxy_ids:
                continue

            vhost_rec = db.session.query(MwWebVhost)\
                    .filter(MwWebVhost.mw_web_id==self.mw_web_id\
                        , MwWebVhost.vhost_id==vhost_id).first()

            reverseproxy_recs = db.session.query(MwWebReverseproxy)\
                    .filter(MwWebReverseproxy.mw_web_id==self.mw_web_id\
                        , MwWebReverseproxy.reverseproxy_id.in_(reverseproxy_ids)).all()

            vhost_rec.mw_web_reverseproxy = reverseproxy_recs

        return 1

    @abstractmethod
    def _getDataOfWebreverseproxy_Vhost(self, vhost):

        vhost_id = vhost['NAME']
        reverseproxy_ids = [ u['NAME'] for u in self.reverse_proxy if vhost_id in u['VHOSTNAME']]

        return reverseproxy_ids, vhost_id

    def __updateSslInfo(self):

        webInfo = {'host_id':self.host_id, 'port':self.port}

        _create_ssl_info(webInfo)

        return 1


    def __updateDomainNameInfo(self):

        webInfo = {'host_id':self.host_id, 'port':self.port}

        _create_domain_name_info(webInfo)

        return 1

def _parse_web_info(webInfo):
    """webInfo 를 dict 로. 문자열이면 **리터럴로만** 해석한다.

    스케줄러·배치 API 를 거치면 `"{'host_id': 'h1', 'port': '8080'}"` 같은 문자열로 온다.
    예전에는 eval() 해서 배치 API 로 임의 코드를 실행할 수 있었다 (CodeQL py/code-injection).
    """
    if isinstance(webInfo, dict):
        return webInfo
    try:
        wi = ast.literal_eval(webInfo)
    except (ValueError, SyntaxError, TypeError) as e:
        raise ValueError(f'webInfo must be a dict literal: {e}') from None
    if not isinstance(wi, dict):
        raise ValueError(f'webInfo must be a dict, got {type(wi).__name__}')
    return wi


def _create_domain_name_info(webInfo):

    if not webInfo:
        return 0, 'Parameters don\'t exist'

    try:
        wi = _parse_web_info(webInfo)
    except ValueError as e:
        return 0, str(e)

    web_rec = db.session.query(MwWeb)\
                .filter(MwWeb.host_id==wi['host_id'], MwWeb.port==wi['port'])\
                .first()

    if not web_rec:
        return 0, ''

    vhost_recs = db.session.query(MwWebVhost)\
                .filter(MwWebVhost.mw_web_id==web_rec.id).all()

    if not vhost_recs:
        return 0, ''

    for v in vhost_recs:

        domains = []
        if v.domain_name:
            domains += v.domain_name.split(',')
        if v.host_alias:
            domains += v.host_alias.split(',')

        domains = list(set(domains))
        ports = v.web_ports.replace(' ','').split(',')

        ssl_yn = 'NO'
        ssl_rec = None

        if v.ssl_yn and v.ssl_yn.name == 'YES':
            ssl_yn = 'YES'

            ssl_rec = db.session.query(MwWebSsl)\
                .filter(MwWebSsl.mw_web_id==web_rec.id\
                      , MwWebSsl.ssl_name==v.ssl_name\
                      ).first()

        current_domain_ports = []
        for domain in domains:

            if re.match(r"^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$", domain):
                continue

            for port in ports:
                current_domain_ports.append((domain, port))

                update_dict = dict( ssl_yn      = ssl_yn
                                  , user_id     = 'scheduler'
                                  , create_on   = datetime.now()
                )

                insert_dict = update_dict.copy()
                insert_dict.update( host_id     = wi['host_id']
                                  , mw_web_vhost_id = v.id
                                  , domain_name = domain
                                  , port        = port
                )

                stmt = insert(MwWebDomain).values(insert_dict)    
                do_update_stmt = stmt.on_conflict_do_update(
                    index_elements=['mw_web_vhost_id', 'domain_name', 'port'],
                    set_=update_dict
                ).returning(MwWebDomain.id)
                rtn = db.session.execute(do_update_stmt)

                if ssl_yn == 'YES' and ssl_rec:
                    domain_id = next(rec[0] for rec in rtn)
                    domain_rec = db.session.query(MwWebDomain)\
                        .filter(MwWebDomain.id==domain_id).first()
                    domain_rec.mw_web_ssl = [ssl_rec]
        
        # 현재 설정에 없는 도메인 정보는 삭제 처리
        delete_stmt = delete(MwWebDomain).where(
                (MwWebDomain.mw_web_vhost_id == v.id),
                ~tuple_(MwWebDomain.domain_name, MwWebDomain.port).in_(current_domain_ports)
        )
        db.session.execute(delete_stmt)

    return 1, 'OK'

def _create_ssl_info(webInfo):

    if not webInfo:
        return 0, ''

    try:
        wi = _parse_web_info(webInfo)
    except ValueError as e:
        return 0, str(e)

    web_rec = db.session.query(MwWeb)\
                .filter(MwWeb.host_id==wi['host_id'], MwWeb.port==wi['port'])\
                .first()

    if not web_rec:
        return 0, ''

    ssls  = web_rec.ssl_object

    ssl_name_list = []
    for ssl in ssls:

        ssl_name     = ssl['NAME'] if ssl.get('NAME') else ''
        ssl_name_list.append(ssl_name)
        ssl_certi    = ssl['CERTIFICATEFILE'] if ssl.get('CERTIFICATEFILE') else ''
        ssl_certikey = ssl['CERTIFICATEKEYFILE'] if ssl.get('CERTIFICATEKEYFILE') else ''
        ssl_cacerti  = ssl['CACERTIFICATEFILE'] if ssl.get('CACERTIFICATEFILE') else ''
        ssl_protocols= ssl['PROTOCOLS'] if ssl.get('PROTOCOLS') else ''
        ssl_ciphers  = ssl['REQUIREDCIPHERS'] if ssl.get('REQUIREDCIPHERS') else ''

        update_dict = dict( ssl_certi     = ssl_certi
                          , ssl_certikey  = ssl_certikey
                          , ssl_cacerti   = ssl_cacerti
                          , ssl_protocols = ssl_protocols
                          , ssl_ciphers   = ssl_ciphers
                          , user_id       = 'scheduler'
                          , create_on     = datetime.now()
            )

        insert_dict = update_dict.copy()
        insert_dict.update( host_id  = wi['host_id']
                          , mw_web_id = web_rec.id
                          , ssl_name  = ssl_name
                )

        stmt = insert(MwWebSsl).values(insert_dict)    
        do_update_stmt = stmt.on_conflict_do_update(
            index_elements=['mw_web_id', 'ssl_name'],
            set_=update_dict
        )
        db.session.execute(do_update_stmt)

    # 현재 설정에 없는 SSL 정보는 삭제 처리
    delete_stmt = delete(MwWebSsl).where(
            (MwWebSsl.mw_web_id == web_rec.id),
            ~MwWebSsl.ssl_name.in_(ssl_name_list)
    )
    db.session.execute(delete_stmt)

    return 1, 'OK'

#차세대 Jeus Domain Configuration
class NewHttpm(WebtobHttpm):

    #Overided
    def _setSubGroup(self):
        return super()._setSubGroup()

    #Overided
    def _getDataOfWeb(self):
        return super()._getDataOfWeb()

    #Overided
    def _getDataOfWebServer(self, server):
        return super()._getDataOfWebServer(server)

    #Overided
    def _getDataOfWebVhost(self, vhost):
        return super()._getDataOfWebVhost(vhost)

    #Overided
    def _getDataOfWebserver_Vhost(self, vhost):
        return super()._getDataOfWebserver_Vhost(vhost)

    #Overided
    def _getDataOfWebUri(self, uri):
        return super()._getDataOfWebUri(uri)

    #Overided
    def _getDataOfWeburi_Vhost(self, vhost):
        return super()._getDataOfWeburi_Vhost(vhost)

    #Overided
    def _getDataOfWebReverseproxy(self, rp):
        return super()._getDataOfWebReverseproxy(rp)

    #Overided
    def _getDataOfWebreverseproxy_Vhost(self, vhost):
        return super()._getDataOfWebreverseproxy_Vhost(vhost)

#유지 Jeus Domain Configuration 
class OldHttpm(WebtobHttpm):

    #Overided
    def _setSubGroup(self):
        return super()._setSubGroup()

    #Overided
    def _getDataOfWeb(self):
        return super()._getDataOfWeb()

    #Overided
    def _getDataOfWebServer(self, server):
        return super()._getDataOfWebServer(server)

    #Overided
    def _getDataOfWebVhost(self, vhost):
        return super()._getDataOfWebVhost(vhost)

    #Overided
    def _getDataOfWebserver_Vhost(self, vhost):
        return super()._getDataOfWebserver_Vhost(vhost)

    #Overided
    def _getDataOfWebUri(self, uri):
        return super()._getDataOfWebUri(uri)

    #Overided
    def _getDataOfWeburi_Vhost(self, vhost):
        return super()._getDataOfWeburi_Vhost(vhost)

    #Overided
    def _getDataOfWebReverseproxy(self, rp):
        return super()._getDataOfWebReverseproxy(rp)

    #Overided
    def _getDataOfWebreverseproxy_Vhost(self, vhost):
        return super()._getDataOfWebreverseproxy_Vhost(vhost)

class WebtobHttpmFactory:
    def webtobHttpm(self, h):
        return h.upsertWebtobHttpm()

def httpm_to_dict(content):

    category = ''
    category_new = ''
    item = ''
    item_dict = dict()
    category_list = []
    all_dict = dict()

    content = content.replace('\\\n', '')
    f = content.split('\n')

    for line in f:
        
        if line.strip() in ('', '\\n'):
            continue

        if line.startswith('*'):
            if category:
                if item:
                    item_dict['NAME'] = item
                    category_list.append(item_dict)
                all_dict.update({category:category_list})
            item_dict = dict()
            category_list = []
            category = line[1:].rstrip()
            item = ''
            continue
        elif line.lstrip().startswith('#'):
            continue		

        if line.find('#') >= 0:
            line = line[:line.find('#')] #Remove Comments

        if line[0] not in (' ','\t'):
            if item and item_dict:
                item_dict['NAME'] = item
                category_list.append(item_dict)
            item_dict = dict()

            ll = line.split()
            item = ll[0]
            if len(ll) > 1:
                line = ''.join(ll[1:])
            else:
                continue
        
        line = line.strip().rstrip(',')
        qline = re.findall(r'(["].*?["])',line)		
        for q in qline:
            qq = q.replace(',','^').replace('=','#').replace('"','')            
            line = line.replace(q,qq)
        linelist = line.split(',')

        dic = dict()
        for ll in linelist:
            ll = ll.strip()
            if '=' not in ll:
                continue
            lld = ll.split('=')
            if len(lld) < 2:
                continue
            value = lld[1].replace('#','=').replace('^',',').replace('\t','').strip()
            value_l = value.split(',')
            value_l = [ v.strip() for v in value_l]
            item_u = lld[0].upper().strip()
            if item_u in ['VHOSTNAME','HOSTNAME','HOSTALIAS','LOGGING']:
                dic.update({item_u:value_l})
            else:
                dic.update({item_u:value})

        line_dict = dic
        item_dict.update(line_dict)

    item_dict['NAME'] = item
    category_list.append(item_dict)
    all_dict.update({category:category_list})

    # *DOMAIN 은 섹션으로 파싱한 뒤 버린다. 위치와 도메인 이름에 관계없이 다른 섹션에 섞이지 않는다
    all_dict.pop('DOMAIN', None)

    return all_dict
