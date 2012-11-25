# __BEGIN_LICENSE__
# Copyright (C) 2008-2010 United States Government as represented by
# the Administrator of the National Aeronautics and Space Administration.
# All Rights Reserved.
# __END_LICENSE__

# status.status values
NOT_STARTED = 'notStarted'
STARTING = 'starting'
RUNNING = 'running'
STOPPING = 'stopping'
SUCCESS = 'success'
ABORTED = 'aborted'
FAILED = 'failed'

# status.procStatus values
RUNNING = 'running'
CLEAN_EXIT = 'cleanExit'
SIGNAL_EXIT = 'signalExit'
ERROR_EXIT = 'errorExit'


STARTABLE_STATUS = (NOT_STARTED,
                    SUCCESS,
                    ABORTED,
                    FAILED)

ACTIVE_STATUS = (STARTING,
                 RUNNING,
                 STOPPING)


def isActive(status):
    return status in ACTIVE_STATUS


def isStartable(status):
    return status in STARTABLE_STATUS
