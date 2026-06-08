"""
Valve Controller Web Application

A Flask-based web application for monitoring and controlling valves through a REST API.
This module serves as the main entry point and is designed to be run by Gunicorn.

Features:
- Web interface for valve status monitoring
- REST API for programmatic valve control with API key authentication
- System monitoring (CPU temperature, thread listing)
- Log viewing (application logs, Gunicorn logs, system logs)

The application exposes endpoints for valve control, system status, and log viewing.
"""


import subprocess
from threading import enumerate as enumerate_threads
from flask import Flask, render_template, jsonify, request
from logmanager import  logger
from valvecontrol import httpstatus, valvestatus, parsecontrol
from app_control import settings, VERSION

logger.info('Starting Valve Controller web app version %s', VERSION)
logger.info('Api-Key = %s', settings['api-key'])
app = Flask(__name__)


def read_log_from_file(file_path):
    """
    Reads and returns the reversed content of a log file.

    This function opens the specified file in read mode with UTF-8 encoding, reads its
    contents into a list of lines, reverses the order of the lines, and returns the
    reversed list.

    Args:
        file_path (str): The path to the file to be read.

    Returns:
        list: A list of strings representing the lines of the file, in reversed order.
    """
    with open(file_path, 'r', encoding='utf-8') as f:
        lines = f.readlines()
    return list(reversed(lines))


def read_cpu_temperature():
    """
    Reads the CPU temperature from a file specified in the application settings.

    This function opens the file path defined in the settings, reads the CPU
    temperature data in millidegrees Celsius, converts it to degrees Celsius, and
    rounds the resulting value to one decimal place before returning it.

    Raises:
        FileNotFoundError: If the file path specified in the settings does not
            exist.
        IOError: If there is an error reading the file.
        ValueError: If the temperature file content cannot be converted to a float.

    Returns:
        float: The CPU temperature in degrees Celsius, rounded to one decimal place.
    """
    with open(settings['cputemp'], 'r', encoding='utf-8') as f:
        log = f.readline()
    return round(float(log) / 1000, 1)


def threadlister():
    """
    Generates a list of threads currently running in the application.

    This function retrieves all active threads in the process, collecting their
    names and native thread IDs, and returns the result as a list. Each thread's
    information is represented as a sublist containing the thread's name and ID.

    Returns:
        list: A list of sublists where each sublist contains a thread's name
            and native thread ID.
    """
    appthreads = []
    for appthread in enumerate_threads():
        appthreads.append([appthread.name, appthread.native_id])
    return appthreads


@app.route('/')
def index():
    """
    Define a route for the root URL that renders the 'index.html' template with various
    context values including CPU temperature, valve states, application version, and
    running threads.

    Returns
    -------
    flask.Response
        The HTTP response object containing the rendered HTML template.
    """
    cputemperature = read_cpu_temperature()
    return render_template('index.html', valves=httpstatus(), cputemperature=cputemperature,
                           version=VERSION, threads=threadlister())


@app.route('/api', methods=['POST'])
def api():
    """
    Handles API POST requests to execute instructions on a specified item.

    This function is a Flask route handling API calls. It checks the headers
    of the request for an API key and validates it. If the key is valid, it
    processes the request to execute a command on the given item via the
    `parsecontrol` function. The response about the item's status is then
    returned in JSON format. In case of incorrect or missing API key, or
    if the request contains malformed JSON, appropriate HTTP error
    responses are returned.

    Raises:
        KeyError: If the required 'item' or 'command' fields are missing from
        the request JSON payload, or if the 'Api-Key' header is not
        present or malformed.

    Returns:
        Response: On valid API key and request, returns the status
        of the requested command in JSON format along with a
        201 status code.
        str: Returns an error message with a 401 status code
        in cases of unauthorized access or JSON parsing errors.
    """
    try:
        logger.debug('API headers: %s', request.headers)
        logger.debug('API request: %s', request.json)
        if 'Api-Key' in request.headers.keys():  # check api key exists
            if request.headers['Api-Key'] == settings['api-key']:  # check for correct API key
                item = request.json['item']
                command = request.json['command']
                parsecontrol(item, command)
                return jsonify(valvestatus()), 201
            logger.warning('API: access attempt using an invalid token')
            return 'access token(s) unuthorised', 401
        logger.warning('API: access attempt without a token')
        return 'access token(s) incorrect', 401
    except KeyError:
        logger.warning('API: Badly formed json message')
        return "badly formed json message", 401


@app.route('/pylog')
def showplogs():
    """
    Route definition for displaying Python logs.

    This route handles the '/pylog' URL path and renders a template
    that displays the Valve-Control log, including CPU temperature
    and the application version.

    Returns:
        flask.Response: The rendered HTML template with context data
        including logs, log title, CPU temperature, and version.
    """
    cputemperature = read_cpu_temperature()
    logs = read_log_from_file(settings['logfilepath'])
    return render_template('logs.html', rows=logs, log='Valve-Control log',
                           cputemperature=cputemperature, version=VERSION)


@app.route('/guaccesslog')
def showgalogs():
    """
    Handles the display of Gunicorn access logs and CPU temperature.

    This function retrieves the current CPU temperature and the Gunicorn access logs,
    and then renders the `logs.html` template to display the logs alongside the CPU
    temperature.

    Returns:
        str: The rendered HTML content for the logs page.
    """
    cputemperature = read_cpu_temperature()
    logs = read_log_from_file(settings['gunicornpath'] + 'gunicorn-access.log')
    return render_template('logs.html', rows=logs, log='Gunicorn Access Log',
                           cputemperature=cputemperature, version=VERSION)


@app.route('/guerrorlog')
def showgelogs():
    """
    Provides the view for displaying the Gunicorn error logs.

    This function reads the CPU temperature and Gunicorn error log content from
    files and renders them in an HTML template. It serves as the backend handling
    for the endpoint `/guerrorlog`.

    Returns:
        str: Rendered HTML template displaying the logs and other related
        information.
    """
    cputemperature = read_cpu_temperature()
    logs = read_log_from_file(settings['gunicornpath'] + 'gunicorn-error.log')
    return render_template('logs.html', rows=logs, log='Gunicorn Error Log',
                           cputemperature=cputemperature, version=VERSION)


@app.route('/syslog')
def showslogs():
    """
    Handles the '/syslog' route to display system log entries in reverse order along
    with CPU temperature.

    Creates a Flask route that retrieves the latest system logs, reverses their
    order, and renders them to an HTML template. Additionally, it retrieves and
    displays the CPU temperature and a version parameter.

    Returns:
        str: Rendered HTML page showing system logs, CPU temperature, and a version
        identifier.
    """
    cputemperature = read_cpu_temperature()
    log = subprocess.Popen('/bin/journalctl -n 200', shell=True,
                           stdout=subprocess.PIPE).stdout.read().decode(encoding='utf-8')
    logs = log.split('\n')
    logs.reverse()
    return render_template('logs.html', rows=logs, log='System Log', cputemperature=cputemperature,
                           version=VERSION)



if __name__ == '__main__':
    app.run(host="0.0.0.0", port=5000) 
