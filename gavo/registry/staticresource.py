"""
Code to deal with "static" resources. 

Static resources are defined by hand somewhere below
inputs/__system__/services/*.rr as sets of key-value pairs.  These are
parsed here into StaticResource instances.  They only contain meta data.
"""

import datetime
import os
import urlparse

from gavo import base
from gavo import svcs
from gavo import utils
from gavo.base import meta
from gavo.svcs import service
from gavo.registry import common
from gavo.registry.common import *

class StaticResource(base.ComputedMetaMixin, common.DateUpdatedMixin):
	"""is a resource defined through a key value-based text file in
	the __system directory.

	These may stand in as a very rudimentary service if hard pressed
	to allow off-site WebBrowser services to be registred.
	"""
	def __init__(self, srcId):
		self.publications = [base.makeStruct(svcs.Publication,
			render="static", sets=["ivo_managed"])]
		# we need a renderer to get into the service list.  This renderer
		# should never kick in, though, since our types should not cause
		# builders to use the automatic capability generation.
		self.limitTo = None
		self.id = srcId
		self.srcName = srcId
		self.rd = base.caches.getRD(STATICRSC_ID)
		# We're not a Structure, so we need to do this manually
		base.ComputedMetaMixin.__init__(self)  
		self._updateDateUpdated()

	def _updateDateUpdated(self):
		srcName = os.path.join(self.rd.resdir, self.id)
		self.dateUpdated = datetime.datetime.utcfromtimestamp(
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

	def _meta_status(self):
		return "active"

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
