from app import db
from app.models.was import MwServer
from app.models.common import LocationEnum, OSEnum, EncodingEnum, RunEnum, YnEnum
from sqlalchemy.exc import IntegrityError
import logging
from datetime import datetime
from flask import g
from app.api.errors import internal_error_message

def get_servers(host_id=None):
    """Retrieve one or all servers"""
    if host_id:
        return db.session.query(MwServer).filter_by(host_id=host_id).first()
    return db.session.query(MwServer).all()

def add_server(data):
    """Create a new server record"""
    try:
        if not data.get('host_id'):
            return None, "host_id is required"
            
        exists = db.session.query(MwServer).filter_by(host_id=data['host_id']).first()
        if exists:
            return None, f"Server {data['host_id']} already exists"
            
        server = MwServer()
        _update_server_fields(server, data)
        
        db.session.add(server)
        db.session.commit()
        return server, "OK"
    except Exception:
        db.session.rollback()
        return None, internal_error_message("mwm add_server Error")

def update_server(host_id, data):
    """Update an existing server record"""
    try:
        server = db.session.query(MwServer).filter_by(host_id=host_id).first()
        if not server:
            return None, f"Server {host_id} not found"
            
        _update_server_fields(server, data)
        db.session.commit()
        return server, "OK"
    except Exception:
        db.session.rollback()
        return None, internal_error_message("mwm update_server Error")

def delete_server(host_id):
    """Delete a server record"""
    try:
        server = db.session.query(MwServer).filter_by(host_id=host_id).first()
        if not server:
            return None, f"Server {host_id} not found"
            
        db.session.delete(server)
        db.session.commit()
        return True, "OK"
    except Exception:
        db.session.rollback()
        return False, internal_error_message("mwm delete_server Error")

def _update_server_fields(server, data):
    """Internal helper to set fields from dict, handling Enums"""
    if 'host_id' in data: server.host_id = data['host_id']
    if 'server_name' in data: server.server_name = data['server_name']
    
    enums = {
        'landscape': LocationEnum,
        'os_type': OSEnum,
        'encoding': EncodingEnum,
        'running_type': RunEnum,
        'use_yn': YnEnum
    }
    
    for field, enum_class in enums.items():
        if field in data and data[field]:
            try:
                # Try by Name (e.g., 'PROD')
                setattr(server, field, enum_class[data[field]])
            except KeyError:
                # Try by Value (e.g., '운영')
                try:
                    setattr(server, field, enum_class(data[field]))
                except ValueError:
                    pass

    if 'jdk_version' in data: server.jdk_version = data['jdk_version']
    if 'ip_address' in data: server.ip_address = data['ip_address']
    if 'vip_address' in data: server.vip_address = data['vip_address']
    if 'primary_host_id' in data: server.primary_host_id = data['primary_host_id']
    if 'dr_host_id' in data: server.dr_host_id = data['dr_host_id']
    
    if g and g.user:
        server.user_id = g.user.username
    server.create_on = datetime.now()
