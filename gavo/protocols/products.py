"""
The products interface, including a core to make the product renderer almost
trivial.
"""

# XXX TODO: this whole __call__ business is worthless.  The products
# need renderHTTP methods, and they should be ordinary nevow resources.
# If that's happened, productrender will become much nicer (at the expense
# of hardcoding nevow here).

import cgi
import datetime
import re
import os
import subprocess
import urllib
import urlparse

from gavo import base
from gavo import grammars
from gavo import rsc
from gavo import rscdef
from gavo import svcs
from gavo import utils
from gavo.base import coords
from gavo.base import valuemappers
from gavo.protocols import creds
from gavo.utils import fitstools

MS = base.makeStruct


class PlainProduct(object):
	"""A base class for products returned by the product core.

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
# XXX TODO: it was probably a bad idea to use __call__ for something like write.
# Ah well.
		f = open(self.sourcePath)
		utils.cat(f, outFile)
		f.close()

	def __str__(self):
		return "<Product %s (%s)>"%(self.sourcePath, self.contentType)
	
	def __repr__(self):
		return str(self)
	
	def __eq__(self, other):
		return (isinstance(other, self.__class__) 
			and self.sourcePath==other.sourcePath
			and self.contentType==other.contentType)
	
	def __ne__(self, other):
		return not self==other

	magicMap = {
		".txt": "text/plain",
		".fits": "image/fits",
		".gz": "application/octet-stream",
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
	"""A class for sentinels signifying products that are protected.

	You can read the data from the product without trouble, so you need
	to make explicit isinstance calls.   The reason for this behaviour
	is that previews on unauthorized products should be possible.
	"""
	def __str__(self):
		return "<Protected product %s, access denied>"%self.sourcePath

	def __eq__(self, other):
		return self.__class__==other.__class__
	

class NonExistingProduct(PlainProduct):
	"""A class for sentiels signifying products that don't exist.

	These should normally yield 404s.
	"""
	def __str__(self):
		return "<Non-existing product %s>"%self.sourcePath

	def __eq__(self, other):
		return self.__class__==other.__class__

	def __call__(self, outFile):
		raise svcs.UnknownURI(self.sourcePath)


class RemoteProduct(PlainProduct):
	"""A class for products at remote sites, given by their URL.
	"""
	def __str__(self):
		return "<Remote %s at %s>"%(self.contentType, self.sourcePath)
	
	def __eq__(self, other):
		return (isinstance(other, self.__class__) 
			and self.sourcePath==other.sourcePath)
	
	def __call__(self, outFile):
		# This is really handled specially by the product renderer,
		# but just in case, let's put something in so humans can
		# still go on if things break
		outFile.write("This should be a redirect to a %s file at\n%s\n"%(
			self.contentType, self.sourcePath))
		outFile.write("If you are reading this, there's something wrong,\n"
			"and you're welcome to complain to the site you got this from.\n")


class CutoutProduct(PlainProduct):
	"""A class representing cutouts from FITS files.
	"""
	def __init__(self, sourcePath, cutoutPars, contentType):
		self.fullFilePath = sourcePath
		self.cutoutPars = cutoutPars
		PlainProduct.__init__(self, None, contentType)

	def __str__(self):
		return "<FITS cutout of %s, (%fx%f)>"%(sourcePath,
			self.cutoutPars[2], self.cutoutPars[3])

	def __eq__(self, other):
		return (isinstance(other, self.__class__) 
			and self.fullFilePath==other.fullFilePath
			and self.contentType==other.contentType
			and self.cutoutPars==other.cutoutPars)
	
	def __call__(self, outFile):
		if self.contentType!="image/fits":
			raise NotImplementedError("Cannot generate cutouts for anything"
				" but FITS yet.")
		prog = base.getBinaryName(os.path.join(base.getConfig("inputsDir"),
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
		print [(ra+sra/2, dec+sdec/2), (ra-sra/2, dec+sdec/2),
			(ra+sra/2, dec-sdec/2), (ra-sra/2, dec-sdec/2),]
		corners = [getPixCoo(*args) for args in (
			(ra+sra/2, dec+sdec/2), (ra-sra/2, dec+sdec/2),
			(ra+sra/2, dec-sdec/2), (ra-sra/2, dec-sdec/2))]
		xVals, yVals = [c[0] for c in corners], [c[1] for c in corners]

		minX, maxX = clampX(min(xVals)), clampX(max(xVals))
		minY, maxY = clampY(min(yVals)), clampY(max(yVals))
		return ["-s", self.fullFilePath, 
			"%d-%d"%(minX, maxX), "%d-%d"%(minY, maxY)]

	def _makeName(self):
		self.name = "cutout-"+os.path.basename(self.fullFilePath)


class ScaledProduct(PlainProduct):
	"""A class representing a scaled FITS file.
	"""
	def __init__(self, sourcePath, pars, contentType):
		self.fullFilePath = sourcePath
		self.scale = pars["scale"]
		PlainProduct.__init__(self, None, contentType)

	def __str__(self):
		return "<Scaled version of %s>"%(self.fullFilePath)

	def __call__(self, outFile):
		raise NotImplementedError("Cannot scale yet")
		if contentType!="image/fits":
			raise NotImplementedError("Cannot generate cutouts for anything"
				" but FITS yet.")

	def _makeName(self):
		self.name = "scaled-"+os.path.basename(self.fullFilePath)


class ProductIterator(grammars.RowIterator):
	"""A RowIterator turning FatProductKeys to Products.

	The source key is a list of annotated FatProductKeys as generated
	within ProductCore.  FatProductKeys without the annotation from
	the DB are turned into NonExistingProducts.
	"""
	def _makeProductForKey(self, fatKey, dbRow):
		"""returns the proper PlainProduct subclass for a FatProductKey
		and its corresponding product table row.
		"""
		path = dbRow["accessPath"]
		if path.startswith("http://"):
			return RemoteProduct(path, dbRow["mime"])

		sourcePath = os.path.join(base.getConfig("inputsDir"), path)
		if fatKey.isCutout():
			rsc = CutoutProduct(sourcePath, fatKey.params, dbRow["mime"])
		elif fatKey.isScaled():
			rsc = ScaledProduct(sourcePath, fatKey.params, dbRow["mime"])
		else:
			rsc = PlainProduct(sourcePath, dbRow["mime"])
		if dbRow["embargo"] is not None and dbRow["embargo"]>self.grammar.now:
			if dbRow["owner"] not in self.grammar.groups:
				rsc = UnauthorizedProduct(sourcePath)
		return rsc

	def _iterRows(self):
		for key in self.sourceToken:
			try:
				prodRow = key.productsRow
			except AttributeError:
				prod = NonExistingProduct(key.baseKey)
			else:
				prod = self._makeProductForKey(key, prodRow)
			yield {
				"source": prod,
			}
		del self.grammar


class ProductsGrammar(grammars.Grammar):
	"""A grammar for "parsing" annotated FatProductKeys to Product
	objects.

	The FatProductRecords must have their product table rows in 
	productsRow attributes (ProductCore.addFSSources does that).

	Product objects are instances of PlainProduct or derived classes.
	"""
	rowIterator = ProductIterator

	_groups = base.StringSetAttribute("groups")

	def __init__(self, *args, **kwargs):
		self.now = datetime.date.today()
		grammars.Grammar.__init__(self, *args, **kwargs)


class ProductCore(svcs.DBCore):
	"""A core retrieving paths and/or data from the product table.

	You will not usually mention this core in your RDs.  It is mainly
	used internally to serve /getproduct queries.

	It does:

	- the actual query, 
	- access validation (i.e., makes sure the user has access to the product), 
	- cutout processing (via a special construct deferring cutouts until they
		are needed)

	It is instanciated from within //products.rd and relies on
	certain features in there.

	The input data consists of FatProductKeys in InMemoryTables.  You
	can pass those in in both an accref param and table rows.  The
	accref param is the normal way if you just want to retrieve a
	single image, the table case is for building tar files and such.
	There is one core instance in //products for each case.
	"""
	name_ = "productCore"

	def _getRequestedKeys(self, inputTable):
		"""returns a list of FatProductKeys requested within inputTable.
		"""
		keysList = [FatProductKey.fromString(r["accref"])
			for r in inputTable.rows if "accref" in r]
		try:
			param = inputTable.getParam("accref")
			if param is not None:
				keysList.append(FatProductKey.fromString(param))
		except base.NotFoundError: # "tar case", accrefs in rows
			pass
		return keysList

	def _addFSSources(self, keysList):
		"""adds productsRow attributes to each in FatProductKey in keysList.

		This happens by querying the products table in the database.
		"""
		keyForAccref = dict(((r.baseKey, r) for r in keysList))

		if not keysList: # stupid SQL doesn't know the empty set
			query, pars = "FALSE", {}
		else:
			query, pars = "accref IN %(keys)s", {"keys": set(k.baseKey
			for k in keysList)}

		prodTbl = rsc.TableForDef(self.queriedTable,
				connection=base.caches.getTableConn(None))
		paths = {}
		for row in prodTbl.iterQuery(self.rd.getById("productsResult"),
				query, pars):
			keyForAccref[row["accref"]].productsRow = row

	def _getGroups(self, user, password):
		if user is None:
			return set()
		else:
			return creds.getGroupsForUser(user, password)

	def run(self, service, inputTable, queryMeta):
		"""returns a data set containing product sources for the keys mentioned in
		inputTable.
		"""
		authGroups = self._getGroups(queryMeta["user"], queryMeta["password"])
		keysList = self._getRequestedKeys(inputTable)
		self._addFSSources(keysList)

		dd = MS(rscdef.DataDescriptor, grammar=MS(ProductsGrammar,
				groups=authGroups),
			make=[MS(rscdef.Make, table=self.outputTable)])
		return rsc.makeData(dd, forceSource=keysList)


class FatProductKey(object):
	"""A product key for a possibly processed image.

	This consists of a key proper and of optional further data specifying
	how it is to be processed.  Currently defined are:

	* ra, dec, sra, sdec: center and extend for cutouts.
	* scale: (integer) factor the image should be scaled down by.

	Stringifying a FPK yields something quoted ready-made for URLs.

	We should probably move as much product handling to this class
	as possible and not use plain strings as product keys any more --
	possibly even in the DB.

	During products processing, these keys receive an additional
	productsRow attribute -- that's a dictionary containing a row form
	//products#products.
	"""
	_buildKeys = (
		("key", str), 
		("ra", float),
		("dec", float),
		("sra", float),
		("sdec", float),
		("scale", int))

	def __init__(self, **kwargs):
		self.params = {}
		for key, valCons in self._buildKeys:
			if key in kwargs and kwargs[key] is not None:
				try:
					val = kwargs.pop(key)
					self.params[key] = valCons(val)
				except (ValueError, TypeError):
					raise base.ValidationError(
						"Invalid value for constructor argument to %s:"
						" %s=%r"%(self.__class__.__name__, key, val), "accref")

		if kwargs:
			raise base.ValidationError(
					"Invalid constructor argument(s) to %s: %s"%(
					self.__class__.__name__,
					", ".join(kwargs)),
				"accref")

		if not "key" in self.params:	
			raise base.ValidationError("Must give key when constructing %s"%(
				self.__class__.__name__), "accref")
		self.baseKey = self.params["key"]

	@classmethod
	def fromRequest(cls, request):
		"""returns a fat product key from a nevow request.

		Basically, it raises an error if there's no key at all, it will return
		a (string) accref if no processing is desired, and it will return
		a FatProductKey if any processing is requested.
		"""
		inArgs = request.args
		buildArgs = {}
		for reqKey, _ in cls._buildKeys:
			argVals = inArgs.get(reqKey, [])
			if len(argVals)>0:
				buildArgs[reqKey] = argVals[0]
		return cls(**buildArgs)

	@classmethod
	def fromString(cls, keyString):
		"""returns a fat product key from a string representation.

		As a convenience, if keyString already is a FatProductKey,
		it is returned unchanged.
		"""
		if isinstance(keyString, FatProductKey):
			return keyString
		args = dict((k, v[0]) 
			for k, v in urlparse.parse_qs("key="+keyString).iteritems())
		return cls(**args)

	def __str__(self):
		# this is an accref as used in getproduct, i.e., the product key
		# plus optionally processing arguments
		key = quoteProductKey(self.params["key"])
		args = urllib.urlencode(dict(
			(k,str(v)) for k, v in self.params.iteritems() if k!="key"))
		if args:
			key = key+"&"+args
		return key

	def __repr__(self):
		return str(self)

	def __eq__(self, other):
		return (isinstance(other, FatProductKey) 
			and self.params==other.params)

	def __ne__(self, other):
		return not self.__eq__(other)

	def isPlain(self):
		return self.params.keys()==["key"]

	_cutoutKeys = frozenset(["ra", "dec", "sra", "sdec"])

	def isCutout(self):
		return len(set(self.params.keys())&self._cutoutKeys)==4

	def isScaled(self):
		return self.params.get("scale", 1)!=1


@utils.document
def quoteProductKey(key):
	"""URL-quotes product keys.

	Actually, it url quotes any string, but we have special arrangements
	for the presence of FatProductKeys, and we make sure the key is
	safe for inclusion in URLs as regards the stupid plus-to-space
	convention.
	"""
	if isinstance(key, FatProductKey):
		return str(key)
	return urllib.quote_plus(key)
rscdef.addProcDefObject("quoteProductKey", quoteProductKey)


@utils.document
def makeProductLink(key, withHost=True):
	"""returns the URL at which a product can be retrieved.
	"""
	url = base.makeSitePath("/getproduct?key=%s"%quoteProductKey(key))
	if withHost:
		url = urlparse.urljoin(base.getConfig("web", "serverURL"), url)
	return url
rscdef.addProcDefObject("makeProductLink", makeProductLink)


# Sigh -- the whole value mapping business needs to be cleaned up.
def _productMapperFactory(colDesc):
	"""A factory for accrefs.

	Within the DC, any column called accref, with a display hint of
	type=product, a UCD of VOX:Image_AccessReference, or a utype
	of Access.Reference may contain a key into the product table.
	Here, we map those to links to the get renderer unless they look
	like a URL to begin with.
	"""
	if not (
			colDesc["name"]=="accref"
			or colDesc["utype"]=="ssa:Access.Reference"
			or colDesc["ucd"]=="VOX:Image_AccessReference"
			or colDesc["displayHint"].get("type")=="product"):
		return
	
	looksLikeURLPat = re.compile("[a-z]{2,5}://")

	def mapper(val):
		if val:
			# type check to allow cut-out or scaled accrefs (which need 
			# makeProductLink in any case)
			if isinstance(val, basestring) and looksLikeURLPat.match(val):
				return val
			else:
				return makeProductLink(val, withHost=True)
	return mapper

valuemappers._registerDefaultMF(_productMapperFactory)
