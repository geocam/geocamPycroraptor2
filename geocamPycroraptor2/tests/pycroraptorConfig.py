#!/usr/bin/env python

"""
This config file has the same content as pycroraptor.json, but in the
form of an executable Python script.  That capability could allow you,
for example, to use environment variables to change the configuration or
to generate multiple config entries from a template.
"""

import json

CONFIG = {
    "PORTS": "ports.json",
    "LOG_DIR": "/tmp/pyraptord/logs",

    "SERVICES": {
        "bc": {
            "command": "bc -i"
        },
        "nohup": {
            "command": "nohup cat"
        },
        "source": {
            "command": "./numberSource.py",
            "stdout": "/tmp/myfifo"
        },
        "sink": {
            "command": "./numberSink.py",
            "stdin": "/tmp/myfifo"
        },
        "sleep": {
            "command": "/bin/sleep 10000"
        }
    },
    "GROUPS": {
        "startup": ["bc", "nohup"]
    }
}

print json.dumps(CONFIG, indent=4, sort_keys=True)
