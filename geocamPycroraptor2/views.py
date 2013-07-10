# __BEGIN_LICENSE__
# Copyright (C) 2008-2010 United States Government as represented by
# the Administrator of the National Aeronautics and Space Administration.
# All Rights Reserved.
# __END_LICENSE__

import json

from django.http import HttpResponse, HttpResponseNotAllowed, Http404, HttpResponseBadRequest
from django.shortcuts import render_to_response
from django.template import RequestContext
from django.conf import settings
import zerorpc

from geocamPycroraptor2 import status as statuslib


def getPyraptordClient():
    ports = json.loads(file(settings.ZEROMQ_PORTS, 'r').read())
    rpcPort = ports['pyraptord']['rpc']
    client = zerorpc.Client(rpcPort)
    return client


def renderDashboard(request, pyraptord):
    logDir = getattr(settings, 'SERVICES_LOG_DIR_URL', None)

    status = pyraptord.getStatusAll()
    serviceConfig = pyraptord.getConfig('SERVICES')

    configItems = serviceConfig.items()
    configItems.sort()
    tb = []
    tb.append('<table>')
    for name, cfg in configItems:
        procStatus = status.get(name, {'status': 'notStarted'})
        procMode = procStatus.get('status')
        procColor = statuslib.getColor(procMode)
        tb.append('<tr>')
        tb.append('<td>%s</td>' % name)
        tb.append('<td style="background-color: %s;">%s</td>' % (procColor, procMode))
        if logDir:
            tb.append('<td><a href="%s%s_latest.txt">latest log</a></td>'
                      % (logDir, name))
            tb.append('<td><a href="%s%s_previous.txt">previous log</a></td>'
                      % (logDir, name))
        tb.append('</tr>')

    tb.append('<tr>')
    if logDir:
        tb.append('<td style="font-weight: bold;">pyraptord</td>')
        tb.append('<td></td>')
        tb.append('<td><a href="%spyraptord_latest.txt">latest log</a></td>'
                  % logDir)
        tb.append('<td><a href="%spyraptord_previous.txt">previous log</a></td>'
                  % logDir)
    tb.append('</tr>')

    tb.append('</table>')
    tb.append('<div style="margin-top: 0.5em;"><a href="%s">all logs</a></div>' % logDir)

    return render_to_response('geocamPycroraptor2/dashboard.html',
                              {'html': ''.join(tb)},
                              context_instance=RequestContext(request))


def dashboard(request):
    pyraptord = getPyraptordClient()
    return renderDashboard(request, pyraptord)
