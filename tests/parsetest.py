"""
Tests pertaining to the parsing system
"""


import unittest

from gavo.parsing import macros
from gavo.parsing import processors


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


if __name__=="__main__":
	unittest.main()
