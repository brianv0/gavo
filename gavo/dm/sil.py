"""
SIL, the Simple Instance Language, is an attempt to allow
data model instances written in a simple, JSON-like language.
"""

from gavo import utils
from gavo.dm import common


# parse methods, used by getGrammar, by nonterminal name there
def _pa_attributeDef(s, p, toks):
	return ("attr", toks[0], toks[2])

def _pa_typeAnnotation(s, p, toks):
	return toks[1]

def _pa_collection(s, p, toks):
	return ("coll", toks[0], toks[1])

def _pa_obj(s, p, toks):
	return ("obj", toks[0], toks[1][2])

def _pa_objectBody(s, p, toks):
	return ("uobj", None, toks[1].asList())

def _pa_sequenceBody(s, p, toks):
	return [toks[1].asList()]

def _pa_reference(s, p, toks):
	return common.Reference(toks[1])

def _pa_simpleImmediate(s, p, toks):
	return common.Atom(toks[0])


class getGrammar(utils.CachedResource):
	"""returns a grammar for parsing a SIL object description.
	"""
	@classmethod
	def impl(cls):
		from gavo.imp.pyparsing import (Word, Literal, alphas, alphanums,
			QuotedString, Forward, ZeroOrMore, Group)

		with utils.pyparsingWhitechars("\t\n\r "):
			qualifiedIdentifier = Word(alphas+"_:", alphanums+"-_:")
			plainIdentifier = Word(alphas+"_", alphanums+"-_")
			externalIdentifier = Word(alphas+"_", alphanums+"_")
			plainLiteral = Word(alphanums+"_-.")
			quotedLiteral = QuotedString(quoteChar='"', escQuote='""')
			reference = Literal('@') + externalIdentifier

			complexImmediate = Forward()
			simpleImmediate = plainLiteral | quotedLiteral
			value = reference | complexImmediate | simpleImmediate

			attributeDef = (plainIdentifier
				+ Literal(":")
				+ value)
			typeAnnotation = (Literal('(')
				+ qualifiedIdentifier
				+ Literal(')'))
			objectBody = (Literal('{')
				+ Group(ZeroOrMore( attributeDef ))
				+ Literal('}'))
			obj = typeAnnotation + objectBody

			sequenceBody = (Literal('[')
				+ Group(ZeroOrMore(objectBody))
				+ Literal(']'))
			collection = typeAnnotation + sequenceBody

			complexImmediate << ( obj | collection )

		for n, func in globals().iteritems():
			if n.startswith("_pa_"):
				locals()[n[4:]].setParseAction(func)

		cls.symbols = locals()
		return obj

	@classmethod
	def enableDebuggingOutput(cls):
		"""(not user-servicable)
		"""
		from gavo.imp.pyparsing import ParserElement
		for name, sym in cls.symbols.iteritems():
			if isinstance(sym, ParserElement):
				sym.setDebug(True)
				sym.setName(name)


def _iterAttrs(node, seqType, roleName):
	"""generates parse events for nodes with attribute children.

	(see _parseTreeToEvents).
	"""
	for child in node[2]:
		assert child[0]=='attr'
		if isinstance(child[2], common.Reference):
			yield ('attr', child[1], resolveName(child[2]))
		elif isinstance(child[2], common.Atom):
			yield ('attr', child[1], child[2])
		elif isinstance(child[2], tuple):
			for grandchild in _parseTreeToEvents(child[2], roleName=child[1]):
				yield grandchild
		else:
			assert False, "Bad object as parsed value: %s"%repr(child[2])


def _iterObjs(node, seqType, roleName):
	for child in node[2]:
		assert child[0]=='uobj'
		for  grandchild in _parseTreeToEvents(child, seqType=seqType, 
				roleName=roleName):
			yield grandchild


_PARSER_EVENT_MAPPING = {
# -> (iterparse ev name, type source, child parser)
	'obj': ('obj', 'fromNode', _iterAttrs),
	'uobj': ('obj', 'seqType', _iterAttrs),
	'coll': ('coll', 'fromNode', _iterObjs)
}

def _parseTreeToEvents(node, seqType=None, roleName=None):
	"""helps iterparse by interpreting the parser events in evStream.
	"""
	opener, typeSource, childParser = _PARSER_EVENT_MAPPING[node[0]]
	if typeSource=='fromNode':
		nodeType = node[1]
	elif typeSource=='seqType':
		nodeType = seqType
	else:
		assert False
	yield (opener, roleName, nodeType)

	for child in childParser(node, nodeType, roleName):
		yield child

	yield ('pop', None, None)


def iterparse(silLiteral):
	"""yields parse events for a SIL literal in a string.

	The parse events are triples of one of the forms:

	* ('attr', roleName, value) add an attribute to the current annotation
	* ('obj', roleName, type) create a new object object of type
	* ('coll', type, None) create a new collection annotation
	* ('pop', None, None) finish current annotation and add it to its container
	"""
	root = getGrammar().parseString(silLiteral, parseAll=True)[0]
	return _parseTreeToEvents(root)


def getAnnotation(silLiteral, nameResolver):
	"""returns an annotation object parsed from silLiteral.

	References are resolved by calling nameResolver(id).
	"""
	obStack, result = [], None

	for evType, arg1, arg2 in iterparse(silLiteral):
		if evType=='obj':
			obStack.append(common.ObjectAnnotation(arg1, arg2))

		elif evType=='coll':
			obStack.append(common.CollectionAnnotation(arg1, arg2))

		elif evType=='pop':
			newRole = obStack.pop()
			if obStack:
				obStack[-1].add(newRole)
			else:
				# we've just popped the total result.  Make sure
				# any furher operations fail.
				del obStack
				result = newRole

		elif evType=='attr':
			obStack[-1].add( #noflake: the del up there is conditional
				common.AtomicAnnotation(arg1, arg2))

		else:
			assert False

	assert result is not None
	return result

if __name__=="__main__":
	g = getGrammar()
	getGrammar.enableDebuggingOutput()
	res = g.parseString(
		"""
					(:testclass) {
				coll: (:foo)[
					{attr1: a}
					{attr2: b}
					{attr3: c}]}
			""", parseAll=True)[0]
	print res
