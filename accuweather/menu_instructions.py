#!/usr/bin/env python3

from typing import Dict

from api_request import ApiResponse
from menu_display import MenuCallback, MenuDisplay

class CallbackMenuInstructions(MenuCallback):
    def invoke(self, vars: Dict, menu: MenuDisplay, last_response: ApiResponse):

        menu.instructions = ''
        location = vars.get('location_key', '')
        if location:
            menu.instructions = 'location_key set to: ' + location
        else:
            menu.instructions = 'There is currently no location_key set'
        if last_response and last_response.status_code >= 400 and last_response.body.get('Code') == 'Unauthorized':
            menu.instructions = 'You may need to upgrade your API key to access all methods'
