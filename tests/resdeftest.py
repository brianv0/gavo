"""
Tests for the various structures in rscdef.
"""

from datetime import date
import os
import unittest
import weakref

import gavo
from gavo import base
from gavo import grammars
from gavo import rscdef
from gavo import rscdesc
from gavo import utils
from gavo.helpers import testhelpers
from gavo.rscdef import scripting



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

	def testWeirdDefaults(self):
		col = base.parseFromString(rscdef.Column,
			'<column name="foo"/>')
		self.assertEqual(col.tablehead, "foo")

	def testValidation(self):
		col = base.parseFromString(rscdef.Column, '<column name="foo"'
			' required="True"><values min="1" max="2"/></column>')
		self.assertRuns(col.validateValue, (1.5,))
		self.assertRuns(col.validateValue, (1,))
		self.assertRuns(col.validateValue, (2,))
		self.assertRaises(base.ValidationError, col.validateValue, -1)
		self.assertRaises(base.ValidationError, col.validateValue, 30)
		self.assertRaises(base.ValidationError, col.validateValue, None)
		col.required = False
		self.assertRuns(col.validateValue, (None,))

	def testRaises(self):
		self.assertRaisesWithMsg(base.LiteralParseError, 
			"At <internal source>, unknown position: 'zucki' is not a"
			" valid value for type",
			base.parseFromString, (rscdef.Column,
				'<column name="foo" type="zucki"/>'))
		self.assertRaisesWithMsg(base.LiteralParseError, 
			"At <internal source>, unknown position: 'xxyyz'"
			" is not a valid value for displayHint",
			base.parseFromString, (rscdef.Column,
				'<column name="foo" displayHint="xxyyz"/>'))
		self.assertRaisesWithMsg(base.StructureError, 
			'At <internal source>, unknown position: '
			"'foo x' is not a valid column name" , 
			base.parseFromString, (rscdef.Column, '<column name="foo x"/>'))


class ValuesTest(testhelpers.VerboseTest):
	"""tests for the rscdef.Values class and its interaction with Column.
	"""
	def testValues(self):
		col = base.parseFromString(rscdef.Column,
			'<column name="foo"><values min="-1.5" max="13.75"/></column>')
		self.assertEqual(col.values.min, -1.5)
		col = base.parseFromString(rscdef.Column,
			'<column name="foo" type="date"><values><option>'
			'2000-01-01</option><option>2000-01-02</option></values></column>')
		self.assertEqual(col.values.validValues, 
			set([date(2000, 1, 1), date(2000, 1, 2)]))
		self.assertRuns(col.validateValue, (date(2000, 1, 1),))
		self.assertRaises(base.ValidationError, col.validateValue, 
			(date(1999, 1, 1),))


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
	
	def testRoles(self):
		t = base.parseFromString(rscdef.TableDef, '<table id="t"></table>')
		self.assertEqual(t.readRoles, base.getConfig("db", "queryRoles"))
		self.assertEqual(t.allRoles, base.getConfig("db", "maintainers"))
		self.assert_(t.readRoles is not base.getConfig("db", "queryRoles"))
		self.assert_(t.allRoles is not base.getConfig("db", "maintainers"))
		t = base.parseFromString(rscdef.TableDef, 
			'<table readRoles="" id="test"></table>')
		self.assertEqual(t.readRoles, set())
		t = base.parseFromString(rscdef.TableDef, 
			'<table allRoles="x" id="test"></table>')
		self.assertEqual(t.allRoles, set(["x"]))
		self.assertEqual(t.readRoles, base.getConfig("db", "queryRoles"))
		t = base.parseFromString(rscdef.TableDef, 
			'<table id="test" allRoles="x" readRoles="y,z"></table>')
		self.assertEqual(t.allRoles, set(["x"]))
		self.assertEqual(t.readRoles, set(["y", "z"]))

	def testADQL(self):
		t = base.parseFromString(rscdef.TableDef, '<table adql="Yes" id="t">'
			'</table>')
		self.assertEqual(t.adql, True)
		for role in base.getConfig("db", "adqlRoles"):
			self.assert_(role in t.readRoles)

	def testReservedWordBails(self):
		self.assertRaisesWithMsg(base.StructureError, 
			'At <internal source>, last known position: 1, 17: Reserved word'
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

	def testQuotedIdentifier(self):
		t = base.parseFromString(rscdef.TableDef, '<table id="t">'
			'<column name="quoted/id number" type="integer"/>'
			'<column name="quoted/table" type="text"/>'
			'<column name="quoted/Harmless"/>'
			'</table>')
		self.failUnless(isinstance(t.getColumnByName("id number").name,
			utils.QuotedName))
		self.assertEqual(t.getColumnByName("id number").type, "integer")
		self.assertRaises(base.NotFoundError, t.getColumnByName, "harmless")
		self.assertEqual(t.getColumnByName("Harmless").type, "real")

	def testPrimary(self):
		t = base.parseFromString(rscdef.TableDef, '<table id="test" primary="a">'
			'<column name="a"/><column name="b"/></table>')
		self.assertEqual(t.primary, ["a",])
		t = base.parseFromString(rscdef.TableDef, '<table id="t" primary="a, b">'
			'<column name="a"/><column name="b"/></table>')
		self.assertEqual(t.primary, ["a", "b"])
		self.assertRaisesWithMsg(base.LiteralParseError,
			"At <internal source>, last known position: 1, 72:"
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

	def testForeignKey(self):
		class Anything(object): pass
		fakeRd = Anything()
		fakeRd.schema, fakeRd.parent, fakeRd.rd = "foo", None, fakeRd
		t = base.parseFromString(rscdef.TableDef, '<table id="test">'
			'<column name="a"/><column name="b"/><foreignKey table="xy"'
			' source="a,b"><dest>b,c </dest></foreignKey>'
			'<foreignKey table="zz" source="b"/></table>')
		t.parent = fakeRd
		self.assertEqual(len(t.foreignKeys), 2)
		fk = t.foreignKeys[0]
		self.assertEqual(fk.source, ["a", "b"])
		self.assertEqual(fk.dest, ["b", "c"])
		self.assertEqual(fk.table, "xy")
		fk = t.foreignKeys[1]
		self.assertEqual(fk.source, ["b"])
		self.assertEqual(fk.source, fk.dest)
		self.assertEqual(fk.table, "zz")


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
		dd.sources.ignoredSources.prepare()
		self.failUnless(dd.sources.ignoredSources.isIgnored("kafoobar"))
		self.failIf(dd.sources.ignoredSources.isIgnored("kafobar"))
		self.failIf(dd.sources.ignoredSources.isIgnored("/baf/ooga/kafobar"))
		self.failUnless(dd.sources.ignoredSources.isIgnored("/bafooga/kafobar"))
		self.failUnless(dd.sources.ignoredSources.isIgnored("baga/kafobar.foo"))


if __name__=="__main__":
	testhelpers.main(DataDescTest)
