# -*- coding: iso-8859-1 -*-
"""
Tests for grammars and their helpers.
"""

import datetime
import os
from cStringIO import StringIO

from gavo import base
from gavo import rsc
from gavo import rscdef
from gavo.helpers import testhelpers



class PredefinedRowfilterTest(testhelpers.VerboseTest):
	def testOnIndex(self):
		dd = testhelpers.getTestRD().getById("expandOnIndex")
		data = rsc.makeData(dd, forceSource=[{"b": 3, "c": 4, "a": "eins"}])
		self.assertEqual(data.getPrimaryTable().rows,
			[{'a': u'eins', 'c': 4, 'b': 3, 'd': 3}, 
				{'a': u'eins', 'c': 4, 'b': 3, 'd': 4}])

	def testDateRange(self):
		dd = testhelpers.getTestRD().getById("expandOnDate")
		data = rsc.makeData(dd, forceSource=[{"start": datetime.date(2000, 5, 8), 
				"end": datetime.date(2000, 5, 10), "a": "line1"},
			{"start": datetime.date(2005, 5, 8), 
			"end": datetime.date(2005, 5, 8), "a": "line2"},])
		self.assertEqual(data.getPrimaryTable().rows, [
			{'a': u'line1', 'e': datetime.datetime(2000, 5, 8, 0, 0)}, 
			{'a': u'line1', 'e': datetime.datetime(2000, 5, 8, 12, 0)}, 
			{'a': u'line1', 'e': datetime.datetime(2000, 5, 9, 0, 0)}, 
			{'a': u'line1', 'e': datetime.datetime(2000, 5, 9, 12, 0)},
			{'a': u'line1', 'e': datetime.datetime(2000, 5, 10, 0, 0)}, 
			{'a': u'line1', 'e': datetime.datetime(2000, 5, 10, 12, 0)}, 
			{'a': u'line2', 'e': datetime.datetime(2005, 5, 8, 0, 0)}, 
			{'a': u'line2', 'e': datetime.datetime(2005, 5, 8, 12, 0)}])

	def testDateRangeDefault(self):
		dd = testhelpers.getTestRD().getById("expandOnDateDefault")
		data = rsc.makeData(dd, forceSource=[{"start": datetime.date(2000, 5, 8), 
				"end": datetime.date(2000, 5, 9), "a": "line1"},
			{"start": datetime.date(2005, 5, 8), 
			"end": datetime.date(2005, 5, 8), "a": "line2"},])
		self.assertEqual(data.getPrimaryTable().rows, [
			{'a': u'line1', 'e': datetime.datetime(2000, 5, 8, 0, 0)}, 
			{'a': u'line1', 'e': datetime.datetime(2000, 5, 9, 0, 0)}, 
			{'a': u'line2', 'e': datetime.datetime(2005, 5, 8, 0, 0)}])

	def testExpandComma(self):
		dd = testhelpers.getTestRD().getById("expandComma")
		data = rsc.makeData(dd, forceSource=[{"stuff": "x,yz,foo, bar ",
			"b": 23}, {"stuff":"quux", "b": 3}])
		self.assertEqual(data.getPrimaryTable().rows, [
			{'a': u'x', 'b': 23}, {'a': u'yz', 'b': 23}, 
			{'a': u'foo', 'b': 23}, {'a': u'bar', 'b': 23}, 
			{'a': u'quux', 'b': 3}])


ignoreTestData = [
	{'a': 'xy', 'b': 'cc', 'd': 'yok'},
	{'a': 'xy', 'b': 'DD'},
	{'a': 'zz', 'b': ''},
	]

class IgnoreTests(testhelpers.VerboseTest):
	def _makeGrammar(self, ignoreClauses):
		return base.parseFromString(rscdef.getGrammar("dictlistGrammar"), 
			"<dictlistGrammar><ignoreOn>%s</ignoreOn></dictlistGrammar>"%
				ignoreClauses)

	def _makeBailingGrammar(self, ignoreClauses):
		return base.parseFromString(rscdef.getGrammar("dictlistGrammar"), 
			"<dictlistGrammar><ignoreOn bail='True'>%s</ignoreOn></dictlistGrammar>"%
				ignoreClauses)

	def _assertResultLen(self, ignoreClauses, expectedLength):
		res = list(self._makeGrammar(ignoreClauses).parse(ignoreTestData))
		self.assertEqual(len(res), expectedLength, 
			"%s yielded %s, expected %d rows"%(ignoreClauses, res, expectedLength))

	def testKeyIs(self):
		self._assertResultLen('<keyIs key="a" value="xy"/>', 1)
		self._assertResultLen('<keyIs key="a" value="zz"/>', 2)
		self._assertResultLen('<keyIs key="a" value=""/>', 3)
		self._assertResultLen('<keyIs key="b" value=""/>', 2)
		self._assertResultLen('<keyIs key="d" value="yok"/>', 2)

	def testKeyPresent(self):
		self._assertResultLen('<keyPresent key="a"/>', 0)
		self._assertResultLen('<keyPresent key="b"/>', 0)
		self._assertResultLen('<keyPresent key="d"/>', 2)
		self._assertResultLen('<keyPresent key="yikes"/>', 3)

	def testTriggerSeq(self):
		self._assertResultLen('<keyPresent key="d"/><keyIs key="b" value=""/>'
			, 1)

	def testNot(self):
		self._assertResultLen('<not><keyPresent key="a"/></not>', 3)
		self._assertResultLen('<not><keyPresent key="d"/></not>', 1)
		self._assertResultLen('<not><keyPresent key="d"/>'
			'<keyIs key="b" value=""/></not>', 2)
	
	def testAnd(self):
		self._assertResultLen('<and><keyIs key="a" value="xy"/>'
			'<keyIs key="b" value="DD"/></and>', 2)

	def testBail(self):
		g = self._makeBailingGrammar('<keyMissing key="d"/>')
		def parseAll():
			return list(g.parse(ignoreTestData))
		self.assertRaises(rscdef.TriggerPulled, parseAll)
	
	def testBailNot(self):
		g = self._makeBailingGrammar('<keyMissing key="a"/>')
		list(g.parse(ignoreTestData))


class EmbeddedGrammarTest(testhelpers.VerboseTest):
	def testSimple(self):
		from gavo import rscdesc
		rd = base.parseFromString(rscdesc.RD, 
			"""<resource schema="test"><data id="fake"><embeddedGrammar>
				<iterator><code>
					yield {'x': 1, 'y': 2}
					yield {'x': 2, 'y': 2}
				</code></iterator></embeddedGrammar></data></resource>""")
		self.assertEqual(list(rd.dds[0].grammar.parse(None)),
			[{'y': 2, 'x': 1}, {'y': 2, 'x': 2}])


class KVGrammarTest(testhelpers.VerboseTest):
	def testSimple(self):
		grammar = base.parseFromString(rscdef.getGrammar("keyValueGrammar"),
			'<keyValueGrammar commentPattern="--.*?\*/" enc="utf-8"/>')
		rec = list(grammar.parse(StringIO("a=b\nc=2 --nothing*/\n"
			"wonkö:Närd".decode("iso-8859-1").encode("utf-8"))))[0]
		self.assertEqual(rec["a"], 'b')
		self.assertEqual(rec["c"], '2')
		self.assertEqual(rec[u"wonkö"], u'Närd')
	
	def testPairs(self):
		grammar = base.parseFromString(rscdef.getGrammar("keyValueGrammar"),
			'<keyValueGrammar kvSeparators="/" pairSeparators="%"'
			' yieldPairs="True"/>')
		recs = [(v['key'], v['value']) 
			for v in grammar.parse(StringIO("a/b%c/d"))]
		self.assertEqual(recs, [('a', 'b'), ('c', 'd')])

	def testError(self):
		self.assertRaisesWithMsg(base.LiteralParseError,
			"At <internal source>, unknown position: '**' is not a valid"
				" value for commentPattern",
			base.parseFromString, 
			(rscdef.getGrammar("keyValueGrammar"),
			'<keyValueGrammar commentPattern="**"/>'))


if __name__=="__main__":
	testhelpers.main(EmbeddedGrammarTest)
