# __BEGIN_LICENSE__
# Copyright (C) 2008-2010 United States Government as represented by
# the Administrator of the National Aeronautics and Space Administration.
# All Rights Reserved.
# __END_LICENSE__

import os
import sys

from geocamPycroraptor2 import log


def daemonize(logPathTemplate, logPathContext, pidPath):
    os.chdir('/')
    os.umask(0)

    # close stdin
    devNull = file('/dev/null', 'rw')
    os.dup2(devNull.fileno(), 0)

    # redirect stdout and stderr to log file
    if logPathTemplate == None:
        logFile = devNull
    else:
        logName, logFile = (log.openLogFromTemplate
                            ('pyraptord',
                             logPathTemplate,
                             logPathContext))
    print 'daemonizing  -- log file %s' % logName
    os.dup2(logFile.fileno(), 1)
    os.dup2(logFile.fileno(), 2)
    sys.stdout = log.StreamLogger('out', sys.stdout)
    sys.stderr = log.StreamLogger('err', sys.stderr)

    # detach from tty
    pid = os.fork()
    if pid:
        os._exit(0)
    os.setsid()
    pid = os.fork()
    if pid:
        os._exit(0)

    # write pid file
    if pidPath != None:
        pidDir = os.path.dirname(pidPath)
        if not os.path.isdir(pidDir):
            os.makedirs(pidDir)
        pidFile = file(pidPath, 'w')
        pidFile.write('%d\n' % os.getpid())
        pidFile.close()
