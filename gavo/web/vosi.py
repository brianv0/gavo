"""
VOSI renderers.

These are really three different renderers for each service.  IVOA wants
it this way (in effect, since they are supposed to be three different
capabilities).
"""

import traceback

from nevow import inevow
from twisted.internet import defer

from gavo import registry
from gavo import svcs
from gavo import utils
from gavo.base import meta
from gavo.registry import capabilities
from gavo.registry import model
from gavo.utils import ElementTree
from gavo.utils.stanxml import Element, registerPrefix, schemaURL, xsiPrefix
from gavo.web import grend


registerPrefix("avl", "http://www.ivoa.net/xml/VOSIAvailability/v1.0",
	schemaURL("VOSIAvailability-v1.0.xsd"))
registerPrefix("cap", "http://www.ivoa.net/xml/VOSICapabilities/v1.0",
	schemaURL("VOSICapabilities-v1.0.xsd"))


class VOSIRenderer(grend.ServiceBasedPage):
	"""An abstract base for renderers handling VOSI requests.

	All of these return some sort of XML and are legal on all services.

	The actual documents returned are defined in _getTree(request)->deferred
	firing stanxml.
	"""
	checkedRenderer = False

	def renderHTTP(self, ctx):
		request = inevow.IRequest(ctx)
		request.setHeader("content-type", "text/xml")
		return defer.maybeDeferred(self._getTree(request)
			).addCallback(self._shipout, ctx
			).addErrback(self._sendError, request)
	
	def _shipout(self, response, ctx):
		return utils.xmlrender(response,
			"<?xml-stylesheet href='/static/xsl/vosi.xsl' type='text/xsl'?>")

	def _sendError(self, failure, request):
		request.setResponseCode(500)
		request.setHeader("content-type", "text/plain")
		request.write("Sorry -- we're experiencing severe problems.\n")
		request.write("If you are reading this, you can help us by\n")
		request.write("reporting the following to gavo@ari.uni-heidelberg.de:\n")
		failure.printException(file=request)
		return ""

	def _getTree(self, request):
		raise ValueError("_getTree has not been overridden.")


############ The availability data model (no better place for it yet)


class AVL(object):
	"""The container for elements from the VOSI availability schema.
	"""
	class AVLElement(Element):
		_prefix = "avl"
	
	class availability(AVLElement):
		_additionalPrefixes = xsiPrefix
	class available(AVLElement): pass
	class upSince(AVLElement): pass
	class downAt(AVLElement): pass
	class backAt(AVLElement): pass
	class note(AVLElement): pass


class CAP(object):
	"""The container for element from the VOSI capabilities schema.
	"""
	class CAPElement(Element):
		_prefix = "cap"
	
	class capabilities(CAPElement): pass


SF = meta.stanFactory

_availabilityBuilder = meta.ModelBasedBuilder([
	('available', SF(AVL.available)),
	('upSince', SF(AVL.upSince)),
	('_scheduledDowntime', SF(AVL.downAt)),
	('backAt', SF(AVL.backAt)),
	('availability_note', SF(AVL.note)),
	])


class VOSIAvailabilityRenderer(VOSIRenderer):
	"""A renderer for a VOSI availability endpoint.
	"""
	name = "availability"

	def _getTree(self, request):
		root = AVL.availability[
			_availabilityBuilder.build(self.service)]
		return root


class VOSICapabilityRenderer(VOSIRenderer):
	"""A renderer for a VOSI capability endpoint.
	"""
	name = "capabilities"

	vosiSet = set(['ivo_managed'])

	def _getTree(self, request):
		root = CAP.capabilities[[
			capabilities.getCapabilityElement(pub)
				for pub in self.service.getPublicationsForSet(self.vosiSet)]]
		return root


class VOSITablesetRenderer(VOSIRenderer):
	"""A renderer for a VOSI table metadata endpoint.
	"""
	name = "tableMetadata"

	def _getTree(self, request):
		root = registry.getTablesetForService(self.service)
		root.addAttribute("xsi:type", "vs1:TableSet")
		return root
