"""
Tests for the macro expansion machinery.
"""

#c Copyright 2008-2017, the GAVO project
#c
#c This program is free software, covered by the GNU GPL.  See the
#c COPYING file in the source distribution.


import os

from gavo.helpers import testhelpers

from gavo import base
from gavo import grammars
from gavo import rscdef
from gavo import rscdesc
from gavo.base import macros



def getCleaned(rawIter):
	"""returns cleaned rawdicts form a rawdict iterator

	(this currently just kills the parser_ key).
	"""
	res = []
	for d in rawIter:
		del d["parser_"]
		res.append(d)
	return res


class NakedMacroTest(testhelpers.VerboseTest):
	"""tests for macros.py's MacroExpander.
	"""
	class SimplePackage(macros.MacroPackage):
		def macro_noArg(self):
			return "foo"
		def macro_oneArg(self, arg):
			return arg
		def macro_twoArg(self, arg1, arg2):
			return arg1+arg2

	def testBasic(self):
		me = macros.MacroExpander(self.SimplePackage())
		for unEx, ex in [
				("No macro calls in here", "No macro calls in here"),
				(r"\noArg", "foo"),
				(r"\\noArg expands to \noArg", r"\noArg expands to foo"),
				(r'\oneArg{bla}', r"bla"),
				(r'\quote{\oneArg{bla}}', '"bla"'),
				(r'\oneArg{\oneArg{bla}}', 'bla'),
				(r'Here is \twoArg{\quote{ba\{\}r}}{\noArg}', 'Here is "ba{}r"foo'),
				(r'Here is \twoArg{bar}{\noArg}', "Here is barfoo"),
				# we probably wouldn't want the following, but it's hard to work around.
				(r'Lots \ of \@ weirdness', "Lots \\ of \\@ weirdness"),
			]:
			self.assertEqual(me.expand(unEx), ex)

	def testWhitespace(self):
		me = self.SimplePackage().getExpander()
		for unEx, ex in [
				(r"There is \noArg\+whitespace here", "There is foowhitespace here"),
				(r"There is \noArg whitespace here", "There is foo whitespace here"),
				("Two\nlines", "Two\nlines"),
				("One\\\nline", "One line"),
			]:
			self.assertEqual(me.expand(unEx), ex)

	def testErrors(self):
		me = self.SimplePackage().getExpander()
		self.assertRaisesWithMsg(base.MacroError,
			'Error during macro expansion: No macro'
			' \\unknown available in a SimplePackage context',
			me.expand, (r"an \unknown Macro",))
		self.assertRaisesWithMsg(base.MacroError,
			'Error during macro expansion: Invalid macro arguments to \\quote: []',
			me.expand, (r"\quote takes an argument",))


class ExpandedAttributeTest(testhelpers.VerboseTest):
	"""tests for macro expansion in structure arguments.
	"""


class MacDefTest(testhelpers.VerboseTest):
	def testExpansion(self):
		res = base.parseFromString(rscdesc.RD, """<resource schema="test">
			<macDef name="yx">x-panded</macDef></resource>""")
		self.assertEqual(res.expand(r"\yx"), "x-panded")

	def testMinLength(self):
		self.assertRaisesWithMsg(base.StructureError, 
			'At [<resource schema="test">\\n\\...], (2, 25):'
			" 'x' is not a valid value for name",
			base.parseFromString,
			(rscdesc.RD, """<resource schema="test">
				<macDef name="x">gurk</macDef></resource>"""))

	def testNoJunk(self):
		self.assertRaisesWithMsg(base.StructureError, 
			'At [<resource schema="test">\\n\\...], (2, 22):'
			" macDef elements have no column attributes or children.",
			base.parseFromString,
			(rscdesc.RD, """<resource schema="test">
				<macDef name="yx"><column name="u"/></macDef></resource>"""))


class _FakeRowIterator(grammars.RowIterator):
	def _iterRows(self):
		yield {"fake": "sure"}
		del self.grammar


class _FakeFileGrammar(grammars.Grammar):
	"""A grammar for testing purposes.

	The source token is a string supposed to be a file name.  The row
	iterator returns a constant row {"fake": "sure"}.
	"""
	name_ = "fakeFileGrammar"
	rowIterator = _FakeRowIterator


def getCleaned(rawIter):
	"""returns cleaned rawdicts form a rawdict iterator

	(this currently just kills the parser_ key).
	"""
	res = []
	for d in rawIter:
		del d["parser_"]
		res.append(d)
	return res


class GrammarMacroTest(testhelpers.VerboseTest):
	def _testOne(self, macroDef, input, result):
		g = base.parseFromString(_FakeFileGrammar, """<fakeFileGrammar>
			<rowfilter><setup>
			<par late="True" name="res">%s</par></setup>
			<code>
				row["res"] = res
				yield row
			</code></rowfilter></fakeFileGrammar>"""%macroDef)
		res = [] 
		irp = os.path.join(base.getConfig("inputsDir"), input)
		expectedRow = {'fake': 'sure', 'res': result}
		if isinstance(result, Exception):
			self.assertRaises(result.__class__,
				lambda: getCleaned(g.parse(irp)))
		else:
			self.assertEqual(getCleaned(g.parse(irp)), 
				[expectedRow])

	def testInputRelative(self):
		self._testOne(r"\inputRelativePath", "foo.one", "foo.one")

	def testNonStrict(self):
		self._testOne(r"\inputRelativePath", "foo+ .one&", "foo+ .one&")

	def testStrict(self):
		self._testOne(r"\inputRelativePath{False}", "foo+ .one&", ValueError())

	def testOffInputs(self):
		self._testOne(r"\inputRelativePath", "/etc/passwd", ValueError())


class RDMacroTest(testhelpers.VerboseTest):
	def testSundry(self):
		rd = base.parseFromString(rscdesc.RD, r"""<resource schema="test">
			<macDef name="base">Foo Bar</macDef>
			<meta name="testing" format="rst">Go to 
			\internallink{h/e/l/l}</meta>
			<meta name="lowername">\decapitalize{\base}</meta></resource>""")
		self.failUnless("</a>" in 
			rd.getMeta("testing").getContent(targetFormat="html", macroPackage=rd))
		self.assertEqual(base.getMetaText(rd, "lowername"),
			"foo Bar")


class TableMacroTest(testhelpers.VerboseTest):
	def testgetParamNull(self):
		t = base.parseFromString(rscdef.TableDef,
			"""<table id="test"><param name="foo"/></table>""")
		self.assertEqual(t.expand("\getParam{foo}"), "NULL")

	def testGetNonexPar(self):
		t = base.parseFromString(rscdef.TableDef,
			"""<table id="test"><param name="foo"/></table>""")
		self.assertEqual(t.expand("\getParam{bar}"), "")

	def testGetFloatPar(self):
		t = base.parseFromString(rscdef.TableDef,
			"""<table id="test"><param name="foo">0.3</param></table>""")
		self.assertEqual(t.expand("\getParam{foo}"), "0.3")

	def testGetDatePar(self):
		t = base.parseFromString(rscdef.TableDef,
			"""<table id="test"><param name="foo" type="timestamp"
				>1975-03-02</param></table>""")
		self.assertEqual(t.expand("\getParam{foo}"), "1975-03-02")



if __name__=="__main__":
	testhelpers.main(TableMacroTest)
