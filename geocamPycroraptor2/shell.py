# __BEGIN_LICENSE__
# Copyright (C) 2008-2010 United States Government as represented by
# the Administrator of the National Aeronautics and Space Administration.
# All Rights Reserved.
# __END_LICENSE__

# pylint: disable=E0611

import gevent
import gevent.monkey
gevent.monkey.patch_all(thread=False)
import zerorpc
from IPython.config.loader import Config
from IPython.frontend.terminal.embed import InteractiveShellEmbed
from IPython.lib.inputhook import inputhook_manager, stdin_ready


from geocamPycroraptor2.util import loadConfig

INTRO = """
Welcome to pyrterm!

This is an IPython shell with the pyraptord zerorpc service bound to the
"d" variable. You can run commands like d.start("mytask").
"""

ipshell = InteractiveShellEmbed(config=Config(),
                                banner1=INTRO)


def inputhook_gevent():
    try:
        while not stdin_ready():
            gevent.sleep(0.05)
    except KeyboardInterrupt:
        pass
    return 0

# tell ipython to use gevent as the mainloop
inputhook_manager.set_inputhook(inputhook_gevent)


class Shell(object):
    def __init__(self, configPath):
        self._config = loadConfig(configPath)
        self._ports = loadConfig(self._config.PORTS)

    def run(self):
        port = self._ports.pyraptord.rpc
        print 'connecting to pyraptord at %s' % port
        d = zerorpc.Client(port)  # pylint: disable=W0612
        ipshell()
