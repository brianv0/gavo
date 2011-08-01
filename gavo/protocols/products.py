"""
Products, a grammar to make them, and a core turning accrefs into lists
of products.

The "user-visible" part are just accrefs, as modelled by the FatProductKey
-- they can contain instructions for cutouts or scaling, hence the additional
structure.

Using the product table and the ProductsGrammar, such accrefs are turned
into subclasses of ProductBase.  These have mime types and know how
to generate their data.  They produce data using their iterData methods;
they are intended to be streamed out by web.productrender, but they
may implement renderHTTP themselves, in which case productrender just
leaves everything to them; it's a bit unfortunate that we thus depend
on nevow here, but we'd have to reimplement quite a bit of it if we don't,
and for now it doesn't seem we'll support a different framework in the 
forseeable future.
"""

from __future__ import with_statement

import cgi
import datetime
import re
import os
import subprocess
import urllib
import urlparse

from nevow import inevow
from nevow import static
from zope.interface import implements

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


class ProductBase(object):
	"""A base class for products returned by the product core.

	See the module docstring for the big picture.

	A product is constructed with a source specfication and a mime type (both
	come from dc.products.  These are available as sourceSpec and contentType;
	additionally, they must come up with a name (suitable as a file name,
	without a path).

	The iterData method has to yield reasonable-sized chunks of data
	(self.chunkSize should be a good choice).

	The getSize method returns either the *exact* size of the byte stream 
	(suitable for content-length) or None.

	Products usually are used as nevow resources.  Therefore, they
	have a renderHTTP method.  You should not in general need to override it.
	It uses writeTo to generate the content, and getSize to figure out
	a size if possible.
	"""
	implements(inevow.IResource)

	chunkSize = 2**16

	def __init__(self, sourceSpec, contentType):
		self.sourceSpec, self.contentType = str(sourceSpec), str(contentType)
		self.name = "invalid product"

	def __str__(self):
		return "<%s %s (%s)>"%(self.__class__.__name__,
			self.sourceSpec, 
			self.contentType)
	
	def __repr__(self):
		return str(self)
	
	def __eq__(self, other):
		return (isinstance(other, self.__class__) 
			and self.sourceSpec==other.sourceSpec
			and self.contentType==other.contentType)
	
	def __ne__(self, other):
		return not self==other

	def iterData(self):
		raise NotImplementedError("Internal error: %s products do not"
			" implement iterData"%self.__class__.__name__)


class FileProduct(ProductBase):
	"""A product corresponding to a local file.

	Mime types are guessed based on a class-local dictionary; this is done
	so we don't depend on nevow here.  If nevow is available, we use its
	static.File mechanism to deliver the data.
	"""
	def __init__(self, sourceSpec, contentType=None):
		ProductBase.__init__(self, sourceSpec, contentType)
		self.name = os.path.basename(self.sourceSpec)
		if contentType is None:
			contentType = self._guessContentType()
	
	def writeTo(self, outFile):
		with open(self.sourceSpec) as f:
			utils.cat(f, outFile)

	# we probably should be using nevow.static's version of this for
	# consistency, but the interface there is too cumbersome for now.
	magicMap = {
		".txt": "text/plain",
		".fits": "image/fits",
		".gz": "application/octet-stream",
		".jpg": "image/jpeg",
		".jpeg": "image/jpeg",
	}

	def _guessContentType(self):
		"""fills the contentType attribute with a guess for the content type
		inferred from sourceSpec's extension.
		"""
		self.contentType = "application/octet-stream"
		if self.sourceSpec is None:
			return
		_, ext = os.path.splitext(self.sourceSpec.lower())
		return self.magicMap.get(ext, self.contentType)

	def iterData(self):
		with open(self.sourceSpec) as f:
			data = f.read(self.chunkSize)
			if data=="":
				return
			yield data

	def renderHTTP(self, ctx):
		request = inevow.IRequest(ctx)
		request.setHeader("content-disposition", 'attachment; filename="%s"'%
			str(self.name))
		request.setLastModified(os.path.getmtime(self.sourceSpec))
		res = static.File(self.sourceSpec)
		# we set the type manually to avoid having different mime types
		# by our and nevow's estimate.  This forces us to clamp encoding
		# to None now.  I *guess* we should do something about .gz and .bz2
		res.type = self.contentType
		res.encoding = None
		return res


class UnauthorizedProduct(FileProduct):
	"""A local file that is not delivered to the current client. 

	iterData returns the data for the benefit of preview making.
	However, there is a renderHTTP method, so the product renderer will
	not use it; it will, instead, raise an Authenticate exception.
	"""
	def __str__(self):
		return "<Protected product %s, access denied>"%self.name

	def __eq__(self, other):
		return self.__class__==other.__class__
	
	def renderHTTP(self, ctx):
		raise svcs.Authenticate(self.sourceSpec)


class NonExistingProduct(ProductBase):
	"""A local file that went away.

	iterData here raises an IOError, renderHTTP an UnknownURI.

	These should normally yield 404s.
	"""
	def __init__(self, sourceSpec, contentType=None):
		ProductBase.__init__(self, sourceSpec, contentType)
		self.name = os.path.basename(sourceSpec)

	def __str__(self):
		return "<Non-existing product %s>"%self.name

	def __eq__(self, other):
		return self.__class__==other.__class__

	def iterData(self):
		raise IOError("%s does not exist"%self.sourceSpec)

	def renderHTTP(self, ctx):
		raise svcs.UnknownURI(self.sourceSpec)


class RemoteProduct(ProductBase):
	"""A class for products at remote sites, given by their URL.
	"""
	def __init__(self, sourceSpec, contentType):
		ProductBase.__init__(self, sourceSpec, contentType)
		self.name = urlparse.urlparse(sourceSpec).path.split("/")[-1] or "file"

	def __str__(self):
		return "<Remote %s at %s>"%(self.contentType, self.sourceSpec)
	
	def __eq__(self, other):
		return (isinstance(other, self.__class__) 
			and self.sourceSpec==other.sourceSpec)

	def iterData(self):
		# this may block arbitrarily long -- try and use twisted's http
		# client instead?
		f = urllib.urlopen(self.sourceSpec)
		while True:
			data = f.read(self.chunkSize)
			if data=="":
				break
			yield data

	def renderHTTP(self, ctx):
		raise svcs.WebRedirect(self.sourceSpec)


class CutoutProduct(ProductBase):
	"""A class representing cutouts from FITS files.
	
	This currently only works for local FITS files.  Objects are
	constructed with the path to the full source and the cutout
	parameters, a dictionary containing the keys ra, dec, sra, and sdec.

	We assume the cutouts are smallish -- they are, right now, not
	streamed, but accumulated in memory.
	"""
	def __init__(self, sourceSpec, cutoutPars, contentType):
		ProductBase.__init__(self, sourceSpec, contentType)
		self.name = "cutout-"+os.path.basename(self.sourceSpec)
		self.cutoutPars = cutoutPars

	def __str__(self):
		return "<FITS cutout of %s, (%fx%f)>"%(self.sourceSpec,
			self.cutoutPars[2], self.cutoutPars[3])

	def __eq__(self, other):
		return (isinstance(other, self.__class__) 
			and self.sourceSpec==other.sourceSpec
			and self.contentType==other.contentType
			and self.cutoutPars==other.cutoutPars)
	
	def _computeGetfitsArgs(self):
		"""returns a list of command line arguments for getfits to cut out
		the field specified in sqlPars from the image specified in item.
		"""
		ra, dec, sra, sdec = [self.cutoutPars[key] for key in 
			["ra", "dec", "sra", "sdec"]]
		f = open(self.sourceSpec)
		header = fitstools.readPrimaryHeaderQuick(f)
		ra, dec = float(ra), float(dec),
		sra, sdec = float(sra), float(sdec),
		getPixCoo = coords.getInvWCSTrafo(header)

		def clampX(x):
			return min(header["NAXIS1"], max(0, x))
		def clampY(y):
			return min(header["NAXIS2"], max(0, y))

		corners = [getPixCoo(*args) for args in (
			(ra+sra/2, dec+sdec/2), (ra-sra/2, dec+sdec/2),
			(ra+sra/2, dec-sdec/2), (ra-sra/2, dec-sdec/2))]
		xVals, yVals = [c[0] for c in corners], [c[1] for c in corners]

		minX, maxX = clampX(min(xVals)), clampX(max(xVals))
		minY, maxY = clampY(min(yVals)), clampY(max(yVals))
		return ["-s", self.sourceSpec, 
			"%d-%d"%(minX, maxX), "%d-%d"%(minY, maxY)]

	def _getProcessParameters(self):
		"""returns a pair of program name and program args to start the
		actual cutout.
		"""
		if self.contentType!="image/fits":
			raise NotImplementedError("Cannot generate cutouts for anything"
				" but FITS yet.")
		prog = base.getBinaryName(os.path.join(base.getConfig("inputsDir"),
			"__system", "bin", "getfits"))
		return prog, self._computeGetfitsArgs()

	def iterData(self):
		prog, args = self._getProcessParameters()
		devnull = open("/dev/null", "w")
		pipe = subprocess.Popen([prog]+args, self.chunkSize,
			stdout=subprocess.PIPE, close_fds=True, stderr=devnull)
		devnull.close()
		while True:
			data = pipe.stdout.read(self.chunkSize)
			if not data:
				break
			yield data
		res = pipe.wait()
		if res:
			raise IOError("Broken pipe, return value %d"%res)

	def renderHTTP(self, ctx):
		prog, args = self._getProcessParameters()
		return svcs.runWithData(prog, "", args, swallowStderr=True
			).addCallback(self._deliver, ctx)
	
	def _deliver(self, result, ctx):
		request = inevow.IRequest(ctx)
		request.setHeader("content-type", self.contentType)
		request.setHeader("content-disposition", 'attachment; filename="%s"'%
			str(self.name))
		return str(result)
		

class ScaledProduct(ProductBase):
	"""A class representing a scaled FITS file.

	pars must be a dictionary containing at least one key, scale, pointing
	to an int with a sensible scale.

	Right now, this only works for local FITS files.
	"""
# TODO: should we use web.streaming resp. producer/consumer here?
# If so: the product renderer should probably check if a product
# implements a producer interface and the act accordingly.
	def __init__(self, sourceSpec, pars, contentType):
		self.scale = pars["scale"]
		ProductBase.__init__(self, sourceSpec, contentType)
		self.name = "scaled-"+os.path.basename(self.sourceSpec)

	def __str__(self):
		return "<Scaled version of %s>"%(self.sourceSpec)

	def iterData(self):
		raise NotImplementedError("Cannot scale yet")
		if contentType!="image/fits":
			raise NotImplementedError("Cannot generate cutouts for anything"
				" but FITS yet.")

	def renderHTTP(self, ctx):
		request = inevow.IRequest(ctx)
		request.setHeader("content-type", self.contentType)
		return self._getDeferred(request, self.iterData())

	def _getDeferred(self, request, iterator):
		d = defer.Deferred()
		reactor.callLater(0.01, d.callback)
		d.addCallback(self._deliver, request, iterator)
		return d

	def _deliver(self, ignored, request, iterator):
		try:
			data = iterator.next()
		except StopIteration:
			return ""
		request.write(data)
		return _getDeferred(request, iterator)


class ProductIterator(grammars.RowIterator):
	"""A RowIterator turning FatProductKeys to Products.

	The source key is a list of annotated FatProductKeys as generated
	within ProductCore.  FatProductKeys without the annotation from
	the DB are turned into NonExistingProducts.
	"""
	def _makeProductForKey(self, fatKey, dbRow):
		"""returns the proper ProductBsse subclass for a FatProductKey
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
			rsc = FileProduct(sourcePath, dbRow["mime"])
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

	Product objects are instances of classes derived from ProductBase.
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
