"""
Tests for the various structures in rscdef.
"""

#c Copyright 2008-2016, the GAVO project
#c
#c This program is free software, covered by the GNU GPL.  See the
#c COPYING file in the source distribution.


import datetime
import os
import weakref

from gavo.helpers import testhelpers

from gavo import base
from gavo import grammars
from gavo import rscdef
from gavo import rscdesc
from gavo import utils
from gavo.base import parsecontext
from gavo.rscdef import scripting


class DictAttributeTest(testhelpers.VerboseTest):
	def testBasic(self):
		class X(base.Structure):
			name_ = "X"
			_s = base.DictAttribute("s")
		res = base.parseFromString(X, """<X><s key="bla">nork</s>
			<s key="foo">por</s></X>""")
		self.assertEqual(res.s, {'foo': 'por', 'bla': 'nork'})
	
	def testItemAtt(self):
		class FooAttribute(base.UnicodeAttribute):
			def parse(self, value):
				return "%%%s%%"%value
		class X(base.Structure):
			name_ = "X"
			_s = base.DictAttribute("s", itemAttD=FooAttribute("foo"))
		res = base.parseFromString(X, """<X><s key="bla">nork</s>
			<s key="foo">por</s></X>""")
		self.assertEqual(res.s, {'foo': '%por%', 'bla': '%nork%'})

	def testAdding(self):
		class X(base.Structure):
			name_ = "X"
			_s = base.DictAttribute("s")
		res = base.parseFromString(X, """<X><s key="bla">nork</s>
			<s key="bla">por</s><s key="u">a</s><s key="u" cumulate="True">bc</s>
			<s key="v" cumulate="True">l</s></X>""")
		self.assertEqual(res.s, {'bla': 'por', 'u': 'abc', 'v': 'l'})

	def testKeyname(self):
		class X(base.Structure):
			name_ = "X"
			_s = base.DictAttribute("s", keyName="name")
		res = base.parseFromString(X, """<X><s key="bla">nork</s>
			<s name="foo">por</s></X>""")
		self.assertEqual(res.s, {'foo': 'por', 'bla': 'nork'})


class ColumnTest(testhelpers.VerboseTest):
	"""tests the rscdef.Column class.
	"""
	def testParse(self):
		col = base.parseFromString(rscdef.Column, '<column name="foo"'
			' type="text" unit="km/s" ucd="foo.bar" description="Some column"'
			' tablehead="Foo" utype="type.bar" required="False"'
			' displayHint="sf=3"><verbLevel>20</verbLevel>'
			' </column>')
		self.assertEqual(col.utype, "type.bar")
		self.assertEqual(col.required, False)
		self.assertEqual(col.verbLevel, 20)
		self.assertEqual(col.displayHint["sf"], "3")

	def testMetaRow(self):
		col = base.parseFromString(rscdef.Column, '<column name="foo"'
			' type="text" unit="km/s" ucd="foo.bar" description="Some column"'
			' tablehead="Foo" utype="type.bar" required="False"'
			' displayHint="sf=3"><verbLevel>20</verbLevel>'
			' </column>')
#XXX TODO: Add test when the migration is ready
#		self.assertEqual(col.getMetaRow(), {})

	def testGetLabel(self):
		col = base.parseFromString(rscdef.Column,
			'<column name="foo"/>')
		self.assertEqual(col.getLabel(), "Foo")

	def testRealizesIndex(self):
		table = base.parseFromString(rscdef.TableDef, """
			<table><column name="urks"/><column name="ba"/>
				<index columns="urks" name="u"/></table>""")
		self.assertEqual(table.columns[0].isIndexed(), True)
		self.assertEqual(table.columns[1].isIndexed(), False)
		col = base.parseFromString(rscdef.Column, '<column name="foo"/>')
		self.failUnless(col.isIndexed() is None)

	def testRealizesPrimary(self):
		table = base.parseFromString(rscdef.TableDef, """
			<table primary="urks"><column name="urks"/><column name="ba"/>
				</table>""")
		self.assertEqual(table.columns[0].isPrimary(), True)
		self.assertEqual(table.columns[1].isPrimary(), False)
		col = base.parseFromString(rscdef.Column, '<column name="foo"/>')
		self.failUnless(col.isPrimary() is None)

	def testValidation(self):
		col = base.parseFromString(rscdef.Param, '<param name="foo"'
			' required="True"><values min="1" max="2"/>1.5</param>')
		self.assertRuns(col.validateValue, (1.5,))
		self.assertRuns(col.validateValue, (1,))
		self.assertRuns(col.validateValue, (2,))
		self.assertRaises(base.ValidationError, col.validateValue, -1)
		self.assertRaises(base.ValidationError, col.validateValue, 30)
		self.assertRaises(base.ValidationError, col.validateValue, None)
		col.required = False
		self.assertRuns(col.validateValue, (None,))

	def testBadTypeRejected(self):
		self.assertRaisesWithMsg(base.LiteralParseError, 
			"At [<column name=\"foo\" type=\"zu...], (1, 0): 'zucki' is not a"
			" valid value for type",
			base.parseFromString, (rscdef.Column,
				'<column name="foo" type="zucki"/>'))
	
	def testBadDisplayHintRejected(self):
		self.assertRaisesWithMsg(base.LiteralParseError, 
			"At [<column name=\"foo\" displayH...], (1, 0): 'xxyyz'"
			" is not a valid value for displayHint",
			base.parseFromString, (rscdef.Column,
				'<column name="foo" displayHint="xxyyz"/>'))
	
	def testBadColumnNameRejected(self):
		self.assertRaisesWithMsg(base.StructureError, 
			'At [<column name="foo x"/>], (1, 0):'
			" 'foo x' is not a valid column name" , 
			base.parseFromString, (rscdef.Column, '<column name="foo x"/>'))

	def testBadNullRejected(self):
		self.assertRaisesWithMsg(base.LiteralParseError,
			"At [<column name=\"x\" type=\"smal...], (1, 58): '.'"
			" is not a valid value for nullLiteral",
			base.parseFromString,
			(rscdef.Column, '<column name="x" type="smallint"><values nullLiteral='
				'"."/></column>'))

	def testNoManualSTC(self):
		self.assertRaisesWithMsg(base.StructureError,
			"At [<column name=\"x\" stcUtype=\"...], (1, 0):"
			" Cannot set stcUtype attributes from XML",
			base.parseFromString,
			(rscdef.Column, '<column name="x" stcUtype="ICRS"/>'))

	def testNoNameFailsSensibly(self):
		self.assertRaisesWithMsg(base.StructureError,
			"At [<column unit=\"d\"/>], (1, 18):"
			" You must set name on column elements",
			base.parseFromString,
			(rscdef.Column, '<column unit="d"/>'))

	def testNoMetaParent(self):
		t = testhelpers.getTestRD().getById("noname")
		self.assertRaises(base.StructureError, 
			t.getColumnByName("alpha").setMetaParent,
			(t,))


class ValuesTest(testhelpers.VerboseTest):
	"""tests for the rscdef.Values class and its interaction with Column.
	"""
	def testValues(self):
		col = base.parseFromString(rscdef.Column,
			'<column name="foo"><values min="-1.5" max="13.75"/></column>')
		self.assertEqual(col.values.min, -1.5)
		col = base.parseFromString(rscdef.Param,
			'<param name="foo" type="date"><values><option>'
			'2000-01-01</option><option>2000-01-02</option></values></param>')
		self.assertEqual(col.values.validValues, 
			set([datetime.date(2000, 1, 1), datetime.date(2000, 1, 2)]))
		self.assertRuns(col.validateValue, (datetime.date(2000, 1, 1),))
		self.assertRaises(base.ValidationError, col.validateValue, 
			(datetime.date(1999, 1, 1),))

	def testArrayDefault(self):
		col = base.parseFromString(rscdef.Column,
			'<column name="foo" type="integer[3]"><values default="1 2 3"/></column>')
		self.assertEqual(col.values.default, (1, 2, 3))


class ScriptTest(testhelpers.VerboseTest):
	"""tests for script elements 
	
	(but not actual scripting, that's somewhere else)
	"""
	def testOkScripts(self):
		s = base.parseFromString(scripting.Script, '<script type="beforeDrop"'
			' lang="SQL" name="test">drop table foo</script>')
		self.assertEqual(s.type, "beforeDrop")
		self.assertEqual(s.name, "test")
		self.assertEqual(s.content_, "drop table foo")

	def testBadScripts(self):
		self.assertRaises(base.StructureError, base.parseFromString,
			*(scripting.Script, '<script type="bad">xy</script>'))
		self.assertRaises(base.StructureError, base.parseFromString,
			*(scripting.Script, '<script name="bad">xy</script>'))


class TableDefTest(testhelpers.VerboseTest):
	"""tests for some basic aspects of table definitions.
	"""
	def testBasic(self):
		t = base.parseFromString(rscdef.TableDef, '<table id="test" onDisk="no"'
			' adql="Off" forceUnique="True" dupePolicy="check"'
			'><column name="ab"/>'
			' <column name="cd" ucd="meta.id"/></table>')
		self.assertEqual(t.id, "test")
		self.assertEqual(t.onDisk, False)
		self.assertEqual(t.adql, False)
		self.assertEqual(t.forceUnique, True)
		self.assertEqual(t.dupePolicy, "check")
		self.assertEqual(len(t.columns), 2)
		self.assertEqual(t.getColumnsByUCD("meta.id")[0].name, "cd")
		self.assertEqual(t.primary, ())

	def testDuplicateUCD(self):
		t = base.parseFromString(rscdef.TableDef, '<table id="t"><column name="x"'
			' ucd="meta.id"/><column name="y" ucd="meta.id"/>'
			' <column name="z" ucd="meta.id;meta.main"/></table>')
		self.assertEqual(len(t.getColumnsByUCD("meta.id")), 2)
		self.assertEqual(t.getColumnsByUCD("meta.id;meta.main")[0].name, "z")
		self.assertRaises(ValueError, t.macro_nameForUCD, "meta.id")

	def testColumnByUtype(self):
		t = base.parseFromString(rscdef.TableDef, '<table id="t">'
			' <column name="x" utype="foo:Bar.gaz"/>'
			' <column name="y" utype="foo:Quux"/>'
			' </table>')
		self.assertEqual(t.getByUtype("foo:quux").name, "y")

	def testParamByUtype(self):
		t = base.parseFromString(rscdef.TableDef, '<table id="t">'
			' <param name="x" utype="foo:Bar.gaz"/>'
			' <param name="y" type="text" utype="foo:Quux">value</param>'
			' </table>')
		self.assertEqual(t.getByUtype("foo:quux").value, "value")

	def testNotFoundByUtype(self):
		t = base.parseFromString(rscdef.TableDef, '<table id="t">'
			' <column name="x" utype="foo:Bar.gaz"/>'
			' <column name="y" utype="foo:Quux"/>'
			' </table>')
		self.assertRaisesWithMsg(base.NotFoundError,
			"column with utype 'stc:astrocoordsystem' could"
				" not be located in table t",
			t.getByUtype,
			("stc:AstroCoordSystem",))

	def testParamByName(self):
		t = base.parseFromString(rscdef.TableDef, '<table id="t">'
			' <param name="y"/><column name="x"/>'
			' </table>')
		self.assertEqual(t.getByName("y").name_, "param")
		self.assertEqual(t.getByName("x").name_, "column")

	def testRoles(self):
		t = base.parseFromString(rscdef.TableDef, '<table id="t"></table>')
		self.assertEqual(t.readProfiles, base.getConfig("db", "queryProfiles"))
		self.assertEqual(t.allProfiles, base.getConfig("db", "maintainers"))
		self.assert_(t.readProfiles is not base.getConfig("db", "queryProfiles"))
		self.assert_(t.allProfiles is not base.getConfig("db", "maintainers"))
		t = base.parseFromString(rscdef.TableDef, 
			'<table readProfiles="" id="test"></table>')
		self.assertEqual(t.readProfiles, set())
		t = base.parseFromString(rscdef.TableDef, 
			'<table allProfiles="x" id="test"></table>')
		self.assertEqual(t.allProfiles, set(["x"]))
		self.assertEqual(t.readProfiles, base.getConfig("db", "queryProfiles"))
		t = base.parseFromString(rscdef.TableDef, 
			'<table id="test" allProfiles="x" readProfiles="y,z"></table>')
		self.assertEqual(t.allProfiles, set(["x"]))
		self.assertEqual(t.readProfiles, set(["y", "z"]))

	def testADQL(self):
		t = base.parseFromString(rscdef.TableDef, '<table adql="Yes" id="t">'
			'</table>')
		self.assertEqual(t.adql, True)
		for pName in base.getConfig("db", "adqlProfiles"):
			self.assert_(pName in t.readProfiles)

	def testReservedWordBails(self):
		self.assertRaisesWithMsg(base.StructureError, 
			'At [<table id=\"abs\"/>], (1, 17): Reserved word'
			' abs is not allowed as a table name',
			base.parseFromString, (rscdef.TableDef, '<table id="abs"/>'))

	def testDuplicateColumns(self):
		# Behavior here: old column def is overwritten
		t = base.parseFromString(rscdef.TableDef, '<table id="t">'	
			'<column name="one" type="text"/><column name="one"/>'
			'</table>')
		fields = list(t)
		self.assertEqual(len(fields), 1)
		self.assertEqual(fields[0].type, "real")

	def testPrimary(self):
		t = base.parseFromString(rscdef.TableDef, '<table id="test" primary="a">'
			'<column name="a"/><column name="b"/></table>')
		self.assertEqual(t.primary, ["a",])
		t = base.parseFromString(rscdef.TableDef, '<table id="t" primary="a, b">'
			'<column name="a"/><column name="b"/></table>')
		self.assertEqual(t.primary, ["a", "b"])
		self.assertRaisesWithMsg(base.LiteralParseError,
			"At [<table id =\"t\" primary=\"a, ...], (1, 72):"
			" 'quatsch' is not a valid value for primary",
			base.parseFromString, (rscdef.TableDef, 
				'<table id ="t" primary="a, quatsch">'
				'<column name="a"/><column name="b"/></table>'))

	def testIndices(self):
		t = base.parseFromString(rscdef.TableDef, '<table id="test">'
			'<column name="a"/><column name="b"/><index columns="a"/></table>')
		self.assertEqual(t.indices[0].columns, ['a'])
		self.assertEqual(t.indices[0].dbname, 'test_a')
		self.assertEqual(t.indices[0].cluster, False)
		self.assertEqual(t.indexedColumns, set(['a']))

	def testForeignKeyMeta(self):
		rd = base.parseFromString(rscdesc.RD,
			"""<resource schema="test">
				<table id="xy">
					<column name="b"/><column name="c"/>
				</table>
				<table id="test">
					<column name="foo"/><column name="b"/>
					<foreignKey inTable="xy" source="foo,b"><dest>b,c </dest></foreignKey>
					<foreignKey inTable="data/test#adqltable" source="foo"
						metaOnly="True"/>
				</table>
			</resource>""")
		t = rd.tables[1]

		self.assertEqual(len(t.foreignKeys), 2)
		fk = t.foreignKeys[0]
		self.assertEqual(fk.source, ["foo", "b"])
		self.assertEqual(fk.dest, ["b", "c"])
		self.assertEqual(fk.destTableName, "test.xy")
		self.assertEqual(fk.isADQLKey, False)
		fk = t.foreignKeys[1]
		self.assertEqual(fk.source, ["foo"])
		self.assertEqual(fk.source, fk.dest)
		self.assertEqual(fk.destTableName, "test.adqltable")
		self.assertEqual(fk.isADQLKey, True)

	def testSTCCopy(self):
		t0 = base.parseFromString(rscdef.TableDef, '<table id="test">'
			'<stc>Position ICRS "a" "b"</stc>'
			'<column name="a"/><column name="b"/><index columns="a"/></table>')
		t = t0.copy(None)
		self.failUnless(t.getColumnByName("a").stc is
			t0.getColumnByName("a").stc)

	def testUnicodeDDL(self):
		t = base.parseFromString(rscdef.TableDef, '<table id="test">'
			'<column name="a" type="unicode"/></table>')
		testhelpers.getTestRD().adopt(t)
		self.assertEqual(t.getDDL(), "CREATE TABLE test.test (a TEXT)")

	def testTempDDL(self):
		t = base.parseFromString(rscdef.TableDef, '<table id="test"'
			' temporary="True"><column name="a"/></table>')
		testhelpers.getTestRD().adopt(t)
		self.assertEqual(t.getDDL(), "CREATE TEMP TABLE test (a real)")


class _QuotedNamesTable(testhelpers.TestResource):
	def make(self, ignored):
		return base.parseFromString(rscdef.TableDef, '<table id="t">'
			'<column name="quoted/id number" type="integer"/>'
			'<column name="quoted/table" type="text"/>'
			'<column name="quoted/Harmless"/>'
			'</table>')


class QuotedColumnNameTest(testhelpers.VerboseTest):
	resources = [("td", _QuotedNamesTable())]

	def testParsedAsQuoted(self):
		self.failUnless(isinstance(self.td.getColumnByName("id number").name,
			utils.QuotedName))
	
	def testPlainNameResolution(self):
		self.assertEqual(self.td.getColumnByName("id number").type, "integer")
	
	def testQuotedNameResolution(self):
		self.assertEqual(self.td.getColumnByName(
			utils.QuotedName("id number")).type, "integer")
	
	def testQuotedNameSensitive(self):
		self.assertRaises(base.NotFoundError, self.td.getColumnByName, 
			utils.QuotedName("harmless"))

	def testQuotedNameResolvesAgain(self):
		self.assertEqual(self.td.getColumnByName(
			utils.QuotedName("Harmless")).type, "real")

	def testInvalidNameRejected(self):
		self.assertRaisesWithMsg(base.StructureError,
			"At [<column name=\"%)#=\"/>], (1, 0): '%)#=' is not a valid column name",
			base.parseFromString,
			(rscdef.Column, '<column name="%)#="/>'))

	def testReservedNameWarns(self):
		with testhelpers.messageCollector() as msgs:
			base.parseFromString(rscdef.Column, '<column name="references"/>')
		self.assertEqual(msgs.events[0][0], 'Warning')
		self.assertTrue(msgs.events[0][1][0].startswith(
			"Column name 'references' conincides"))


class _ResTestTable(testhelpers.TestResource):
	def make(self, ignored):
		return base.parseFromString(rscdef.TableDef,
			"""<table id="restest"><column name="foo" type="text"/>
				<column name="bar" type="integer"/>
				<param name="foo">2</param><param name="pbar"/></table>""")


class TableNameResolutionTest(testhelpers.VerboseTest):
	resources = [("td", _ResTestTable())]

	def testColumnsResolved(self):
		res = parsecontext.resolveNameBased(self.td, "bar")
		self.failUnless(res is self.td.columns[1])

	def testParametersResolved(self):
		res = parsecontext.resolveNameBased(self.td, "pbar")
		self.failUnless(res is self.td.params[1])
	
	def testColumnsPreferred(self):
		res = parsecontext.resolveNameBased(self.td, "foo")
		self.failUnless(res is self.td.columns[0])

	def testFailureIsNotFound(self):
		self.assertRaisesWithMsg(base.NotFoundError,
		"column 'crazy_mess' could not be located in table restest",
		parsecontext.resolveNameBased,
		(self.td, "crazy_mess"))


class RdAttrTest(testhelpers.VerboseTest):
	"""tests for automatic inference of rd parents.
	"""
	def setUp(self):
		class TableContainer(base.Structure):
			name_ = "container"
			_table = base.StructAttribute("table", childFactory=rscdef.TableDef)

		class FakeRD(base.Structure):
			name_ = "rd"
			_table = base.StructAttribute("table", childFactory=rscdef.TableDef,
				default=None)
			_container = base.StructAttribute("c", childFactory=TableContainer)
			def __init__(self, parent):
				base.Structure.__init__(self, parent)
				self.rd = weakref.proxy(self)
			def getId(self):
				return id(self)

		self.FakeRD = FakeRD
		self.fakeRD = FakeRD(None)
	
	def testNoRd(self):
		t = rscdef.TableDef(None)
		self.assertEqual(t.rd, None)
	
	def testDirectParent(self):
		t = rscdef.TableDef(None)
		self.fakeRD.feedObject("table", t)
		self.assertEqual(t.rd.getId(), self.fakeRD.getId())
	
	def testIndirectParent(self):
		rd = base.parseFromString(self.FakeRD, '<rd><container><table id="t"/>'
			'</container></rd>')
		self.assertEqual(rd.c.table.rd.getId(), rd.getId())


class DataDescTest(testhelpers.VerboseTest):
	"""tests for creation of DataDesc objects.
	"""
	def testGrammars(self):
		dd = base.parseFromString(rscdef.DataDescriptor,
			'<data><nullGrammar/></data>')
		self.failUnless(isinstance(dd.grammar, rscdef.getGrammar("nullGrammar")))
		dd = base.parseFromString(rscdef.DataDescriptor,
			'<data><fitsProdGrammar qnd="True"/></data>')
		self.failUnless(
			isinstance(dd.grammar, rscdef.getGrammar("fitsProdGrammar")))
		dd = base.parseFromString(rscdef.DataDescriptor,
			'<data><dictlistGrammar/></data>')
		self.failUnless(isinstance(dd.grammar,
			rscdef.getGrammar("dictlistGrammar")))

	def testIgnorePats(self):
		dd = base.parseFromString(rscdef.DataDescriptor,
			'<data><sources pattern="*"><ignoreSources pattern="*foo*"/></sources>'
			'<nullGrammar/></data>')
		dd.sources.ignoredSources.prepare(None)
		self.failUnless(dd.sources.ignoredSources.isIgnored("kafoobar"))
		self.failIf(dd.sources.ignoredSources.isIgnored("kafobar"))
		self.failIf(dd.sources.ignoredSources.isIgnored("/baf/ooga/kafobar"))
		self.failUnless(dd.sources.ignoredSources.isIgnored("/bafooga/kafobar"))
		self.failUnless(dd.sources.ignoredSources.isIgnored("baga/kafobar.foo"))


class ParamTest(testhelpers.VerboseTest):
	def testReal(self):
		res = base.parseFromString(rscdef.Param,
			'<param name="u">3.0</param>')
		self.assertEqual(res.content_, "3.0")
		self.assertEqual(res.value, 3.0)

	def testNaNisNULL(self):
		res = base.parseFromString(rscdef.Param,
			'<param name="u">NaN</param>')
		self.assertEqual(res.getStringValue(), "")
		self.assertEqual(res.value, None)

	def testString(self):
		res = base.parseFromString(rscdef.Param,
			'<param name="u" type="text">some string</param>')
		self.assertEqual(res.value, "some string")

	def testTimestamp(self):
		res = base.parseFromString(rscdef.Param,
			'<param name="u" type="timestamp">1969-04-06T04:20:23</param>')
		self.assertEqual(res.value, datetime.datetime(1969, 4, 6, 4, 20, 23))

	def testDate(self):
		res = base.parseFromString(rscdef.Param,
			'<param name="u" type="date">1969-04-06</param>')
		self.assertEqual(res.value, datetime.date(1969, 4, 6))

	def testEmptyNotreq(self):
		res = base.parseFromString(rscdef.Param,
			'<param name="u" type="timestamp"/>')
		self.assertEqual(res.value, None)
	
	def testEmptyReq(self):
		self.assertRaisesWithMsg(base.StructureError,
			"At [<param name=\"u\" type=\"times...], (1, 50):"
			" Required value not given for param u",
			base.parseFromString,
			(rscdef.Param,
			'<param name="u" type="timestamp" required="True"/>'))

	def testBadLiteral(self):
		self.assertRaisesWithMsg(base.ValidationError,
			"Field u: u'nothing' is not a valid literal for u",
			base.parseFromString,
			(rscdef.Param,
			'<param name="u" type="integer">nothing</param>'))
	
	def testCopying(self):
		res = base.parseFromString(rscdef.TableDef,
			'<table><param name="foo" id="foo">2</param>'
			'<param original="foo" name="bar"/></table>')
		self.assertEqual(res.params[1].name, "bar")
		self.assertEqual(res.params[1].value, 2.0)

	def test__NULL__IsNull(self):
		par = base.parseFromString(rscdef.Param,
			'<param name="foo" type="text">__NULL__</param>')
		self.assertEqual(par.value, None)

	def testEmptyIsNotNull(self):
		par = base.parseFromString(rscdef.Param,
			'<param name="foo" type="text" required="True">__EMPTY__</param>')
		self.assertEqual(par.value, '')

	def testSpoint(self):
		par = base.parseFromString(rscdef.Param,
			'<param name="foo" type="text" xtype="adql:POINT">'
				'position ICRS 10 12</param>')
		self.assertAlmostEqual(par.value.x, 0.1745329251994)

	def testIntArray(self):
		par = base.parseFromString(rscdef.Param,
			'<param name="foo" type="integer[]">'
				'10 12 -130</param>')
		self.assertEqual(par.value, (10, 12, -130))

	def testFloatArray(self):
		par = base.parseFromString(rscdef.Param,
			'<param name="foo" type="real[2]">'
				'10. 12.</param>')
		self.assertEqual(par.value, (10., 12.))

	def testParseFromArray(self):
		par = base.parseFromString(rscdef.Param,
			'<param name="foo" type="integer[]"/>')
		par.set(['10', '12', '-130'])
		self.assertEqual(par.value, [10, 12, -130])

	def testParseFromFloatArray(self):
		par = base.parseFromString(rscdef.Param,
			'<param name="foo" type="real[2]"/>')
		par.set('10. 12.')
		self.assertEqual(par.value, (10., 12.))

	def testParseFromStringArray(self):
		par = base.parseFromString(rscdef.Param,
			'<param name="foo" type="text[]"/>')
		par.set(['a10', 'b12', 'c-130'])
		self.assertEqual(par.value, ['a10', 'b12', 'c-130'])


class GroupTest(testhelpers.VerboseTest):
	def testBasicColumn(self):
		t = base.parseFromString(rscdef.TableDef,
			"<table><column name='x'/><column name='y'/><column name='z'/>"
			"<group name='foo'><columnRef dest='y'/></group></table>")
		g = t.groups[0]
		self.assertEqual(g.name, "foo")
		self.assertEqual(g.columnRefs[0].key, "y")
		c = list(g.iterColumns())[0]
		self.assertEqual(c.type, "real")

	def testMultiGroups(self):
		t = base.parseFromString(rscdef.TableDef,
			"<table><column name='x'/><column name='y'/><column name='z'/>"
			"<group name='foo'><columnRef dest='y'/><columnRef dest='x'/></group>"
			"<group name='bar'><columnRef dest='x'/><columnRef dest='z'/></group>"
			"</table>")
		g = t.groups[0]
		self.assertEqual(g.name, "foo")
		self.assertEqual(len(g.columnRefs), 2)
		self.failUnless(t.columns[0] is list(g.iterColumns())[1])
		g = t.groups[1]
		self.assertEqual(g.name, "bar")

	def testColParams(self):
		t = base.parseFromString(rscdef.TableDef,
			"<table><column name='x'/><param name='y'>0.25</param>"
			"<column name='z'/>"
			"<group name='foo'><columnRef dest='x'/><paramRef dest='y'/>"
			"<param name='u'>32</param>"
			"</group></table>")
		g = t.groups[0]
		self.assertEqual(list(g.iterColumns())[0].name, "x")
		params = list(g.iterParams())
		self.assertEqual(params[0].name, "y")
		self.assertEqual(params[0].value, 0.25)
		self.assertEqual(params[1].name, "u")
		self.assertEqual(params[1].value, 32)
	
	def testBadReference(self):
		self.assertRaisesWithMsg(base.StructureError,
			"At [<table id='u'><column name=...], (1, 117): No param"
			" or field column in found in table u",
			base.parseFromString,
			(rscdef.TableDef,
			"<table id='u'><column name='x'/><column name='y'/><column name='z'/>"
			"<group name='foo'><columnRef dest='bad'/></group></table>"))

	def testNesting(self):
		t = base.parseFromString(rscdef.TableDef,
			"<table><column name='x'/><column name='y'/><column name='z'/>"
			"<group name='foo'><columnRef dest='y'/>"
			" <group name='bar'><columnRef dest='x'/><columnRef dest='z'/></group>"
			"</group></table>")
		g = t.groups[0]
		self.assertEqual(g.name, "foo")
		self.failUnless(list(g.iterColumns())[0] is t.columns[1])
		innerG = g.groups[0]
		self.assertEqual(innerG.name, "bar")
		columns = list(innerG.iterColumns())
		self.failUnless(columns[0] is t.columns[0])
		self.failUnless(columns[1] is t.columns[2])

	def testCopying(self):
		t = base.parseFromString(rscdef.TableDef,
			"<table><column name='x'/><column name='y'/><column name='z'/>"
			"<group ucd='test' name='foo'><columnRef dest='y'/>"
			"<param name='par'>20</param><group><columnRef dest='z'/></group>"
			"</group></table>")
		t2 = t.copy(None)
		g = t.groups[0]
		g2 = t2.groups[0]
		self.assertEqual(g.ucd, g2.ucd)
		self.failIf(g is g2)
		self.assertEqual(g2.name, "foo")
		self.assertEqual(g2.ucd, "test")
		self.failIf(list(g.iterColumns())[0] is list(g2.iterColumns())[0])
		self.failUnless(list(g2.iterColumns())[0] is t2.columns[1])
		self.failIf(g.groups[0] is g2.groups[0])
		self.failUnless(list(g2.groups[0].iterColumns())[0] is t2.columns[2])


class ChangeTest(testhelpers.VerboseTest):
	def testCopyTable(self):
		orig = base.parseFromString(rscdef.TableDef, '<table id="a" onDisk="True"'
			' temporary="True"><column name="col"/></table>')
		copy = orig.change(id="b")
		self.assertEqual(copy.id, "b")
		self.assertEqual(copy.onDisk, False)
		self.assertEqual(copy.temporary, True)
		self.assertEqual(copy.columns[0].name, "col")

	def testCopyWithRDAttr(self):
		rd = base.parseFromString(rscdesc.RD, '<resource resdir="/" schema="test">'
			'<data id="a" updating="True"><customGrammar module="foo"/>'
			'</data></resource>')
		copy = rd.getById("a").change(auto=False)
		self.assertEqual(copy.id, None)
		self.assertEqual(copy.auto, False)
		self.assertEqual(copy.updating, True)


if __name__=="__main__":
	testhelpers.main(ParamTest)
