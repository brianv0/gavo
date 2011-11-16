"""
Tests for rsc.XTable
"""

import datetime

from gavo.helpers import testhelpers

from gavo import base
from gavo import rsc
from gavo import rscdef
from gavo import rscdesc
from gavo import svcs
from gavo.stc import dm

import tresc

class MemoryPrimaryKeyTest(testhelpers.VerboseTest):
	"""tests for handling of primary keys on in-memory tables.
	"""
	def testAtomicPrimary(self):
		td = base.parseFromString(rscdef.TableDef, '<table><column name="x" type='
			'"text"/><column name="y" type="text"/><primary>x</primary></table>')
		t = rsc.TableForDef(td, 
			rows=[{"x": "aba", "y": "bab"}, {"x": "xyx", "y": "yxy"}])
		self.assertEqual(t.getRow("aba"), {"x": "aba", "y": "bab"})
		self.assertRaises(KeyError, t.getRow)
		self.assertRaises(KeyError, t.getRow, "wommo")
		t.addRow({"x": "wommo"})
		self.assertEqual(t.getRow("wommo"), {"x": "wommo"})
		t = rsc.TableForDef(td,
			rows=[{"x": "aba", "y": "bab"}, {"x": "xyx", "y": "yxy"}], 
			suppressIndex=True)
		self.assertRaises(ValueError, t.getRow, "aba")

	def testCompoundPrimary(self):
		td = base.parseFromString(rscdef.TableDef, '<table><column name="x" type='
			'"text"/><column name="y" type="text"/><primary>x,y</primary></table>')
		t = rsc.TableForDef(td, rows=
			[{"x": "aba", "y": "bab"}, {"x": "xyx", "y": "yxy"}])
		self.assertEqual(t.getRow("aba", "bab"), {"x": "aba", "y": "bab"})
		self.assertRaises(KeyError, t.getRow, "bab", "aba")
		self.assertRaises(KeyError, t.getRow, "xyx")


class UniqueForcedTest(tresc.TestWithDBConnection):
	"""tests for correct handling of duplicate keys when uniqueness is enforced.
	"""
	_tt = '<resource schema="test"><table id="bla" %s</resource>'

	def _makeTD(self, tdLiteral):
		rd = base.parseFromString(rscdesc.RD, 
			self._tt%tdLiteral)
		return rd.getById("bla")

	def testCheckOk(self):
		td = self._makeTD('forceUnique="True"><column name="x" type='
			'"text"/><column name="y" type="text"/><primary>x</primary></table>')
		t = rsc.TableForDef(td, nometa=True, rows=
			[{"x": "aba", "y": "bab"}, {"x": "xyx", "y": "yxy"}],
			connection=self.conn)
		self.assertEqual(t.getRow("aba"), {"x": "aba", "y": "bab"})
		t.addRow({"x": "aba", "y": "bab"})
		self.assertEqual(t.getRow("aba"), {"x": "aba", "y": "bab"})
	
	def testCheckRaises(self):
		td = self._makeTD('forceUnique="True"><column name="x" type='
			'"text"/><column name="y" type="text"/><primary>x</primary></table>')
		self.assertRaises(base.ValidationError, rsc.TableForDef, td, nometa=True,
			rows=[{"x": "aba", "y": "bab"}, {"x": "aba", "y": "yxy"}],
			connection=self.conn)
		t = rsc.TableForDef(td, rows=
			[{"x": "aba", "y": "bab"}, {"x": "xyx", "y": "yxy"}],
			connection=self.conn)
		self.assertRaisesWithMsg(base.ValidationError, 
			"Differing rows for primary key ('aba',); bax vs. bab",
			t.addRow, ({"x": "aba", "y": "bax"},))

	def testDrop(self):
		td = self._makeTD('forceUnique="True" dupePolicy="drop">'
			'<column name="x" type="text"/><column name="y" type="text"/>'
			'<primary>x</primary></table>')
		t = rsc.TableForDef(td, nometa=True, rows=
			[{"x": "aba", "y": "bab"}, {"x": "xyx", "y": "yxy"}],
			connection=self.conn)
		self.assertEqual(t.getRow("aba"), {"x": "aba", "y": "bab"})
		t.addRow({"x": "aba", "y": "bax"})
		self.assertEqual(t.getRow("aba"), {"x": "aba", "y": "bab"})

	def testOverwrite(self):
		td = self._makeTD('forceUnique="True">'
			'<dupePolicy>overwrite</dupePolicy><column name="x" type='
			'"text"/><column name="y" type="text"/><primary>x</primary></table>')
		t = rsc.TableForDef(td, nometa=True, rows=
			[{"x": "aba", "y": "bab"}, {"x": "xyx", "y": "yxy"}],
			connection=self.conn)
		self.assertEqual(t.getRow("aba"), {"x": "aba", "y": "bab"})
		t.addRow({"x": "aba", "y": "bax"})
		self.assertEqual(t.getRow("aba"), {"x": "aba", "y": "bax"})

	def testCompoundKey(self):
		td = self._makeTD('forceUnique="True">'
			'<dupePolicy>overwrite</dupePolicy><column name="x" type='
			'"text"/><column name="n" type="integer"/><column name="y" type="text"/>'
			'<primary>x,n</primary></table>')
		t = rsc.TableForDef(td, nometa=True, rows=
			[{"x": "aba", "n": 1, "y": "bab"}, {"x": "aba", "n":2, "y": "yxy"}],
			connection=self.conn)
		t.addRow({"x": "aba", "n": 3, "y": "bab"})
		t.addRow({"x": "aba", "n": 1, "y": "aba"})
		self.assertEqual(t.getRow("aba", 1), {"x": "aba", "n": 1, "y": "aba"})

	def testWithNull(self):
		td = self._makeTD('forceUnique="True"><column name="x" type='
			'"text"/><column name="y" type="text"/><primary>x</primary></table>')
		t = rsc.TableForDef(td, nometa=True, rows=
			[{"x": "aba", "y": None}, {"x": "xyx", "y": None}],
			connection=self.conn)
		self.assertEqual(t.getRow("aba"), {"x": "aba", "y": None})
		t.addRow({"x": "aba", "y": None})
		self.assertEqual(t.getRow("aba"), {"x": "aba", "y": None})
		t.addRow({"x": "aba", "y": "bab"})
		self.assertEqual(t.getRow("aba"), {"x": "aba", "y": None})


class WrapTest(testhelpers.VerboseTest):
	"""tests for wrapping of Tables in Data.
	"""
	def testWithRd(self):
		table = rsc.TableForDef(
			testhelpers.getTestRD().getById("typesTable").change(onDisk=False))
		data = rsc.wrapTable(table)
		self.assertEqual(len(data.tables), 1)
		self.assertEqual(str(data.getMeta("test.inRd")), "from Rd")
	
	def testWithRdSource(self):
		origTable = rsc.TableForDef(
			testhelpers.getTestRD().getById("typesTable").change(onDisk=False))
		newTD = rscdef.makeTDForColumns(
			"copy", origTable.tableDef.columns)
		data = rsc.wrapTable(rsc.TableForDef(newTD), origTable.tableDef)
		self.assertEqual(data.dd.rd.schema, "test")
		self.assertEqual(data.getPrimaryTable().tableDef.rd.schema, "test")


class DBUniqueForcedTest(UniqueForcedTest):
	"""tests for correct handling of duplicate keys when uniqueness is enforced
	in DB tables
	"""
	_tt = '<resource schema="test"><table onDisk="True" id="bla" %s</resource>'

	def testCheckRaises(self):
# For these, semantics between DB tables and InMemoryTables differ --
# DBTables currently raise other Exceptions, and partially at different
# times.
		td = self._makeTD('forceUnique="True"><column name="x" type='
			'"text"/><column name="y" type="text"/><primary>x</primary></table>')
		t = rsc.TableForDef(td, nometa=True, rows=
			[{"x": "aba", "y": "bab"}, {"x": "xyx", "y": "yxy"}],
			connection=self.conn)
		self.assertRaises(base.ValidationError, 
			t.addRow, {"x": "aba", "y": "bax"},)


class DBTableTest(tresc.TestWithDBConnection):
	"""tests for creation, filling and takedown of DB tables.
	"""
	def _getRD(self):
		return base.parseFromString(rscdesc.RD, '<resource schema="testing">'
			'<table id="xy" onDisk="True">'
			'<column name="x" type="integer"/>'
			'<column name="y" type="text"/><primary>x</primary></table>'
			'</resource>')

	def testCreation(self):
		td = self._getRD().getTableDefById("xy")
		querier = base.SimpleQuerier(connection=self.conn)
		table = rsc.TableForDef(td, connection=self.conn, nometa=True)
		self.assert_(querier.tableExists(td.getQName()))
		table.drop()
		self.assert_(not querier.tableExists(td.getQName()))

	def testFilling(self):
		td = self._getRD().getTableDefById("xy")
		table = rsc.TableForDef(td, nometa=True, connection=self.conn)
		table.recreate()
		table.addRow({'x': 100, 'y': "abc"})
		self.assertEqual([{'x': 100, 'y': "abc"}], [row for row in table])
	
	def testFeeding(self):
		td = self._getRD().getTableDefById("xy")
		table = rsc.TableForDef(td, nometa=True, connection=self.conn)
		table.recreate()
		table.feedRows([
			{'x': 100, 'y': "abc"},
			{'x': 200, 'y': "ab"},
			{'x': 50, 'y': "ab"}])
		self.assertEqual(3, len([row for row in table]))


class DBTableQueryTest(tresc.TestWithDBConnection):
	def setUp(self):
		tresc.TestWithDBConnection.setUp(self)
		self.rd = base.parseFromString(rscdesc.RD, 
			'<resource schema="testing">'
			'<table id="xy" onDisk="True">'
			'<column name="x" type="integer"/>'
			'<column name="y" type="text"/></table>'
			'<data id="xyData"><dictlistGrammar/><table original="xy"/>'
			'<rowmaker id="d_xy" idmaps="x,y"/>'
			'<make table="xy" rowmaker="d_xy"/></data>'
			'</resource>')
		self.rd.sourceId = "testing"
		self.data = rsc.makeData(self.rd.getById("xyData"),
			forceSource=[{"x": 9, "y": ""}]+
				[{"x": i, "y": "x"*(9-i)} for i in range(10)],
				connection=self.conn)

	def testPlainQuery(self):
		resdef = svcs.OutputTableDef.fromTableDef(
			self.rd.getTableDefById("xy"), None)
		res = rsc.makeTableForQuery(self.data.tables["xy"], resdef, "", {})
		self.assertEqual(len(res.rows), 11)
	
	def testDistinctQuery(self):
		resdef = svcs.OutputTableDef.fromTableDef(
			self.rd.getTableDefById("xy"), None)
		res = rsc.makeTableForQuery(self.data.tables["xy"], resdef, "", {},
			distinct=True, connection=self.conn)
		self.assertEqual(len(res.rows), 10)

	def testWithLimit(self):
		resdef = svcs.OutputTableDef.fromTableDef(
			self.rd.getTableDefById("xy"), None)
		res = rsc.makeTableForQuery(self.data.tables["xy"], resdef, "", {},
			limits=("ORDER BY y LIMIT %(limit_)s", {"limit_": 4}))
		self.assertEqual(len(res.rows), 4)
		self.assertEqual(res.rows[-1], {u'y': u'xx', u'x': 7})

	def testWithWhere(self):
		resdef = svcs.OutputTableDef.fromTableDef(
			self.rd.getTableDefById("xy"), None)
		res = rsc.makeTableForQuery(self.data.tables["xy"], resdef, 
			"x=%(x)s", {"x":9})
		self.assertEqual(len(res.rows), 2)


class FixupTest(tresc.TestWithDBConnection):
	def testInvalidFixup(self):
		self.assertRaisesWithMsg(base.BadCode, 
			"At (1, 50):"
			" Bad source code in function (invalid syntax (<string>, line 2))",
			base.parseFromString, (rscdef.TableDef, 
			'<table id="test"><column name="ab" fixup="9m+5s"/></table>'))
	
	def testSimpleFixup(self):
		td = base.parseFromString(rscdef.TableDef, 
			'<table id="test" onDisk="True" temporary="True">'
			'<column name="ab" type="text" fixup="\'ab\'+___"/></table>')
		t = rsc.TableForDef(td, rows=[{"ab": "xy"}, {"ab": "zz"}],
			connection=self.conn)
		self.assertEqual(
			list(t.iterQuery(svcs.OutputTableDef.fromTableDef(td, None), "")),
			[{u'ab': u'abxy'}, {u'ab': u'abzz'}])

	def testMultiFixup(self):
		td = base.parseFromString(rscdef.TableDef, 
			'<table id="testMulti" onDisk="True" temporary="True">'
			'<column name="ab" type="date"'
			' fixup="___+datetime.timedelta(days=1)"/>'
			'<column name="x" type="integer" fixup="___-2"/>'
			'<column name="t" type="text" fixup="___ or \'\\test\'"/>'
			'</table>')
		t = rsc.TableForDef(td, rows=[
			{"ab": datetime.date(2002, 2, 2), "x": 14, 't': "ab"}, 
			{"ab": datetime.date(2002, 2, 3), "x": 15, 't': None}],
			connection=self.conn)
		self.assertEqual(
			list(t.iterQuery(svcs.OutputTableDef.fromTableDef(td, None), "")), [
				{u'x': 12, u'ab': datetime.date(2002, 2, 3),
					't': 'ab'}, 
				{u'x': 13, u'ab': datetime.date(2002, 2, 4),
					't': 'test macro expansion'}])


class STCTest(testhelpers.VerboseTest):
	"""tests for various aspects of STC handling.
	"""
	def testSimpleSTC(self):
		td = base.parseFromString(rscdef.TableDef, 
			'<table id="simple">'
			'  <stc>Position ICRS "ra" "dec"</stc>'
			'  <column name="ra" unit="deg"/>'
			'  <column name="dec" unit="deg"/>'
			'  <column name="mag" unit="mag"/>'
			'</table>')
		self.assertEqual(td.getColumnByName("ra").stc.sys.spaceFrame.refFrame, 
			"ICRS")
		self.assertEqual(td.getColumnByName("mag").stc, None)

	def testErrorCircle(self):
		td = base.parseFromString(rscdef.TableDef, 
			'<table id="errors">'
			'  <stc>Position ICRS 20 20 Error "e_pos" "e_pos"</stc>'
			'  <column name="e_pos"/>'
			'</table>')
		posSTC = td.getColumnByName("e_pos").stc
		self.failUnless(isinstance(posSTC.place.error, dm.RadiusWiggle))

	def testComplexSTC(self):
		td = base.parseFromString(rscdef.TableDef, 
			'<table id="complex">'
			'  <stc>TimeInterval TT "start" "end" Position ICRS "ra" "dec"'
			'    Error "e_ra" "e_dec"</stc>'
			'  <stc>PositionInterval FK5 "raMin" "decMin"</stc>'
			'  <column name="ra" unit="deg"/>'
			'  <column name="dec" unit="deg"/>'
			'  <column name="e_ra" unit="deg"/>'
			'  <column name="e_dec" unit="deg"/>'
			'  <column name="start" type="timestamp"/>'
			'  <column name="end" type="timestamp"/>'
			'  <column name="raMin" unit="deg"/>'
			'  <column name="decMin" unit="deg"/>'
			'  <column name="mag" unit="mag"/>'
			'</table>')
		bigSTC = td.getColumnByName("ra").stc
		self.assertEqual(td.getColumnByName("ra").stc.sys.spaceFrame.refFrame, "ICRS")
		self.assertEqual(td.getColumnByName("mag").stc, None)
		self.assertEqual(td.getColumnByName("start").stc, bigSTC)
		self.assertEqual(td.getColumnByName("end").stc, bigSTC)
		self.assertEqual(td.getColumnByName("start").stc.sys.timeFrame.timeScale,
			"TT")
		self.assertEqual(td.getColumnByName("raMin").stc.sys.spaceFrame.refFrame, 
			"FK5")

	def testGeometrySTC(self):
		td = base.parseFromString(rscdef.TableDef,
			'<table id="geo">'
			'  <stc>Box ICRS [bbox]</stc>'
			'  <column name="bbox" type="box"/>'
			'</table>')
		self.assertEqual("ICRS",
			td.getColumnByName("bbox").stc.sys.spaceFrame.refFrame), 
	
	def testCopying(self):
		td = base.parseFromString(rscdef.TableDef,
			'<table id="geo">'
			'  <stc>Box ICRS [bbox]</stc>'
			'  <column name="bbox" type="box"/>'
			'</table>')
		tdc = td.copy(None)
		self.assertEqual(tdc.getColumnByName("bbox").stc.sys.spaceFrame.refFrame, 
			"ICRS")
		self.failUnless(tdc.getColumnByName("bbox").stc is
			td.getColumnByName("bbox").stc)


class _ParamTD(testhelpers.TestResource):
	def make(self, ignored):
		return base.parseFromString(rscdef.TableDef, 
			'<table id="u"><param name="i" type="integer"/>'
			'<param name="d" type="timestamp">'
			'2011-11-11T11:11:11</param>'
			'<param name="s" type="text"/></table>')


class ParamTest(testhelpers.VerboseTest):
	resources = [("td", _ParamTD())]

	def testPlain(self):
		table = rsc.TableForDef(self.td)
		self.assertEqual(table.getParam("i"), None)
		self.assertEqual(table.getParam("d"), datetime.datetime(
			2011, 11, 11, 11, 11, 11))
	
	def testNoClobber(self):
		table = rsc.TableForDef(self.td)
		table.setParam("i", 10)
		self.assertEqual(table.getParam("i"), 10)
		table2 = rsc.TableForDef(self.td)
		self.assertEqual(table2.getParam("i"), None)
	
	def testParamCons(self):
		table = rsc.TableForDef(self.td, params={
				"i": 10, "d": "2010-10-10T10:10:10"})
		self.assertEqual(table.getParam("i"), 10)
		self.assertEqual(table.getParam("d"), datetime.datetime(
			2010, 10, 10, 10, 10, 10))
	
	def testSetParam(self):
		table = rsc.TableForDef(self.td)
		table.setParam("i", 10)
		table.setParam("d", "2010-10-10T10:10:10")
		self.assertEqual(table.getParam("i"), 10)
		self.assertEqual(table.getParam("d"), datetime.datetime(
			2010, 10, 10, 10, 10, 10))

	def testSetParamFail(self):
		table = rsc.TableForDef(self.td)
		self.assertRaisesWithMsg(base.NotFoundError,
		"column 'doric' could not be located in table u",
		table.setParam,
		("doric", 10))

	def testMacro(self):
		table = rsc.TableForDef(self.td)
		table.setParam("s", r"\metaString{publisherID}")
		self.assertEqual(table.getParam("s"), 
			base.getMetaText(table, "publisherID"))


class QueryTableTest(testhelpers.VerboseTest):
	resources = [("basetable", tresc.csTestTable)]

	def testBasic(self):
		table = rsc.QueryTable(self.basetable.tableDef, 
			"SELECT * FROM %s"%self.basetable.tableDef.getQName(),
			connection=self.basetable.connection)
		rows = list(table)
		self.failUnless(isinstance(rows[0], dict))

	def testFromColumns(self):
		table = rsc.QueryTable.fromColumns(
			[self.basetable.tableDef.getColumnByName("alpha"),
				{"name": "mag2", "ucd": "phot.mag;times.two"}],
			"SELECT alpha, mag*2 FROM %s"%self.basetable.tableDef.getQName(),
			connection=self.basetable.connection)

	def testRepeatedIteration(self):
		table = rsc.QueryTable(self.basetable.tableDef, 
			"SELECT * FROM %s"%self.basetable.tableDef.getQName(),
			connection=self.basetable.connection)
		rows = list(table)
		rows = list(table)
		self.failUnless(isinstance(rows[0], dict))

	def testRefusesRows(self):
		self.assertRaisesWithMsg(base.Error,
			"QueryTables cannot be constructed with rows",
			rsc.QueryTable,
			(None, ""),
			rows=[])


if __name__=="__main__":
	testhelpers.main(STCTest)
