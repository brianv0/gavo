"""
Code to deal with "static" resources. 

Static resources are defined by hand somewhere below
inputs/__system__/services/*.rr as sets of key-value pairs.  These are
parsed here into StaticResource instances.  They only contain meta data.
"""

import os

from gavo import base
from gavo import svcs


# The path to the resource descriptor for the servicelist & c
rdId = "__system__/services"


class StaticResource(base.MetaMixin):
	"""is a resource defined through a key value-based text file in
	the __system directory.

	These may stand in as a very rudimentary service if hard pressed
	to allow off-site WebBrowser services to be registred.
	"""
	def __init__(self, srcId):
		self.publications = [base.makeStruct(svcs.Publication,
			render="static", sets=["ivo_managed"])]
		self.limitTo = None
		self.id = srcId
		self.srcName = srcId
		self.rd = base.caches.getRD(rdId)
		base.MetaMixin.__init__(self)  # We're not a Structure, so we need
		                               # to do this manually

	def getIDKey(self):
		return "static/"+self.id

	def getURL(self, renderer, qtype="POST", includeServerURL=True):
		return self.getMeta("accessURL", default=None)

	def getDescriptor(self):
		return _descriptor


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
	rd = base.caches.getRD(rdId)
	srcName = os.path.join(rd.resdir, srcId)
	grammar = rd.getById("fixedrecords").grammar
	return makeStaticResource(srcId, [(v["key"], v["value"]) 
		for v in grammar.parse(srcName)])


def iterStaticResources():
	rd = base.caches.getRD(rdId)
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
