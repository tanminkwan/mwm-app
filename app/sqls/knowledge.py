
from app import db
from sqlalchemy.sql import func
from .monitor import insert_row, select_row
from sys import exc_info

def insert_tag(tag):

    rtn = 0
    row, _ = select_row('ut_tag',{'tag':tag})
    if not row:
        insert_dict = dict(tag = tag)
        tag_id, _ = insert_row('ut_tag', insert_dict)
        rtn = tag_id
    else:
        rtn = row.id
    
    return rtn