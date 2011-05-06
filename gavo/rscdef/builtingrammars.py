"""
The built-in grammars of DaCHS.

Amend this GRAMMAR_REGISTRY if you write a new embedded grammar.

We had self-registration of grammars at one point, but having to
import all grammars seemed quite a bit of waste, so how there's this
manual registry.
"""

from gavo import base
from gavo import utils

GRAMMAR_REGISTRY = {
# elementName -> (module (without gavo.), class name)
	"binaryGrammar": ("grammars.binarygrammar", "BinaryGrammar"),
	"columnGrammar": ("grammars.columngrammar", "ColumnGrammar"),
	"contextGrammar": ("svcs.inputdef", "ContextGrammar"),
	"customGrammar": ("grammars.customgrammar", "CustomGrammar"),
	"dictlistGrammar": ("grammars.dictlistgrammar", "DictlistGrammar"),
	"directGrammar": ("grammars.directgrammar", "DirectGrammar"),
	"embeddedGrammar": ("grammars.embeddedgrammar", "EmbeddedGrammar"),
	"fitsProdGrammar": ("grammars.fitsprodgrammar", "FITSProdGrammar"),
	"freeREGrammar": ("grammars.freeregrammar", "FreeREGrammar"),
	"keyValueGrammar": ("grammars.kvgrammar", "KeyValueGrammar"),
	"nullGrammar": ("grammars.common", "NullGrammar"),
	"reGrammar": ("grammars.regrammar", "REGrammar"),
	"rowsetGrammar": ("grammars.rowsetgrammar", "RowsetGrammar"),
	"voTableGrammar": ("grammars.votablegrammar", "VOTableGrammar"),
}

@utils.memoized
def getGrammar(grammarName):
	if grammarName not in GRAMMAR_REGISTRY:
		raise base.NotFoundError(grammarName, "grammar", "defined grammars")
	grammarClass = utils.loadInternalObject(*GRAMMAR_REGISTRY[grammarName])
	if grammarClass.name_!=grammarName:
		raise base.ReportableError("Internal Error: Grammar %s is registred"
			" under the wrong name."%grammarName,
			hint="This is probably a typo in grammars.__init__; it needs"
			" to be fixed there")
	return grammarClass
