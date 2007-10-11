from twisted.application import service, internet
from nevow import rend, loaders, appserver

import dispatcher
import standardcores
from gavo import parsing
from gavo import resourcecache
from gavo import votable
from gavo.parsing import resource
from gavo.parsing import tablegrammar

parsing.verbose = True

class Reloader(rend.Page):
	def locateChild(self, ctx, segments):
		resourcecache.clearCaches()
		reload(standardcores)
		reload(dispatcher)
		reload(resource)
		page = dispatcher.ArchiveService()
		return page.locateChild(ctx, segments)

application = service.Application("archive")
internet.TCPServer(8080, appserver.NevowSite(
	Reloader())).setServiceParent(application)
	
