"""
Code dealing with product (i.e., fits file) delivery.
"""

# XXXX TODO: turn this into a core?

import cStringIO
import cgi
import os

from mx import DateTime

from nevow import inevow
from nevow import static

from zope.interface import implements

from gavo import config
from gavo import coords
from gavo import datadef
from gavo import fitstools
from gavo import resourcecache
from gavo.parsing import rowsetgrammar
from gavo.parsing import resource
from gavo.web.common import Error, UnknownURI
from gavo.web import common
from gavo.web import creds
from gavo.web import runner
from gavo.web import standardcores

class ItemNotFound(Error):
	pass


def isFree(item):
	return DateTime.now()>item["embargo"]


class Product(standardcores.DbBasedCore):
	"""is a core delivering single products.

	This core stands in as a complete nevow resource -- I can't see why one
	would want to reference it from resource descriptors, and thus it's not in
	the cores registry.
	"""
# XXX TODO factor core and renderer here and make this a service based on
# the product table
	implements(inevow.IResource)

	name = "getproduct"

	def __init__(self, ctx, segments):
		super(Product, self).__init__(
			resourcecache.getRd("__system__/products/products"), 
				{"table": "products"})
		origDD = self.rd.getDataById("data")
		inputDef = resource.RecordDef()
		inputDef.updateFrom(origDD.getPrimaryRecordDef())
		inputDef.set_items([datadef.makeCopyingField(f) 
			for f in inputDef.get_items()])
		self.dataDef = datadef.DataTransformer(self.rd, initvals={
			"Grammar": rowsetgrammar.RowsetGrammar(initvals={
				"dbFields": origDD.getPrimaryRecordDef().get_items()}),
			"Semantics": resource.Semantics(initvals={
				"recordDefs": [inputDef]}),
			"id": "<generated>",
		})
		self.queryMeta = common.QueryMeta(ctx)
		self.queryMeta["format"] = "internal"
		
	def locateChild(self, ctx, segments):
		return self, ()

	def _parseOutput(self, res, ctx, sqlPars, queryMeta):
		result = super(Product, self)._parseOutput(
			res, self.dataDef, sqlPars, queryMeta).getPrimaryTable()
		if len(result)==0:
			raise common.UnknownURI()
		if len(result)!=1:
			raise Error("More than one item matched the key.  Honestly, this"
				" can't happen.")
		item = result[0]
		if not isFree(item):
			return creds.runAuthenticated(ctx, item["owner"], 
				lambda: self._deliverFile(sqlPars, ctx, item, queryMeta))
		else:
			return self._deliverFile(sqlPars, ctx, item, queryMeta)
	
	def _deliverFile(self, sqlPars, ctx, item, queryMeta):
		if "sra" in sqlPars:
			if queryMeta.ctxArgs.has_key("preview"):
				raise gavo.Error("No previews on cutout images yet, sorry")
			return self._deliverCutout(sqlPars, ctx, item)
		else:
			return self._deliverImageFile(ctx, item, 
				queryMeta.ctxArgs.has_key("preview"))

	def _makeFitsRequest(self, ctx, fName, fSize):
		request = inevow.IRequest(ctx)
		request.setHeader("content-type", "image/fits")
		request.setHeader('content-disposition', 'attachment; filename="%s"'%fName)
		if fSize:
			request.setHeader('content-length', fSize)
		return request

	def _computeGetfitsArgs(self, sqlPars, targetPath):
		"""returns a list of command line arguments for getfits to cut out
		the field specified in sqlPars from the image specified in item.
		"""
		f = open(targetPath)
		header = fitstools.readPrimaryHeaderQuick(f)
		ra, dec = float(sqlPars["ra"]), float(sqlPars["dec"]),
		sra, sdec = float(sqlPars["sra"]), float(sqlPars["sdec"]),
		getPixCoo = coords.getInvWCSTrafo(header)
		x, y = getPixCoo(ra, dec)
		w = abs(getPixCoo(ra+sra/2, dec)[0]-getPixCoo(ra-sra/2, dec)[0])
		h = abs(getPixCoo(ra, dec+sdec/2,)[1]-getPixCoo(ra, dec-sdec/2,)[1])
		return ["-s", targetPath, str(x), str(y), str(w), str(h)]

	def _deliverCutout(self, sqlPars, ctx, item):
		"""transfers a cutout image defined by ctx["key"] and the ra, dec, sra, 
		and sdec parameters in sqlPars.
		"""
# XXX todo: this should be based on the cutout resource descriptor.
		targetPath = str(os.path.join(config.get("inputsDir"), item["accessPath"]))
		args = self._computeGetfitsArgs(sqlPars, targetPath)
		request = self._makeFitsRequest(ctx, "cutout-"+os.path.basename(
			targetPath), None)
		if request.method == 'HEAD':
			return ''
		prog = runner.getBinaryName(os.path.join(config.get("inputsDir"),
			"__system__", "cutout", "bin", "getfits"))
		runner.StreamingRunner(prog, args, request)
		return request.deferred

	def _deliverImageFile(self, ctx, item, preview):
		if preview:
			return self._deliverPreview(ctx, item)
		else:
			return self._deliverFileAsIs(ctx, item)

	def _deliverPreview(self, ctx, item):
		targetPath = str(os.path.join(config.get("inputsDir"), item["accessPath"]))
		previewName = os.path.join(config.get("inputsDir"), "__system__",
			"products", "bin", "fitspreview")
		runner.runWithData(previewName, [targetPath]
			).addCallback(self._deliverJpeg, ctx
			).addErrback(self._previewFailed, ctx)
	
	def _deliverJpeg(self, jpegString, ctx):
		request = inevow.IRequest(ctx)
		request.setHeader("content-type", "image/jpeg")
		static.FileTransfer(cStringIO.StringIO(jpegString), len(jpegString), 
			request)
		return request.deferred

	def _deliverFileAsIs(self, ctx, item):
		targetPath = str(os.path.join(config.get("inputsDir"), item["accessPath"]))
		request = self._makeFitsRequest(ctx, os.path.basename(targetPath),
			os.path.getsize(targetPath))
		if request.method == 'HEAD':
			return ''
		static.FileTransfer(open(targetPath, "r"), os.path.getsize(targetPath), 
			request)
		return request.deferred
	
	def run(self, ctx, queryMeta):
		# Note that ctx.arg only returns the first arg of a name, but that's what
		# we want here
		sqlPars = dict([(k, v[0]) 
			for k, v in cgi.parse_qs("key="+ctx.arg("key")).items()])
		return self.runDbQuery("key=%(key)s", sqlPars, 
				self.dataDef.getPrimaryRecordDef(), queryMeta).addCallback(
			self._parseOutput, ctx, sqlPars, queryMeta).addErrback(
			lambda f: f)

	def renderHTTP(self, ctx):
		queryMeta = common.QueryMeta(ctx)
		return self.run(ctx, queryMeta)
