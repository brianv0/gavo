"""
Code dealing with product (i.e., fits file) delivery.
"""

import os

from nevow import inevow
from nevow import static

from zope.interface import implements

from gavo import config
from gavo import resourcecache
from gavo.web import standardcores
from gavo.web import common
from gavo.web.common import Error, UnknownURI

class ItemNotFound(Error):
	pass


class Product(standardcores.DbBasedCore):

	implements(inevow.IResource)

	tableName = "products"

	def __init__(self, segments):
		self.rd = resourcecache.getRd("products/products")
		self.queryMeta = common.QueryMeta({})
		self.queryMeta["format"] = "internal"
		
	def locateChild(self, ctx, segments):
		return self, ()

	def _locateData(self, key):
		return self.run("key=%(key)s", {"key": key}, self.queryMeta)

	def raiseError(self, failure):
		print ">>>>>>>>>>>>>>> Error", failure
		raise Error(failure)

	def renderHTTP(self, ctx):
		# Note that ctx.arg only returns the first instance, but that's what
		# we want here
		d = self._locateData(ctx.arg("key"))
		d.addCallback(lambda res: self.parseOutput(ctx, res)
			).addErrback(self.raiseError)
		return d
	
	def parseOutput(self, ctx, res):
# XXX: self.__class__ -> Product when done debugging
		result = super(self.__class__, self).parseOutput(res,
			self.rd.getTableDefByName(self.tableName), self.queryMeta).getTables()[0]
		if len(result)!=1:
			raise Error("More than one item matched the key.  Honestly, this"
				" can't happen.")
		item = result[0]
		targetPath = os.path.join(config.get("inputsDir"), item["accessPath"])
		request = inevow.IRequest(ctx)
		request.setHeader("content-type", "application/octet-stream")
		request.setHeader('content-disposition', 
			'attachment; filename="%s"'%str(os.path.basename(targetPath)))
		fsize = os.path.getsize(targetPath)
		request.setHeader('content-length', fsize)
		if request.method == 'HEAD':
			return ''
		static.FileTransfer(open(targetPath, "r"), fsize, request)
		return request.deferred
