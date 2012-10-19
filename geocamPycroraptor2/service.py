# __BEGIN_LICENSE__
# Copyright (C) 2008-2010 United States Government as represented by
# the Administrator of the National Aeronautics and Space Administration.
# All Rights Reserved.
# __END_LICENSE__

import subprocess
import shlex
import logging
import os
import signal
import errno

import gevent
import gevent.monkey
gevent.monkey.patch_all(thread=False)

from geocamPycroraptor2.util import trackerG
from geocamPycroraptor2.signals import SIG_VERBOSE
from geocamPycroraptor2 import prexceptions, log
from geocamPycroraptor2 import status as statuslib


class Service(object):
    def __init__(self, name, config, parent):
        self._name = name
        self._config = config
        self._proc = None
        self._childStdin = None
        self._tslineLogger = None
        self._logBuffer = None
        self._logger = None
        self._outLogger = None
        self._errLogger = None
        self._eventLogger = None
        self._stdinLogger = None
        self._statusDict = None
        self._status = None
        self._jobs = []
        self._parent = parent
        self._env = {'name': self._name}
        self._log = None
        self._setStatus({'status': statuslib.NOT_STARTED})

    def getCommand(self):
        return self._config.get('command',
                                self._name)

    def getLogNameTemplate(self):
        return self._config.get('log',
                                '${name}_${unique}.txt')

    def getWorkingDir(self):
        return self._config.get('workingDir')

    def getEnvVariables(self):
        return self._config.get('env', {})

    def start(self):
        if not self.isStartable():
            raise prexceptions.ServiceAlreadyActive(self._name)

        cmdArgs = shlex.split(self.getCommand())

        self._logger = logging.getLogger('service.%s' % self._name)
        self._logger.setLevel(logging.DEBUG)
        self._logger.propagate = False

        #self._logBuffer = log.LineBuffer()
        # FIX: add handler for line buffer

        logName = self.getLogNameTemplate()
        if logName is None:
            self._log = None
        else:
            logPath = os.path.join(self._parent._logDir,
                                   logName)
            _fname, self._log = (log.openLogFromTemplate
                                 (self._name,
                                  logPath,
                                  self._env))

            #sh = logging.StreamHandler(self._log)
            sh = log.AutoFlushStreamHandler(self._log)
            sh.setLevel(logging.DEBUG)
            sh.setFormatter(log.UtcFormatter('%(asctime)s %(name)s %(message)s'))
            self._logger.addHandler(sh)

        childStdoutReadFd, childStdoutWriteFd = trackerG.openpty(self._name)
        childStderrReadFd, childStderrWriteFd = trackerG.openpty(self._name)
        trackerG.debug()

        self._eventLogger = self._logger.getChild('evt n')
        self._eventLogger.setLevel(logging.DEBUG)

        workingDir = self.getWorkingDir()
        if workingDir:
            os.chdir(workingDir)

        childEnv = os.environ.copy()
        for k, v in self.getEnvVariables().iteritems():
            if v == None:
                if k in childEnv:
                    del childEnv[k]
            else:
                childEnv[k] = v

        self._eventLogger.info('starting')
        escapedArgs = ' '.join(['"%s"' % arg
                                for arg in cmdArgs])
        self._eventLogger.info('command: %s', escapedArgs)

        startupError = None
        try:
            self._proc = subprocess.Popen(cmdArgs,
                                          stdin=subprocess.PIPE,
                                          stdout=childStdoutWriteFd,
                                          stderr=childStderrWriteFd,
                                          env=childEnv,
                                          close_fds=True)
        except OSError, oe:
            if oe.errno == errno.ENOENT:
                startupError = ('is executable "%s" in PATH? Popen call returned no such file or directory'
                                % cmdArgs[0])
            else:
                startupError = oe
        except Exception, exc:
            startupError = exc
        trackerG.close(childStdoutWriteFd)
        trackerG.close(childStderrWriteFd)
        if startupError is not None:
            self._eventLogger.warning('startup error: %s', startupError)
            self._parent._logger.debug('failed to start service %s', self._name)
            self._setStatus(dict(status=statuslib.FAILED,
                                 procStatus=statuslib.ERROR_EXIT,
                                 returnValue=1,
                                 startupFailed=1))
            self._postExitCleanup()
        else:
            self._stdinLogger = self._logger.getChild('inp')
            self._stdinLogger.setLevel(logging.DEBUG)

            self._outLogger = (log.StreamLogger
                               (childStdoutReadFd,
                                self._logger.getChild('out')))

            self._errLogger = (log.StreamLogger
                               (childStderrReadFd,
                                self._logger.getChild('err')))
            self._childStdin = self._proc.stdin
            self._setStatus(dict(status=statuslib.RUNNING,
                                 procStatus=statuslib.RUNNING,
                                 pid=self._proc.pid))

    def stop(self):
        if not self.isActive():
            raise prexceptions.ServiceNotActive(self._name)

        statusDict = self._statusDict.copy()
        statusDict['status'] = statuslib.STOPPING
        self._setStatus(statusDict)

        self._jobs.append(gevent.spawn(self._stopInternal))

    def getStatus(self):
        return self._statusDict

    def isActive(self):
        return statuslib.isActive(self._status)

    def isStartable(self):
        return statuslib.isStartable(self._status)

    def _stopInternal(self):
        self._proc.send_signal(signal.SIGTERM)
        gevent.sleep(5)
        self._proc.send_signal(signal.SIGKILL)

    def _setStatus(self, statusDict):
        self._statusDict = statusDict
        self._status = statusDict['status']

    def _cleanup(self):
        if self._proc and self._proc.poll() != None:
            if self._proc.returncode < 0:
                sigNum = -self._proc.returncode
                if sigNum in (signal.SIGTERM, signal.SIGHUP):
                    status0 = statuslib.ABORTED
                else:
                    status0 = statuslib.FAILED
                newStatus = dict(status=status0,
                                 procStatus=statuslib.SIGNAL_EXIT,
                                 sigNum=sigNum)
                if sigNum in SIG_VERBOSE:
                    newStatus.update(SIG_VERBOSE[sigNum])
            elif self._proc.returncode > 0:
                newStatus = dict(status=statuslib.FAILED,
                                 procStatus=statuslib.ERROR_EXIT,
                                 returnValue=self._proc.returncode)
            else:
                newStatus = dict(status=statuslib.SUCCESS,
                                 procStatus=statuslib.CLEAN_EXIT,
                                 returnValue=0)
            self._setStatus(newStatus)
            self._postExitCleanup()
            self._proc = None

    def _postExitCleanup(self):
        self._proc = None
        for job in self._jobs:
            job.kill()
        self._jobs = []
        if self._childStdin:
            self._childStdin.close()
            self._childStdin = None
        if self._outLogger:
            self._outLogger.stop()
            self._outLogger = None
        if self._errLogger:
            self._errLogger.stop()
            self._errLogger = None
        if self._eventLogger:
            self._eventLogger = None
        if self._stdinLogger:
            self._stdinLogger = None
        self._log.flush()
        self._log.close()
        # note: keep self._logBuffer around in case a client requests old log data.
        #  it will be reinitialized the next time the task is started.
        # self._checkForPendingRestart()

    def stdin(self, text):
        if not self.isActive():
            raise prexceptions.ServiceNotActive(self._name)

        self._stdinLogger.info(log.escapeEndOfLine(text))
        self._childStdin.write(text)
        self._childStdin.flush()
