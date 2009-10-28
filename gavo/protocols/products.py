"""
The products interface, including a core to make the product renderer almost
trivial.
"""

import cgi
import datetime
import md5
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
from gavo.protocols import creds
from gavo.utils import fitstools

MS = base.makeStruct


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
# XXX it was probably a bad idea to use __call__ for something like write.
# A well.
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
	def __init__(self, sourcePath, cutoutPars, contentType):
		self.fullFilePath = sourcePath
		self.cutoutPars = cutoutPars
		if contentType!="image/fits":
			raise NotImplementedError("Cannot generate cutouts for anything"
				" but FITS yet.")
		PlainProduct.__init__(self, None, contentType)

	def __str__(self):
		return "<FITS cutout of %s, (%fx%f)>"%(sourcePath,
			self.cutoutPars[2], self.cutoutPars[3])
	
	def __call__(self, outFile):
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


class ProductIterator(grammars.RowIterator):
	"""is an iterator over product rows.

	The source key is a pair of (parsedKeys, key mapping), where
	key mapping maps the access key to the product table info about
	the file.
	"""
	def _makeProductForRow(self, row, dbRow):
		"""returns the proper PlainProduct subclass for an image described by
		the parsed key row and the product table row dbRow.
		"""
		sourcePath = os.path.join(base.getConfig("inputsDir"), dbRow["accessPath"])
		if row["sra"]:
			rsc = CutoutProduct(sourcePath, row, dbRow["mime"])
		else:
			rsc = PlainProduct(sourcePath, dbRow["mime"])
		if dbRow["embargo"] is not None and dbRow["embargo"]>self.grammar.now:
			if dbRow["owner"] not in self.grammar.groups:
				rsc = UnauthorizedProduct(sourcePath)
		return rsc

	def _iterRows(self):
		parsedKeys, productMap = self.sourceToken
		for row in parsedKeys.rows:
			try:
				prodRow = productMap.getRow(row["key"])
			except KeyError:
				rsc = NonExistingProduct(row["key"])
			else:
				rsc = self._makeProductForRow(row, prodRow)
			yield {
				"source": rsc,
			}
		del self.grammar


class ProductsGrammar(grammars.Grammar):
	"""is a grammar for parsing raw DB results and parsed keys into 
	delivery records.

	It's a bit hard doing the things that need to be done with procs,
	hence this custom grammar.
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

	* the actual query, 
	* access validation (i.e., makes sure the user has access to the product), 
	* cutout processing (via a special construct deferring cutouts until they
	  are needed)

	The rd it is constructed with must contain a table named products
	with at least the fields this table has in products.rd (so,
	it probably should always be __system__/products.rd).

	In case of cutouts, the database sees the naked accrefs and
	resolves them to file system paths.  These are then combined
	with the parsed keys table in the grammar to form the objects
	returned to the renderer.
	"""
	name_ = "productCore"

	def onParentComplete(self):
		self.queryResultDef = svcs.OutputTableDef.fromTableDef(
			self.rd.getById("products"))

	def _parseKeys(self, keys):
		"""returns an iterator over dictionaries of parsed fields of the 
		(possibly cut-out) product keys in keys.

		These may have cutout specs.  None items in keys are dropped.
		"""
		for key in keys:
			if key is not None:
				yield dict(cgi.parse_qsl("key="+key))

	def _getSQLWhere(self, inputData):
		"""returns a query string fragment and the parameters
		to query the DB for the access paths for the input keys.

		In addition, the function will return a keysTable
		containing a "parsed" keys (i.e., (key, ra, dec, sra,
		sdec) for cutouts.  This key table is later the real
		input for the ProductsGrammar.
		"""
		keys = [r["key"] for r in inputData.getPrimaryTable().rows
			if "key" in r]
		keysTableDef = self.rd.getById("parsedKeys")
		keysTable = rsc.makeTableFromRows(keysTableDef, 
			self._parseKeys(keys))
		if not keys: # stupid SQL doesn't know the empty set
			return keysTable, "FALSE", {}
		return keysTable, "key IN %(keys)s", {"keys": set(r["key"] 
			for r in keysTable.rows)}

	def _getGroups(self, user, password):
		if user is None:
			return set()
		else:
			return creds.getGroupsForUser(user, password)

	def run(self, service, inputData, queryMeta):
		"""returns a data set containing sources for the keys mentioned in
		inputData's primary table.

		Errors while retrieving auth info will be ignored and translated
		as no groups.
		"""
		authGroups = self._getGroups(queryMeta["user"], queryMeta["password"])
		keysTable, where, pars = self._getSQLWhere(inputData)
		prodTable = rsc.TableForDef(self.queriedTable)
		resTable = rsc.makeTableForQuery(prodTable, self.queryResultDef, 
			where, pars, suppressIndex=False)

		dd = MS(rscdef.DataDescriptor, grammar=MS(ProductsGrammar,
				groups=authGroups),
			make=[MS(rscdef.Make, table=self.outputTable)])
		return rsc.makeData(dd, forceSource=(keysTable, resTable))

svcs.registerCore(ProductCore)


########## Finally, the product interface (the above core is used in the
########## rd, so this must be defined later that the registerCore)

class ProductRMixin(rscdef.RMixinBase):
	"""A mixin for tables containing "products".

	A "product" here is some kind of binary, typically a FITS file.
	The table receives the columns accref, accsize, owner, and embargo
	(which is defined in __system__/products#prodcolUsertable).

	owner and embargo let you introduce access control.  Embargo is a
	date at which the product will become publicly available.  As long
	as this date is in the future, only authenticated users belonging to
	the *group* owner are allowed to access the product.

	In addition, the mixin arranges for the products to be added to the
	system table products, which is important when delivering the files.

	Tables mixing this in should be fed from grammars using the defineProduct
	rowgen.
	"""
	name = "products"

	def __init__(self):
		rscdef.RMixinBase.__init__(self, "__system__/products", "productColumns")
	
	def processLate(self, tableDef):
		# find all DDs referencing tableDef and add a maker for the products
		# table to them.  Then, fiddle the mappings for productColumns into 
		# the table's rowmaker
		if not tableDef.onDisk:
			raise base.StructureError("Tables mixing in product must be"
				" onDisk, but %s is not"%tableDef.id)
		for dd in tableDef.rd.iterDDs():
			for td in dd:
				if td.id==tableDef.id:
					dd._makes.feedObject(dd, rscdef.Make(dd, 
						table=self.rd.getTableDefById("products"),
						rowmaker=self.rd.getById("productsMaker")))
			for make in dd.makes:
				if make.table.id==tableDef.id:
					make.rowmaker.feedFrom(self.rd.getById("prodcolUsertable"))


rscdef.registerRMixin(ProductRMixin())


@utils.document
def quoteProductKey(key):
	"""URL-quotes product keys.

	Actually, it url quotes any string, but the plus handling we have
	here is particularly important for product keys.
	"""
	return urllib.quote_plus(key.replace("+", "%2B"))
rscdef.addRmkFunc("quoteProductKey", quoteProductKey)


@utils.document
def makeProductLink(key, withHost=True):
	"""returns the URL at which a product can be retrieved.
	"""
	url = base.makeSitePath("/getproduct?key=%s"%quoteProductKey(key))
	if withHost:
		url = urlparse.urljoin(base.getConfig("web", "serverURL"), url)
	return url
rscdef.addRmkFunc("makeProductLink", makeProductLink)
