"""
Tests for the various structures in rscdef.
"""

#c Copyright 2008-2017, the GAVO project
#c
#c This program is free software, covered by the GNU GPL.  See the
#c COPYING file in the source distribution.


import datetime
import os

from gavo.helpers import testhelpers

from gavo import base
from gavo import rsc
from gavo import rscdef
from gavo import rscdesc
from gavo.rscdef import rmkdef
from gavo.utils import DEG


def makeDD(tableCode, rowmakerCode, grammar="<dictlistGrammar/>",
		moreMakeStuff="", parentRD=None):
	dd = base.parseFromString(rscdef.DataDescriptor,
		'<data><table id="foo">%s</table>'
		'<make table="foo">'
		' <rowmaker id="_foo">%s</rowmaker>'
		'  %s'
		'</make>'
		'%s'
		'</data>'%(
			tableCode, rowmakerCode, moreMakeStuff, grammar))
	if parentRD:
		dd.parent = parentRD
	td = dd.getTableDefById("foo")
	return dd, td


class RowmakerDefTest(testhelpers.VerboseTest):
	"""tests for some aspects of creation of rowmaker definitions.
	"""
	def testBasic(self):
		makeDD('<column name="x"/>', '<map dest="x">a+b</map>')
		map = base.parseFromString(rscdef.MapRule,'<map dest="bar"/>')
		self.assertEqual(map.source, "bar")

	def testNoDestRaises(self):
		self.assertRaisesWithMsg(base.StructureError,
			'At [<map>bar</map>], (1, 8): '
			"You must set key on map elements",
			base.parseFromString, (rscdef.MapRule, '<map>bar</map>'))

	def testStatementRaises(self):
		self.assertRaisesWithMsg(base.BadCode,
			'At [<data><table id="foo"><colu...], (1, 108):'
			" Bad source code in expression (Not an expression)",
			makeDD, ('<column name="x"/>',
				'<map dest="x">c = a+b</map>'))

	def testBadSourceRaises(self):
		self.assertRaisesWithMsg(base.BadCode,
			'At [<data><table id="foo"><colu...], (1, 102): Bad source'
			" code in expression (invalid syntax (line 1))",
			makeDD, ('<column name="x"/>', '<map dest="x">-</map>'))
	
	def testPleonasticRaises(self):
		self.assertRaisesWithMsg(base.StructureError,
			'At [<map dest="bar" src="foo">b...], (1, 29):'
			' Map must have exactly one of source attribute or element content',
			base.parseFromString, 
			(rscdef.MapRule,'<map dest="bar" src="foo">bar</map>'))


class RowmakerMapTest(testhelpers.VerboseTest):
	"""tests for mapping of values during parsing.
	"""
	def testBasicCode(self):
		dd, td = makeDD('<column name="x" type="integer" required="True"/>',
			'<map dest="x">int(vars["src"])</map>')
		mapper = dd.makes[0].rowmaker.compileForTableDef(td)
		self.assertEqual(mapper({'src': '15'}, None)['x'], 15)

	def testBasicMap(self):
		dd, td = makeDD('<column name="x" type="integer" required="True"/>',
			'<map dest="x" src="src"/>')
		mapper = dd.makes[0].rowmaker.compileForTableDef(td)
		self.assertEqual(mapper({'src': '15'}, None)['x'], 15)

	def testBadBasicMap(self):
		self.assertRaisesWithMsg(base.LiteralParseError,
			'At [<data><table id="foo"><colu...], (1, 144):'
			" '@src' is not a valid value for source",
			makeDD, ('<column name="x" type="integer" required="True"/>',
			'<map dest="x" src="@src"/>'))

	def testWithDefault(self):
		dd, td = makeDD('<column name="x" type="integer" required="True"'
			'><values default="18"/></column>', '<map dest="x">int(@x)</map>')
		mapper = dd.makes[0].rowmaker.compileForTableDef(td)
		self.assertEqual(mapper({}, None)['x'], 18)

	def testMessages(self):
		dd, td = makeDD('<column name="x" type="integer" required="True"/>',
			'<map dest="x">int(@src)</map>')
		mapper = dd.makes[0].rowmaker.compileForTableDef(td)
		self.assertRaisesWithMsg(base.ValidationError,
			"Field x: While building x in _foo: Key 'src' not found in a mapping.",
			mapper, ({}, None))
		self.assertRaisesWithMsg(base.ValidationError,
			"Field x: While building x in _foo: invalid literal for int()"
				" with base 10: 'ab c'",
			mapper, ({"src": "ab c"}, None))
	
	def testMultilineExpressions(self):
		dd, td = makeDD('<column name="x" type="integer" required="True"/>'
			'<column name="y" type="text"/>',
			'<map dest="y">("foobar"+\n'
			'@src.decode("utf-8"))\n</map>'
			'<map dest="x">int(\n@src\n)</map>')
		mapper = dd.makes[0].rowmaker.compileForTableDef(td)
		self.assertEqual(mapper({"src": '-20'}, None), {"x": -20, "y": 'foobar-20'})
		self.assertRaisesWithMsg(base.ValidationError,
			"Field x: While building x in _foo: invalid literal for int() with base 10: '3x3'",
			mapper, ({"src": "3x3"}, None))
		self.assertRaisesWithMsg(base.ValidationError,
			"Field y: While building y in _foo: 'utf8' codec can't decode byte 0x98 in position 0:"
				" invalid start byte",
			mapper, ({"src": "\x98x"}, None))

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
		mapper = dd.makes[0].rowmaker.compileForTableDef(td)
		self.assertEqual(mapper({"si": "0", "ii": "2000", "bi": "-3000",
				"r": "0.25", "dp": "25e3", "b": "Off", "tx": "abc", "c": u"\xae",
				"d": "2004-04-08", "ts": "2004-04-08T22:30:15", "t": "22:30:14",
				"raw": ["x", "y", "z"]}, None), {
			'c': u'\xae', 'b': False, 'd': datetime.date(2004, 4, 8), 
			'tx': u'abc', 'bi': -3000, 
			'ts': datetime.datetime(2004, 4, 8, 22, 30, 15), 'ii': 2000, 
			'raw': ['x', 'y', 'z'], 'si': 0, 'r': 0.25, 
			't': datetime.time(22, 30, 14), 'dp': 25000.0})

	def testIdmapsSimple(self):
		dd, td = makeDD('<column name="foo"/><column name="bar"/>',
			'<idmaps>foo</idmaps><map key="bar">3.0</map>')
		mapper = dd.makes[0].rowmaker.compileForTableDef(td)
		self.assertEqual(mapper({'foo': 2}, None),
			{'foo': 2, 'bar': 3.0})

	def testIdmapsDontOverwrite(self):
		dd, td = makeDD('<column name="foo"/><column name="bar"/>',
			'<map dest="foo">float(@foo)/2</map><idmaps>*</idmaps>')
		mapper = dd.makes[0].rowmaker.compileForTableDef(td)
		self.assertEqual(mapper({'foo': 2, 'bar': 2}, None),
			{'foo': 1, 'bar':2})

	def testIdmapsAndNull(self):
		dd, td = makeDD('<column name="foo" type="text"/>',
			'<map dest="foo">parseWithNull(@foo, str, "None")</map>'
			'<idmaps>*</idmaps>')
		mapper = dd.makes[0].rowmaker.compileForTableDef(td)
		self.assertEqual(mapper({'foo': "None"}, None), {'foo': None})
		self.assertEqual(mapper({'foo': "123"}, None), {'foo': "123"})

	def testMapNullAuto(self):
		dd, td = makeDD('<column name="foo" type="integer"/>',
			'<map dest="foo" nullExpr="22"/>')
		mapper = dd.makes[0].rowmaker.compileForTableDef(td)
		self.assertEqual(mapper({'foo': "22"}, None), {'foo': None})
		self.assertEqual(mapper({'foo': "23"}, None), {'foo': 23})

	def testMapNullExprValue(self):
		dd, td = makeDD('<column name="foo" type="integer"/>',
			'<map dest="foo" nullExpr="22">parseInt(@bar)+22</map>')
		mapper = dd.makes[0].rowmaker.compileForTableDef(td)
		self.assertEqual(mapper({'bar': "0"}, None), {'foo': None})
		self.assertEqual(mapper({'bar': "1"}, None), {'foo': 23})

	def testBadNullExpr(self):
		self.assertRaisesWithMsg(base.BadCode,
			'At [<data><table id="foo"><colu...], (1, 152):'
			" Bad source code in expression (invalid syntax"
			" (line 1))",
			makeDD,
			('<column name="foo" type="integer"/>',
				'<map dest="foo" nullExpr="22-">parseInt(@bar)+22</map>'))

	def testNullExcAutoTimestamp(self):
		dd, td = makeDD('<column name="foo" type="timestamp"/>',
			'<map dest="foo" src="foo" nullExcs="ValueError"/>')
		mapper = dd.makes[0].rowmaker.compileForTableDef(td)
		self.assertEqual(mapper({'foo': "x3"}, None), {'foo': None})


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
		mapper = data.rowmakers[0].compileForTableDef(data.makes[0].table)
		self.assertEqual(mapper({"src": 23}, None), {'si': 23})
	
	def testInline(self):
		dd, td = makeDD('  <column name="si" type="smallint"/>',
			'  <apply name="p1"><code>\n'
			'	for i in range(int(vars["src"])):\n'
			'		result["si"] = result.get("si", 0)+i\n'
			'	</code></apply>')
		mapper = dd.makes[0].rowmaker.compileForTableDef(td)
		self.assertEqual(mapper({"src": 23}, None), {'si': 253})
	
	def testRaising(self):
		self.assertRaisesWithMsg(base.NotFoundError,
			"Element with id u'quatsch' could not be located in parse context",
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
		self.assertEqual(res.getPrimaryTable().rows, 
			[{'ct': 0}, {'ct': 1}, {'ct': 2}])

	def testVariablesAvailable(self):
		rmkdef = base.parseFromString(rscdef.RowmakerDef, """<rowmaker>
				<apply>	
					<setup>
						<par key="foo" late="True">@xzzx+"h"</par>
					</setup>
					<code>
						result["norks"] = foo
					</code>
				</apply>
			</rowmaker>""")
		tab = rsc.TableForDef(base.makeStruct(rscdef.TableDef, columns=[]))
		rmk = rmkdef.compileForTableDef(tab.tableDef)
		self.assertEqual(rmk({"xzzx": "u"}, None)["norks"], "uh")


class VarTest(testhelpers.VerboseTest):
	"""tests for rowmaker variables.
	"""
	def testBadNameRaises(self):
		self.assertRaisesWithMsg(base.StructureError,
			'At [<data><table id="foo"></tab...], (1, 86):'
			" '77x' is not a valid value for name",
			makeDD, ('', '<var name="77x">a</var>'))

	def testBadSourceRaises(self):
		self.assertRaisesWithMsg(base.StructureError,
			'At [<data><table id="foo"></tab...], (1, 88): Bad source code in'
			' expression (Not an expression)',
			makeDD, ('', '<var name="x77">a=b</var>'))

	def testBasic(self):
		dd, td = makeDD('  <column name="si" type="smallint"/>',
			'  <var name="x">28</var>'
			'  <var name="y">29+@x</var>'
			'  <map dest="si">@y</map>')
		mapper = dd.makes[0].rowmaker.compileForTableDef(td)
		self.assertEqual(mapper({}, None), {'si': 57})

	def testRaising(self):
		dd, td = makeDD('  <column name="si" type="smallint"/>',
			'  <map dest="si" nullExcs="ZeroDivisionError">1/0</map>')
		mapper = dd.makes[0].rowmaker.compileForTableDef(td)
		self.assertEqual(mapper({}, None), {'si': None})


class SimpleMapsTest(testhelpers.VerboseTest):
	def testBasic(self):
		dd, td = makeDD('<column name="si" type="smallint"/>'
			'<column name="bi" type="smallint"/>',
			'  <simplemaps>si:x, bi:y</simplemaps>')
		mapper = dd.makes[0].rowmaker.compileForTableDef(td)
		self.assertEqual(mapper({'x': 57, 'y':'28'}, None), 
			{'si': 57, 'bi': 28})

	def testFromAttribute(self):
		dd = base.parseFromString(rscdef.DataDescriptor,
			'<data><table id="foo"><column name="z" type="date"/></table>'
			'<dictlistGrammar/><make table="foo">'
			'<rowmaker simplemaps="z:ds"/></make></data>')
		td = dd.getTableDefById("foo")
		mapper = dd.makes[0].rowmaker.compileForTableDef(td)
		self.assertEqual(mapper({'ds': '2010-01-03'}, None), 
			 {'z': datetime.date(2010, 1, 3)})
	
	def testMissingTargetFails(self):
		dd, td = makeDD('<column name="si" type="smallint"/>',
			'  <simplemaps>bi:y</simplemaps>')
		self.assertRaisesWithMsg(base.NotFoundError,
			"column u'bi' could not be located in table foo's columns",
			dd.makes[0].rowmaker.compileForTableDef, (td,))


class PredefinedTest(testhelpers.VerboseTest):
	"""tests for procedures from //procs.
	"""
	def testSimbadOk(self):
		dd, td = makeDD('  <column name="alpha" type="real"/>'
			'  <column name="delta" type="real"/>',
			'  <apply procDef="//procs#resolveObject">'
			'		<bind key="identifier">vars["src"]</bind>'
			'	</apply>'
			' <map dest="alpha">@simbadAlpha</map>'
			' <map dest="delta">@simbadDelta</map>')
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
			'<idmaps>*</idmaps>'%(os.path.abspath("test_data/map1.map"),
					os.path.abspath("test_data/map2.map")))
		res = rsc.makeData(dd, forceSource=[{'in1': 'foo', 'in2': 'left'}])
		self.assertEqual(res.getPrimaryTable().rows, 
			[{'y': u'right', 'x': u'bar'}])

	def testMapDict(self):
		dd, td = makeDD('  <column name="foo" type="text"/>',
			'  <apply procDef="//procs#dictMap" name="mapFoo">'
			'		<bind key="key">"foo"</bind>'
			'		<bind key="mapping">{"x": "u", "0": "1"}</bind>'
			'	</apply><idmaps>*</idmaps>')
		res = rsc.makeData(dd, forceSource=[{'foo': "x"}])
		self.assertEqual(res.getPrimaryTable().rows[0]["foo"], "u")

		self.assertRaisesWithMsg(base.ValidationError,
			"Field foo: dictMap saw '1', which it was not prepared to see.",
			rsc.makeData,
			(dd,), forceSource=[{'foo': "1"}])

	def testMapDictDefault(self):
		dd, td = makeDD('  <column name="foo" type="text"/>',
			'  <apply procDef="//procs#dictMap" name="mapFoo">'
			'		<bind key="key">"foo"</bind>'
			'		<bind key="default">None</bind>'
			'		<bind key="mapping">{"x": "u", "0": "1"}</bind>'
			'	</apply><idmaps>*</idmaps>')
		res = rsc.makeData(dd, forceSource=[{'foo': "x"}, {"foo": "y"}])
		rows = res.getPrimaryTable().rows
		self.assertEqual(rows[0]["foo"], "u")
		self.assertEqual(rows[1]["foo"], None)


class RowmakerMacroTest(testhelpers.VerboseTest):
	"""tests for the standard macros defined by row makers.
	"""
	def test_standardPubDID(self):
		dd, td = makeDD('<column name="x" type="text" required="True"/>',
			r'<map dest="x">\standardPubDID</map>',
			parentRD=testhelpers.getTestRD("ssatest"))
		mapper = dd.makes[0].rowmaker.compileForTableDef(td)
		self.assertEqual(
			mapper(
				{'prodtblAccref': 'foo'}, None)['x'], 
			'ivo://x-unregistred/~?foo')
	
	def test_dlMetaURI(self):
		dd, td = makeDD('<column name="x" type="text" required="True"/>',
			r'<map dest="x">\dlMetaURI{dl}</map>',
			parentRD=testhelpers.getTestRD("ssatest"))
		mapper = dd.makes[0].rowmaker.compileForTableDef(td)
		self.assertEqual(
			mapper(
				{'prodtblAccref': 'foo'}, None)['x'], 
			'http://localhost:8080/data/ssatest/dl/dlmeta'
				'?ID=ivo%3A//x-unregistred/%7E%3Ffoo')

	def test_inputRelativePath(self):
		dd, td = makeDD('<column name="x" type="text" required="True"/>',
			r'<map dest="x">\inputRelativePath</map>',
			parentRD=testhelpers.getTestRD("ssatest"))

		class Parser:
			sourceToken = dd.rd.getAbsPath('foo/bar+baz')

		mapper = dd.makes[0].rowmaker.compileForTableDef(td)
		self.assertEqual(
			mapper({"parser_": Parser} , None)['x'], 
			'foo/bar+baz')

	def test_rowsMade(self):
		dd, td = makeDD('<column name="x" type="integer" required="True"/>',
			r'<map dest="x">\rowsMade</map>')

		mapper = dd.makes[0].rowmaker.compileForTableDef(td)
		self.assertEqual(
			mapper({}, None)['x'], 
			0)
		self.assertEqual(
			mapper({}, None)['x'], 
			1)

	def test_property(self):
		dd, td = makeDD('<column name="x" type="integer" required="True"/>',
			r'<map dest="x">\property{prop}</map>',
			grammar='<dictlistGrammar/><property key="prop">bla</property>')
		mapper = dd.makes[0].rowmaker.compileForTableDef(td)
		self.assertEqual(
			mapper({}, None)['x'], 
			"bla")

	def test_srcstem(self):
		dd, td = makeDD('<column name="x" type="integer" required="True"/>',
			r'<map dest="x">\srcstem</map>')
		mapper = dd.makes[0].rowmaker.compileForTableDef(td)

		class Parser:
			sourceToken = 'goo/quux/foo/bar+baz.tar.gz'

		self.assertEqual(
			mapper({"parser_": Parser}, None)['x'], 
			"bar+baz")

	def test_lastSourceEl(self):
		dd, td = makeDD('<column name="x" type="text" required="True"/>',
			r'<map dest="x">\lastSourceElements{3}</map>',
			parentRD=testhelpers.getTestRD("ssatest"))
		mapper = dd.makes[0].rowmaker.compileForTableDef(td)

		class Parser:
			sourceToken = dd.rd.getAbsPath('goo/quux/foo/bar+baz')

		self.assertEqual(
			mapper({"parser_": Parser}, None)['x'], 
			'quux/foo/bar+baz')

	def test_rootlessPathl(self):
		dd, td = makeDD('<column name="x" type="text" required="True"/>',
			r'<map dest="x">\rootlessPath</map>',
			parentRD=testhelpers.getTestRD("ssatest"))
		mapper = dd.makes[0].rowmaker.compileForTableDef(td)

		class Parser:
			sourceToken = dd.rd.getAbsPath('norz/foo.fits')

		self.assertEqual(
			mapper({"parser_": Parser}, None)['x'], 
			'norz/foo.fits')

	def test_inputSize(self):
		dd, td = makeDD('<column name="x" type="integer" required="True"/>',
			r'<map dest="x">\inputSize</map>',
			parentRD=testhelpers.getTestRD("ssatest"))
		mapper = dd.makes[0].rowmaker.compileForTableDef(td)

		class Parser:
			sourceToken = dd.rd.getAbsPath('data/spec3.ssatest')

		self.assertEqual(
			mapper({"parser_": Parser}, None)['x'], 213)

	def test_qName(self):
		dd, td = makeDD('<column name="x" type="text" required="True"/>',
			r'<map dest="x">\qName</map>',
			parentRD=testhelpers.getTestRD("ssatest"))
		mapper = dd.makes[0].rowmaker.compileForTableDef(td)
		self.assertEqual(
			mapper({}, None)['x'], 'test.foo')


class IgnoreOnTest(testhelpers.VerboseTest):
	"""tests for working ignoreOn clauses.
	"""
	def testBasic(self):
		dd, td = makeDD('<column name="si"/>',
			'<ignoreOn><keyPresent key="y"/></ignoreOn><idmaps>*</idmaps>')
		mapper = dd.makes[0].rowmaker.compileForTableDef(td)
		self.assertEqual(mapper({'si': '1'}, None), {'si': 1.0})
		self.assertRaises(rscdef.IgnoreThisRow, mapper,
			{'si': 1, 'y': None}, None)
	
	def testBuilding(self):
		dd, td = makeDD('<column name="si"/>',
			'<ignoreOn><keyMissing key="y"/></ignoreOn><idmaps>*</idmaps>')
		table = rsc.makeData(dd, forceSource=[{'si':1}, {'si':2, 'y':"yes"},
			{'si': 3}]).getPrimaryTable()
		self.assertEqual(table.rows, [{'si':2.}])


class ToParameterTest(testhelpers.VerboseTest):
	def testPlain(self):
		dd, td = makeDD('<param name="u" type="integer"/>', "", 
			'<dictlistGrammar asPars="True"/>',
			'<parmaker><map dest="u" src="u"/></parmaker>')
		data = rsc.makeData(dd, forceSource=[{"u": "10"}])
		self.assertEqual(data.getPrimaryTable().getParam("u"), 10)
	
	def testConstant(self):
		dd, td = makeDD('<param name="u" type="integer"/>', "", 
			'<dictlistGrammar/>',
			'<parmaker><map dest="u">10</map></parmaker>')
		data = rsc.makeData(dd, forceSource=[])
		self.assertEqual(data.getPrimaryTable().getParam("u"), 10)
			
	def testIdmaps(self):
		dd, td = makeDD('<param name="u" type="timestamp"/>'
				'<param name="pos" type="spoint"/>', "", 
			'<dictlistGrammar asPars="True"/>',
			'<parmaker idmaps="*"/>')
		data = rsc.makeData(dd, forceSource=[
			{'u': "2010-10-10T10:10:10", 'pos': '34,-30'}])
		self.assertEqual(data.getPrimaryTable().getParam("u"), 
			datetime.datetime(2010, 10, 10, 10, 10, 10))
		self.assertAlmostEqual(data.getPrimaryTable().getParam("pos").x,
			34*DEG)

	def testBadDest(self):
		dd, td = makeDD('<param name="u" type="timestamp"/>', "",
			'<dictlistGrammar/>',
			'<parmaker><map dest="foo">10</map></parmaker>')
		self.assertRaisesWithMsg(base.NotFoundError,
			"column u'foo' could not be located in table foo's params",
			rsc.makeData,
			(dd, rsc.parseNonValidating, []))

	def testBadSource(self):
		dd, td = makeDD('<param name="u" type="timestamp"/>', "",
			'<dictlistGrammar/>',
			'<parmaker><map dest="u" src="bar"/></parmaker>')
		self.assertRaisesWithMsg(base.ValidationError,
			"Field u: While building u in None: Key 'bar' not found in a mapping.",
			rsc.makeData,
			(dd, rsc.parseNonValidating, []))


if __name__=="__main__":
	testhelpers.main(ToParameterTest)
