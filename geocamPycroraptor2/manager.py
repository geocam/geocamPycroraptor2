# __BEGIN_LICENSE__
# Copyright (C) 2008-2010 United States Government as represented by
# the Administrator of the National Aeronautics and Space Administration.
# All Rights Reserved.
# __END_LICENSE__

import os
import logging

import gevent
import gevent.monkey
gevent.monkey.patch_all(thread=False)

from geocamPycroraptor2.util import loadConfig
from geocamPycroraptor2.service import Service
from geocamPycroraptor2 import prexceptions, daemonize


class Manager(object):
    def __init__(self, opts):
        self._opts = opts
        self._config = loadConfig(opts.config)
        self._name = opts.name
        self._logDir = self._config.get('LOG_DIR', '/tmp/pyraptord/logs')
        self._logFile = self._config.get('LOG_FILE', 'pyraptord_${unique}.txt')
        self._pidFile = self._config.get('PID_FILE', 'pyraptord_pid.txt')

    def _start(self):
        self._ports = loadConfig(self._config.PORTS)
        self._port = self._ports[self._name]

        if not self._opts.foreground:
            (daemonize.daemonize
             (os.path.join(self._logDir, self._logFile),
              {},
              os.path.join(self._logDir, self._pidFile)))

        self._services = {}
        if 'startup' in self._config.GROUPS:
            startupGroup = self._config.GROUPS.startup
            logging.debug('startup group: %s', startupGroup)
            for svcName in startupGroup:
                print 'here0'
                self.start(svcName)
        else:
            logging.debug('no group named "startup"')
        print 'here1'
        self._jobs = []
        self._jobs.append(gevent.spawn(self._cleanupChildren))
        print 'here2'

    def _cleanupChildren(self):
        while 1:
            for svc in self._services.itervalues():
                svc._cleanup()
            gevent.sleep(0.1)

    def _getService(self, svcName):
        svcConfig = self._config.SERVICES.get(svcName)
        if svcConfig is None:
            raise prexceptions.UnknownService(svcName)

        svc = self._services.get(svcName)
        if svc is None:
            svc = Service(svcName,
                          svcConfig,
                          self)
            self._services[svcName] = svc

        return svc

    def start(self, svcName):
        """
        Start *svcName*.
        """
        self._getService(svcName).start()

    def stdin(self, svcName, text):
        """
        Write *text* to the stdin stream for *svcName*.
        """
        self._getService(svcName).stdin(text)

    def stop(self, svcName):
        """
        Stop *svcName*.
        """
        self._getService(svcName).stop()

    def getStatus(self, svcName):
        """
        Get status of *svcName*.
        """
        return self._getService(svcName).getStatus()
