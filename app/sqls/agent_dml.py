import logging
from app import db
from .jeus_dml import JeusDomain, JeusDomainFactory, OldJeusDomain, NewJeusDomain
from .webtob_dml import WebtobHttpm, WebtobHttpmFactory, NewHttpm, httpm_to_dict
from app.sqls.was import get_was_instance_id, get_domain_id_as_pk
from app.sqls.agent import update_result_status, update_was_status, get_result, get_autorun_func\
    , send_command_immediately, get_or_insert_command_type, insert_command_master\
    , get_command_master
from app.sqls.monitor import update_rows, insert_row, select_row, select_rows
from app.sqls.relationship import get_dependent_was_id
from app.models.common import get_date
from datetime import datetime, timedelta
from deepdiff import DeepDiff
import json
import xmltodict
import sys
import re
import csv
from io import StringIO
from sqlalchemy.dialects.postgresql import insert

class AutorunResult:

    def __init__(self, result=None, result_id=None):
        if result!=None:
            self.result = result
        elif result_id!=None:
            self.result = get_result(result_id)
        else:
            self.result=None

    def get_autorun_func(self):

        if self.result.ag_command_detail.command_class.name == 'DownloadFile':
            return None, None

        real_key_value1 = self._get_real_key_value1(self.result.key_value1)

        return get_autorun_func(self.result.command_id, real_key_value1)

    def _get_real_key_value1(self, key_value1):

        real_key_value1 = key_value1

        n_list = key_value1.rsplit('.',1)

        if len(n_list) == 2 and len(n_list[1]) == 12:
            rec = get_command_master(n_list[1])
            if rec:
                real_key_value1 = n_list[0]

        return real_key_value1

    def call_autorun_func(self):

        autorunFunc, autorunParam = self.get_autorun_func()

        if not autorunFunc:
            return 0, 'No Autorun'

        func = None

        try:
            func = getattr(self, autorunFunc)
        except AttributeError as e:
            return -1, autorunFunc + ': Not Exists'

        try:

            if autorunParam:
                rtn, msg = func(autorunParam, self.result.command_id)
            else:
                rtn, msg = func()

            code = 'COMPLITED' if rtn > 0 else 'NOCHANGE' if rtn==0 else 'ERROR'
            self.update_result_status(code, msg)

        except Exception as e:
            db.session.rollback()
            excType, excValue, traceback = sys.exc_info()
            logging.error(f'AutorunResult.callAutorunFunc Error : autorunFunc: {autorunFunc} autorunParam: {autorunParam} command_id: {self.result.command_id}')
            logging.error(f'AutorunResult.callAutorunFunc Error : 1{excType} 2{excValue} 3{traceback}')
            self.update_result_status('ERROR', str(excValue))

        return 1, 'OK'

    def __get_domain_info(self):

        result = self.result

        file_name = result.key_value1
        file_path = result.key_value2

        content   = result.result_text
        host_id   = result.host_id.lower()
        agent_id  = result.agent_id

        if result.ag_command_detail.command_class.name == 'ExeAgentFunc':
            sys_user = ''
        else:
            sys_user = agent_id[agent_id.find('_')+1:agent_id.rfind('_')]

        #Getting domain id from file_path ex) /sw/jeus/domains/PPRM_Domain/config
        real_domain_id = ''
        if 'domain' in file_name and file_name.endswith('.xml'):
            real_domain_id = file_path[file_path.find('domains')+8:file_path.find('config')-1]

        elif 'JEUSMain' in file_name:
            fpl = file_path.split('/')
            real_domain_id = fpl[fpl.index('config')-1]

        domain_id = get_domain_id_as_pk(host_id, real_domain_id)
        # 예외로직 : utc10t 두번째 jeusok 의 domain id를 jeusok2_dev로 고정
        if host_id == 'uok01a' and 'usropt01/jeus60/jeusok' in file_path:
            domain_id = 'jeusok2_dev'

        return dict(
            host_id = host_id,
            domain_id = domain_id,
            content = content,
            sys_user = sys_user,
            agent_id = agent_id,
        )

    def update_jeus_domain(self):
        domain_info = self.__get_domain_info()
        return AutorunResult.update_domain(domain_info)

    @classmethod
    def update_domain(cls, domain_info, skip_check=False):

        doc        = xmltodict.parse(domain_info['content'])
        json_type  = json.dumps(doc)
        dict2_type = json.loads(json_type)
        
        domain = dict2_type['domain'] if dict2_type.get('domain') else dict2_type['jeus-system'] if dict2_type.get('jeus-system') else None

        if not domain:
            return -1, 'domain item doesn\'t exist'

        rec, _ = select_row('mw_was',{'was_id':domain_info['domain_id']})
        
        if not skip_check and rec and rec.was_object:

            diff = DeepDiff(rec.was_object, domain, ignore_order=True)

            #Not changed
            if not diff:
                update_rows('mw_was', {'create_on': datetime.now()}, {'was_id': domain_info['domain_id']})
                return 0, 'Not changed'

            insert_dict = dict(
                mw_was_id      = rec.id,
                old_was_object = rec.was_object,
                changed_object = diff.to_json(),
                old_was_text   = rec.was_text,
            )

            insert_row('mw_was_change_history', insert_dict)
        
        fac = JeusDomainFactory()
        
        param = dict(
            domain_id = domain_info['domain_id'],
            host_id   = domain_info['host_id'],
            domain    = domain,
            raw_data  = domain_info['content'],
            sys_user  = domain_info['sys_user'],
            agent_id  = domain_info['agent_id'],
        )

        if dict2_type.get('domain'):
            jeus = NewJeusDomain(**param)
        elif dict2_type.get('jeus-system'):
            jeus = OldJeusDomain(**param)

        rtn , msg = fac.jeus_domain(jeus)
        
        return rtn, msg

    def update_url_rewrite(self):

        result = self.result
        
        filter_dict = dict(command_id=result.command_id)
        cmaster, _ = select_row('ag_command_master', filter_dict)

        urlrewrite_config = cmaster.additional_params

        update_dict = dict(
            urlrewrite_text = result.result_text
           ,urlrewrite_update_date = datetime.now()
        )

        host_id   = result.host_id.lower()

        filter_dict = dict(
            host_id           = host_id
           ,urlrewrite_config = urlrewrite_config
        )

        update_rows('mw_web_vhost', update_dict, filter_dict)

        return 1, ''

    def update_file_ssl_by_api(self):

        result = self.result

        result_text   = result.result_text
        certi = json.loads(result_text)

        logging.info(f'certi : {certi}')

        ssl_certi = certi['certifile']

        notbefore, notafter = self._get_ssl_datetime(certi)

        update_dict = dict(
            notbefore = notbefore
           ,notafter  = notafter
           ,subject   = certi['subject']
           ,serial    = certi['serial']
           ,issuer    = certi['issuer']
           ,update_dt = datetime.now()
            )

        host_id   = result.host_id.lower()

        filter_dict = dict(
            host_id   = host_id
           ,ssl_certi = ssl_certi
        )

        return update_rows('mw_web_ssl', update_dict, filter_dict)

    def _get_ssl_datetime(self, certi):

        if 'GMT' in certi['notbefore']:
            notbefore = datetime.strptime(certi['notbefore'], "%a %b %d %H:%M:%S %Z %Y")\
                        + timedelta(hours=9)

            notafter  = datetime.strptime(certi['notafter'], "%a %b %d %H:%M:%S %Z %Y")\
                        + timedelta(hours=9)
        else:
            notbefore = datetime.strptime(certi['notbefore'], "%a %b %d %H:%M:%S KST %Y")
            notafter  = datetime.strptime(certi['notafter'], "%a %b %d %H:%M:%S KST %Y")

        return notbefore, notafter

    def update_connect_ssl_by_api(self):

        result = self.result
        result_text   = result.result_text
        result_dict = json.loads(result_text)

        host_id   = result.host_id.lower()
        domain_full = result_dict.get('domain_name', result_dict.get('domain', ''))
        
        domain = ''
        port = ''

        if ':' in domain_full:
            domain, port = domain_full.split(':', 1)
        else:
            domain = domain_full
            port = result_dict.get('port')

        # result에 정보가 부족한 경우 command의 additional_params에서 보충
        if not domain or not port:
            cmaster = get_command_master(result.command_id)
            if cmaster and cmaster.additional_params:
                try:
                    # JSON 형태인 경우 (신규)
                    params = json.loads(cmaster.additional_params)
                    if not domain: domain = params.get('domain_name', '')
                    if not port: port = str(params.get('port', ''))
                except:
                    # domain:port 문자열 형태인 경우 (기존)
                    if ':' in cmaster.additional_params:
                        p_domain, p_port = cmaster.additional_params.split(':', 1)
                        if not domain: domain = p_domain
                        if not port: port = p_port

        # 최종적으로 port가 없는 경우 기본값 443 사용
        if not port:
            port = '443'

        filter_dict = dict(
            host_id     = host_id
           ,domain_name = domain
           ,port        = str(port)
        )

        update_dict = dict(
            update_dt = datetime.now()
            )

        if result_dict['certs']:

            certi = next( r for r in result_dict['certs'] if r['index']=="1")

            notbefore, notafter = self._get_ssl_datetime(certi)

            update_dict.update(
                dict(
                notbefore = notbefore
            ,notafter  = notafter
            ,subject   = certi['subject']
            ,serial    = certi['serial']
            ,issuer    = certi['issuer']
                )
            )

            certi_ca = next(( r for r in result_dict['certs'] if r['index']=="2"), None )

            if certi_ca:
                notbefore_ca, notafter_ca = self._get_ssl_datetime(certi_ca)
                update_dict.update(
                    dict(
                     notbefore_ca = notbefore_ca
                    ,notafter_ca  = notafter_ca
                    ,subject_ca   = certi_ca['subject']
                    ,serial_ca    = certi_ca['serial']
                    ,issuer_ca    = certi_ca['issuer']
                    )
                )
        else:
            update_dict.update(
                dict(
                    notbefore = None,
                    notafter  = None,
                    subject   = "No Valid Certificate.",
                    serial    = None,
                    issuer    = None,
                    notbefore_ca = None,
                    notafter_ca  = None,
                    subject_ca   = None,
                    serial_ca    = None,
                    issuer_ca    = None
                )
            )

        rtn, msg = update_rows('mw_web_domain', update_dict, filter_dict)

        # mw_web_domain에 해당 레코드가 없으면 → mw_etc_ssl_domain에 upsert
        if rtn < 0:
            etc_filter = dict(
                host_id     = host_id,
                domain_name = domain,
                port        = port
            )

            etc_rec, _ = select_row('mw_etc_ssl_domain', etc_filter)

            etc_update = dict(**update_dict, agent_id=result.agent_id)

            if etc_rec:
                rtn, msg = update_rows('mw_etc_ssl_domain', etc_update, etc_filter)
            else:
                insert_dict = dict(**etc_filter, **etc_update)
                rtn, msg = insert_row('mw_etc_ssl_domain', insert_dict)
                if rtn > 0:
                    msg = 'Inserted into mw_etc_ssl_domain'

        return rtn, msg

    def update_connect_ssl(self):

        result = self.result

        content   = result.result_text
        host_id   = result.host_id.lower()

        ssl_dict = self._parse_ssl_info(content)

        domain_full = ssl_dict.get('domain_name', ssl_dict.get('domain', ''))
        if not domain_full:
            return -1, 'Domain doesn\'t exist'

        if ':' not in domain_full:
            return -1, 'Domain isn\'t valid'

        #if not ssl_dict.get('serial'):
        #    return -1, 'Serial doesn\'t exist'

        if not ssl_dict.get('notafter') or not ssl_dict['notafter']:
            update_dict = dict(
                subject   = 'Connection Failed'
               ,update_dt = datetime.now()
            )

            #return -1, 'NotAfter isn\'t valid'
        else:
            update_dict = dict(
                notbefore = ssl_dict['notbefore']
               ,notafter  = ssl_dict['notafter']
                ,subject   = ssl_dict['subject']
               ,serial    = ssl_dict['serial']
               ,issuer    = ssl_dict['issuer']
               ,update_dt = datetime.now()
            )

        domain, port = domain_full.split(':', 1)

        filter_dict = dict(
            host_id     = host_id
           ,domain_name = domain
           ,port        = port
        )

        return update_rows('mw_web_domain', update_dict, filter_dict)

    def update_file_ssl(self):

        result = self.result

        content   = result.result_text
        host_id   = result.host_id.lower()

        ssl_dict = self._parse_ssl_info(content)

        if not ssl_dict.get('file'):
            return -1, 'SSL file doesn\'t exist'

        if not ssl_dict.get('serial'):
            return -1, 'Serial doesn\'t exist'

        if not ssl_dict.get('notafter') or not ssl_dict['notafter']:
            return -1, 'NotAfter isn\'t valid'

        ssl_certi = ssl_dict['file']

        update_dict = dict(
            notbefore = ssl_dict['notbefore']
           ,notafter  = ssl_dict['notafter']
           ,subject   = ssl_dict['subject']
           ,serial    = ssl_dict['serial']
           ,issuer    = ssl_dict['issuer']
           ,update_dt = datetime.now()
        )

        filter_dict = dict(
            host_id     = host_id
           ,ssl_certi   = ssl_certi
        )

        return update_rows('mw_web_ssl', update_dict, filter_dict)

    def _parse_ssl_info(self, content):

        item_names = ['file','domain','domain_name','notbefore','notafter','subject','serial','issuer']
        rtn_dict = {}
        info_list = content.splitlines()

        for l in info_list:

            tlist = [ i.strip() for i in l.split('=',1) ]

            if len(tlist)==2 and tlist[0].lower() in item_names:

                if tlist[0].lower() in ['notbefore','notafter']:

                    try:
                        if 'GMT' in tlist[1]:
                            dt = datetime.strptime(tlist[1], '%b %d %H:%M:%S %Y %Z')\
                                + timedelta(hours=9)
                        else:
                            dt = datetime.strptime(tlist[1], '%b %d %H:%M:%S %Y %Z')

                    except ValueError:
                        dt = None

                    rtn_dict.update({tlist[0].lower():dt})
                else:
                    rtn_dict.update({tlist[0].lower():tlist[1]})

        return rtn_dict

    def update_httpm(self):

        result = self.result

        file_name = result.key_value1
        file_path = result.key_value2
        content   = result.result_text
        host_id   = result.host_id.lower()

        domain_id = ""

        agent_id = result.agent_id

        if result.ag_command_detail.command_class.name == 'ExeAgentFunc':
            sys_user = ''
        else:
            sys_user = agent_id[agent_id.find('_')+1:agent_id.rfind('_')]

        return self._update_httpm(host_id, content, sys_user=sys_user\
                        , domain_id=domain_id, agent_id=agent_id)

    def _update_httpm(self, host_id, content, sys_user='', domain_id='', agent_id=''):

        httpm = httpm_to_dict(content)

        if not httpm['NODE'][0].get('JSVPORT'):
            httpm['NODE'][0]['JSVPORT'] = 0

        if httpm['NODE'][0].get('PORT'):
            tmp = httpm['NODE'][0]['PORT']
            port = int(tmp.split(',')[0])
        else:
            port = 0
            httpm['NODE'][0]['PORT'] = "0"

        rec, _ = select_row('mw_web',{'host_id':host_id,'port':port})

        if rec:
            diff = DeepDiff(rec.httpm_object, httpm, ignore_order=True)

            #Not changed
            if not diff:
                update_rows('mw_web', {'create_on': datetime.now()}, {'host_id': host_id, 'port': port})
                return 0, 'Not changed'

            insert_dict = dict(
                mw_web_id         = rec.id,
                old_httpm_object  = rec.httpm_object,
                changed_object    = diff.to_json(),
                old_web_text      = rec.web_text,
            )

            insert_row('mw_web_change_history', insert_dict)

        fac = WebtobHttpmFactory()
        
        httpm = NewHttpm(
            host_id, 
            httpm,
            raw_data  = content,
            sys_user  = sys_user, 
            domain_id = domain_id, 
            agent_id  = agent_id
        )
        
        rtn , msg = fac.webtobHttpm(httpm)
        return rtn, msg

    def update_web_main(self):

        result = self.result

        file_name = result.key_value1
        file_path = result.key_value2

        content   = result.result_text
        host_id   = result.host_id.lower()

        fpl = file_path.split('/')
        real_domain_id = fpl[fpl.index('config')-1]

        domain_id = get_domain_id_as_pk(host_id, real_domain_id)
        # 예외로직 : utc10t 두번째 jeusok 의 domain id를 jeusok2_dev로 고정
        if host_id == 'uok01a' and 'usropt01/jeus60/jeusok' in file_path:
            domain_id = 'jeusok2_dev'

        if file_path[-1:] in ['/','\\']:
            file_path = file_path[:-1]

        #예) '/usropt02/jeus/config/urt02a/urt02a_servlet_rehi2' => 'rehi2'
        engine_command_cand1 = file_path.split('_')[-1:][0]
        #예) '/usropt02/jeus/config/urt02a/urt02a_servlet_rehi2' => '2'
        engine_command_cand2 = file_path[-1:]
        
        was_instance_id = get_was_instance_id(host_id, domain_id, engine_command_cand1)
        if not was_instance_id:
            was_instance_id = get_was_instance_id(host_id, domain_id, engine_command_cand2)

        if not was_instance_id:
            return -1, 'was_instance_id doesn\'t exist'

        return self._update_web_main(host_id, domain_id, was_instance_id, content)
        
    def _update_web_main(self, host_id, domain_id, was_instance_id, content):

        doc        = xmltodict.parse(content)
        json_type  = json.dumps(doc)
        dict2_type = json.loads(json_type)
        
        domain = dict2_type['web-container']
        domain.update(name=was_instance_id)
        
        fac = JeusDomainFactory()
        jeusDomain = OldJeusDomain(domain_id, host_id, domain, doc)
        rtn , _ = fac.jeus_web_connection(jeusDomain)
        
        return rtn, ''

    def read_out_file(self, command_type_id, command_id):
        rtn , _ = insert_command_master(command_type_id, [self.result.agent_id])
        return rtn, ''

    def read_cid_out_file(self, command_type_id, command_id):
        rtn , _ = insert_command_master(command_type_id, [self.result.agent_id], command_id)
        return rtn, ''

    def update_jeus_license_info(self):

        result = self.result

        content   = result.result_text

        re_dict = self._parse_jeus_license_info(content)

        logging.info(f're_dict : {re_dict}')

        if not re_dict.get('domain'):
            return -1, 'No data found'

        update_dict = dict(
            license_cpu         = re_dict['cpu'] if re_dict.get('cpu') else 0
           ,license_edition     = re_dict['edition'] if re_dict.get('edition') else ''
           ,license_hostname    = re_dict['host-name'] if re_dict.get('host-name') else ''
           ,license_issue_date  = re_dict['issue-day'] if re_dict.get('issue-day') else None
           ,license_due_date    = re_dict['due-day'] if re_dict.get('due-day') else None
           ,license_text        = content
           ,license_update_date = get_date()
           ,version_info        = re_dict['version-info'] if re_dict.get('version-info') else None
        )

        filter_dict = dict(
            was_id     = re_dict['domain']
        )

        return update_rows('mw_was', update_dict, filter_dict)

    def _parse_jeus_license_info(self, content):

        item_names = ['domain','edition','issue-day','cpu','host-name','due-day']
        rtn_dict = {}
        info_list = content.splitlines()

        for line in info_list:

            l = line.strip('=')
            tlist = [ i.strip() for i in l.split(':',1) ]

            if len(tlist)==1 and len(l) > 0 and l[0].isdigit():
                rtn_dict.update({'version-info':l})

            elif len(tlist)==2 and tlist[0].lower() in item_names:

                if tlist[0].lower() in ['issue-day','due-day']:

                    try:
                        dt = datetime.strptime(tlist[1], '%Y/%m/%d')
                    except ValueError:
                        dt = None

                    rtn_dict.update({tlist[0].lower():dt})
                elif tlist[0].lower() == 'cpu':
                    if tlist[1] == 'unlimited':
                        rtn_dict.update({tlist[0].lower():0})
                    else:
                        rtn_dict.update({tlist[0].lower():int(tlist[1])})
                else:
                    rtn_dict.update({tlist[0].lower():tlist[1]})

        return rtn_dict

    def update_filtered_info(self):

        result = self.result

        content   = result.result_text

        re_dict = self._parse_filtered_info(content)

        if not re_dict.get('domain'):
            return -1, 'No data found'

        update_dict = dict(
            filtered_text        = content
           ,filtered_update_date = get_date()
        )

        filter_dict = dict(
            was_id     = re_dict['domain']
           ,application_home = re_dict['application_home']
        )

        return update_rows('mw_application', update_dict, filter_dict)

    def _parse_filtered_info(self, content):

        item_names = ['domain','application_home']
        rtn_dict = {}
        info_list = content.splitlines()

        for line in info_list:

            tlist = [ i.strip() for i in line.split(':',1) ]

            if len(tlist)==2 and tlist[0].lower() in item_names:

                rtn_dict.update({tlist[0].lower():tlist[1]})

        return rtn_dict

    def update_webtob_license_info(self):

        result = self.result

        content   = result.result_text

        re_dict = self._parse_webtob_license_info(content)

        if not re_dict.get('host_id'):
            return -1, 'No data found'

        update_dict = dict(
            license_cpu         = re_dict['cpu'] if re_dict.get('cpu') else 0
           ,license_edition     = re_dict['edition'] if re_dict.get('edition') else ''
           ,license_hostname    = re_dict['license check by hostname'] if re_dict.get('license check by hostname') else ''
           ,license_issue_date  = re_dict['license issue date'] if re_dict.get('license issue date') else None
           ,license_text        = content
           ,license_update_date = get_date()
        )

        filter_dict = dict(
            host_id  = re_dict['host_id']
           ,port     = re_dict['port']
        )

        return update_rows('mw_web', update_dict, filter_dict)

    def _parse_webtob_license_info(self, content):

        item_names = ['domain','edition','license issue date','license check by hostname']
        rtn_dict = {}
        info_list = content.splitlines()

        for l in info_list:

            tlist = [ i.strip() for i in l.split(':',1) ]

            if len(tlist)==2 and tlist[0].lower() in item_names:

                if tlist[0].lower() == 'license issue date':

                    try:
                        dt = datetime.strptime(tlist[1], '%Y/%m/%d')
                    except ValueError:
                        dt = None

                    rtn_dict.update({tlist[0].lower():dt})
                elif tlist[0] == 'domain':
                    host_id, port = tlist[1].split('__')
                    rtn_dict.update({'host_id':host_id, 'port':int(port)})
                else:
                    rtn_dict.update({tlist[0].lower():tlist[1]})
            elif 'CPU license' in l:
                cpu = re.findall(r'\d+', l)
                rtn_dict.update({'cpu':int(cpu[0])})

        return rtn_dict

    def update_was_status(self):

        result = self.result

        rtn, _ = update_was_status(result.key_value2, result.result_text, result.host_id)

        return rtn, ''

    def update_jeus_properties(self):

        result = self.result

        #혹시 한 jeus에 여러 domain이 설치된 경우도 있을 수 있어서
        was_ids = self._get_was_id_for_jeus_home(result.agent_id, result.key_value2)

        if not was_ids:
            return 0, 'WAS not found'

        update_dict = dict(
            jeus_properties_text = result.result_text
           ,jeus_properties_update_date = datetime.now()
        )

        for was_id in was_ids:

            filter_dict = dict(
                was_id           = was_id
            )

            update_rows('mw_was', update_dict, filter_dict)

        return 1, ''

    def update_webtob_monitor(self):

        result = self.result

        row, _ = select_row('mw_web',{'agent_id':result.agent_id})
        
        if not row:
            return 0, 'WEB not found'

        dicts = self.__get_si(result.result_text, result.create_on.strftime('%Y.%m.%d %H:%M'))

        for r in dicts:
            srow, _ = select_row('mw_web_server',{'svr_id':r['svr_id'],'mw_web_id':row.id})

            if srow:
                srow.monitor_now = r

                tmp = dict()
                if srow.monitor_history:
                    tmp = srow.monitor_history
                else:
                    tmp = {'history':[]}

                tmp['history'].append(r)
                srow.monitor_history = tmp

        return 1, ''

    def __get_si(self, result, date):

        array_ = []
        
        for line in result.splitlines():
            if not line.strip():
                continue

            logging.info(f'line : {line}')
            ll = [ t for t in line.split(' ') if t and '(' not in t and ')' not in t]
            
            array_.append(
                dict(
                    svr_id = ll[1],
                    status = ll[2],
                    regs   = ll[3],
                    count  = ll[4],
                    cqcnt  = ll[5],
                    aqcnt  = ll[6],
                    qpcnt  = ll[7],
                    emcnt  = ll[8],
                    rscnt  = ll[9],
                    rbcnt  = ll[10],
                    date   = date,
                )
            )

        return array_

    def update_webtob_version(self):

        result = self.result

        row, _ = select_row('mw_web',{'agent_id':result.agent_id})
        
        if not row:
            return 0, 'WEB not found'

        row.version_info = result.result_text

        return 1, ''

    def _get_was_id_for_jeus_home(self, agent_id, jeusprop_location):

        filter_dict = dict(
            mapping_key = 'DOMAIN_HOME'
           ,agent_id    = agent_id
           ,string_to_replace = jeusprop_location
        )

        recs, _ = select_rows('ag_command_helper', filter_dict)

        if recs:
            return [ r.target_file_name for r in recs]

        filter_dict = dict(
            agent_id    = agent_id
        )

        recs, _ = select_rows('mw_was', filter_dict)
        
        if recs:
            return [ r.was_id for r in recs]

        return None

    def restartMWAgent(self):

        result = self.result

        if result.ag_command_detail.ag_agent.agent_sub_type != None:
            return -1, 'agent_sub_type is not defined.'

        _restartShell = {
            'WIN_JEUS8' :'run.agent.bat'
           ,'WIN_JEUS7' :'run.agent4j7.bat'
           ,'WIN_JEUS6' :'run.agent4j6.bat'
           ,'UNIX_JEUS6':'run.agent4j6.sh'
           ,'UNIX_JEUS8':'run.agent.sh'
        }

        agent_sub_type = result.ag_command_detail.ag_agent.agent_sub_type.name
        
        command_type_id = get_or_insert_command_type('ExeShell'
           ,target_file_name=_restartShell[agent_sub_type])

        rtn, _ = send_command_immediately(result.agent_id, command_type_id)

        return rtn, ''

    def update_result_status(self, code, message):

        update_dict = dict(
            result_status  = code
           ,complited_date = datetime.now()
           ,result_message = message
        )

        filter_dict = dict(id = self.result.id)

        update_rows('ag_result', update_dict, filter_dict)

    def update_gc_parsed_log(self):
        result = self.result
        content = result.result_text
        host_id = result.host_id.lower()
        
        if not content:
            return 0, 'No data found'
            
        f = StringIO(content)
        reader = csv.reader(f)
        try:
            next(reader) # 헤더 스킵
        except StopIteration:
            return -1, 'Empty CSV'

        insert_data_list = []
        for row in reader:
            if len(row) < 4:
                continue
                
            was_instance_id = row[0]
            try:
                start_date = datetime.strptime(row[1], "%Y-%m-%dT%H:%M:%S.%f")
                duration = float(row[2])
                end_date = datetime.strptime(row[3], "%Y-%m-%dT%H:%M:%S.%f")
            except ValueError:
                continue
            
            insert_data_list.append({
                'host_id': host_id,
                'was_instance_id': was_instance_id,
                'start_date': start_date,
                'duration': duration,
                'end_date': end_date
            })
            
        if not insert_data_list:
            return 0, 'No valid data to insert'
            
        from app.models.monitor import MoGcParsedLog
        stmt = insert(MoGcParsedLog).values(insert_data_list)
        do_nothing_stmt = stmt.on_conflict_do_nothing(
            index_elements=['host_id', 'was_instance_id', 'start_date']
        )
        db.session.execute(do_nothing_stmt)
        return 1, 'OK'

    def log_2_knowledge(self):
        from app.common import jsonl_to_markdown
        from app.models.common import get_date
        import json
        
        result = self.result
        content = result.result_text
        
        if not content:
            return 0, 'No data found'
            
        try:
            jsonl_md = jsonl_to_markdown(content)
        except Exception as e:
            return -1, f"Markdown conversion failed: {str(e)}"
            
        # 파라미터 파싱
        file_val = ''
        start_val = ''
        end_val = ''
        keywords_val = ''
        try:
            if result.ag_command_detail and result.ag_command_detail.additional_params:
                params = json.loads(result.ag_command_detail.additional_params)
                file_val = params.get('file', '')
                
                target_date = params.get('targetDate', '')
                if target_date:
                    start_time = params.get('startTime', '')
                    end_time = params.get('endTime', '')
                    start_val = target_date + start_time
                    end_val = target_date + end_time
                else:
                    start_val = params.get('start', '')
                    end_val = params.get('end', '')
                    
                keywords_val = params.get('keywords', '')
        except Exception:
            pass

        # DB에서 WAS 정보 조회
        from app.models.was import MwWasInstance
        host_id = result.host_id.lower() if result.host_id else ''
        file_path = result.key_value2 or ''
        # 파일경로에서 최하위 디렉토리명 추출
        parts = file_path.rstrip('/').rstrip('\\').replace('\\', '/').split('/')
        was_instance_id = parts[-1] if parts else ''
        
        was_name = ''
        was_id = ''
        located_host_id = ''
        instance_id = ''
        instance_host_id = ''
        
        if host_id and was_instance_id:
            # 여러건이 나올 경우 첫번째 row만 취함
            instance = db.session.query(MwWasInstance).filter_by(
                host_id=host_id, was_instance_id=was_instance_id
            ).first()
            
            if instance:
                instance_id = instance.was_instance_id or ''
                instance_host_id = instance.host_id or ''
                if instance.mw_was:
                    was_name = instance.mw_was.was_name or ''
                    was_id = instance.mw_was.was_id or ''
                    located_host_id = instance.mw_was.located_host_id or ''

        # content_md 구성
        markdown_text = f"""## Log 추출 기준
- WAS 이름: {was_name} 
- WAS Domain id : {was_id}
- WAS 설치 서버 : {located_host_id}
- WAS instance id : {instance_id}
- WAS instance 실행 서버 : {instance_host_id}
- Log 파일 : {file_val}
- 발생 기간 : {start_val} ~ {end_val}
- 추출 문자열 : {keywords_val}
## Log 추출 내용
{jsonl_md}"""

        # content_name 구성
        formatted_start = start_val
        if len(start_val) >= 12:
            try:
                # ex) 202608271230 -> 2026.08.27 12:30
                dt_str = start_val[:14].replace(' ', '').replace('-','').replace(':','')
                if len(dt_str) >= 12:
                    from datetime import datetime
                    dt = datetime.strptime(dt_str[:12], "%Y%m%d%H%M")
                    formatted_start = dt.strftime("%Y.%m.%d %H:%M")
            except Exception:
                pass

        content_name = f"Log Extracted - {host_id} - {was_instance_id} - {formatted_start}"
        search_tags = f"command_id={result.command_id}"
        
        insert_dict = dict(
            content_name = content_name,
            content_md = markdown_text,
            search_tags = search_tags
        )
        
        from app.sqls.monitor import insert_row
        rtn, msg = insert_row('ut_md_content', insert_dict)
        
        # 지식유형-LOG추출 태그 맵핑
        if rtn > 0:
            from app.models.knowledge import UtTag, UtMdContent
            target_tag = db.session.query(UtTag).filter_by(tag='지식유형-LOG추출').first()
            if target_tag:
                md_content = db.session.query(UtMdContent).get(rtn)
                if md_content:
                    md_content.ut_tag.append(target_tag)
                    db.session.commit()

        return rtn, msg
