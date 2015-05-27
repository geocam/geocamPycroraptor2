# __BEGIN_LICENSE__
# Copyright (C) 2008-2010 United States Government as represented by
# the Administrator of the National Aeronautics and Space Administration.
# All Rights Reserved.
# __END_LICENSE__

import sys
import json

from django.shortcuts import render_to_response
from django.template import RequestContext
from django.conf import settings
from django.middleware.csrf import get_token
import zerorpc

from geocamPycroraptor2 import status as statuslib


def getPyraptordClient(clientName='pyraptord'):
    ports = json.loads(file(settings.ZEROMQ_PORTS, 'r').read())
    rpcPort = ports[clientName]['rpc']
    client = zerorpc.Client(rpcPort)
    return client


def commandButton(cmd, svcName, disabled=False):
    disabledFlag = ''
    if disabled:
        disabledFlag = ' disabled="disabled"'
    return ('<button type="submit" name="cmd" value="%s.%s"%s>%s</button>'
            % (cmd, svcName, disabledFlag, cmd))


def renderDashboard(request, pyraptord=None, cmd=None, response=None):
    if pyraptord is None:
        pyraptord = getPyraptordClient()

    logDir = getattr(settings, 'SERVICES_LOG_DIR_URL', None)

    status = pyraptord.getStatusAll()
    serviceConfig = pyraptord.getConfig('SERVICES')

    configItems = serviceConfig.items()
    configItems.sort()
    tb = []
    tb.append('<h1 style="font-weight: bold;">Service Manager</h1>')
    if cmd is not None:
        tb.append('<div style="margin: 0.5em; font-size: 1.2em; background-color: #ccc;"><i>command:</i> %s <i>response:</i> %s</div>'
                  % (cmd, response))
    tb.append('<div style="margin: 0.5em; font-size: 1.2em; "><a href="." style="font-size: 1.2em;">refresh</a></div>')
    tb.append('<form method="post" action=".">')
    tb.append('<input type="hidden" name="csrfmiddlewaretoken" value="%s"/>' % get_token(request))
    tb.append('<table>')
    for name, _cfg in configItems:
        procStatus = status.get(name, {'status': 'notStarted'})
        procMode = procStatus.get('status')
        procColor = statuslib.getColor(procMode)
        tb.append('<tr>')
        tb.append('<td>%s</td>' % name)
        tb.append('<td style="background-color: %s;">%s</td>' % (procColor, procMode))
        tb.append('<td>%s</td>' % commandButton('start', name, disabled=not statuslib.isStartable(procMode)))
        tb.append('<td>%s</td>' % commandButton('stop', name, disabled=not statuslib.isActive(procMode)))
        tb.append('<td>%s</td>' % commandButton('restart', name))
        if logDir:
            tb.append('<td><a href="%s%s_latest.txt">latest log</a></td>'
                      % (logDir, name))
            tb.append('<td><a href="%s%s_previous.txt">previous log</a></td>'
                      % (logDir, name))
        tb.append('</tr>')

    tb.append('<tr>')
    if logDir:
        tb.append('<td style="font-weight: bold;">pyraptord</td>')
        tb.append('<td colspan="4"></td>')
        tb.append('<td><a href="%spyraptord_latest.txt">latest log</a></td>'
                  % logDir)
        tb.append('<td><a href="%spyraptord_previous.txt">previous log</a></td>'
                  % logDir)
    tb.append('</tr>')

    tb.append('</table>')
    tb.append('<div style="margin-top: 0.5em;"><a href="%s">all logs</a></div>' % logDir)
    tb.append('</form>')

    return render_to_response('geocamPycroraptor2/dashboard.html',
                              {'html': ''.join(tb)},
                              context_instance=RequestContext(request))


def runCommandInternal(pyraptord, cmd, svcName):
    response = 'ok'
    try:
        pyraptord(cmd, svcName)
    except:  # pylint: disable=W0702
        excType, excValue, _excTb = sys.exc_info()
        response = ('%s.%s: %s'
                    % (excType.__module__,
                       excType.__name__,
                       str(excValue)))
    cmdSummary = '%s("%s")' % (cmd, svcName)
    return (cmdSummary, response)


def runCommand(request, cmd, svcName):
    pyraptord = getPyraptordClient()
    cmdSummary, response = runCommandInternal(pyraptord, cmd, svcName)
    return renderDashboard(request,
                           pyraptord=pyraptord,
                           cmd=cmdSummary,
                           response=response)


def dashboard(request):
    if request.method == 'POST':
        cmdPair = request.POST.get('cmd', None)
        if cmdPair:
            cmd, svcName = cmdPair.split('.', 1)
            assert cmd in ('start', 'stop', 'restart')
            return runCommand(request, cmd, svcName)

    return renderDashboard(request)


def stopPyraptordServiceIfRunning(pyraptord, svcName):
    try:
        pyraptord.stop(svcName)
    except zerorpc.RemoteError:
        pass
