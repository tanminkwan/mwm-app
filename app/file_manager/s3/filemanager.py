"""
You need to add on config this:

    AWS_ACCESS_KEY_ID
    AWS_SECRET_ACCESS_KEY
    REGION_NAME
    BUCKET_NAME
    BUCKET_PREFIX
"""

import logging
import os

from flask.globals import _request_ctx_stack
from flask_appbuilder.filemanager import FileManager, uuid_namegen
from flask_appbuilder.upload import FileUploadField
import boto3
from botocore.client import Config

try:
    from flask import _app_ctx_stack
except ImportError:
    _app_ctx_stack = None

app_stack = _app_ctx_stack or _request_ctx_stack

log = logging.getLogger(__name__)


class S3FileUploadField(FileUploadField):
    """File upload field for S3"""

    def __init__(self, label=None, validators=None,
                 filemanager=None,
                 **kwargs):
        """
            Constructor.

            :param label:
                Display label
            :param validators:
                Validators
        """
        super(S3FileUploadField, self).__init__(label, validators, **kwargs)
        if filemanager is not None:
            self.filemanager = filemanager()
        else:
            self.filemanager = FileManager()
        self._should_delete = False

class S3FileManager(FileManager):
    """File upload to S3
    """

    def __init__(self,
                 bucket_name=None,
                 relative_path='',
                 namegen=None,
                 allowed_extensions=None,
                 **kwargs):

        ctx = app_stack.top

        if "AWS_URL" in ctx.app.config:
            self.aws_url = ctx.app.config["AWS_URL"]
        else:
            self.aws_url = None
        if "AWS_ACCESS_KEY_ID" in ctx.app.config:
            self.aws_access_key_id = ctx.app.config["AWS_ACCESS_KEY_ID"]
        else:
            raise Exception('Config key AWS_ACCESS_KEY_ID is mandatory')
        if "AWS_SECRET_ACCESS_KEY" in ctx.app.config:
            self.aws_secret_access_key = ctx.app.config["AWS_SECRET_ACCESS_KEY"]
        else:
            raise Exception('Config key AWS_SECRET_ACCESS_KEY is mandatory')
        if 'BUCKET_NAME' in ctx.app.config and not bucket_name:
            bucket_name = ctx.app.config['BUCKET_NAME']
        if not bucket_name:
            raise Exception('Config key BUCKET_NAME is mandatory')
        if 'BUCKET_PREFIX' in ctx.app.config and not relative_path:
            relative_path = ctx.app.config['BUCKET_PREFIX']

        self.bucket_name = bucket_name
        self.relative_path = relative_path
        self.namegen = namegen or uuid_namegen
        if not allowed_extensions and 'FILE_ALLOWED_EXTENSIONS' in ctx.app.config:
            self.allowed_extensions = ctx.app.config['FILE_ALLOWED_EXTENSIONS']
        else:
            self.allowed_extensions = allowed_extensions
        self._should_delete = False

    def get_s3_client(self):
        
        s3_client = boto3.client('s3',
                                 endpoint_url=self.aws_url,
                                 aws_access_key_id=self.aws_access_key_id,
                                 aws_secret_access_key=self.aws_secret_access_key,
                                 config=Config(signature_version='s3v4'))
        return s3_client

    def delete_file(self, filename):
        client = self.get_s3_client()
        file_path = os.path.join(self.relative_path, filename)
        client.delete_object(Bucket=self.bucket_name, Key=file_path)

    def save_file(self, data, filename):
        
        client = self.get_s3_client()
        file_path = os.path.join(self.relative_path, filename)
        client.put_object(Body=data, Bucket=self.bucket_name, Key=file_path)
        return filename

    def get_file(self, filename):
        client = self.get_s3_client()
        file_path = os.path.join(self.relative_path, filename)
        response = client.get_object(Bucket=self.bucket_name, Key=file_path)
        body = response['Body'].read()
        return body
"""
class FileUploadView(ModelView):
    datamodel = SQLAInterface(FileManage)

    list_columns = ['filename']

    edit_form_extra_fields = add_form_extra_fields = {
        "filename": S3FileUploadField("S3 File",
                                        description="",
                                        filemanager=S3FileManager,
                                        )
    }

    def pre_delete(self, rel_obj):
        filename = getattr(rel_obj, 'filename')
        file_obj = S3FileManager()
        file_obj.delete_file(filename)
"""