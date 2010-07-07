"""
Rough hack towards a twisted application running the data center server.
"""


import datetime
import pwd
import sys
import urlparse

from twisted.application import service, internet
from twisted.internet import reactor
from nevow import rend, loaders, appserver

from gavo import base
from gavo import rscdesc         # for getRD in base.caches
from gavo import utils
from gavo.protocols import basic # for registration
from gavo.base import cron
from gavo.base import config
from gavo.user import serve
from gavo.web import root

debug = False

class Reloader(rend.Page):
	def locateChild(self, ctx, segments):
		page = root.ArchiveService()
		return page.locateChild(ctx, segments)


base.setDBProfile("trustedquery")

interface = base.getConfig("web", "bindAddress")

# Figure out whether to drop privileges
uid = None
user = base.getConfig("web", "user")
if user:
	try:
		uid = pwd.getpwnam(user)[2]
	except KeyError:
		sys.stderr.write("Cannot change to user %s (not found)\n"%user)
		sys.exit(1)

application = service.Application("archive", uid=uid)

serve.setupServer(application)
internet.TCPServer(base.getConfig("web", "serverPort"), 
	root.site, interface=interface).setServiceParent(application)
