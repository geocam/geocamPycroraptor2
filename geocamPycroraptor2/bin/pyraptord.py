#!/usr/bin/env python
# __BEGIN_LICENSE__
# Copyright (C) 2008-2010 United States Government as represented by
# the Administrator of the National Aeronautics and Space Administration.
# All Rights Reserved.
# __END_LICENSE__

import os
import logging
import errno
import signal
import time

import zerorpc

from geocamPycroraptor2.manager import Manager
from geocamPycroraptor2.util import getPid, waitUntilDead


def getPidForManager(m):
    return getPid(os.path.join(m._logDir, m._pidFile))


def start(m):
    pid = getPidForManager(m)
    if pid is None:
        startInternal(m)
    else:
        print 'pyraptord is already running, pid %s' % pid


def startInternal(m):
    print 'starting pyraptord...'
    m._start()
    s = zerorpc.Server(m)
    s.bind(m._port)
    logging.info('pyraptord: listening on %s', m._port)
    print 'started'
    s.run()


def stop(m):
    pid = getPidForManager(m)
    if pid:
        print 'stopping pyraptord (first attempt, SIGTERM), pid %s...' % pid
        os.kill(pid, signal.SIGTERM)
        isDead = waitUntilDead(pid, timeout=5)
        if isDead:
            print 'stopped'
            return True
        print 'stopping pyraptord (second attempt, SIGKILL), pid %s...' % pid
        os.kill(pid, signal.SIGKILL)
        isDead = waitUntilDead(pid, timeout=5)
        if isDead:
            logging.info('stopped')
            return True
        print "can't kill running pyraptord, pid %s", pid
        return False
    else:
        print 'pyraptord does not appear to be running'
        return True


def restart(m):
    print 'restarting pyraptord'
    isStopped = stop(m)
    if isStopped:
        startInternal(m)


def status(m):
    pid = getPidForManager(m)
    if pid is None:
        print 'pyraptord is stopped'
    else:
        print 'pyraptord is running, pid %s' % pid


COMMAND_REGISTRY = {
    'start': start,
    'stop': stop,
    'restart': restart,
    'status': status
}


def pyraptord(handler, opts):
    m = Manager(opts)
    logging.basicConfig(level=logging.DEBUG)
    handler(m)


def main():
    import optparse
    parser = optparse.OptionParser('usage: %prog <start|stop|restart|status>')
    parser.add_option('-c', '--config',
                      help='Pycroraptor config file to use [%default]',
                      default='pycroraptor.yaml')
    parser.add_option('-f', '--foreground',
                      action='store_true', default=False,
                      help='Run in foreground (do not daemonize)')
    parser.add_option('-n', '--name',
                      help='Name of pyraptord zerorpc service [%default]',
                      default='pyraptord')
    opts, args = parser.parse_args()
    if len(args) != 1:
        parser.error('expected exactly 1 arg')

    cmd = args[0]
    handler = COMMAND_REGISTRY.get(cmd)
    if handler is None:
        parser.error('unknown command "%s"' % cmd)

    pyraptord(handler, opts)


if __name__ == '__main__':
    main()
