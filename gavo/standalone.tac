import pwd
import sys
import urlparse

from twisted.application import service, internet
from nevow import rend, loaders, appserver

from gavo import base
from gavo import rscdesc         # for getRD in base.caches
from gavo.protocols import basic # for registration
from gavo.web import dispatcher

debug = False

class Reloader(rend.Page):
	def locateChild(self, ctx, segments):
		page = dispatcher.ArchiveService()
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
if debug:
	mainPage = Reloader()
else:
	mainPage = dispatcher.ArchiveService()

internet.TCPServer(base.getConfig("web", "serverPort"), appserver.NevowSite(
	mainPage), interface=interface).setServiceParent(application)
	
