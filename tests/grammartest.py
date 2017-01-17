# -*- coding: iso-8859-1 -*-
"""
Tests for grammars and their helpers.
"""

#c Copyright 2008-2017, the GAVO project
#c
#c This program is free software, covered by the GNU GPL.  See the
#c COPYING file in the source distribution.


import datetime
import os
import struct
from cStringIO import StringIO

from gavo.helpers import testhelpers

from gavo import base
from gavo import rsc
from gavo import rscdef
from gavo import utils
from gavo.grammars import binarygrammar
from gavo.grammars import columngrammar
from gavo.grammars import common
from gavo.grammars import directgrammar
from gavo.grammars import fitsprodgrammar
from gavo.grammars import pdsgrammar
from gavo.grammars import regrammar
from gavo.helpers import testtricks

import tresc


def getCleaned(rawIter):
	"""returns cleaned rawdicts form a rawdict iterator

	(this currently just kills the parser_ key).
	"""
	res = []
	for d in rawIter:
		del d["parser_"]
		res.append(d)
	return res


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

	def testStandardPreviewPath(self):
		dd = testhelpers.getTestRD().getById("productimport-skip")
		res = set()
		for source in dd.iterSources(None):
			for row in dd.grammar.parse(source, None):
				res.add(row["prodtblPreview"])
		self.assertEqual(res, set(['./prefoo/ZGF0YS9hLmltcA==',
			'./prefoo/ZGF0YS9iLmltcA==']))


class SequencedRowfilterTest(testhelpers.VerboseTest):
	def _makeGrammar(self, rowgenDefs):
		return base.parseFromString(rscdef.getGrammar("dictlistGrammar"), 
			"<dictlistGrammar>%s</dictlistGrammar>"%rowgenDefs)

	def _getProcessedFor(self, filterDefs, input):
		g = self._makeGrammar(filterDefs)
		res = getCleaned(g.parse(input))
		return res

	def testSimplePipe(self):
		res = self._getProcessedFor("""
			<rowfilter><code>
					row["output"] = row["input"]+1
					del row["input"]
					yield row
			</code></rowfilter>
			<rowfilter><code>
					row["processed"] = row["output"]*row["output"]
					yield row
			</code></rowfilter>""", [{"input": 2}])
		self.assertEqual(res, [{"output":3, "processed":9}])
	
	def testForking(self):
		res = self._getProcessedFor("""
			<rowfilter><code>
					b = row["input"]
					del row["input"]
					row["output"] = b
					yield row.copy()
					row["output"] += b
					yield row
			</code></rowfilter>
			<rowfilter><code>
					row["processed"] = row["output"]*row["output"]
					yield row.copy()
					row["processed"] = row["processed"]*row["output"]
					yield row
			</code></rowfilter>""", [{"input": 2}])
		self.assertEqual(res, [
			{"output":2, "processed":4},
			{"output":2, "processed":8},
			{"output":4, "processed":16},
			{"output":4, "processed":64},])


class MacroTest(testhelpers.VerboseTest):
	def testDLURL(self):
		from gavo import rscdesc
		rd = base.parseFromString(rscdesc.RD, r"""<resource schema="test"
				resdir=".">
			<table id="foo"><column name="prodtblPath" type="text"/></table>
			<data id="i">
				<sources pattern="data/ex.fits"/>
				<fitsProdGrammar>
					<rowfilter procDef="//products#define">
						<bind name="table">"foo"</bind>
						<bind name="path">\fullDLURL{echdl}</bind>
					</rowfilter>
				</fitsProdGrammar>
				<make table="foo"/></data>
				<service id="echdl"><datalinkCore/></service></resource>""")
		rd.sourceId = "glob/bob"
		rows = rsc.makeData(rd.getById("i")).getPrimaryTable().rows
		self.assertEqual(rows[0]["prodtblPath"],
			"http://localhost:8080/glob/bob/echdl/dlget"
			"?ID=ivo%3A%2F%2Fx-unregistred%2F%7E%3Fdata%2Fex.fits")


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
		self.assertEqual(getCleaned(rd.dds[0].grammar.parse(None)),
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
			"At [<keyValueGrammar commentPat...], (1, 0):"
			" '**' is not a valid value for commentPattern",
			base.parseFromString, 
			(rscdef.getGrammar("keyValueGrammar"),
			'<keyValueGrammar commentPattern="**"/>'))


class CSVGrammarTest(testhelpers.VerboseTest):
	def testSimple(self):
		grammar = base.parseFromString(rscdef.getGrammar("csvGrammar"),
			'<csvGrammar/>')
		recs = getCleaned(grammar.parse(StringIO("la,le,lu\n1, 2, schaut")))
		self.assertEqual(recs,
			[{"la": '1', "le": ' 2', "lu": " schaut"}])

	def testStrip(self):
		grammar = base.parseFromString(rscdef.getGrammar("csvGrammar"),
			'<csvGrammar strip="True"/>')
		recs = getCleaned(grammar.parse(StringIO("la,le,lu\n1, 2, schaut")))
		self.assertEqual(recs,
			[{"la": '1', "le": '2', "lu": "schaut"}])

	def testNames(self):
		grammar = base.parseFromString(rscdef.getGrammar("csvGrammar"),
			'<csvGrammar names="col1, col2, col3"/>')
		recs = getCleaned(grammar.parse(StringIO("la,le,lu\n1,2,schaut")))
		self.assertEqual(recs, [
			{"col1": "la", "col2": "le", "col3": "lu"},
			{"col1": '1', "col2": '2', "col3": "schaut"}])

	def testSkipLines(self):
		grammar = base.parseFromString(rscdef.getGrammar("csvGrammar"),
			'<csvGrammar topIgnoredLines="3"/>')
		recs = getCleaned(grammar.parse(StringIO(
			"There's\nsome\njunk at the top here\nla,le,lu\n1,2,schaut")))
		self.assertEqual(recs, [
			{"la": '1', "le": '2', "lu": "schaut"}])

	def testWithPreFilter(self):
		grammar = base.parseFromString(rscdef.getGrammar("csvGrammar"),
			'<csvGrammar preFilter="zcat"/>')
		recs = getCleaned(grammar.parse(StringIO(
			'\x1f\x8b\x08\x08\xb7\xd2\xa4U\x00\x03zw.txt\x00\xcbI\xd4\xc9I'
			'\xd5\xc9)\xe52\xd41\xd2)N\xceH,-\xe1\x02\x00S@8\x1f\x14\x00\x00\x00')))
		self.assertEqual(recs, [
			{"la": '1', "le": '2', "lu": "schaut"}])


class ColDefTest(testhelpers.VerboseTest):
	def testSimple(self):
		g = base.parseFromString(columngrammar.ColumnGrammar,
			'<columnGrammar colDefs="a:1 B:2-5 C_dfoo:4 _gobble:6-8"/>')
		res = getCleaned(g.parse(StringIO("abcdefghijklmnoq")))[0]
		self.assertEqual(res, {'a': 'a', 'C_dfoo': 'd', 'B': 'bcde', 
			'_gobble': 'fgh'})

	def testFunkyWhite(self):
		g = base.parseFromString(columngrammar.ColumnGrammar,
			'<columnGrammar colDefs="a :1 B: 2 - 5 C_dfoo: 4 _gobble : 6 -8"/>')
		res = getCleaned(g.parse(StringIO("abcdefghijklmnoq")))[0]
		self.assertEqual(res, {'a': 'a', 'C_dfoo': 'd', 'B': 'bcde', 
			'_gobble': 'fgh'})
	
	def testHalfopen(self):
		g = base.parseFromString(columngrammar.ColumnGrammar,
			'<columnGrammar><colDefs>a:5- B:-5</colDefs></columnGrammar>')
		res = getCleaned(g.parse(StringIO("abcdefg")))[0]
		self.assertEqual(res, {'a': 'efg', 'B': 'abcde'})

	def testBeauty(self):
		g = base.parseFromString(columngrammar.ColumnGrammar,
			"""<columnGrammar><colDefs>
				a:      5- 
				B:      -5
				gnugga: 1-2
				</colDefs></columnGrammar>""")
		res = getCleaned(g.parse(StringIO("abcdefg")))[0]
		self.assertEqual(res, {'a': 'efg', 'B': 'abcde', 'gnugga': 'ab'})

	def testErrorBadChar(self):
		self.assertRaisesWithMsg(base.LiteralParseError,
			"At [<columnGrammar><colDefs>a:5...], (1, 34):"
			" 'a:5-% B:-5' is not a valid value for colDefs",
			base.parseFromString, (columngrammar.ColumnGrammar,
			'<columnGrammar><colDefs>a:5-% B:-5</colDefs></columnGrammar>'))
	
	def testErrorNiceHint(self):
		try:
			base.parseFromString(columngrammar.ColumnGrammar,
				'<columnGrammar><colDefs>a:5- B:c</colDefs></columnGrammar>')
		except base.LiteralParseError, ex:
			self.failUnless(ex.hint.endswith(
				"Expected end of text (at char 5), (line:1, col:6)"))
		else:
			self.fail("LiteralParseError not raised")


class ColumnGrammarTest(testhelpers.VerboseTest):
	def testWithComment(self):
		g = base.parseFromString(columngrammar.ColumnGrammar,
			'<columnGrammar commentIntroducer="#"><colDefs>a:1-</colDefs>'
			'</columnGrammar>')
		res = list(g.parse(StringIO("#Anfang\nMitte\n#Ende")))
		self.assertEqual(len(res), 1)
		self.assertEqual(res[0]['a'], 'Mitte')

	def testWithoutComment(self):
		g = base.parseFromString(columngrammar.ColumnGrammar,
			'<columnGrammar><colDefs>a:1-</colDefs>'
			'</columnGrammar>')
		res = list(g.parse(StringIO("#Anfang\nMitte\n#Ende")))
		self.assertEqual(len(res), 3)
		self.assertEqual(res[0]['a'], "#Anfang")


class BinaryRecordTest(testhelpers.VerboseTest):
	def testTypes(self):
		brd = base.parseFromString(binarygrammar.BinaryRecordDef,
			"""<binaryRecordDef binfmt="packed">
				chr(1s) fong(12s) b(b) B(B) h(h) H(H) i(i) I(I) q(q) Q(Q)
				f(f) d(d)</binaryRecordDef>""")
		self.assertEqual(brd.structFormat, "=1s12sbBhHiIqQfd")
		self.assertEqual(brd.recordLength, 55)

	def testBadIdentifier(self):
		self.assertRaises(base.LiteralParseError,
			base.parseFromString, binarygrammar.BinaryRecordDef,
			"<binaryRecordDef>22s(d)</binaryRecordDef>")

	def testBadCode(self):
		self.assertRaises(base.LiteralParseError,
			base.parseFromString, binarygrammar.BinaryRecordDef,
			"<binaryRecordDef>x(P)</binaryRecordDef>")

	def testNativeTypes(self):
		brd = base.parseFromString(binarygrammar.BinaryRecordDef,
			"<binaryRecordDef>c(1s)s(i)t(d)</binaryRecordDef>")
		self.assertEqual(brd.structFormat, "1sid")
		self.failIf(brd.recordLength==13, "You platform doesn't pack?")


class BinaryGrammarTest(testhelpers.VerboseTest):
	plainTestData = [(42, 0.25), (-30, 40.)]
	plainExpectedResult = [{'s': 42, 't': 0.25}, {'s': -30, 't': 40.0}]

	def testUnarmoredParse(self):
		inputFile = StringIO("u"*20+"".join(struct.pack("id", *r) 
			for r in self.plainTestData))
		grammar = base.parseFromString(binarygrammar.BinaryGrammar,
			"""<binaryGrammar skipBytes="20"><binaryRecordDef>s(i)t(d)
			</binaryRecordDef></binaryGrammar>""")
		self.assertEqual(
			getCleaned(grammar.parse(inputFile)),
			self.plainExpectedResult)

	def testNetworkBinfmt(self):
		inputFile = StringIO("".join(struct.pack("!id", *r) 
			for r in self.plainTestData))
		grammar = base.parseFromString(binarygrammar.BinaryGrammar,
			"""<binaryGrammar><binaryRecordDef binfmt="big">s(i)t(d)
			</binaryRecordDef></binaryGrammar>""")
		self.assertEqual(
			getCleaned(grammar.parse(inputFile)),
			self.plainExpectedResult)


	def testFortranParse(self):

		def doFortranArmor(data):
			return struct.pack("i%dsi"%len(data), len(data), data, len(data))

		inputFile = StringIO("".join(doFortranArmor(struct.pack("id", *r))
			for r in self.plainTestData))
		grammar = base.parseFromString(binarygrammar.BinaryGrammar,
			"""<binaryGrammar armor="fortran"><binaryRecordDef>s(i)t(d)
			</binaryRecordDef></binaryGrammar>""")
		self.assertEqual(
			getCleaned(grammar.parse(inputFile)),
			self.plainExpectedResult)


class FITSProdGrammarTest(testhelpers.VerboseTest):

	sample = os.path.join(base.getConfig("inputsDir"), "data", "ex.fits")
	grammarT = fitsprodgrammar.FITSProdGrammar

	def _getParse(self, grammarDef):
		grammar = base.parseFromString(self.grammarT, grammarDef)
		return list(grammar.parse(self.sample))[0]

	def _assertBasicFieldsPresent(self, d):
		self.assertEqual(len(d), 104)
		self.assertEqual(d["EXTEND"], True)
		self.assertEqual(d["OBSERVER"], "M.Wolf")
		self.assertEqual(d["LATPOLE"], 0.0)
		self.failUnless("PLATE_ID" in d)

	def testBasic(self):
		self._assertBasicFieldsPresent(
			self._getParse("""<fitsProdGrammar qnd="False"/>"""))

	def testBasicQnD(self):
		self._assertBasicFieldsPresent(
			self._getParse("""<fitsProdGrammar/>"""))

	def testNameMapping(self):
		d = self._getParse("""<fitsProdGrammar><mapKeys><map
			dest="blind">EXPTIME</map></mapKeys></fitsProdGrammar>""")
		self.assertEqual(d["blind"], '10801')
	
	def testHDUsField(self):
		d = self._getParse("""<fitsProdGrammar hdusField="__HDUS"/>""")
		self.assertEqual(d["__HDUS"][0].data[0][0], 7896.0)


class ReGrammarTest(testhelpers.VerboseTest):
	def testBadInputRejection(self):
		grammar = base.parseFromString(regrammar.REGrammar,
			"""<reGrammar names="a,b"/>""")
		self.assertRaisesWithMsg(base.SourceParseError,
			"At line 1: 1 fields found, expected 2",
			lambda: list(grammar.parse(StringIO("1 2\n3"))),
			())

	def testComment(self):
		grammar = base.parseFromString(regrammar.REGrammar,
			"""<reGrammar names="a,b" commentPat="(?m)^#.*$"/>""")
		self.assertEqual(
			getCleaned(grammar.parse(
				StringIO("1 2\n# more data\n3 2\n#end of file.\n"))),
			[{'a': '1', 'b': '2'}, {'a': '3', 'b': '2'}])

	def testNoComment(self):
		grammar = base.parseFromString(regrammar.REGrammar,
			"""<reGrammar names="a,b"/>""")
		self.assertEqual(
			getCleaned(grammar.parse(
				StringIO("1 2\n#more data\n3 2\n#endof file.\n"))), [
				{'a': '1', 'b': '2'},
				{'a': '#more', 'b': 'data'},
				{'a': '3', 'b': '2'},
				{'a': '#endof', 'b': 'file.'}])

	def testIgnoredEnd(self):
		grammar = base.parseFromString(regrammar.REGrammar,
			r"""<reGrammar names="a,b" recordSep="\\\\" commentPat="(?m)^\\.*$"/>""")
		self.assertEqual(
			getCleaned(grammar.parse(
				StringIO("1\n2\\\\\n3 4\\\\\n\\ignore all this\n\n\\and this.\n"))), [
				{'a': '1', 'b': '2'},
				{'a': '3', 'b': '4'}])

	def testLineCount(self):
		grammar = base.parseFromString(regrammar.REGrammar,
			r"""<reGrammar names="a,b" recordSep="//" fieldSep=","/>""")
		self.assertRaisesWithMsg(base.SourceParseError,
			"At line 2: 1 fields found, expected 2",
			list,
			(grammar.parse(StringIO("a,b//c,d//e\n,f//g,h//j//\n1,d//\n")),))


class FilteredInputTest(testhelpers.VerboseTest):
	def testSimple(self):
		with testtricks.testFile("filterInput", "ab\ncd\nef\n") as srcName:
			f = common.FilteredInputFile("tac", open(srcName))
			self.assertEqual(f.read(), "ef\ncd\nab\n")
			f.close()

	def testLargeOutput(self):
		data = "                    \n"*200000
		with testtricks.testFile(
				"filterInput", data, writeGz=True) as srcName:
			f = common.FilteredInputFile("zcat", open(srcName))
			result = f.read()
			self.assertEqual(result, data)
			f.close()

	def testLargeInput(self):
		inF = StringIO("                    \n"*200000)
		f = common.FilteredInputFile("gzip", inF)
		result = f.read()
		self.assertEqual(len(result), 10216)
		f.close()

	def testFailedCommand(self):
		f = common.FilteredInputFile("verpotshket", StringIO("abc"),
			silent=True)
		self.assertRaisesWithMsg(IOError,
			"Child exited with return code 127",
			f.read,
			())

	def testReadWithSizeAndClose(self):
		f = common.FilteredInputFile("yes", StringIO("abc"), silent=True)
		self.assertEqual("y\n"*10, f.read(20))
		f.close()
		self.assertEqual(f.process.returncode, -15)

	def testReadline(self):
		f = common.FilteredInputFile("zcat", StringIO(
			"H4sIAFcmV1AAA0vkSgQCMDHcABcXAN3p7JLdAAAA".decode("base64")))
		self.assertEqual(f.readline(), "a\n")
		self.assertEqual(f.readline(), "aaaa\n")
		self.assertEqual(f.readline(), "a"*212+"\n")
		self.assertEqual(f.readline(), "\n")
		self.assertEqual(f.readline(), "")

	def testReadlineNoLF(self):
		f = common.FilteredInputFile("cat", StringIO(
			"AAAA\nBBBB"))
		self.assertEqual(f.readline(), "AAAA\n")
		self.assertEqual(f.readline(), "BBBB")


class DirectGrammarTest(testhelpers.VerboseTest):
# this is for direct grammars that can't be automatically made:
# Just make sure they're producing something resembling C source.
	rd = testhelpers.getTestRD("dgs")

	def _assertCommonItems(self, src):
		self.failUnless(src.startswith("#include"))
		self.failUnless("fi_i,            /* I, integer */" in src)
		self.failUnless("writeHeader(destination);" in src)

	def testColGrammar(self):
		src = directgrammar.getSource("data/dgs#col")
		self._assertCommonItems(src)
		self.failUnless("parseFloat(inputLine, F(fi_f), start, len);" in src)

	def testSplitGrammar(self):
		src = directgrammar.getSource("data/dgs#split")
		self._assertCommonItems(src)
		self.failUnless('char *curCont;' in src)
		self.failUnless('curCont = strtok(inputLine, "|");' in src)
		self.failUnless('curCont = strtok(NULL, "|");' in src)

	def testBinGrammar(self):
		src = directgrammar.getSource("data/dgs#bin")
		self._assertCommonItems(src)
		self.failUnless('#define FIXED_RECORD_SIZE 50' in src)
		self.failUnless('MAKE_INT(fi_i, *(int32_t*)(inputLine+));' in src)
		self.failUnless('bytesRead = fread(inputLine, 1, FIXED_RECORD_SIZE, inF);' 
			in src)

	def testSourcePlausible(self):
		src = directgrammar.getSource("data/dgs#fits")
		self._assertCommonItems(src)
		self.failUnless("if (COL_DESCS[i].fitsType==TSTRING) {" in src)
		self.failUnless("MAKE_BIGINT(fi_b, ((long long*)(data[1]))[rowIndex]);" 
			in src)

	def testFITSSecondExtension(self):
		src = directgrammar.getSource("data/dgs#fits2nd")
		self.failUnless("fits_movabs_hdu(fitsInput, 2+1," in src)
		self.failUnless("FITSColDesc COL_DESCS[1] = {\n"
			"{.cSize = sizeof(long long), .fitsType = TLONGLONG, .index=1}\n};"
			in src)

	def testFITSWithAdditionalCols(self):
		src = directgrammar.getSource("data/dgs#fitsplus")
		self._assertCommonItems(src)
		self.failUnless("FITSColDesc COL_DESCS[5] = {" in src)
		self.failUnless("#define QUERY_N_PARS 6")
		self.failUnless("MAKE_NULL(fi_artificial);"
			" /* MAKE_TEXT(fi_artificial, FILL IN VALUE); */" in src)

	# XXX TODO: tests for column reordering, skipping unused columns in FITS

directgrammar.CBooster.silence_for_test = True

class _FITSBoosterImportedTable(testhelpers.TestResource):
	resources = [("conn", tresc.dbConnection)]

	def make(self, deps):
		conn = deps["conn"]
		dd = base.caches.getRD("data/dgs").getById("impfits")
		self.srcName = dd.grammar.cBooster
		with open(self.srcName, "w") as f:
			f.write(directgrammar.getSource("data/dgs#fits"))

		data = rsc.makeData(dd, connection=conn)
		table = data.getPrimaryTable()
		rows = list(table.iterQuery(table.tableDef))
		return rows, data.getPrimaryTable()

	def clean(self, res):
		os.unlink(self.srcName)
		res[1].drop()


class FITSDirectGrammarTest(testhelpers.VerboseTest):
	
	resources = [("imped", _FITSBoosterImportedTable())]

	def testInteger(self):
		self.assertEqual(self.imped[0][0]["i"], 450000)

	def testBigint(self):
		self.assertEqual(self.imped[0][0]["b"], 4009249430L)
	
	def testFloat(self):
		self.assertEqual(self.imped[0][0]["f"], 3.2)
	
	def testDouble(self):
		self.assertEqual(self.imped[0][0]["d"], 5e120)

	def testTextAndMap(self):
		self.assertEqual(self.imped[0][0]["t"], "foobar")

	def testUnknownNULL(self):
		self.assertEqual(self.imped[0][0]["artificial"], None)


class PDSGrammarTest(testhelpers.VerboseTest):
	def testLabelTypes(self):
		grammar = base.parseFromString(pdsgrammar.PDSGrammar, "<pdsGrammar/>")
		try:
			recs = list(grammar.parse(StringIO(
				'PDS_VERSION_ID = PDS3\r\nLABEL_REVISION_NOTE = '
				'"SE-MTC,09/07/2010"\r\n\r\n /* File format and length */'
				'\r\nPRODUCT_ID = "S1_00237390711"\r\nORIGINAL_PRODUCT_ID ='
				' "PSA7AD50"\r\nEND\r\n')))
		except base.ReportableError:
			# PyPDS probably missing, skip this test
			return

		self.assertEqual(len(recs), 1)
		self.assertEqual(recs[0]["PRODUCT_ID"], '"S1_00237390711"')


if __name__=="__main__":
	testhelpers.main(FITSDirectGrammarTest)
