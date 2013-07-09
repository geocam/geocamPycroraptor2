#!/usr/bin/env python

import sys
import time

i = 0
while 1:
    print i
    sys.stdout.flush()
    i += 1
    time.sleep(1)
