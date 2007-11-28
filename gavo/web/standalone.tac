from twisted.application import service, internet
from nevow import rend, loaders, appserver

from gavo import parsing
from gavo import resourcecache
from gavo.web import dispatcher
from gavo.web import htmltable
from gavo.web import product
from gavo.web import resourcebased

parsing.verbose = True

class Reloader(rend.Page):
	def locateChild(self, ctx, segments):
		page = dispatcher.ArchiveService()
		return page.locateChild(ctx, segments)

application = service.Application("archive")
internet.TCPServer(8080, appserver.NevowSite(
	Reloader())).setServiceParent(application)
	
