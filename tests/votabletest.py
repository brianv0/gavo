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
from gavo import rscdesc
from gavo.formats import votable
from gavo.imp import VOTable
from gavo.utils import ElementTree

import testhelpers

testData="""some silly test data
-33  -3400abc
23829328.9xxy
     22      
          nas 
"""

class VotableTest(unittest.TestCase):
	def _makeRD(self):
		"""returns a test resource descriptor.
		"""
		return base.parseFromString(rscdesc.RD, """
			<resource resdir="%s" schema="test">
				<meta name="description">Some test data for VOTables.</meta>
				<meta name="_legal">Hands off this fascinating data</meta>
				<cooSys id="sys1" equ="J2000.0" epoch="1998" system="eq_FK5"/>
				<cooSys id="sys2" equ="J2000.0" system="ICRS"/>
				<table id="foo">
					<column name="anInt" type="integer"
						description="This is a first data field"/>
					<column name="aFloat"
						description="This ain't &amp;alpha; for sure."/>
					<column name="bla" type="text"/>
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
			</resource>"""%os.path.abspath("data"))

	def setUp(self):
		rd = self._makeRD()
		dataSet = rsc.makeData(rd.getById("bar"), forceSource=StringIO(testData))
		votMaker = votable.VOTableMaker(tablecoding="td")
		output = StringIO()
		votMaker.writeVOT(votMaker.makeVOT(dataSet), output)
		self.rawVOTable = output.getvalue()
		self.tree = ElementTree.fromstring(self.rawVOTable)

	def testValidates(self):
		"""test for validity of the generated VOTable.
		"""
		pipe = os.popen(
			"xmlstarlet val --err --xsd %s -"
				" > validationres.txt"%pkg_resources.resource_filename('gavo',
					"resources/xml/VOTable-1.1.xsd"), "w")
		pipe.write(self.rawVOTable)
		res = pipe.close()
		f = open("validationres.txt")
		valprot = f.read()
		f.close()
		os.unlink("validationres.txt")
		self.assertEqual(valprot.strip(), "- - valid", 
			"Generated VOTable doesn't match schema:\n%s"%valprot)

	def testNullvalues(self):
		"""tests for correct serialization of Null values.
		"""
		tbldata = self.tree.find(".//%s"%votable.voTag("TABLEDATA"))
		self.assertEqual(tbldata[3][1].text, None, "NaN isn't rendered as"
			" NULL")
		fields = self.tree.findall(".//%s"%votable.voTag("FIELD"))
		f0Null = fields[0].find(votable.voTag("VALUES")).get("null")
		self.assertEqual(tbldata[2][0].text, f0Null)

	def testRanges(self):
		"""tests for ranges given in VALUES.
		"""
		fields = self.tree.findall(".//%s"%votable.voTag("FIELD"))
		f0 = fields[0].find(votable.voTag("VALUES"))
		self.assertEqual(f0.find(votable.voTag("MIN")).get("value"), "-33",
			"integer minimum bad")
		self.assertEqual(f0.find(votable.voTag("MAX")).get("value"), "23829",
			"integer maximum bad")
		f1 = fields[1].find(votable.voTag("VALUES"))
		self.assertEqual(f1.find(votable.voTag("MIN")).get("value"), "-3400.0",
			"float minimum bad")
		self.assertEqual(f1.find(votable.voTag("MAX")).get("value"), "328.9",
			"float maximum bad")
		self.assertEqual(fields[2].find(votable.voTag("VALUES")), None,
			"VALUES element given for string data")


def _makeImportTestData():
# used by ImportTest, we want to cache this.
	f = _makeImportTestData
	if not hasattr(f, "data"):
		try:
			conn = base.getDefaultDBConnection()
			f.tableDef = votable.uploadVOTable("votabletest", 
				open("data/importtest.vot"), conn).tableDef
			querier = base.SimpleQuerier(connection=conn)
			f.data = list(querier.query("select * from votabletest"))
		finally:
			conn.close()
	return f.tableDef, f.data


class ImportTest(testhelpers.VerboseTest):
	"""tests for working VOTable DD generation.
	"""
# Ok, so isn't a *unit* test by any stretch.  Sue me.
	def setUp(self):
		self.tableDef, self.data = _makeImportTestData()

	def testValidData(self):
		row = self.data[0]
		self.assertAlmostEqual(row[0], 72.183030)
		self.assertEqual(row[3], 1)
		self.assertEqual(row[5], 'NGC 104')
		self.failUnless(isinstance(row[6], unicode))
		self.assertAlmostEqual(row[7][0], 305.9)
		self.assertEqual(str(row[9]), '"')

	def testNULLs(self):
		row = self.data[1]
		self.assertEqual(row, (None,)*len(row))

	def testNames(self):
		self.assertEqual([f.name for f in self.tableDef],
			['_r', 'field', 'field_', 'class_', 'result__', 'Cluster', 
				'RAJ2000', 'GLON', 'xFexHxz', 'n_xFexHxz', 'xFexHxc', 
				'FileName', 'HR', 'n_VHB'])

	def testTypes(self):
		self.assertEqual([f.type for f in self.tableDef], 
			['double precision', 'double precision', 'double precision', 
				'integer', 'smallint', 'text', 'text', 'real[2]', 'real', 
				'bytea', 'real', 'text', 'text', 'char'])


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
		vot = votable.getAsVOTable(data)
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
				' Do not use &apos; or &quot;."',
			'<INFO name="warning" value="In table fud: Now, this *really*',
		])
	
	def testLegal(self):
		def setupData(data):
			data.addMeta("copyright", "Please reference someone else")
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
		tx = votable.getAsVOTable(table)
		self.failUnless(
			re.search('<GROUP ID="[^"]*" utype="stc:AstroCoordSystem"', tx))
		self.failUnless('<PARAM arraysize="*" datatype="char" utype="stc:AstroCoo'
			'rdSystem.SpaceFrame.CoordRefFrame" value="ICRS" />' in tx)
		self.failUnless('" utype="stc:AstroCoords"><GROUP ref="alpha"'
			' utype="stc:AstroCoords.Position2D.Value2.C1"' in tx)
		self.failUnless('<FIELD ID="alpha" ' in tx)
		

class STCParseTest(testhelpers.VerboseTest):
	"""tests for parsing of STC info from VOTables.
	"""
	def _doRoundtrip(self, table):
		vot = VOTable.parse(StringIO(votable.getAsVOTable(table)))
		dddef = votable.makeDDForVOTable("testTable", vot)
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
		vot = VOTable.parse(StringIO("""
		<VOTABLE version="1.1"><RESOURCE><TABLE><GROUP ID="ll" utype="stc:AstroCoordSystem"><PARAM arraysize="*" datatype="char" utype="stc:AstroCoordSystem.SpaceFrame.CoordRefFrame" value="ICRS" /><PARAM arraysize="*" datatype="char" utype="stc:AstroCoordSystem.SpaceFrame.Megablast" value="ENABLED" /></GROUP><GROUP ID="ll_coo" ref="ll" utype="stc:AstroCoords"><GROUP ref="alpha" utype="stc:AstroCoords.Position2D.Value2.C1" /><GROUP ref="delta" utype="stc:AstroCoords.BlasterLocation" /></GROUP><FIELD ID="alpha" arraysize="1" datatype="float" name="alpha" unit="deg"/><FIELD ID="delta" arraysize="1" datatype="float" name="delta" unit="deg"/></TABLE></RESOURCE></VOTABLE>"""))
		dddef = votable.makeDDForVOTable("testTable", vot)
		td = dddef.getPrimary()
		self.assertEqual(
			td.getColumnByName("alpha").stc.spaceFrame.refFrame, "ICRS")
		self.assertEqual(
			td.getColumnByName("alpha").stcUtype, 
			"AstroCoords.Position2D.Value2.C1")
		self.assertEqual(
			td.getColumnByName("delta").stcUtype, 
			"AstroCoords.BlasterLocation")


if __name__=="__main__":
	testhelpers.main(STCParseTest)
