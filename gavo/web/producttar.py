"""
Helper functions for producing tar files from tables containing
a product column.

Everything in this module expects the product interface, i.e., tables
must at least contain accref, owner, embargo, and accsize fields.
"""

# XXX TODO: shouldn't this be an output filter?  Or even a core?
# Of course, that would it make kind of hard to keep it in OutputOptions...

import cStringIO
import os
import tarfile
import tempfile
import time

from gavo import config
from gavo import datadef
from gavo import resourcecache
from gavo import sqlsupport
from gavo import table
from gavo.parsing import resource
from gavo.web import creds
from gavo.web import product


_tarGenFields = set(["key", "owner", "embargo", "accessPath"])

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
		yield baseName
		i = 1
		while True:
			yield "dc_data/%s-%03d%s"%(base, i, ext)
			i += 1

	def makeName(self, baseName):
		for name in self._buildNames(baseName):
			if name.lower() not in self.knownNames:
				self.knownNames.add(name)
				return name


class ProductTarMaker:
	""" is a factory for tar files.

	You probably don't want to instanciate it directly but instead get a copy
	through the getProductMaker function below.

	Then call getTarFileName with the coreResult of a query, and you'll 
	receive a file name containing the desired tar file.
	"""
	def __init__(self):
		self.rd = resourcecache.getRd("__system__/products/products")
		self.items = [f for f in self.rd.getTableDefByName("products").get_items()
			if f.get_dest() in _tarGenFields]
		self.dd = resource.makeRowsetDataDesc(self.rd, self.items)
		f = self.dd.get_Semantics().get_recordDefs()[0].get_items()[3]

	def _getProducts(self, table):
		"""returns a list of product keys and sizes for products present in table.
		"""
		return [row["accref"] for row in table.rows if row["accref"]]

	def _resolveProductKeys(self, keyList):
		"""returns a list of paths to products from a list as returned by
		_getProducts.
		"""
		sq = sqlsupport.SimpleQuerier()
# We currently have a bit of an encoding mess in the various databases,
# so pull the strings down to bytestring.  Don't use non-ascii chars
# in your filenames...
		keyList = [str(k) for k in keyList]
		return resource.InternalDataSet(self.dd, table.Table, sq.query(
			"SELECT %s FROM products WHERE key IN %%(keys)s"%(
					", ".join([f.get_dest() for f in self.items])),
			{"keys": keyList}).fetchall())

	def _getEmbargoedFile(self, name):
		stuff = cStringIO.StringIO("This file is embargoed.  Sorry.\n")
		b = tarfile.TarInfo(name)
		b.size = len(stuff.getvalue())
		b.mtime = time.time()
		return b, stuff

	def _writeTar(self, productData, allowedGroups):
		"""actually writes the tar.

		allowedGroups should be a set of groups the currently logged in user
		belongs to.
		"""
		handle, fName = tempfile.mkstemp(".tar")
		nameGen = UniqueNameGenerator()
		outputTar = tarfile.TarFile(fName, "w")
		os.close(handle)
		for prodRec in productData.getPrimaryTable():
			targetName = nameGen.makeName(os.path.basename(prodRec["accessPath"]))
			if (not product.isFree(prodRec) and 
					prodRec["owner"] not in allowedGroups):
				outputTar.addfile(*self._getEmbargoedFile(targetName))
			else:
				outputTar.add(os.path.join(config.get("inputsDir"), 
					prodRec["accessPath"]), targetName)
		outputTar.close()
		return fName

	def _getGroups(self, user, password):
		if user==None:
			return set()
		else:
			return creds.getGroupsForUser(user, password, async=False)

	def getTarFile(self, coreResult, user, password):
		"""returns a deferred firing the name of a tar file containing 
		all accessible products in coreResult's primary table.

		All errors must be handled upstream.

		The caller is responsible for cleaning up the file if no error occurred.

		If you're not after protected resources, you can pass None as user
		and password.
		"""
		return self._writeTar(
			self._resolveProductKeys(self._getProducts(
				coreResult.getPrimaryTable())),
			self._getGroups(user, password))


_tarmaker = None

def getTarMaker():
	global _tarmaker
	if _tarmaker is None:
		_tarmaker = ProductTarMaker()
	return _tarmaker
