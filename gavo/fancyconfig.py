"""
A wrapper around ConfigParser that defines syntax and types within
the configuration options.
"""

import ConfigParser
import re
import os
import weakref

defaultSection = "general"  # must be all lowercase


class ConfigError(Exception):
	"""is the base class of the user visible exceptions from this module.
	"""

class ParseError(ConfigError):
	"""is raised by ConfigItem's parse methods if there is a problem with
	the input.

	These should only escape to users of this module unless they call
	ConfigItem.set themselves (which they shouldn't).
	"""

class NoConfigItem(ConfigError):
	"""is raised by Configuration if a non-existing configuration
	item is set or requested.
	"""

class BadConfigValue(ConfigError):
	"""is raised by getConfiguration when there is a syntax error or the
	like in a value.

	The error message gives a hint at the reason of the error and is intended
	for human consumption.
	"""

class SyntaxError(ConfigError):
	"""is raised when the input file syntax is bad (i.e., on
	ConfigParser.ParsingErrors)
	"""


class ConfigItem(object):
	"""is a description of a configuration item including methods
	to parse and unparse them.

	This class is an abstract base class for options with real syntax
	(_parse and _unparse methods).

	ConfigItems have a section and a name (as in ConfigParser), a
	value (that defaults to default), an origin (which is "default",
	if the value has not been changed and otherwise can be freely
	used  by clients), and a description.  The origin is important
	for distinguishing what to save.

	You need to define the _parse and _unparse methods in deriving
	classes.  The _parse methods must take a byte string (the encoding
	has to be utf-8) and return anything or raise ParseErrors (with
	a sensible description of the problem) if there is a problem
	with the input; the must not raise other exceptions when passed a
	string (but may do anything when passed something else.  _unparse
	methods must not raise exceptions, take a value as returned
	by parse (nothing else must be passed in) and return a
	string that _parse would parse into this value.

	Thus, the set method *only* takes strings as values.  To set
	parsed values, assign to value directly.  However, _unparse
	methods are not required to cope with any crazy stuff you enter
	in this way, and thus you suddenly may receive all kinds of
	funny exceptions when serializing a Configuration.

	Inheriting classes need to specify a class attribute default that
	kicks in when no default has been specified during construction.
	These must be strings parseable by _parse.

	Finally, you should provide a typedesc class attribute, a description
	of the type intended for human consumption.  See the documentation
	functions below to get an idea how the would be shown.
	"""

	typedesc = "unspecified value"

	def __init__(self, name, section=defaultSection, default=None,
			description="Undocumented"):
		self.section, self.name = section, name
		if default is None:
			default = self.default
		self.default = default
		self.set(default, "default")
		self.description = description
		self.parent = None # will be set on adoption by a Configuration
	
	def set(self, value, origin="user"):
		self.value, self.origin = self._parse(value), origin

	def getAsString(self):
		return self._unparse(self.value)

	def _parse(self, value):
		raise ParseError("Internal error: Base config item used.")
	
	def _unparse(self, value):
		return value


class StringConfigItem(ConfigItem):
	"""is a config item containing unicode strings.

	The serialization of the config file is supposed to be utf-8.

	The special value None is used as a Null value literal.

	Tests are below.
	"""

	typedesc = "string"
	default = ""

	def _parse(self, value):
		if value=="None":
			return None
		if isinstance(value, unicode):
			return value
		try:
			return value.decode("utf-8")
		except UnicodeError:
			raise ParseError("Not a valid utf-8 string: %s"%repr(value))
		except AttributeError:
			raise ParseError("Only strings are allowed in %s, not %s"%(
				self.__class__.__name__, repr(value)))

	def _unparse(self, value):
		if value is None:
			return "None"
		return value.encode("utf-8")


class IntConfigItem(ConfigItem):
	"""is a config item containing an integer.

	It supports a Null value through the special None literal.
	>>> ci = IntConfigItem("foo"); print ci.value
	None
	>>> ci = IntConfigItem("foo", default="23"); ci.value
	23
	>>> ci.set("42"); ci.value
	42
	>>> ci.getAsString()
	'42'
	"""

	typedesc = "integer"
	default = "None"

	def _parse(self, value):
		if value=="None":
			return None
		try:
			return int(value)
		except ValueError:
			raise ParseError("%s is not an integer literal"%value)

	def _unparse(self, value):
		return str(value)


class ListConfigItem(StringConfigItem):
	r"""is a ConfigItem containing a list of strings, comma separated.

	The values are space-normalized.  Trailing whitespace-only items are
	discarded, so "" is an empty list, "," is a list containing one
	empty string.

	There is currently no way to embed commas in the values.  If that
	should become necessary, I'd probably go for backslash escaping.

	>>> ci = ListConfigItem("foo"); ci.value, ci.getAsString()
	([], '')
	>>> ci.set(ci.getAsString());ci.value
	[]
	>>> ci.set("3, 2, 1, Z\xc3\xbcndung"); ci.value, ci.getAsString()
	([u'3', u'2', u'1', u'Z\xfcndung'], '3, 2, 1, Z\xc3\xbcndung, ')
	>>> ci.set(",");ci.value
	[u'']
	>>> ci.set(ci.getAsString());ci.value
	[u'']
	"""

	typedesc = "list of strings"
	default = ""

	def _parse(self, value):
		res = [s.strip() 
			for s in StringConfigItem._parse(self, value).split(",")]
		if not res[-1]:
			del res[-1]
		return res
	
	def _unparse(self, value):
		return StringConfigItem._unparse(self, ", ".join(value+[""]))


class IntListConfigItem(ListConfigItem):
	"""is a ConfigItem containing a list of ints, comma separated.

	Literal handling is analoguos to ListConfigItem.

	>>> ci = IntListConfigItem("foo"); ci.value, ci.getAsString()
	([], '')
	>>> ci.set("3,2, 1"); ci.value, ci.getAsString()
	([3, 2, 1], '3, 2, 1, ')
	>>> ci.set(ci.getAsString()); ci.value
	[3, 2, 1]
	>>> ci.set("1, 2, 3, rubbish")
	Traceback (most recent call last):
	ParseError: Non-integer in integer list
	"""

	typedesc = "list of integers"
	default = ""

	def _parse(self, value):
		try:
			return [int(s) for s in ListConfigItem._parse(self, value)]
		except ValueError, msg:
			raise ParseError("Non-integer in integer list")
	
	def _unparse(self, value):
		return ListConfigItem._unparse(self, [str(n) for n in value])


class DictConfigItem(ListConfigItem):
	r"""is a config item that contains a concise representation of
	a string-string mapping.

	The literal format is {<key>:<value>,}, where whitespace is ignored
	between tokens and the last comma may be ommitted.

	No commas and colons are allowed within keys and values.  To lift this,
	I'd probably go for backslash escaping.

	>>> ci = DictConfigItem("foo"); ci.value
	{}
	>>> ci.set("ab:cd, foo:Fu\xc3\x9f"); ci.value
	{u'ab': u'cd', u'foo': u'Fu\xdf'}
	>>> ci.getAsString();ci.set(ci.getAsString()); ci.value
	'ab:cd, foo:Fu\xc3\x9f, '
	{u'ab': u'cd', u'foo': u'Fu\xdf'}
	>>> ci.set("ab:cd, rubbish")
	Traceback (most recent call last):
	ParseError: 'rubbish' is not a valid mapping literal element
	"""

	typespec = "mapping"
	default = ""

	def _parse(self, value):
		res = {}
		for item in ListConfigItem._parse(self, value):
			try:
				k, v = item.split(":")
				res[k.strip()] = v.strip()
			except ValueError:
				raise ParseError("'%s' is not a valid mapping literal element"%
					item)
		return res
	
	def _unparse(self, value):
		return ListConfigItem._unparse(self,
			["%s:%s"%(k, v) for k, v in value.iteritems()])


class BooleanConfigItem(ConfigItem):
	"""is a config item that contains a boolean and can be parsed from
	many fancy representations.
	"""

	typespec = "boolean"
	default = "False"

	trueLiterals = set(["true", "yes", "t", "on", "enabled", "1"])
	falseLiterals = set(["false", "no", "f", "off", "disabled", "0"])
	def _parse(self, value):
		value = value.lower()
		if value in self.trueLiterals:
			return True
		elif value in self.falseLiterals:
			return False
		else:
			raise ParseError("'%s' is no recognized boolean literal."%value)
	
	def _unparse(self, value):
		return {True: "True", False: "False"}[value]


class EnumeratedConfigItem(StringConfigItem):
	"""is a ConfigItem taking string values out of a set of possible strings.

	Use the keyword argument options to pass in the possible strings.
	The first item becomes the default unless you give a default.
	You must give a non-empty list of strings as options.
	"""

	typespec = "value from a defined set"

	def __init__(self, name, section=defaultSection, default=None,
			description="Undocumented", options=[]):
		if default is None:
			default = options[0]
		self.options = set(options)
		self.typespec = "value from the list %s"%(", ".join(self.options))
		StringConfigItem.__init__(self, name, section, default, description)
	
	def _parse(self, value):
		encVal = StringConfigItem._parse(self, value)
		if encVal not in self.options:
			raise ParseError("%s is not an allowed value.  Choose one of"
				" %s"%(value, ", ".join([o.encode("utf-8") for o in self.options])))
		return encVal


class PathConfigItem(StringConfigItem):
	"""is a ConfigItem for a unix shell-type path.

	The individual items are separated by colons, ~ is replaced by the
	current value of $HOME (or "/", if unset), and $<key> substitutions
	are supported, with key having to point to a key in the defaultSection.

	To embed a real $ sign, double it.

	This is parented ConfigItem, i.e., it needs a Configuration parent
	before its value can be accessed.
	"""

	typespec = "shell-type path"

	def _parse(self, value):
		self._unparsed = StringConfigItem._parse(self, value)
		if self._unparsed is None:
			return []
		else:
			return [s.strip() for s in self._unparsed.split(":")]
	
	def _unparse(self, value):
		return StringConfigItem._unparse(self, self._unparsed)

	def _getValue(self):
		def resolveReference(mat):
			if mat.group(1)=='$':
				return '$'
			else:
				return self.parent.get(mat.group(1))
		res = []
		for p in self._value:
			if p.startswith("~"):
				p = os.environ.get("HOME", "")+p[1:]
			if '$' in p:
				p = re.sub(r"\$(\w+)", resolveReference, p)
			res.append(p)
		return res

	def _setValue(self, val):
		self._value = val
	
	value = property(_getValue, _setValue)


class Configuration(object):
	"""is a collection of ConfigItems and provides an interface to access them.

	You construct it with the ConfigItems you want and then use the get
	method to access their content.  You can either use get(section, name)
	or just get(name), which implies the defaultSection section defined
	at the top (right now, "general").

	To read configuration items, use addFromFp.  addFromFp should only
	raise subclasses of ConfigError.

	You can also set individual items using set.

	The class follows the default behaviour of ConfigParser in that section
	case is preserved, but item names are lowercased.

	Note that direct access to items is not forbidden, but you have to
	keep case mangling of keys into account when doing so.
	"""
	def __init__(self, *items):
		self.items = {}
		for item in items:
			self.items[item.section.lower(), item.name.lower()] = item
			item.parent = weakref.proxy(self)

	def __iter__(self):
		return iter(self.items)

	def get(self, arg1, arg2=None):
		if arg2 is None:
			name, section = arg1.lower(), defaultSection
		else:
			name, section = arg2.lower(), arg1.lower()
		if (section, name) in self.items:
			return self.items[section, name].value
		else:
			raise NoConfigItem("No such configuration item: [%s] %s"%(
				section, name))

	def set(self, arg1, arg2, arg3=None, origin="user"):
		"""sets a configuration item to a value.

		arg1 can be a section, in which case arg2 is a key and arg3 is a
		value; alternatively, if arg3 is not given, arg1 is a key in
		the defaultSection, and arg2 is the value.

		All arguments are strings that must be parseable by the referenced
		item's _parse method.
		
		Origin is a tag you can use to, e.g., determine what to save.
		"""
		if arg3 is None:
			section, name, value = defaultSection, arg1, arg2
		else:
			section, name, value = arg1, arg2, arg3
		if (section.lower(), name.lower()) in self.items:
			return self.items[section.lower(), name.lower()].set(value, origin)
		else:
			raise NoConfigItem("No such configuration item: [%s] %s"%(
				section, name))


	def addFromFp(self, fp, origin="user", fName="<internal>"):
		"""adds the config items in the file fp to self.
		"""
		p = ConfigParser.SafeConfigParser()
		try:
			p.readfp(fp, fName)
		except ConfigParser.ParsingError, msg:
			raise SyntaxError("Config syntax error in %s: %s"%(fName, 
				unicode(msg)))
		sections = p.sections()
		for section in sections:
			for name, value in p.items(section):
				try:
					self.set(section, name, value, origin)
				except ParseError, msg:
					raise BadConfigValue("While parsing value of %s in section %s,"
						" file %s:\n%s"%
						(name, section, fName, unicode(msg)))


def _addToConfig(config, fName, origin):
	"""adds the config items in the file named in fName to the Configuration, 
	tagging them with origin.

	fName can be None or point to a non-exisiting file.  In both cases,
	the function does nothing.
	"""
	if not fName or not os.path.exists(fName):
		return
	f = open(fName)
	config.addFromFp(f, origin=origin, fName=fName)
	f.close()
	

def readConfiguration(config, systemFName, userFName):
	"""fills the Configuration config with values from the the two locations.

	File names that are none or point to non-existing locations are
	ignored.
	"""
	_addToConfig(config, systemFName, "system")
	_addToConfig(config, userFName, "user")


def makeTxtDocs(config):
	import textwrap
	docs = []
	sections = {}
	for section, key in config:
		sections.setdefault(section, []).append(key)
	sectNames = sections.keys()
	sectNames.sort()
	if defaultSection in sectNames:
		sectNames.remove(defaultSection)
		sectNames.insert(0, defaultSection)
	for section in sectNames:
		items = sections[section]
		if not items:
			continue
		hdr = "Section [%s]"%(config.items[section, items[0]].section)
		docs.append("\n%s\n%s\n"%(hdr, "'"*len(hdr)))
		items.sort()
		for item in items:
			ci = config.items[section, item]
			docs.append("* %s: %s; "%(ci.name, ci.typedesc)) 
			docs.append("  defaults to '%s' --"%ci.default)
			docs.append(textwrap.fill(ci.description, width=72, initial_indent="  ",
				subsequent_indent="  "))
	return "\n".join(docs)
		
	

def _getTestSuite():
	"""returns a unittest suite for this module.

	It's in-file since I want to keep the thing in a single file.
	"""
	import unittest
	from cStringIO import StringIO

	class TestConfigItems(unittest.TestCase):
		"""tests for individual config items.
		"""
		def testStringConfigItemDefaultArgs(self):
			ci = StringConfigItem("foo")
			self.assertEqual(ci.name, "foo")
			self.assertEqual(ci.section, defaultSection)
			self.assertEqual(ci.value, "")
			self.assertEqual(ci.description, "Undocumented")
			self.assertEqual(ci.origin, "default")
			ci.set("bar", "user")
			self.assertEqual(ci.value, "bar")
			self.assertEqual(ci.origin, "user")
			self.assertEqual(ci.name, "foo")
			self.assertEqual(ci.section, defaultSection)
			self.assertEqual(ci.getAsString(), "bar")

		def testStringConfigItemNoDefaults(self):
			ci = StringConfigItem("foo", section="bar", default="quux",
				description="An expressionist config item")
			self.assertEqual(ci.name, "foo")
			self.assertEqual(ci.section, "bar")
			self.assertEqual(ci.value, "quux")
			self.assertEqual(ci.description, "An expressionist config item")
			self.assertEqual(ci.origin, "default")
			ci.set("None", "user")
			self.assertEqual(ci.value, None)
			self.assertEqual(ci.origin, "user")
			self.assertEqual(ci.getAsString(), "None")

		def testStringConfigItemEncoding(self):
			ci = StringConfigItem("foo", default='F\xc3\xbc\xc3\x9fe')
			self.assertEqual(ci.value.encode("iso-8859-1"), 'F\xfc\xdfe')
			self.assertEqual(ci.getAsString(), 'F\xc3\xbc\xc3\x9fe')
			self.assertRaises(ParseError, ci.set, 'Fu\xdf')

		def testIntConfigItem(self):
			ci = IntConfigItem("foo")
			self.assertEqual(ci.value, None)
			ci = IntConfigItem("foo", default="0")
			self.assertEqual(ci.value, 0)
			ci.set("42")
			self.assertEqual(ci.value, 42)
			self.assertEqual(ci.getAsString(), "42")

		def testBooleanConfigItem(self):
			ci = BooleanConfigItem("foo", default="0")
			self.assertEqual(ci.value, False)
			self.assertEqual(ci.getAsString(), "False")
			ci.set("true")
			self.assertEqual(ci.value, True)
			ci.set("on")
			self.assertEqual(ci.value, True)
			self.assertEqual(ci.getAsString(), "True")
			self.assertRaises(ParseError, ci.set, "undecided")

		def testEnumeratedConfigItem(self):
			ci = EnumeratedConfigItem("foo", options=["bar", "foo", u"Fu\xdf"])
			self.assertEqual(ci.value, "bar")
			self.assertRaises(ParseError, ci.set, "quux")
			self.assertRaises(ParseError, ci.set, "gr\xc3\x9f")
			ci.set('Fu\xc3\x9f')
			self.assertEqual(ci.value, u"Fu\xdf")
			self.assertEqual(ci.getAsString(), 'Fu\xc3\x9f')


	class ReadConfigTest(unittest.TestCase):
		"""tests for reading complete configurations.
		"""
		def _getConfig(self):
			return Configuration(
				StringConfigItem("emptyDefault", description="is empty by default"),
				StringConfigItem("fooDefault", default="foo",
					description="is foo by default"),
				IntConfigItem("count", "types", default="0", description=
					"is an integer"),
				ListConfigItem("enum", "types", description="is a list", 
					default="foo, bar"),
				IntListConfigItem("intenum", "types", description="is a list of ints",
					default="1,2,3"),
				DictConfigItem("map", "types", description="is a mapping",
					default="intLit:1, floatLit:0.1, bla: wurg"),)

		def testDefaults(self):
			config = self._getConfig()
			self.assertEqual(config.get("emptyDefault"), "")
			self.assertEqual(config.get("fooDefault"), "foo")
			self.assertEqual(config.get("types", "count"), 0)
			self.assertEqual(config.get("types", "enum"), [u"foo", u"bar"])
			self.assertEqual(config.get("types", "intenum"), [1,2,3])
			self.assertEqual(config.get("types", "map"), {"intLit": "1",
				"floatLit": "0.1", "bla": "wurg"})

		def testSetting(self):
			config = self._getConfig()
			config.set("emptyDefault", "foo")
			self.assertEqual(config.get("emptyDefault"), "foo")
			self.assertEqual(config.items[defaultSection, "emptydefault"].origin,
				"user")
			self.assertEqual(config.items[defaultSection, "foodefault"].origin,
				"default")

		def testReading(self):
			config = self._getConfig()
			config.addFromFp(StringIO("[general]\n"
				"emptyDefault: bar\n"
				"fooDefault: quux\n"
				"[types]\n"
				"count: 7\n"
				"enum: one, two,three:3\n"
				"intenum: 1, 1,3,3\n"
				"map: Fu\xc3\x9f: y, x:Fu\xc3\x9f\n"))
			self.assertEqual(config.get("emptyDefault"), "bar")
			self.assertEqual(config.get("fooDefault"), "quux")
			self.assertEqual(config.get("types", "count"), 7)
			self.assertEqual(config.get("types", "enum"), ["one", "two", "three:3"])
			self.assertEqual(config.get("types", "intenum"), [1,1,3,3])
			self.assertEqual(config.get("types", "map"), {u'Fu\xdf': "y",
				"x": u'Fu\xdf'})
			self.assertEqual(config.items["types", "map"].origin, "user")

		def testRaising(self):
			config = self._getConfig()
			self.assertRaises(BadConfigValue, config.addFromFp, 
				StringIO("[types]\nintenum: brasel\n"))
			self.assertRaises(SyntaxError, config.addFromFp, 
				StringIO("intenum: brasel\n"))
			self.assertRaises(NoConfigItem, config.addFromFp,
				StringIO("[types]\nnonexisting: True\n"))
			self.assertRaises(ParseError, config.items["types", "count"].set,
				"abc")

	l = locals()
	tests = [l[name] for name in l 
		if isinstance(l[name], type) and issubclass(l[name], unittest.TestCase)]
	loader = unittest.TestLoader()
	suite = unittest.TestSuite([loader.loadTestsFromTestCase(t)
		for t in tests])
	return suite


def _test():
	import fancyconfig, doctest, unittest
	suite = _getTestSuite()
	suite.addTest(doctest.DocTestSuite(fancyconfig))
	unittest.TextTestRunner().run(suite)


if __name__=="__main__":
	_test()
