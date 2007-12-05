"""
This module contains utility classes for resource parsing.
"""

import os
import re
import time
import weakref

from gavo import config
from gavo import coords
from gavo import utils
import gavo


class RowFunction:
	"""is something that operates on table rows.

	Macros and RowProcessors are RowFunctions.

	Implementing classes have to define a method _compute taking
	a rowdict and keyword arguments.  The names of these arguments
	have to be defined in calls to the addArgument(name, src, val)
	method (or addArguments).  If src is given, the value of the
	argument is that taken from the corresponding field in the record,
	otherwise the argument is constant val.

	When a row function is called together with a rowdict, RowFunction
	will compute the named arguments (including @-expansions) and
	then call _compute with the requested arguments.  It returns
	whatever _compute returns.
	"""

	def __init__(self, argTuples=[]):
		self.colArguments = []
		self.constants = []
		self.addArguments(argTuples)

	@staticmethod
	def getName():
		return "Uncallable abstract row function"

	def addArgument(self, argName, srcName=None, value=None):
		"""adds an argument that is filled from a field of current record.

		There are two calling conventions here for historical reasons:
		Either you give the name of the argument, the name of the source
		field and a constant value separately (with None for the source
		field to use value), or you pass one tuple with the complete information.
		"""
		if isinstance(argName, tuple):
			argName, srcName, value = argName
		if srcName:
			self.colArguments.append((argName.encode("ascii"), srcName))
		else:
			self.constants.append((argName.encode("ascii"), value))

	def addArguments(self, argTuples):
		"""adds arguments from the sequence argTuples.

		An element of argTriples has to be valid as arguments for the
		addArgument method.
		"""
		for args in argTuples:
			self.addArgument(*args)
	
	def _buildArgDict(self, atExpand, rowdict):
		args = {}
		for name, src in self.colArguments:
			if src[0]=="@":
				args[name] = rowdict.get(atExpand(src, rowdict))
			else:
				args[name] = rowdict.get(src)
		for name, val in self.constants:
			if val[0]=="@":
				args[name] = atExpand(val, rowdict)
			else:
				args[name] = val
		return args

	def getArgument(self, argName):
		"""returns source or value for the argument called argName.

		This is mainly for introspection of macros, which again should only
		be necessary for error handling.

		If the argument doesn't exist, a KeyError is raised.
		"""
		for name, val in self.colArguments:
			if name==argName:
				return val
		for name, val in self.constants:
			if name==argName:
				return val
		raise KeyError("No argument named %s"%argName)

	def __call__(self, atExpand, rowdict):
		try:
			return self._compute(rowdict, **self._buildArgDict(atExpand, rowdict))
		except Exception, msg:
			if hasattr(self, "errorField"):
				utils.raiseTb(gavo.ValidationError, str(msg), 
					self.getArgument(self.errorField))
			else:
				raise


class RDComputer:
	"""is a container computing values of @-expansions.

	The idea is that you can say "@bla, par" in some attribute values,
	and whatever processes this will replace it with the result of
	fc_bla(rowdict, par).

	The RDComputer can substitute "general" values global to the
	resource descriptor, like the current date, the root path of
	the resource, the schema name.

	To define new field computing functions, just add a method
	named _fc_<your name> receiving the row dictionary and possibly
	further string arguments (separated with commas in the call)
	in this class.  If you deperately need to, you can do this on
	instanciated RDComputers.
	"""
	def __init__(self, rd):
		self.rd = rd

	def compute(self, cfname, rows, *args):
		return getattr(self, "_fc_"+cfname)(rows, *args)

	def _fc_today(self, rows):
		"""returns the current date.

		This is available in general @-expansions.
		"""
		return time.strftime("%Y-%m-%d")

	def _fc_schemaq(self, rows, tableName):
		"""returns the argument qualified with the resource's schema.

		This is available in general @-expansions.
		"""
		return "%s.%s"%(self.rd.get_schema(),
			tableName)

	def _getRelativePath(self, fullPath, rootPath):
		"""returns rest if fullPath has the form rootPath/rest and raises an
		exception otherwise.
		"""
		if not fullPath.startswith(rootPath):
			raise Error("Full path %s does not start with resource root %s"%
				(fullPath, rootPath))
		return fullPath[len(rootPath):].lstrip("/")

	def _fc_inputRelativePath(self, rows):
		"""returns the current source's path relative to inputsDir
		(or raises an error if it's not from there).

		This is available in general @-expansions.
		"""
		fullPath = self.context.sourceName
		rootPath = config.get("inputsDir")
		return self._getRelativePath(fullPath, rootPath)

	def _fc_rdId(self, rows):
		"""returns the id of the resource descriptor.

		This is the input-relative path of the rd source file, minus any
		extensions.
		"""
		return self.rd.sourceId

	def _fc_attr(self, rows, attName):
		"""returns the attribute attName of the resource descriptor.

		This is a last-resort affair if some program needs to smuggle in data
		through a resource descriptor.  One example is the service list in
		which you need to know what resource descriptor you operate on.

		Don't use it.  The properties on data desriptors are a slightly
		more structured way to achieve most of what this could do.
		"""
# Clearly, this is a bad hack -- just don't use it.
		return getattr(self.rd, attName)

	def _fc_property(self, rows, property):
		"""returns the named property of the data descriptor.

		Properties can be set using the property element or the register_property
		method (but don't modify data descriptors you got from the cache...)
		"""
		return self.rd.get_property(property)


class FieldComputer(RDComputer):
	"""is a container for various functions computing field values.

	The FieldComputer works like an RDComputer except that it is bound
	to a parse context. Through it, it can access the full grammar
	and the full semantics, so you should be able to compute quite
	a wide range of values.
	"""
	def __init__(self, parseContext):
		if parseContext==None:
			# This is for the benefit of doc generation.  A FieldComputer without
			# resource descriptor is pretty useless anywhere else.
			RDComputer.__init__(self, None)
			self.context = None
		else:
			RDComputer.__init__(self, parseContext.getDataSet().
				getDescriptor().getRD())
			self.context = weakref.proxy(parseContext)

	def _fc_property(self, rows, property):
		"""returns the named property of the data descriptor.

		Properties can be set using the property element or the register_property
		method (but don't modify data descriptors you got from the cache...)
		"""
		return self.context.getDescriptor.get_property(property)

	def _fc_srcstem(self, rows):
		"""returns the stem of the source file currently parsed.
		
		Example: if you're currently parsing /tmp/foo.bar, the stem is foo.
		"""
		return os.path.splitext(os.path.basename(self.context.sourceName))[0]

	def _fc_lastSourceElements(self, rows, numElements):
		"""returns the last numElements items of the current source's path.
		"""
		newPath = []
		fullPath = self.context.sourceName
		for i in range(int(numElements)):
			fullPath, part = os.path.split(fullPath)
			newPath.append(part)
		newPath.reverse()
		return os.path.join(*newPath)

	def _fc_rootlessPath(self, rows):
		"""returns the the current source's path with the resource descriptor's
		root removed.
		"""
		fullPath = self.context.sourceName
		rootPath = self.rd.get_resdir()
		return self._getRelativePath(fullPath, rootPath)

	def _fc_inputSize(self, rows):
		"""returns the size of the current source.
		"""
		fullPath = self.context.sourceName
		return os.path.getsize(fullPath)

	def _fc_docField(self, rows, fieldName):
		"""returns the value of the field fieldName in the document record.
		"""
		return self.context.getData().getDocRec()[fieldName]

	def getDocs(self, underliner):
		docItems = []
		for name in dir(self):
			if name.startswith("_fc_"):
				docItems.append((name[4:], getattr(self, name).__doc__))
		return utils.formatDocs(docItems, underliner)


def atExpand(val, rowdict, fieldComputer):
	"""expands computed fields.

	If val is a string and starts with an @, the rest is passed to
	computeFunc (which mostly is the compute method of a FieldComputer
	instance), the value of which is returned, unless val starts with
	two @ signs, in which case the first of these ats is stripped
	(poor man's escaping).	Other values are returned unchanged.
	"""
	if not isinstance(val, basestring):
		return val
	if val.startswith("@@"):
		return val[1:]
	if val.startswith("@"):
		desc = val[1:].split(",")
		if not desc[-1].strip():
			del desc[-1]
		return fieldComputer.compute(desc[0], rowdict, *desc[1:])
	return val


def parseCooPair(soup):
	"""returns a pair of RA, DEC floats if they can be made out in soup
	or raises a value error.

	No range checking is done (yet), i.e., as long as two numbers can be
	made out, the function is happy.

	>>> parseCooPair("23 12")
	(23.0, 12.0)
	>>> parseCooPair("3.75 -12.125")
	(3.75, -12.125)
	>>> parseCooPair("3 25,-12 30")
	(51.25, -12.5)
	>>> map(str, parseCooPair("12 15 30.5 +52 18 27.5"))
	['183.877083333', '52.3076388889']
	>>> parseCooPair("3.39 -12 39")
	Traceback (most recent call last):
	ValueError: Invalid hourangle with sepchar ' ': '3.39'
	>>> parseCooPair("12 15 30.5 +52 18 27.5e")
	Traceback (most recent call last):
	ValueError: 12 15 30.5 +52 18 27.5e has no discernible position in it
	>>> parseCooPair("QSO2230+44.3")
	Traceback (most recent call last):
	ValueError: QSO2230+44.3 has no discernible position in it
	"""
	soup = soup.strip()

	def parseFloatPair(soup):
		mat = re.match("(%s)\s*[\s,/]\s*(%s)$"%(gavo.floatRE, gavo.floatRE),
			soup)
		if mat:
			return float(mat.group(1)), float(mat.group(2))

	def parseHourangleDms(soup):
		hourangleRE = r"(?:\d+\s+)?(?:\d+\s+)?\d+(?:\.\d*)?"
		dmsRE = "[+-]?\s*(?:\d+\s+)?(?:\d+\s+)?\d+(?:\.\d*)?"
		mat = re.match("(%s)\s*[\s,/]?\s*(%s)$"%(hourangleRE, dmsRE), soup)
		if mat:
			try:
				return coords.hourangleToDeg(mat.group(1)), coords.dmsToDeg(
					mat.group(2))
			except gavo.Error, msg:
				raise ValueError(str(msg))

	for func in [parseFloatPair, parseHourangleDms]:
		res = func(soup)
		if res:
			return res
	raise ValueError("%s has no discernible position in it"%soup)


def _test():
	import doctest, parsehelpers
	doctest.testmod(parsehelpers)


if __name__=="__main__":
	import sys
	if len(sys.argv)>1 and sys.argv[1]=="docs":
		underliner = "."
		if len(sys.argv)>2:
			underliner = sys.argv[2]
		print FieldComputer(None).getDocs(underliner)
	else:
		_test()
