"""
Tests pertaining to the parsing system
"""


import os
import unittest

from gavo import nullui
from gavo.parsing import importparser
from gavo.parsing import macros
from gavo.parsing import processors
from gavo.parsing import resource


class MacroErrorTest(unittest.TestCase):
	"""Tests for error reporting of macros and processors.
	"""
	def testDateRangeFieldReporting(self):
		p = processors.DateExpander([("start", "startDate", ""),
			("end", "endDate", ""), ("hrInterval", "intv", "")])
		try:
			l = p(None, {"startDate": "2000-01-01", "endDate": "2000-13-31",
				"intv": "300"})
		except Exception, msg:
			self.assertEqual(msg.fieldName, "endDate")
		else:
			self.fail("2000-13-31 is regarded as a valid date...")
		try:
			l = p(None, {"startDate": "2000-01-01", "endDate": "2000-12-31",
				"intv": "a00"})
		except Exception, msg:
			self.assertEqual(msg.fieldName, "intv")
		else:
			self.fail("a00 is regarded as a valid integer...")


class ProcessorsTest(unittest.TestCase):
	"""Tests for some row processors.
	"""
	def setUp(self):
		self.rd = importparser.getRd(os.path.abspath("test.vord"))
	
	def testExpandComma(self):
		"""test for correct operation of the expandComma row processor.
		"""
		dd = self.rd.getDataById("processortest")
		data = resource.InternalDataSet(dd, dataSource=[
			(12.5, "one, two, three"),
			(1.2, ""),
			(2.2, "four,"),
			(0, "five")])
		rows = data.getPrimaryTable().rows
		self.assertEqual(len(rows), 5)
		self.assertAlmostEqual(rows[0]["c"], 12.5)
		self.assertEqual(rows[0]["tf"], "one")
		self.assertEqual(rows[4]["tf"], "five")
	

if __name__=="__main__":
	unittest.main()
