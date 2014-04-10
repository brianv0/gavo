"""
Code dealing with product (i.e., fits file) delivery.
"""

#c Copyright 2008-2014, the GAVO project
#c
#c This program is free software, covered by the GNU GPL.  See the
#c COPYING file in the source distribution.


from cStringIO import StringIO
import datetime
import hashlib
import os
import subprocess
import tempfile

from twisted.internet import defer
from twisted.internet import threads

from nevow import inevow

from zope.interface import implements

import Image

import numpy

from gavo import base
from gavo import svcs
from gavo import utils
from gavo.protocols import products
from gavo.utils import pyfits
from gavo.utils import fitstools
from gavo.web import grend

class ItemNotFound(base.Error):
	pass


# TODO: make this configurable -- globally?  by service?
PREVIEW_SIZE = 200

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
	if prod.pr["mime"]!="image/fits":
		raise base.DataError("Cutout previews only for image/fits")

	f = StringIO(prod.read())
	hdu = pyfits.open(f)[0]
	origWidth, origHeight = hdu.header["NAXIS2"], hdu.header["NAXIS1"]
	size = max(origWidth, origHeight)
	scale = max(1, size//PREVIEW_SIZE+1)
	destWidth, destHeight = origWidth//scale, origHeight//scale

# TODO: refactor this and the code in fitstools 
	summedInds = range(scale)
	img = numpy.zeros((destWidth, destHeight), 'float32')

	data = hdu.data
	for rowInd in range(destHeight):
		wideRow = (numpy.sum(
			data[:,rowInd*scale:(rowInd+1)*scale], 1, 'float32'
			)/scale)[:destWidth*scale]
		# horizontal scaling via reshaping to a matrix and then summing over
		# its columns.
		newRow = numpy.sum(
			numpy.transpose(wideRow.reshape((destWidth, scale))), 0)/scale
		img[:,rowInd] = newRow

	f.close()
	img = numpy.flipud(img)

	pixMax, pixMin = numpy.max(img), numpy.min(img)
	img = numpy.asarray((img-pixMin)/(pixMax-pixMin)*255, 'uint8')
	f = StringIO()
	Image.fromarray(img).save(f, format="jpeg")
	return defer.succeed(f.getvalue())


	
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
		args[:0] = [prod.rAccref.localpath]
		return PreviewCacheManager.getPreviewFor(prod.pr["mime"], args
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
		return self.runServiceWithFormalData(data, ctx
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
