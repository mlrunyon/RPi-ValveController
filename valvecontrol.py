"""
Raspberry Pi Valve Control System

This module provides a comprehensive interface for controlling and monitoring laboratory
valves via [Raspberry Pi I^2C output]. It implements safety interlocks to prevent conflicting
valve states, handles system commands, and provides status monitoring capabilities.

Features:
- Individual valve control (open/close) with conflict prevention
- Batch operations (close all valves)
- System control commands (restart)
- Status reporting for monitoring
- Logging of all valve operations and errors

The module initializes [MOSFET channels via I^2C], defines valve configurations with their relationships,
and provides functions for valve manipulation through a consistent interface.

Dependencies:
- Sequent microsystems lib8mosind: For I2C control of hardware
- threading.Timer: For delayed execution of commands
- logmanager: For operational logging
"""

from threading import Timer
import os
from RPi import lib8mosind
from logmanager import logger


logger.info('Application starting')
STACK = 0
channels = [1,2,3] # "channels" referred to as mosfets in github repo

# initialize channels to OFF
for ch in channels:
    lib8mosind.set(STACK, ch, 0)

# assign channels to valves
valves = [
    {
        'id': 1,
        'channel': channels[0],
        'description': 'Pipette input',
        'excluded': 2
    },
    {
        'id': 2,
        'channel': channels[1],
        'description': 'Pipette output',
        'excluded': 1
    },
    {
        'id': 10,
        'channel': channels[2],
        'description': 'Turbo',
        'excluded': 2
    }
]


def parsecontrol(item, command):
    """
    Parses and executes control instructions for items such as valves or system commands.

    This function handles control commands for items (e.g., valves) by executing
    the corresponding actions (opening, closing, restarting, etc.). It utilizes specific
    rules to process the commands and takes recovery measures in case of invalid inputs
    or errors.

    Parameters:
    item : str
        Specifies the name of the control item (e.g., 'valve1', 'closeallvalves', 'restart').
    command : str
        Provides the command to execute for the given item (e.g., 'open', 'close', 'pi').

    Raises:
    ValueError
        If the conversion of values such as valve number fails.
    IndexError
        If accessing an invalid index during item processing.
    """
    # print('%s : %s' % (item, command))
    try:
        if item[:5] == 'valve':
            valve = int(item[5:])
            if 0 < valve < 14:
                if command == 'open':
                    valveopen(valve)
                elif command == 'close':
                    valveclose(valve)
                else:
                    logger.warning('bad valve command')
            else:
                logger.warning('bad valve number')
        elif item == 'closeallvalves':
            allclose()
        elif item == 'restart':
            if command == 'pi':
                logger.warning('Restart command recieved: system will restart in 15 seconds')
                timerthread = Timer(15, reboot)
                timerthread.start()
    except ValueError:
        logger.warning('incorrect json message')
    except IndexError:
        logger.warning('bad valve number')


def valveopen(valveid):
    """
    Opens a valve based on its unique identifier if no conflicting valve is open.

    Before opening, it checks whether the valve marked as excluded for the specified valve is already open.
    If the excluded valve is open, the operation is aborted, logging a warning.
    If no conflict is found, the specified valve is opened, and this action is logged.

    Parameters:
        valveid (int): The unique identifier of the valve to be opened.
    """
    valve = [valve for valve in valves if valve['id'] == valveid][0]
    excluded = [valvex for valvex in valves if valvex['id'] == valve['excluded']][0]

    # Read all channel states (bitmask: 1 = ON, 0 = OFF)
    status = lib8mosind.get_all(STACK)
    excluded_state = (status >> (excluded['channel'] - 1)) & 1  # bit-shift to check channel

    if excluded_state == 1:
        logger.warning('Cannot open valve %s: excluded valve %s is already open', valveid, excluded['id'])

    # If excluded channel is not on, valve will open
    else:
        lib8mosind.set(STACK, valve['channel'], 1)
        logger.info('Valve %s (%s) opened', valveid, valve['description'])


def valveclose(valveid):
    """
    Closes the specified valve based on its ID.

    Identifies the valve with the given ID in the list of valves,
    ensures that the MOSFET channel is set to a low state, and logs the
    operation. This action effectively closes the valve. The provided valve
    ID should match an existing valve's ID within the list.

    Parameters:
        valveid (int): The ID of the valve to be closed.
    """
    valve = [valve for valve in valves if valve['id'] == valveid][0]
    lib8mosind.set(STACK, valve['channel'], 0)
    logger.info('Valve %s (%s) closed', valveid, valve['description'])


def allclose():
    """
    Close all valves by setting the output of the specified channels to 0.

    Summary:
    This function outputs a signal of 0 to all channels specified in
    'channels' list, effectively closing all valves. It also logs an info
    message indicating the operation.

    Returns:
    None
    """
    lib8mosind.set(STACK, channels, 0)
    logger.info('All Valves Closed')

def status(value):
    """
    Determines the status based on a given value.
    
    Function evaluates the provided integer value and returns a corresponding
    status string. Specifically, it checks whether the value equals zero to
    determine if the status is 'closed'. Any other value results in a status
    of 'open'.

    Parameters:
    value (int): The value to evaluate for determining the status.

    Returns:
    str: A string representing the status. Returns 'closed' if the value is
    0; otherwise, returns 'open'.
    """
    return 'closed' if value == 0 else 'open'



def valvestatus():
    """
    Determines the status of valves based on their I2C-reported state.

    This function iterates through a list of valves, checks each valve's state, 
    and compiles a list of dictionaries containing the valve ID
    and its respective status.

    Returns:
        list[dict]: A list where each dictionary contains the ID of a valve and
        its corresponding status, based on MOSFET channel status.
    """
    states = lib8mosind.get_all(STACK)  # bitmask of all channel states
    return [
        {'valve': valve['id'], 'status': status((states >> (valve['channel'] - 1)) & 1)}
        for valve in valves if valve['id'] > 0
    ]


def httpstatus():
   """
    Determine and return the status of a list of valves based on their I2C-reported state.

    This function iterates through a list of valve objects, checks each valve's state
    (1 open or 0 closed) then constructs a list of dictionaries containing
    the valve's ID, description, and current status.

    Returns:
        list[dict]: A list of dictionaries each containing the valve's `id` (int),
        `description` (str), and its current `status` (bool or other relevant type
        returned by the `status` function).
    """
    states = lib8mosind.get_all(STACK)  # bitmask of all channel states
    return [
        {
            'id': valve['id'],
            'description': valve['description'],
            'status': status((states >> (valve['channel'] - 1)) & 1)
        }
        for valve in valves if valve['id'] > 0
    ]


def reboot():
    """
    Reboots the local machine.

    This function logs a warning message indicating that the system is about to restart
    and then executes a system command to initiate a reboot.

    Raises:
        This function does not explicitly raise any exceptions, but it depends on the
        behavior of the underlying operating system and might fail in environments
        without sufficient permissions.

    """
    logger.warning('System is restarting now')
    os.system('sudo reboot')


ready_channel = 4  # spare MOSFET channel
def turn_on():
    lib8mosind.set(STACK, ready_channel, 1)
def turn_off():
    lib8mosind.set(STACK, ready_channel, 0)
"""
Indicates the application is ready via 3 blinks on MOSFET channel 4
"""
for i in range(3):
    Timer(i * 2, turn_on).start()   # turn ON at 0s, 2s, 4s
    Timer(i * 2 + 1, turn_off).start()  # turn OFF at 1s, 3s, 5s



logger.info("Application ready (I2C)")