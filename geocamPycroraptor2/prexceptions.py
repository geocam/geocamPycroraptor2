# __BEGIN_LICENSE__
# Copyright (C) 2008-2010 United States Government as represented by
# the Administrator of the National Aeronautics and Space Administration.
# All Rights Reserved.
# __END_LICENSE__


class ServiceAlreadyActive(Exception):
    pass


class ServiceNotActive(Exception):
    pass


class UnknownService(Exception):
    pass
