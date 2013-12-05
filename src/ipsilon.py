#!/usr/bin/python
#
# Copyright (C) 2013  Simo Sorce <simo@redhat.com>
#
# see file 'COPYING' for use and warranty information
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

import sys
sys.stdout = sys.stderr

import os
import atexit
import threading
import cherrypy
from util import plugin
from util import data
from jinja2 import Environment, FileSystemLoader
import root


cherrypy.config.update('ipsilon.conf')

plugins = plugin.Plugins()
idp_providers = plugins.get_providers()
cherrypy.config.update({'idp_providers': idp_providers})

datastore = data.Store()
admin_config = datastore.get_admin_config()
cherrypy.config.update(admin_config)

templates = os.path.join(cherrypy.config['base.dir'], 'templates')
env = Environment(loader=FileSystemLoader(templates))

if __name__ == "__main__":
    cherrypy.quickstart(root.Root(env))

else:
    cherrypy.config.update({'environment': 'embedded'})

    if cherrypy.__version__.startswith('3.0') and cherrypy.engine.state == 0:
        cherrypy.engine.start(blocking=False)
        atexit.register(cherrypy.engine.stop)

    application = cherrypy.Application(root.Root(env),
                                       script_name=None, config=None)
