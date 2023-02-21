#!/usr/bin/env python3

from collections import OrderedDict
from datetime import datetime
from enum import Enum
import json
import pytz
import requests
from typing import Dict
import urllib

from lines_display import LinesDisplay
from timer import RepeatingTimer

class Verb(Enum):
    GET = 'GET'
    POST = 'POST'
    PUT = 'PUT'
    PATCH = 'PATCH'
    DELETE = 'DELETE'

    def __str__(self):
        return self.name



class ApiResponse:
    def __init__(self, raw_response: requests.Response = None, json_data: Dict = None):
        if raw_response is not None:
            self.status_code = raw_response.status_code
            self.duration = raw_response.elapsed.total_seconds()
            self.error = None
            self.text = raw_response.text if raw_response.text else ''
            self.body = None
            try:
                self.body = raw_response.json(object_pairs_hook=OrderedDict)
            except Exception:
                if self.text != '' and self.text != 'null':
                    self.error = 'invalid JSON response: {0}'.format(self.text)
        if json_data is not None:
            self.status_code = json_data.get('status_code', None)
            self.duration = json_data.get('duration', None)
            self.body = json_data.get('body', {})
            self.error = json_data.get('error', None)
            self.text = None

    def to_json(self) -> Dict:
        result = {
            'status_code': self.status_code,
            'duration': self.duration,
            'body': self.body if self.body is not None else self.text,
            'error': self.error
        }
        remove_if_empty = ['error']
        for key in remove_if_empty:
            if not result[key]:
                result.pop(key)
        return result



class ApiResponseCallback:
    def invoke(self, request: 'ApiRequest', response: ApiResponse, vars: Dict, display: LinesDisplay):
        pass



class ApiRequest:
    def __init__(
        self,
        desc: str = '',
        verb: Verb = Verb.GET,
        base: str = 'localhost',
        endpoint: str = '/',
        headers: Dict = {},
        params: Dict = {},
        body: Dict = {},
        bucket_label: str = '',
        callback: ApiResponseCallback = ApiResponseCallback(),
        json_data: Dict = None
    ):
        self.verb = verb
        self.base = base
        self.endpoint = endpoint
        self.headers = headers
        self.params = params
        self.body = body
        self.bucket_label = bucket_label
        self.callback = callback
        self.timestamp: datetime = None
        if json_data:
            self.verb = Verb[json_data.get('verb', 'GET')]
            self.endpoint = json_data.get('endpoint', self.endpoint)
            self.headers = json_data.get('headers', self.headers)
            self.body = json_data.get('body', self.body)
            self.params = json_data.get('params', self.params)
            self.timestamp = json_data.get('timestamp', self.timestamp)
        self.desc = '{0}{1}'.format((desc + ' - ') if desc else '', str(self).splitlines()[0])

    def __str__(self):
        return '{0} {1}{2}{3}{4}'.format(
            self.verb,
            self.endpoint,
            '?{0}'.format(urllib.parse.urlencode(self.params)) if self.params else '',
            '\nheaders = {0}'.format(json.dumps(self.headers, indent = 4)) if self.headers else '',
            '\nbody = {0}'.format(json.dumps(self.body, indent=4)) if self.body else ''
        )

    def to_json(self) -> Dict:
        result = {
            'base': self.base,
            'verb': str(self.verb),
            'endpoint': self.endpoint,
            'headers': self.headers,
            'body': self.body,
            'params': self.params,
            'timestamp': self.timestamp.isoformat()
        }
        remove_if_empty = ['headers', 'body', 'params']
        for key in remove_if_empty:
            if not result[key]:
                result.pop(key)
        return result

    def fire(self, display: LinesDisplay, vars: Dict) -> ApiResponse:
        display.set_header('Executing request…')
        display.set_footer('')
        display.print('\nSending {0} {1}{2}\n'.format(
            self.verb,
            self.endpoint,
            '?{0}'.format(urllib.parse.urlencode(self.params)) if self.params else ''
        ))
        if self.headers:
            display.print('headers = ')
            display.print_json(self.headers, False)
        if self.body:
            display.print('body = ')
            display.print_json(self.body, False)
        display.print('\n\n')
        url = self.base + self.endpoint
        if self.params and self.verb is not Verb.GET:
            # Requests doesn't allow params with most verbs, as it would be against
            # recommended practice, but we should support doing so anyway
            url += '?{0}'.format(urllib.parse.urlencode(self.params))

        self.timestamp = datetime.utcnow().replace(tzinfo=pytz.utc)
        rt = RepeatingTimer(0.25, lambda: display.print('.', flush=False))
        if self.verb == Verb.GET:
            raw_response = requests.get(url, headers=self.headers, params=self.params)
        elif self.verb == Verb.POST:
            raw_response = requests.post(url, headers=self.headers, json=self.body)
        elif self.verb == Verb.PATCH:
            raw_response = requests.patch(url, headers=self.headers, json=self.body)
        elif self.verb == Verb.PUT:
            raw_response = requests.put(url, headers=self.headers, json=self.body)
        elif self.verb == Verb.DELETE:
            raw_response = requests.delete(url, headers=self.headers)
        rt.stop()
        response = ApiResponse(raw_response)

        display.print('\nReceived response {0} in {1}s:\n'.format(
            response.status_code,
            '{0:.3f}'.format(response.duration)
        ))
        if response.body:
            display.print_json(response.body)
        else:
            display.print(response.text)

        try:
            self.callback.invoke(self, response, vars, display)
        except Exception as e:
            pass

        return response