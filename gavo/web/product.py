"""
Code dealing with product (i.e., fits file) delivery.
"""

# XXXX TODO: turn this into a core?

import cStringIO
import cgi
import md5
import os

from mx import DateTime

from twisted.internet import defer

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


class PreviewCacheManager(object):
	"""is a class that manages the preview cache.

	It's really the class that manages it, so don't bother creating instances.

	The idea is that you pass the arguments to the preview binary, and
	the class generates a more-or-less unique file name from them.  It then
	checks if that name exists in the cache dir.

	If it exists, it is touched and the content is returned, if it doesn't
	the preview is generated, stored under that file name, and again
	the content is returned.

	Any failures while writing the preview are ignored, so we should be
	able to run cacheless.

	Since we touch files before delivering them, you can clean up rarely
	used previews by deleting all files in the preview cache older than,
	say, a year.
	"""
	cachePath = config.get("web", "previewCache")
	previewName = os.path.join(config.get("inputsDir"), "__system",
		"bin", "fitspreview")

	@classmethod
	def getCacheName(cls, args):
		return os.path.join(cls.cachePath, md5.new(str(args)).hexdigest())

	@classmethod
	def saveToCache(self, data, cacheName):
		try:
			f = open(cacheName, "w")
			f.write(data)
			f.close()
		except IOError: # caching failed, don't care
			pass
		return data

	@classmethod
	def getPreviewFor(cls, args):
		"""returns a deferred firing a string containing the preview (a jpeg,
		in general).
		"""
		cacheName = cls.getCacheName(args)
		if os.path.exists(cacheName):
			try:
				os.utime(cacheName, None)
			except os.error: # may be a permission problem
				pass    # not important enough to bother
			f = open(cacheName)
			res = f.read()
			f.close()
			return defer.succeed(res)
		else:
			return runner.runWithData(cls.previewName, "", args
				).addCallback(cls.saveToCache, cacheName)


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
		inputDef = resource.TableDef(self.rd)
		inputDef.updateFrom(origDD.getPrimaryTableDef())
		inputDef.set_items([datadef.OutputField.fromDataField(f) 
			for f in inputDef.get_items()])
		self.dataDef = datadef.DataTransformer(self.rd, initvals={
			"Grammar": rowsetgrammar.RowsetGrammar(initvals={
				"dbFields": origDD.getPrimaryTableDef().get_items()}),
			"Semantics": resource.Semantics(initvals={
				"tableDefs": [inputDef]}),
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
		args = [targetPath]
		try:
			args.append(str(int(ctx.arg("width", 200))))
		except (KeyError, ValueError, IndexError):
			pass
		return PreviewCacheManager.getPreviewFor(args
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
				self.dataDef.getPrimaryTableDef(), queryMeta).addCallback(
			self._parseOutput, ctx, sqlPars, queryMeta).addErrback(
			lambda f: f)

	def renderHTTP(self, ctx):
		queryMeta = common.QueryMeta(ctx)
		return self.run(ctx, queryMeta)

	def locateChild(self, ctx, segments):
		return self, ()
