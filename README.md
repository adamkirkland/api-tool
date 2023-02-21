# API TOOL

Tool for querying RESTful APIs, and monitoring Socket.IO connections. Responses are logged, and (planned, in future) changes in response structure are detected between different invocations of the same request.

### Installation and running

`pip install -r requirements.txt`

`python main.py`

### Defining a project
A project needs to be defined to use the tool, containing a project.json file. The json file defines the requests that can be queried, along with other information such as where to log requests to.

Possible API requests are sourced from an array 'requests' in the project json, which will be documented in full at a later date.

The project json field 'variables' is used to define variables that can be referenced from inside any string value elsewhere in the json when surrounded by two sets of curly braces, and which can also be updated dynamically by any of the optional menu or API request callbacks. This is useful for e.g. recording and retrieving tokens returned from a login response.

### TODO
- Diffing key structure between responses of the same request type
- Improve handling of tiny console windows
- Allow user to terminate ongoing request
- More detail in this readme file!
- Native pagination support for requests that require it
- Headless mode