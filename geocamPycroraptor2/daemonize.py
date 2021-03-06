# __BEGIN_LICENSE__
# Copyright (C) 2008-2010 United States Government as represented by
# the Administrator of the National Aeronautics and Space Administration.
# All Rights Reserved.
# __END_LICENSE__

import os
import sys
import signal

from geocamPycroraptor2 import log
from geocamPycroraptor2.util import getPid, waitUntilDead


def cleanIfExists(path):
    if os.path.exists(path):
        try:
            os.unlink(path)
        except OSError:
            print 'could not delete file %s', path


def daemonize(name, logFile, detachTty=True):
    os.chdir('/')
    os.umask(0)

    # close stdin
    devNull = open('/dev/null', 'w')
    os.dup2(devNull.fileno(), 0)

    if logFile is None:
        logFile = devNull
        print 'no log'
    else:
        print 'log at %s' % logFile.name

    os.dup2(logFile.fileno(), 1)
    os.dup2(logFile.fileno(), 2)
    sys.stdout = log.TimestampingStream('%s.out' % name, sys.stdout)
    sys.stderr = log.TimestampingStream('%s.err' % name, sys.stderr)

    if detachTty:
        # detach from tty
        pid = os.fork()
        if pid:
            os._exit(0)
        os.setsid()
        pid = os.fork()
        if pid:
            os._exit(0)


class Daemon(object):
    COMMANDS = ('start', 'stop', 'restart', 'status')

    def __init__(self, name, pidPath):
        self._name = name
        self._pidPath = pidPath

    def execute(self, cmd):
        if cmd in self.COMMANDS:
            return getattr(self, cmd)()

    def start(self):
        pid = getPid(self._pidPath)
        if pid is None:
            print 'starting %s' % self._name
            return True
        else:
            print '%s is already running, pid %s' % (self._name, pid)
            return False

    def writePid(self):
        try:
            f = open(self._pidPath, 'w')
            f.write('%d\n' % os.getpid())
            f.close()
        except:  # pylint: disable=W0702
            print >> sys.stderr, 'could not write pid to path "%s"' % self._pidPath

    def removePid(self):
        cleanIfExists(self._pidPath)

    def stop(self):
        pid = getPid(self._pidPath)
        if pid:
            print ('stopping %s (first attempt, SIGTERM), pid %s...'
                   % (self._name, pid))
            os.kill(pid, signal.SIGTERM)
            isDead = waitUntilDead(pid, timeout=10)
            if isDead:
                print 'stopped'
                self.removePid()
                return
            print ('stopping %s (second attempt, SIGKILL), pid %s...'
                   % (self._name, pid))
            os.kill(pid, signal.SIGKILL)
            isDead = waitUntilDead(pid, timeout=10)
            if isDead:
                print 'stopped'
                self.removePid()
                return
            print ("can't kill running %s, pid %s"
                   % (self._name, pid))
        else:
            print '%s does not appear to be running' % self._name

    def restart(self):
        print 'restarting %s' % self._name
        self.stop()
        return self.start()

    def status(self):
        pid = getPid(self._pidPath)
        if pid is None:
            print '%s is stopped' % self._name
        else:
            print '%s is running, pid %s' % (self._name, pid)
