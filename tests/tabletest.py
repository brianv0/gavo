"""
Tests for rsc.XTable
"""

import datetime

from gavo import base
from gavo import rsc
from gavo import rscdef
from gavo import rscdesc
from gavo import svcs

import testhelpers


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


class UniqueForcedTest(testhelpers.VerboseTest):
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
			[{"x": "aba", "y": "bab"}, {"x": "xyx", "y": "yxy"}])
		try:
			self.assertEqual(t.getRow("aba"), {"x": "aba", "y": "bab"})
			t.addRow({"x": "aba", "y": "bab"})
			self.assertEqual(t.getRow("aba"), {"x": "aba", "y": "bab"})
		finally:
			t.close()
	
	def testCheckRaises(self):
		td = self._makeTD('forceUnique="True"><column name="x" type='
			'"text"/><column name="y" type="text"/><primary>x</primary></table>')
		self.assertRaises(base.ValidationError, rsc.TableForDef, td, nometa=True,
			rows=[{"x": "aba", "y": "bab"}, {"x": "aba", "y": "yxy"}])
		t = rsc.TableForDef(td, rows=
			[{"x": "aba", "y": "bab"}, {"x": "xyx", "y": "yxy"}])
		try:
			self.assertRaisesWithMsg(base.ValidationError, 
				"Differing rows for primary key ('aba',); bax vs. bab",
				t.addRow, ({"x": "aba", "y": "bax"},))
		finally:
			t.close()

	def testDrop(self):
		td = self._makeTD('forceUnique="True" dupePolicy="drop">'
			'<column name="x" type="text"/><column name="y" type="text"/>'
			'<primary>x</primary></table>')
		t = rsc.TableForDef(td, nometa=True, rows=
			[{"x": "aba", "y": "bab"}, {"x": "xyx", "y": "yxy"}])
		try:
			self.assertEqual(t.getRow("aba"), {"x": "aba", "y": "bab"})
			t.addRow({"x": "aba", "y": "bax"})
			self.assertEqual(t.getRow("aba"), {"x": "aba", "y": "bab"})
		finally:
			t.close()

	def testOverwrite(self):
		td = self._makeTD('forceUnique="True">'
			'<dupePolicy>overwrite</dupePolicy><column name="x" type='
			'"text"/><column name="y" type="text"/><primary>x</primary></table>')
		t = rsc.TableForDef(td, nometa=True, rows=
			[{"x": "aba", "y": "bab"}, {"x": "xyx", "y": "yxy"}])
		try:
			self.assertEqual(t.getRow("aba"), {"x": "aba", "y": "bab"})
			t.addRow({"x": "aba", "y": "bax"})
			self.assertEqual(t.getRow("aba"), {"x": "aba", "y": "bax"})
		finally:
			t.close()

	def testCompoundKey(self):
		td = self._makeTD('forceUnique="True">'
			'<dupePolicy>overwrite</dupePolicy><column name="x" type='
			'"text"/><column name="n" type="integer"/><column name="y" type="text"/>'
			'<primary>x,n</primary></table>')
		t = rsc.TableForDef(td, nometa=True, rows=
			[{"x": "aba", "n": 1, "y": "bab"}, {"x": "aba", "n":2, "y": "yxy"}])
		try:
			t.addRow({"x": "aba", "n": 3, "y": "bab"})
			t.addRow({"x": "aba", "n": 1, "y": "aba"})
			self.assertEqual(t.getRow("aba", 1), {"x": "aba", "n": 1, "y": "aba"})
		finally:
			t.close()

	def testWithNull(self):
		td = self._makeTD('forceUnique="True"><column name="x" type='
			'"text"/><column name="y" type="text"/><primary>x</primary></table>')
		t = rsc.TableForDef(td, nometa=True, rows=
			[{"x": "aba", "y": None}, {"x": "xyx", "y": None}])
		try:
			self.assertEqual(t.getRow("aba"), {"x": "aba", "y": None})
			t.addRow({"x": "aba", "y": None})
			self.assertEqual(t.getRow("aba"), {"x": "aba", "y": None})
			t.addRow({"x": "aba", "y": "bab"})
			self.assertEqual(t.getRow("aba"), {"x": "aba", "y": None})
		finally:
			t.close()


class DBUniqueForcedTest(UniqueForcedTest):
	"""tests for correct handling of duplicate keys when uniqueness is enforced
	in DB tables
	"""
	_tt = '<resource schema="test"><table onDisk="True" id="bla" %s</resource>'

	def setUp(self):
		base.setDBProfile("test")

	def tearDown(self):
		base.SimpleQuerier().runIsolatedQuery("DROP TABLE test.bla")

	def testCheckRaises(self):
# For these, semantics between DB tables and InMemoryTables differ --
# DBTables currently raise other Exceptions, and partially at different
# times.
		td = self._makeTD('forceUnique="True"><column name="x" type='
			'"text"/><column name="y" type="text"/><primary>x</primary></table>')
		t = rsc.TableForDef(td, nometa=True, rows=
			[{"x": "aba", "y": "bab"}, {"x": "xyx", "y": "yxy"}])
		self.assertRaises(base.ValidationError, 
			t.addRow, {"x": "aba", "y": "bax"},)


class DBTableTest(testhelpers.VerboseTest):
	"""tests for creation, filling and takedown of DB tables.
	"""
	def setUp(self):
		base.setDBProfile("test")

	def _getRD(self):
		return base.parseFromString(rscdesc.RD, '<resource schema="testing">'
			'<table id="xy" onDisk="True">'
			'<column name="x" type="integer"/>'
			'<column name="y" type="text"/><primary>x</primary></table>'
			'</resource>')

	def testCreation(self):
		td = self._getRD().getTableDefById("xy")
		querier = base.SimpleQuerier()
		try:
			table = rsc.TableForDef(td, connection=querier.connection, nometa=True)
			self.assert_(querier.tableExists(td.getQName()))
		finally:
			querier.close() # implicit rollback
		self.assert_(not base.SimpleQuerier().tableExists(td.getQName()))

	def testFilling(self):
		td = self._getRD().getTableDefById("xy")
		table = rsc.TableForDef(td, nometa=True)
		table.addRow({'x': 100, 'y': "abc"})
		self.assertEqual([{'x': 100, 'y': "abc"}], [row for row in table])
		table.drop()
		table.commit()
		self.assert_(not base.SimpleQuerier().tableExists(td.getQName()))
	
	def testFeeding(self):
		td = self._getRD().getTableDefById("xy")
		table = rsc.TableForDef(td, nometa=True)
		try:
			table.feedRows([
				{'x': 100, 'y': "abc"},
				{'x': 200, 'y': "ab"},
				{'x': 50, 'y': "ab"}])
			self.assertEqual(3, len([row for row in table]))
		finally:
			table.drop()
			table.commit()


class DBTableQueryTest(testhelpers.VerboseTest):
	def setUp(self):
		self.rd = base.parseFromString(rscdesc.RD, 
			'<resource schema="testing">'
			'<table id="xy" onDisk="True">'
			'<column name="x" type="integer"/>'
			'<column name="y" type="text"/></table>'
			'<data id="xyData"><dictlistGrammar/><table ref="xy"/>'
			'<rowmaker id="d_xy" idmaps="x,y"/>'
			'<make table="xy" rowmaker="d_xy"/></data>'
			'</resource>')
		self.rd.sourceId = "testing"
		self.data = rsc.makeData(self.rd.getById("xyData"),
			forceSource=[{"x": 9, "y": ""}]+
				[{"x": i, "y": "x"*(9-i)} for i in range(10)])

	def tearDown(self):
		self.data.tables["xy"].drop().commit()

	def testPlainQuery(self):
		resdef = svcs.OutputTableDef.fromTableDef(
			self.rd.getTableDefById("xy"))
		res = rsc.makeTableForQuery(self.data.tables["xy"], resdef, "", {})
		self.assertEqual(len(res.rows), 11)
	
	def testDistinctQuery(self):
		resdef = svcs.OutputTableDef.fromTableDef(
			self.rd.getTableDefById("xy"))
		res = rsc.makeTableForQuery(self.data.tables["xy"], resdef, "", {},
			distinct=True)
		self.assertEqual(len(res.rows), 10)

	def testWithLimit(self):
		resdef = svcs.OutputTableDef.fromTableDef(
			self.rd.getTableDefById("xy"))
		res = rsc.makeTableForQuery(self.data.tables["xy"], resdef, "", {},
			limits=("ORDER BY y LIMIT %(limit_)s", {"limit_": 4}))
		self.assertEqual(len(res.rows), 4)
		self.assertEqual(res.rows[-1], {u'y': u'xx', u'x': 7})

	def testWithWhere(self):
		resdef = svcs.OutputTableDef.fromTableDef(
			self.rd.getTableDefById("xy"))
		res = rsc.makeTableForQuery(self.data.tables["xy"], resdef, 
			"x=%(x)s", {"x":9})
		self.assertEqual(len(res.rows), 2)


class FixupTest(testhelpers.VerboseTest):
	"""tests for column fixup attributes.
	"""
	def testInvalidFixup(self):
		self.assertRaisesWithMsg(base.LiteralParseError, 
			"'9m+5s' is not correct python syntax", base.parseFromString,
			(rscdef.TableDef, 
			'<table id="test"><column name="ab" fixup="9m+5s"/></table>'))
	
	def testSimpleFixup(self):
		td = base.parseFromString(rscdef.TableDef, 
			'<table id="test" onDisk="True" temporary="True">'
			'<column name="ab" type="text" fixup="\'ab\'+___"/></table>')
		t = rsc.TableForDef(td, rows=[{"ab": "xy"}, {"ab": "zz"}])
		try:
			self.assertEqual(
				list(t.iterQuery(svcs.OutputTableDef.fromTableDef(td), "")),
				[{u'ab': u'abxy'}, {u'ab': u'abzz'}])
		finally:
			t.drop()
			t.close()

	def testMultiFixup(self):
		td = base.parseFromString(rscdef.TableDef, 
			'<table id="testMulti" onDisk="True" temporary="True">'
			'<column name="ab" type="date"'
			' fixup="___+datetime.timedelta(days=1)"/>'
			'<column name="x" type="integer" fixup="___-2"/></table>')
		t = rsc.TableForDef(td, rows=[
			{"ab": datetime.date(2002, 2, 2), "x": 14}, 
			{"ab": datetime.date(2002, 2, 3), "x": 15}])
		try:
			self.assertEqual(
				list(t.iterQuery(svcs.OutputTableDef.fromTableDef(td), "")), [
					{u'x': 12, u'ab': datetime.date(2002, 2, 3)}, 
					{u'x': 13, u'ab': datetime.date(2002, 2, 4)}])
		finally:
			t.drop()
			t.close()


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
		self.assertEqual(td.getColumnByName("ra").stc.spaceFrame,
			"ICRS")
		self.assertEqual(td.getColumnByName("mag").stc, None)

	def testComplexSTC(self):
		td = base.parseFromString(rscdef.TableDef, 
			'<table id="complex">'
			'  <stc>TimeInterval TT "start" "end" Position ICRS "ra" "dec"'
			'    Error "e_ra" "e_dec"</stc>'
			'  <stc>PositionInterval FK5 "raMin" "decMin"</stc>'
			'  <column name="ra" unit="deg"/>'
			'  <column name="dec" unit="deg"/>'
			'  <column name="start" type="timestamp"/>'
			'  <column name="end" type="timestamp"/>'
			'  <column name="raMin" unit="deg"/>'
			'  <column name="decMin" unit="deg"/>'
			'  <column name="mag" unit="mag"/>'
			'</table>')
		bigSTC = td.getColumnByName("ra").stc
		self.assertEqual(td.getColumnByName("ra").stc.spaceFrame,
			"ICRS")
		self.assertEqual(td.getColumnByName("mag").stc, None)
		self.assertEqual(td.getColumnByName("start").stc, bigSTC)
		self.assertEqual(td.getColumnByName("end").stc, bigSTC)
		self.assertEqual(td.getColumnByName("raMin").stc.spaceFrame, "FK5")

	def testGeometrySTC(self):
		td = base.parseFromString(rscdef.TableDef,
			'<table id="geo">'
			'  <stc>Box ICRS [bbox]</stc>'
			'  <column name="bbox" type="box"/>'
			'</table>')
		self.assertEqual(td.getColumnByName("bbox").stc.spaceFrame, "ICRS")
	
	def testCopying(self):
		td = base.parseFromString(rscdef.TableDef,
			'<table id="geo">'
			'  <stc>Box ICRS [bbox]</stc>'
			'  <column name="bbox" type="box"/>'
			'</table>')
		tdc = td.copy(None)
		self.assertEqual(tdc.getColumnByName("bbox").stc.spaceFrame, "ICRS")
		self.failUnless(tdc.getColumnByName("bbox").stc is
			td.getColumnByName("bbox").stc)

# test exc. with duplicate names.

if __name__=="__main__":
	testhelpers.main(STCTest)
