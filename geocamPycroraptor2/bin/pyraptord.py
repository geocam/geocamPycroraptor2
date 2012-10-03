#!/usr/bin/env python
# __BEGIN_LICENSE__
# Copyright (C) 2008-2010 United States Government as represented by
# the Administrator of the National Aeronautics and Space Administration.
# All Rights Reserved.
# __END_LICENSE__

import os

import zerorpc

from geocamPycroraptor2.manager import Manager
from geocamPycroraptor2.daemonize import Daemon


def pyraptord(cmd, opts):
    m = Manager(opts)
    d = Daemon(opts.name,
               os.path.join(m._logDir, m._pidFile))

    if cmd in ('start', 'restart'):
        doStart = d.execute(cmd)
        if doStart:
            m._start()
            s = zerorpc.Server(m)
            s.bind(m._port)
            m._logger.info('pyraptord: listening on %s', m._port)
            m._logger.info('started')
            d.writePid()
            s.run()
    else:
        d.execute(cmd)


def main():
    import optparse
    parser = optparse.OptionParser('usage: %prog <start|stop|restart|status>')
    parser.add_option('-c', '--config',
                      help='Pycroraptor config file to use [%default]',
                      default='pycroraptor.json')
    parser.add_option('-f', '--foreground',
                      action='store_true', default=False,
                      help='Run in foreground (do not daemonize)')
    parser.add_option('-n', '--name',
                      help='Name of pyraptord zerorpc service [%default]',
                      default='pyraptord')
    opts, args = parser.parse_args()
    if len(args) == 0:
        cmd = 'start'
    elif len(args) == 1:
        cmd = args[0]
    else:
        parser.error('expected at most 1 command')

    if cmd not in Daemon.COMMANDS:
        parser.error('unknown command "%s"' % cmd)

    pyraptord(cmd, opts)


if __name__ == '__main__':
    main()
