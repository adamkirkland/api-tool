import json
import socketio
from typing import Dict
import urllib
import weakref

from lines_display import LinesDisplay

# This is pretty narrowly applicable at the moment - there are various Socket.IO
# versions out there, which aren't all compatible with each other, and which
# require different versions of the socketio library to use properly
class SocketIORequest:

    # The version of the Python socketio library we have to use claims to be able
    # to handle all events via the 'message' handler, but that does not work. In
    # order to listen to all events, we need to use a special namespace handler
    class AllEventsHandler(socketio.namespace.ClientNamespace):
        def __init__(self, parent: 'SocketIORequest'):
            super().__init__()
            self.parent_wref = weakref.ref(parent)

        def trigger_event(self, event, *args):
            payload = args[0] if (len(args) > 0) else {}
            parent = self.parent_wref()
            if parent is not None:
                parent.on_event(event, payload)

    def __init__(
        self,
        desc: str = '',
        endpoint: str = '',
        params: Dict = {},
        event: str = '',
        data: Dict = {},
        display: LinesDisplay = None
    ):
        self.url = endpoint + ('?{0}'.format(urllib.parse.urlencode(params)) if params else '')
        self.event = event
        self.data = data
        self.display = display
        self.desc = desc if desc else str(self).splitlines()[0]

    def __str__(self):
        return 'Socket.IO {0} {1}{2}'.format(
            self.url.split('?')[0],
            self.event,
            '\ndata = {0}'.format(json.dumps(self.data, indent = 4)) if self.data else ''
        )

    def start(self):
        self.sio = socketio.Client()
        self.sio.register_namespace(self.AllEventsHandler(self))
        self.sio.on('connect', self.on_connect)
        self.sio.on('connect_error', self.on_connect_error)
        self.sio.on('disconnect', self.disconnect)

        with self.display.mutex:
            self.display.print('\nConnecting to Socket.IO server')
        self.sio.connect(self.url)

    def stop(self):
        self.sio.disconnect()

    def callback(self, data: Dict):
        with self.display.mutex:
            self.display.print('\nEmit received callback with data:')
            self.display.print_json(data)

    def on_connect(self):
        with self.display.mutex:
            self.display.print('\nSuccessfully connected to server')
        if self.event:
            data = self.data if self.data else {}
            with self.display.mutex:
                self.display.print('\nEmitting event {0} with data:'.format(self.event))
                self.display.print_json(data)
            self.sio.emit(self.event, data, callback=self.callback)

    def on_event(self, event: str, data: Dict):
        with self.display.mutex:
            self.display.print('\nReceived event {0} with data:'.format(event))
            self.display.print_json(data)

    def on_connect_error(self, data: Dict):
        if data:
            data = json.loads(data)
        with self.display.mutex:
            self.display.print('\nConnection failed with data:')
            self.display.print_json(data)

    def disconnect(self):
        with self.display.mutex:
            self.display.print('\nDisconnected from server')
