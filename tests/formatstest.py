# -*- coding: iso-8859-1 -*-
"""
Tests having to do with various output formats.
"""

from __future__ import with_statement

import datetime
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
from gavo.base import valuemappers
from gavo.formats import fitstable
from gavo.formats import texttable
from gavo.formats import csvtable
from gavo.formats import votablewrite
from gavo.svcs import outputdef
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


class FITSWriterTest(unittest.TestCase):
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


class TextOutputTest(unittest.TestCase):
	"""tests for the text table output of data sets.
	"""
	def setUp(self):
		self.rd = testhelpers.getTestRD()
		self.dd = self.rd.getById("tableMaker")
	
	def testWithHarmlessData(self):
		"""tests for text output with mostly harmless data.
		"""
		data = rsc.makeData(self.dd, forceSource=[
			(1, 2, 3, "testing", '2004-05-05'),
			(-30, 3.1415, math.pi, "Four score", '2004-05-05'),])
		self.assertEqual(texttable.getAsText(data),
			"1\t2.0\t3.0\ttesting\t2453130.5\n"
			"-30\t3.1415\t3.14159265359\tFour score\t2453130.5\n")
	
	def testWithNulls(self):
		data = rsc.makeData(self.dd, forceSource=[
			(None, None, None, None, None)])
		self.assertEqual(texttable.getAsText(data),
			'None\tNone\tNone\tNone\tNone\n')
	
	def testWithNastyString(self):
		data = rsc.makeData(self.dd, forceSource=[
			(1, 2, 3, "Wäre es da nicht besser,\n die Regierung setzte das Volk"
				" ab\tund wählte ein anderes?", '2004-05-05'),])
		self.assertEqual(texttable.getAsText(data),
			"1\t2.0\t3.0\tW\\xe4re es da nicht besser,\\n die Regierung setzte"
				" das Volk ab\\tund w\\xe4hlte ein anderes?\t2453130.5\n")


class FormatDataTest(testhelpers.VerboseTest):
	"""A test trying various formats on a simple data.
	"""
	def setUp(self):
		rd = testhelpers.getTestRD("testdata")
		self.data = rsc.makeData(rd.getById("twotables"), forceSource=[
			{"anint": 1, "afloat": 0.5, "atext": "eins", 
				"adate": datetime.date(2003, 10, 10), "adouble": 1.5},
			{"anint": 2, "afloat": -0.5, "atext": "zw\xf6i".decode("iso-8859-1"), 
				"adate": datetime.date(2013, 10, 10), "adouble": 2.5},])

	def testRaising(self):
		self.assertRaises(formats.CannotSerializeIn, formats.formatData,
			"wabbadubba", self.data, open("/dev/null"))

	def assertOutputContains(self, format, fragments):
		destF = StringIO()
		formats.formatData(format, self.data, destF)
		result = destF.getvalue()
		for frag in fragments:
			if not frag in result:
				with open("res.data", "w") as f:
					f.write(result)
				raise AssertionError("Format %s: fragment '%s' not in result"
					" (res.data)"%(format, frag))

	def testTSV(self):
		self.assertOutputContains("tsv", [
			"1\t", "\t-0.5\t", "\teins\t", "\t2452922.5\n", "zw\\xf6i"])

	def testVOTable(self):
		self.assertOutputContains("votable", [
			'<DESCRIPTION>Some test data with a reason',
			'</TABLE><TABLE name="barsobal">',
			'<STREAM encoding="base64">AAAAAT/4AAAAAAAAAAAAAkAEAAAA'])

	def testFITS(self):
		self.assertOutputContains("fits", [
			'SIMPLE  =                    T',
			"XTENSION= 'BINTABLE'",
			"TTYPE2  = 'afloat  '",
			"TTYPE2  = 'adouble '",
			"eins",
			'zw\xc3\xb6i'])

	def testHTML(self):
		self.assertOutputContains("html", [
			'<table class="results">',
			'Real</th><th ',
			'td>-0.5</td><td>zw\xc3\xb6i</td><td>2456575.5</td>'])

	def testCSV(self):
		self.assertOutputContains("csv", ["2,-0.5,zw\xc3\xb6i,2456575.5"])


class _NullTestTable(testhelpers.TestResource):
	"""A table having some types and an all-null row.
	"""
	def make(self, deps):
		td = base.parseFromString(rscdef.TableDef,
			"""
			<table id="nulls">
				<column name="anint" type="integer">
					<values nullLiteral="-2147483648"/>
				</column>
				<column name="afloat"/>
				<column name="adouble" type="double precision"/>
				<column name="atext" type="text"/>
				<column name="adate" type="date" displayHint="format=humanDate"/>
				<column name="aPos" type="spoint"/>
			</table>
			""")
		return rsc.TableForDef(td,
			rows=[dict((col.name, None) for col in td)])


_nullTestTable = _NullTestTable()


class NullValueTest(testhelpers.VerboseTest):
	resources = [("nullsTable", _nullTestTable)]

	def _runTestForFormat(self, formatName, assertion):
		destF = StringIO()
		formats.formatData(formatName, self.nullsTable, destF)
		assertion(destF.getvalue())

	def testHTML(self):
		def assertion(data):
			self.assertEqual(
				re.search("<tr>(<td>.*)</tr>", data).group(0),
				"<tr><td>N/A</td><td>N/A</td><td>N/A</td>"
					"<td>N/A</td><td>N/A</td><td>N/A</td></tr>")
		self._runTestForFormat("html", assertion)
	
	def testTDVOTable(self):  
		# there's votabletest exercising this more thoroughly, but while we
		# are at it...
		def assertion(data):
			self.failUnless('<VALUES null="-2147483648"' in data)
			self.failUnless('<TR><TD>-2147483648</TD><TD>NaN</TD><TD>'
				'NaN</TD><TD></TD><TD></TD><TD></TD></TR>' in data)
		self._runTestForFormat("votabletd", assertion)

	def testBinVOTable(self):
		def assertion(data):
			self.failUnless('<VALUES null="-2147483648"' in data)
			decoded = re.search(
				'(?s)<STREAM encoding="base64">(.*)</STREAM>',
				data).group(1).decode("base64")
			self.assertEqual(decoded, "".join([
				'\x80\x00\x00\x00', 
				'\x7f\xc0\x00\x00', 
				'\x7f\xf8\x00\x00\x00\x00\x00\x00', 
				'\x00\x00\x00\x00', 
				'\x00\x00\x00\x00', 
				'\x00\x00\x00\x00']))
		self._runTestForFormat("votable", assertion)

	def testBin2VOTable(self):
		def assertion(data):
			self.failUnless('<VALUES null="-2147483648"' in data)
			decoded = re.search(
				'(?s)<STREAM encoding="base64">(.*)</STREAM>',
				data).group(1).decode("base64")
			self.assertEqual(decoded, "".join([
				'\xfc\x00\x00\x00\x00', 
				'\x7f\xc0\x00\x00', 
				'\x7f\xf8\x00\x00\x00\x00\x00\x00', 
				'\x00\x00\x00\x00', 
				'\x00\x00\x00\x00', 
				'\x00\x00\x00\x00']))
		self._runTestForFormat("votableb2", assertion)


	def testCSV(self):
		def assertion(data):
			self.assertEqual(",,,,,", data.strip())
		self._runTestForFormat("csv", assertion)

	def testTSV(self):
		def assertion(data):
			self.assertEqual('None\tNone\tNone\tNone\tNone\tNone', data.strip())
		self._runTestForFormat("tsv", assertion)


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
				re.search("<tr>(<td>.*)</tr>", data).group(0),
					'<tr><td>N/A</td><td>N/A</td><td>N/A</td></tr>')
		self._runTestForFormat("html", assertion)
	
	def testTDVOTable(self):  
		# there's votabletest exercising this more thoroughly, but while we
		# are at it...
		def assertion(data):
			self.failUnless('<VALUES null="-1"' in data)
			self.failUnless('<TR><TD>-1</TD><TD>xxy</TD><TD>xxy</TD>'
				'</TR>' in data)
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
			self.assertEqual('None\tNone\tNone', data.strip())
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
