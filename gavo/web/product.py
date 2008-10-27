"""
Code dealing with product (i.e., fits file) delivery.
"""

import cStringIO
import cgi
import md5
import os
import subprocess
import tempfile

from mx import DateTime

from twisted.internet import defer
from twisted.internet import threads

from nevow import inevow
from nevow import static

from zope.interface import implements

import gavo
from gavo import config
from gavo import coords
from gavo import datadef
from gavo import fitstools
from gavo import record
from gavo import resourcecache
from gavo.parsing import rowsetgrammar
from gavo.parsing import resource
from gavo.web.common import Error, UnknownURI
from gavo.web import common
from gavo.web import core
from gavo.web import creds
from gavo.web import gwidgets
from gavo.web import runner
from gavo.web import standardcores

class ItemNotFound(Error):
	pass


errorPng = ('iVBORw0KGgoAAAANSUhEUgAAAGQAAAAUAQMAAABBDgrWAAAABlBMVEUAAAD///+'
	'l2Z/dAAAACXBIWXMAAAsTAAALEwEAmpwYAAAAB3RJTUUH2AoYCBM7M1OqPQAAAAh0RVh0Q29tb'
	'WVudAD2zJa/AAAAa0lEQVQY02P4jwQ+MFDA+1f//7/8c3kQ7489iPev/vl8MG/+f4g0hDfhsUr'
	'F3T8Sx+dMeAzkTT6pVhT6ry59zuSTQJ7xwXUFjv8qgLyDQN7n833Fj/8VAXnnQbyHHRLZ/woYj'
	'wg/pMidxPEAITLlun9HY4kAAAAASUVORK5CYII=').decode("base64")


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


def _makePreviewFromCutout(args, prod, request):
	handle, fName = tempfile.mkstemp(".fits", "cutout", config.get("tempDir"))
	f = os.fdopen(handle, "w")

	def makeCutout():
		return threads.deferToThread(prod, f)

	def makePreview(_):
		f.close()
		args[:0] = [fName]
		return runner.runWithData(PreviewCacheManager.previewName, "", args)

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
		args.append(str(min(config.get("web", "maxPreviewWidth"),
			int(request.args.get("width", [200])[0]))))
	except (KeyError, ValueError, IndexError):
		pass

	if prod.sourcePath:  # static file: just dump
		args[:0] = [prod.sourcePath]
		return PreviewCacheManager.getPreviewFor(args
			).addCallback(deliverJpeg, request
			).addErrback(deliverFailPreview, request)
	else:
		return _makePreviewFromCutout(args, prod, request
			).addCallback(deliverJpeg, request
			).addErrback(deliverFailPreview, request)


class PlainProduct(object):
	"""is a base class for products returned by the product core.

	A product has a name (always has to be a string suitable for a
	file name, and *without* a path), a sourcePath (may be None if
	the content is computed on the fly), a contentType.

	If called, it has to spew out content to the only argument of
	__call__, supposed to be something file-like.
	"""
	chunkSize = 2**16

	def __init__(self, sourcePath, contentType=None):
		self.sourcePath, self.contentType = sourcePath, contentType
		if self.contentType is None:
			self._guessContentType()
		self._makeName()

	def __call__(self, outFile):
		f = open(self.sourcePath)
		while True:
			data = f.read(self.chunkSize)
			if not data:
				break
			outFile.write(data)
		f.close()
	
	def __str__(self):
		return "<Product %s>"%self.sourcePath

# XXX TODO bad hack -- have mime type move from siap to products
	magicMap = {
		".txt": "text/plain",
		".fits": "image/fits",
		".gz": "image/fits",  # Yikes.
		".jpg": "image/jpeg",
		".jpeg": "image/jpeg",
	}

	def _guessContentType(self):
		"""fills the contentType attribute with a guess for the content type
		inferred from sourcePath's extension.
		"""
		self.contentType = "application/octet-stream"
		if self.sourcePath is None:
			return
		_, ext = os.path.splitext(self.sourcePath.lower())
		self.contentType = self.magicMap.get(ext, self.contentType)

	def _makeName(self):
		self.name = os.path.basename(self.sourcePath)


class UnauthorizedProduct(PlainProduct):
	"""is a class for sentinels signifying products that are protected.

	You can read the data from the product without trouble, so you need
	to make explicit isinstance calls.   The reason for this behaviour
	is that previews on unauthorized products should be possible.
	"""
	def __str__(self):
		return "<Protected product %s, access denied>"


class NonExistingProduct(PlainProduct):
	"""is a class for sentiels signifying products that don't exist.

	These should normally yield 404s.
	"""
	def __str__(self):
		return "<Non-existing product %s>"
	
	def __call__(self, outFile):
		raise common.UnknownURI(outFile)


class CutoutProduct(PlainProduct):
	"""is a class returning cutouts from FITS files.
	"""
	def __init__(self, sourcePath, cutoutPars):
		self.fullFilePath = sourcePath
		self.cutoutPars = cutoutPars
		PlainProduct.__init__(self, None, "image/fits")

	def __str__(self):
		return "<FITS cutout of %s, (%fx%f)>"%(sourcePath,
			self.cutoutPars[2], self.cutoutPars[3])
	
	def __call__(self, outFile):
		prog = runner.getBinaryName(os.path.join(config.get("inputsDir"),
			"__system", "bin", "getfits"))
		devnull = open("/dev/null", "w")
		pipe = subprocess.Popen([prog]+self._computeGetfitsArgs(), self.chunkSize,
			stdout=subprocess.PIPE, close_fds=True, stderr=devnull)
		devnull.close()
		while True:
			data = pipe.stdout.read(self.chunkSize)
			if not data:
				break
			outFile.write(data)
		res = pipe.wait()
		if res:
			raise IOError("Broken pipe, return value %d"%res)

	def _computeGetfitsArgs(self):
		"""returns a list of command line arguments for getfits to cut out
		the field specified in sqlPars from the image specified in item.
		"""
		ra, dec, sra, sdec = [self.cutoutPars[key] for key in 
			["ra", "dec", "sra", "sdec"]]
		f = open(self.fullFilePath)
		header = fitstools.readPrimaryHeaderQuick(f)
		ra, dec = float(ra), float(dec),
		sra, sdec = float(sra), float(sdec),
		getPixCoo = coords.getInvWCSTrafo(header)

		def clampX(x):
			return min(header["NAXIS1"], max(0, x))
		def clampY(y):
			return min(header["NAXIS2"], max(0, y))

		x, y = map(int, getPixCoo(ra, dec))
		w = int(abs(clampX(getPixCoo(ra+sra/2, dec)[0]
			)-clampX(getPixCoo(ra-sra/2, dec)[0])))
		h = int(abs(clampY(getPixCoo(ra, dec+sdec/2)[1]
			)-clampY(getPixCoo(ra, dec-sdec/2)[1])))
		x = max(0, min(header["NAXIS1"]-w, x-w/2))
		y = max(0, min(header["NAXIS2"]-h, y-h/2))
		return ["-s", self.fullFilePath, "%d-%d"%(x, x+w), "%d-%d"%(y, y+h)]

	def _makeName(self):
		self.name = "cutout-"+os.path.basename(self.fullFilePath)


class ProductsGrammar(rowsetgrammar.RowsetGrammar):
	"""is a grammar for parsing raw DB results into delivery records.

	It's a bit hard doing the things that need to be done with macros,
	hence this custom grammar.
	"""
	def __init__(self, initvals={}):
		rowsetgrammar.RowsetGrammar.__init__(self,
			additionalFields={
				"groups": None,    # set-valued by program logic
				"realInput": None, # table of parsed product keys
			},
			initvals=initvals)
		self.now = DateTime.now()

	def _makeProductForRow(self, row, dbRow):
		"""returns the proper PlainProduct subclass for an image described by
		the parsed key row and the prodcut table info dbRow.
		"""
		sourcePath = os.path.join(config.get("inputsDir"), dbRow["accessPath"])
		if row["sra"]:
			rsc = CutoutProduct(sourcePath, row)
		else:
			rsc = PlainProduct(sourcePath)
		if dbRow["embargo"]>self.now:
			if dbRow["owner"] not in self.get_groups():
				rsc = UnauthorizedProduct(sourcePath)
		return rsc

	def _iterRows(self, parseContext):
		dbRowsByKey = dict((r["key"], r)
			for r in rowsetgrammar.RowsetGrammar._iterRows(self, parseContext))
		for row in self.get_realInput():
			if row["key"] in dbRowsByKey:
				rsc = self._makeProductForRow(row, dbRowsByKey[row["key"]])
			else:
				rsc = NonExistingProduct(row["key"])
			yield {
				"source": rsc,
			}


class ProductCore(standardcores.DbBasedCore):
	"""is a core retrieving paths and/or data from the product table.

	It does:
	
	* the actual query,
	* access validation (i.e., makes sure the user has access to the product),
	* cutout processing (via a special construct deferring cutouts until they
	  are needed)

	The rd it is constructed with must contain a table named products with
	at least the fields this table has in products.vord (so, it probably
	should always be products.vord).

	This is a bit of a hack in that a table containing the parsed keys (accrefs
	plus cutout specs, if present) is added to the input data in _getSQLWhere.
	The database sees the naked accrefs and resolves them to file system paths.
	These are then combined with the parsed keys table in the grammar to form the
	objects returned to the renderer.
	"""
	def __init__(self, rd, initvals):
		vals = initvals.copy()
		if not "table" in initvals:
			initvals["table"] = "products"
		standardcores.DbBasedCore.__init__(self, rd, initvals)

	def getInputFields(self):
		return record.DataFieldList([gwidgets.InputKey.fromDataField(
				self.tableDef.getFieldByName("key"))])

	def getQueryFields(self, queryMeta):
		return record.DataFieldList([datadef.OutputField.fromDataField(f)
			for f in self.rd.getTableDefByName("pDbOutput").get_items()])

	def getOutputFields(self):
		return record.DataFieldList([datadef.OutputField.fromDataField(f)
			for f in self.rd.getTableDefByName("pCoreOutput").get_items()])

	def _parseKeys(self, keys):
		"""returns an iterator over dictionaires of parsed fields of the 
		(possibly cut-out) product keys in keys.

		These may have cutout specs.  None items in keys are dropped.
		"""
		for key in keys:
			if key is not None:
				yield dict(cgi.parse_qsl("key="+key))

	def _getSQLWhere(self, inputData, queryMeta):
		"""returns a query string fragment and the parameters to query
		the DB for the access paths for the input keys.

		As a side effect, an attribute keysTable will be created, containing
		a table of "parsed" keys (i.e., (key, ra, dec, sra, sdec) for cutouts.
		This key table is later the real input for the ProductsGrammar.
		"""
		keys = [inputData.docRec.get("key")]+[
			r.get("key") for r in inputData.getPrimaryTable().rows]
		self.keysTable = resource.makeSimpleData(self.rd.getTableDefByName(
			"parsedKeys"), self._parseKeys(keys)).getPrimaryTable()
		return "key IN %(keys)s", {"keys": set(r["key"] 
			for r in self.keysTable.rows)}

	def _getGroups(self, user, password):
		if user is None:
			return set()
		else:
			return creds.getGroupsForUser(user, password, async=False)

	def _parseOutput(self, dbResponse, outputTD, queryMeta):
		"""enriches the input to _parseOutput by the groups the querying
		user is authorized for.

		Errors while retrieving auth info will be ignored and translated
		as no groups.
		"""
		copiedArgs = dbResponse, outputTD, queryMeta
		return creds.getGroupsForUser(queryMeta["user"], queryMeta["password"],
				async=True
			).addCallback(self._realParseOutput, *copiedArgs
			).addErrback(lambda failure: self._realParseOutput(set(),
				*copiedArgs))
	
	def _realParseOutput(self, groups, dbResponse, outputTD, queryMeta):
		"""turns the db output into a list of result records.
		"""
		dd = self.rd.getDataById("pCoreOutput")
		dd.set_Grammar(ProductsGrammar(initvals={
			"groups": groups,
			"realInput": self.keysTable,
			"dbFields": self.rd.getTableDefByName("pDbOutput").get_items(),}))
		res = resource.InternalDataSet(dd, dataSource=dbResponse)
		return res

core.registerCore("product", ProductCore)
