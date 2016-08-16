"""
SIL, the Simple Instance Language, is an attempt to allow
data model instances written in a simple, JSON-like language.
"""

import re

from gavo import utils
from gavo.dm import common


# sentinels for further processing
class Atom(unicode):
	"""a sentinel class for atomic values of roles
	"""
	noQuotesOkRE = re.compile("[\w_.]+$")

	def asSIL(self):
		if self.noQuotesOkRE.match(self):
			return unicode(self)
		else:
			return '"%s"'%(self.replace('"', '""'))
	
	def __repr__(self):
		return "a"+unicode.__repr__(self).lstrip("u")


class Reference(unicode):
	"""a sentinel class for roles referencing something else.
	"""
	def asSIL(self):
		return "@%s"%self


# parse methods, used by getGrammar, by nonterminal name there
def _pa_attributeDef(s, p, toks):
	return ("attr", toks[0], toks[2])

def _pa_typeAnnotation(s, p, toks):
	return toks[1]

def _pa_collection(s, p, toks):
	if len(toks)==1:
		# no explicit type annotation; we return None as type.
		return ("coll", None, toks[0])
	else:
		return ("coll", toks[0], toks[1])

def _pa_obj(s, p, toks):
	return ("obj", toks[0], toks[1][2])

def _pa_objectBody(s, p, toks):
	return ("uobj", None, toks[1].asList())

def _pa_sequenceBody(s, p, toks):
	return [toks[1].asList()]

def _pa_reference(s, p, toks):
	return Reference(toks[1])

def _pa_simpleImmediate(s, p, toks):
	return Atom(toks[0])


class getGrammar(utils.CachedResource):
	"""returns a grammar for parsing a SIL object description.
	"""
	@classmethod
	def impl(cls):
		from gavo.imp.pyparsing import (Word, Literal, alphas, alphanums,
			QuotedString, Forward, ZeroOrMore, Group, Optional)

		with utils.pyparsingWhitechars("\t\n\r "):
			qualifiedIdentifier = Word(alphas+"_:", alphanums+"-._:")
			plainIdentifier = Word(alphas+"_", alphanums+"-._")
			externalIdentifier = Word(alphas+"_", alphanums+"._/#-")
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
				+ Group(ZeroOrMore(value | objectBody))
				+ Literal(']'))
			collection = Optional(typeAnnotation) + sequenceBody

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
		if isinstance(child[2], (Reference, Atom)):
			yield ('attr', child[1], child[2])
		elif isinstance(child[2], tuple):
			for grandchild in _parseTreeToEvents(child[2], roleName=child[1]):
				yield grandchild
		else:
			assert False, "Bad object as parsed value: %s"%repr(child[2])


def _iterObjs(node, seqType, roleName):
	for child in node[2]:
		if isinstance(child, (Reference, Atom)):
			yield ('item', child, None)

		else:
			# complex child -- yield  events
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
	* ('coll', type, None) create a new collection annotation (type can be None)
	* ('item', val, None) add an atomic value to the current collection
	* ('pop', None, None) finish current annotation and add it to its container
	"""
	root = getGrammar().parseString(silLiteral, parseAll=True)[0]
	return _parseTreeToEvents(root)


def getAnnotation(silLiteral, annotationFactory):
	"""returns an annotation object parsed from silLiteral.

	annotationFactory is a callable that takes attributeName/attributeValue
	pairs and returns annotations; attributeValue is either an Atom or
	a Reference in these cases.
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
			obStack[-1].add( #noflake: the del obStack up there is conditional
				annotationFactory(arg1, arg2))

		elif evType=='item':
			collection = obStack[-1] #noflake: see above
			assert isinstance(collection, common.CollectionAnnotation)
			collection.add(annotationFactory(collection.name, arg1)) 

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
seq: [a "b c d" @e]}""", parseAll=True)[0]
	print res
