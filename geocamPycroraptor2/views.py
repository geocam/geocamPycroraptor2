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


def dashboard(request):
    pyraptord = getPyraptordClient()
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
        tb.append('<td style="background-color: %s;">%s</td>' % (procColor, name))
        tb.append('<td style="background-color: %s;">%s</td>' % (procColor, procMode))
        tb.append('</tr>')
    tb.append('</table>')
    return render_to_response('geocamPycroraptor2/dashboard.html',
                              {'html': ''.join(tb)},
                              context_instance=RequestContext(request))
