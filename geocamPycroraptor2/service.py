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
import sys
import os
import fcntl
import traceback

import gevent
import gevent.monkey
gevent.monkey.patch_all(thread=False)

from geocamPycroraptor2.util import trackerG
from geocamPycroraptor2.signals import SIG_VERBOSE
from geocamPycroraptor2 import prexceptions, log
from geocamPycroraptor2 import status as statuslib


try:
    MAXFD = os.sysconf("SC_OPEN_MAX")
except:
    MAXFD = 256


class PopenNoErrPipe(object):
    """
    This is a re-implementation of a subset of subprocess.Popen. Its main
    purpose is to support piping stdin or stdout to a named pipe without
    blocking the parent process.

    (Normally an open() call on a named pipe blocks until there is a
    peer connected to the other end of the pipe, and in the normal
    Popen() implementation, when the child blocks before the exec()
    call, it causes the parent to block as well.)
    """

    def _set_cloexec_flag(self, fd, cloexec=True):
        try:
            cloexec_flag = fcntl.FD_CLOEXEC
        except AttributeError:
            cloexec_flag = 1

        old = fcntl.fcntl(fd, fcntl.F_GETFD)
        if cloexec:
            fcntl.fcntl(fd, fcntl.F_SETFD, old | cloexec_flag)
        else:
            fcntl.fcntl(fd, fcntl.F_SETFD, old & ~cloexec_flag)

    def __init__(self, args,
                 stdin=None,
                 stdout=None,
                 stderr=None,
                 preexec_fn=None,
                 env=None,
                 close_fds=True,
                 cwd=None):
        self.returncode = None
        self.pid = None

        if stdin is subprocess.PIPE:
            stdin, stdinWrite = os.pipe()
            self._set_cloexec_flag(stdin)
            self._set_cloexec_flag(stdinWrite)
        else:
            stdinWrite = None

        pid = os.fork()
        assert pid >= 0
        if pid == 0:
            # child
            try:
                if stdin is not None:
                    os.dup2(stdin, 0)

                if stdout is not None:
                    os.dup2(stdout, 1)

                if stderr is not None:
                    os.dup2(stderr, 2)

                if close_fds:
                    os.closerange(3, MAXFD)

                if cwd:
                    os.chdir(cwd)

                if preexec_fn:
                    preexec_fn()

                if env:
                    os.execvpe(args[0], args, env)
                else:
                    os.execvp(args[0], args)

                assert False, 'should never reach this point'

            except:
                print >> sys.stderr, traceback.format_exc()
                print >> sys.stderr, 'service startup failed'
                os._exit(1)

            finally:
                # make really sure the child exits on failure.
                # otherwise we can get some really pathological error
                # modes if, for example, the traceback above raises an
                # exception.
                os._exit(1)

        else:
            # parent
            self.pid = pid
            if stdinWrite:
                self.stdin = os.fdopen(stdinWrite, 'wb', 0)
            else:
                self.stdin = None

    def poll(self):
        if self.returncode is None:
            try:
                pid, sts = os.waitpid(self.pid, os.WNOHANG)
                if pid == self.pid:
                    if os.WIFSIGNALED(sts):
                        self.returncode = -os.WTERMSIG(sts)
                    elif os.WIFEXITED(sts):
                        self.returncode = os.WEXITSTATUS(sts)
                    else:
                        raise RuntimeError("don't understand exit status %s" % sts)
            except os.error as e:
                if e.errno == errno.ECHILD:
                    self.returncode = 0
        return self.returncode

    def send_signal(self, sig):
        os.kill(self.pid, sig)


class Service(object):
    def __init__(self, name, parent):
        self._name = name
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
        self._restart = False
        self._streamHandler = None

    def getConfig(self):
        return self._parent.getServiceConfig(self._name)

    def getCommand(self):
        return self.getConfig().get('command',
                                    self._name)

    def getLogNameTemplate(self):
        return self.getConfig().get('log',
                                    '${name}_${unique}.txt')

    def getWorkingDir(self):
        return self.getConfig().get('cwd')

    def getEnvVariables(self):
        return self.getConfig().get('env', {})

    def getStdout(self):
        return self.getConfig().get('stdout')

    def getStdin(self):
        return self.getConfig().get('stdin')

    def openExternalStreams(self):
        """
        If needed, open streams that connect the child process console
        to something other than the pyraptord parent process.

        We do this in the child process after the fork because it may
        block (for example, when the path is a named pipe and there is
        no peer connected to the other end of the pipe yet).
        """

        stdinPath = self.getStdin()
        if stdinPath:
            fd = os.open(stdinPath, os.O_RDONLY)
            assert fd >= 0
            os.dup2(fd, 0)
            os.close(fd)

        stdoutPath = self.getStdout()
        if stdoutPath:
            try:
                fd = os.open(stdoutPath, os.O_WRONLY)
            except:
                print >> sys.stderr, traceback.format_exc()
                print >> sys.stderr, 'could not open %s for writing' % stdoutPath
                os._exit(1)
            assert fd >= 0
            os.dup2(fd, 1)
            os.close(fd)


    def start(self):
        if not self.isStartable():
            raise prexceptions.ServiceAlreadyActive(self._name)

        cmdArgs = shlex.split(self.getCommand().encode('utf8'))

        self._logger = logging.getLogger('service.%s' % self._name)
        self._logger.setLevel(logging.DEBUG)
        self._logger.propagate = False

        #self._logBuffer = log.LineBuffer()
        # FIX: add handler for line buffer

        logName = self.getLogNameTemplate()
        self._log = None
        if logName is not None:
            logPath = os.path.join(self._parent._logDir,
                                   logName)
            try:
                _fname, self._log = (log.openLogFromTemplate
                                     (self._name,
                                      logPath,
                                      self._env))
            except:
                self._parent._logger.warning('could not open log file for service "%s" at path "%s"',
                                             self._name, logPath)

        if self._log is not None:
            #sh = logging.StreamHandler(self._log)
            self._streamHandler = log.AutoFlushStreamHandler(self._log)
            self._streamHandler.setLevel(logging.DEBUG)
            self._streamHandler.setFormatter(log.UtcFormatter('%(asctime)s %(name)s %(message)s'))
            self._logger.addHandler(self._streamHandler)

        stdinPath = self.getStdin()
        if stdinPath is None:
            childStdinReadFd = subprocess.PIPE
            popenStdin = childStdinReadFd
        else:
            popenStdin = None

        stdoutPath = self.getStdout()
        if stdoutPath is None:
            childStdoutReadFd, childStdoutWriteFd = trackerG.openpty(self._name)
            popenStdout = childStdoutWriteFd
        else:
            popenStdout = None
        childStderrReadFd, childStderrWriteFd = trackerG.openpty(self._name)
        trackerG.debug()

        self._eventLogger = self._logger.getChild('evt n')
        self._eventLogger.setLevel(logging.DEBUG)

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

        if self.getStdin() or self.getStdout():
            popenClass = PopenNoErrPipe
        else:
            popenClass = subprocess.Popen

        startupError = None
        try:
            self._proc = popenClass(cmdArgs,
                                    stdin=popenStdin,
                                    stdout=popenStdout,
                                    stderr=childStderrWriteFd,
                                    env=childEnv,
                                    close_fds=True,
                                    cwd=self.getWorkingDir(),
                                    preexec_fn=self.openExternalStreams)
        except OSError, oe:
            if oe.errno == errno.ENOENT:
                startupError = ('is executable "%s" in PATH? Popen call returned no such file or directory'
                                % cmdArgs[0])
            else:
                startupError = oe
        except Exception, exc:
            startupError = exc
        if not stdoutPath:
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
            if not stdinPath:
                self._stdinLogger = self._logger.getChild('inp')
                self._stdinLogger.setLevel(logging.DEBUG)
                self._childStdin = self._proc.stdin

            if not stdoutPath:
                self._outLogger = (log.StreamLogger
                                   (childStdoutReadFd,
                                    self._logger.getChild('out'),
                                    label='%s.out' % self._name))

            self._errLogger = (log.StreamLogger
                               (childStderrReadFd,
                                self._logger.getChild('err'),
                                label='%s.err' % self._name))
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

    def restart(self):
        if self.isActive():
            self._restart = True
            self.stop()
        else:
            self.start()

    def getStatus(self):
        return self._statusDict

    def isActive(self):
        return statuslib.isActive(self._status)

    def isStartable(self):
        return statuslib.isStartable(self._status)

    def _stopInternal(self):
        if self._proc:
            self._eventLogger.warning('received stop command, sending SIGTERM signal')
            self._proc.send_signal(signal.SIGTERM)
        gevent.sleep(5)
        if self._proc:
            self._eventLogger.warning('service did not stop after first attempt, sending SIGKILL signal')
            self._proc.send_signal(signal.SIGKILL)

    def _setStatus(self, statusDict):
        self._statusDict = statusDict
        self._status = statusDict['status']

    def _cleanup(self):
        if self._proc and self._proc.poll() != None:
            # process exited

            # bit of a hack... leave some time to collect console
            # output. needs to be longer than the refresh period in
            # geocamUtil.gevent.util.copyFileToQueue()
            gevent.sleep(0.15)

            if self._proc.returncode < 0:
                sigNum = -self._proc.returncode
                if sigNum in (signal.SIGHUP, signal.SIGINT, signal.SIGTERM):
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
            self._eventLogger.warning('stopped')
            self._eventLogger.warning('status: %s', newStatus)
            self._postExitCleanup()

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
        if self._streamHandler:
            self._logger.removeHandler(self._streamHandler)
            self._streamHandler = None
        if self._log:
            self._log.close()
            self._log = None
        # note: keep self._logBuffer around in case a client requests old log data.
        #  it will be reinitialized the next time the task is started.
        if self._restart:
            self._restart = False
            self.start()

    def stdin(self, text):
        if not self.isActive():
            raise prexceptions.ServiceNotActive(self._name)

        self._stdinLogger.info(log.escapeEndOfLine(text))
        self._childStdin.write(text)
        self._childStdin.flush()
