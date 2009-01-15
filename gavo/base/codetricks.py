"""
Functions dealing with compilation and introspection of python and 
external code.
"""

import compiler
import compiler.ast
import imp
import os
import re
import shutil
import sys
import tempfile

from gavo.base import config
from gavo.base import excs


def _iterDerivedClasses(baseClass, objects):
	"""iterates over all subclasses of baseClass in the sequence objects.
	"""
	for cand in objects:
		try:
			if issubclass(cand, baseClass) and cand is not baseClass:
				yield cand
		except TypeError:  # issubclass wants a class
			pass


class _Deferred(object):
	"""is a helper class for DeferringDict.
	"""
	def __init__(self, callable, args=(), kwargs={}):
		self.callable, self.args, self.kwargs = callable, args, kwargs
	
	def actualize(self):
		return self.callable(*self.args, **self.kwargs)


class DeferringDict(dict):
	"""is a dictionary that stores tuples of a callable and its
	arguments and will, on the first access, do the calls.

	This is used below to defer the construction of instances in the class
	resolver to when they are actually used.  This is important with interfaces,
	since they usually need the entire system up before they can sensibly
	be built.
	"""
	def __setitem__(self, key, value):
		if isinstance(value, tuple):
			dict.__setitem__(self, key, _Deferred(*value))
		else:
			dict.__setitem__(self, key, _Deferred(value))

	def __getitem__(self, key):
		val = dict.__getitem__(self, key)
		if isinstance(val, _Deferred):
			val = val.actualize()
			dict.__setitem__(self, key, val)
		return val


def buildClassResolver(baseClass, objects, instances=False):
	"""returns a function resolving classes deriving from baseClass
	in the sequence objects by their names.

	This is used to build registries of Macros and RowProcessors.  The
	classes in question have to have a name attribute.

	objects would usually be something like globals().values()

	If instances is True the function will return instances instead
	of classes.
	"""
	if instances:
		registry = DeferringDict()
	else:
		registry = {}
	for cls in _iterDerivedClasses(baseClass, objects):
		if hasattr(cls, "name"):
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
		if not makeClassDocs(Macro, globals().values()):
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


def compileFunction(src, funcName, useGlobals=None):
	"""runs src through exec and returns the item funcName from the resulting
	namespace.

	This is typically used to define functions, like this:
	>>> resFunc = compileFunction("def f(x): print x", "f")
	>>> resFunc(1); resFunc("abc")
	1
	abc
	"""
	locals = {}
	if useGlobals is None:
		useGlobals = globals()
	exec src in useGlobals, locals
	return locals[funcName]


def ensureExpression(expr, errName="unknown"):
	"""raises a LiteralParserError if expr is not a parseable python expression.
	"""
	# bizarre bug in the compiler modules: naked strings are compiled into
	# just a module name.  Fix it by forcing an expression on those:
	if expr.startswith("'") or expr.startswith('"'):
		expr = "''+"+expr
	try:
		ast = compiler.parse(expr)
	except SyntaxError:
		raise excs.LiteralParseError("'%s' is not correct python syntax"%
			expr, errName, expr)
	# An ast for an expression is a Discard inside at Stmt inside the
	# top-level Module
	try:
		exprNodes = ast.node.nodes
		if len(exprNodes)!=1:
			raise ValueError("Not a single statement")
		if not isinstance(exprNodes[0], compiler.ast.Discard):
			raise ValueError("Not an expression")
	except (ValueError, AttributeError):
		raise excs.LiteralParseError("'%s' is not a valid python expression"%
			expr, errName, expr)


def getBinaryName(baseName):
	"""returns the name of a binary it thinks is appropriate for the platform.

	To do this, it asks config for the platform name, sees if there's a binary
	<bin>-<platname> if platform is nonempty.  If it exists, it returns that name,
	in all other cases, it returns baseName unchanged.
	"""
	platform = config.get("platform")
	if platform:
		platName = baseName+"-"+platform
		if os.path.exists(platName):
			return platName
	return baseName


def loadPythonModule(fqName):
	"""imports fqName and returns the module with a module description.

	The module description is what what find_module returns.

	fqName is a fully qualified path to the module without the .py.
	"""
	moduleName = os.path.basename(fqName)
	modpath = os.path.dirname(fqName)
	moddesc = imp.find_module(moduleName, [modpath])
	try:
		imp.acquire_lock()
		modNs = imp.load_module(moduleName, *moddesc)
	finally:
		imp.release_lock()
	return modNs, moddesc


def _test():
	import doctest, codetricks
	doctest.testmod(codetricks)


if __name__=="__main__":
	_test()
