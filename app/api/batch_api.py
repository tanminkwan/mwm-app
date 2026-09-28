from app import appbuilder, db
from flask import jsonify, request
from flask_appbuilder.api import BaseApi, expose, protect
from app.sqls.batch import batch_function_registry
import app.sqls.batch as batch_module
import logging
from app.api.errors import internal_error

class BatchApi(BaseApi):
    resource_name = 'batch'

    @expose('/list', methods=['GET'])
    @protect()
    def list_functions(self):
        """List all registered batch functions and their descriptions"""
        return jsonify(batch_function_registry)

    @expose('/run/<function_name>', methods=['POST'])
    @protect()
    def run_function(self, function_name):
        """
        Execute a batch function by name.
        JSON payload can contain 'params' (list or dict) and optionally 'command_id'.
        """
        if function_name not in batch_function_registry:
            return jsonify({"message": f"Function '{function_name}' is not registered."}), 404

        # Get the actual function from the module
        func = getattr(batch_module, function_name, None)
        if not func:
            return jsonify({"message": f"Function '{function_name}' found in registry but not in module."}), 500

        try:
            data = request.json if request.data else {}
            command_id = data.get('command_id', 'API_CALL')
            params = data.get('params', [])

            # Batch functions wrapped with @batch_function expect (command_id, *args, **kwargs)
            if isinstance(params, list):
                rtn, msg = func(command_id, *params)
            elif isinstance(params, dict):
                rtn, msg = func(command_id, **params)
            else:
                rtn, msg = func(command_id)

            status_code = 200 if rtn == 1 else 400
            return jsonify({"return_code": rtn, "message": msg}), status_code

        except Exception:
            return internal_error(f"mwm BatchApi.run_function Error: {function_name}")

appbuilder.add_api(BatchApi)
