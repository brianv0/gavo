"""
Some tests for votable production.
"""

from cStringIO import StringIO
import datetime
import os
import pkg_resources
import re
import unittest

from gavo import base
from gavo import rsc
from gavo import rscdef
from gavo import rscdesc
from gavo import utils
from gavo import votable
from gavo.formats import votableread, votablewrite
from gavo.utils import ElementTree

import testhelpers

class _TestVOTable(testhelpers.TestResource):
	"""Used in VOTableTest.
	"""

	testData="""some silly test data
-33  -3400abc
23829328.9xxy
     22      
          nas
"""

	rdLiteral = """
		<resource resdir="%s" schema="test">
			<meta name="description">Some test data for VOTables.</meta>
			<meta name="_legal">Hands off this fascinating data</meta>
			<table id="foo">
				<meta name="note" tag="1">Note 1</meta>
				<meta name="note" tag="2">Note 2</meta>
				<column name="anInt" type="integer"
					description="This is a first data field" note="1"
					xtype="test:junk"/>
				<column name="aFloat"
					description="This ain't &amp;alpha; for sure." note="1"/>
				<column name="bla" type="text" note="2"/>
			</table>
			<data id="bar">
				<meta name="_infolink">http://vo.org/x?a=b&amp;c=d</meta>
				<columnGrammar topIgnoredLines="1">
					<col key="anInt">1-5</col>
					<col key="aFloat">6-10</col>
					<col key="bla">11-13</col>
				</columnGrammar>
				<rowmaker id="_foo" idmaps="*"/>
				<make table="foo" rowmaker="_foo"/>
			</data>
		</resource>"""%os.path.abspath("data")

	def _makeRD(self):
		"""returns a test resource descriptor.
		"""
		return base.parseFromString(rscdesc.RD, self.rdLiteral)

	def make(self, ignored):
		rd = self._makeRD()
		dataSet = rsc.makeData(rd.getById("bar"), 
			forceSource=StringIO(self.testData))
		rawVOTable = votablewrite.getAsVOTable(dataSet, tablecoding="td")
		tree = ElementTree.fromstring(rawVOTable)
		return rawVOTable, tree

_testVOTable = _TestVOTable()


class VOTableTest(testhelpers.VerboseTest, testhelpers.XSDTestMixin):

	resources = [("testData", _testVOTable)]

	def testValidates(self):
		"""test for validity of the generated VOTable.
		"""
		self.assertValidates(self.testData[0])

	def testNullvalues(self):
		"""tests for correct serialization of Null values.
		"""
		tree = self.testData[1]
		tbldata = tree.find(".//%s"%votable.voTag("TABLEDATA"))
		self.assertEqual(tbldata[3][1].text, 'NaN', "NaN isn't rendered as"
			" NULL")
		fields = tree.findall(".//%s"%votable.voTag("FIELD"))
		f0Null = fields[0].find(str(votable.voTag("VALUES"))).get("null")
		self.assertEqual(tbldata[2][0].text, f0Null)

	def testRanges(self):
		"""tests for ranges given in VALUES.
		"""
		tree = self.testData[1]
		fields = tree.findall(".//%s"%votable.voTag("FIELD"))
		f0 = fields[0].find(str(votable.voTag("VALUES")))
		self.assertEqual(f0.find(str(votable.voTag("MIN"))).get("value"), "-33",
			"integer minimum bad")
		self.assertEqual(f0.find(str(votable.voTag("MAX"))).get("value"), "23829",
			"integer maximum bad")
		f1 = fields[1].find(str(votable.voTag("VALUES")))
		self.assertEqual(f1.find(str(votable.voTag("MIN"))).get("value"), "-3400.0",
			"float minimum bad")
		self.assertEqual(f1.find(str(votable.voTag("MAX"))).get("value"), "328.9",
			"float maximum bad")
		self.assertEqual(fields[2].find(str(votable.voTag("VALUES"))), None,
			"VALUES element given for string data")

	def testNotes(self):
		tree = self.testData[1]
		groups = tree.findall(".//%s"%votable.voTag("GROUP"))
		self.assertEqual(groups[0].get("name"), "note-1")
		self.assertEqual(groups[0][0].text, "Note 1")
		self.assertEqual(groups[0][1].get("ref"), "anInt")
		self.assertEqual(groups[0][2].get("ref"), "aFloat")
		self.assertEqual(groups[1][0].text, "Note 2")
		self.assertEqual(groups[1][1].get("ref"), "bla")

	def testXtype(self):
		tree = self.testData[1]
		intCol = tree.findall(".//%s"%votable.voTag("FIELD"))[0]
		self.assertEqual(intCol.get("xtype"), "test:junk")


class _ImportTestData(testhelpers.TestResource):
	def __init__(self, fName):
		self.fName = fName
		testhelpers.TestResource.__init__(self)

	def make(self, ignored):
		try:
			conn = base.getDefaultDBConnection()
			tableDef = votableread.uploadVOTable("votabletest", 
				open(self.fName), conn).tableDef
			querier = base.SimpleQuerier(connection=conn)
			data = list(querier.query("select * from votabletest"))
		finally:
			if not conn.closed:
				conn.close()
		return tableDef, data


class ImportTest(testhelpers.VerboseTest):
	"""tests for working VOTable ingestion.
	"""
# Ok, so isn't a *unit* test by any stretch.  Sue me.
	resources = [("testData", _ImportTestData("data/importtest.vot"))]

	def testValidData(self):
		td, data = self.testData
		row = data[0]
		self.assertAlmostEqual(row[0], 72.183030)
		self.assertEqual(row[3], 1)
		self.assertEqual(row[5], 'NGC 104')
		self.failUnless(isinstance(row[6], unicode))
		self.assertAlmostEqual(row[7][0], 305.9)
		self.assertEqual(row[9], 34)

	def testNULLs(self):
		td, data = self.testData
		row = data[1]
		self.assertEqual(row, (None,)*len(row))

	def testNames(self):
		td, data = self.testData
		self.assertEqual([f.name for f in td],
			['_r', 'field', 'field_', 'class_', 'result__', 'Cluster', 
				'RAJ2000', 'GLON', 'xFexHxz', 'n_xFexHxz', 'xFexHxc', 
				'FileName', 'HR', 'n_VHB'])

	def testTypes(self):
		td, data = self.testData
		self.assertEqual([f.type for f in td], 
			['double precision', 'double precision', 'double precision', 
				'integer', 'smallint', 'text', 'text', 'real[2]', 'real', 
				'smallint', 'real', 'text', 'text', 'char'])


class NastyImportTest(testhelpers.VerboseTest):
	"""tests for working VOTable ingestion with ugly VOTables.
	"""
	def _assertAfterIngestion(self, fielddefs, literals, testCode,
			nameMaker):
		conn = base.getDefaultDBConnection()
		table = votableread.uploadVOTable("junk",
			StringIO(
			'<VOTABLE><RESOURCE><TABLE>'+
			fielddefs+
			'<DATA><TABLEDATA>'+
			'\n'.join('<TR>%s</TR>'%''.join('<TD>%s</TD>'%l
				for l in row) for row in literals)+
			'</TABLEDATA></DATA>'
			'</TABLE></RESOURCE></VOTABLE>'.encode("utf-8")),
			conn, nameMaker=nameMaker)
		testCode(table)
		conn.close()

	def testDupesRejected(self):
		self.assertRaises(base.ValidationError,
			self._assertAfterIngestion,
			'<FIELD name="condition-x" datatype="boolean"/>'
			'<FIELD name="condition-x" datatype="int"/>',
			[['True', '0']], None, nameMaker=votableread.QuotedNameMaker())

	def testNastyName(self):
		def test(table):
			self.assertEqual(list(table), [{'condition-x': True}])
			self.assertEqual(table.tableDef.columns[0].name, "condition-x")

		self._assertAfterIngestion(
			'<FIELD name="condition-x" datatype="boolean"/>',
			[['True']], test, nameMaker=votableread.QuotedNameMaker())
	
	def testNastierName(self):
		def test(table):
			self.assertEqual(list(table), 
				 [{'altogether "messy" shit': True}])
			self.assertEqual(table.tableDef.columns[0].name, 
				'altogether "messy" shit')

		self._assertAfterIngestion(
			'<FIELD name=\'altogether "messy" shit\' datatype="boolean"/>',
			[['True']], test, nameMaker=votableread.QuotedNameMaker())

	def testNoIdentifiers(self):
		def test(table):
			self.failUnless(isinstance(table.tableDef.columns[0].name,
				utils.QuotedName))
			self.failUnless(isinstance(table.tableDef.columns[1].name,
				basestring))

		self._assertAfterIngestion(
			'<FIELD name="SELECT" datatype="boolean"/>'
			'<FIELD name="SELECT_" datatype="boolean"/>',
			[['True', 'False']], test, nameMaker=votableread.AutoQuotedNameMaker())


class MetaTest(testhelpers.VerboseTest):
	"""tests for inclusion of some meta items.
	"""
	def _getTestData(self):
		table = rsc.TableForDef(
			testhelpers.getTestRD().getById("typestable").change(onDisk=False,
				id="fud"),
			rows=[{"anint": 10, "afloat": 0.1, "adouble": 0.2,
				"atext": "a", "adate": datetime.date(2004, 01, 01)}])
		return rsc.wrapTable(table)

	def _assertVOTableContains(self, setupFunc, expectedStrings):
		data = self._getTestData()
		setupFunc(data)
		vot = votablewrite.getAsVOTable(data)
		try:
			for s in expectedStrings:
				self.failUnless(s in vot, "%r not in VOTable"%s)
		except AssertionError:
			open("lastbad.xml", "w").write(vot)
			raise

	def testWarning(self):
		def setupData(data):
			data.getPrimaryTable().addMeta("_warning", 
				"Last warning: Do not use ' or \".")
			data.getPrimaryTable().addMeta("_warning", 
				"Now, this *really* is the last warning")
		self._assertVOTableContains(setupData, [
			'<INFO name="warning" value="In table fud: Last warning:'
				' Do not use \' or &quot;."',
			'<INFO name="warning" value="In table fud: Now, this *really*',
		])
	
	def testLegal(self):
		def setupData(data):
			data.dd.rd.addMeta("copyright", "Please reference someone else")
		self._assertVOTableContains(setupData, [
			'<INFO name="legal" value="Please reference someone else"'])


def _pprintVOT(vot):
	os.popen("xmlstarlet fo", "w").write(vot)


def _getTableWithSimpleSTC():
	td = testhelpers.getTestRD().getById("adql").change(onDisk=False)
	return rsc.TableForDef(td, rows=[
		{'alpha': 10, 'delta': -10, 'mag': -1, 'rv': -4}])


class STCEmbedTest(testhelpers.VerboseTest):
	"""tests for proper inclusion of STC in VOTables.
	"""
	def testSimpleSTC(self):
		table = _getTableWithSimpleSTC()
		tx = votablewrite.getAsVOTable(table)
		self.failUnless(
			re.search('<GROUP [^>]*utype="stc:CatalogEntryLocation"', tx))
		self.failUnless(re.search('<PARAM [^>]*utype="stc:AstroCoo'
			'rdSystem.SpaceFrame.CoordRefFrame"[^>]* value="ICRS"', tx))
		self.failUnless(re.search('<FIELD[^>]* ID="alpha" ', tx))
		self.failUnless('<FIELDref utype="stc:AstroCoords.Position2D'
			'.Value2.C2" ref="delta"' in tx)

	def testMultiTables(self):
		# twice the same table -- this is mainly for id mapping
		table = _getTableWithSimpleSTC()
		dd = base.makeStruct(rscdef.DataDescriptor, tables=[
			table.tableDef, table.tableDef], parent_=table.tableDef.rd)
		tdCopy = table.tableDef.copy(dd)
		tdCopy.id = "copy"
		tableCopy = rsc.TableForDef(tdCopy)
		data = rsc.Data(dd, tables={table.tableDef.id: table,
			"copy": tableCopy})
		serialized = votablewrite.getAsVOTable(data)
		for fragment in [
				'Position2D.Value2.C2" ref="delta"',
				'ID="delta"',
				'Position2D.Value2.C2" ref="delta0"',
				'ID="delta0"']:
			self.failUnless(fragment in serialized)


class STCParseTest(testhelpers.VerboseTest):
	"""tests for parsing of STC info from VOTables.
	"""
	def _doRoundtrip(self, table):
		serialized = votablewrite.getAsVOTable(table)
		vot = votable.readRaw(StringIO(serialized))
		dddef = votableread.makeDDForVOTable("testTable", vot)
		return dddef.getPrimary()

	def _assertSTCEquivalent(self, td1, td2):
		for orig, deser in zip(td1, td2):
			self.assertEqual(orig.name, deser.name)
			self.assertEqual(orig.stcUtype, deser.stcUtype)
			self.assertEqual(orig.stc, deser.stc)

	def testSimpleRoundtrip(self):
		src = _getTableWithSimpleSTC()
		td = self._doRoundtrip(src)
		self._assertSTCEquivalent(src.tableDef, td)

	def testComplexRoundtrip(self):
		src = rsc.TableForDef(testhelpers.getTestRD().getById("stcfancy"))
		td = self._doRoundtrip(src)
		self._assertSTCEquivalent(src.tableDef, td)

	def testWhackyUtypesIgnored(self):
		vot = votable.readRaw(StringIO("""
		<VOTABLE version="1.2"><RESOURCE><TABLE><GROUP ID="ll" utype="stc:CatalogEntryLocation"><PARAM arraysize="*" datatype="char" utype="stc:AstroCoordSystem.SpaceFrame.CoordRefFrame" value="ICRS" /><PARAM arraysize="*" datatype="char" utype="stc:AstroCoordSystem.SpaceFrame.Megablast" value="ENABLED" /><FIELDref ref="alpha" utype="stc:AstroCoords.Position2D.Value2.C1" /><FIELDref ref="delta" utype="stc:AstroCoords.BlasterLocation" /></GROUP><FIELD ID="alpha" arraysize="1" datatype="float" name="alpha" unit="deg"/><FIELD ID="delta" arraysize="1" datatype="float" name="delta" unit="deg"/></TABLE></RESOURCE></VOTABLE>"""))
		dddef = votableread.makeDDForVOTable("testTable", vot)
		td = dddef.getPrimary()
		self.assertEqual(
			td.getColumnByName("alpha").stc.sys.spaceFrame.refFrame, "ICRS")
		self.assertEqual(
			td.getColumnByName("alpha").stcUtype, 
			"stc:AstroCoords.Position2D.Value2.C1")
		self.assertEqual(
			td.getColumnByName("delta").stcUtype, 
			"stc:AstroCoords.BlasterLocation")


class SimpleAPIReadTest(testhelpers.VerboseTest):
	def testSimpleData(self):
		data, metadata = votable.load("data/importtest.vot")
		self.assertEqual(len(metadata), 14)
		self.assertEqual(metadata[0].a_name, "_r")
		self.assertEqual(data[0][3], 1)
		self.assertEqual(data[1][0], None)


if __name__=="__main__":
	testhelpers.main(ImportTest)
