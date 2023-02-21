#!/usr/bin/env python3

import argparse
from collections import OrderedDict
import importlib
import inspect
import json
import os
import sys
from typing import Any, Dict, List, Tuple

from api_request import ApiRequest, ApiResponse, Verb
from lines_display import LinesDisplay
from menu_display import MenuDisplay
from socketio_request import SocketIORequest

def sanitize_for_filename(input: str) -> str:
    for prefix in ['https://', 'http://', 'wss://', 'www.', '/']:
        input = input[len(prefix):] if input.startswith(prefix) else input

    return input\
        .replace('/', '-')\
        .replace('+', '')\
        .replace('?', '-')

def save(request: ApiRequest, response: ApiResponse, project_dir: str, project: Dict):
    vars = project.get('variables', {})
    output_dir = os.path.join(project_dir, replace_vars_str(project.get('output_path', ''), vars))
    if not os.path.exists(output_dir):
        os.mkdir(output_dir)

    bucket_dir = os.path.join(output_dir, request.bucket_label)
    if not os.path.exists(bucket_dir):
        os.mkdir(bucket_dir)

    raw_dir = os.path.join(bucket_dir, 'raw')
    if not os.path.exists(raw_dir):
        os.mkdir(raw_dir)

    filename = sanitize_for_filename('{0} {1}'.format(
        request.timestamp.strftime('%Y-%m-%dT%H-%M-%S'),
        str(request).splitlines()[0].replace('/', '', 1)
    ))

    output = {
        'request': request.to_json(),
        'response': response.to_json()
    }
    with open(os.path.join(bucket_dir, filename + '.json'), 'w') as file:
        file.write(json.dumps(output))

    with open(os.path.join(raw_dir, filename + '.txt'), 'w') as file:
        file.write(json.dumps(response.to_json()['body'], indent=4))

    with open(project_path, 'w') as project_file:
        json.dump(project, project_file, indent=4)

def load(project_dir: str, project: Dict) -> List[Tuple[ApiRequest, ApiResponse]]:
    vars = project.get('variables', {})
    output_dir = os.path.join(project_dir, replace_vars_str(project.get('output_path', ''), vars))
    output_file_path = os.path.join(output_dir, 'output.json')
    result = []
    try:
        with open(output_file_path, 'r') as file:
            file_json = json.load(file)
            for pair_obj in file_json:
                request = ApiRequest(json_data=pair_obj.get('request', {}))
                response = ApiResponse(json_data=pair_obj.get('response', {}))
                result.append((request, response))
    except Exception as e:
        pass
    return result

def replace_vars_str(instr: str, vars: Dict) -> str:
    for key in vars.keys():
        instr = instr.replace('{{' + key + '}}', vars[key])
    return instr

def replace_vars_list(inlist: list, vars: Dict) -> list:
    result = []
    for val in inlist:
        if isinstance(val, str):
            result.append(replace_vars_str(val, vars))
        elif isinstance(val, dict):
            result.append(replace_vars_dict(val, vars))
        elif isinstance(val, list):
            result.append(replace_vars_list(val, vars))
        else:
            result.append(val)
    return result

def replace_vars_dict(indict: Dict, vars: Dict) -> Dict:
    result = {}
    for key in indict.keys():
        val = indict[key]
        if isinstance(val, str):
            result[key] = replace_vars_str(val, vars)
        elif isinstance(val, dict):
            result[key] = replace_vars_dict(val, vars)
        elif isinstance(val, list):
            result[key] = replace_vars_list(val, vars)
        else:
            result[key] = val
    return result

def load_callback(module_name: str, project_dir: str) -> Any:
    callback = None
    if module_name:
        if project_dir not in sys.path:
            sys.path.append(project_dir)
        module = importlib.import_module(module_name)
        classes = inspect.getmembers(module, lambda x: inspect.isclass(x) and x.__module__ == module_name and getattr(x, 'invoke', None))
        if len(classes) > 0:
            callback = classes[0][1]()
    return callback

def build_request(request_json: Dict, project: Dict, vars: Dict, project_dir: str, display: LinesDisplay = None) -> ApiRequest:
    method = replace_vars_str(request_json.get('method', 'GET'), vars)
    if method == 'Socket.IO':
        event_dict = replace_vars_dict(request_json.get('emit_on_connect', {}), vars)
        event = next((x for x in event_dict.keys()), '')
        data = replace_vars_dict(event_dict.get(event, {}), vars)
        return SocketIORequest(
            desc=replace_vars_str(request_json.get('desc', ''), vars),
            endpoint=replace_vars_str(request_json.get('endpoint', ''), vars),
            params=replace_vars_dict(request_json.get('params', {}), vars),
            event=event,
            data=data,
            display=display
        )
    elif method in Verb.__members__:
        return ApiRequest(
            desc=replace_vars_str(request_json.get('desc', ''), vars),
            verb=Verb[method],
            base=replace_vars_str(project.get('api_base', ''), vars),
            endpoint=replace_vars_str(request_json.get('endpoint', '/'), vars),
            headers=replace_vars_dict(request_json.get('headers', {}), vars),
            params=replace_vars_dict(request_json.get('params', {}), vars),
            body=replace_vars_dict(request_json.get('body', {}), vars),
            bucket_label=sanitize_for_filename('{0} {1}{2}'.format(
                method,
                sanitize_for_filename(project.get('api_base', '')),
                request_json.get('endpoint', '/')
            )),
            callback=load_callback(request_json.get('callback', None), project_dir)
        )
    else:
        return None

def dict_merge(d1, d2):
    for k, v in d1.items():
        if k in d2:
            if all(isinstance(e, dict) for e in (v, d2[k])):
                d2[k] = dict_merge(v, d2[k])
    d3 = d1.copy()
    d3.update(d2)
    return d3

if __name__ == '__main__':
    # Parse and verify args
    parser = argparse.ArgumentParser(description='API request testing tool')
    parser.add_argument(
        '--project', dest='project_dir', metavar='FILE',
        help='path to the directory for the project, containing a project.json file. See README.md for help creating the project'
    )
    args = parser.parse_args()

    # Identify the project to use
    project_dir = args.project_dir
    if not project_dir or not os.path.exists(project_dir):
        possible_dirs = [path for path in os.listdir('.') if os.path.isdir(path) and os.path.exists(os.path.join(path, 'project.json'))]
        if not possible_dirs:
            print('Error - could not find any valid project directories. Consult README.md for more details')
            sys.exit()
        if len(possible_dirs) == 1:
            project_dir = possible_dirs[0]
        else:
            project_names = []
            for dir in possible_dirs:
                with open(os.path.join(os.path.abspath(dir), 'project.json')) as project_file:
                    project = json.load(project_file)
                    project_names.append(project.get('name', ''))
            menu = MenuDisplay(
                title='Select from available projects:',
                items=[('{0} - {1}'.format(dir, project_names[i]), str(i)) for i, dir in enumerate(possible_dirs)]
            )
            selected = menu.wait_for_selection()
            project_dir = possible_dirs[int(selected)]
    project_dir = os.path.abspath(project_dir)
    project_path = os.path.join(project_dir, 'project.json')
    if not os.path.exists(project_path):
        print('Error - could not find project.json at {0}'.format(project_path))
        sys.exit()

    # Open project json file
    with open(project_path) as project_file:
        project = json.load(project_file, object_pairs_hook=OrderedDict)
    # A project can have a "base" project, which just means we merge the project files together
    requests_dicts = project.get('requests', [])
    if project.get('base_project') and os.path.exists(project['base_project']):
        base_project_path = os.path.join(os.path.abspath(project['base_project']), 'project.json')
        with open(base_project_path) as base_project_file:
            base_project = json.load(base_project_file, object_pairs_hook=OrderedDict)
            project = dict_merge(base_project, project)
            requests_dicts = project.get('requests', [])
            project.pop('requests')  # don't copy the new requests into the child project, so they don't get saved

    # Build menu
    vars = project.get('variables', {})
    shortcut_chars = '0123456789abcdefghijklmnoprstuvwxyz'
    requests = [build_request(x, project, vars, project_dir) for x in requests_dicts]
    shortcut_chars += ' ' * max(0, (len(requests) - len(shortcut_chars)))
    menu_items = [(x.desc, shortcut_chars[idx]) for idx, x in enumerate(filter(None, requests))]
    menu_callback = load_callback(project.get('callback_menu', None), project_dir)
    menu = MenuDisplay(
        title='Select a request:',
        items=menu_items + [('quit', 'q')],
        callback=menu_callback
    )

    # Main program loop
    display = LinesDisplay()
    last_response = None
    menu_exit = False
    while not menu_exit:
        # Optional menu callback defined on a per-project bases
        try:
            menu.callback.invoke(vars, menu, last_response)
        except Exception as e:
            pass

        # Get user menu selection
        selected = menu.wait_for_selection()
        if selected is None or selected >= len(menu_items):
            menu_exit = True
            continue

        # Execute the selection. The request object will start rendering immediately in the display
        # TODO the user has no way of cancelling the request here
        request = build_request(requests_dicts[selected], project, vars, project_dir, display)
        if not request:
            continue
        if isinstance(request, ApiRequest):
            response = request.fire(display, vars)
            project['variables'] = vars
            save(request, response, project_dir, project)
            last_response = response
        elif isinstance(request, SocketIORequest):
            request.start()
            last_response = None
        else:
            continue

        # Once the request has finished executing, allow the user to browse around the results for a while
        display.display_and_browse()
        # Socket requests are ongoing, so we have to make sure to stop once the user is done browsing
        if isinstance(request, SocketIORequest):
            request.stop()
