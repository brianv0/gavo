"""
This module contains various helper functions and classes for processing
GAVO resources.
"""

import copy
import datetime
import math
import os
import re
import shutil
import sys
import tempfile
import time


from mx import DateTime

import gavo
from gavo import logger


class Error(gavo.Error):
	pass


def _iterDerivedClasses(baseClass, objects):
	"""iterates over all subclasses of baseClass in the sequence objects.
	"""
	for cand in objects:
		try:
			if issubclass(cand, baseClass) and cand is not baseClass:
				yield cand
		except TypeError:  # issubclass wants a class
			pass


def buildClassResolver(baseClass, objects, instances=False):
	"""returns a function resolving classes deriving from baseClass
	in the sequence objects by their names.

	This is used to build registries of Macros and RowProcessors.  The
	classes in question have to have a name attribute.

	objects would usually be something like globals().values()

	If instances is True the function will return instances instead
	of classes.
	"""
	registry = {}
	for cls in _iterDerivedClasses(baseClass, objects):
		if instances:
			registry[cls.name] = cls()
		else:
			registry[cls.name] = cls
	def resolve(name, registry=registry):
		return registry[name]
	return resolve


def formatDocs(docItems, underliner):
	"""returns RST-formatted docs for docItems.

	docItems is a list of (title, doc) tuples.  doc is currently
	rendered in a preformatted block.
	"""
	def formatDocstring(docstring):
		"""returns a docstring with a consistent indentation.

		Rule (1): any whitespace in front of the first line is discarded.
		Rule (2): if there is a second line, any whitespace at its front
		  is the "governing whitespace"
		Rule (3): any governing whitespace in front of the following lines
		  is removed
		Rule (4): All lines are indented by 2 blanks.
		"""
		lines = docstring.split("\n")
		newLines = [lines.pop(0).lstrip()]
		if lines:
			whitespacePat = re.compile("^"+re.match(r"\s*", lines[0]).group())
			for line in lines:
				newLines.append(whitespacePat.sub("", line))
		return "  "+("\n  ".join(newLines))

	docLines = []
	for title, body in docItems:
		docLines.extend([title, underliner*len(title), "", "::", "",
			formatDocstring(body), ""])
	docLines.append("\n.. END AUTO\n")
	return "\n".join(docLines)


def makeClassDocs(baseClass, objects):
	"""prints hopefully RST-formatted docs for all subclasses
	of baseClass in objects.

	The function returns True if it finds arguments it expects ("docs"
	and optionally a char to build underlines from) in the command line,
	False if not (and it doesn't print anything in this case) if not.

	Thus, you'll usually use it like this:

	if __name__=="__main__":	
		if not utils.makeClassDocs(Macro, globals().values()):
			_test()
	"""
	if len(sys.argv) in [2,3] and sys.argv[1]=="docs":
		if len(sys.argv)==3:
			underliner = sys.argv[2][0]
		else:
			underliner = "."
	else:
		return False
	docs = []
	for cls in _iterDerivedClasses(baseClass, objects):
		try:
			title = cls.name
		except AttributeError:
			title = cls.__name__
		docs.append((title, cls.__doc__))
	docs.sort()
	print formatDocs(docs, underliner)
	return True


def fixIndentation(code, newIndent):
	"""returns code with all whitespace from the first line removed from
	every line and newIndent prepended to every line.
	"""
	codeLines = [line for line in code.split("\n") if line.strip()]
	firstIndent = re.match("^\s*", codeLines[0]).group()
	fixedLines = []
	for line in codeLines:
		if line[:len(firstIndent)]!=firstIndent:
			raise Error("Bad indent in line %s"%repr(line))
		fixedLines.append(newIndent+line[len(firstIndent):])
	return "\n".join(fixedLines)


class DummyClass:
	"""is a class that just prints out all method calls with their arguments.

	>>> l = DummyClass()
	Dummy class instantiated: () {}
	>>> l.foo()
	Called foo, (), {}
	>>> l.baz(1, 2, 3)
	Called baz, (1, 2, 3), {}
	>>> l.bar(2, val=3)
	Called bar, (2,), {'val': 3}
	"""
	def __init__(self, *args, **kwargs):
		print "Dummy class instantiated:", args, kwargs

	def __getattr__(self, key):
		return lambda *args, **kwargs: sys.stdout.write("Called %s, %s, %s\n"%(
			key, args, kwargs))


class Conversions:
	"""is a container for converters from parsed literals to python
	values.

	A converter has the signature

	convert_to_type(val) -> val_of_type

	It must be a no-op if val already has type.  They should accept
	strings as val, and they must return a value of their promised
	type or raise an exception.

	We should support the standard VOTable types here.  XXX missing:
	bit, range checking for integer types, complex numbers XXX

	In addition, we do Strings (XXX think about distinction of
	unicode and bytestrings).

	This is a singleton class that should not be instanciated but
	instead be accessed through the convert class method.

	The conversions themselves are used without binding, thus no "self"
	argument.
	"""
	def _convertToFloat(val):
		if val.startswith("+"):
			val = val[1:]
		return float(val.replace(" ", ""))

	def _convertToInt(val):
		return int(val)
	
	def _convertToBoolean(val):
		return bool(val)

	def _convertToString(val):
		return str(val)

	def _convert(self, type, val, nullvalue):
		if val==nullvalue:
			return None
		else:
			return self.registry[type](val)

	@classmethod
	def convert(cls, targetType, val, nullvalue):
		instance = cls()
		cls.convert = instance._convert
		return instance.convert(targetType, val, nullvalue)

	registry = {
		"float": _convertToFloat,
		"double": _convertToFloat,
		"int": _convertToInt,
		"short": _convertToInt,
		"long": _convertToInt,
		"unsignedByte": _convertToInt,
		"str": _convertToString,
	}


class NameMap:
	"""is a name mapper fed from a simple text file.

	The text file format simply is:

	<target-id> "TAB" <src-id>{whitespace <src-id>}

	src-ids have to be encoded quoted-printable when they contain whitespace
	or other "bad" characters ("="!).  You can have #-comments and empty
	lines.
	"""
	def __init__(self, src, missingOk=False):
		self._parseSrc(src, missingOk)
	
	def __contains__(self, name):
		return name in self.namesDict

	def _parseSrc(self, src, missingOk):
		self.namesDict = {}
		try:
			f = open(src)
		except IOError:
			if not missingOk:
				raise
			else:
				return
		try:
			for ln in f:
				if ln.startswith("#") or not ln.strip():
					continue
				ob, names = re.split("\t+", ln)
				for name in names.lower().split():
					self.namesDict[name.decode("quoted-printable")] = ob
		except ValueError:
			raise gavo.Error("Syntax error in %s: Line %s not understood."%(
				src, repr(ln)))
		f.close()
	
	def resolve(self, name):
		return self.namesDict[name.lower()]


def degToRad(deg):
	"""returns the angle deg (in degrees) in radians.
	"""
	return deg/360.*2*math.pi


def radToDeg(rad):
	"""returns the angle rad (in radians) in degrees.
	"""
	return rad/2./math.pi*360


def jYearToDateTime(jYear):
	"""returns a DateTime instance for a fractional (julian) year.
	
	This refers to time specifications like J2001.32.
	"""
	frac, year = math.modf(float(jYear))
	# Workaround for crazy bug giving dates like 1997-13-1 on some
	# mx.DateTime versions
	if year<0:
		frac += 1
		year -= 1
	return DateTime.DateTime(int(year))+365.25*frac


def dateTimeToJYear(dt):
	"""returns a fractional (julian) year for a mx.DateTime instance.
	"""
	return dt.jdn/365.25-4712


def findMinimum(f, left, right, minInterval=3e-8):
	"""returns an estimate for the minimum of the single-argument function f 
	on (left,right).

	minInterval is a fourth of the smallest test interval considered.  

	For constant functions, a value close to left will be returned.

	This function should only be used on functions having exactly
	one minimum in the interval.
	"""
# replace this at some point by some better method (Num. Recip. in C, 394f)
# -- this is easy to fool and massively suboptimal.
	mid = (right+left)/2.
	offset = (right-left)/4.
	if offset<minInterval:
		return mid
	if f(left+offset)<=f(mid+offset):
		return findMinimum(f, left, mid, minInterval)
	else:
		return findMinimum(f, mid, right, minInterval)


def silence(fun, *args, **kwargs):
	"""executes fun(*args, **kwargs) with stdout redirected to /dev/null.

	This would be a classic for context managers once we have python 2.5.

	This is necessary to shut up silly output from libraries like pyparsing
	and pyfits.
	"""
	realstdout = sys.stdout
	sys.stdout = open("/dev/null", "w")
	try:
		res = fun(*args, **kwargs)
	finally:
		sys.stdout.close()
		sys.stdout = realstdout
	return res


def getMatchingTuple(tupList, key, matchIndex):
	"""returns the first tuple from tupList that has tuple[matchIndex]=key.
	"""
	for t in tupList:
		if t[matchIndex]==key:
			return t
	raise KeyError(key)


def getErrorField():
	"""returns the field attribute of the current exception or "<unknown>"
	if it does not have one.

	This is for use when re-raising gavo.ValidationErrors.
	"""
	_, val, _ = sys.exc_info()
	return getattr(val, "fieldName", "<unknown>")


def getRelativePath(fullPath, rootPath):
	"""returns rest if fullPath has the form rootPath/rest and raises an
	exception otherwise.
	"""
	if not fullPath.startswith(rootPath):
		raise Error("Full path %s does not start with resource root %s"%
			(fullPath, rootPath))
	return fullPath[len(rootPath):].lstrip("/")


def runInSandbox(setUp, func, tearDown, *args, **kwargs):
	"""runs func in a temporary ("sandbox") directory.

	func is called with args and kwargs.  setUp and tearDown are
	two functions also called with args and kwargs; in addition, they
	are passed the path of the tempdir (setUp) or the path of the
	original directory (teardown) in the first argument.
	
	setUp is called after the directory has been created,
	but the process is still in the current WD.
	
	tearDown is called before the temp dir is deleted and in this directory.
	Its return value is the return value of runInSandbox, which is the
	preferred way of getting data out of the sandbox.

	If any of the handlers raise exceptions, the following handlers will not
	be called.  The sandbox will be torn down, though.
	"""
	owd = os.getcwd()
	wd = tempfile.mkdtemp("sandbox")
	try:
		if setUp:
			setUp(wd, *args, **kwargs)
		os.chdir(wd)
		func(*args, **kwargs)
		result = tearDown(owd, *args, **kwargs)
	finally:
		os.chdir(owd)
		shutil.rmtree(wd)
	return result


def makeEllipsis(aStr, maxLen):
	if len(aStr)>maxLen:
		return aStr[:maxLen-3]+"..."
	return aStr


def displayError(exc):
	if isinstance(exc, gavo.Error):
		prefix = "*** Operation failed:"
	else:
		prefix = "*** Uncaught exception:"
	if hasattr(exc, "gavoData"):
		data = str(exc.gavoData)
	else:
		data = ""
	msg = "%s: %s"%(prefix, str(exc))
	gavo.logger.error(msg, exc_info=True)
	sys.stderr.write("\n%s\nA traceback should be available in the log.\n"%(msg))
	if data:
		gavo.logger.error("Pertaining data: %s\n"%data)
		sys.stderr.write("Pertaining data: %s\n"%makeEllipsis(data, 60))


def symlinkwalk(dir, ignoreDotDirs=True):
	"""is os.path.walk following symlinks.  
	
	*Warning*: This will wreak havoc when a symlink points back to a parent.
	"""
	for root, dirs, files in os.walk(dir):
		if ignoreDotDirs:
			ignored = [dir for dir in dirs
				if dir.startswith(".")]
			for dir in ignored:
				dirs.remove(dir)
			if os.path.basename(root).startswith("."):
				continue
		yield root, dirs, files
		for child in dirs:
			if os.path.islink(os.path.join(root, child)):
				for v in symlinkwalk(os.path.join(root, child)):
					yield v


def _test():
	import doctest, utils
	doctest.testmod(utils)


if __name__=="__main__":
	_test()
