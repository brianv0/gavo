# -*- coding: iso-8859-1 -*-
"""
Tests having to do with various output formats.
"""

#c Copyright 2008-2017, the GAVO project
#c
#c This program is free software, covered by the GNU GPL.  See the
#c COPYING file in the source distribution.


from __future__ import with_statement

import datetime
import json
import math
import os
import re
import unittest
from cStringIO import StringIO

from gavo.helpers import testhelpers

from gavo import base
from gavo import formats
from gavo import rsc
from gavo import rscdef
from gavo import rscdesc
from gavo import utils
from gavo import votable
from gavo.base import valuemappers
from gavo.formats import jsontable
from gavo.formats import fitstable
from gavo.formats import texttable
from gavo.formats import csvtable
from gavo.formats import votablewrite
from gavo.svcs import outputdef
from gavo.utils import pgsphere
from gavo.utils import pyfits
from gavo.web import htmltable


_colDefs = {
	"klein": '<column name="klein"  type="smallint">'
		'<values nullLiteral="-1"/></column>',
	"prim": '<column name="prim" type="integer"'
		' description="Some random primary key"/><primary>prim</primary>',
	"nopt": '<column name="nopt" type="real" required="True"/>',
	"echter": '<column name="echter" type="double precision"/>',
	"datum": '<column name="datum" type="date"/>',
	"indf": '<column name="indf" type="text"/><index columns="indf"/>'}


def _getFields(*args):
	return [_colDefs[a] for a in args]


class ResolutionTest(testhelpers.VerboseTest):
	def testResolutionUnknownKey(self):
		self.assertRaisesWithMsg(formats.CannotSerializeIn,
			"Cannot serialize in 'votable/td'.",
			formats.getWriterFor,
			("votable/td",))
	
	def testResolutionKey(self):
		self.assertEqual(formats.getWriterFor("tsv"),
			texttable.renderAsText)

	def testResolutionMimeWithBlanks(self):
		self.assertEqual(
			formats.getWriterFor("text/csv; header = present").func_name,
			"<lambda>")
	
	def testMimeGetting(self):
		self.assertEqual(
			formats.getMIMEFor("votableb2"),
			"application/x-votable+xml;serialization=BINARY2")

	def testIterFormats(self):
		labels = list(formats.iterFormats())
		self.assertTrue("votableb2", labels)
		self.assertTrue("tsv", labels)


class FITSWriterTest(testhelpers.VerboseTest):
	def _makeRD(self, colNames, rd=None):
		return base.parseFromString(rscdesc.RD,
			"""<resource resdir="%s" schema="test">
			<data id="randomTest">
				<dictlistGrammar/>
				<table id="foo">
					%s
				</table>
				<rowmaker id="_foo" idmaps="%s"/>
				<make table="foo" rowmaker="_foo"/>
			</data>
		</resource>
		"""%(os.path.abspath("."), "\n".join(_getFields(*colNames)),
			",".join(colNames)))

	_testData = [{"klein": 1, "prim": 2, "nopt": 4.25, "indf": "CEN A"},
				{"klein": 2, "prim": 7, "nopt": 9.32, "indf":
					"QSO 3248+33 Component Gamma"}]

	def testMakeSimpleTable(self):
		"""tests for creation of a simple FITS table.
		"""
		rd = self._makeRD(["klein", "prim", "nopt", "indf"])
		dataSet = rsc.makeData(rd.getById("randomTest"),
			forceSource=self._testData)
		hdulist = fitstable.makeFITSTable(dataSet)
		self.assertEqual(len(hdulist), 2, "Primary or extension hdu missing")
		self.assert_(hdulist[0].header.has_key("DATE"), "No DATE keyword"
			" in primary header")
		ft = hdulist[1].data
		self.assertEqual(ft.field("klein")[0], 1)
		self.assertEqual(ft.field("prim")[1], 7)
		self.assertEqual(ft.field("nopt")[0], 4.25)
		self.assertEqual(ft.field("indf")[1], "QSO 3248+33 Component Gamma")
		self.assertEqual(len(hdulist[1].columns), 4)
		self.assertEqual(hdulist[1].columns[3].format, "27A")
	
	def testMakeDoubleTable(self):
		"""tests for creation of a two-extension FITS table.
		"""
		rd = self._makeRD(("klein", "prim", "nopt", "indf"))
		rec2 = base.parseFromString(rscdef.TableDef, 
			'<table id="part2">%s</table>'%"".join(_getFields("prim", "nopt")))
		dd = rd.getById("randomTest")
		dd.tables.append(rec2)
		dd.makes.append(base.makeStruct(rscdef.Make, table=rec2))
		dd.finishElement()
		dataSet = rsc.makeData(dd, forceSource=self._testData)
		hdulist = fitstable.makeFITSTable(dataSet)
		self.assertEqual(len(hdulist), 3, "Exporting composite data sets"
			" doesn't catch additional tables")

	def testTableWrite(self):
		rd = self._makeRD(("klein", "prim", "nopt", "indf"))
		dataSet = rsc.makeData(rd.getById("randomTest"),
			forceSource=self._testData)
		fName = fitstable.makeFITSTableFile(dataSet)
		self.assert_(os.path.exists(fName), "makeFITSTableFile doesn't"
			" create the file it says it creates")
		hdulist = pyfits.open(fName)
		self.assertEqual(len(hdulist), 2, "makeFITSTableFile wrote"
			" weird file")
		os.unlink(fName)

	def testSomeNullvalues(self):
		rd = self._makeRD(("klein", "echter", "indf"))
		dataSet = rsc.makeData(rd.getById("randomTest"),
			forceSource=[{"klein": None, "echter": None, "indf": None}])
		hdulist = fitstable.makeFITSTable(dataSet)
		resTup = hdulist[1].data[0]
		self.assertEqual(resTup[0], -1)
		self.failIf(resTup[1]==resTup[1]) # "isNan"
		self.assertEqual(resTup[2], "None") # Well, that should probably be sth else...


class _TestDataTable(testhelpers.TestResource):
	"""A fairly random table with mildly challenging data.
	"""
	def make(self, deps):
		dd = testhelpers.getTestRD().getById("tableMaker")
		data = rsc.makeData(dd, forceSource=[
			(1, -2, 3, "Wäre es da nicht besser,\n die Regierung setzte das Volk"
				" ab\tund wählte ein anderes?", '2004-05-05', 
				pgsphere.SPoint.fromDegrees(124, -30)),
			(None, None, None, None, None, None)])
		return data

_testDataTable = _TestDataTable()


class _FormattedData(testhelpers.TestResource):
	"""_testDataTable after being pushed through formats.getFormatted.
	"""
	resources = [("data", _testDataTable)]

	def __init__(self, destFormat, debug=False):
		self.destFormat = destFormat
		self.debug = debug
		testhelpers.TestResource.__init__(self)

	def make(self, dependencies):
		with utils.silence():
			output = formats.getFormatted(self.destFormat, dependencies["data"])
		if self.debug:
			print output
		return output


class _FormattedAndParsedData(testhelpers.TestResource):
	"""_testDataTable serialised and deserialized again through loads.

	What's coming back is (result-string, result-data).
	"""
	resources = [("data", _testDataTable)]

	def __init__(self, destFormat, loads, debug=False):
		self.destFormat = destFormat
		self.debug = debug
		self.loads = loads
		testhelpers.TestResource.__init__(self)

	def make(self, dependencies):
		data = _FormattedData(self.destFormat, self.debug).make(dependencies)
		return data, self.loads(data)


class _JSONTable(testhelpers.TestResource):
	"""A table that went through JSON serialisation.

	The resource is (json-text, decoded-json).
	"""
	resources = [("data", _testDataTable)]

	def make(self, deps):
		jsText = formats.getFormatted("json", deps["data"])
		decoded = json.loads(jsText)
		return jsText, decoded


class JSONOutputTest(testhelpers.VerboseTest):
	resources = [("tAndD", _FormattedAndParsedData('json', json.loads))]

	def testColumns(self):
		c1, c2, c3, c4, c5, c6 = self.tAndD[1]["columns"]
		self.assertEqual(c1["datatype"], "int")
		self.assertEqual(c2["name"], "afloat")
		self.assertEqual(c3["arraysize"], "1")
		self.assertEqual(c4["description"], u'Just by a \xb5.')
		self.assertEqual(c5["datatype"], "double")
		self.assertEqual(c6["datatype"], "char")

	def testContains(self):
		self.assertEqual(self.tAndD[1]["contains"], "table")
	
	def testData(self):
		self.assertEqual(self.tAndD[1]["data"], [
			[1, -2.0, 3.0, u'W\xe4re es da nicht besser,\n'
				u' die Regierung setzte das Volk ab\tund w\xe4hlte ein anderes?', 
				2453130.5, u'Position UNKNOWNFrame 124. -30.'], 
			[None, None, None, None, None, None]])

	def testParameterDescription(self):
		intPar = self.tAndD[1]["params"]["intPar"]
		self.assertEqual(intPar["value"], 42)
		self.assertEqual(intPar["description"], "test integer parameter")
	
	def testParameterMetadata(self):
		floatPar = self.tAndD[1]["params"]["exactFloatPar"]
		self.assertEqual(floatPar["value"], 0.25)
		self.assertEqual(floatPar["unit"], "m")
		self.assertEqual(floatPar["ucd"], "phys.width")

	def testMetaInfo(self):
		dd = testhelpers.getTestRD().getById("tableMaker")
		data = rsc.makeData(dd, forceSource=[
			(1, 2, 3, "ei", '2004-05-05')])
		table = data.getPrimaryTable()
		table.addMeta("_warning", "Warning 1")
		table.addMeta("_warning", "Warning 2")
		table.addMeta("_queryStatus", "OK")
		afterRoundtrip = json.loads(
			formats.getFormatted("json", data))
		self.assertEqual(afterRoundtrip["warnings"],
			["Warning 1", "Warning 2"])
		self.assertEqual(afterRoundtrip["queryStatus"],
			"OK")


class FormatOutputTest(testhelpers.VerboseTest):
	"""a base class for tests against formatted output.
	"""
	# extra pain to allow both _FormattedData and _FormattedAndPardData
	# in output
	def _getOutput(self):
		if isinstance(self.output, tuple):
			return self.output[0]
		else:
			return self.output

	def assertOutputHas(self, fragment):
		self.assertTrue(fragment in self._getOutput(),
			"'%s' not found in output"%fragment)

	def assertOutputHasNot(self, fragment):
		self.assertFalse(fragment in self._getOutput(),
			"Forbidded string '%s' found in output"%fragment)


class TextOutputTest(FormatOutputTest):
	resources = [("output", _FormattedData("txt"))]
	
	def testNullSerialization(self):
		self.assertEqual(self.output.split('\n')[1],
			'N/A   N/A  N/A                                                                                         N/A        N/A                              N/A')
	
	def testValues(self):
		self.assertEqual(self.output.split("\n")[0],
			"  1  -2.0  3.0  W\\xe4re es da nicht besser,\\n die Regierung setzte das Volk ab\\tund w\\xe4hlte ein anderes?  2453130.5  Position UNKNOWNFrame 124. -30.")


class TSVColumnsOutputTest(FormatOutputTest):
	resources = [("output", _FormattedData("tsv"))]
	
	def testNullSerialization(self):
		self.assertEqual(self.output.split('\n')[1],
			'N/A\tN/A\tN/A\tN/A\tN/A\tN/A')
	
	def testValues(self):
		self.assertEqual(self.output.split("\n")[0],
			"1\t-2.0\t3.0\tW\\xe4re es da nicht besser,\\n die Regierung setzte"
				" das Volk ab\\tund w\\xe4hlte ein anderes?\t2453130.5\t"
				"Position UNKNOWNFrame 124. -30.")



class CSVOutputTest(FormatOutputTest):
	resources = [("output", _FormattedData("csv"))]

	def testNumerics(self):
		self.assertTrue(self.output.startswith('1,-2.0,3.0,'))
		
	def testStringDefusion(self):
		self.assertOutputHas(',"W\xc3\xa4re es da nicht'
			' besser, die Regierung setzte das Volk ab und w\xc3\xa4hlte'
			' ein anderes?",')
	
	def testNULLs(self):
		self.assertEqual(self.output.split("\r\n")[1], ',,,,,')
	
	def testWeirdTypes(self):
		self.assertOutputHas("2453130.5,Position UNKNOWNFrame 124. -30.")


class CSVHeaderOutputTest(FormatOutputTest):
	resources = [("output", _FormattedData("csv_header", False))]

	def testWeirdTypes(self):
		self.assertOutputHas("2453130.5,Position UNKNOWNFrame 124. -30.")

	def testParamCommentWritten(self):
		self.assertOutputHas('# intPar = 42 // test integer parameter')

 	def testParamStringValueUsed(self):
 		self.assertOutputHas('# roughFloatPar = 0.3 // \r\n')

 	def testNullParamNotWritten(self):
 		self.assertOutputHasNot('stringPar')

	def testHeaderPresent(self):
		self.assertEqual(self.output.split("\r\n")[3], 
			"anint,afloat,adouble,atext,adate,apos")


class DefaultVOTableOutputTest(FormatOutputTest):
	resources = [("output", _FormattedData("votable", False))]

	def testTableDescriptionPickedUp(self):
		self.assertOutputHas('<DESCRIPTION>Some test data with a reason')
	
	def testUnicodeDeclared(self):
		self.assertOutputHas('datatype="unicodeChar"')
	
	def testEncodingInDescription(self):
		self.assertOutputHas(u'Just by a \xb5'.encode("utf-8"))

	def testDataEncoded(self):
		self.assertOutputHas(
			'<STREAM encoding="base64">AAAAAcAAAABACAAAAAAAAAAAAF')

	def testParam(self):
		self.assertOutputHas("<PARAM")
		self.assertOutputHas('name="roughFloatPar"')
		self.assertOutputHas('value="0.3"')
		self.assertOutputHas(' ucd="phys.width"')


class TDVOTableOutputTest(DefaultVOTableOutputTest):
	resources = [("output", _FormattedData("votabletd", False))]

	def testDataEncoded(self):
		self.assertOutputHas("<DATA><TABLEDATA>")
		self.assertOutputHas("<TD>W\xc3\xa4re es da nicht besser,")
	
	def testNullSerialization(self):
		self.assertOutputHas("<TR><TD>-8888</TD><TD>NaN</TD><TD>NaN</TD>"
			"<TD></TD><TD>NaN</TD><TD></TD></TR>")
		self.assertOutputHas('null="-8888"')


class B2VOTableOutputTest(DefaultVOTableOutputTest):
	resources = [("output", _FormattedAndParsedData(
		"votableb2", votable.loads))]

	def testDataEncoded(self):
		self.assertOutputHas("<DATA><BINARY2>")
		self.assertOutputHas('<STREAM encoding="base64">AAAAAAHAAAAAQAg'
			'AAAAAAAAAAABSAFcA5AByAGUA')
	
	def testNULLsDecoded(self):
		data, metadata = self.output[1]
		self.assertEqual(data[1], [None, None, None, None, None, None])
	
	def testGeometry(self):
		# XXX TODO: actually parse this
		data, metadata = self.output[1]
		self.assertEqual(data[0][5], 'Position UNKNOWNFrame 124. -30.')

	def testRegionDeclared(self):
		data, metadata = self.output[1]
		self.assertEqual(metadata[5].xtype, "adql:POINT")


class V11VOTableOutputTest(DefaultVOTableOutputTest):
	resources = [("output", _FormattedData("votabletd1.1"))]

	def testDataEncoded(self):
		self.assertOutputHas("<DATA><TABLEDATA>")
		self.assertOutputHas("<TD>W\xc3\xa4re es da nicht besser,")

	def testNamespace(self):
		self.assertOutputHas('version="1.1"')
		self.assertOutputHas('xmlns="http://www.ivoa.net/xml/VOTable/v1.1"')

	def testXtypeSwallowed(self):
		self.assertFalse("xtype" in self.output)


class FITSOutputTest(FormatOutputTest):
	resources = [("output", _FormattedData("fits"))]

	def testIsFITS(self):
		self.assertOutputHas('SIMPLE  =                    T')
	
	def testBintablePresent(self):
		self.assertOutputHas("XTENSION= 'BINTABLE'")
	
	def testColumnMapping(self):
		self.assertOutputHas("TTYPE2  = 'afloat  '")
		self.assertOutputHas("TTYPE3  = 'adouble '")
		self.assertOutputHas("TFORM3  = 'D       '")
	
	def testSimplePar(self):
		self.assertOutputHas(
			"INTPAR  =                   42 / test integer parameter")
	
	def testHierarchPar(self):
		self.assertOutputHas(
			"HIERARCH exactFloatPar = 0.25 / This can be exactly represented"
				" in two's complemEND")
	
	def testDataEncoded(self):
		self.assertOutputHas("W\xc3\xa4re es da nic")
		self.assertOutputHas('\x00\x00\x00\x01')

	def testNULLsEncoded(self):
		self.assertEqual(self.output[5899:5919],
			'\xff\xff\xddH\x7f\xc0\x00\x00\x7f\xf8\x00\x00\x00\x00\x00\x00None')


class HTMLOutputTest(FormatOutputTest):
	resources = [("output", _FormattedData("html"))]

	def testTableDeclared(self):
		self.assertOutputHas('<table class="results">')
	
	def testMetadataWritten(self):
		self.assertOutputHas('Real</th><th ')
	
	def testNormalData(self):
		self.assertOutputHas(
			'<tr class="data"><td>1</td><td>-2.0</td><td>3.0</td><td>')
		self.assertOutputHas('W\xc3\xa4re es da nicht besser,')
		self.assertOutputHas('w\xc3\xa4hlte ein anderes?</td><td>2453130.5')
	
	def testNULLs(self):
		self.assertOutputHas('<td>N/A</td><td>N/A</td>')

	
class FormatDataTest(testhelpers.VerboseTest):
	resources = [("data", _testDataTable)]

	def testRaising(self):
		self.assertRaises(formats.CannotSerializeIn, formats.formatData,
			"wabbadubba", self.data, open("/dev/null"))


class _ExplicitNullTestTable(testhelpers.TestResource):
	"""A table having some types with explicit null values and an all-null row.
	"""
	def make(self, deps):
		td = base.parseFromString(rscdef.TableDef,
			"""
			<table id="nulls">
				<column name="anint" type="integer"><values nullLiteral="-1"/></column>
				<column name="atext" type="text"><values nullLiteral="xxy"/></column>
				<column name="fixtx" type="char(7)"><values nullLiteral="xxy"/></column>
			</table>
			""")
		return rsc.TableForDef(td,
			rows=[dict((col.name, None) for col in td)])


_explicitNullTestTable = _ExplicitNullTestTable()

class ExplicitNullValueTest(testhelpers.VerboseTest):
	resources = [("nullsTable", _explicitNullTestTable)]

	def _runTestForFormat(self, formatName, assertion):
		destF = StringIO()
		formats.formatData(formatName, self.nullsTable, destF)
		assertion(destF.getvalue())

	def testHTML(self):
		def assertion(data):
			self.assertEqual(
				re.search('<tr class="data">(<td>.*)</tr>', data).group(0),
					'<tr class="data"><td>N/A</td><td>N/A</td><td>N/A</td></tr>')
		self._runTestForFormat("html", assertion)
	
	def testTDVOTable(self):  
		# there's votabletest exercising this more thoroughly, but while we
		# are at it...
		def assertion(data):
			self.failUnless('<VALUES null="-1"' in data)
			self.failUnless('<TR><TD>-1</TD><TD></TD><TD></TD></TR>' in data)
		self._runTestForFormat("votabletd", assertion)

	def testBinVOTable(self):
		def assertion(data):
			self.failUnless('<VALUES null="-1"' in data)
			self.failUnless('<VALUES null="xxy"' in data)
			decoded = re.search(
				'(?s)<STREAM encoding="base64">(.*)</STREAM>',
				data).group(1).decode("base64")
			self.assertEqual(decoded, "".join([
				'\xff\xff\xff\xff',
				'\x00\x00\x00\x03xxy',
				'xxy    ',]))
		self._runTestForFormat("votable", assertion)

	def testCSV(self):
		def assertion(data):
			self.assertEqual(",,", data.strip())
		self._runTestForFormat("csv", assertion)

	def testTSV(self):
		def assertion(data):
			self.assertEqual('N/A\tN/A\tN/A', data.strip())
		self._runTestForFormat("tsv", assertion)


def _mkr(i, s, d, dd, obl, st):
	return locals()

class _RenderedHTML(testhelpers.TestResource):
	def make(self, ignored):
		td = base.parseFromString(outputdef.OutputTableDef,
			"""
			<outputTable id="foo">
				<outputField name="i" type="integer"/>
				<outputField name="s" type="text" description="some string &lt;"/>
				<outputField name="d" type="timestamp" tablehead="date"/>
				<outputField name="dd" type="timestamp" tablehead="Ja"
					unit="Y-M-D" note="junk"/>
				<outputField name="obl" type="text">
					<formatter>
						if data is None:
							return None
						return "&amp;"+data+"&lt;"
					</formatter>
				</outputField>
				<outputField name="st" type="text" wantsRow="True">
					<formatter>
						if data["i"] is None:
							return None
						return T.a(href=str(2*data["i"]))[str(data["obl"])]
					</formatter>
				</outputField>
				<meta name="note" tag="junk">
					This column only here for no purpose at all
				</meta>
			</outputTable>
			""")
		table = rsc.TableForDef(td, rows=[
			_mkr(1, "Hnä".decode("iso-8859-1"), 
				datetime.datetime(2005, 4, 3, 2, 1),
				datetime.datetime(2005, 4, 3, 2, 22), "gurke", None),
			_mkr(None, None, None, None, None, None)])
		destF = StringIO()
		formats.formatData("html", table, destF)
		return destF.getvalue(), testhelpers.getXMLTree(destF.getvalue())


class HTMLRenderTest(testhelpers.VerboseTest):
	resources = [("rendered", _RenderedHTML())]

	def _assertXpathText(self, xpath, value):
		els = self.rendered[1].xpath(xpath)
		self.assertEqual(len(els), 1, "Ambiguous xpath %s"%xpath)
		self.assertEqual(els[0].text, value)

	def testTitleFallbackOnName(self):
		self._assertXpathText("table/thead/tr[1]/th[1]", "I")

	def testTitleIsTablehead(self):
		self._assertXpathText("table/thead/tr[1]/th[4]", "Ja")

	def testDescriptionTitleEscaped(self):
		self.assertEqual(
			self.rendered[1].xpath("table/thead/tr[1]/th[2]")[0].get("title"),
			"some string <")

	def testNoteInTitle(self):
		self._assertXpathText("table/thead/tr[1]/th[4]/sup/a", "junk")

	def testIntRendered(self):
		self._assertXpathText("table/tbody/tr[1]/td[1]", "1")

	def testIntNull(self):
		self._assertXpathText("table/tbody/tr[2]/td[1]", "N/A")

	def testUnicodeRendered(self):
		self._assertXpathText("table/tbody/tr[1]/td[2]", 
			"Hn\xe4".decode("iso-8859-1"))

	def testTextNull(self):
		self._assertXpathText("table/tbody/tr[2]/td[2]", "N/A")
	
	def testDefaultDateDisplay(self):
		self._assertXpathText("table/tbody/tr[1]/td[3]", 
			"2453463.58403")

	def testDateNull(self):
		self._assertXpathText("table/tbody/tr[2]/td[3]", "N/A")

	def testISODateDisplay(self):
		self._assertXpathText("table/tbody/tr[1]/td[4]", 
			"2005-04-03T02:22:00")

	def testDateNull(self):
		self._assertXpathText("table/tbody/tr[2]/td[4]", "N/A")

	def testSingleFormatter(self):
		self._assertXpathText("table/tbody/tr[1]/td[5]", 
			"&gurke<")

	def testSingleFormatterNull(self):
		self._assertXpathText("table/tbody/tr[2]/td[5]", "N/A")

	def testRowFormatter(self):
		self._assertXpathText("table/tbody/tr[1]/td[6]/a", 
			"gurke")
		anchor = self.rendered[1].xpath("table/tbody/tr[1]/td[6]/a")[0]
		self.assertEqual(anchor.get("href"), "2")

	def testRowFormatterNull(self):
		self._assertXpathText("table/tbody/tr[2]/td[6]", "N/A")

	def testFootnotePresent(self):
		self._assertXpathText("dl/dd/p", 
			"This column only here for no purpose at all")
		anchor = self.rendered[1].xpath("dl/dt/a")[0]
		self.assertEqual(anchor.get("name"), "note-junk")


if __name__=="__main__":
	testhelpers.main(HTMLRenderTest)
