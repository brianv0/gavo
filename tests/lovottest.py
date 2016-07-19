"""
Tests for our low-level VOTable interface.
"""

#c Copyright 2008-2016, the GAVO project
#c
#c This program is free software, covered by the GNU GPL.  See the
#c COPYING file in the source distribution.


import datetime
import re
import struct
from cStringIO import StringIO

from numpy import rec

from gavo.helpers import testhelpers

from gavo import base
from gavo import votable
from gavo.utils import pgsphere
from gavo.votable import common
from gavo.votable import V
from gavo.utils.plainxml import iterparse


class NullFlagsSerTest(testhelpers.VerboseTest):
	__metaclass__ = testhelpers.SamplesBasedAutoTest

	def _runTest(self, sample):
		nFields, nullMap, expected = sample
		self.assertEqual(common.NULLFlags(nFields).serialize(nullMap), expected)
	
	samples = [
		(1, [True], "\x80"),
		(1, [False], "\x00"),
		(8, [True, False, True, False, False, False, False, False], "\xa0"),
		(9, [True, False, True, False, False, False, False, False, False], 
			"\xa0\x00"),
		(12, [False]*4+[True]*2+[False]*5+[True], "\x0c\x10"),
		(16, [False]*15+[True], "\x00\x01"),
		(65, [False]*64+[True], "\x00\x00\x00\x00\x00\x00\x00\x00\x80"),
	]


class NullFlagsDeserTest(testhelpers.VerboseTest):
	__metaclass__ = testhelpers.SamplesBasedAutoTest

	def _runTest(self, sample):
		nFields, expected, input = sample
		self.assertEqual(common.NULLFlags(nFields).deserialize(input), 
			expected)
	
	samples = NullFlagsSerTest.samples


class IterParseTest(testhelpers.VerboseTest):
	"""tests for our custom iterparser.
	"""
	__metaclass__ = testhelpers.SamplesBasedAutoTest

	def _runTest(self, sample):
		xml, parsed = sample
		self.assertEqual(list(iterparse(StringIO(xml))), parsed)
	
	samples = [
		("<doc/>", [("start", "doc", {}), ("end", "doc", None)]),
		('<doc href="x"/>', 
			[("start", "doc", {"href": "x"}), ("end", "doc", None)]),
		('<doc>fl\xc3\xb6ge</doc>', [
			("start", "doc", {}), 
			("data", None, u"fl\xf6ge"), 
			("end", "doc", None)]),
		('<doc obj="fl\xc3\xb6ge"/>', 
			[("start", "doc", {"obj": u"fl\xf6ge"}), ("end", "doc", None)]),
		('<doc><abc>'+"unu"*10000+'</abc>\n<bcd>klutz</bcd></doc>', [
			("start", "doc", {}), 
			("start", "abc", {}),
			("data", None, "unu"*10000),
			("end", "abc", None),
			("data", None, "\n"),
			("start", "bcd", {}),
			("data", None, "klutz"),
			("end", "bcd", None),
			("end", "doc", None)]),
		('<doc xmlns="http://insane"/>', [
			("start", "doc", {u'xmlns': u'http://insane'}), ("end", "doc", None),])
	]


class TrivialParseTest(testhelpers.VerboseTest):
	"""tests operating on an empty VOTable.
	"""
	def testTrivialParse(self):
		self.assertEqual(list(votable.parseString("<VOTABLE/>")), [])

	def testTrivialWatchlist(self):
		res = list(votable.parseString("<VOTABLE/>",
			watchset=[V.VOTABLE]))
		self.assertEqual(len(res), 1)
		self.failUnless(isinstance(res[0], V.VOTABLE))
	
	def testTrivialWithNamespace(self):
		res = list(votable.parseString(
			'<VOTABLE xmlns="http://www.ivoa.net/xml/VOTable/v1.2"/>',
			watchset=[V.VOTABLE]))
		self.failUnless(isinstance(res[0], V.VOTABLE))

	def testTrivialOldNamespace(self):
		res = list(votable.parseString(
			'<VOTABLE xmlns="http://www.ivoa.net/xml/VOTable/v1.1"/>',
			watchset=[V.VOTABLE]))
		self.failUnless(isinstance(res[0], V.VOTABLE))


class TrivialWriteTest(testhelpers.VerboseTest):
	def testEmpty(self):
		res = votable.asString(V.VOTABLE(), xmlDecl=True)
		self.failUnless("<?xml version='1.0' encoding='utf-8'?>" in res)
		self.failUnless("<VOTABLE version=" in res)
		self.failUnless("/>" in res)


class ErrorParseTest(testhelpers.VerboseTest):
	"""tests for more-or-less benign behaviour on input errors.
	"""
	def testExpatReporting(self):
		try:
			list(votable.parseString("<VOTABLE>"))
		except Exception, ex:
			pass
		self.assertEqual(ex.__class__.__name__, "VOTableParseError")
		self.assertEqual(str(ex), "no element found: line 1, column 9")

	def testInternalReporting(self):
		table = votable.parseString("<VOTABLE><RESOURCE><TABLE>\n"
			'<FIELD name="x" datatype="boolean"/>\n'
			'<DATA><TABLEDATA>\n'
			'<TR><TDA>True</TDA></TR>\n'
			'</TABLEDATA></DATA>\n'
			"</TABLE></RESOURCE></VOTABLE>\n").next()
		try:
			list(table)
		except Exception, ex:
			pass
		self.assertEqual(ex.__class__.__name__, "VOTableParseError")
		self.assertEqual(str(ex), "At [<VOTABLE><RESOURCE><TABLE>\\...], (4, 4):"
			" Unexpected element TDA")


class TextParseTest(testhelpers.VerboseTest):
	"""tests for parsing elements with text content.
	"""
	def _getInfoItem(self, infoLiteral):
		return list(votable.parseString(
			'<VOTABLE>%s</VOTABLE>'%infoLiteral,
			watchset=[V.INFO]))[0]

	def testEmptyInfo(self):
		res = self._getInfoItem('<INFO name="t" value="0"/>')
		self.assertEqual(res.value, "0")
		self.assertEqual(res.name, "t")
	
	def testFullInfo(self):
		res = self._getInfoItem('<INFO name="t" value="0">abc</INFO>')
		self.assertEqual(res.text_, "abc")

	def testUnicode(self):
		# xml defaults to utf-8
		res = self._getInfoItem('<INFO name="t" value="0">\xc3\xa4rn</INFO>')
		self.assertEqual(res.text_, u"\xe4rn")


class IdTest(testhelpers.VerboseTest):
	"""tests for the management of id attributes.
	"""
	def testSimpleId(self):
		els = list(votable.parseString(
			'<VOTABLE><INFO ID="xy">abc</INFO></VOTABLE>',
			watchset=[V.INFO, V.VOTABLE]))
		self.failUnless(els[0].idmap is els[1].idmap)
		self.failUnless(els[0].idmap["xy"] is els[0])
	
	def testForwardReference(self):
		iter = votable.parseString(
			'<VOTABLE><INFO ID="xy" ref="z">abc</INFO>'
			'<INFO ID="z" ref="xy">zz</INFO></VOTABLE>',
			watchset=[V.INFO])
		info0 = iter.next()
		self.assertRaises(KeyError, lambda: info0.idmap[info0.ref])
		info1 = iter.next()
		self.failUnless(info0.idmap[info0.ref] is info1)
		self.failUnless(info1.idmap[info1.ref] is info0)
		self.assertRaises(StopIteration, iter.next)


class TabledataReadTest(testhelpers.VerboseTest):
	"""tests for deserialization of TABLEDATA encoded values.
	"""
	__metaclass__ = testhelpers.SamplesBasedAutoTest

	def _runTest(self, sample):
		fielddefs, literals, expected = sample
		table = votable.parseString((
			'<VOTABLE><RESOURCE><TABLE>'+
			fielddefs+
			'<DATA><TABLEDATA>'+
			'\n'.join('<TR>%s</TR>'%''.join('<TD>%s</TD>'%l
				for l in row) for row in literals)+
			'</TABLEDATA></DATA>'
			'</TABLE></RESOURCE></VOTABLE>').encode("utf-8")).next()
		self.assertEqual(list(table), expected)
	
	samples = [(
			'<FIELD name="x" datatype="boolean"/>',
			[['TRue'], ['T'],  ['False'], ['?']],
			[[True],   [True], [False],   [None]]
		), (
			'<FIELD name="x" datatype="unsignedByte"/>'
			'<FIELD name="y" datatype="unsignedByte"><VALUES null="16"/></FIELD>',
			[['',   ''],   ['0x10', '0x10'], ['10', '16'], ['', '']],
			[[None, None], [16,     16],     [10,    None], [None, None]]
		), (
			'<FIELD name="x" datatype="char"/>',
			[[''],   ['a'], ['&apos;'], [u'\xe4'], ['&#xe4;'], ['']],
			[[None], ['a'], ["'"],      ['\xe4'], ['\xe4'], [None]],
		), (
			'<FIELD name="x" datatype="short"><VALUES null="0"/></FIELD>'
			'<FIELD name="y" datatype="int"/>'
			'<FIELD name="z" datatype="long"><VALUES null="222399322"/></FIELD>',
			[['0', '0', '0'], ['-3', '-300', '222399322'], ['0xff', '0xcafebabe', '0xcafebabedeadbeef'], ['', '', '']],
			[[None, 0,  0],   [-3,    -300,  None],        [255,    -889275714,   -3819410105021120785L], [None, None, None]]
		), (
			'<FIELD name="x" datatype="float"><VALUES null="-999."/></FIELD>'
			'<FIELD name="y" datatype="float"/>',
			[['1', '0.5e10'], ['-999.', '']],
			[[1.0, 5e09],     [None, None]]
		), ( # 05
			'<FIELD name="x" datatype="floatComplex"><VALUES null="-999. 0"/></FIELD>'
			'<FIELD name="y" datatype="floatComplex"/>',
			[['1 1', '0.5e10 -2e5'], ['-999. 0', '20']],
			[[(1+1j), 5e09-2e5j],    [None, 20+0j]]
		), (
			'<FIELD name="x" datatype="boolean" arraysize="*"/>',
			[['true false ? T'],        [' T'], ['']],
			[[(True, False, None, True)], [(True,)], [None]]
		), (
			'<FIELD name="y" datatype="unsignedByte" arraysize="*">'
			' <VALUES null="16"/></FIELD>',
			[['10 0x10\t 16 \n 0x16'], ['']],
			[[(10, 16, None, 22)], [None]]
		), (
			'<FIELD name="x" datatype="char" arraysize="4"/>',
			[[''], ['auto'], ['&apos;xx&quot;'], [u'\xe4'], ['&#xe4;'], ['']],
			[[None], ['auto'], ["'xx\""], ['\xe4'], ['\xe4'], [None]],
		), (
			'<FIELD name="x" datatype="short" arraysize="*"><VALUES null="0"/></FIELD>',
			[['1 2 3 0 1'], [""]], 
			[[(1,2,3,None,1)], [None]]
		), (
			'<FIELD name="y" datatype="floatComplex" arraysize="*"/>',
			[['1 1 0.5e10 -2e5'], [""]],
			[[((1+1j), 5e09-2e5j)], [None]]
		), (
			'<FIELD datatype="short" arraysize="2x3"/>',
			[['0 1 2 3 4 5']],
			[[(0,1,2,3,4,5)]],
		), (
			'<FIELD name="x" datatype="float"/>',
			[['NaN'], ['']],
			[[None],  [None]]
		), (
			'<FIELD datatype="unicodeChar" arraysize="*"/>',
			[[u'\xe4'], [""]],
			[[u'\xe4'], [None]]
		),
	]


class FloatTDEncodingTest(testhelpers.VerboseTest):
	"""tests for proper handling of special float values.
	"""
	def _decode(self, fielddefs, literals):
		table = votable.parseString((
			'<VOTABLE><RESOURCE><TABLE>'+
			fielddefs+
			'<DATA><TABLEDATA>'+
			'\n'.join('<TR>%s</TR>'%''.join('<TD>%s</TD>'%l
				for l in row) for row in literals)+
			'</TABLEDATA></DATA>'
			'</TABLE></RESOURCE></VOTABLE>').encode("utf-8")).next()
		return list(table)

	def testNAN(self):
		vals = self._decode(
			'<FIELD name="y" datatype="float"/>',
			[['NaN']])[0]
		self.failUnless(vals[0] is None)
	
	def testInfinities(self):
		vals = self._decode(
			'<FIELD name="y" datatype="float"/>',
			[['+Inf'], ['-Inf']])
		self.failUnless(vals[0][0]==2*vals[0][0])
		self.failUnless(vals[1][0]==2*vals[1][0])

	def testWeirdArray(self):
		vals = self._decode(
			'<FIELD name="y" datatype="float" arraysize="3"/>',
			[['NaN +Inf -Inf']])[0]
		self.assertEqual(repr(vals), '[(None, inf, -inf)]')


class TabledataWriteTest(testhelpers.VerboseTest):
	"""tests for serializing TABLEDATA VOTables.
	"""
	__metaclass__ = testhelpers.SamplesBasedAutoTest

	def _runTest(self, sample):
		fielddefs, input, expected = sample
		vot = V.VOTABLE[V.RESOURCE[votable.DelayedTable(
			V.TABLE[fielddefs], input, V.TABLEDATA)]]
		res = votable.asString(vot)
		mat = re.search("<TABLEDATA>(.*)</TABLEDATA>", res)
		content = mat and mat.group(1)
		self.assertEqual(content, expected)

	samples = [(
			[V.FIELD(datatype="float")],
			[[1],[None],[float("NaN")], [3L]],
			"<TR><TD>1.0</TD></TR><TR><TD>NaN</TD></TR><TR><TD>NaN</TD></TR><TR><TD>3.0</TD></TR>"
		), (
			[V.FIELD(datatype="double")],
			[[1.52587890625e-05], [float("+Inf")]],
			'<TR><TD>1.52587890625e-05</TD></TR><TR><TD>inf</TD></TR>'
		), (
			[V.FIELD(datatype="boolean")],
			[[True], [False], [None]],
			'<TR><TD>1</TD></TR><TR><TD>0</TD></TR><TR><TD>?</TD></TR>'
		), ([
				V.FIELD(datatype="bit"),
				V.FIELD(datatype="unsignedByte"),
				V.FIELD(datatype="short"),
				V.FIELD(datatype="int"),
				V.FIELD(datatype="long")],
			[[0,1,2,3,4]],
			'<TR><TD>0</TD><TD>1</TD><TD>2</TD><TD>3</TD><TD>4</TD></TR>'
		), (
			[V.FIELD(datatype="unicodeChar")],
			[u'\xe4'],
			'<TR><TD>\xc3\xa4</TD></TR>'
		), (  # 5
			[V.FIELD(datatype="char")],
			[u'\xe4'],
			'<TR><TD>?</TD></TR>'
		), (
			[V.FIELD(datatype="floatComplex")],
			[[0.5+0.25j]],
			'<TR><TD>0.5 0.25</TD></TR>'
		), ([
				V.FIELD(datatype="unsignedByte")[V.VALUES(null="23")],
				V.FIELD(datatype="unicodeChar")[V.VALUES(null="\x00")],
				V.FIELD(datatype="float")[V.VALUES(null="-9999")]],
			[[1, "a", 1.5], [None, None, None]],
			'<TR><TD>1</TD><TD>a</TD><TD>1.5</TD></TR>'
			'<TR><TD>23</TD><TD>&x00;</TD><TD>NaN</TD></TR>'
		), (
			[V.FIELD(datatype="unsignedByte", arraysize="2")[V.VALUES(null="0xff")]],
			[[[]], [[2]], [None], [[2, 3, 4]]],
		'<TR><TD>0xff 0xff</TD></TR><TR><TD>2 0xff</TD></TR>'
		'<TR><TD></TD></TR><TR><TD>2 3</TD></TR>'
		), (
			[V.FIELD(datatype="bit", arraysize="*")],
			[[430049293488]],
			'<TR><TD>110010000100000111011110111010010110000</TD></TR>'
		), (  # 10
			[V.FIELD(datatype="doubleComplex", arraysize="2")[V.VALUES(null="0 0")]],
			[[[2+2j, None, 4+4j]]],
			'<TR><TD>2.0 2.0 NaN NaN</TD></TR>'
		), (
			[V.FIELD(datatype="double", arraysize="*")[V.VALUES(null="23")]],
			[[None], [[None]]],
			"<TR><TD></TD></TR><TR><TD>NaN</TD></TR>"
		)
	]


class BinaryWriteTest(testhelpers.VerboseTest):
	"""tests for serializing BINARY VOTables.
	"""
	__metaclass__ = testhelpers.SamplesBasedAutoTest

	def _runTest(self, sample):
		fielddefs, input, expected = sample
		vot = V.VOTABLE[V.RESOURCE[votable.DelayedTable(
			V.TABLE[fielddefs], input, V.BINARY)]]
		mat = re.search('(?s)<STREAM encoding="base64">(.*)</STREAM>', 
			votable.asString(vot))
		content = mat and mat.group(1)
		self.assertEqual(content.decode("base64"), expected)

	samples = [(
			[V.FIELD(datatype="float")],
			[[1],[None],[common.NaN]],
			struct.pack("!fff", 1, common.NaN, common.NaN)
		), (
			[V.FIELD(datatype="double")],
			[[1],[None],[common.NaN]],
			struct.pack("!ddd", 1, common.NaN, common.NaN)
		), (
			[V.FIELD(datatype="boolean")],
			[[True],[False],[None]],
			"10?"
		), (
			[V.FIELD(datatype="bit")],
			[[1],[0]],
			"\x01\x00"
		), (
			[V.FIELD(datatype="unsignedByte")],
			[[20]],
			"\x14"
		), (  # 5
			[V.FIELD(datatype="unsignedByte")[V.VALUES(null="23")]],
			[[20], [None]],
			"\x14\x17"
		), (
			[V.FIELD(datatype="short")],
			[[20]],
			"\x00\x14"
		), (
			[V.FIELD(datatype="int")],
			[[-20]],
			"\xff\xff\xff\xec"
		), (
			[V.FIELD(datatype="long")],
			[[-20]],
			"\xff\xff\xff\xff\xff\xff\xff\xec"
		), (
			[V.FIELD(datatype="char")[V.VALUES(null="x")]],
			[['a'], [None]],
			"ax"
		), (  # 10
			[V.FIELD(datatype="unicodeChar")[V.VALUES(null=u"\udead")]],
			[['a'], ['\xe4'.decode("iso-8859-1")], [None]],
			"\x00a\x00\xe4\xde\xad"
		), (
			[V.FIELD(datatype="floatComplex")],
			[[6+7j], [None]],
			struct.pack("!ff", 6, 7)+struct.pack("!ff", common.NaN, common.NaN)
		), (
			[V.FIELD(datatype="bit", arraysize="17")],
			[[1],[2**25-1]],
			"\x00\x00\x01\xff\xff\xff"
		), (
			[V.FIELD(datatype="bit", arraysize="*")],
			[[1],[2**25-1]],
			"\x00\x00\x00\x08\x01"
			"\x00\x00\x00\x20\x01\xff\xff\xff"
		), (
			[V.FIELD(datatype="unsignedByte", arraysize="*")],
			[[[]], [[1]], [[0, 1, 2]]],
			"\x00\x00\x00\x00"
			"\x00\x00\x00\x01\x01"
			"\x00\x00\x00\x03\x00\x01\x02"
		), ( # 15
			[V.FIELD(datatype="unsignedByte", arraysize="2")[V.VALUES(null="255")]],
			[[[]], [[1]], [[0, 1, 2]]],
			"\xff\xff"
			"\x01\xff"
			"\x00\x01"
		), (
			[V.FIELD(datatype="short", arraysize="2*")],
			[[[]], [[1]], [[0, 1, 2]]],
			"\x00\x00\x00\x00"
			"\x00\x00\x00\x01\x00\x01"
			"\x00\x00\x00\x03\x00\x00\x00\x01\x00\x02"
		), (
			[V.FIELD(datatype="char", arraysize="2")],
			[["abc"], ["a"]],
			"aba "
		), (
			[V.FIELD(datatype="char", arraysize="*")],
			[["abc"], ["a"]],
			"\0\0\0\x03abc\0\0\0\x01a"
		), (
			[V.FIELD(datatype="unicodeChar", arraysize="2")],
			[[u"\u00e4bc"], [u"\u00e4"]],
			'\x00\xe4\x00b\x00\xe4\x00 '
		), ( #20
			[V.FIELD(datatype="short", arraysize="3x2")],
			[[[1,2,3,4,5,6]]],
			'\x00\x01\x00\x02\x00\x03\x00\x04\x00\x05\x00\x06'
		),
	]


class BinaryReadTest(testhelpers.VerboseTest):
	"""tests for deserializing BINARY VOTables.
	"""
	__metaclass__ = testhelpers.SamplesBasedAutoTest

	def _runTest(self, sample):
		fielddefs, stuff, expected = sample
		table = votable.parseString((
			'<VOTABLE><RESOURCE><TABLE>'+
			fielddefs+
			'<DATA><BINARY><STREAM encoding="base64">'+
			stuff.encode("base64")+
			'</STREAM></BINARY></DATA>'
			'</TABLE></RESOURCE></VOTABLE>').encode("utf-8")).next()
		self.assertEqual(list(table), expected)

	samples = [(
			'<FIELD datatype="boolean"/>',
			"10?",
			[[True],[False],[None]],
		), (
			'<FIELD datatype="bit"/>',
			"\x01\x00\xff",
			[[1],[0],[1]],
		), (
			'<FIELD datatype="bit" arraysize="9"/>',
			"\x01\x00\xff\xff",
			[[256],[511]],
		), (
			'<FIELD datatype="bit" arraysize="*"/>',
			"\x00\x00\x00\x03\xff\x00\x00\x00\x45"
				"\xff\x00\x00\x00\x00\x00\x00\x00\x01",
			[[7],[0x1f0000000000000001]],
		), (
			'<FIELD datatype="char"><VALUES null="a"/></FIELD>',
			"x\x00a",
			[['x'],['\x00'], [None]],
		), (
			'<FIELD datatype="unicodeChar"><VALUES null="&#xbabe;"/></FIELD>',
			"\x00a\x23\x42\xba\xbe",
			[['a'],[u'\u2342'], [None]],
		), (
			'<FIELD datatype="unsignedByte"><VALUES null="12"/></FIELD>'
				'<FIELD datatype="short"><VALUES null="12"/></FIELD>'
				'<FIELD datatype="int"><VALUES null="12"/></FIELD>'
				'<FIELD datatype="long"><VALUES null="12"/></FIELD>',
			"\x0c\x00\x0c\x00\x00\x00\x0c\x00\x00\x00\x00\x00\x00\x00\x0c"
			"\x0d\x0d\x0d\x00\x0d\x0d\x0c\x00\xdd\x00\x00\x00\x00\x00\x0c", [
				[None, None, None, None],
				[13, 3341, 855308, 62205969853054988L]]
		), (
			'<FIELD datatype="float"/>',
			"\x7f\xc0\x00\x00:\x80\x00\x00",
			[[None], [0.0009765625]]
		), (
			'<FIELD datatype="double"/>',
			"\x7f\xf8\x00\x00\x00\x00\x00\x00?P\x00\x01\x00\x00\x00\x00",
			[[None], [0.00097656343132257462]]
		), (
			'<FIELD datatype="doubleComplex"/>',
			"\x7f\xf8\x00\x00\x00\x00\x00\x00?P\x00\x01\x00\x00\x00\x00"
			'@\x04\x00\x00\x00\x00\x00\x00?\xe0\x00\x00\x00\x00\x00\x00',
			[[None], [2.5+0.5j]]
		), (
			'<FIELD datatype="char" arraysize="4"><VALUES null="0000"/></FIELD>',
			"abcd0000",
			[["abcd"], [None]]
		), (
			'<FIELD datatype="char" arraysize="*"/>',
			"\x00\x00\x00\x00\x00\x00\x00\x03abc",
			[[""], ["abc"]]
		), (
			'<FIELD datatype="unicodeChar" arraysize="*"/>',
			"\x00\x00\x00\x03\x00a\x23\x42bc",
			[[u"a\u2342\u6263"]]
		), (
			'<FIELD datatype="unicodeChar" arraysize="2"/>',
			"\x00a\x23\x42",
			[[u"a\u2342"]]
		), (
			'<FIELD datatype="unsignedByte" arraysize="2"/>',
			'\x00\x01',
			[[(0, 1)]],
		), (  # 15
			'<FIELD datatype="short" arraysize="*"><VALUES null="16"/></FIELD>',
			'\x00\x00\x00\x03\x00\x01\x00\x10\x00\x02',
			[[(1, None, 2)]],
		), (
			'<FIELD datatype="int" arraysize="2"/>',
			'\x00\x00\x00\x03\x00\x01\x00\x10',
			[[(3, 0x10010)]],
		), (
			'<FIELD datatype="float" arraysize="2"/>',
			'\x7f\xc0\x00\x00:\x80\x00\x00',
			[[(None, 0.0009765625)]],
		), (
			'<FIELD datatype="double" arraysize="*"/>',
			'\x00\x00\x00\x02\x7f\xf8\x00\x00\x00\x00\x00\x00'
				'?P\x00\x01\x00\x00\x00\x00',
			[[(None, 0.00097656343132257462)]]
		), (
			'<FIELD datatype="float" arraysize="2"><VALUES null="2"/></FIELD>',
			'\x7f\xc0\x00\x00:\x80\x00\x00',
			[[(None, 0.0009765625)]],
		), (
			'<FIELD datatype="floatComplex" arraysize="2"/>',
			'\x7f\xc0\x00\x00:\x80\x00\x00'
				'A\x80\x00\x00A\x0c\x00\x00',
			[[(None, 16+8.75j)]],
		), (
			'<FIELD datatype="short" arraysize="2x3"/>',
			'\x00\x00\x00\x01\x00\x02\x00\x03\x00\x04\x00\x05',
			[[(0,1,2,3,4,5)]],
		)]


class Binary2WriteTest(testhelpers.VerboseTest):
	"""tests for serializing BINARY2 VOTables.
	"""
	__metaclass__ = testhelpers.SamplesBasedAutoTest

	def _runTest(self, sample):
		fielddefs, input, expected = sample
		vot = V.VOTABLE[V.RESOURCE[votable.DelayedTable(
			V.TABLE[fielddefs], input, V.BINARY2)]]
		mat = re.search('(?s)<STREAM encoding="base64">(.*)</STREAM>', 
			votable.asString(vot))
		content = mat and mat.group(1)
		self.assertEqual(content.decode("base64"), expected)

	samples = [(
			[V.FIELD(datatype="float")],
			[[1.],[None],[common.NaN]],
			struct.pack("!BfBfBf", 0, 1., 0x80, common.NaN, 0, common.NaN)
		), (
			[V.FIELD(datatype="double")],
			[[1.],[None],[common.NaN]],
			struct.pack("!BdBdBd", 0, 1., 0x80, common.NaN, 0, common.NaN)
		), (
			[V.FIELD(datatype="boolean")],
			[[True],[False],[None]],
			"\x001\x000\x80?"
		), (
			[V.FIELD(datatype="bit")],
			[[1],[0]],
			"\x00\x01\x00\x00"
		), (
			[V.FIELD(datatype="unsignedByte")],
			[[20], [None]],
			"\x00\x14\x80\xff"
		), (  # 5
			[V.FIELD(datatype="unsignedByte")[V.VALUES(null="23")]],
			[[20], [None]],
			"\x00\x14\x80\xff"
		), (
			[V.FIELD(datatype="short")],
			[[20],[None]],
			"\x00\x00\x14\x80\x00\x00"
		), (
			[V.FIELD(datatype="int")],
			[[-20], [None]],
			"\x00\xff\xff\xff\xec\x80\x00\x00\x00\x00"
		), (
			[V.FIELD(datatype="long")],
			[[-20], [None]],
			"\x00\xff\xff\xff\xff\xff\xff\xff\xec\x80\x00\x00\x00\x00\x00\x00\x00\x00"
		), (
			[V.FIELD(datatype="char")[V.VALUES(null="x")]],
			[['a'], [None]],
			"\x00a\x80\x00"
		), (  # 10
			[V.FIELD(datatype="unicodeChar")[V.VALUES(null=u"\udead")]],
			[['a'], ['\xe4'.decode("iso-8859-1")], [None]],
			"\x00\x00a\x00\x00\xe4\x80\x00\x00"
		), (
			[V.FIELD(datatype="floatComplex")],
			[[6+7j], [None]],
			struct.pack("!Bff", 0,  6, 7)+struct.pack(
				"!Bff", 0x80, common.NaN, common.NaN)
		), (
			[V.FIELD(datatype="bit", arraysize="17")],
			[[1], [2**25-1], [None]],
			"\x00\x00\x00\x01\x00\xff\xff\xff\x80\x00\x00\x00\x00"
		), (
			[V.FIELD(datatype="bit", arraysize="*")],
			[[1],[2**25-1], [None]],
			"\x00\x00\x00\x00\x08\x01"
			"\x00\x00\x00\x00\x20\x01\xff\xff\xff"
			"\x80\x00\x00\x00\x00"
		), (
			[V.FIELD(datatype="unsignedByte", arraysize="*")],
			[[[]], [[1]], [[0, 1, 2]], [None]],
			"\x00\x00\x00\x00\x00"
			"\x00\x00\x00\x00\x01\x01"
			"\x00\x00\x00\x00\x03\x00\x01\x02"
			"\x80\x00\x00\x00\x00"
		), ( # 15
			[V.FIELD(datatype="unsignedByte", arraysize="2")[V.VALUES(null="255")]],
			[[[]], [[1]], [[0, 1, 2]], [None]],
			"\x00\xff\xff"
			"\x00\x01\xff"
			"\x00\x00\x01"
			"\x80\xff\xff"
		), (
			[V.FIELD(datatype="short", arraysize="2*")],
			[[[]], [[1]], [[0, 1, 2]], [None]],
			"\x00\x00\x00\x00\x00"
			"\x00\x00\x00\x00\x01\x00\x01"
			"\x00\x00\x00\x00\x03\x00\x00\x00\x01\x00\x02"
			"\x80\x00\x00\x00\x00"
		), (
			[V.FIELD(datatype="char", arraysize="2")],
			[["abc"], ["a"], [None]],
			"\x00ab\x00a\x00\x80\x00\x00"
		), (
			[V.FIELD(datatype="char", arraysize="*")],
			[["abc"], ["a"], [None]],
			"\x00\0\0\0\x03abc\x00\0\0\0\x01a\x80\0\0\0\0"
		), (
			[V.FIELD(datatype="unicodeChar", arraysize="2")],
			[[u"\u00e4bc"], [u"\u00e4"], [None]],
			'\x00\x00\xe4\x00b\x00\x00\xe4\x00\x00\x80\0\0\0\0'
		), ( #20
			[V.FIELD(datatype="short", arraysize="3x2")],
			[[[1,2,3,4,5,6]], [None]],
			'\x00\x00\x01\x00\x02\x00\x03\x00\x04\x00\x05\x00\x06'
			'\x80\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00'
		),
	]


class Binary2ReadTest(testhelpers.VerboseTest):
	"""tests for deserializing BINARY VOTables.
	"""
	__metaclass__ = testhelpers.SamplesBasedAutoTest

	def _runTest(self, sample):
		fielddefs, stuff, expected = sample
		table = votable.parseString((
			'<VOTABLE><RESOURCE><TABLE>'+
			fielddefs+
			'<DATA><BINARY2><STREAM encoding="base64">'+
			stuff.encode("base64")+
			'</STREAM></BINARY2></DATA>'
			'</TABLE></RESOURCE></VOTABLE>').encode("utf-8")).next()
		self.assertEqual(list(table), expected)

	samples = [(
			'<FIELD datatype="boolean"/>',
			"\x001\x000\x80?",
			[[True],[False],[None]],
		), (
			'<FIELD datatype="bit"/>',
			"\x00\x01\x00\x00\x00\xff\x80\x00",
			[[1],[0],[1], [None]],
		), (
			'<FIELD datatype="bit" arraysize="9"/>',
			"\x00\x01\x00\x00\xff\xff\x80\x00\x00",
			[[256],[511], [None]],
		), (
			'<FIELD datatype="bit" arraysize="*"/>',
			"\x00\x00\x00\x00\x03\xff\x00\x00\x00\x00\x45"
				"\xff\x00\x00\x00\x00\x00\x00\x00\x01\x80\x00\x00\x00\x00",
			[[7],[0x1f0000000000000001], [None]],
		), (
			'<FIELD datatype="char"><VALUES null="a"/></FIELD>',
			"\x00x\x00\x00\x00a\x80\x00",
			[['x'],['\x00'], [None], [None]],
		), ( 
# 05
			'<FIELD datatype="unicodeChar"><VALUES null="&#xbabe;"/></FIELD>',
			"\x00\x00a\x00\x23\x42\x00\xba\xbe\x80\x00\x00",
			[['a'],[u'\u2342'], [None], [None]],
		), (
			'<FIELD datatype="unsignedByte"><VALUES null="12"/></FIELD>'
				'<FIELD datatype="short"><VALUES null="12"/></FIELD>'
				'<FIELD datatype="int"><VALUES null="12"/></FIELD>'
				'<FIELD datatype="long"><VALUES null="12"/></FIELD>',
			"\x00\x0c\x00\x0c\x00\x00\x00\x0c\x00\x00\x00\x00\x00\x00\x00\x0c"
			"\xf0\x0c\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00"
			"\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00"
			"\x00\x0d\x0d\x0d\x00\x0d\x0d\x0c\x00\xdd\x00\x00\x00\x00\x00\x0c", [
				[None, None, None, None],
				[None, None, None, None],
				[0, 0, 0, 0],
				[13, 3341, 855308, 62205969853054988L]]
		), (
			'<FIELD datatype="float"/>',
			"\x00\x7f\xc0\x00\x00\x00:\x80\x00\x00\x80\x00\x00\x00\x00",
			[[None], [0.0009765625], [None]]
		), (
			'<FIELD datatype="double"/>',
			"\x00\x7f\xf8\x00\x00\x00\x00\x00\x00\x00?P\x00\x01\x00\x00\x00\x00",
			[[None], [0.00097656343132257462]]
		), (
			'<FIELD datatype="doubleComplex"/>',
			"\x00\x7f\xf8\x00\x00\x00\x00\x00\x00?P\x00\x01\x00\x00\x00\x00"
			'\x00@\x04\x00\x00\x00\x00\x00\x00?\xe0\x00\x00\x00\x00\x00\x00'
			'\x80@\x04\x00\x00\x00\x00\x00\x00?\xe0\x00\x00\x00\x00\x00\x00',
			[[None], [2.5+0.5j], [None]]
		), (
# 10
			'<FIELD datatype="char" arraysize="4"><VALUES null="x"/></FIELD>',
			"\x00abcd\x80\x00\x00\x00\x00",
			[["abcd"], [None]]
		), (
			'<FIELD datatype="char" arraysize="*"/>',
			"\x00\x00\x00\x00\x00\x00\x00\x00\x00\x03abc\x80\x00\x00\x00\x00",
			[[""], ["abc"], [None]]
		), (
			'<FIELD datatype="unicodeChar" arraysize="*"/>',
			"\x00\x00\x00\x00\x03\x00a\x23\x42bc",
			[[u"a\u2342\u6263"]]
		), (
			'<FIELD datatype="unicodeChar" arraysize="2"/>',
			"\x00\x00a\x23\x42\x80\x00\x00\x00\x00",
			[[u"a\u2342"], [None]]
		), (
			'<FIELD datatype="unsignedByte" arraysize="2"/>',
			'\x00\x00\x01\x80\x00\x00',
			[[(0, 1)], [None]],
		), (  
# 15
			'<FIELD datatype="short" arraysize="*"><VALUES null="16"/></FIELD>',
			'\x00\x00\x00\x00\x03\x00\x01\x00\x10\x00\x02'
			'\x80\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00',
			[[(1, None, 2)], [None], [()]],
		), (
			'<FIELD datatype="int" arraysize="2"/>',
			'\x00\x00\x00\x00\x03\x00\x01\x00\x10\x80\0\0\0\0\0\0\0\0',
			[[(3, 0x10010)], [None]],
		), (
			'<FIELD datatype="float" arraysize="2"/>',
			'\x00\x7f\xc0\x00\x00:\x80\x00\x00',
			[[(None, 0.0009765625)]],
		), (
			'<FIELD datatype="double" arraysize="*"/>',
			'\x00\x00\x00\x00\x02\x7f\xf8\x00\x00\x00\x00\x00\x00'
				'?P\x00\x01\x00\x00\x00\x00',
			[[(None, 0.00097656343132257462)]]
		), (
			'<FIELD datatype="float" arraysize="2"><VALUES null="2"/></FIELD>',
			'\x00\x7f\xc0\x00\x00:\x80\x00\x00',
			[[(None, 0.0009765625)]],
		), (
			'<FIELD datatype="floatComplex" arraysize="2"/>',
			'\x00\x7f\xc0\x00\x00:\x80\x00\x00'
				'A\x80\x00\x00A\x0c\x00\x00',
			[[(None, 16+8.75j)]],
		), (
			'<FIELD datatype="short" arraysize="2x3"/>',
			'\x00\x00\x00\x00\x01\x00\x02\x00\x03\x00\x04\x00\x05',
			[[(0,1,2,3,4,5)]],
		)]


class NDArrayTest(testhelpers.VerboseTest):
	"""tests for the (non-existing) support for multi-D arrays.
	"""
	def _assertRavels(self, arrayspec, data, expected):
		res = votable.unravelArray(arrayspec, data)
		self.assertEqual(res, expected)

	def testUnravelNull(self):
		self._assertRavels("*", range(10), range(10))
	
	def testUnravelPlain(self):
		self._assertRavels("3x2", range(6), [[0,1,2],[3,4,5]])

	def testUnravelSkewed(self):
		self._assertRavels("3x2", range(5), [[0,1,2],[3,4]])

	def testUnravelOverlong(self):
		self._assertRavels("3x2", range(9), [[0,1,2],[3,4,5],[6,7,8]])

	def testUnravelAccpetsStar(self):
		self._assertRavels("3x2*", range(9), [[0,1,2],[3,4,5],[6,7,8]])

	def testUnravel3d(self):
		self._assertRavels("3x2x2", range(12), 
			[[[0,1,2],[3,4,5]], [[6,7,8],[9,10,11]]])


class WeirdTablesTest(testhelpers.VerboseTest):
	"""tests with malformed tables and fringe cases.
	"""
	def testEmpty(self):
		for data in votable.parseString("<VOTABLE/>"):
			self.fail("A table is returned for an empty VOTable")

	def testEmptySimple(self):
		data, metadata = votable.load(StringIO("<VOTABLE/>"))
		self.failUnless(data is None)

	def testBadStructure(self):
		it = votable.parseString("<VOTABLE>")
		self.assertRaisesWithMsg(votable.VOTableParseError, 
			"no element found: line 1, column 9", list, it)

	def testLargeTabledata(self):
		# This test is supposed to exercise multi-chunk parsing.  So,
		# raise the "*20" below when you raise tableparser._StreamData.minChunk
		vot = V.VOTABLE[V.RESOURCE[votable.DelayedTable(
    	V.TABLE[V.FIELD(name="col1", datatype="char", arraysize="*"),],
    	[["a"*1000]]*20, V.BINARY)]]
		dest = StringIO()
		votable.write(vot, dest)
		dest.seek(0)
		data, metadata = votable.load(dest)
		self.assertEqual(len(data), 20)
		self.assertEqual(len(data[0]), 1)
		self.assertEqual(len(data[0][0]), 1000)

	def testUnknownAttributesFails(self):
		it = votable.parseString('<VOTABLE><RESOURCE class="upper"/></VOTABLE>')
		self.assertRaisesWithMsg(votable.VOTableParseError, 
			'At [<VOTABLE><RESOURCE class="u...], (1, 9): Invalid VOTable construct: constructor() got an unexpected keyword argument \'class\'',
			list, 
			(it,))

	def testBadTag(self):
		it = votable.parseString("<VOTABLE><FOO/></VOTABLE>")
		self.assertRaisesWithMsg(votable.VOTableParseError, 
			"At [<VOTABLE><FOO/></VOTABLE>], (1, 9): Unknown tag: FOO", list, it)



class StringArrayTest(testhelpers.VerboseTest):
	"""tests for the extra-special case of 2+D char arrays.
	"""
	def _get2DTable(self, enc):
		return V.VOTABLE[V.RESOURCE[votable.DelayedTable(
			V.TABLE[V.FIELD(name="test", datatype="char", arraysize="2x*")], 
			[[("ab", "c", "def")]], enc)]]

	def test2dTdencWrite(self):
		self.failUnless("<TD>abc de</TD>" in votable.asString(
			self._get2DTable(V.TABLEDATA)))

	def test2dBinaryWrite(self):
		self.assertRaises(NotImplementedError,
			lambda: votable.asString(self._get2DTable(V.BINARY)))


class UnicodeCharStringsTest(testhelpers.VerboseTest):
# Make sure we don't bomb when someone hands us unicode strings
# for char tables.
	def _getDataTable(self, enc):
		return votable.asString(
			V.VOTABLE[V.RESOURCE[votable.DelayedTable(
				V.TABLE[V.FIELD(name="test", datatype="char", arraysize="*")], 
				[[u"\u03b2"]], enc)]])

	def testInTD(self):
		self.failUnless("<TD>?</TD>" in 
			self._getDataTable(V.TABLEDATA))

	def testInBinary(self):
		self.failUnless('STREAM encoding="base64">AAAAAT8'
			in self._getDataTable(V.BINARY))


class SimpleInterfaceTest(testhelpers.VerboseTest):
	def testIterDict(self):
		data, metadata = votable.load("test_data/importtest.vot")
		res = list(metadata.iterDicts(data))
		self.assertEqual(res[0]["FileName"], "ngc104.dat")
		self.assertEqual(res[1]["apex"], None)

	def testWrite(self):
		data, metadata = votable.load("test_data/importtest.vot")
		dest = StringIO()
		votable.save(data, metadata.votTable, dest)
		content = dest.getvalue()
		self.failUnless("QFILtsN2C/ZAGBY4hllK" in content)
		self.failUnless('name="n_VHB"' in content)
		self.failUnless('Right Ascension (J2000)</DESCRIPTION>' in content)


class RecordArrayTest(testhelpers.VerboseTest):
	def testPlain(self):
		data, metadata = votable.loads("""<VOTABLE>
			<RESOURCE><TABLE>
				<FIELD name="a" datatype="int"/>
				<FIELD name="b" datatype="double"/>
				<FIELD name="c" datatype="char" arraysize="4"/>
				<DATA><TABLEDATA>
					<TR><TD>1</TD><TD>23.25</TD><TD>abcd</TD></TR>
					<TR><TD>2</TD><TD>-2e6</TD><TD>x</TD></TR>
				</TABLEDATA></DATA></TABLE></RESOURCE></VOTABLE>""")
		arr = rec.array(data, dtype=votable.makeDtype(metadata))
		self.assertEqual(tuple(arr[0]), (1, 23.25, 'abcd'))
		self.assertEqual(tuple(arr[1]),  (2, -2000000.0, 'x'))

	def testVarLengthStrings(self):
		data, metadata = votable.loads("""<VOTABLE>
			<RESOURCE><TABLE>
				<FIELD name="a" datatype="short"/>
				<FIELD name="c" datatype="char" arraysize="*"/>
				<DATA><TABLEDATA>
					<TR><TD>1</TD><TD>short string</TD></TR>
					<TR><TD>2</TD><TD>A long, long string that will have to be trunc...</TD></TR>
				</TABLEDATA></DATA></TABLE></RESOURCE></VOTABLE>""")
		arr = rec.fromrecords(data, dtype=votable.makeDtype(metadata))
		self.assertEqual(arr[0][1], 'short string')
		self.assertEqual(arr[1][1], 'A long, long string ')


class StanXMLText(testhelpers.VerboseTest):
	# make sure VOTable work as normal stanxml trees in a pinch
	def testSimple(self):
		vot = V.VOTABLE[
			V.INFO(name="QUERY_STATUS", value="ERROR")["Nothing, testing"]]
		self.assertEqual(vot.render(), '<VOTABLE version="1.3" xmlns="http://www.ivoa.net/xml/VOTable/v1.3" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xsi:schemaLocation="http://www.ivoa.net/xml/VOTable/v1.3 http://vo.ari.uni-heidelberg.de/docs/schemata/VOTable-1.3.xsd"><INFO name="QUERY_STATUS" value="ERROR">Nothing, testing</INFO></VOTABLE>')


class _BOMB(V._VOTElement):
	def isEmpty(self):
		return False

	def write(self, outputFile):
		raise base.ReportableError("This element is a VOTable Bomb.")


class StackUnwindingTest(testhelpers.VerboseTest):
# these are test that even if there's an ugly error during VOTable
# serialization, some semblance of VOTable results, and also that 
# there's an appropriate error message
	def testErrorWhileMeta(self):
		vot = V.VOTABLE[
			V.RESOURCE(type="results")[
				V.TABLE[
					V.FIELD(name="junk"),],
				V.DEFINITIONS[_BOMB()]]]
		result = votable.asString(vot)
		self.failUnless("</INFO></RESOURCE></VOTABLE>" in result)
		self.failUnless("content is probably incomplete" in result)
		self.failUnless("This element is a VOTable Bomb")
	
	def testErrorWhileTABLEData(self):
		vot = V.VOTABLE[
			V.RESOURCE(type="results")[
				votable.DelayedTable(
					V.TABLE[
						V.FIELD(name="junk", datatype="float"),],
					[[0.2], ["abc"]], V.TABLEDATA)]]
		result = votable.asString(vot)
		self.failUnless("<TD>0.2" in result)
		self.failUnless("content is probably incomplete" in result)
		self.failUnless("could not convert string to float: abc" in result)
		self.failUnless("</TABLEDATA>" in result)
		self.failUnless("</RESOURCE></VOTABLE>" in result)

	def testErrorWhileBINARY(self):
		vot = V.VOTABLE[
			V.RESOURCE(type="results")[
				votable.DelayedTable(
					V.TABLE[
						V.FIELD(name="junk", datatype="float"),],
					[[0.2], ["abc"]], V.BINARY)]]
		result = votable.asString(vot)
		self.failUnless("PkzMzQ==" in result)
		self.failUnless("content is probably incomplete" in result)
		self.failUnless("is not a float" in result)
		self.failUnless("</BINARY>" in result)
		self.failUnless("</RESOURCE></VOTABLE>" in result)


class ParamTypecodeGuessingTest(testhelpers.SimpleSampleComparisonTest):

	functionToRun = staticmethod(votable.guessParamAttrsForValue)
	
	samples = [
		(15, {"datatype": "int"}),
		("23", {"datatype": "char", "arraysize": "*"}),
		([1, 2], {"datatype": "int", "arraysize": "2"}),
		([[1, 2], [2, 3], [4, 5]], {"datatype": "int", "arraysize": "2x3"}),
		(["abc", "defg", "alles Quatsch"], {"datatype": "char", 
			"arraysize": "13x3"}),
# 05
		([datetime.datetime.now(), datetime.datetime.now()],
			{"datatype": "char", "arraysize": "20x2", "xtype": "adql:TIMESTAMP"}),
		(pgsphere.SPoint.fromDegrees(10, 20), 
			{'arraysize': '*', 'datatype': 'char', 'xtype': 'adql:POINT'}),
		([pgsphere.SPoint.fromDegrees(10, 20)], 
			ValueError("Arrays of variable-length arrays are not allowed.")),
		(base.NotGiven, base.NotFoundError(repr(base.NotGiven), 
			"VOTable type code for", "paramval.py predefined types")),
	]


class ParamValueSerializationTest(testhelpers.SimpleSampleComparisonTest):

	def functionToRun(self, args):
		datatype, arraysize, val = args
		param = V.PARAM(name="tmp", datatype=datatype, arraysize=arraysize)
		votable.serializeToParam(param, val)
		return param.value

	samples = [
		(("int", None, None), "99"),
		(("char", "*", None), ""),
		(("char", "4", None), "xxxx"),
		(("float", "1", None), "NaN"),
		(("double", "2x2", None), "NaN NaN NaN NaN"),
# 5
		(("long", "2x2", None), "99 99 99 99"),
		(("int", None, 33), "33"),
		(("char", "4x*", ["foobar", "wo", "nnnn"]), "foobwo  nnnn"),
		(("int", "2x3x4", range(24)), '0 1 2 3 4 5 6 7 8 9 10 11 12 13 14 15 16 17 18 19 20 21 22 23'),
		(("double", None, 0.25), "0.25"),
		(("double", "2", [0.25, 1]), "0.25 1.0"),
	]

	def testDatetimeValue(self):
		param = V.PARAM(name="tmp", datatype="char", arraysize="*",
			xtype="adql:TIMESTAMP")
		votable.serializeToParam(param, 
			datetime.datetime(2015, 5, 19, 15, 6, 22, 25))
		self.assertEqual(param.value, "2015-05-19T15:06:22Z")

	def testDatetimeNULL(self):
		param = V.PARAM(name="tmp", datatype="char", arraysize="*",
			xtype="adql:TIMESTAMP")
		votable.serializeToParam(param, None)
		self.assertEqual(param.value, "")
	
	def testSPointValue(self):
		param = V.PARAM(name="tmp", datatype="char", arraysize="*",
			xtype="adql:POINT")
		votable.serializeToParam(param, 
			pgsphere.SPoint.fromDegrees(10, 12))
		self.assertEqual(param.value, "Position UNKNOWNFrame 10. 12.")


if __name__=="__main__":
	testhelpers.main(BinaryReadTest)
