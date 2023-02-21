#!/usr/bin/env python3

from typing import Dict

from api_request import ApiRequest, ApiResponse, ApiResponseCallback
from lines_display import LinesDisplay

class CallbackIncrementId(ApiResponseCallback):
    def invoke(self, request: ApiRequest, response: ApiResponse, vars: Dict, display: LinesDisplay):
        old_id = int(vars.get('next_id', '1'))
        vars['next_id'] = str(old_id + 1)
