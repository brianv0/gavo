"""
This is a twisted tac application definition for running the data center
software behind an apache proxy.  It uses the web.nevowRoot resource
to figure out the prefix.  This prefix has to be reflected in the apache
setup.
"""

from twisted.application import service, strports
from nevow import appserver, inevow, rend, loaders, vhost
from zope.interface import implements

from gavo import config
from gavo.web import dispatcher


class VhostFakeRoot(object):
	"""is a wrapper for a resource to work at a non-root location behind
	an apache proxy.
	"""
	implements(inevow.IResource)
	def __init__(self, wrapped):
		self.wrapped = wrapped
	
	def renderHTTP(self, ctx):
		return self.wrapped.renderHTTP(ctx)
		
	def locateChild(self, ctx, segments):
		"""Returns a VHostMonster if the first segment is "vhost". Otherwise
		delegates to the wrapped resource."""
		if segments[0] == "vhost":
			return vhost.VHostMonsterResource(), segments[1:]
		else:
			return self.wrapped.locateChild(ctx, segments)


site = appserver.NevowSite(VhostFakeRoot(dispatcher.ArchiveService()))
application = service.Application("archive")
strports.service("tcp:8080:interface=127.0.0.1", site).setServiceParent(
	application)
