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

import gavo
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


errorPng = ('iVBORw0KGgoAAAANSUhEUgAAAQAAAAAUAgMAAAAfLAvMAAAADFBM'
'VEUkJCRfX1+ampr+/v4wizjb\nAAAA40lEQVQ4y+WTwQoBURiFPYaiPAGPwHvYyJqaJUoz'
'D+ANqJmNiM3slJL7AIqdjTJpcJOFom7u\nHd3jzlhY/ykL/s05Z/N1/r97U/hwUj8KOI0T'
'iV5piOgIaIcAeMxLsVyToBu4KqMWBYDcO2gGSCLg\nbgA6NiwBXKCMIzVghfSm2a6KbbbJ'
'ZP62kyLokgBjeJ5rK87dIvRsohQPS7QGsMpeUa6HS9ucfyDF\neuTQjgirgpriWPZMA6kE'
'1w6xgb+6dCSPwgV0S0yMI62w93XmyFZ76d8C3Ouj/mF6dnOfPWX2b7/x\nq4AnJhXSaagw'
'wtEAAAAASUVORK5CYII=\n').decode("base64")


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
		
	def _parseOutput(self, res, ctx, sqlPars, queryMeta):
		result = super(Product, self)._parseOutput(
			res, self.dataDef, sqlPars, queryMeta).getPrimaryTable()
		if len(result)==0:
			raise common.UnknownURI()
		if len(result)!=1:
			raise Error("More than one item matched the key.  Honestly, this"
				" can't happen.")
		item = result[0]
# XXX TODO: It's bad if the previews require a password, but this is nasty
# as well.  Think of sth better.
		if not ctx.arg("preview") and not isFree(item):
			return creds.runAuthenticated(ctx, item["owner"], 
				lambda: self._deliverFile(sqlPars, ctx, item, queryMeta))
		else:
			return self._deliverFile(sqlPars, ctx, item, queryMeta)
	
	def _deliverFile(self, sqlPars, ctx, item, queryMeta):
		if "sra" in sqlPars:
			if queryMeta.ctxArgs.has_key("preview"):
				self._sendErrorPreview(ctx)
			return self._deliverCutout(sqlPars, ctx, item)
		else:
			return self._deliverImageFile(ctx, item, 
				ctx.arg("preview"))

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
		x, y = map(int, getPixCoo(ra, dec))
		w = min(header["NAXIS1"],
			int(abs(getPixCoo(ra+sra/2, dec)[0]-getPixCoo(ra-sra/2, dec)[0])))
		h = min(header["NAXIS2"], 
			int(abs(getPixCoo(ra, dec+sdec/2,)[1]-getPixCoo(ra, dec-sdec/2,)[1])))
		x = max(0, min(header["NAXIS1"]-w, x-w/2))
		y = max(0, min(header["NAXIS2"]-h, y-h/2))
		return ["-s", targetPath, "%d-%d"%(x, x+w), "%d-%d"%(y, y+h)]

	def _deliverCutout(self, sqlPars, ctx, item):
		"""transfers a cutout image defined by ctx["key"] and the ra, dec, sra, 
		and sdec parameters in sqlPars.
		"""
# XXX TODO: this should be based on the cutout resource descriptor.
		targetPath = str(os.path.join(config.get("inputsDir"), item["accessPath"]))
		args = self._computeGetfitsArgs(sqlPars, targetPath)
		request = self._makeFitsRequest(ctx, "cutout-"+os.path.basename(
			targetPath), None)
		if request.method == 'HEAD':
			return ''
		prog = runner.getBinaryName(os.path.join(config.get("inputsDir"),
			"__system", "bin", "getfits"))
		runner.StreamingRunner(prog, args, request)
		return request.deferred

	def _deliverImageFile(self, ctx, item, preview):
		if preview:
			return self._deliverPreview(ctx, item)
		else:
			return self._deliverFileAsIs(ctx, item)

	def _deliverPreview(self, ctx, item):
		targetPath = str(os.path.join(config.get("inputsDir"), item["accessPath"]))
		previewName = os.path.join(config.get("inputsDir"), "__system",
			"bin", "fitspreview")
		args = [targetPath]
		try:
			args.append(str(int(ctx.arg("width", 200))))
		except (KeyError, ValueError, IndexError):
			pass
		return runner.runWithData(previewName, "", args
			).addCallback(self._deliverJpeg, ctx
			).addErrback(self._previewFailed, ctx)
	
	def _deliverJpeg(self, jpegString, ctx):
		request = inevow.IRequest(ctx)
		request.setHeader("content-type", "image/jpeg")
		static.FileTransfer(cStringIO.StringIO(jpegString), len(jpegString), 
			request)
		return request.deferred
	
	def _previewFailed(self, failure, ctx):
		failure.printTraceback()
		return self._sendErrorPreview(ctx)
	
	def _sendErrorPreview(self, ctx):
		request = inevow.IRequest(ctx)
		request.setHeader("content-type", "image/png")
		static.FileTransfer(cStringIO.StringIO(errorPng), len(errorPng), 
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

	def locateChild(self, ctx, segments):
		return self, ()
