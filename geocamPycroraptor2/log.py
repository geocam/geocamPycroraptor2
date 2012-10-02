# __BEGIN_LICENSE__
# Copyright (C) 2008-2010 United States Government as represented by
# the Administrator of the National Aeronautics and Space Administration.
# All Rights Reserved.
# __END_LICENSE__

import os
import re
import datetime
from string import Template

import gevent

from geocamUtil.gevent.util import queueFromFile, LineParser

from geocamPycroraptor2.util import trackerG


UNIQUE_REGEX = r'\$\{unique\}|\$unique\b'


def getFileNameTimeString(timestamp=None):
    if timestamp is None:
        timestamp = datetime.datetime.utcnow()
    us = timestamp.microsecond
    seconds = timestamp.strftime('%Y-%m-%d-%H%M%S')
    return '%s-%06d-UTC' % (seconds, us)


def getTimeString(timestamp=None):
    if timestamp is None:
        timestamp = datetime.datetime.utcnow()
    return timestamp.isoformat() + 'Z'


def openLogFromPath(owner, path, mode='a+'):
    logDir = os.path.dirname(path)
    if not os.path.exists(logDir):
        os.makedirs(logDir)
    logFile = trackerG.open(owner, path, mode, 0)
    return logFile


def expandVal(tmpl, env):
    if '$' in tmpl:
        return Template(tmpl).substitute(env)
    else:
        return tmpl


def _expandUniq(fname, uniq, env):
    fnameWithUniq = re.sub(UNIQUE_REGEX,
                           uniq,
                           fname)
    return expandVal(fnameWithUniq, env)


def _forceSymLink(src, target):
    if os.path.lexists(target):
        if os.path.islink(target):
            os.unlink(target)
        else:
            raise Exception('_forceSymLink: %s exists and is not a symlink, not overwriting'
                            % target)
    else:
        if not os.path.isdir(os.path.dirname(target)):
            os.makedirs(os.path.dirname(target))
    try:
        os.symlink(src, target)
    except OSError, err:
        raise OSError('%s [in symlink "%s" "%s"]'
                      % (str(err), src, target))


def _findUniqueFileAndSetSymLink(fnameTemplate, env):
    fname = _expandUniq(fnameTemplate,
                        getFileNameTimeString(), env)
    symSrc = os.path.basename(fname)
    symTarget = _expandUniq(fnameTemplate, 'latest', env)
    _forceSymLink(symSrc, symTarget)
    return fname


def openLogFromTemplate(owner, fnameTemplate, env):
    fname = _findUniqueFileAndSetSymLink(fnameTemplate, env)
    return (fname, openLogFromPath(owner, fname))


class TimestampLine:
    def __init__(self, streamName, lineType, text, timestamp=None):
        if timestamp == None:
            timestamp = datetime.datetime.now()
        self.streamName = streamName
        self.lineType = lineType
        self.text = text
        self.timestamp = timestamp


class LineSource(object):
    def __init__(self, lineHandler=None):
        self._lineHandlers = {}
        self._lineHandlerCount = 0
        if lineHandler:
            self.addLineHandler(lineHandler)

    def addLineHandler(self, handler):
        handlerRef = self._lineHandlerCount
        self._lineHandlerCount += 1
        self._lineHandlers[handlerRef] = handler
        return handlerRef

    def delLineHandler(self, handlerRef):
        del self._lineHandlers[handlerRef]

    def handleLine(self, tsline):
        for hnd in self._lineHandlers.itervalues():
            hnd(tsline)


class TimestampLineParser(LineParser, LineSource):
    def __init__(self, streamName,
                 lineHandler=None,
                 maxLineLength=160):
        LineParser.__init__(self, self.handleRawLine)
        LineSource.__init__(self, lineHandler)
        self._streamName = streamName

    def timestamp(self, line):
        if line.endswith('\r\n'):
            text = line[:-2]
            lineType = 'n'
        elif line.endswith('\n'):
            text = line[:-1]
            lineType = 'n'
        else:
            text = line
            lineType = 'c'
        return TimestampLine(self._streamName,
                             lineType,
                             text,
                             datetime.datetime.utcnow())

    def handleRawLine(self, text):
        self.handleLine(self.timestamp(text))


class TimestampLineSource(TimestampLineParser):
    def __init__(self, streamName, fd,
                 lineHandler=None,
                 maxLineLength=160):
        (super(TimestampLineSource, self).__init__
         (streamName, lineHandler, maxLineLength))
        self._fd = fd
        self._q = queueFromFile(fd, maxLineLength)
        self._job = gevent.spawn(self._handleQueue)
        
    def stop(self):
        trackerG.close(self._fd)
        self._q.put(StopIteration)
        if self._job is not None:
            self._job.kill()
            self._job = None

    def _handleQueue(self):
        print '_hq'
        for line in self._q:
            print 'yo log'
            self.handleRawLine(line)


class EventLineSource(LineSource):
    def __init__(self, streamName,
                 lineHandler=None):
        LineSource.__init__(self, lineHandler)
        self._streamName = streamName

    def stop(self):
        pass

    def log(self, text):
        self.handleLine(TimestampLine
                        (self._streamName,
                         'n',
                         text,
                         datetime.datetime.utcnow()))


class LineBuffer(LineSource):
    def __init__(self, lineHandler=None, maxSize=2048):
        LineSource.__init__(self, lineHandler)
        self._maxSize = maxSize
        self._lines = []
        self._lineCount = 0

    def addLine(self, tsline):
        DELETE_SIZE = self._maxSize // 2
        if len(self._lines) == self._maxSize - DELETE_SIZE:
            del self._lines[0:DELETE_SIZE]
        tsline.lineCount = self._lineCount
        self._lines.append(tsline)
        self._lineCount += 1
        self.handleLine(tsline)

    def getLines(self, minTime=None, maxLines=None):
        n = len(self._lines)
        if minTime:
            minIndex = n
            for i in reversed(xrange(0, n)):
                line = self._lines[i]
                if line.timestamp < minTime:
                    minIndex = i + 1
                    break
        else:
            minIndex = 0
        if maxLines:
            minIndex = max(minIndex, n - maxLines)
        return self._lines[minIndex:]


class TimestampLineLogger:
    def __init__(self, stream):
        self._stream = stream

    def handleLine(self, tsline):
        self._stream.write('%s %s %s %s\n'
                           % (tsline.streamName,
                              tsline.lineType,
                              getTimeString(tsline.timestamp),
                              tsline.text))


class StreamLogger(TimestampLineParser):
    def __init__(self, streamName, outStream,
                 maxLineLength=160):
        self._logger = TimestampLineLogger(outStream)
        TimestampLineParser.__init__(self,
                                     streamName,
                                     self._logger.handleLine,
                                     maxLineLength)
