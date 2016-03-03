# __BEGIN_LICENSE__
# Copyright (C) 2008-2010 United States Government as represented by
# the Administrator of the National Aeronautics and Space Administration.
# All Rights Reserved.
# __END_LICENSE__

import os
import re
import datetime
import pytz

from string import Template
import logging
import traceback

import gevent

from geocamUtil.geventUtil.util import queueFromFile, LineParser

from geocamPycroraptor2.util import trackerG


UNIQUE_REGEX = r'\$\{unique\}|\$unique\b'


class UtcFormatter(logging.Formatter):
    def formatTime(self, record, datefmt=None):
        dt = datetime.datetime.utcfromtimestamp(record.created)
        if datefmt:
            return dt.strftime(datefmt)
        else:
            return dt.isoformat() + 'Z'


def getFileNameTimeString(timestamp=None):
    if timestamp is None:
        timestamp = datetime.datetime.now(pytz.utc)
    us = timestamp.microsecond
    seconds = timestamp.strftime('%Y-%m-%d-%H%M%S')
    return '%s-%06d-UTC' % (seconds, us)


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
    latestLink = _expandUniq(fnameTemplate, 'latest', env)

    # create service_previous.txt symlink
    if os.path.islink(latestLink):
        prevSymSrc = os.readlink(latestLink)
        previousLink = _expandUniq(fnameTemplate, 'previous', env)
        _forceSymLink(prevSymSrc, previousLink)

    _forceSymLink(symSrc, latestLink)
    return fname


def openLogFromTemplate(owner, fnameTemplate, env):
    fname = _findUniqueFileAndSetSymLink(fnameTemplate, env)
    return (fname, openLogFromPath(owner, fname))


class AutoFlushStreamHandler(logging.StreamHandler):
    def emit(self, rec):
        result = super(AutoFlushStreamHandler, self).emit(rec)
        self.flush()
        return result


class LineBuffer(logging.Handler):
    def __init__(self, maxSize=2048):
        super(LineBuffer, self).__init__()
        self._maxSize = maxSize
        self._lines = []
        self._lineCount = 0

    def emit(self, rec):
        DELETE_SIZE = self._maxSize // 2
        if len(self._lines) == self._maxSize - DELETE_SIZE:
            del self._lines[0:DELETE_SIZE]
        # rec.lineCount = self._lineCount
        self._lines.append(rec)
        self._lineCount += 1

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


def escapeEndOfLine(line):
    if line.endswith('\r\n'):
        return 'n ' + line[:-2]
    elif line.endswith('\n'):
        return 'n ' + line[:-1]
    elif line.endswith('\r'):
        return 'r ' + line[:-1]
    else:
        return 'c ' + line


def getStreamLogger(name, stream):
    result = logging.getLogger(name)
    result.setLevel(logging.DEBUG)
    sh = logging.StreamHandler(stream)
    sh.setLevel(logging.DEBUG)
    sh.setFormatter(UtcFormatter('%(asctime)s %(name)s %(message)s'))
    result.addHandler(sh)
    result.propagate = False
    return result


class TimestampingStream(LineParser):
    def __init__(self, name, stream, maxLineLength=160):
        super(TimestampingStream, self).__init__(self.handleLine, maxLineLength)
        self._stream = stream
        self._logger = getStreamLogger(name, stream)

    def handleLine(self, line):
        self._logger.info(escapeEndOfLine(line))

    def flush(self):
        super(TimestampingStream, self).flush()
        self._stream.flush()


class StreamLogger(object):
    def __init__(self, inFd, logger,
                 level=logging.DEBUG,
                 maxLineLength=160,
                 label=None):
        self._logger = logger
        self._logger.setLevel(level)
        self._q = queueFromFile(inFd, maxLineLength, label)
        self._job = gevent.spawn(self._handleQueue)

    def _handleQueue(self):
        for line in self._q:
            self._logger.info(escapeEndOfLine(line))

    def stop(self):
        self._job.kill()
        # could probably more thoroughly flush things


class PublishHandler(logging.Handler):
    def __init__(self, publisher):
        super(PublishHandler, self).__init__()
        self._p = publisher

    def emit(self, record):
        try:
            if not self._p.hasSubscribers():
                return
            text = self.format(record)
            _, topic, _ = text.split(' ', 2)
            self._p.publish(topic, text)
        except:  # pylint: disable=W0702
            logging.warning(traceback.format_exc())
            logging.warning('could not publish message, continuing')
