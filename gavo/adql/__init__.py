from gavo.adql.common import *
from gavo.adql.tree import (
	getTreeBuildingGrammar as getGrammar,
	addFieldInfos)
from gavo.adql.nodes import flatten
from gavo.adql.grammar import (
	getADQLGrammar as getRawGrammar, 
	ParseException)
from gavo.adql.morphpg import (
	morphPG,
	insertQ3Calls)

def parseToTree(adqlStatement):
	return getGrammar().parseString(adqlStatement)[0]
