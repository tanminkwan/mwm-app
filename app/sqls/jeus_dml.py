from app.models.common import get_user
from abc import ABC, abstractmethod
import logging
from flask import g
from app import appbuilder, db
from datetime import datetime
from sqlalchemy import null, text, delete
from sqlalchemy.dialects.postgresql import insert, JSON
from app.models.was import MwServer, MwWas, MwWasInstance, MwWeb, MwWebVhost, MwWasHttpListener\
    , MwWasWebtobConnector, MwWebReverseproxy, MwDatasource, MwApplication\
    , MwWebServer, MwAppMaster, MwDBMaster
from app.sqls.was import get_landscape
from app.sqls.relationship import get_real_web_host_id
from app.sqls.monitor import select_row 
from app.sqls.knowledge import insert_tag

import re

# JVM 힙 크기 접미사 → 바이트 배수. 접미사가 없으면 값 자체가 바이트다.
_HEAP_UNITS_IN_BYTES = {
    'k': 1024,
    'm': 1024 ** 2,
    'g': 1024 ** 3,
    't': 1024 ** 4,
}


def _parse_heap_size_mb(size_text):
    """`-Xms` / `-Xmx` 의 값 부분을 **MB 정수**로 바꾼다. 해석 불가면 -1.

    JVM 표기는 `<수>[k|K|m|M|g|G|t|T]` 이며 접미사가 없으면 바이트다.
    `mw_was_instance.min_heap_size` / `max_heap_size` 는 MB 로 저장한다.

    예전 구현은 `int(size_text[:-1])` 로 **마지막 한 글자를 무조건 잘라냈다.**
    그래서 두 가지가 틀렸다 (TASK 5-7 §4).
      - 단위를 환산하지 않고 버려서 `2g` 와 `2m` 이 똑같이 2 가 됐다
      - 단위가 없으면 마지막 **숫자**가 잘려 `512` 가 51 이 됐다
    """
    if not size_text:
        return -1

    unit = size_text[-1].lower()
    if unit in _HEAP_UNITS_IN_BYTES:
        number, multiplier = size_text[:-1], _HEAP_UNITS_IN_BYTES[unit]
    else:
        number, multiplier = size_text, 1

    if not number.isnumeric():
        return -1

    return int(number) * multiplier // (1024 ** 2)


class JeusDomain(ABC):

    def __init__(self, domain_id, host_id, domain, raw_data, sys_user="", agent_id=""):
        self.domain_id     = domain_id
        self.host_id       = host_id
        self.domain        = domain
        self.raw_data      = raw_data
        self.sys_user      = sys_user
        self.agent_id      = agent_id
        self.landscape     = ''
        self.databases     = []
        self.applications  = []
        self.clusters      = []
        self.servers       = []
        self.single_server = []
        self.datasources_dict   = dict()
        self.applications_dict  = dict()
        #self.was_instances_dict = dict()
        self._setSubGroup()

    @abstractmethod
    def _setSubGroup(self):
        raise NotImplementedError

    def upsertWebConnection(self):

        # Upsert mw_webconnection
        _, insert_http_array, update_http_array, insert_webtob_array, update_webtob_array\
            = self.__getArrayDictOfWebConnections(self.single_server)

        ## Upsert mw_was_httplistener
        for insert_dict, update_dict in zip(insert_http_array, update_http_array):

            stmt = insert(MwWasHttpListener).values(insert_dict)    
            do_update_stmt = stmt.on_conflict_do_update(
                index_elements=['was_id', 'was_instance_id', 'webconnection_id'],
                set_=update_dict
            )
            db.session.execute(do_update_stmt)

        ## Upsert mw_was_webtobconnector
        for insert_dict, update_dict in zip(insert_webtob_array, update_webtob_array):

            stmt = insert(MwWasWebtobConnector).values(insert_dict)    
            do_update_stmt = stmt.on_conflict_do_update(
                index_elements=['was_id', 'was_instance_id', 'webconnection_id'],
                set_=update_dict
            )
            db.session.execute(do_update_stmt)

        # Commit
        #db.session.commit()
        return 1, {'result':'OK'}

    def upsertJeusDomain(self):

        # 
        self.landscape = get_landscape(self.host_id)

        if self.landscape is None:
            error_msg = f"Host '{self.host_id}' not found in MwServer. Please register the server first."
            logging.error(f"mwm upsertJeusDomain Error: {error_msg}")
            return -10, error_msg

        try:
            # Upsert mw_was
            _, insert_dict, update_dict = self.__getDictOfWas(self.domain)

            stmt = insert(MwWas).values(insert_dict)    
            do_update_stmt = stmt.on_conflict_do_update(
                index_elements=['was_id'],
                set_=update_dict
            )
            db.session.execute(do_update_stmt)
            
            # Upsert mw_datasource
            _, insert_array, update_array \
                = self.__getArrayDictOfDatasources(self.databases)
            
            for insert_dict, update_dict in zip(insert_array, update_array):

                stmt = insert(MwDatasource).values(insert_dict)    
                do_update_stmt = stmt.on_conflict_do_update(
                    index_elements=['was_id', 'datasource_id'],
                    set_=update_dict
                ).returning(MwDatasource.datasource_id, MwDatasource.id)
                result = db.session.execute(do_update_stmt)

                for rec in result:
                    self.datasources_dict.update({rec[0]:rec[1]})

            # Upsert mw_db_master (2021-09-03)
            self.__upsertDBMaster(insert_array)

            # Upsert mw_application
            _, insert_array, update_array \
                = self.__getArrayDictOfApplications(self.applications)
            
            for insert_dict, update_dict in zip(insert_array, update_array):

                stmt = insert(MwApplication).values(insert_dict)    
                do_update_stmt = stmt.on_conflict_do_update(
                    index_elements=['was_id', 'application_id'],
                    set_=update_dict
                ).returning(MwApplication.application_id, MwApplication.id)
                result = db.session.execute(do_update_stmt)

                for rec in result:
                    self.applications_dict.update({rec[0]:rec[1]})

            # Upsert mw_was_instance
            _, insert_array, update_array, _tag_array \
                = self.__getArrayDictOfWasInstances(self.servers, self.clusters)

            # delete removed was instances (2026-02-23)
            current_instance_ids = [ia['was_instance_id'] for ia in insert_array]
            delete_stmt = delete(MwWasInstance).where(
                    (MwWasInstance.was_id == self.domain_id),
                    ~MwWasInstance.was_instance_id.in_(current_instance_ids)
            )
            db.session.execute(delete_stmt)

            # Upsert mw_app_master (2021-09-03)
            self.__upsertAppMaster(insert_array)

            for insert_dict, update_dict in zip(insert_array, update_array):

                stmt = insert(MwWasInstance).values(insert_dict)    
                do_update_stmt = stmt.on_conflict_do_update(
                    index_elements=['was_id', 'was_instance_id'],
                    set_=update_dict
                ).returning(MwWasInstance.was_instance_id, MwWasInstance.id)
                result = db.session.execute(do_update_stmt)

                #for rec in result:
                #    self.__updateWasInstanceTag(rec[1], tag)
                #    self.was_instances_dict.update({rec[0]:rec[1]})

            # insert/delete mw_datasource_wasinstance
            self.__updateDatasource_Wasinstances(self.servers)

            # insert/delete mw_application_wasinstance
            self.__updateApplication_Wasinstances(self.applications)

            # Upsert mw_webconnection
            _, insert_http_array, update_http_array, insert_webtob_array, update_webtob_array\
                = self.__getArrayDictOfWebConnections(self.servers)

            ## Upsert mw_was_httplistener
            for insert_dict, update_dict in zip(insert_http_array, update_http_array):

                stmt = insert(MwWasHttpListener).values(insert_dict)    
                do_update_stmt = stmt.on_conflict_do_update(
                    index_elements=['was_id', 'was_instance_id', 'webconnection_id'],
                    set_=update_dict
                )
                db.session.execute(do_update_stmt)

            ## Upsert mw_was_webtobconnector
            for insert_dict, update_dict in zip(insert_webtob_array, update_webtob_array):

                stmt = insert(MwWasWebtobConnector).values(insert_dict)    
                do_update_stmt = stmt.on_conflict_do_update(
                    index_elements=['was_id', 'was_instance_id', 'webconnection_id'],
                    set_=update_dict
                )
                db.session.execute(do_update_stmt)

            return 1, 'OK'

        except Exception as e:
            db.session.rollback()
            logging.error(f"mwm upsertJeusDomain Exception: {str(e)}")
            return -1, str(e)

    def __getDictOfWas(self, domain):

        update_dict = self._getDataOfWas(domain)
        update_dict.update(
            was_text = self.raw_data
        )

        insert_dict = update_dict.copy()
        insert_dict.update(
            was_id   = self.domain_id
        )

        return 1, insert_dict, update_dict

    """
    def __getTagWas(self):

        tag = 'WAS-' + self.domain_id + '-' + self.host_id + '-'\
                    + ( self.sys_user if self.sys_user else 'NOUSERID')
        tag_id = insertResourceTag('mw_was', tag)
        return tag_id
    """
    @abstractmethod
    def _getDataOfWas(self, domain):
        raise NotImplementedError

    def __getArrayDictOfDatasources(self, datasources):

        update_array = []
        insert_array = []
        update_dict = {}
        insert_dict = {}   
        db_property = ''

        for ds in datasources:

            update_dict, datasource_id_str = self._getDataOfDatasource(ds)

            insert_dict = update_dict.copy()
            insert_dict.update(was_id = self.domain_id, datasource_id = datasource_id_str)

            update_array.append(update_dict)
            insert_array.append(insert_dict)        

        return 1, insert_array, update_array

    @abstractmethod
    def _getDataOfDatasource(self, ds):

        db_property = ''
        if ds.get('property'):
            properties = ds['property'] if isinstance(ds['property'], list)\
                                 else [ds['property']]
            for prop in properties:
                db_property += prop['name'] + ':' + prop['value']+ ','

        #db property parsing
        if db_property and any(x is None for x in 
                               [ds.get('server-name'),
                                ds.get('port-number'), 
                                ds.get('database-name')]):

            db_server_name, db_server_port, db_dbms_id = self._getDBparams(db_property)
        else:
            db_server_name        = ds['server-name'] \
                                    if ds.get('server-name') else null()
            db_server_port        = ds['port-number'] \
                                    if ds.get('port-number') else null()
            db_dbms_id            = ds['database-name'] \
                                    if ds.get('database-name') else null()

        update_dict = dict(
            db_jndi_id            = ds['export-name'],
            datasource_type       = ds['data-source-type'] \
                                    if ds.get('data-source-type') else null(),
            datasource_class_name = ds['data-source-class-name'] \
                                    if ds.get('data-source-class-name') else null(),
            vender_name           = ds['vendor'] if ds.get('vendor') else null(),
            db_user_id            = ds['user'],
            db_dbms_id            = db_dbms_id,
            db_server_name        = db_server_name,
            db_server_port        = db_server_port,
            db_property           = db_property if db_property else null(),
            stmt_query_timeout    = ds['stmt-query-timeout'] \
                                    if ds.get('stmt-query-timeout') else null(),
            db_pool_min           = ds['connection-pool']['pooling']['min'],
            db_pool_max           = ds['connection-pool']['pooling']['max'],
            db_pool_step          = ds['connection-pool']['pooling']['step'],
            db_pool_period        = ds['connection-pool']['pooling']['period'],
            user_id               = get_user(),
            create_on             = datetime.now()
        )

        datasource_id = ds['data-source-id']\
                            if ds.get('data-source-id') else '('+self.host_id+')'+ds['export-name']

        return update_dict, datasource_id

    def __getArrayDictOfApplications(self, applications):

        update_array = []
        insert_array = []
        update_dict = {}
        insert_dict = {}

        for ap in applications:

            update_dict, application_id = self._getDataOfApplication(ap)

            insert_dict = update_dict.copy()
            insert_dict.update(was_id = self.domain_id, application_id = application_id)

            update_array.append(update_dict)
            insert_array.append(insert_dict)        

        return 1, insert_array, update_array

    @abstractmethod
    def _getDataOfApplication(self, ap):
        raise NotImplementedError

    def __getArrayDictOfWasInstances(self, servers, clusters):

        update_array = []
        insert_array = []
        tag_array    = []
        update_dict = {}
        insert_dict = {}
        
        for server in servers:

            update_dict, was_instance_id = self._getDataOfWasInstances(server, clusters)

            insert_dict = update_dict.copy()
            insert_dict.update(\
                was_id = self.domain_id
              , was_instance_id = was_instance_id
              )

            update_array.append(update_dict)
            insert_array.append(insert_dict)
            tag_array.append(self.__getTagWasInstance(was_instance_id))

        return 1, insert_array, update_array, tag_array

    @abstractmethod
    def _getDataOfWasInstances(self, server):
        raise NotImplementedError

    def __updateWasInstanceTag(self, id, tag):

        wasInstance_rec = db.session.query(MwWasInstance)\
                .filter(MwWasInstance.id==id).first()
        wasInstance_rec.ut_tag = tag

        return 1

    def __getTagWasInstance(self, was_instance_id):

        rtn = []
        if '_Domain' in self.domain_id and '_M' in was_instance_id:
            tag1 = self.domain_id.replace('_Domain','')[1:]
            tag2 = was_instance_id.split('_M')[0]
            tag = 'MS-' + tag1 + '_Domain-' + tag2
            tag_id = insert_tag(tag)
            row, _ = select_row('ut_tag',{'id':tag_id})
            rtn.append(row)
        return rtn

    def __updateDatasource_Wasinstances(self, servers):

        for server in servers:

            datasources, was_instance_id\
                 = self._getDataOfDatasourcesforWasInstance(server)

            if not datasources:
                continue

            wasInstance_rec = db.session.query(MwWasInstance)\
                    .filter(MwWasInstance.was_id==self.domain_id\
                        , MwWasInstance.was_instance_id==was_instance_id).first()

            datasource_recs = db.session.query(MwDatasource)\
                    .filter(MwDatasource.was_id==self.domain_id\
                        , MwDatasource.datasource_id.in_(datasources)).all()

            wasInstance_rec.mw_datasource = datasource_recs

            #update assoc_dbmaster_appmaster
            self._makeRelationDBMasterAppMaster(self._getAppID(was_instance_id), datasource_recs)

        return 1

    @abstractmethod
    def _getDataOfDatasourcesforWasInstance(self, server):
        raise NotImplementedError

    def __updateApplication_Wasinstances(self, applications):

        map_dict = self._getDataOfApplicationsforWasInstance(applications)

        for server, apps in map_dict.items():

            wasInstance_rec = db.session.query(MwWasInstance)\
                    .filter(MwWasInstance.was_id==self.domain_id\
                        , MwWasInstance.was_instance_id==server).first()

            application_recs = db.session.query(MwApplication)\
                    .filter(MwApplication.was_id==self.domain_id\
                        , MwApplication.application_id.in_(apps)).all()

            if wasInstance_rec:
                wasInstance_rec.mw_application = application_recs
        
        return 1

    @abstractmethod
    def _getDataOfApplicationsforWasInstance(self, applications):
        raise NotImplementedError

    def __getArrayDictOfWebConnections(self, servers):

        update_http_a = []
        insert_http_a = []
        update_webtob_a = []
        insert_webtob_a = []
        update_http_array = []
        insert_http_array = []
        update_webtob_array = []
        insert_webtob_array = []

        for server in servers:

            insert_http_a, update_http_a, insert_webtob_a, update_webtob_a\
                 = self._getDataOfWebConnections(server)

            update_http_array.extend(update_http_a)
            insert_http_array.extend(insert_http_a) 
            update_webtob_array.extend(update_webtob_a)
            insert_webtob_array.extend(insert_webtob_a)            

        return 1, insert_http_array, update_http_array, insert_webtob_array, update_webtob_array

    @abstractmethod
    def _getDataOfWebConnections(self, server):
        raise NotImplementedError

    def _getDBparams(self, db_property):

        #Get HOST values
        tmp = re.split('HOST=|host=', db_property)
        if len(tmp)<=1:
            return None, None, None

        hosts = []   
        for i in range(1, len(tmp)):
	        hosts.append(tmp[i][:tmp[i].find(')')])

        db_server_name = ','.join(hosts)

        #Get PORT values
        tmp = re.split('PORT=|port=', db_property)

        if len(tmp)<=1:
            return db_server_name, None, None

        db_server_port = int(tmp[1][:tmp[1].find(')')])

        tmp = re.split('SERVICE_NAME=|DATABASE_NAME=|service_name=|database_name=', db_property)

        if len(tmp)<=1:
        	return db_server_name, db_server_port, None

        db_dbms_id = tmp[1][:tmp[1].find(')')]

        return db_server_name, db_server_port, db_dbms_id

    def __upsertDBMaster(self, insert_array):

        for db_config in insert_array:

            rec = db.session.query(MwDBMaster)\
                   .filter(MwDBMaster.db_dbms_id==db_config['db_dbms_id']\
                          ,MwDBMaster.landscape==self.landscape).first()

            if not rec:
                
                insert_dict = dict(
                    landscape      = self.landscape,
                    db_dbms_id     = db_config['db_dbms_id'],
                    vender_name    = db_config['vender_name'],
                    db_server_name = db_config['db_server_name'],
                    db_server_port = db_config['db_server_port'],
                    user_id        = get_user(),
                    create_on      = datetime.now()
                    )
            
                stmt = insert(MwDBMaster).values(insert_dict)
                r = db.session.execute(stmt)

        return 1

    def _getAppID(self, was_instance_id):
        # 마지막 숫자 묶음을 지운다. 예전 식 (\d+)(?!.*\d) 는 숫자가 길면 제곱으로 느려졌다 (CodeQL py/polynomial-redos)
        last = None
        for last in re.finditer(r'\d+', was_instance_id):
            pass
        tmp = was_instance_id[:last.start()] + was_instance_id[last.end():] if last else was_instance_id
        tmp = re.sub(r'_MS[A-Z]','_MS', tmp)
        return self.domain_id + '.' + tmp\
                 if was_instance_id != 'adminServer' else 'NOAPP'

    def __upsertAppMaster(self, insert_array):

        for ia in insert_array:

            app_id = self._getAppID(ia['was_instance_id'])

            rec = db.session.query(MwAppMaster)\
                        .filter(MwAppMaster.app_id==app_id).first()

            if not rec:
                
                insert_dict = dict(
                    app_id    = app_id,
                    landscape = self.landscape,
                    user_id   = get_user(),
                    create_on = datetime.now()
                    )
            
                stmt = insert(MwAppMaster).values(insert_dict)
                r = db.session.execute(stmt)

        return 1

    def _makeRelationDBMasterAppMaster(self, app_id, datasource_recs):

        rec = db.session.query(MwAppMaster)\
               .filter(MwAppMaster.app_id==app_id).first()

        if not rec:
            return 0

        for d_rec in datasource_recs:
            dm_rec = db.session.query(MwDBMaster)\
               .filter(MwDBMaster.db_dbms_id==d_rec.db_dbms_id\
                      ,MwDBMaster.landscape==self.landscape).first()

            if not dm_rec in rec.mw_db_master:
                
                rec.mw_db_master.append(dm_rec)

        return 1

    def _getJvmOptions(self, jvm_option):

        min_heap_size  = -1
        max_heap_size  = -1
        apm_type       = ''
        jvm_option_str = ''

        if isinstance(jvm_option, list):
            jvm_option_str = '\n'.join(jvm_option)
        else:
            jvm_option_str = jvm_option

        for opt in jvm_option_str.split():
            if '-Xms' in opt:
                min_heap_size = _parse_heap_size_mb(opt[4:])
            elif '-Xmx' in opt:
                max_heap_size = _parse_heap_size_mb(opt[4:])

        if 'pharos.agent' in jvm_option_str:
            apm_type = 'PHAROS'
        elif 'jennifer.config' in jvm_option_str:
            apm_type = 'JENNIFER'
        else:
            apm_type = 'NONE'

        return min_heap_size, max_heap_size, apm_type, jvm_option_str

#차세대 Jeus Domain Configuration
class NewJeusDomain(JeusDomain):

    #Overided
    def _setSubGroup(self):

        if self.domain.get('resources') and self.domain['resources'].get('data-source'):
            tmp = self.domain['resources']['data-source']['database']
            self.databases = tmp.copy() if isinstance(tmp,list) else [tmp]

        if self.domain.get('deployed-applications'):
            tmp = self.domain['deployed-applications']['deployed-application']
            self.applications = tmp.copy() if isinstance(tmp,list) else [tmp]

        if self.domain.get('clusters'):
            tmp = self.domain['clusters']['cluster']
            self.clusters = tmp.copy() if isinstance(tmp,list) else [tmp]

        if self.domain.get('servers'):
            tmp = self.domain['servers']['server']
            self.servers = tmp.copy() if isinstance(tmp,list) else [tmp]

    #Overided
    def _getDataOfWas(self, domain):

        dict_ = dict(
                adminserver_name = domain['admin-server-name'] if domain.get('admin-server-name') \
                                    else domain['master-server-name'],
                log_home         = domain['domain-log-home'] \
                                    if domain.get('domain-log-home') else null(),
                located_host_id  = self.host_id,
                newgeneration_yn = 'YES',
                landscape        = self.landscape,
                production_mode  = domain['production-mode'] \
                                    if domain.get('production-mode') else null(),
                cluster_object   = domain['clusters'] if domain.get('clusters') else null(),
                was_object       = self.domain,
                agent_id         = self.agent_id,
                user_id          = get_user(),
                create_on        = datetime.now()
            )

        if self.sys_user:
            dict_['sys_user'] = self.sys_user

        return dict_

    def _getDataOfDatasource(self, ds):
        return super()._getDataOfDatasource(ds)

    def _getDataOfApplication(self, ap):
        return dict(
                application_home = ap['path'],
                context_path     = ap['context-path']\
                                    if ap.get('context-path') else null(),
                deploy_type      = ap['type'].upper() if ap['type'].upper()\
                                             in ['WAR','EAR','JAR'] else 'EXPLODED',
                user_id          = get_user(),
                create_on        = datetime.now()
            ), ap['id']

    def _getDataOfWasInstances(self, server, clusters):

        min_heap_size, max_heap_size, apm_type, jvm_option\
            = self._getJvmOptions(server['jvm-config']['jvm-option'])

        clusters = clusters if isinstance(clusters,list) else [clusters]

        clustered_yn = 'NO'    
        
        for c in clusters:
            if server['name'] in c['servers']['server-name']:
                clustered_yn = 'YES'
                break

        if isinstance(server['listeners']['listener'], list):
            was_instance_port = server['listeners']['listener'][0]['listen-port']
        else:
            was_instance_port = server['listeners']['listener']['listen-port']

        was_instance_id = server['name']

        node_name = server['node-name'].lower() if server.get('node-name') else self.host_id

        update_dict = dict(
                was_instance_port = was_instance_port,
                host_id           = node_name ,
                min_heap_size     = min_heap_size,
                max_heap_size     = max_heap_size,
                jvm_option        = jvm_option,
                log_home          = server['log-home'] if server.get('log-home') else null(),
                apm_type          = apm_type,
                app_id            = self._getAppID(was_instance_id),
                clustered_yn      = clustered_yn,
                user_id          = get_user(),
                create_on        = datetime.now()
        )

        return update_dict, was_instance_id

    def _getDataOfDatasourcesforWasInstance(self, server):

        if not server.get('data-sources'):
            return [], ""
            
        tmp = server['data-sources']['data-source']
        datasources = tmp if isinstance(tmp,list) else [tmp]

        was_instance_id = server['name']

        return datasources, was_instance_id

    def _getDataOfApplicationsforWasInstance(self, applications):
        
        map_dict = dict()

        for app in applications:

            servers = []

            if app.get('target-server'):
                
                tmp = app['target-server']
                servers.extend(tmp if isinstance(tmp,list) else [tmp])

            #In case of JEUS7
            if app.get('targets'):
                
                tmp = app['targets']
                tmp = tmp if isinstance(tmp,list) else [tmp]
                servers.extend([t['server'] for t in tmp])

            if app.get('target-cluster'):

                tmp = self.clusters
                clusters_inwas = tmp if isinstance(tmp,list) else [tmp]

                tmp = app['target-cluster']
                clusters = tmp if isinstance(tmp,list) else [tmp]

                for cluster in clusters:
                    tmp = next( c['servers']['server-name']\
                         for c in clusters_inwas if c['name']==cluster['name'])
                    
                    tmp = tmp if isinstance(tmp,list) else [tmp]
                    tmp = [ {'name':s} for s in tmp ]
                    servers.extend(tmp)

            for server in servers:
                if map_dict.get(server['name']):
                    map_dict[server['name']].append(app['id'])
                else:
                    map_dict[server['name']] = [app['id']]

        return map_dict

    def _getDataOfWebConnections(self, server):

        update_http_a = []
        insert_http_a = []
        update_webtob_a = []
        insert_webtob_a = []
        update_dict = {}
        insert_dict = {}
        
        webconn_list = []
        listener_list = []

        if not server.get('web-engine'):
            return [], [], [], []

        if server['web-engine']['web-connections'].get('http-listener'):

            tmp = server['web-engine']['web-connections']['http-listener']
            webconn_list = tmp if isinstance(tmp, list) else [tmp]

            tmp = server['listeners']['listener']
            listener_list = tmp if isinstance(tmp, list) else [tmp]

            for webconn in webconn_list:
                li = next((li for li in listener_list\
                                     if li['name']==webconn['server-listener-ref']), None)
                ssl_yn = 'YES' if li and li.get('ssl') else 'NO'

                update_dict = dict(
                    listen_port           = li['listen-port'] if li else -1,
                    min_thread_pool_count = webconn['thread-pool']['min']\
                                        if webconn['thread-pool'].get('min') else null(),
                    max_thread_pool_count = webconn['thread-pool']['max']\
                                        if webconn['thread-pool'].get('max') else null(),
                    ssl_yn                = ssl_yn,
                    domain_name           = null(),
                    httplistener_object   = webconn,
                    user_id          = get_user(),
                    create_on        = datetime.now()
                )

                insert_dict = update_dict.copy()
                insert_dict.update(was_id = self.domain_id\
                                , was_instance_id = server['name']
                                , webconnection_id = webconn['name'])

                update_http_a.append(update_dict)
                insert_http_a.append(insert_dict)   
                    
        if server['web-engine']['web-connections'].get('webtob-connector'):

            tmp = server['web-engine']['web-connections']['webtob-connector']
            webconn_list = tmp if isinstance(tmp, list) else [tmp]
                    
            for webconn in webconn_list:

                disable_pipe = 'YES'
                if webconn.get('network-address'):
                    web_host_id = webconn['network-address']['ip-address'].lower()
                    web_home    = null()
                    jsv_port    = webconn['network-address']['port']
                elif webconn.get('domain-socket-address'):
                    web_host_id = '<domain-socket>'
                    web_home    = webconn['domain-socket-address']['webtob-home']\
                            if webconn['domain-socket-address'].get('webtob-home') else null()
                    jsv_port    = webconn['domain-socket-address']['webtob-ipcbaseport']
                    disable_pipe = 'NO'
                else:
                    web_host_id = null()
                    web_home    = null()
                    jsv_port    = null()

                update_dict = dict(

                    web_host_id            = web_host_id,
                    real_web_host_id       = get_real_web_host_id(web_host_id, self.host_id),
                    web_home               = web_home,
                    jsv_port               = jsv_port,
                    jsv_id                 = webconn['registration-id'],
                    web_hth_count          = webconn['hth-count']\
                                        if webconn.get('hth-count') else null(),
                    web_reconnect_interval = webconn['reconnect-interval']\
                                        if webconn.get('reconnect-interval') else null(),
                    thread_pool_count      = webconn['thread-pool']['number']\
                                        if webconn['thread-pool'].get('number') else null(),
                    webtobconnector_object = webconn,
                    disable_pipe     = 'YES',
                    user_id          = get_user(),
                    create_on        = datetime.now()
                )
                insert_dict = update_dict.copy()
                insert_dict.update(was_id = self.domain_id\
                            , was_instance_id = server['name']
                            , webconnection_id = webconn['name'])

                update_webtob_a.append(update_dict)
                insert_webtob_a.append(insert_dict)   

        return insert_http_a, update_http_a, insert_webtob_a, update_webtob_a

#유지 Jeus Domain Configuration 
class OldJeusDomain(JeusDomain):

    #Overided
    def _setSubGroup(self):

        if self.domain.get('resource') and self.domain['resource'].get('data-source'):
            tmp = self.domain['resource']['data-source']['database']
            self.databases = tmp.copy() if isinstance(tmp,list) else [tmp]

        if self.domain.get('application'):
            tmp = self.domain['application']
            self.applications = tmp.copy() if isinstance(tmp,list) else [tmp]

            for app in self.applications:
                # AS-IS 국외점포 ejb application 문제 : 하나의 application tag 에 어러개의 application이 있음
                if isinstance(app['name'], list):
                    self.applications.remove(app)

        if self.domain.get('node') and self.domain['node'].get('engine-container'):
            tmp = self.domain['node']['engine-container']
            self.servers = tmp.copy() if isinstance(tmp,list) else [tmp]

        #WEBMain.xml 인 경우
        if self.domain.get('context-group'):
            self.single_server = [self.domain]

    #Overided
    def _getDataOfWas(self, domain):

        return dict(
            adminserver_name = null(),
            log_home         = null(),
            located_host_id  = domain['node']['name'].lower(),
            newgeneration_yn = 'NO',
            production_mode  = null(),
            sys_user      = self.sys_user,
            cluster_object   = null(),
            was_object       = self.domain,
            agent_id         = self.agent_id,
            user_id          = get_user(),
            create_on        = datetime.now()
        )

    def _getDataOfDatasource(self, ds):
        return super()._getDataOfDatasource(ds)

    def _getDataOfApplication(self, ap):

        if ap.get('deployment-type'):
            deploy_type = ap['deployment-type']
        elif ap['class-ftp-unit'].upper() in ['WAR','EAR','JAR']:
            deploy_type = ap['class-ftp-unit'].upper()
        else:
            deploy_type = 'EXPLODED'

        return dict(
                application_home = ap['path'],
                context_path     = ap['web-component']['context-root']\
                                    if ap.get('web-component') and ap['web-component'].get('context-root') else null(),
                deploy_type      = deploy_type,
                user_id          = get_user(),
                create_on        = datetime.now()
            ), ap['name']

    def _getDataOfWasInstances(self, server, clusters):

        min_heap_size, max_heap_size, apm_type, jvm_option\
            = self._getJvmOptions(server['command-option'])

        clustered_yn = 'NO'
        
        tmp = server['engine-command']
        engine_commands = tmp if isinstance(tmp,list) else [tmp]

        engine_command = next( e_c['name']\
                         for e_c in engine_commands if e_c['type']=='servlet')

        was_instance_id = self.host_id + '_' + server['name']

        update_dict = dict(
                was_instance_port = server['base-port'] if server.get('base-port') else null(),
                host_id           = self.host_id,
                min_heap_size     = min_heap_size,
                max_heap_size     = max_heap_size,
                jvm_option        = jvm_option,
                log_home          = null(),
                apm_type          = apm_type,
                app_id            = self._getAppID(was_instance_id),
                engine_command    = engine_command,
                clustered_yn      = clustered_yn,
                user_id          = get_user(),
                create_on        = datetime.now()
        )

        return update_dict, was_instance_id

    def _getDataOfDatasourcesforWasInstance(self, server):
        if not self.datasources_dict:
            return [], ""

        datasources = [ d for d in self.datasources_dict ]
        was_instance_id = self.host_id + '_' + server['name']

        return datasources, was_instance_id

    def _getDataOfApplicationsforWasInstance(self, applications):

        map_dict = dict()

        for app in applications:

            servers = []

            if app.get('deployment-target'):
                
                tmp = app['deployment-target']['target']
                servers.extend(tmp if isinstance(tmp,list) else [tmp])

            for server in servers:

                #tmp = server['engine-container-name']
                #was_instance_id = tmp[tmp.find(self.host_id) + len(self.host_id) + 1:]
                was_instance_id = server['engine-container-name']

                if map_dict.get(was_instance_id):                    
                    map_dict[was_instance_id].append(app['name'])
                else:
                    map_dict[was_instance_id] = [app['name']]

        return map_dict

    def _getDataOfWebConnections(self, server):

        update_http_a = []
        insert_http_a = []
        update_webtob_a = []
        insert_webtob_a = []
        update_dict = {}
        insert_dict = {}
        
        webconn_list = []
        listener_list = []

        if not server.get('context-group') \
            or not server['context-group'].get('webserver-connection'):
            return [], [], [], []

        if server['context-group']['webserver-connection'].get('http-listener'):

            tmp = server['context-group']['webserver-connection']['http-listener']
            listener_list = tmp if isinstance(tmp, list) else [tmp]
                    
            for webconn in listener_list:
                ssl_yn = 'YES' if webconn.get('ssl') else 'NO'

                update_dict = dict(
                    listen_port           = webconn['port'],
                    min_thread_pool_count = webconn['thread-pool']['min']\
                                        if webconn['thread-pool'].get('min') else null(),
                    max_thread_pool_count = webconn['thread-pool']['max']\
                                        if webconn['thread-pool'].get('max') else null(),
                    ssl_yn                = ssl_yn,
                    domain_name           = null(),
                    httplistener_object   = webconn,
                    user_id          = get_user(),
                    create_on        = datetime.now()
                )

                insert_dict = update_dict.copy()
                insert_dict.update(was_id = self.domain_id\
                                , was_instance_id = server['name']
                                , webconnection_id = webconn['listener-id'])

                update_http_a.append(update_dict)
                insert_http_a.append(insert_dict) 

        if server['context-group']['webserver-connection'].get('webtob-listener'):

            tmp = server['context-group']['webserver-connection']['webtob-listener']
            webconn_list = tmp if isinstance(tmp, list) else [tmp]
                    
            for webconn in webconn_list:

                disable_pipe = 'NO' if webconn.get('disable-pipe') and webconn['disable-pipe'] == 'false' else 'YES'
                update_dict = dict(

                    web_host_id            = webconn['webtob-address'].lower() if webconn.get('hth-count') else 'localhost' ,
                    web_home               = null(),
                    jsv_port               = webconn['port'],
                    jsv_id                 = webconn['registration-id'],
                    web_hth_count          = webconn['hth-count']\
                                        if webconn.get('hth-count') else null(),
                    web_reconnect_interval = null(),
                    thread_pool_count      = webconn['thread-pool']['max']\
                                        if webconn['thread-pool'].get('max') else null(),
                    disable_pipe           = disable_pipe,
                    webtobconnector_object = webconn,
                    user_id                = get_user(),
                    create_on              = datetime.now()
                )
                insert_dict = update_dict.copy()
                insert_dict.update(was_id = self.domain_id\
                            , was_instance_id = server['name']
                            , webconnection_id = webconn['listener-id'])

                update_webtob_a.append(update_dict)
                insert_webtob_a.append(insert_dict)   

        return insert_http_a, update_http_a, insert_webtob_a, update_webtob_a

class JeusDomainFactory:
    def jeus_domain(self, h):
        return h.upsertJeusDomain()

    def jeus_web_connection(self, h):
        return h.upsertWebConnection()
