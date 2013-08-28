
Pycroraptor2 is a process manager, essentially intended to be a Python
replacement for the `Microraptor Process Manager
<http://www.microraptor.org/>`_. Pycroraptor2 is in a working state but
is not yet a feature-complete replacement for Microraptor.

The Pycroraptor2 system includes several components:

 * The ``pyraptord`` process management daemon. Typically, an
   instance of ``pyraptord`` is the parent process for all managed
   processes running on a particular host.

 * The ``pyrterm`` client shell that provides a tty user interface
   for controlling processes managed by ``pyraptord``.

 * A web interface for controlling processes managed by ``pyraptord``.
   This component has not been implemented yet.

Pycroraptor2 also offers a `ZeroRPC <http://zerorpc.dotcloud.com/>`_
API.  To quickly get started using this API, you can use the ``zerorpc``
command-line tool included in the `ZeroRPC Python repo
<https://github.com/dotcloud/zerorpc-python>`_ or use the ``zclient``
Python shell included in the `geocamUtil repo
<https://github.com/geocam/geocamUtilWeb>`_.

Features
~~~~~~~~

(Fill this in)

Requirements
~~~~~~~~~~~~

``pyraptord`` is currently known to work in Linux (tested on RedHat
Enterprise Linux 6 and Ubuntu 12.04) and Mac OS X (tested on Snow
Leopard 10.6.8).

It probably will not work in any version of Windows without extensive
modifications.

Installation
~~~~~~~~~~~~

Pycroraptor2 depends on geocamUtil::

  git clone git@github.com:geocam/geocamUtil.git
  cd geocamUtil
  python setup.py install

Download or clone from the `geocamPycroraptor2 repository on GitHub
<https://github.com/geocam/geocamPycroraptor2>`_::

  git clone git@github.com:geocam/geocamPycroraptor2.git

Configuration
~~~~~~~~~~~~~

In order to run, Pycroraptor2 requires two configuration files:

 * The ``ports.json`` file specifies network endpoints for named
   services that are available through the `0MQ socket library
   <http://zeromq.org>`_.  This file specifies the endpoint where
   ``pyraptord`` should listen for commands and tells ``pyrterm`` or
   ``zclient`` where to find ``pyraptord``.

 * The ``pycroraptor.json`` file specifies the rest of the Pycroraptor2
   configuration, including how to run processes and where to put log
   files.

Examples for these files can be found in the ``tests`` subdirectory of
the Pycroraptor2 repo.

Pycroraptor2 is often used to manage persistent processes that are
started on boot. To make that happen::

 * You need to install a boot script for Pycroraptor2 that brings up the
   ``pyraptord`` instance for that host. See the `Boot Script`_ section
   below.

 * In order to start processes at ``pyraptord`` start time, they should
   be placed in the ``startup`` group in ``pycroraptor.json``.

Boot Script
~~~~~~~~~~~

Example boot scripts for ``pyraptord`` are available in the ``bin``
subdirectory of the Pycroraptor2 repo, for the following platforms:

 * RedHat Enterprise Linux 6 (``pyraptord_boot_script_rhel``)

Each boot script contains its own platform-specific install instructions.

Operation
~~~~~~~~~

.. o __BEGIN_LICENSE__
.. o Copyright (C) 2008-2010 United States Government as represented by
.. o the Administrator of the National Aeronautics and Space Administration.
.. o All Rights Reserved.
.. o __END_LICENSE__
