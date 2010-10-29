"""
Tests for the various structures in rscdef.
"""

import datetime
import os

from gavo import base
from gavo import rsc
from gavo import rscdef
from gavo import rscdesc
from gavo.helpers import testhelpers
from gavo.rscdef import rmkdef



class _FakeTable(object):
	def __init__(self, td):
		self.tableDef = td


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
			'At (1, 8): '
			"You must set dest on map elements",
			base.parseFromString, (rscdef.MapRule, '<map>bar</map>'))
		self.assertRaisesWithMsg(base.BadCode,
			"At (1, 89):"
			" Bad source code in expression (Not an expression)",
			makeDD, ('<column name="x"/>',
				'<map dest="x">c = a+b</map>'))
		self.assertRaisesWithMsg(base.BadCode,
			"At (1, 83): Bad source"
			" code in expression (unexpected EOF while parsing (line 1))",
			makeDD, ('<column name="x"/>', '<map dest="x">-</map>'))
		self.assertRaisesWithMsg(base.StructureError,
			'At (1, 29):'
			' Map must have exactly one of src attribute or element content',
			base.parseFromString, 
			(rscdef.MapRule,'<map dest="bar" src="foo">bar</map>'))


class RowmakerMapTest(testhelpers.VerboseTest):
	"""tests for mapping of values during parsing.
	"""
	def testBasicCode(self):
		dd, td = makeDD('<column name="x" type="integer"/>',
			'<map dest="x">int(src)</map>')
		mapper = dd.rowmakers[0].compileForTable(_FakeTable(td))
		self.assertEqual(mapper({'src': '15'})['x'], 15)

	def testBasicMap(self):
		dd, td = makeDD('<column name="x" type="integer"/>',
			'<map dest="x" src="src"/>')
		mapper = dd.rowmakers[0].compileForTable(_FakeTable(td))
		self.assertEqual(mapper({'src': '15'})['x'], 15)

	def testWithDefault(self):
		dd, td = makeDD('<column name="x" type="integer"><values default="18"/>'
			'</column>', '<map dest="x">int(x)</map>')
		mapper = dd.rowmakers[0].compileForTable(_FakeTable(td))
		self.assertEqual(mapper({})['x'], 18)

	def testMessages(self):
		dd, td = makeDD('<column name="x" type="integer"/>',
			'<map dest="x">int(src)</map>')
		mapper = dd.rowmakers[0].compileForTable(_FakeTable(td))
		self.assertRaisesWithMsg(base.ValidationError,
			"While building x in _foo: name 'src' is not defined",
			mapper, ({}, ))
		self.assertRaisesWithMsg(base.ValidationError,
			"While building x in _foo: invalid literal for int()"
				" with base 10: 'ab c'",
			mapper, ({"src": "ab c"},))
	
	def testMultilineExpressions(self):
		dd, td = makeDD('<column name="x" type="integer"/>'
			'<column name="y" type="text"/>',
			'<map dest="y">("foobar"+\n'
			'src.decode("utf-8"))\n</map>'
			'<map dest="x">int(\nsrc\n)</map>')
		mapper = dd.rowmakers[0].compileForTable(_FakeTable(td))
		self.assertEqual(mapper({"src": '-20'}), {"x": -20, "y": 'foobar-20'})
		self.assertRaisesWithMsg(base.ValidationError,
			"While building x in _foo: invalid literal for int() with base 10: '3x3'",
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
			'<map dest="si" src="si"/>'
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
		mapper = dd.rowmakers[0].compileForTable(_FakeTable(td))
		self.assertEqual(mapper({"si": "0", "ii": "2000", "bi": "-3000",
				"r": "0.25", "dp": "25e3", "b": "Off", "tx": "abc", "c": u"\xae",
				"d": "2004-04-08", "ts": "2004-04-08T22:30:15", "t": "22:30:14",
				"raw": ["x", "y", "z"]}), {
			'c': u'\xae', 'b': False, 'd': datetime.date(2004, 4, 8), 
			'tx': u'abc', 'bi': -3000, 
			'ts': datetime.datetime(2004, 4, 8, 22, 30, 15), 'ii': 2000, 
			'raw': ['x', 'y', 'z'], 'si': 0, 'r': 0.25, 
			't': datetime.time(22, 30, 14), 'dp': 25000.0})

	def testIdmapsDontOverwrite(self):
		dd, td = makeDD('<column name="foo"/><column name="bar"/>',
			'<map dest="foo">float(foo)/2</map><idmaps>*</idmaps>')
		mapper = dd.rowmakers[0].compileForTable(_FakeTable(td))
		self.assertEqual(mapper({'foo': 2, 'bar': 2}),
			{'foo': 1, 'bar':2})

	def testIdmapsAndNull(self):
		dd, td = makeDD('<column name="foo" type="text"/>',
			'<map dest="foo">parseWithNull(foo, str, "None")</map><idmaps>*</idmaps>')
		mapper = dd.rowmakers[0].compileForTable(_FakeTable(td))
		self.assertEqual(mapper({'foo': "None"}), {'foo': None})
		self.assertEqual(mapper({'foo': "123"}), {'foo': "123"})


class ApplyTest(testhelpers.VerboseTest):
	"""Tests for mapping procedures.
	"""
	def testArtificial(self):
		from gavo import rscdesc
		rd = base.parseFromString(rscdesc.RD,
		'<resource schema="test"><procDef type="apply" id="artificial">'
			'<setup><par key="val"/></setup><code>result["si"] = val</code>'
			'</procDef>'
			'<data><table id="foo"><column name="si" type="smallint"/></table>'
			'<rowmaker id="_foo"><apply procDef="artificial" name="p1">\n'
			'<bind key="val">23</bind></apply></rowmaker>\n'
			'<make table="foo" rowmaker="_foo"/>'
			'<dictlistGrammar/></data></resource>')
		data = rd.dds[0]
		mapper = data.rowmakers[0].compileForTable(_FakeTable(data.makes[0].table))
		self.assertEqual(mapper({"src": 23}), {'si': 23})
	
	def testInline(self):
		dd, td = makeDD('  <column name="si" type="smallint"/>',
			'  <apply name="p1"><code>\n'
			'	for i in range(int(vars["src"])):\n'
			'		result["si"] = result.get("si", 0)+i\n'
			'	</code></apply>')
		mapper = dd.rowmakers[0].compileForTable(_FakeTable(td))
		self.assertEqual(mapper({"src": 23}), {'si': 253})
	
	def testRaising(self):
		self.assertRaisesWithMsg(base.StructureError,
			"At (1, 50):"
			" Reference to unknown item 'quatsch'.",
			makeDD, ('', '<apply name="xy" procDef="quatsch"/>'))

	def testArgExpansion(self):
		dd, td = makeDD('<column name="d" type="date"/>',
			'<apply name="foo">'
			' <code>result["si"] = "\\test{1}{2}"\n</code>'
			'</apply>')
		res = rsc.makeData(dd, forceSource=[{}])
		self.assertEqual(res.getPrimaryTable().rows, 
			[{'si': 'test macro expansion'},])

	def testTableAccess(self):
		dd, td = makeDD('<column name="d" type="date"/>',
			'<apply name="foo">'
			' <code>result["ct"] = len(targetTable)\n</code>'
			'</apply>')
		res = rsc.makeData(dd, forceSource=[{}, {}, {}])
		self.assertEqual(res.getPrimaryTable().rows, [{'ct': 0}, {'ct': 1}, {'ct': 2}])


class VarTest(testhelpers.VerboseTest):
	"""tests for rowmaker variables.
	"""
	def testRaising(self):
		self.assertRaisesWithMsg(base.StructureError,
			"At (1, 67):"
			" '77x' is not a valid value for name",
			makeDD, ('', '<var name="77x">a</var>'))
		self.assertRaisesWithMsg(base.StructureError,
			'At (1, 69): Bad source code in'
			' expression (Not an expression)',
			makeDD, ('', '<var name="x77">a=b</var>'))

	def testBasic(self):
		dd, td = makeDD('  <column name="si" type="smallint"/>',
			'  <var name="x">28</var>'
			'  <var name="y">29+x</var>'
			'  <map dest="si">y</map>')
		mapper = dd.rowmakers[0].compileForTable(_FakeTable(td))
		self.assertEqual(mapper({}), {'si': 57})


class PredefinedTest(testhelpers.VerboseTest):
	"""tests for procedures from //procs.
	"""
	def testSimbad(self):
		dd, td = makeDD('  <column name="alpha" type="real"/>'
			'  <column name="delta" type="real"/>',
			'  <apply procDef="//procs#resolveObject">'
			'		<bind key="identifier">vars["src"]</bind>'
			'	</apply>'
			' <map dest="alpha">simbadAlpha</map>'
			' <map dest="delta">simbadDelta</map>')
		res = rsc.makeData(dd, forceSource=[{'src': "Aldebaran"}])
		row = res.getPrimaryTable().rows[0]
		self.assertEqual(str(row["alpha"])[:6], "68.980")
		self.assertEqual(len(row), 2)
	
	def testSimbadFail(self):
		dd, td = makeDD('<column name="alpha" type="real"/>'
			'  <column name="delta" type="real"/>',
			'  <apply procDef="//procs#resolveObject">'
			'  <bind key="ignoreUnknowns">False</bind>'
			'	 <bind key="identifier">src</bind>'
			'	</apply>'
			' <map dest="alpha">simbadAlpha</map>'
			' <map dest="delta">simbadDelta</map>')
		self.assertRaises(base.ValidationError,
			rsc.makeData, dd, forceSource=[{'src': "Quxmux_333x"}])

	def testNoAliasing(self):
		dd, td = makeDD('<column name="x" type="text"/>'
				'<column name="y" type="text"/>',
			'<apply procDef="//procs#mapValue">'
				'<bind key="sourceName">"%s"</bind>'
				'<bind key="destination">"x"</bind><bind key="value">'
				'vars["in1"]</bind></apply>'
			'<apply procDef="//procs#mapValue">'
				'<bind key="sourceName">"%s"</bind>'
				'<bind key="destination">"y"</bind><bind key="value">'
				'vars["in2"]</bind></apply>'
			'<idmaps>*</idmaps>'%(os.path.abspath("data/map1.map"),
					os.path.abspath("data/map2.map")))
		res = rsc.makeData(dd, forceSource=[{'in1': 'foo', 'in2': 'left'}])
		self.assertEqual(res.getPrimaryTable().rows, 
			[{'y': u'right', 'x': u'bar'}])


class IgnoreOnTest(testhelpers.VerboseTest):
	"""tests for working ignoreOn clauses.
	"""
	def testBasic(self):
		dd, td = makeDD('<column name="si"/>',
			'<ignoreOn><keyPresent key="y"/></ignoreOn><idmaps>*</idmaps>')
		mapper = dd.rowmakers[0].compileForTable(_FakeTable(td))
		self.assertEqual(mapper({'si': '1'}), {'si': 1.0})
		self.assertRaises(rscdef.IgnoreThisRow, mapper,
			{'si': 1, 'y': None})
	
	def testBuilding(self):
		dd, td = makeDD('<column name="si"/>',
			'<ignoreOn><keyMissing key="y"/></ignoreOn><idmaps>*</idmaps>')
		table = rsc.makeData(dd, forceSource=[{'si':1}, {'si':2, 'y':"yes"},
			{'si': 3}]).getPrimaryTable()
		self.assertEqual(table.rows, [{'si':2.}])


if __name__=="__main__":
	testhelpers.main(RowmakerMapTest)
