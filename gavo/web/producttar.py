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

from gavo import base
from gavo import grammars
from gavo import rsc
from gavo.protocols import products
from gavo.web import streaming


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
				return name


class ProductTarMaker(object):
	""" is a factory for tar files.

	You probably don't want to instanciate it directly but instead get a copy
	through the getProductMaker function below.

	You call writeProductTar(matchedRows, queryMeta, destination), 
	which then will:

	* extract the accrefs from matchedRows, raising a ValidationError on
	  _OUTPUT if the accref column is missing,
	* make an input data set containing only the accrefs,
	* pass that to the product core,
	* evaluate the result of the product core to add the files to a tar
	  archive that is written to destination,
	"""
	def __init__(self):
		self.rd = base.caches.getRD("__system__/products")
		self.core = self.rd.getById("forTar")
		self.inputDD = self.core.inputDD.copy(None)
		self.inputDD.grammar = base.makeStruct(grammars.DictlistGrammar)

	def _getEmbargoedFile(self, name):
		stuff = StringIO("This file is embargoed.  Sorry.\n")
		b = tarfile.TarInfo(name)
		b.size = len(stuff.getvalue())
		b.mtime = time.time()
		return b, stuff

	def _getTarInfoFromProduct(self, prod, name):
		"""returns a tar info from a general products.PlainProduct instance
		prod.

		This is relatively inefficient for data that's actuall on disk,
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

		allowedGroups should be a set of groups the currently logged in user
		belongs to.
		"""
		nameGen = UniqueNameGenerator()
		outputTar = tarfile.TarFile("data.tar", "w", destination)
		for prodRec in productData.getPrimaryTable():
			src = prodRec["source"]
			if isinstance(src, products.NonExistingProduct):
				continue # just skip files that somehow don't exist any more
			if src.sourcePath:  # actual file in the file system
				targetName = nameGen.makeName(os.path.basename(src.sourcePath))
				if isinstance(src, products.UnauthorizedProduct):
					outputTar.addfile(*self._getEmbargoedFile(targetName))
				else:
					outputTar.add(src.sourcePath, targetName)
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
		if "accref" not in table.tableDef.columns:
			raise base.ValidationError("This query does not select any"
				" columns with access references", "_OUTPUT")
		inputData = rsc.makeData(self.inputDD, forceSource=table.rows)
		prods = self.core.run(coreResult.service, inputData, queryMeta)
		return self._streamOutTar(prods, request, queryMeta)


_tarmaker = None

def getTarMaker():
	global _tarmaker
	if _tarmaker is None:
		_tarmaker = ProductTarMaker()
	return _tarmaker
