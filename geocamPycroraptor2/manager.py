# __BEGIN_LICENSE__
# Copyright (C) 2008-2010 United States Government as represented by
# the Administrator of the National Aeronautics and Space Administration.
# All Rights Reserved.
# __END_LICENSE__

import os
import sys
import logging
import signal

import gevent
import gevent.monkey
gevent.monkey.patch_all(thread=False)

from geocamPycroraptor2.util import loadConfig
from geocamPycroraptor2.service import Service
from geocamPycroraptor2.signals import SIG_VERBOSE
from geocamPycroraptor2 import prexceptions, daemonize, log


class Manager(object):
    def __init__(self, opts):
        self._opts = opts
        self._config = loadConfig(opts.config)
        self._name = opts.name
        self._logDir = self._config.get('LOG_DIR', '/tmp/pyraptord/logs')
        self._logFname = self._config.get('LOG_FILE', 'pyraptord_${unique}.txt')
        self._pidFile = self._config.get('PID_FILE', 'pyraptord_pid.txt')
        self._logger = logging.getLogger('pyraptord.evt')
        self._logger.setLevel(logging.DEBUG)
        self._logger.propagate = False
        self._quitting = False
        self._preQuitHandler = None
        self._postQuitHandler = None

    def _getSignalsToHandle(self):
        result = [signal.SIGHUP, signal.SIGTERM]
        if self._opts.foreground:
            result.append(signal.SIGINT)
        return result

    def _start(self):
        fmt = log.UtcFormatter('%(asctime)s %(name)s n %(message)s')

        if self._opts.foreground:
            # send logger output to console
            ch = logging.StreamHandler(sys.stderr)
            ch.setFormatter(fmt)
            ch.setLevel(logging.DEBUG)
            self._logger.addHandler(ch)

        if self._logFname is None:
            self._logPath = '/dev/null'
            self._logFile = None
        else:
            logPathTemplate = os.path.join(self._logDir, self._logFname)
            self._logPath, self._logFile = (log.openLogFromTemplate
                                            ('pyraptord',
                                             logPathTemplate,
                                             {}))

            # send logger output to file
            lh = logging.StreamHandler(self._logFile)
            lh.setFormatter(fmt)
            lh.setLevel(logging.DEBUG)
            self._logger.addHandler(lh)

        self._logger.debug('installing signal handlers')
        for sig in self._getSignalsToHandle():
            signal.signal(sig, self._handleSignal)

        # load ports config
        self._ports = loadConfig(self._config.PORTS)
        self._port = self._ports[self._name]

        if not self._opts.foreground:
            self._logger.debug('daemonizing')
            daemonize.daemonize('pyraptord', self._logFile)

        # start startup services
        self._services = {}
        if 'startup' in self._config.GROUPS:
            startupGroup = self._config.GROUPS.startup
            self._logger.debug('startup group: %s', startupGroup)
            for svcName in startupGroup:
                self.start(svcName)
        else:
            self._logger.debug('no group named "startup"')
        self._jobs = []
        self._jobs.append(gevent.spawn(self._cleanupChildren))

    def _handleSignal(self, sigNum, frame):
        if sigNum in SIG_VERBOSE:
            desc = SIG_VERBOSE[sigNum]['sigName']
        else:
            desc = 'unknown'
        self._logger.info('caught signal %d (%s), shutting down',
                          sigNum, desc)
        try:
            self.quit()
        except:  # pylint: disable=W0702
            self._logger.warning('caught exception during shutdown!')
            self._logger.warning(traceback.format_exc())
            self._logger.warning('now doing a hard exit')
            os._exit(1)

    def _getActiveServices(self):
        return [svc
                for svc in self._services.itervalues()
                if svc.isActive()]

    def _cleanupChildren(self):
        while 1:
            for svc in self._services.itervalues():
                svc._cleanup()
            gevent.sleep(0.1)
        self._checkForQuitComplete()

    def _quitInternal(self):
        # leave time to respond to caller before shutting down
        gevent.sleep(0.05)
        self._quitting = True
        if self._preQuitHandler is not None:
            self._preQuitHandler()
        for svc in self._services.itervalues():
            if svc.isActive():
                svc.stop()
        self._checkForQuitComplete()

    def _checkForQuitComplete(self):
        if self._quitting and not self._getActiveServices():
            self._logger.info('all services stopped')
            if self._postQuitHandler is not None:
                self._postQuitHandler()
            self._logger.info('terminating pyraptord process')
            # exit by clearing the SIGTERM handler and SIGTERM-ing this process.
            # sys.exit() doesn't work with gevent pre-1.0
            signal.signal(signal.SIGTERM, signal.SIG_DFL)
            os.kill(os.getpid(), signal.SIGTERM)

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

    def quit(self):
        """
        Stop all managed services and quit pyraptord.
        """
        gevent.spawn(self._quitInternal)
