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
from gavo.registry import builders
from gavo.utils import ElementTree
from gavo.utils.stanxml import Element, XSINamespace, schemaURL
from gavo.web import grend


class VOSIRenderer(grend.ServiceBasedRenderer):
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

AVLNamespace = "http://www.ivoa.net/xml/Availability/v0.4"
ElementTree._namespace_map[AVLNamespace] = "avl"

class AVL(object):
	"""The container for elements from this IVOA availability schema.
	"""
	class AVLElement(Element):
		namespace = AVLNamespace
	
	class availability(AVLElement):
		a_xsi_schemaLocation = "%s %s"%(AVLNamespace, 
			schemaURL("availability-0.4.xsd"))
		xsi_schemaLocation_name = "xsi:schemaLocation"
		a_xmlns_xsi = XSINamespace
		xmlns_xsi_name = "xmlns:xsi"
	
	class available(AVLElement): pass
	class upSince(AVLElement): pass
	class downAt(AVLElement): pass
	class backAt(AVLElement): pass
	class note(AVLElement): pass


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
		return AVL.availability[
			_availabilityBuilder.build(self.service)]

svcs.registerRenderer(VOSIAvailabilityRenderer)


class VOSICapabilityRenderer(VOSIRenderer):
	"""A renderer for a VOSI capability endpoint.

	We just return the complete service record since inventing some
	container element doesn't really cut it here.
	"""
	name = "capabilities"

	def _getTree(self, request):
		request.setHeader("Last-Modified", 
			utils.datetimeToRFC2616(self.service.rd.dateUpdated))
		root = registry.getVORMetadataElement(self.service)
		registry.addSchemaLocations(root)
		return root

svcs.registerRenderer(VOSICapabilityRenderer)


class VOSITablesetRenderer(VOSIRenderer):
	"""A renderer for a VOSI table metadata endpoint.
	"""
	name = "tableMetadata"

	def _getTree(self, request):
		request.setHeader("Last-Modified", 
			utils.datetimeToRFC2616(self.service.rd.dateUpdated))
		root = registry.getTablesetForService(self.service)
		root.a_xmlns_vs1 = root.namespace
		root.xmlns_vs1_name = "xmlns:vs1"
		root.a_xsi_type = "vs1:TableSet"
		root.xsi_type_name = "xsi:type"
		registry.addSchemaLocations(root)
		return root

svcs.registerRenderer(VOSITablesetRenderer)
