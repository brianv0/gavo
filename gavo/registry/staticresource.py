"""
Resources defined through simple key-value files.

Static resources are defined by hand somewhere below
inputs/__system__/services/*.rr as sets of key-value pairs.  These are
parsed here into StaticResource instances.  They only contain meta data.

This is probably a dead end.  I guess there should be an RD defining these.
"""

import datetime
import os
import urlparse

from gavo import base
from gavo import svcs
from gavo import utils
from gavo.base import meta
from gavo.svcs import service
from gavo.registry.common import *


class NonServiceResource(base.ComputedMetaMixin, DateUpdatedMixin,
		svcs.RegistryMetaMixin):
	def __init__(self, datetimeUpdated):
		# We're not a Structure, so we need to do this manually
		base.ComputedMetaMixin.__init__(self)  
		self.dateUpdated = datetimeUpdated

		# we need a renderer to get into the service list.  This renderer
		# should never kick in, though, since our types should not cause
		# builders to use the automatic capability generation.
		self.publications = [base.makeStruct(svcs.Publication,
			render="static", sets=["ivo_managed"])]


	def iterChildren(self):
		# structure emulation to let meta validation work here
		if False: yield
		

class StaticResource(NonServiceResource):
	"""is a resource defined through a key value-based text file in
	the __system directory.

	These may stand in as a very rudimentary service if hard pressed
	to allow off-site WebBrowser services to be registred.
	"""
	def __init__(self, srcId):
		self.rd = base.caches.getRD(STATICRSC_ID)
		self.id = srcId
		self.limitTo = None
		self.srcName = srcId
		NonServiceResource.__init__(self, self._getDateUpdated())

	def _getDateUpdated(self):
		srcName = os.path.join(self.rd.resdir, self.id)
		return datetime.datetime.utcfromtimestamp(
			os.path.getmtime(srcName))

	def getURL(self, renderer, absolute=True):
		url = self.getMeta("accessURL")
		if url is None:
			return None
		if not absolute:
			url = urlparse.urlunparse((None, None)+urlparse.urlparse(url)[2:])
		return url

	def getDescriptor(self):
		return _descriptor

	def _meta_identifier(self):
		return "ivo://%s/static/%s"%(
			base.getConfig("ivoa", "authority"), 
			self.id)

	def _meta_recTimestamp(self):
		return self.getMeta("datetimeUpdated")

	def _meta_status(self):
		return "active"


class _FakeRD(object):
	def __init__(self, id):
		self.sourceId = id


class DeletedResource(NonServiceResource):
	"""a remainder of a deleted resource.  These are always built from information
	in the database, since that is the only place they are remembered.
	"""
	resType = "deleted"

	def __init__(self, ivoId, resTuple):
		self.resTuple = resTuple
		self.rd = _FakeRD(resTuple["sourceRd"])
		self.id = resTuple["internalId"]
		NonServiceResource.__init__(self, self.resTuple["dateUpdated"])
		self.setMeta("identifier", ivoId)
		self.setMeta("status", "deleted")
		self.setMeta("recTimestamp", resTuple["recTimestamp"])
		self.dateUpdated = resTuple["recTimestamp"]


def makeStaticResource(srcId, srcPairs):
	"""returns a StaticResource instance for the sequence of (metaKey,
	metaValue) pairs srcPairs.

	srcPairs typically come from the grammar defined in services.rd#fixedrecords.
	"""
	res = StaticResource(srcId)
	for k, v in srcPairs:
		res.addMeta(k, v)
	return res


def loadStaticResource(srcId):
	rd = base.caches.getRD(STATICRSC_ID)
	srcName = os.path.join(rd.resdir, srcId)
	grammar = rd.getById("fixedrecords").grammar
	return makeStaticResource(srcId, [(v["key"], v["value"]) 
		for v in grammar.parse(srcName)])


def iterStaticResources():
	rd = base.caches.getRD(STATICRSC_ID)
	for src in rd.getById("fixedrecords").iterSources():
		id = src[len(rd.resdir):]
		if id.startswith("/"):
			id = id[1:]
		yield loadStaticResource(id)


if __name__=="__main__":
	from gavo import rscdesc
	from gavo.protocols import basic
	from gavo import web
	m = loadStaticResource("registryrecs/ari.rr")
	print unicode(m.getMeta("title", raiseOnFail=True)).encode("iso-8859-1")
