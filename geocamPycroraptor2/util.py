# __BEGIN_LICENSE__
# Copyright (C) 2008-2010 United States Government as represented by
# the Administrator of the National Aeronautics and Space Administration.
# All Rights Reserved.
# __END_LICENSE__

import os
import pty
import logging
import errno
import time
import json

import gevent

from geocamUtil.dotDict import convertToDotDictRecurse


class FdTracker(object):
    def __init__(self):
        self._openFds = {}
        self.logger = logging.getLogger('FdTracker')

    def open(self, owner, filename, flag, mode=0777):
        f = open(filename, flag, mode)
        self._openFds[f.fileno()] = owner
        return f

    def openpty(self, owner):
        master, slave = pty.openpty()
        self._openFds[master] = owner
        self._openFds[slave] = owner
        return master, slave

    def close(self, fd):
        os.close(fd)
        del self._openFds[fd]

    def debug(self):
        fdsByOwner = {}
        for fd, owner in self._openFds.iteritems():
            entry = fdsByOwner.setdefault(owner, [])
            entry.append(fd)

        self.logger.debug('Allocated fds (%s total):',
                          len(self._openFds))

        owners = sorted(fdsByOwner.keys())
        for owner in owners:
            fds = sorted(fdsByOwner[owner])
            self.logger.debug('  %s: %s', owner, fds)


trackerG = FdTracker()


def loadConfig(path):
    f = open(path, 'r')
    j = json.load(f)
    return convertToDotDictRecurse(j)


class ConfigField(object):
    def __init__(self, config, field):
        self.config = config
        self.field = field

    def getSubField1(self, field):
        return ConfigField(self.getValue(), field)

    def getSubField(self, fieldPath):
        current = self
        if fieldPath == '':
            elts = []
        else:
            elts = fieldPath.split('.')
        for elt in elts:
            current = current.getSubField1(elt)
        return current

    def getValue(self):
        return getattr(self.config, self.field)

    def setValue(self, val):
        setattr(self.config, self.field, val)

    def update(self, val):
        self.getValue().update(val)


def pidIsActive(pid):
    try:
        os.kill(pid, 0)
        return True
    except OSError, oe:
        if oe.errno == errno.ESRCH:
            return False
        else:
            raise


def getPid(pidPath):
    try:
        pidFile = open(pidPath, 'r')
    except IOError, ie:
        if ie.errno == errno.ENOENT:
            return None
        else:
            raise
    pid = int(pidFile.read())
    if pidIsActive(pid):
        return pid
    else:
        print ('getPid: process does not appear to be running, removing stale pid file "%s"'
               % pidPath)
        os.unlink(pidPath)
        return None


def waitUntilDead(pid, timeout):
    startTime = time.time()
    while 1:
        elapsed = time.time() - startTime
        if elapsed > timeout:
            return False
        if not pidIsActive(pid):
            return True
        gevent.sleep(0.1)
