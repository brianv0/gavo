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

# XXX use port attribute when we can rely on having python 2.5
_serverName = urlparse.urlparse(base.getConfig("web", "serverURL"))[1]
if ":" in _serverName:
	_serverName, _targetPort = _serverName.split(":")
else:
	_serverName, _targetPort = _serverName, 80
_targetPort = int(_targetPort)
if base.getConfig("web", "serverPort") is not None:
	_targetPort = base.getConfig("web", "serverPort")

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

internet.TCPServer(_targetPort, appserver.NevowSite(
	mainPage), interface=_serverName).setServiceParent(application)
	
