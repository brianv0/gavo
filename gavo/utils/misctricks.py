"""
Various helpers that didn't fit into any other xTricks.
"""

from gavo.utils import excs


class _UndefinedType(type):
	"""the metaclass for Undefined.

	Internally used.
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
	"""A string-like thing basically representing SQL quoted identifiers.

	This has some features that make handling these relatively painless
	in ADQL code.

	The most horrible feature is that these hash and compare as their embedded
	names, except to other QuotedNamess.

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
		else:
			return self.name==other

	def __ne__(self, other):
		return not self==other

	def __str__(self):
		return '"%s"'%(self.name.replace('"', '""'))

	def __repr__(self):
		return 'QuotedName(%s)'%repr(self.name)

	def lower(self):  # service to ADQL name resolution
		return self
	
	def capitalize(self):  # service for table head and such
		return self


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


def _test():
	import doctest, misctricks
	doctest.testmod(misctricks)


if __name__=="__main__":
	_test()
