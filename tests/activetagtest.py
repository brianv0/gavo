"""
Tests for active tags within RDs (and friends).
"""

from gavo import base
from gavo import rscdef
from gavo.helpers import testhelpers


class BasicTest(testhelpers.VerboseTest):
	def testStreamContent(self):
		ctx = base.ParseContext()
		res = base.parseFromString(rscdef.TableDef, """<table id="bar">
			<STREAM id="foo"><table id="u" onDisk="True"><column name="x"/>
			</table></STREAM></table>""", context=ctx)
		parsedEvents = ctx.idmap["foo"].events
		self.assertEqual(len(parsedEvents), 6)
		self.assertEqual(parsedEvents[0][1], "table")
		self.assertEqual(parsedEvents[1][:3], ("value", "onDisk", "True"))
		self.assertEqual(parsedEvents[-1][:2], ("end", "table"))
		self.assertEqual(str(parsedEvents[3][-1]), "(2, 48)")

if __name__=="__main__":
	testhelpers.main(BasicTest)
