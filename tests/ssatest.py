"""
Some tests around the SSAP infrastructure.
"""

from gavo import api
from gavo.helpers import testhelpers

def getRD():
	return api.getRD("//ssap")


class RDTest(testhelpers.VerboseTest):
# tests for some aspects of the ssap rd.
	def testUtypes(self):
		self.assertEqual("ssa:Access.Reference",
			getRD().getById("ssabase").getColumnByName("accref").utype)

	def testNormalizedDescription(self):
		self.failUnless("matches your query" in
			getRD().getById("ssahcd_outtable").getColumnByName("ssa_score"
				).description)
			

if __name__=="__main__":
	testhelpers.main(RDTest)
