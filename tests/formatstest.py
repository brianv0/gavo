# -*- coding: iso-8859-1 -*-
"""
Tests having to do with various output formats.
"""

from __future__ import with_statement

import datetime
import math
import os
import unittest
from cStringIO import StringIO


from gavo import base
from gavo import formats
from gavo import rsc
from gavo import rscdef
from gavo import rscdesc
from gavo.base import valuemappers
from gavo.formats import fitstable
from gavo.formats import texttable
from gavo.formats import csvtable
from gavo.helpers import testhelpers
from gavo.utils import pyfits




_colDefs = {
	"klein": '<column name="klein"  type="smallint"/>',
	"prim": '<column name="prim" type="integer"'
		' description="Some random primary key"/><primary>prim</primary>',
	"nopt": '<column name="nopt" type="real" required="True"/>',
	"echter": '<column name="echter" type="double precision"/>',
	"datum": '<column name="datum" type="date"/>',
	"indf": '<column name="indf" type="text"/><index columns="indf"/>'}


def _getFields(*args):
	return [_colDefs[a] for a in args]


class FITSWriterTest(unittest.TestCase):
	def _makeRd(self, colNames, rd=None):
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
		rd = self._makeRd(["klein", "prim", "nopt", "indf"])
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
		rd = self._makeRd(("klein", "prim", "nopt", "indf"))
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
		rd = self._makeRd(("klein", "prim", "nopt", "indf"))
		dataSet = rsc.makeData(rd.getById("randomTest"),
			forceSource=self._testData)
		fName = fitstable.makeFITSTableFile(dataSet)
		self.assert_(os.path.exists(fName), "makeFITSTableFile doesn't"
			" create the file it says it creates")
		hdulist = pyfits.open(fName)
		self.assertEqual(len(hdulist), 2, "makeFITSTableFile wrote"
			" weird file")
		os.unlink(fName)


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
			'-2147483648\tnan\tnan\t\tNone\n')
	
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
			'<table class="results"><tr>',
			'Real</th><th ',
			'td>-0.5</td><td>zw\xc3\xb6i</td><td>2456575.5'])

	def testCSV(self):
		self.assertOutputContains("csv", ["2,-0.5,zw\xc3\xb6i,2456575.5"])

if __name__=="__main__":
	testhelpers.main(FormatDataTest)
