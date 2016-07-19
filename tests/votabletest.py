"""
Some tests for votable production.
"""

#c Copyright 2008-2016, the GAVO project
#c
#c This program is free software, covered by the GNU GPL.  See the
#c COPYING file in the source distribution.


from cStringIO import StringIO
import datetime
import os
import pkg_resources
import re
import unittest

from gavo.helpers import testhelpers

from gavo import base
from gavo import rsc
from gavo import rscdef
from gavo import rscdesc
from gavo import utils
from gavo import votable
from gavo.formats import votableread, votablewrite
from gavo.utils import ElementTree
from gavo.utils import pgsphere

import tresc


def getTDForVOTable(votCode):
	"""returns an rsc.TableDef instance for a votable defined by the
	fields, params, and groups within votCode.
	"""
	for votRes in votable.parseString("<VOTABLE><RESOURCE><TABLE>"
			"%s<DATA/></TABLE></RESOURCE></VOTABLE>"%votCode):
		return votableread.makeTableDefForVOTable(
			"testing", votRes.tableDefinition)


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
				<meta name="utype">test:testTable</meta>
				<meta name="note" tag="1">Note 1</meta>
				<meta name="note" tag="2">Note 2</meta>
				<column name="anInt" type="integer"
					description="This is a first data field" note="1"
					xtype="test:junk">
					<values nullLiteral="-32923"/>
				</column>
				<column name="aFloat"
					description="This ain't &amp;alpha; for sure." note="1"/>
				<column name="bla" type="text" note="2"/>
				<column name="varArr" type="real[]"
					description="horrible array"/>
				<param name="somePar" type="double precision">3.500</param>
			</table>
			<data id="bar">
				<meta name="utype">test:testResource</meta>
				<meta name="_infolink">http://vo.org/x?a=b&amp;c=d</meta>
				<columnGrammar topIgnoredLines="1">
					<col key="anInt">1-5</col>
					<col key="aFloat">6-10</col>
					<col key="bla">11-13</col>
				</columnGrammar>
				<rowmaker id="_foo" idmaps="*">
					<apply>
						<code>
							if vars["anInt"]=='-33':
								vars["varArr"] = None
							else:
								vars["varArr"] = [1,2]
						</code>
					</apply>
				</rowmaker>
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


def _getVOTTreeForTable(tdXML):
	td = base.parseFromString(rscdef.TableDef, tdXML)
	table = rsc.TableForDef(td)
	rawVOTable = votablewrite.getAsVOTable(table, tablecoding="td",
		suppressNamespace=True)
	return ElementTree.fromstring(rawVOTable)


def _pprintEtree(root):
	import subprocess
	p = subprocess.Popen(["xmlstarlet", "fo"], stdin=subprocess.PIPE)
	ElementTree.ElementTree(root).write(p.stdin)
	p.stdin.close()


def _getElementByID(root, id):
	for el in root.getiterator():
		if el.attrib.get("ID")==id:
			return el


class VOTableTest(testhelpers.VerboseTest, testhelpers.XSDTestMixin):

	resources = [("testData", _testVOTable)]

	def testValidates(self):
		"""test for validity of the generated VOTable.
		"""
		self.assertValidates(self.testData[0])

	def testFloatNullvalue(self):
		"""tests for correct serialization of Null values.
		"""
		tree = self.testData[1]
		tbldata = tree.find(".//%s"%votable.voTag("TABLEDATA"))
		self.assertEqual(tbldata[3][1].text, 'NaN', "NULL isn't rendered as"
			" NaN")
	
	def testIntNullvalue(self):
		tree = self.testData[1]
		tbldata = tree.find(".//%s"%votable.voTag("TABLEDATA"))
		fields = tree.findall(".//%s"%votable.voTag("FIELD"))
		f0Null = fields[0].find(str(votable.voTag("VALUES"))).get("null")
		self.assertEqual(tbldata[2][0].text, f0Null)

	def testArrayNullvalue(self):
		tbldata = self.testData[1].find(".//%s"%votable.voTag("TABLEDATA"))
		self.assertEqual(tbldata[0][3].text, None)

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

	def testParamVal(self):
		tree = self.testData[1]
		table = tree.findall(".//%s"%votable.voTag("TABLE"))[0]
		params = table.findall(".//%s"%votable.voTag("PARAM"))
		self.assertEqual(params[0].get("value"), "3.500")
		self.assertEqual(params[0].get("name"), "somePar")
		self.assertEqual(params[0].get("datatype"), "double")

	def testTableUtype(self):
		table = self.testData[1].findall(".//%s"%votable.voTag("TABLE"))[0]
		self.assertEqual(table.get("utype"), "test:testTable")

	def testResourceUtype(self):
		votRes = self.testData[1].findall(".//%s"%votable.voTag("RESOURCE"))[0]
		self.assertEqual(votRes.get("utype"), "test:testResource")


class _ImportTestData(testhelpers.TestResource):
	def __init__(self, fName, nameMaker=None):
		self.fName, self.nameMaker = fName, nameMaker
		testhelpers.TestResource.__init__(self)

	def make(self, deps):
		# we need a connection of our own so the temp table gets torn down
		# immediately
		self.conn = base.getDBConnection("untrustedquery")
		tableDef = votableread.uploadVOTable("votabletest", 
			open(self.fName), connection=self.conn, nameMaker=self.nameMaker).tableDef
		querier = base.UnmanagedQuerier(connection=self.conn)
		data = list(querier.query("select * from votabletest"))
		return tableDef, data
	
	def clean(self, ignored):
		self.conn.close()


class ImportTest(testhelpers.VerboseTest):
	"""tests for working VOTable ingestion.
	"""
	resources = [("testData", _ImportTestData("test_data/importtest.vot"))]

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
				'FileName', 'HR', 'n_VHB', 'apex', 'roi'])

	def testTypes(self):
		td, data = self.testData
		self.assertEqual([f.type for f in td], 
			['double precision', 'double precision', 'double precision', 
				'integer', 'smallint', 'text', 'text', 'real[2]', 'real', 
				'smallint', 'real', 'text', 'text', 'char', 'spoint', 'spoly'])

	def testParams(self):
		td, data = self.testData
		self.assertEqual(td.params[0].name, "qua1")
		self.assertEqual(td.params[1].name, "qua2")
		self.assertEqual(td.params[0].value, "first param")
		self.assertEqual(td.params[1].value, 2)

	def testColumnMeta(self):
		td, _ = self.testData
		col = td.getColumnByName("field")
		self.assertEqual(col.ucd, "POS_EQ_RA_MAIN")
		self.assertEqual(col.type, "double precision")
		self.assertEqual(col.unit, "deg")
		self.assertEqual(col.description, 
			"Right ascension (FK5) Equinox=J2000. (computed by"
			" VizieR, not part of the original data)")

	def testPointVals(self):
		_, data = self.testData
		self.failUnless(isinstance(data[0][14], pgsphere.SPoint))
		self.assertAlmostEqual(data[0][14].x, 42*utils.DEG)
		self.assertEqual(data[1][14], None)

	def testRegionVals(self):
		_, data = self.testData
		self.failUnless(isinstance(data[0][15], pgsphere.SPoly))
		self.assertEqual(data[1][15], None)


class VizierImportTest(testhelpers.VerboseTest):
	"""tests for ingestion of a random vizier VOTable.
	"""
	resources = [("testData", _ImportTestData("test_data/vizier_votable.vot",
		nameMaker=votableread.AutoQuotedNameMaker()))]

	def testNames(self):
		td, data = self.testData
		self.assertEqual(len(data), 50)
		self.assertEqual(td.columns[4].name.name, "RA(ICRS)")
		self.assertEqual(td.columns[4].key, 'RA__ICRS__')
	
	def testData(self):
		td, data = self.testData
		for tuple in data:
			if tuple[4]=="04 26 20.741":
				break
		else:
			self.fail("04 26 20.741 not found in any row.")


class NastyImportTest(tresc.TestWithDBConnection):
	"""tests for working VOTable ingestion with ugly VOTables.
	"""
	def _assertAfterIngestion(self, fielddefs, literals, testCode,
			nameMaker):
		table = votableread.uploadVOTable("junk",
			StringIO(
			'<VOTABLE><RESOURCE><TABLE>'+
			fielddefs+
			'<DATA><TABLEDATA>'+
			'\n'.join('<TR>%s</TR>'%''.join('<TD>%s</TD>'%l
				for l in row) for row in literals)+
			'</TABLEDATA></DATA>'
			'</TABLE></RESOURCE></VOTABLE>'.encode("utf-8")),
			self.conn, nameMaker=nameMaker)
		testCode(table)

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

	def testXtypes(self):
		def test(table):
			self.assertEqual(table.tableDef.columns[0].type, 'spoint')
			data = list(table)
			self.assertEqual(data[0]["p"], None)
			self.assertEqual(data[0]["d"], None)
			self.assertAlmostEqual(data[1]["p"].x, 2*utils.DEG)
			self.assertAlmostEqual(data[1]["p"].y, 3*utils.DEG)
			self.assertEqual(data[1]["d"], datetime.datetime(2005, 5, 6, 21, 10, 19))
			self.assertEqual(data[1]["u"], '2005-05-06T21:10:19')

		self._assertAfterIngestion(
			'<FIELD name="p" datatype="char" arraysize="*" xtype="adql:POINT"/>'
			'<FIELD name="u" datatype="char" arraysize="*" xtype="adql:FANTASY"/>'
			'<FIELD name="d" datatype="char" arraysize="*" xtype="adql:TIMESTAMP"/>',
			[['', '', ''], 
				['Position ICRS 2 3', '2005-05-06T21:10:19', '2005-05-06T21:10:19']], 
			test, nameMaker=votableread.AutoQuotedNameMaker())


class MetaTest(testhelpers.VerboseTest):
	"""tests for inclusion of some meta items.
	"""
	def _getTestData(self):
		table = rsc.TableForDef(
			testhelpers.getTestRD().getById("typesTable").change(onDisk=False,
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

	def testMetaExpanded(self):
		def setupData(data):
			data.dd.rd.addMeta("copyright", "\\RSTccby{world}")
		self._assertVOTableContains(setupData, [
			'<INFO name="legal" value="world is licensed under the `Creative'])

	def testSource(self):
		def setupData(data):
			data.getPrimaryTable().addMeta("source", "1543droc.book.....C")
		self._assertVOTableContains(setupData, [
			'<INFO name="source" value="1543droc.book.....C"'])


class VOTableRenderTest(testhelpers.VerboseTest):
	def _getTable(self, colDef, rows=[{'x': None}]):
		return rsc.TableForDef(base.parseFromString(rscdef.TableDef,
				'<table>%s</table>'%colDef), rows=rows)

	def _getAsVOTable(self, colDef, **contextArgs):
		rows = contextArgs.pop("rows", [{"x": None}])
		contextArgs["tablecoding"] = contextArgs.get("tablecoding", "td")
		return votablewrite.getAsVOTable(
			self._getTable(colDef, rows),
			votablewrite.VOTableContext(**contextArgs))

	def _assertVOTContains(self, colDef, literals, **contextArgs):
		res = self._getAsVOTable(colDef, **contextArgs)
		for lit in literals:
			try:
				self.failUnless(lit in res)
			except AssertionError:
				print res
				raise

	def _getAsETree(self, colDef, **contextArgs):
		vot = self._getAsVOTable(colDef, **contextArgs)
		return ElementTree.fromstring(vot)

	def _getEls(self, tree, elementName):
		return tree.findall(".//%s"%votable.voTag(elementName))


class ParamNullValueTest(VOTableRenderTest):
	def _getParamsFor(self, colDef):
		tree = self._getAsETree(colDef)
		return self._getEls(tree, "PARAM")

	def _getParamFor(self, colDef):
		pars = self._getParamsFor(colDef)
		self.assertEqual(len(pars), 1)
		return pars[0]

	def _assertDeclaredNull(self, colDef, nullLiteral):
		par = self._getParamFor(colDef)
		self.assertEqual(par.get("value"), nullLiteral)
		self.assertEqual(par[0].tag, votable.voTag("VALUES"))
		self.assertEqual(par[0].get("null"), nullLiteral)

	def _assertParsesAsNULL(self, colDef):
		par = self._getParamFor(colDef)
		self.assertEqual(par.get("value"), "")

	def testEmptyString(self):
		par = self._getParamFor('<param name="x" type="text"/>')
		self.assertEqual(par.get("value"), "")

	def testEmptyIntIsNull(self):
		self._assertParsesAsNULL(
			'<param name="x" type="integer"/>')

	def testStringNullDefault(self):
		self._assertParsesAsNULL(
			'<param name="x" type="text">__NULL__</param>')

	def testNonDefaultNULL(self):
		par = self._getParamFor(
			'<param name="x" type="integer"><values nullLiteral="-1"/>-1</param>')
		self.assertEqual(par.get("value"), "")
		self.assertEqual(par[0].tag, votable.voTag("VALUES"))
		self.assertEqual(par[0].get("null"), "-1")

	def testIntDefault(self):
		table = self._getTable('<param name="x" type="integer"/>')
		table.setParam("x", None)
		par = self._getEls(
			ElementTree.fromstring(
				votablewrite.getAsVOTable(table)), "PARAM")[0]
		self.assertEqual(par.get("value"), '')

	def testFloatNaN(self):
		par = self._getParamFor('<param name="x">NaN</param>')
		self.assertEqual(par.get("value"), "")

	def testFloatEmpty(self):
		par = self._getParamFor('<param name="x"/>')
		self.assertEqual(par.get("value"), "")


	def testNonNullNotDeclared(self):
		par = self._getParamsFor('<param name="z" type="text">abc</param>')[0]
		self.assertEqual(self._getEls(par, "VALUES"), [])


class TabledataNullValueTest(VOTableRenderTest):
	def testIntNullRaising(self):
		table = self._getTable('<column name="x" type="integer"/>')
		self.assertRaisesWithMsg(votable.BadVOTableData,
			"Field 'x', value None: None passed for field that has no NULL value",
			votablewrite.getAsVOTable,
			(table, votablewrite.VOTableContext(acquireSamples=False)))

	def testIntNullGiven(self):
		self._assertVOTContains('<column name="x" type="integer">'
			'<values nullLiteral="-99"/></column>', [
			'<VALUES null="-99">',
			'<TR><TD>-99</TD></TR>'])
	
	def testCharNullGiven(self):
		self._assertVOTContains('<column name="x" type="char">'
				'<values nullLiteral="x"/></column>', [
			'<VALUES null="x">',
			'<TR><TD>x</TD></TR>'])

	def testTextNullGiven(self):
		self._assertVOTContains('<column name="x" type="text">'
				'<values nullLiteral="&quot;not given&quot;"/></column>', [
			'<VALUES null="&quot;not given&quot;">',
			'<TR><TD></TD></TR>'])
	
	def testTextNullAuto(self):
		self._assertVOTContains('<column name="x" type="text"/>',[
			'<TR><TD></TD></TR>'])
	
	def testTextNullAutoNoSample(self):
		self._assertVOTContains('<column name="x" type="text"/>',[
			'<TR><TD></TD></TR>'], acquireSamples=False)

	def testRealNullIgnoreGiven(self):
		self._assertVOTContains('<column name="x">'
				'<values nullLiteral="-9999."/></column>', [
			'<VALUES null="-9999.">',
			'<TR><TD>NaN</TD></TR>'])


class BinaryNullValueTest(VOTableRenderTest):
	def testVarArrayNull(self):
		tree = self._getAsETree('<column name="x" type="real[]"/>',
			tablecoding="binary")
		self.assertEqual(
			self._getEls(tree, "STREAM")[0].text.decode("base64"),
			'\x00\x00\x00\x00')


class GeoXtypeTest(VOTableRenderTest):
	def testRegionXtype(self):
		tree = self._getAsETree('<column name="x" type="spoly"/>')
		self.assertEqual(
			self._getEls(tree, "FIELD")[0].get("xtype"), 
			"adql:REGION")

	def testPointXtype(self):
		tree = self._getAsETree('<column name="x" type="spoint"/>')
		self.assertEqual(
			self._getEls(tree, "FIELD")[0].get("xtype"), 
			"adql:POINT")


class TypesSerializationTest(VOTableRenderTest):
	def testUnicode(self):
		data, metadata = votable.load(
			StringIO(self._getAsVOTable('<column name="x" type="unicode"/>', 
				rows=[{"x": u"f\u00fcr"}])))
		self.assertEqual(data[0][0], u"f\u00fcr")

	def testUnicodeBin(self):
		data, metadata = votable.load(
			StringIO(self._getAsVOTable('<column name="x" type="unicode"/>', 
				rows=[{"x": u"f\u00fcr"}], tablecoding="binary")))
		self.assertEqual(data[0][0], u"f\u00fcr")

	def testByteaBin(self):
		data, metadata = votable.load(
			StringIO(self._getAsVOTable('<column name="x" type="bytea"/>', 
				rows=[{"x": "\0"}], tablecoding="binary")))
		self.assertEqual(data[0][0], 0)

	def testByteaBin2(self):
		data, metadata = votable.load(
			StringIO(self._getAsVOTable('<column name="x" type="bytea"/>', 
				rows=[{"x": "u"}], tablecoding="binary2")))
		self.assertEqual(data[0][0], 117)

	def testByteaWithType(self):
		data, metadata = votable.load(
			StringIO(self._getAsVOTable('<column name="x" type="bytea"'
				' required="true"/>', 
				rows=[{"x": "u"}], tablecoding="td")))
		self.assertEqual(metadata[0].datatype, "unsignedByte")
		self.assertEqual(data[0][0], 117)

	def testBytearr(self):
		data, metadata = votable.load(
			StringIO(self._getAsVOTable('<column name="x" type="bytea"/>', 
				rows=[{"x": "u"}], tablecoding="td")))
		self.assertEqual(data[0][0], 117)


class ValuesParsedTest(testhelpers.VerboseTest):
	def testNull(self):
		td = getTDForVOTable(
			'<FIELD name="foo" datatype="int"><VALUES null="-1"/></FIELD>')
		self.assertEqual(td.getColumnByName("foo").values.nullLiteral,
			"-1")
	
	def testMinMax(self):
		td = getTDForVOTable(
			'<FIELD name="foo" datatype="int"><VALUES>'
			'<MIN value="23"/><MAX value="42"/></VALUES></FIELD>')
		self.assertEqual(td.getColumnByName("foo").values.min, 23)
		self.assertEqual(td.getColumnByName("foo").values.max, 42)

	def testOptions(self):
		td = getTDForVOTable(
			'<FIELD name="foo" datatype="int"><VALUES>'
			'<OPTION value="23"/><OPTION value="42" name="yes"/></VALUES></FIELD>')
		opts = td.getColumnByName("foo").values.options
		self.assertEqual(opts[0].content_, 23)
		self.assertEqual(opts[0].title, "23")
		self.assertEqual(opts[1].content_, 42)
		self.assertEqual(opts[1].title, "yes")


class GroupWriteTest(testhelpers.VerboseTest):
	def testEmptyGroup(self):
		tree = _getVOTTreeForTable(
			'<table><group name="tg" ucd="empty.group" utype="testing:silly"'
			' description="A meaningless group"/>'
				'</table>')
		res = tree.findall("RESOURCE/TABLE/GROUP")
		self.assertEqual(len(res), 1)
		self.assertEqual(res[0].attrib["ucd"], "empty.group")
		self.assertEqual(res[0].attrib["utype"], "testing:silly")
		self.assertEqual(res[0].attrib["name"], "tg")
		self.assertEqual(res[0].find("DESCRIPTION").text,
			"A meaningless group")
	
	def testRefs(self):
		tree = _getVOTTreeForTable(
			'<table><group><columnRef dest="x"/><columnRef dest="y"/>'
			'<paramRef dest="z"/></group>'
			'<column name="x"/><column name="y"/>'
			'<param name="z" type="integer">4</param>'
			'</table>')
		table = tree.find("RESOURCE/TABLE")
		g = table.find("GROUP")

		refs = [el.attrib["ref"] for el in g.findall("FIELDref")]
		self.assertEqual(len(refs), 2)
		self.assertEqual(_getElementByID(table, refs[0]).attrib["name"], "x")
		self.assertEqual(_getElementByID(table, refs[1]).attrib["name"], "y")

		refs = [el.attrib["ref"] for el in g.findall("PARAMref")]
		self.assertEqual(len(refs), 1)
		self.assertEqual(_getElementByID(table, refs[0]).attrib["value"], "4")

	def testLocalParam(self):
		tree = _getVOTTreeForTable(
			'<table><group><param name="u" type="integer">5</param></group>'
				'</table>')
		pars = tree.findall("RESOURCE/TABLE/GROUP/PARAM")
		self.assertEqual(len(pars), 1)
		self.assertEqual(pars[0].attrib["value"], "5")

	def testRecursive(self):
		tree = _getVOTTreeForTable(
			"<table><group><group><columnRef dest='x'/><columnRef dest='y'/></group>"
			'<group><paramRef dest="z"/></group></group>'
				'<column name="x"/><column name="y"/>'
				'<param name="z" type="integer">4</param>'
				'</table>')
		groups = tree.findall("RESOURCE/TABLE/GROUP/GROUP")
		self.assertEqual(len(groups), 2)

		colRefs = [c.attrib["ref"] for c in groups[0].findall("FIELDref")]
		self.assertEqual(len(colRefs), 2)
		self.assertEqual(_getElementByID(tree, colRefs[1]).attrib["name"], "y")
		self.assertEqual(len(groups[0].findall("PARAMref")), 0)

		paramRefs = [c.attrib["ref"] for c in groups[1].findall("PARAMref")]
		self.assertEqual(_getElementByID(tree, paramRefs[0]).attrib["value"], "4")
		self.assertEqual(len(groups[1].findall("FIELDref")), 0)

	def testCopied(self):
		td = base.parseFromString(rscdef.TableDef,
			'<table><group><group><columnRef dest="x"/><columnRef dest="y"/>'
				'<param name="u" type="integer">5</param></group>'
				'<group><paramRef dest="z"/></group></group>'
				'<column name="x"/><column name="y"/>'
				'<param name="z" type="integer">4</param>'
				'</table>')
		td = td.copy(None)
		tree = ElementTree.fromstring(
			votablewrite.getAsVOTable(
				rsc.TableForDef(td), tablecoding="td", suppressNamespace=True))

		groups = tree.findall("RESOURCE/TABLE/GROUP/GROUP")
		self.assertEqual(len(groups), 2)

		colRefs = [c.attrib["ref"] for c in groups[0].findall("FIELDref")]
		self.assertEqual(_getElementByID(tree, colRefs[1]).attrib["name"], "y")

		paramRefs = [c.attrib["ref"] for c in groups[1].findall("PARAMref")]
		self.assertEqual(_getElementByID(tree, paramRefs[0]).attrib["value"], "4")

		self.assertEqual(tree.find("RESOURCE/TABLE/GROUP/GROUP/PARAM").
			attrib["value"], "5")


def _getTableWithSimpleSTC():
	td = testhelpers.getTestRD().getById("adql").change(onDisk=False)
	return rsc.TableForDef(td, rows=[
		{'alpha': 10, 'delta': -10, 'mag': -1, 'rV': -4, 'tinyflag': "\x80"}])


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
		mat = re.search(
			'<FIELDref[^>]*utype="stc:AstroCoords.Position2D.Value2.C2[^>]*>',
			tx)
		self.failUnless('ref="delta"' in mat.group())

	def testMultiTables(self):
		# twice the same table -- this is mainly for id mapping
		table = _getTableWithSimpleSTC()
		tdCopy = table.tableDef.copy(None)
		tdCopy.id = "copy"
		tableCopy = rsc.TableForDef(tdCopy)
		dd = base.makeStruct(rscdef.DataDescriptor, makes=[
			base.makeStruct(rscdef.Make, table=table.tableDef),
			base.makeStruct(rscdef.Make, table=tdCopy)], 
			parent_=table.tableDef.rd)
		data = rsc.Data(dd, tables={table.tableDef.id: table,
			"copy": tableCopy})

		tree = testhelpers.getXMLTree(
			votablewrite.getAsVOTable(data), debug=False)
		for path in [
				"//FIELD[@ID='delta']",
				"//FIELD[@ID='delta0']",
				"//FIELDref[@ref='delta' and @utype='stc:AstroCoords.Position2D.Value2.C2']",
				"//FIELDref[@ref='delta0' and @utype='stc:AstroCoords.Position2D.Value2.C2']",
				]:
			self.failUnless(len(tree.xpath(path))==1, "%s not found"%path)


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
		data, metadata = votable.load("test_data/importtest.vot")
		self.assertEqual(len(metadata), 16)
		self.assertEqual(metadata[0].name, "_r")
		self.assertEqual(data[0][3], 1)
		self.assertEqual(data[1][0], None)


class VOTReadTest(testhelpers.VerboseTest):
	def testQ3CIndex(self):
		rows = votable.parse(StringIO(
			"""<VOTABLE><RESOURCE><TABLE>
				<FIELD name="a" datatype="float" ucd="pos.eq.ra;meta.main"/>
				<FIELD name="d" datatype="float" ucd="pos.eq.dec;meta.main"/>
				<DATA><TABLEDATA><TR><TD>1</TD><TD>2</TD></TR></TABLEDATA></DATA>
				</TABLE></RESOURCE></VOTABLE>""")).next()
		td = votableread.makeTableDefForVOTable("foo", rows.tableDefinition)
		self.assertEqual(td.indices[0].content_.strip(),
			r"q3c_ang2ipix(a, d)")

	def testNoQ3CIndexOnChar(self):
		rows = votable.parse(StringIO(
			"""<VOTABLE><RESOURCE><TABLE>
				<FIELD name="a" datatype="char" arraysize="*" 
					ucd="pos.eq.ra;meta.main"/>
				<FIELD name="d" datatype="float" ucd="pos.eq.dec;meta.main"/>
				<DATA><TABLEDATA><TR><TD>1</TD><TD>2</TD></TR></TABLEDATA></DATA>
				</TABLE></RESOURCE></VOTABLE>""")).next()
		td = votableread.makeTableDefForVOTable("foo", rows.tableDefinition)
		self.assertEqual(len(td.indices), 0)

	def testNoIndex(self):
		# The thing shouldn't crash or do anything stupid with silly UCDs.
		rows = votable.parse(StringIO(
			"""<VOTABLE><RESOURCE><TABLE>
				<FIELD name="a" datatype="float" ucd="pos.eq.ra;meta.main"/>
				<FIELD name="d" datatype="float" ucd="pos.eq.ra;meta.main"/>
				<DATA><TABLEDATA><TR><TD>1</TD><TD>2</TD></TR></TABLEDATA></DATA>
				</TABLE></RESOURCE></VOTABLE>""")).next()
		td = votableread.makeTableDefForVOTable("foo", rows.tableDefinition)
		self.assertEqual(td.indices, [])


class OverflowTest(testhelpers.VerboseTest):
	resources = [("tab", tresc.randomDataTable)]

	def testWithoutOverflow(self):
		res = votablewrite.getAsVOTable(self.tab, 
			votablewrite.VOTableContext(
				overflowElement=votable.OverflowElement(20,
					votable.V.GROUP(name="overflow"))))
		self.failIf('<GROUP name="overflow"' in res)

	def testWithOverflow(self):
		res = votablewrite.getAsVOTable(self.tab, 
			votablewrite.VOTableContext(
				overflowElement=votable.OverflowElement(2,
					votable.V.GROUP(name="overflow"))))
		self.failUnless('</TABLE><GROUP name="overflow"' in res)
		# since the overflow element is rendered in a context of its own,
		# it's non-trivial that no xml namespaces are declared on it.
		self.failIf('name="overflow" xmlns' in res)


class HackMetaTest(testhelpers.VerboseTest):
	"""tests for nasty hacks in data's meta stuff that lead so certain
	VOTable manipulations.
	"""
	def _getTestTable(self):
		td = base.parseFromString(rscdef.TableDef,
			'<table id="silly"><column name="u"/></table>')
		return rsc.TableForDef(td)

	def testRootAttributes(self):
		table = self._getTestTable()
		table.addMeta("_votableRootAttributes", "malformed mess")
		table.addMeta("_votableRootAttributes", "xmlns:crazy='http://forget.this'")
		res = votablewrite.getAsVOTable(table,
			votablewrite.VOTableContext(suppressNamespace=True))
		self.failUnless(
			"VOTABLE version=\"1.3\" malformed mess xmlns:crazy='http://forget.this'"
			in res)

	def testInfoMeta(self):
		table = self._getTestTable()
		table.addMeta("info", "Info from meta", 
			infoValue="bar", infoName="fromMeta", infoId="x_x")
		root = ElementTree.fromstring(votablewrite.getAsVOTable(table,
			votablewrite.VOTableContext(suppressNamespace=True)))
		mat = root.findall("RESOURCE/INFO")
		self.assertEqual(len(mat), 1)
		info = mat[0]
		self.assertEqual(info.attrib["ID"], "x_x")
		self.assertEqual(info.attrib["name"], "fromMeta")
		self.assertEqual(info.attrib["value"], "bar")
		self.assertEqual(info.text, "Info from meta")


class LinkTest(testhelpers.VerboseTest):
	def _getAsTree(self, tableXML):
		if tableXML.startswith("<data"):
			rootType = rscdef.DataDescriptor
			makeThing = rsc.makeData
		else:
			rootType = rscdef.TableDef
			makeThing = rsc.TableForDef

		t = makeThing(base.parseFromString(rootType, tableXML))
		return testhelpers.getXMLTree(
			votablewrite.getAsVOTable(t,
				votablewrite.VOTableContext(suppressNamespace=True)), debug=False)

	def testColumnLink(self):
		tree = self._getAsTree("""<table id="u">
			<column name="z"><meta name="votlink" role="check">ivo://ranz/k
			</meta></column></table>""")
		self.assertEqual(tree.xpath("RESOURCE/TABLE/FIELD/LINK/@href")[0], 
			"ivo://ranz/k")
		self.assertEqual(tree.xpath("RESOURCE/TABLE/FIELD/LINK/@content-role")[0], 
			"check")

	def testTableLink(self):
		tree = self._getAsTree("""<table id="u">
			<meta name="votlink" contentType="inode/fifo">ivo://ranz/k</meta>
			<column name="z"></column></table>""")
		self.assertEqual(tree.xpath("RESOURCE/TABLE/LINK/@href")[0], 
			"ivo://ranz/k")
		self.assertEqual(tree.xpath("RESOURCE/TABLE/LINK/@content-type")[0], 
			"inode/fifo")

	def testDataLink(self):
		tree = self._getAsTree("""<data id="a">
			<meta name="votlink" linkname="onlink">http://server/on</meta>
			<meta name="votlink" linkname="offlink">http://server/off</meta>
			<table id="u">
			<column name="z"></column></table><make table="u"/></data>""")
		self.assertEqual(tree.xpath("RESOURCE/TABLE/LINK/@href")[0], 
			"http://server/on")
		self.assertEqual(tree.xpath("RESOURCE/TABLE/LINK/@name")[0], 
			"onlink")
		self.assertEqual(tree.xpath("RESOURCE/TABLE/LINK/@href")[1], 
			"http://server/off")
		self.assertEqual(tree.xpath("RESOURCE/TABLE/LINK/@name")[1], 
			"offlink")


if __name__=="__main__":
	testhelpers.main(LinkTest)
