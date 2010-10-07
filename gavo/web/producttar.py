"""
Helper functions for producing tar files from tables containing
a product column.

Everything in this module expects the product interface, i.e., tables
must at least contain accref, owner, embargo, and accsize fields.
"""

# XXX TODO: this should eventually become a renderer on the product core,
# redirected to from the current TarResponse.

from cStringIO import StringIO
import os
import tarfile
import tempfile
import time
import urllib

from gavo import base
from gavo import grammars
from gavo import rsc
from gavo import rscdef
from gavo import svcs
from gavo.protocols import products
from gavo.web import streaming


MS = base.makeStruct


class UniqueNameGenerator:
	"""is a factory to build unique file names from possibly ambiguous ones.

	If the lower case of a name is not known to an instance, it just returns
	that name.  Otherwise, it disambiguates by adding characters in front
	of the extension.
	"""
	def __init__(self):
		self.knownNames = set()

	def _buildNames(self, baseName):
		base, ext = os.path.splitext(baseName)
		yield "dc_data/%s%s"%(base, ext)
		i = 1
		while True:
			yield "dc_data/%s-%03d%s"%(base, i, ext)
			i += 1

	def makeName(self, baseName):
		for name in self._buildNames(baseName):
			if name.lower() not in self.knownNames:
				self.knownNames.add(name)
				return str(name)


class ColToRowIterator(grammars.RowIterator):
	"""is a RowIterator for ColToRowGrammars.

	A hacky feature is that a ColToRowIterator will not return the same
	row twice.  This is a convenience for TarMakers to keep them from
	tarring in identical files that somehow manage to be mentioned more
	than once in a result table.
	"""
	def __init__(self, *args, **kwargs):
		grammars.RowIterator.__init__(self, *args, **kwargs)
		self.seenKeys = set()

	def _iterRows(self):
		for row in self.sourceToken:
			for key in self.grammar.sourceKeys:
				if row.get(key):
					accref = row[key]
					# this is a service for "rich" product displays that
					# select more than one row: if we have a list (SQL array)
					# extract the first element and use that as access key
					if isinstance(accref, list):
						accref = accref[0]
					# The str below is for product.CutoutProductKeys
					if str(accref) not in self.seenKeys:
						yield {self.grammar.targetKey: accref}
						self.seenKeys.add(str(accref))


class ColToRowGrammar(grammars.Grammar):
	"""is a grammar that selects some columns and returns each of them
	as a row with a specified key.

	This is useful to extract all products from tables that can have
	multiple columns carrying products.

	The input is a sequence of dictionaries (i.e., Table rows).
	"""

	rowIterator = ColToRowIterator

	_targetKey = base.UnicodeAttribute("targetKey", default=base.Undefined,
		description="Name of the target columns")
	_sourceKeys = base.ListOfAtomsAttribute("sourceKeys",
		description="Names of the source columns.", 
		itemAttD=base.UnicodeAttribute("sourceKey"))


class ProductTarMaker(object):
	""" is a factory for tar files.

	You probably don't want to instanciate it directly but instead get a copy
	through the getProductMaker function below.

	The main entry point to this class is deliverProductTar.
	"""
	def __init__(self):
		self.rd = base.caches.getRD("__system__/products")
		self.core = self.rd.getById("forTar")
		self.inputDD = self.core.inputDD.copy(None)
		self.inputDD.grammar = base.makeStruct(
			rscdef.getGrammar("dictlistGrammar"))

	def _getEmbargoedFile(self, name):
		stuff = StringIO("This file is embargoed.  Sorry.\n")
		b = tarfile.TarInfo(name)
		b.size = len(stuff.getvalue())
		b.mtime = time.time()
		return b, stuff

	def _getTarInfoFromProduct(self, prod, name):
		"""returns a tar info from a general products.PlainProduct instance
		prod.

		This is relatively inefficient for data that's actually on disk,
		so you should only use it when data is being computed on the fly.
		"""
		assert not isinstance(prod, products.UnauthorizedProduct)
		stuff = StringIO()
		prod(stuff)
		stuff.seek(0)
		b = tarfile.TarInfo(name)
		b.size = len(stuff.getvalue())
		b.mtime = time.time()
		return b, stuff

	def _getHeaderVals(self, queryMeta):
		if queryMeta.get("Overflow"):
			return "truncated_data.tar", "application/x-tar"
		else:
			return "data.tar", "application/x-tar"

	def _productsToTar(self, productData, destination):
		"""actually writes the tar.
		"""
		nameGen = UniqueNameGenerator()
		outputTar = tarfile.TarFile.open("data.tar", "w|", destination)
		for prodRec in productData.getPrimaryTable():
			src = prodRec["source"]
			if isinstance(src, products.NonExistingProduct):
				continue # just skip files that somehow don't exist any more
			if src.sourcePath:  # actual file in the file system
				targetName = nameGen.makeName(os.path.basename(src.sourcePath))
				if isinstance(src, products.UnauthorizedProduct):
					outputTar.addfile(*self._getEmbargoedFile(targetName))
				else:
					outputTar.add(str(src.sourcePath), str(targetName))
			else: # anything else is read from the src
				outputTar.addfile(*self._getTarInfoFromProduct(src,
					nameGen.makeName(os.path.basename(src.fullFilePath))))
		outputTar.close()
		return ""  # finish off request if necessary.

	def _streamOutTar(self, productData, request, queryMeta):
		name, mime = self._getHeaderVals(queryMeta)
		request.setHeader('content-disposition', 
			'attachment; filename=%s'%name)
		request.setHeader("content-type", mime)

		def writeTar(dest):
			self._productsToTar(productData, dest)
		return streaming.streamOut(writeTar, request)

	def deliverProductTar(self, coreResult, request, queryMeta):
		"""causes a tar containing all accrefs mentioned in coreResult
		to be streamed out via request.
		"""
		table = coreResult.original.getPrimaryTable()
		productColumns = table.tableDef.getProductColumns()
		if not productColumns:
			raise base.ValidationError("This query does not select any"
				" columns with access references", "_OUTPUT")
		inputDD = MS(svcs.InputDescriptor, 
			grammar= MS(ColToRowGrammar, targetKey="key",
				sourceKeys=productColumns),
			makes=MS(rscdef.Make, table=self.rd.getById("pCoreInput")))
		inputData = rsc.makeData(inputDD, forceSource=table.rows)
		if not inputData.getPrimaryTable().rows:
			raise base.ValidationError("No products selected", colName="query")
		prods = self.core.run(coreResult.service, inputData, queryMeta)
		return self._streamOutTar(prods, request, queryMeta)


_tarmaker = None

def getTarMaker():
	global _tarmaker
	if _tarmaker is None:
		_tarmaker = ProductTarMaker()
	return _tarmaker
