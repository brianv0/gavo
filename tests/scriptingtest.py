"""
Tests dealing with script parsing and execution.
"""

#c Copyright 2008-2017, the GAVO project
#c
#c This program is free software, covered by the GNU GPL.  See the
#c COPYING file in the source distribution.


from gavo.helpers import testhelpers

from gavo.rscdef import scripting



class SQLSplittingTest(testhelpers.VerboseTest):
	__metaclass__ = testhelpers.SamplesBasedAutoTest
	grammar = scripting.getSQLScriptGrammar()

	def _runTest(self, sample):
		script, expectedNumberOfParts = sample
		parts = self.grammar.parseString(script)
		self.assertEqual(len(parts), expectedNumberOfParts, 
			"Too many parts: %s"%parts)
	
	samples = [
		("select * from foo", 1),
		("select * from foo;", 1),
		("select * from foo where \"cra;zy\"=';'", 1),
		("select * from foo;update where bla=7", 2),
		("SELECT a=$$a;bc$$", 1),
		("SELECT a=$$abc$$;c", 2),
		("/* this should be ignored: ; */; this should be there", 1),
		("$funcdef$ stmt; stmt; $$deep;er$$ $funcdef$; two", 2),
		("$funcdef$ stmt\n\n; stmt; $$deep;er$$ $funcdef$; two", 2),
		("'multiline\nstring;'", 1),
		("statement1;\n -- Sp'\nstatement 2 'quoted';", 2),
	]


if __name__=="__main__":
	testhelpers.main(SQLSplittingTest)
