from app import db
from sqlalchemy.orm import aliased
from app.models.was import MwWasInstance, MwServer, MwWas, MwWeb, MwWaschangeHistory\
            , MwWebchangeHistory

def get_next_old_was_text(id):
    # Aliases for self-join
    current_data = aliased(MwWaschangeHistory)
    next_data = aliased(MwWaschangeHistory)

    # Query to get the specific data
    specific_data = db.session.query(current_data).filter(current_data.id == id).one()

    # Subquery to find the next data
    subquery = (db.session.query(next_data)
                .filter(next_data.mw_was_id == specific_data.mw_was_id,
                        next_data.create_on > specific_data.create_on)
                .order_by(next_data.create_on)
                .limit(1)
                .subquery())

    # Query to get the old_was_text of the next data
    next_data_query = (db.session.query(next_data.old_was_text)
                       .select_entity_from(subquery))

    # Execute the query
    next_data_result = db.session.execute(next_data_query).scalar()

    if next_data_result:
        next_old_was_text = next_data_result
    else:
        # Query to get MwWas.was_text if there is no next data
        was_text_query = (db.session.query(MwWas.was_text)
                          .filter(MwWas.id == specific_data.mw_was_id))
        
        next_old_was_text = db.session.execute(was_text_query).scalar()

    return specific_data.old_was_text, next_old_was_text

def get_next_old_web_text(id):
    # Aliases for self-join
    current_data = aliased(MwWebchangeHistory)
    next_data = aliased(MwWebchangeHistory)

    # Query to get the specific data
    specific_data = db.session.query(current_data).filter(current_data.id == id).one()

    # Subquery to find the next data
    subquery = (db.session.query(next_data)
                .filter(next_data.mw_web_id == specific_data.mw_web_id,
                        next_data.create_on > specific_data.create_on)
                .order_by(next_data.create_on)
                .limit(1)
                .subquery())

    # Query to get the old_was_text of the next data
    next_data_query = (db.session.query(next_data.old_web_text)
                       .select_entity_from(subquery))

    # Execute the query
    next_data_result = db.session.execute(next_data_query).scalar()

    if next_data_result:
        next_old_web_text = next_data_result
    else:
        # Query to get MwWeb.web_text if there is no next data
        web_text_query = (db.session.query(MwWeb.web_text)
                          .filter(MwWeb.id == specific_data.mw_web_id))
        
        next_old_web_text = db.session.execute(web_text_query).scalar()

    return specific_data.old_web_text, next_old_web_text

def get_changed_was(create_on=None):

    recs = None

    if create_on:
        recs = db.session.query(MwWaschangeHistory)\
            .filter(MwWaschangeHistory.create_on>=create_on)\
            .order_by(MwWaschangeHistory.create_on.desc()).all()
    
    if recs:
        return recs
    else:
        return None 

def get_changed_web(create_on=None):

    recs = None

    if create_on:
        recs = db.session.query(MwWebchangeHistory)\
            .filter(MwWebchangeHistory.create_on>=create_on)\
            .order_by(MwWebchangeHistory.create_on.desc()).all()
    
    if recs:
        return recs
    else:
        return None 

def get_was_instance_id(host_id, domain_id, engine_command):
    if host_id:
        host_id = host_id.lower()

    was_instance_rec = db.session.query(MwWasInstance)\
                    .filter(MwWasInstance.host_id==host_id
                        , MwWasInstance.was_id==domain_id
                        , MwWasInstance.engine_command.like('%'+engine_command+'%')).first()
    if was_instance_rec:
        return was_instance_rec.was_instance_id
    else:
        return None

def get_domain_id_as_pk(host_id, real_domain_id, second=False):
    if host_id:
        host_id = host_id.lower()

    #차세대
    if real_domain_id.find('_Domain') >= 0:
        domain_id = real_domain_id
    #ASIS
    else:
        
        landscape = get_landscape(host_id)

        #운영국외점포 분기
        if host_id in ['uok01a','uok02d']:
            real_domain_id = real_domain_id + '_A'
        elif host_id in ['uok03a','uok04d']:
            real_domain_id = real_domain_id + '_L'
        elif host_id in ['uok05a','uok06d']:
            real_domain_id = real_domain_id + '_N'
            
        if landscape == 'TEST' or real_domain_id == 'jeusei2':
            domain_id = real_domain_id + '_test'
        elif landscape == 'DEV':
            domain_id = real_domain_id + '_dev'
        else:
            domain_id = real_domain_id

    if second==True:
        domain_id += '2'

    return domain_id

def get_landscape(host_id):
    if host_id:
        host_id = host_id.lower()

    print('HH :',host_id)
    server_rec = db.session.query(MwServer)\
                    .filter(MwServer.host_id==host_id).first()
    if server_rec:
        return server_rec.landscape.name
    else:
        return None
