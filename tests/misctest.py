"""
Some unit tests that don't (yet) fit a section of their own.
"""

import os
import sys
import unittest

from nevow import context
from nevow.testutil import FakeRequest

import pyfits

import gavo
from gavo import config
from gavo import datadef
from gavo import fitstable
from gavo import nullui
from gavo import sqlsupport
from gavo import table
from gavo.parsing import importparser
from gavo.parsing import resource
from gavo.parsing import rowsetgrammar
from gavo.web import resourcebased


_predefinedFields = {
	"klein": datadef.DataField(dest="klein", dbtype="smallint", source="klein"),
	"prim": datadef.DataField(dest="prim", dbtype="integer", source="prim",
		primary="True", description="Some random primary key"),
	"nopt": datadef.DataField(dest="nopt", dbtype="real", optional="False",
		source="nopt"),
	"echter": datadef.DataField(dest="echter", dbtype="double precision",
		source="echter"),
	"datum": datadef.DataField(dest="datum", dbtype="date", source="datum"),
	"indf": datadef.DataField(dest="indf", dbtype="text", index="find",
		source="indf"),}


def _getFields(*args):
	return [_predefinedFields[a].copy() for a in args]


class VOPlotTest(unittest.TestCase):
	"""test for the VOPlot renderer.
	"""
	def setUp(self):
		self.request = FakeRequest(args={"foo": ["33.3"], "bar": ["w", "v"]})
		self.request.path = "http://urgl.wap.no/nv"
		self.context = context.RequestContext(tag=self.request)

	def testUrlProduction(self):
		"""tests for correct URLs in the VOPlot embed element.
		"""
		vop = resourcebased.VOPlotResponse(None)
		self.assertEqual(
			vop.render_voplotArea(self.context, None).attributes["parameters"],
			"?_FORMAT=VOTable&foo=33.3&bar=w&bar=v&_TDENC=True")
		self.assertEqual(
			vop.render_voplotArea(self.context, None).attributes["votablepath"],
				"http://urgl.wap.no/nv")


class FitsWriterTest(unittest.TestCase):
	def _makeRd(self, fields, rd=None):
		if rd is None:
			rd = resource.ResourceDescriptor()
		rd.set_resdir(os.path.abspath("."))
		rd.set_schema("test")
		grammar = rowsetgrammar.RowsetGrammar(initvals={"dbFields": fields})
		dataDesc = resource.DataDescriptor(rd, 
			id="randomTest",
			Grammar=grammar,
			Semantics=resource.Semantics(
				initvals={
					"recordDefs": [
						resource.RecordDef(initvals={
							"table": "foo",
							"items": fields,
							"create": True,
						})]}))
		rd.addto_dataSrcs(dataDesc)
		return rd

	def testMakeSimpleTable(self):
		"""tests for creation of a simple FITS table.
		"""
		rd = self._makeRd(_getFields("klein", "prim", "nopt", "indf"))
		dataSet = resource.InternalDataSet(rd.get_dataSrcs()[0], 
			table.Table, dataSource=[
				(1, 2, 4.25, "CEN A"),
				(2, 7, 9.32, "QSO 3248+33 Component Gamma")])
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
		rd = self._makeRd(_getFields("klein", "prim", "nopt", "indf"))
		rec2 = resource.RecordDef(initvals={
			"table": "part",
			"items": _getFields("prim", "nopt"),
			"create": True,
		})
		rd.getDataById("randomTest").get_Semantics().addto_recordDefs(
			rec2)
		dataSet = resource.InternalDataSet(rd.get_dataSrcs()[0], 
			table.Table, dataSource=[
				(1, 2, 4.25, "CEN A"),
				(2, 7, 9.32, "QSO 3248+33 Component Gamma")])
		hdulist = fitstable.makeFITSTable(dataSet)
		self.assertEqual(len(hdulist), 3, "Exporting composite data sets"
			" doesn't catch additional tables")

	def testTableWrite(self):
		rd = self._makeRd(_getFields("klein", "prim", "nopt", "indf"))
		dataSet = resource.InternalDataSet(rd.get_dataSrcs()[0], 
			table.Table, dataSource=[
				(1, 2, 4.25, "CEN A"),
				(2, 7, 9.32, "QSO 3248+33 Component Gamma")])
		fName = fitstable.makeFITSTableFile(dataSet)
		self.assert_(os.path.exists(fName), "makeFITSTableFile doesn't"
			" create the file it says it creates")
		hdulist = pyfits.open(fName)
		self.assertEqual(len(hdulist), 2, "makeFITSTableFile wrote"
			" weird file")
		os.unlink(fName)


if __name__=="__main__":
	unittest.main()
