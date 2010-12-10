"""
Functions dealing with compilation and introspection of python and 
external code.
"""

#c Copyright 2009 the GAVO Project.
#c
#c This program is free software, covered by the GNU GPL.  See COPYING.

import compiler
import compiler.ast
import contextlib
import imp
import itertools
import inspect
import functools
import os
import re
import shutil
import string
import sys
import tempfile
import weakref

from gavo.utils import algotricks
from gavo.utils import misctricks
from gavo.utils import excs


class CachedGetter(object):
	"""A cache for a callable.

	This is basically memoization, except that these are supposed to be
	singletons;  CachedGetters should be used where the construction of
	a resource (e.g., a grammar) should be deferred until it is actually
	needed to save on startup times.

	The resource is created on the first call, all further calls just return
	references to the original object.

	You can also leave out the getter argument and add an argumentless method 
	impl computing the value to cache.
	"""
	def __init__(self, getter, *args, **kwargs):
		if getter is None:
			getter = self.impl
		self.cache, self.getter = None, getter
		self.args, self.kwargs = args, kwargs
	
	def __call__(self):
		if self.cache is None:
			self.cache = self.getter(*self.args, **self.kwargs)
			del self.args
			del self.kwargs
		return self.cache


class CachedResource(object):
	"""is like CachedGetter but with a built-in getter.

	Here, you define your class and have a class method impl returning
	what you want.
	"""
	cache = None

	@classmethod 
	def __new__(cls, arg):
		if cls.cache is None:
			cls.cache = cls.impl()
		return cls.cache


class IdManagerMixin(object):
	"""
	A mixin for objects requiring unique IDs.
	
	The primaray use case is XML generation, where you want stable IDs
	for objects, but IDs must be unique over an entire XML file.
	
	The IdManagerMixin provides some methods for doing that:
		
		- makeIdFor(object) -- returns an id for object, or None if makeIdFor has
			already been called for that object (i.e., it presumably already is
			in the document).

		- getIdFor(object) -- returns an id for object if makeIdFor has already
			been called before.  Otherwise, a NotFoundError is raised

		- getOrMakeIdFor(object) -- returns an id for object; if object has
			been seen before, it's the same id as before.  Identity is by equality
			for purposes of dictionaries.

		- getForId(id) -- returns the object belonging to an id that has
			been handed out before.  Raises a NotFoundError for unknown ids.

		- cloneFrom(other) -- overwrites the self's id management dictionaries 
			with those from other.  You want this if two id managers must work
			on the same document.
	"""
	__cleanupPat = re.compile("[^A-Za-z_]+")
# Return a proxy instead of raising a KeyError here?  We probably no not
# really want to generate xml with forward references, but who knows?
	def __getIdMaps(self):
		try:
			return self.__objectToId, self.__idsToObject
		except AttributeError:
			self.__objectToId, self.__idsToObject = {}, {}
			return self.__objectToId, self.__idsToObject

	def _fixSuggestion(self, suggestion, invMap):
		for i in itertools.count():
			newId = suggestion+str(i)
			if newId not in invMap:
				return newId

	def cloneFrom(self, other):
		"""takes the id management dictionaries from other.
		"""
		self.__objectToId, self.__idsToObject = other.__getIdMaps()

	def makeIdFor(self, ob, suggestion=None):
		map, invMap = self.__getIdMaps()
		if suggestion:
			suggestion = self.__cleanupPat.sub("", suggestion)
		if id(ob) in map:
			return None

		if suggestion is not None: 
			if suggestion in invMap:
				newId = self._fixSuggestion(suggestion, invMap)
			else:
				newId = suggestion
		else:
			newId = intToFunnyWord(id(ob))

		# register id(ob) <-> newId map, avoiding refs to ob
		map[id(ob)] = newId
		try:
			invMap[newId] = weakref.proxy(ob)
		except TypeError:  # something we can't weakref to
			invMap[newId] = ob
		return newId
	
	def getIdFor(self, ob):
		try:
			return self.__getIdMaps()[0][id(ob)]
		except KeyError:
			raise excs.NotFoundError(repr(ob), what="object",
				within="id manager %r"%(self,), hint="Someone asked for the"
				" id of an object not managed by the id manager.  This usually"
				" is a software bug.")

	def getOrMakeIdFor(self, ob, suggestion=None):
		try:
			return self.getIdFor(ob)
		except excs.NotFoundError:
			return self.makeIdFor(ob, suggestion)

	def getForId(self, id):
		try:
			return self.__getIdMaps()[1][id]
		except KeyError:
			raise excs.NotFoundError(id, what="id", within="id manager %r"%(self,),
				hint="Someone asked for the object belonging to an id that has"
				" been generated externally (i.e., not by this id manager).  This"
				" usually is an internal error of the software.")


class NullObject(object):
	"""A Null object, i.e. one that accepts any method call whatsoever.

	This mainly here for use in scaffolding.
	"""
	def __getattr__(self, name):
		return self
	
	def __call__(self, *args, **kwargs):
		pass


def iterDerivedClasses(baseClass, objects):
	"""iterates over all subclasses of baseClass in the sequence objects.
	"""
	for cand in objects:
		try:
			if issubclass(cand, baseClass) and cand is not baseClass:
				yield cand
		except TypeError:  # issubclass wants a class
			pass


def iterDerivedObjects(baseClass, objects):
	"""iterates over all instances of baseClass in the sequence objects.
	"""
	for cand in objects:
		if isinstance(cand, baseClass):
			yield cand


def buildClassResolver(baseClass, objects, instances=False,
		key=lambda obj: getattr(obj, "name", None), default=None):
	"""returns a function resolving classes deriving from baseClass
	in the sequence objects by their names.

	This is used to build registries of Macros and RowProcessors.  The
	classes in question have to have a name attribute.

	objects would usually be something like globals().values()

	If instances is True the function will return instances instead
	of classes.

	key is a function taking an object and returning the key under which
	you will later access it.  If this function returns None, the object
	will not be entered into the registry.
	"""
	if instances:
		registry = algotricks.DeferringDict()
	else:
		registry = {}
	for cls in iterDerivedClasses(baseClass, objects):
		clsKey = key(cls)
		if clsKey is not None:
			registry[clsKey] = cls
	def resolve(name, registry=registry):
		try:
			return registry[name]
		except KeyError:
			if default is not None:
				return default
			raise
	resolve.registry = registry
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

	Thus, you'll usually use it like this::

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
	for cls in iterDerivedClasses(baseClass, objects):
		try:
			title = cls.name
		except AttributeError:
			title = cls.__name__
		docs.append((title, cls.__doc__))
	docs.sort()
	print formatDocs(docs, underliner)
	return True


@contextlib.contextmanager
def silence():
	"""a context manager to temporarily redirect stdout to /dev/null.

	This is used to shut up some versions of pyparsing and pyfits that
	insist on spewing stuff to stdout from deep within in relatively
	normal situations.
	"""
	realstdout = sys.stdout
	sys.stdout = open("/dev/null", "w")
	try:
		yield
	finally:
		sys.stdout.close()
		sys.stdout = realstdout


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
	# within DaCHS, this should be within tempDir, but we don't bother to
	# get access to DaCHS' config.  So there.
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
	try:
		exec src in useGlobals, locals
	except Exception, ex:
		raise misctricks.logOldExc(excs.BadCode(src, "function", ex))
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
	except SyntaxError, msg:
		raise misctricks.logOldExc(excs.BadCode(expr, "expression", msg))
	# An ast for an expression is a Discard inside at Stmt inside the
	# top-level Module
	try:
		exprNodes = ast.node.nodes
		if len(exprNodes)!=1:
			raise ValueError("Not a single statement")
		if not isinstance(exprNodes[0], compiler.ast.Discard):
			raise ValueError("Not an expression")
	except (ValueError, AttributeError), ex:
		raise misctricks.logOldExc(excs.BadCode(expr, "expression", ex))


def importModule(modName):
	"""imports a module from the module path.

	Use this to programmatically import "normal" modules, e.g., dc-internal
	ones.  It uses python's standard import mechanism and returns the
	module object.

	We're using exec and python's normal import, so the semantics
	should be identical to saying import modName except that the
	caller's namespace is not changed.

	The function returns the imported module.
	"""
	# ward against exploits (we're about to use exec): check syntax
	if not re.match("([A-Za-z_]+)(\.[A-Za-z_]+)*", modName):
		raise excs.Error("Invalid name in internal import: %s"%modName)
	parts = modName.split(".")
	vars = {}
	if len(parts)==1:
		exec "import %s"%modName in vars
	else:
		exec "from %s import %s"%(".".join(parts[:-1]), parts[-1]) in vars
	return vars[parts[-1]]


def loadPythonModule(fqName):
	"""imports fqName and returns the module with a module description.

	The module description is what what find_module returns; you may
	need this for reloading and similar.

	Do not use this function to import DC-internal modules; this may
	mess up singletons since you could bypass python's mechanisms
	to prevent multiple imports of the same module.

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


def loadInternalObject(relativeName, objectName):
	"""gets a name from an internal module.

	relativeName is the python module path (not including "gavo."),
	objectName the name of something within the module.

	This is used for "manual" registries (grammars, cores,...).
	"""
	modName = "gavo."+relativeName
	module = importModule(modName)
	return getattr(module, objectName)


def memoized(origFun):
	"""is a very simple memoizing decorator.

	Beware: This decorator is signature-changing (the resulting function will
	accept all positional arguments, but no keyword arguments, only to
	TypeError out when the original function is called.
	"""
	cache = {}
	def fun(*args):
		if args not in cache:
			cache[args] = origFun(*args)
		return cache[args]
	return functools.update_wrapper(fun, origFun)


def document(origFun):
	"""is a decorator that adds a "buildDocsForThis" attribute to its argument.

	This attribute is evaluated by documentation generators.
	"""
	origFun.buildDocsForThis = True
	return origFun


def iterConsecutivePairs(sequence):
	"""returns pairs of consecutive items from sequence.

	If the last item cannot be paired, it is dropped.

	>>> list(iterConsecutivePairs(range(6)))
	[(0, 1), (2, 3), (4, 5)]
	>>> list(iterConsecutivePairs(range(5)))
	[(0, 1), (2, 3)]
	"""
	iter1, iter2 = iter(sequence), iter(sequence)
	iter2.next()
	return itertools.izip(
		itertools.islice(iter1, None, None, 2),
		itertools.islice(iter2, None, None, 2))


def identity(x):
	return x


def intToFunnyWord(anInt, translation=string.maketrans(
		"-0123456789abcdef", 
		"zaeiousmnthwblpgd")):
	"""returns a sometimes funny (but unique) word from an arbitrary integer.
	"""
	return "".join(reversed(("%x"%anInt).translate(translation)))


def addDefaults(dataDict, defaultDict):
	"""adds key-value pairs from defaultDict to dataDict if the key is missing
	in dataDict.
	"""
	for key, value in defaultDict.iteritems():
		if key not in dataDict:
			dataDict[key] = value


def memoizeOn(onObject, generatingObject, generatingFunction, *args):
	"""memoizes the result of generatingFunction on onObject.

	This is for caching things that adapt to onObjects; see procdefs
	and rowmakers for examples why this is useful.
	"""
	cacheName = "_cache%s%s"%(generatingObject.__class__.__name__, 
		str(id(generatingObject)))
	if getattr(onObject, cacheName, None) is None:
		setattr(onObject, cacheName, generatingFunction(*args))
	return getattr(onObject, cacheName)


def stealVar(varName):
	"""returns the first local variable called varName in the frame stack
	above my caller.

	This is obviously abominable.  This is only used within the DC code where
	the author deemed the specification ugly.
	"""
	frame = inspect.currentframe().f_back.f_back
	while frame:
		if varName in frame.f_locals:
			return frame.f_locals[varName]
		frame = frame.f_back
	raise ValueError("No local %s in the stack"%varName)


def printFrames():
	"""prints a compact list of frames.

	This is an aid for printf debugging.
	"""
	frame = inspect.currentframe().f_back.f_back
	if inspect.getframeinfo(frame)[2]=="getJobsTable":
		return
	while frame:
		print "[%s,%s], [%s]"%inspect.getframeinfo(frame)[:3]
		frame = frame.f_back


def _test():
	import doctest, codetricks
	doctest.testmod(codetricks)


if __name__=="__main__":
	_test()
