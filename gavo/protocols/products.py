"""
Products, a grammar to make them, and a core turning accrefs into lists
of products.

The "user-visible" part are just accrefs, as modelled by the RAccref
-- they can contain instructions for cutouts or scaling, hence the additional
structure.

Using the product table and the ProductsGrammar, such accrefs are turned
into subclasses of ProductBase.  

These have mime types and know how to generate their data through their
synchronous iterData methods.  They must also work as nevow resources and thus
have implement asynchronuous renderHTTP(ctx) methods It's a bit unfortunate
that we thus depend on nevow here, but we'd have to reimplement quite a bit of
it if we don't, and for now it doesn't seem we'll support a different framework
in the forseeable future.  
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
from twisted.internet import threads
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


@utils.memoized
def getProductsTable():
	"""returns a DBTable for the product table.

	This is memoized, i.e., it will be the same table for all threads.
	This should be ok as long as pycopg's promise of its thread-safety
	holds.
	"""
	td = base.caches.getRD("//products").getById("products")
	conn = base.getDBConnection("admin", autocommitted=True)
	return rsc.TableForDef(td, connection=conn)


class ProductBase(object):
	"""A base class for products returned by the product core.

	See the module docstring for the big picture.

	The constructor arguments of RAccrefs depend on what they are.
	The common interface (also used by the ProductGrammar below) is the 
	the class method fromRAccref(rAccref, grammar=None).  It returns None
	if the RAccref is not for a product of the respective sort, the
	product otherwise.  Grammar, if given, is an instance of the
	products grammar.  It is important, e.g., in controlling access
	to embargoed products.  This is the main reason you should
	never hand out products yourself but always expose the to the user
	through the product core.

	The iterData method has to yield reasonable-sized chunks of data
	(self.chunkSize should be a good choice).  It must be synchronuous.

	Products usually are used as nevow resources.  Therefore, they
	must have a renderHTTP method.  This must be asynchronuous, i.e., it
	should not block for extended periods of time.

	All products must at least have the attributes sourceSpec (a string
	with an interpretation that's up to the subclass), contentType (which
	should usually be what renderHTTP puts into its content-type), and
	name (something suitable as a file name; the default constructor
	calls a _makeName method to come up with one, and you should simply
	override it).
	"""
	implements(inevow.IResource)

	chunkSize = 2**16

	def __init__(self, sourceSpec, contentType):
		self.sourceSpec, self.contentType = str(sourceSpec), str(contentType)
		self._makeName()

	def _makeName(self):
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

	@classmethod
	def fromRAccref(self, accref, grammar=None):
		return None # ProductBase is not responsible for anything.

	def iterData(self):
		raise NotImplementedError("Internal error: %s products do not"
			" implement iterData"%self.__class__.__name__)

	def renderHTTP(self, ctx):
		raise NotImplementedError("Internal error: %s products cannot be"
			" rendered."%self.__class__.__name__)


class FileProduct(ProductBase):
	"""A product corresponding to a local file.

	Mime types are guessed based on a class-local dictionary; this is done
	so we don't depend on nevow here.  If nevow is available, we use its
	static.File mechanism to deliver the data.

	This is basically a fallback for fromRAccref; as long as the 
	accessPath in the RAccref's productsRow corresponds to a real file and
	no params are in the RAccref, this will return a product.
	"""
	def __init__(self, sourcePath, contentType=None):
		ProductBase.__init__(self, sourcePath, contentType)
		if contentType is None:
			self.contentType = self._guessContentType()

	@classmethod
	def fromRAccref(cls, rAccref, grammar=None):
		if rAccref.params:  # not a plain file
			return None
		if os.path.exists(rAccref.localpath):
			return cls(rAccref.localpath, rAccref.productsRow["mime"])

	def _makeName(self):
		self.name = os.path.basename(self.sourceSpec)
	
	# we probably should be using nevow.static's version of this for
	# consistency, but the interface there is too cumbersome for now.
	# It's not regularly used by the DC software any more, anyway.
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
	@classmethod
	def fromRAccref(cls, rAccref, grammar=None):
		dbRow = rAccref.productsRow
		if (dbRow["embargo"] is None 
				or dbRow["embargo"]<datetime.date.today()):
			return None
		if grammar is None or dbRow["owner"] not in grammar.groups:
			return cls(rAccref)

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
	def __str__(self):
		return "<Non-existing product %s>"%self.sourceSpec

	def __eq__(self, other):
		return self.__class__==other.__class__

	@classmethod
	def fromRAccref(cls, rAccref, grammar=None):
		try:
			ignored = rAccref.productsRow
		except base.NotFoundError:
			return cls(rAccref.accref, "text/html")

	def _makeName(self):
		self.name = "missing.html"

	def iterData(self):
		raise IOError("%s does not exist"%self.sourceSpec)

	def renderHTTP(self, ctx):
		raise svcs.UnknownURI(self.sourceSpec)


class InvalidProduct(NonExistingProduct):
	"""An invalid file.
	
	This is returned by getProductForRAccref if all else fails.  This
	usually happens when a file known to the products table is deleted,
	but it could also be an attempt to use unsupported combinations
	of files and parameters.

	Since any situation leading here is a bit weird, we probably
	should be doing something else but just return a 404.  Hm...

	This class always returns an instance from fromRAccref; this means
	any resolution chain ends with it.  But it shouldn't be in
	PRODUCT_CLASSES in the first place since the fallback is
	hardcoded into getProductForRAccref.
	"""
	def __str__(self):
		return "<Invalid product %s>"%self.sourceSpec

	@classmethod
	def fromRAccref(cls, rAccref, grammar=None):
		return cls(rAccref.accref, "text/html")
	
	def _makeName(self):
		self.name = "invalid.html"
	
	def iterData(self):
		raise IOError("%s is invalid"%self.sourceSpec)


class RemoteProduct(ProductBase):
	"""A class for products at remote sites, given by their URL.
	"""
	def _makeName(self):
		self.name = urlparse.urlparse(self.sourceSpec
			).path.split("/")[-1] or "file"

	def __str__(self):
		return "<Remote %s at %s>"%(self.contentType, self.sourceSpec)
	
	def __eq__(self, other):
		return (isinstance(other, self.__class__) 
			and self.sourceSpec==other.sourceSpec)

	_schemePat = re.compile("(https?|ftp)://")

	@classmethod
	def fromRAccref(cls, rAccref, grammar=None):
		if cls._schemePat.match(rAccref.productsRow["accessPath"]):
			return cls(rAccref.productsRow["accessPath"], 
				rAccref.productsRow["mime"])

	def iterData(self):
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
	def __init__(self, sourceSpec, cutoutPars):
		ProductBase.__init__(self, sourceSpec, "image/fits")
		self.getfitsArgs = self._computeGetfitsArgs(cutoutPars)
	
	def _makeName(self):
		self.name = "cutout-"+os.path.basename(self.sourceSpec)

	def __str__(self):
		return "<FITS cutout of %s, (%fx%f)>"%(self.sourceSpec,
			self.cutoutPars[2], self.cutoutPars[3])

	def __eq__(self, other):
		return (isinstance(other, self.__class__) 
			and self.sourceSpec==other.sourceSpec
			and self.getfitsArgs==other.getfitsArgs)

	_myKeys = frozenset(["ra", "dec", "sra", "sdec"])

	@classmethod
	def fromRAccref(cls, rAccref, grammar=None):
		if len(set(rAccref.params.keys())&cls._myKeys)==4:
			if rAccref.productsRow["mime"]!="image/fits":
				raise base.ValidationError("Cannot generate cutouts for anything"
					" but FITS yet.", "accref")
			return cls(rAccref.localpath, rAccref.params)

	def _computeGetfitsArgs(self, params):
		"""returns a list of command line arguments for getfits to cut out
		the field specified in sqlPars from the image specified in item.
		"""
		ra, dec, sra, sdec = [params[key] for key in 
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
		prog = base.getBinaryName(os.path.join(base.getConfig("inputsDir"),
			"__system", "bin", "getfits"))
		return prog, self.getfitsArgs

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
	def __init__(self, sourceSpec, scale, contentType):
		ProductBase.__init__(self, sourceSpec, contentType)
		self.scale = pars["scale"]
	
	def __str__(self):
		return "<Scaled version of %s>"%(self.sourceSpec)

	@classmethod
	def fromRAccref(cls, rAccref, grammar=None):
		if rAccref.params.keys()==["scale"]:
			if rAccref.productsRow["mime"]!="image/fits":
				raise base.ValidationError("Cannot generate scaled versions"
					" for anything but FITS yet.", "accref")
			return cls(rAccref.localpath, rAccref.params["scale"], "image/fits")

	def _makeName(self):
		self.name = "scaled-"+os.path.basename(self.sourceSpec)

	def iterData(self):
		raise NotImplementedError("Cannot scale yet")

	def renderHTTP(self, ctx):
		request = inevow.IRequest(ctx)
		request.setHeader("content-type", self.contentType)
		return self._getDeferred(request, self.iterData())
# TODO: should we use web.streaming resp. producer/consumer here?
# If so: the product renderer should probably check if a product
# implements a producer interface and the act accordingly.

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


class DCCProduct(ProductBase):
	"""A class representing a product returned by a DC core.

	These products are constructed with a complete rAccref, which also
	becomes the product's sourceSpec.

	The source path of the rAccref's productsRow must have the form
	dcc://<rd.id>/<core id>?<coreAccref>; rd.id is the rd id with slashes
	replaced by dots.  This means this scheme doesn't work for RDs with ids
	containing dots, but you shouldn't do that in the first place.  coreAccref is
	just an opaque string that does not necessarily match the product's accref,
	but probably will in most cases.

	The context grammar receives a dictionary with the param dict, plus
	the coreAccref as accref.  The core must return an actual mime type 
	and a string.

	As a special service, iterData here can take a svcs.QueryMeta
	instance which, if given, is passed on to the core.
	
	See SDMCore for an example for how this can work.
	"""
	def __init__(self, rAccref):
		ProductBase.__init__(self, rAccref.productsRow["accessPath"], 
			rAccref.productsRow["mime"])
		self.params = rAccref.params
		self.name = os.path.basename(rAccref.productsRow["accref"])
		self._parseAccessPath()

	_schemePat = re.compile("dcc://")

	@classmethod
	def fromRAccref(cls, rAccref, grammar=None):
		if cls._schemePat.match(rAccref.productsRow["accessPath"]):
			return cls(rAccref)

	def _makeName(self):
		self.name = "untitled"  # set in the constructor
	
	def _parseAccessPath(self):
		# The scheme is manually handled to shoehorn urlparse into supporting
		# queries (and, potentially, fragments)
		if not self.sourceSpec.startswith("dcc:"):
			raise svcs.UnknownURI("DCC products can only be generated for dcc"
				" URIs")
		res = urlparse.urlparse(self.sourceSpec[4:])
		self.core = base.caches.getRD(
			res.netloc.replace(".", "/")).getById(res.path.lstrip("/"))
		self.accref = res.query

	def iterData(self, queryMeta=svcs.emptyQueryMeta):
		inData = self.params.copy()
		inData["accref"] = self.accref
		inputTable = rsc.TableForDef(self.core.inputTable)
		inputTable.setParams(inData, raiseOnBadKeys=False)
		self.contentType, data = self.core.run(self, inputTable, queryMeta)
		yield data
	
	def renderHTTP(self, ctx):
		return threads.deferToThread(self.iterData, 
			svcs.QueryMeta.fromContext(ctx)
		).addCallback(self._deliver, ctx)
	
	def _deliver(self, resultIterator, ctx):
		request = inevow.IRequest(ctx)
		request.setHeader("content-type", self.contentType)
		request.setHeader("content-disposition", 'attachment; filename="%s"'%
			str(self.name))
		return "".join(resultIterator)


# The following list is checked by getProductForRAccref in sequence.
# Each product is asked in turn, and the first that matches wins.
# So, ORDER IS ALL-IMPORTANT here.
PRODUCT_CLASSES = [
	NonExistingProduct,
	UnauthorizedProduct,
	RemoteProduct,
	DCCProduct,
	CutoutProduct,
	ScaledProduct,
	FileProduct,
]

def getProductForRAccref(rAccref, grammar=None):
	"""returns a product for a RAccref.

	This tries, in sequence, to make a product using each element
	of PRODUCT_CLASSES' fromRAccref method.  If nothing succeeds,
	it will return an InvalidProduct.
	"""
	for prodClass in PRODUCT_CLASSES:
		res = prodClass.fromRAccref(rAccref, grammar)
		if res is not None:
			return res
	return InvalidProduct.fromRAccref(rAccref, grammar)



class ProductIterator(grammars.RowIterator):
	"""A RowIterator turning RAccrefs to instances of subclasses of
	ProductBase.

	The source key is a list of RAccrefs, as, e.g., produced by
	the ProductCore.
	"""
	def _iterRows(self):
		for rAccref in self.sourceToken:
			yield {
				"source": getProductForRAccref(rAccref, self.grammar)
			}
		del self.grammar


class ProductsGrammar(grammars.Grammar):
	"""A grammar for "parsing" annotated RAccref to Product
	objects.

	The RAccref must have their product table rows in 
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

	It is instanciated from within //products.rd and relies on
	tables within that RD.

	The input data consists of accref; you can use the string form
	of RAccrefs, and if you renderer wants, it can pass in ready-made
	RAccrefs.  You can pass accrefs in through both an accref 
	param and table rows.  
	
	The accref param is the normal way if you just want to retrieve a single
	image, the table case is for building tar files and such.  There is one core
	instance in //products for each case.

	The core returns a table containing rows with the single column source.
	Each contains a subclass of ProductBase above.

	All this is so complicated because special processing may take place
	(user autorisation, cutouts, ...) but primarily because we wanted
	the tar generation to use this core.  Looking at the mess that's caused
	suggests that probably was the wrong decision.
	"""
	name_ = "productCore"

	def _getRAccrefs(self, inputTable):
		"""returns a list of RAccref requested within inputTable.
		"""
		keysList = [RAccref.fromString(r["accref"])
			for r in inputTable.rows if "accref" in r]
		try:
			param = inputTable.getParam("accref")
			if param is not None:
				keysList.append(RAccref.fromString(param))
		except base.NotFoundError: # "tar case", accrefs in rows
			pass
		return keysList

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

		dd = MS(rscdef.DataDescriptor, grammar=MS(ProductsGrammar,
				groups=authGroups),
			make=[MS(rscdef.Make, table=self.outputTable)])

		return rsc.makeData(dd, forceSource=self._getRAccrefs(inputTable))


class RAccref(object):
	"""A product key including possible modifiers.

	The product key is in the accref attribute.

	The modifiers come in the params dictionary.  It contains (typed)
	values, the possible keys of which are given in _buildKeys.  The
	values in passed in the inputDict constructor argument are parsed,
	anything not in _buildKeys is discarded.

	In principle, these modifiers are just the query part of a URL,
	and they generally come from the arguments of a web request.  However,
	we don't want to carry around all request args, just those meant
	for product generation.
	
	One major reason for having this class is serialization into URL-parts.
	Basically, stringifying a RAccref yields something that can be pasted
	to <server root>/getproduct to yield the product URL.  For the
	path part, this means just percent-escaping blanks, plusses and percents
	in the file name.  The parameters are urlencoded and appended with
	a question mark.  This representation is be parsed by the fromString
	function.

	RAccrefs have a (read only) property productsRow attribute -- that's 
	a dictionary containing the row for accres from //products#products
	if that exists.  If it doesn't, accessing the property will raise
	an NotFoundError.
	"""
	_buildKeys = dict((
		("dm", str),    # data model, VOTable generation
		("ra", float),  # cutouts
		("dec", float), # cutouts
		("sra", float), # cutouts
		("sdec", float),# cutouts
		("scale", int), # FITS scaling
	))

	def __init__(self, accref, inputDict={}):
		self.accref = accref
		self.params = self._parseInputDict(inputDict)
	
	@classmethod
	def fromPathAndArgs(cls, path, args):
		"""returns a rich accref from a path and a parse_qs-dictionary args.

		(it's mainly a helper for fromRequest and fromString).
		"""
		inputDict = {}
		for key, value in args.iteritems():
			if len(value)>0:
				inputDict[key] = value[-1]

		# Save old URLs: if no (real) path was passed, try to get it
		# from key.  Remove this ca. 2014, together with 
		# RaccrefTest.(testPathFromKey|testKeyMandatory)
		if not path.strip("/").strip():
			if "key" in inputDict:
				path = inputDict["key"]
			else:
				raise base.ValidationError(
					"Must give key when constructing RAccref",
					"accref")

		return cls(path, inputDict)

	@classmethod
	def fromRequest(cls, path, request):
		"""returns a rich accref from a nevow request.

		Basically, it raises an error if there's no key at all, it will return
		a (string) accref if no processing is desired, and it will return
		a RAccref if any processing is requested.
		"""
		return cls.fromPathAndArgs(path, request.args)


	@classmethod
	def fromString(cls, keyString):
		"""returns a fat product key from a string representation.

		As a convenience, if keyString already is a RAccref,
		it is returned unchanged.
		"""
		if isinstance(keyString, RAccref):
			return keyString

		qSep = keyString.rfind("?")
		if qSep!=-1:
			return cls.fromPathAndArgs(
				unquoteProductKey(keyString[:qSep]), 
				urlparse.parse_qs(keyString[qSep+1:]))

		return cls(unquoteProductKey(keyString))

	@property
	def productsRow(self):
		"""returns the row in dc.products corresponding to this RAccref's
		accref, or raises a NotFoundError.
		"""
		try:
			return self._productsRowCache
		except AttributeError:
			pt = getProductsTable()
			res = list(pt.iterQuery(pt.tableDef, "accref=%(accref)s", 
				{"accref": self.accref}))
			if not res:
				raise base.NotFoundError(self.accref, "accref", "product table",
					hint="Product URLs may disappear, though in general they should"
					" not.  If you have an ivo-id for the file you are trying to"
					" locate, you may still find it by querying the ivoa.obscore table"
					" using TAP and ADQL.")
			self._productsRowCache = res[0]
			return self._productsRowCache

	def __str__(self):
		# See the class docstring on quoting considerations.
		res = quoteProductKey(self.accref)
		args = urllib.urlencode(dict(
			(k,str(v)) for k, v in self.params.iteritems()))
		if args:
			res = res+"?"+args
		return res

	def __repr__(self):
		return str(self)

	def __eq__(self, other):
		return (isinstance(other, RAccref) 
			and self.params==other.params)

	def __ne__(self, other):
		return not self.__eq__(other)

	def _parseInputDict(self, inputDict):
		res = {}
		for key, val in inputDict.iteritems():
			if val is not None and key in self._buildKeys:
				try:
					res[key] = self._buildKeys[key](val)
				except (ValueError, TypeError):
					raise base.ValidationError(
						"Invalid value for constructor argument to %s:"
						" %s=%r"%(self.__class__.__name__, key, val), "accref")
		return res

	@property
	def localpath(self):
		try:
			return self._localpathCache
		except AttributeError:
			self._localpathCache = os.path.join(base.getConfig("inputsDir"), 
				self.productsRow["accessPath"])
		return self._localpathCache


def unquoteProductKey(key):
	"""reverses quoteProductKey.
	"""
	return urllib.unquote(key)


@utils.document
def quoteProductKey(key):
	"""returns key as getproduct URL-part.

	if key is a string, it is quoted as a naked accref so it's usable
	as the path part of an URL.  If it's an RAccref, it is just stringified.
	The result is something that can be used after getproduct in URLs
	in any case.
	"""
	if isinstance(key, RAccref):
		return str(key)
	return urllib.quote(key)
rscdef.addProcDefObject("quoteProductKey", quoteProductKey)


@utils.document
def makeProductLink(key, withHost=True):
	"""returns the URL at which a product can be retrieved.

	key can be an accref string or an RAccref
	"""
	url = base.makeSitePath("/getproduct/%s"%RAccref.fromString(key))
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
