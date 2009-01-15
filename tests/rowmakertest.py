"""
Tests for the various structures in rscdef.
"""

import datetime
import os

import gavo
from gavo import base
from gavo import grammars
from gavo import rsc
from gavo import rscdef
from gavo import rscdesc
from gavo.rscdef import rmkdef

import testhelpers


def makeDD(tableCode, rowmakerCode):
	dd = base.parseFromString(rscdef.DataDescriptor,
		'<data><table id="foo">%s</table>'
		'<rowmaker id="_foo">%s</rowmaker>'
		'<make table="foo" rowmaker="_foo"/>'
		'<dictlistGrammar/></data>'%(
			tableCode, rowmakerCode))
	td = dd.getTableDefById("foo")
	return dd, td

class RowmakerDefTest(testhelpers.VerboseTest):
	"""tests for some aspects of creation of rowmaker definitions.
	"""
	def testBasic(self):
		makeDD('<column name="x"/>', '<map dest="x">a+b</map>')
		map = base.parseFromString(rscdef.MapRule,'<map dest="bar"/>')
		self.assertEqual(map.src, "bar")

	def testRaises(self):
		self.assertRaisesWithMsg(base.StructureError,
			"You must set dest on map elements",
			base.parseFromString, (rscdef.MapRule, '<map>bar</map>'))
		self.assertRaisesWithMsg(base.LiteralParseError,
			"'c = a+b' is not a valid python expression",
			makeDD, ('<column name="x"/>',
				'<map dest="x">c = a+b</map>'))
		self.assertRaisesWithMsg(base.LiteralParseError,
			"'-' is not correct python syntax",
			makeDD, ('<column name="x"/>', '<map dest="x">-</map>'))
		self.assertRaisesWithMsg(base.StructureError,
			'Map must have exactly one of src attribute or element content',
			base.parseFromString, 
			(rscdef.MapRule,'<map dest="bar" src="foo">bar</map>'))


class RowmakerMapTest(testhelpers.VerboseTest):
	"""tests for mapping of values during parsing.
	"""
	def testBasicCode(self):
		dd, td = makeDD('<column name="x" type="integer"/>',
			'<map dest="x">int(src)</map>')
		mapper = dd.rowmakers[0].compileForTable(td)
		self.assertEqual(mapper({'src': '15'})['x'], 15)

	def testBasicMap(self):
		dd, td = makeDD('<column name="x" type="integer"/>',
			'<map dest="x" src="src"/>')
		mapper = dd.rowmakers[0].compileForTable(td)
		self.assertEqual(mapper({'src': '15'})['x'], 15)

	def testWithDefault(self):
		dd, td = makeDD('<column name="x" type="integer"/>',
			'<map dest="x">int(src)</map>'
			'<default key="src">18</default>')
		mapper = dd.rowmakers[0].compileForTable(td)
		self.assertEqual(mapper({})['x'], 18)

	def testMessages(self):
		dd, td = makeDD('<column name="x" type="integer"/>',
			'<map dest="x">int(src)</map>')
		mapper = dd.rowmakers[0].compileForTable(td)
		self.assertRaisesWithMsg(base.ValidationError,
			"While building x in _foo: name 'src' is not defined",
			mapper, ({}, ))
		self.assertRaisesWithMsg(base.ValidationError,
			"While building x in _foo: invalid literal for int(): ab c",
			mapper, ({"src": "ab c"},))
	
	def testMultilineExpressions(self):
		dd, td = makeDD('<column name="x" type="integer"/>'
			'<column name="y" type="text"/>',
			'<map dest="y">("foobar"+\n'
			'src.decode("utf-8"))\n</map>'
			'<map dest="x">int(\nsrc\n)</map>')
		mapper = dd.rowmakers[0].compileForTable(td)
		self.assertEqual(mapper({"src": '-20'}), {"x": -20, "y": 'foobar-20'})
		self.assertRaisesWithMsg(base.ValidationError,
			"While building x in _foo: invalid literal for int(): 3x3",
			mapper, ({"src": "3x3"},))
		self.assertRaisesWithMsg(base.ValidationError,
			"While building y in _foo: 'utf8' codec can't decode byte 0x98 in position 0:"
				" unexpected code byte",
			mapper, ({"src": "\x98x"},))

	def testDefaultLiterals(self):
		dd, td = makeDD('<column name="si" type="smallint"/>'
			'  <column name="ii" type="integer"/>'
			'  <column name="bi" type="bigint"/>'
			'  <column name="r"/>'
			'  <column name="dp" type="double precision"/>'
			'  <column name="b" type="boolean"/>'
			'  <column name="tx" type="text"/>'
			'  <column name="c" type="char"/>'
			'  <column name="d" type="date"/>'
			'  <column name="ts" type="timestamp"/>'
			'  <column name="t" type="time"/>'
			'  <column name="raw" type="raw"/>',
			' <map dest="si" src="si"/>'
			' <map dest="ii" src="ii"/>'
			' <map dest="bi" src="bi"/>'
			' <map dest="r" src="r"/>'
			' <map dest="dp" src="dp"/>'
			' <map dest="b" src="b"/>'
			' <map dest="tx" src="tx"/>'
			' <map dest="c" src="c"/>'
			' <map dest="d" src="d"/>'
			' <map dest="ts" src="ts"/>'
			' <map dest="t" src="t"/>'
			' <map dest="raw" src="raw"/>')
		mapper = dd.rowmakers[0].compileForTable(td)
		self.assertEqual(mapper({"si": "0", "ii": "2000", "bi": "-3000",
				"r": "0.25", "dp": "25e3", "b": "Off", "tx": "abc", "c": u"\xae",
				"d": "2004-04-08", "ts": "2004-04-08T22:30:15", "t": "22:30:14",
				"raw": ["x", "y", "z"]}), {
			'c': u'\xae', 'b': False, 'd': datetime.date(2004, 4, 8), 
			'tx': u'abc', 'bi': -3000, 
			'ts': datetime.datetime(2004, 4, 8, 22, 30, 15), 'ii': 2000, 
			'raw': ['x', 'y', 'z'], 'si': 0, 'r': 0.25, 
			't': datetime.time(22, 30, 14), 'dp': 25000.0})


class ProcTest(testhelpers.VerboseTest):
	"""Tests for mapping procedures.
	"""
	def testArtificial(self):
		base.parseFromString(rmkdef.ProcDef,
			'<proc name="artificial" isGlobal="True">'
			'<arg key="val"/>\n'
			'  result["si"] = val\n'
			'</proc>')
		dd, td = makeDD('<column name="si" type="smallint"/>',
			'  <proc name="p1" predefined="artificial">'
			'		<arg key="val">src</arg>'
			'	</proc>')
		mapper = dd.rowmakers[0].compileForTable(td)
		self.assertEqual(mapper({"src": 23}), {'si': 23})
	
	def testInline(self):
		dd, td = makeDD('  <column name="si" type="smallint"/>',
			'  <proc name="p1">'
			'		<arg key="val">src</arg>\n'
			'for i in range(int(val)):\n'
			'		result["si"] = result.get("si", 0)+i\n'
			'	</proc>')
		mapper = dd.rowmakers[0].compileForTable(td)
		self.assertEqual(mapper({"src": 23}), {'si': 253})
	
	def testRaising(self):
		self.assertRaisesWithMsg(base.StructureError,
			"You must set name on proc elements",
			makeDD, ('', '<proc/>'))
		self.assertRaisesWithMsg(base.StructureError,
			"No such predefined procedure: quatsch",
			makeDD, ('', '<proc name="xy" predefined="quatsch"/>'))

	def testDefaultArgs(self):
		dd, td = makeDD('<column name="si" type="smallint"/>',
			'<proc name="foo">'
			'	<arg key="x1">22</arg>'
			' <arg key="x2" default="23">x2in</arg>\n'
			' result["si"] = int(x1+x2)\n'
			'</proc>')
		self.assertEqual(dd.rowmakers[0]._getSource(td)[0],
			'_result = {}\nfoo(_result, rowdict_, tableDef_, x1=22, x2=x2in)')
		self.assertEqual(dd.rowmakers[0].procs[0]._getFormalArgs(), 
			"result, vars, tableDef, x1, x2=base.Undefined")
	
	def testArgExpansion(self):
		dd, td = makeDD('<column name="d" type="date"/>',
			'<proc name="foo">'
			'	<arg key="x1">"\\test"</arg>'
			' <arg key="x2" default="\'\\test{1}{2}\'"/>\n'
			' result["si"] = x1+x2\n'
			'</proc>')
		res = rsc.makeData(dd, forceSource=[{'x2': '2'}, {}])
		self.assertEqual(res.getPrimaryTable().rows, 
			[{'si': 'test macro expansion2'}, 
			{'si': 'test macro expansiontest macro expansion'}])
	
	def testIndentation(self):
		dd, td = makeDD('<column name="d" type="date"/>',
			'<proc name="foo">'
			'	<arg key="x1"></arg>'
			' <arg key="x2"/>\n'
			' for i in range(10):\n'
			' \tx1+=i\n'
			'</proc>')
		dd, td = makeDD('<column name="d" type="date"/>',
			'<proc name="foo">'
			'	<arg key="x1"></arg>'
			' <arg key="x2"/>\n'
			'for i in range(10):\n'
			' x1+=i\n'
			'print "a"\n'
			'</proc>')

	def testConsStuff(self):
		base.parseFromString(rmkdef.ProcDef, '<proc name="consstufftest"'
			' isGlobal="True"><consComp><arg key="mapping"/>\n'
			' assMap = base.parseAssignments(mapping)\n'
			' del mapping\n'
			' return locals()\n'
			'</consComp><arg key="foo"/>\n'
			'vars["mapped"] = assMap[foo]</proc>')
		dd, td = makeDD('<column name="mapped" type="text"/>',
			'<proc predefined="consstufftest">'
			'<consArg key="mapping">"x:y 1:2"</consArg></proc>'
			'<map dest="mapped"/>')
		res = rsc.makeData(dd, forceSource=[{'foo': 'x'}, {'foo': '1'}])
		self.assertEqual(res.getPrimaryTable().rows,
			[{'mapped': u'y'}, {'mapped': u'2'}])


class VarTest(testhelpers.VerboseTest):
	"""tests for rowmaker variables.
	"""
	def testRaising(self):
		self.assertRaisesWithMsg(base.StructureError,
			"Var names must be valid python identifiers, and 77x is not",
			makeDD, ('', '<var name="77x">a</var>'))
		self.assertRaisesWithMsg(base.StructureError,
			"'a=b' is not a valid python expression",
			makeDD, ('', '<var name="x77">a=b</var>'))

	def testBasic(self):
		dd, td = makeDD('  <column name="si" type="smallint"/>',
			'  <var name="x">28</var>'
			'  <var name="y">29+x</var>'
			'  <map dest="si">y</map>')
		mapper = dd.rowmakers[0].compileForTable(td)
		self.assertEqual(mapper({}), {'si': 57})


class PredefinedTest(testhelpers.VerboseTest):
	"""tests for using predefined procedures.
	"""
	def testSimbad(self):
		dd, td = makeDD('  <column name="alpha" type="real"/>'
			'  <column name="delta" type="real"/>',
			'  <proc predefined="resolveObject">'
			'		<arg key="identifier">src</arg>'
			'	</proc>'
			' <map dest="alpha">simbadAlpha</map>'
			' <map dest="delta">simbadDelta</map>')
		res = rsc.makeData(dd, forceSource=[{'src': "Aldebaran"}])
		row = res.getPrimaryTable().rows[0]
		self.assertEqual(str(row["alpha"])[:6], "68.980")
		self.assertEqual(len(row), 2)
	
	def testSimbadFail(self):
		dd, td = makeDD('<column name="alpha" type="real"/>'
			'  <column name="delta" type="real"/>',
			'  <proc predefined="resolveObject">'
			'  <consArg key="ignoreUnknowns">False</consArg>'
			'		<arg key="identifier">src</arg>'
			'	</proc>'
			' <map dest="alpha">simbadAlpha</map>'
			' <map dest="delta">simbadDelta</map>')
		self.assertRaises(base.ValidationError,
			rsc.makeData, dd, forceSource=[{'src': "Quxmux_333x"}])

	def testNoAliasing(self):
		dd, td = makeDD('<column name="x" type="text"/>'
				'<column name="y" type="text"/>',
			'<proc predefined="mapValue" name="map1">'
				'<consArg key="sourceName">"%s"</consArg>'
				'<consArg key="destination">"x"</consArg><arg key="value">'
				'in1</arg></proc>'
			'<proc predefined="mapValue" name="map2">'
				'<consArg key="sourceName">"%s"</consArg>'
				'<consArg key="destination">"y"</consArg><arg key="value">'
				'in2</arg></proc>'
			'<idmaps>*</idmaps>'%(os.path.abspath("data/map1.map"),
					os.path.abspath("data/map2.map")))
		res = rsc.makeData(dd, forceSource=[{'in1': 'foo', 'in2': 'left'}])
		self.assertEqual(res.getPrimaryTable().rows, 
			[{'y': u'right', 'x': u'bar'}])

if __name__=="__main__":
	testhelpers.main(PredefinedTest)
