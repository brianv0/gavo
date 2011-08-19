"""
Code dealing with product (i.e., fits file) delivery.
"""

import cStringIO
import datetime
import hashlib
import os
import subprocess
import tempfile

from twisted.internet import defer
from twisted.internet import threads

from nevow import inevow

from zope.interface import implements

from gavo import base
from gavo import svcs
from gavo import utils
from gavo.protocols import products
from gavo.web import grend

class ItemNotFound(base.Error):
	pass


errorPng = ('iVBORw0KGgoAAAANSUhEUgAAAGQAAAAUAQMAAABBDgrWAAAABlBMVEUAAAD///+'
	'l2Z/dAAAACXBIWXMAAAsTAAALEwEAmpwYAAAAB3RJTUUH2AoYCBM7M1OqPQAAAAh0RVh0Q29tb'
	'WVudAD2zJa/AAAAa0lEQVQY02P4jwQ+MFDA+1f//7/8c3kQ7489iPev/vl8MG/+f4g0hDfhsUr'
	'F3T8Sx+dMeAzkTT6pVhT6ry59zuSTQJ7xwXUFjv8qgLyDQN7n833Fj/8VAXnnQbyHHRLZ/woYj'
	'wg/pMidxPEAITLlun9HY4kAAAAASUVORK5CYII=').decode("base64")


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
	cachePath = base.getConfig("web", "previewCache")
	previewNames = {
		'image/fits':
			base.getBinaryName(
				os.path.join(base.getConfig("inputsDir"), "__system",
				"bin", "fitspreview")),
		'image/jpeg':
			base.getBinaryName(
				os.path.join(base.getConfig("inputsDir"), "__system",
				"bin", "jpegpreview")),
		}

	@classmethod
	def getCacheName(cls, args):
		return os.path.join(cls.cachePath, hashlib.md5(str(args)).hexdigest())

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
	def getPreviewFor(cls, mime, args):
		"""returns a deferred firing a string containing the preview (a jpeg).
		"""
		cacheName = cls.getCacheName(args)
		previewMaker = cls.previewNames.get(mime, None)
		if previewMaker is None:
			raise base.DataError("Cannot make previews for %s."%mime)
		if os.path.exists(cacheName):
			try:
				os.utime(cacheName, None)
			except os.error: # may be a permission problem
				pass  # it's the the utime, and we don't use that right now anyway
			f = open(cacheName)
			res = f.read()
			f.close()
			return defer.succeed(res)
		else:
			return svcs.runWithData(previewMaker, "", args
				).addCallback(cls.saveToCache, cacheName)


def _makePreviewFromCutout(args, prod, request):
	handle, fName = tempfile.mkstemp(".fits", "cutout", 
		dir=base.getConfig("tempDir"))
	f = os.fdopen(handle, "w")
	mime = prod.contentType

	def makeCutout():
		def feedProduct():
			for chunk in prod.iterData():
				f.write(chunk)
		return threads.deferToThread(feedProduct)

	def makePreview(_):
		f.close()
		args[:0] = [fName]
		return svcs.runWithData(PreviewCacheManager.previewNames[mime], 
			"", args)

	def cleanUp(arg):
		# arg can be a result or a failure -- both a simply handed through up.
		try:
			os.unlink(fName)
		except os.error:
			pass
		return arg

	return makeCutout(
		).addCallback(makePreview
		).addCallback(cleanUp
		).addErrback(cleanUp)

	
def makePreviewFromProduct(prod, request):
	"""returns a resource spewing out a preview of the Product prod.
	"""
	args = []
	try:
		args.append(str(min(base.getConfig("web", "maxPreviewWidth"),
			int(request.args.get("width", [200])[0]))))
	except (KeyError, ValueError, IndexError):
		pass

	if isinstance(prod, products.FileProduct):  # static file: just dump
		args[:0] = [prod.sourceSpec]
		return PreviewCacheManager.getPreviewFor(prod.contentType, args
			).addCallback(deliverJpeg, request
			).addErrback(deliverFailPreview, request)
	else:
		return _makePreviewFromCutout(args, prod, request
			).addCallback(deliverJpeg, request
			).addErrback(deliverFailPreview, request)


def deliverJpeg(data, request):
	"""writes data to request, declared as a jpeg.

	Previews are supposed to be small, so we write them to request
	directly.  It will do the necessary buffering.
	"""
	request.setHeader("content-type", "image/jpeg")
	request.setHeader("content-length", str(len(data)))
	request.write(data)
	return ""


def deliverFailPreview(failure, request):
	failure.printTraceback()
	data = errorPng
	request.setResponseCode(500)
	request.setHeader("content-type", "image/png")
	request.setHeader("content-length", str(len(data)))
	request.write(data)
	return ""


class ProductRenderer(grend.ServiceBasedPage):
	"""The renderer used for delivering products.

	This will only work with a ProductCore since the resulting
	data set has to contain products.Resources.  Thus, you probably
	will not use this in user RDs.
	"""
	name = "get"
	pathFromSegments = ""

	def renderHTTP(self, ctx):
		request = inevow.IRequest(ctx)
		try:
			data = {"accref": 
				products.RAccref.fromRequest(self.pathFromSegments, request)}
		except base.NotFoundError:
			raise base.ui.logOldExc(svcs.UnknownURI("No product specified"))
		return self.runServiceWithContext(data, ctx
			).addCallback(self._deliver, ctx)
	
	def _deliver(self, result, ctx):
		doPreview = result.queryMeta.ctxArgs.get("preview")
		rsc = result.original.getPrimaryTable().rows[0]['source']
		request = inevow.IRequest(ctx)

		if doPreview:
			res = makePreviewFromProduct(rsc, request)
			return res

		return rsc

	def locateChild(self, ctx, segments):
		if segments:
			self.pathFromSegments = "/".join(segments)
		return self, ()


class SDMRenderer(grend.ServiceBasedPage):
# THIS WAS A TEMPORARY HACK.  It's not used in new code.  Remove it
# and the reference to it from svc.cores about 2011-09
	"""A renderer that makes VOTables from SDM-like tables as generated
	by sdmCores.

	Don't use this externally -- it will probably go away when we've
	figured out how our new structured accrefs are to look like.
	"""
	name = "sdm"

	def renderHTTP(self, ctx):
		request = inevow.IRequest(ctx)
		try:
			data = {"accref": request.args["key"][0]}
		except (IndexError, KeyError):
			raise base.ui.logOldExc(svcs.UnknownURI("No product specified"))
		return self.runServiceWithContext(data, ctx
			).addCallback(self._deliver, ctx)

	def _deliver(self, result, ctx):
		from gavo import votable
		from gavo.protocols import ssap

		mime, payload = result.original

		request = inevow.IRequest(ctx)
		request.setHeader("content-type", mime)
		request.setHeader('content-disposition', 
			'attachment; filename=spec.vot')

		return payload
