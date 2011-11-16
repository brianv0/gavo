"""
Various helpers that didn't fit into any other xTricks.
"""

from __future__ import with_statement

import contextlib
import os
import re
import struct
import threading
import time
import urllib2

from gavo.utils import excs


class _UndefinedType(type):
	"""the metaclass for Undefined.

	Used internally.
	"""
	def __str__(cls):
		raise excs.StructureError("%s cannot be stringified."%cls.__name__)

	__unicode__ = __str__

	def __repr__(cls):
		return "<Undefined>"

	def __nonzero__(cls):
		return False


class Undefined(object):
	"""a sentinel for all kinds of undefined values.

	Do not instantiate.

	>>> Undefined()
	Traceback (most recent call last):
	TypeError: Undefined cannot be instantiated.
	>>> bool(Undefined)
	False
	>>> repr(Undefined)
	'<Undefined>'
	>>> str(Undefined)
	Traceback (most recent call last):
	StructureError: Undefined cannot be stringified.
	"""
	__metaclass__ = _UndefinedType

	def __init__(self):
		raise TypeError("Undefined cannot be instantiated.")


class QuotedName(object):
	"""A string-like thing basically representing SQL delimited identifiers.

	This has some features that make handling these relatively painless
	in ADQL code.

	The most horrible feature is that these hash and compare as their embedded
	names, except to other QuotedNamess.

	SQL-92, in 5.2, roughly says:

	delimited identifiers compare literally with each other,
	delimited identifiers compare with regular identifiers after the
	latter are all turned to upper case.  But since postgres turns everything
	to lower case, we do so here, too.

	>>> n1, n2, n3 = QuotedName("foo"), QuotedName('foo"l'), QuotedName("foo")
	>>> n1==n2,n1==n3,hash(n1)==hash("foo")
	(False, True, True)
	>>> print n1, n2
	"foo" "foo""l"
	"""
	def __init__(self, name):
		self.name = name
	
	def __hash__(self):
		return hash(self.name)
	
	def __eq__(self, other):
		if isinstance(other, QuotedName):
			return self.name==other.name
		elif isinstance(other, basestring):
			return self.name==other.lower()
		else:
			return False

	def __ne__(self, other):
		return not self==other

	def __str__(self):
		return '"%s"'%(self.name.replace('"', '""'))

	def __repr__(self):
		return 'QuotedName(%s)'%repr(self.name)

	def lower(self):  # service to ADQL name resolution
		return self

	def flatten(self): # ADQL query serialization
		return str(self)

	def capitalize(self):  # service for table head and such
		return self.name.capitalize()
	
	def __add__(self, other):  # for disambiguateColumns
		return QuotedName(self.name+other)
	

def getfirst(args, key, default=Undefined):
	"""returns the first value of key in the web argument-like object args.

	args is a dictionary mapping keys to lists of values.  If key is present,
	the first element of the list is returned; else, or if the list is
	empty, default if given.  If not, a Validation error for the requested
	column is raised.

	>>> getfirst({'x': [1,2,3]}, 'x')
	1
	>>> getfirst({'x': []}, 'x')
	Traceback (most recent call last):
	ValidationError: Missing mandatory parameter x
	>>> getfirst({'x': []}, 'y')
	Traceback (most recent call last):
	ValidationError: Missing mandatory parameter y
	>>> print(getfirst({'x': []}, 'y', None))
	None
	"""
	try:
		return args[key][0]
	except (KeyError, IndexError):
		if default is Undefined:
			raise excs.ValidationError("Missing mandatory parameter %s"%key,
				colName=key)
		return default


def sendUIEvent(eventName, *args):
	"""sends an eventName to the DC event dispatcher.

	If no event dispatcher is available, do nothing.

	The base.ui object that the GAVO DC software uses for event dispatching
	is only available to sub-packages above base.  Other code should not
	use or need it under normal circumstances, but if it does, it can
	use this.

	All other code should use base.ui.notify<eventName>(*args) directly.
	"""
	try:
		from gavo.base import ui
		getattr(ui, "notify"+eventName)(*args)
	except ImportError:
		pass


def logOldExc(exc):
	"""logs the mutation of the currently handled exception to exc.

	This just does a notifyExceptionMutation using sendUIEvent; it should
	only be used by code at or below base.
	"""
	sendUIEvent("ExceptionMutation", exc)
	return exc


def getFortranRec(f):
	"""reads a "fortran record" from f and returns the payload.

	A "fortran record" comes from an unformatted file and has a
	4-byte payload length before and after the payload.  Native endianess
	is assumed here.

	If the two length specs do not match, a ValueError is raised.
	"""
	try:
		startPos = f.tell()
	except IOError:
		startPos = "(stdin)"
	rawLength = f.read(4)
	if rawLength=='': # EOF
		return None
	recLen = struct.unpack("i", rawLength)[0]
	data = f.read(recLen)
	rawPost = f.read(4)
	if not rawPost:
		raise ValueError("Record starting at %s has no postamble"%startPos)
	postambleLen = struct.unpack("i", rawPost)[0]
	if recLen!=postambleLen:
		raise ValueError("Record length at record (%d) and did not match"
			" postamble declared length (%d) at %s"%(
				recLen, postambleLen, startPos))
	return data


def iterFortranRecs(f, skip=0):
	"""iterates over the fortran records in f.

	For details, see getFortranRec.
	"""
	while True:
		rec = getFortranRec(f)
		if rec is None:
			break
		if skip>0:
			skip -= 1
			continue
		yield rec


def getWithCache(url, cacheDir, extraHeaders={}):
	"""returns the content of url, from a cache if possible.

	Of course, you only want to use this if there's some external guarantee
	that the resource behing url doesn't change.  No expiry mechanism is
	present here.
	"""
	if not os.path.isdir(cacheDir):
		os.makedirs(cacheDir)
	cacheName = os.path.join(cacheDir, re.sub("[^\w]+", "", url)+".cache")
	if os.path.exists(cacheName):
		with open(cacheName) as f:
			return f.read()
	else:
		f = urllib2.urlopen(url)
		doc = f.read()
		f.close()
		with open(cacheName, "w") as f:
			f.write(doc)
		return doc


####################### Pyparsing hacks
# This may not be the best place to put this, but I don't really have a
# better one at this point.  We need some configuration of pyparsing, and
# this is probably imported by all modules doing pyparsing.

try:
	from pyparsing import ParserElement, ParseException
	ParserElement.enablePackrat()
	# Hack to get around behaviour swings of setParseAction; we use
	# addParseAction throughout and retrofit it to pyparsings that don't have it.
	if not hasattr(ParserElement, "addParseAction"):
		ParserElement.addParseAction = ParserElement.setParseAction

	_PYPARSE_LOCK = threading.Lock()

	@contextlib.contextmanager
	def pyparsingWhitechars(whiteChars):
		"""a context manager that serializes pyparsing grammar compilation
		and manages its whitespace chars.

		We need different whitespace definitions in some parts of DaCHS.
		(The default used to be " \\t" for a while, so this is what things
		get reset to).

		Since whitespace apparently can only be set globally for pyparsing,
		we provide this c.m.  Since it is possible that grammars will be
		compiled in threads (e.g., as a side effect of getRD), this is
		protected by a lock.  This, in turn, means that this can 
		potentially block for a long time.

		Bottom line: When compiling pyparsing grammars, *always* set
		the whitespace chars explicitely, and do it through this c.m.
		"""
		_PYPARSE_LOCK.acquire()
		ParserElement.setDefaultWhitespaceChars(whiteChars)
		try:
			yield
		finally:
			ParserElement.setDefaultWhitespaceChars(" \t")
			_PYPARSE_LOCK.release()
except ImportError, ex:  # no pyparsing, let clients bomb if they need it.
	@contextlib.contextmanager
	def pyparsingWhitechars(arg):
		raise ex
		yield



def _test():
	import doctest, misctricks
	doctest.testmod(misctricks)


if __name__=="__main__":
	_test()
