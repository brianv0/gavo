"""
Tests for the macro expansion machinery.
"""

from gavo import base
from gavo import rscdef
from gavo.helpers import testhelpers
from gavo.base import macros



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


if __name__=="__main__":
	testhelpers.main(NakedMacroTest)
