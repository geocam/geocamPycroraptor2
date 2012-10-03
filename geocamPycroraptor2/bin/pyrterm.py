#!/usr/bin/env python
# __BEGIN_LICENSE__
# Copyright (C) 2008-2010 United States Government as represented by
# the Administrator of the National Aeronautics and Space Administration.
# All Rights Reserved.
# __END_LICENSE__

import logging

from geocamPycroraptor2.shell import Shell


def pyrterm(opts):
    logging.basicConfig(level=logging.DEBUG)
    s = Shell(opts.config)
    s.run()


def main():
    import optparse
    parser = optparse.OptionParser('usage: %prog')
    parser.add_option('-c', '--config',
                      help='Pycroraptor config file to use [%default]',
                      default='pycroraptor.json')
    opts, args = parser.parse_args()
    if args:
        parser.error('expected no args')
    if not opts.config:
        parser.error('--config option is required')
    pyrterm(opts)


if __name__ == '__main__':
    main()
