# -*- coding: iso-8859-1 -*-
"""
Some unit tests that don't (yet) fit a section of their own.
"""

import cStringIO
import datetime
import math
import os
import shutil
import sys
import tempfile
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
from gavo import texttable
from gavo import votable
from gavo.helpers import filestuff
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
					"tableDefs": [
						resource.TableDef(rd, initvals={
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
		rec2 = resource.TableDef(rd, initvals={
			"table": "part",
			"items": _getFields("prim", "nopt"),
			"create": True,
		})
		rd.getDataById("randomTest").get_Semantics().addto_tableDefs(
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


class MapperTest(unittest.TestCase):
	"""collects tests for votable/html value mappers.
	"""
	def testJdMap(self):
		colProps = {"sample": datetime.datetime(2005, 6, 4, 23, 12, 21),
			"unit": "d"}
		mapper = votable.datetimeMapperFactory(colProps)
		self.assertAlmostEqual(2453526.4669097224,
			mapper(datetime.datetime(2005, 6, 4, 23, 12, 21)))
		self.assertAlmostEqual(2434014.6659837961,
			mapper(datetime.datetime(1952, 1, 3, 3, 59, 1)))
		self.assertAlmostEqual(2451910.0,
			mapper(datetime.datetime(2000, 12, 31, 12, 00, 00)))
		self.assertAlmostEqual(2451909.999988426,
			mapper(datetime.datetime(2000, 12, 31, 11, 59, 59)))


class RenamerDryTest(unittest.TestCase):
	"""tests for some aspects of the file renamer without touching the file system.
	"""
	def testSerialization(self):
		"""tests for correct serialization of clobbering renames.
		"""
		f = filestuff.FileRenamer({})
		fileMap = {'a': 'b', 'b': 'c', '2': '3', '1': '2'}
		self.assertEqual(f.makeRenameProc(fileMap),
			[('b', 'c'), ('a', 'b'), ('2', '3'), ('1', '2')])
	
	def testCycleDetection(self):
		"""tests for cycle detection in renaming recipies.
		"""
		f = filestuff.FileRenamer({})
		fileMap = {'a': 'b', 'b': 'c', 'c': 'a'}
		self.assertRaises(filestuff.Error, f.makeRenameProc, fileMap)


class RenamerWetTest(unittest.TestCase):
	"""tests for behaviour of the file renamer on the file system.
	"""
	def setUp(self):
		def touch(name):
			f = open(name, "w")
			f.close()
		self.testDir = tempfile.mkdtemp("testrun")
		for fName in ["a.fits", "a.txt", "b.txt", "b.jpeg", "foo"]:
			touch(os.path.join(self.testDir, fName))

	def tearDown(self):
		shutil.rmtree(self.testDir, onerror=lambda exc: None)

	def testOperation(self):
		"""tests an almost-realistic application
		"""
		f = filestuff.FileRenamer.loadFromFile(
			cStringIO.StringIO("a->b \nb->c\n 2->3\n1 ->2\n\n# a comment\n"
				"foo-> bar\n"))
		f.renameInPath(self.testDir)
		found = set(os.listdir(self.testDir))
		expected = set(["b.fits", "b.txt", "c.txt", "c.jpeg", "bar"])
		self.assertEqual(found, expected)
	
	def testNoClobber(self):
		"""tests for effects of repeated application.
		"""
		f = filestuff.FileRenamer.loadFromFile(
			cStringIO.StringIO("a->b \nb->c\n 2->3\n1 ->2\n\n# a comment\n"
				"foo-> bar\n"))
		f.renameInPath(self.testDir)
		self.assertRaises(filestuff.Error, f.renameInPath, self.testDir)


class TextOutputTest(unittest.TestCase):
	"""tests for the text table output of data sets.
	"""
	def setUp(self):
		self.rd = importparser.getRd(os.path.abspath("test.vord"))
		self.dd = self.rd.getDataById("tableMaker")
	
	def testWithHarmlessData(self):
		"""tests for text output with mostly harmless data.
		"""
		data = resource.InternalDataSet(self.dd, dataSource=[
			(1, 2, 3, "testing", '2004-05-05'),
			(-30, 3.1415, math.pi, "Four score", '2004-05-05'),])
		self.assertEqual(texttable.getAsText(data),
			"1\t2.0\t3.0\ttesting\t2453130.5\n"
			"-30\t3.1415\t3.14159265359\tFour score\t2453130.5\n")
	
	def testWithNulls(self):
		data = resource.InternalDataSet(self.dd, dataSource=[
			(None, None, None, None, None)])
		self.assertEqual(texttable.getAsText(data),
			'-2147483648\tnan\tnan\t\tNone\n')
	
	def testWithNastyString(self):
		data = resource.InternalDataSet(self.dd, dataSource=[
			(1, 2, 3, "Wäre es da nicht besser,\n die Regierung setzte das Volk"
				" ab\tund wählte ein anderes?", '2004-05-05'),])
		self.assertEqual(texttable.getAsText(data),
			"1\t2.0\t3.0\tW\\xe4re es da nicht besser,\\n die Regierung setzte"
				" das Volk ab\\tund w\\xe4hlte ein anderes?\t2453130.5\n")

def singleTest():
	suite = unittest.makeSuite(TextOutputTest, "test")
	runner = unittest.TextTestRunner()
	runner.run(suite)


if __name__=="__main__":
	unittest.main()
#	singleTest()
