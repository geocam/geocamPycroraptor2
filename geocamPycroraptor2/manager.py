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
    """
    Pyraptord is a process manager that daemonizes and logs the console
    output of managed services, and provides a network API for live
    console interaction and remote start/stop/restart commands.
    """

    def __init__(self, opts):
        self._opts = opts
        self._configPath = opts.config
        self._config = loadConfig(self._configPath)
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
        return [signal.SIGHUP, signal.SIGINT, signal.SIGTERM]

    def _disableGeventDefaultSigintHandler(self):
        h = gevent.hub.get_hub()
        if h.keyboard_interrupt_signal is not None:
            h.keyboard_interrupt_signal.cancel()
            h.keyboard_interrupt_signal = None

    def _start(self):
        fmt = log.UtcFormatter('%(asctime)s %(name)s n %(message)s')

        if self._opts.foreground:
            # send logger output to console
            ch = logging.StreamHandler(sys.stderr)
            ch.setFormatter(fmt)
            ch.setLevel(logging.DEBUG)
            self._logger.addHandler(ch)

        self._logPath = '/dev/null'
        self._logFile = None
        if self._logFname is not None:
            logPathTemplate = os.path.join(self._logDir, self._logFname)
            try:
                self._logPath, self._logFile = (log.openLogFromTemplate
                                                ('pyraptord',
                                                 logPathTemplate,
                                                 {}))
            except:
                self._logger.error('could not open log file %s!', logPathTemplate)

        if self._logFile is not None:
            # send logger output to file
            lh = logging.StreamHandler(self._logFile)
            lh.setFormatter(fmt)
            lh.setLevel(logging.DEBUG)
            self._logger.addHandler(lh)

        self._logger.debug('installing signal handlers')
        for sig in self._getSignalsToHandle():
            signal.signal(sig, self._handleSignal)
        gevent.spawn(self._disableGeventDefaultSigintHandler)

        # load ports config
        self._ports = loadConfig(self._config.PORTS)
        self._port = self._ports[self._name].rpc

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


    def _handleSignal(self, sigNum='unknown', frame=None):
        if sigNum in SIG_VERBOSE:
            desc = SIG_VERBOSE[sigNum]['sigName']
        else:
            desc = 'unknown'
        self._logger.info('caught signal %s (%s), shutting down',
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
            self._checkForQuitComplete()
            gevent.sleep(0.1)

    def _quitInternal(self):
        # leave time to respond to caller before shutting down
        gevent.sleep(0.05)
        self._quitting = True
        if self._preQuitHandler is not None:
            self._preQuitHandler()
        for svc in self._services.itervalues():
            if svc.isActive():
                self._logger.info('stopping %s' % svc._name)
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
        self._logger.debug('received: start %s', svcName)
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
        self._logger.debug('received: stop %s', svcName)
        self._getService(svcName).stop()

    def restart(self, svcName):
        """
        Restart *svcName*.
        """
        self._logger.debug('received: restart %s', svcName)
        self._getService(svcName).restart()

    def getStatus(self, svcName):
        """
        Get status of *svcName*.
        """
        return self._getService(svcName).getStatus()

    def getStatusAll(self):
        """
        Get status of all services.
        """
        return dict([(svcName, svc.getStatus())
                     for svcName, svc in self._services.iteritems()])

    def loadConfig(self, path=None):
        """
        Load a new config file from *path* (defaults to the previous
        config file). Note: you can add or modify services by loading a
        new config, but you must restart pyraptord if you want to remove
        unwanted services or change global settings such as the
        pyraptord zerorpc endpoint.
        """
        self._logger.debug('received: loadConfig %s', path)
        if path is not None:
            self._configPath = os.path.abspath(path)
        newConfig = loadConfig(self._configPath)
        for k, v in newConfig.iteritems():
            if k in self._config and isinstance(v, dict):
                self._config[k].update(v)
            else:
                self._config[k] = v
        self._logger.debug('loaded new config %s', self._configPath)

    def quit(self):
        """
        Stop all managed services and quit pyraptord.
        """
        gevent.spawn(self._quitInternal)
