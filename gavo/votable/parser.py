"""
Stream parsing of VOTables.

This module builds on a shallow wrapping of expat in utils.iterparse.
There is an "almost-tight" parsing loop in the parse method.  It
builds an xmlstan tree (mainly through the _processNodeDefault method).
"""

# To fiddle with the nodes as they are generated, define an
# _end_ELEMENTNAME method.  If you do this, you will have to do
# any adding of children to parents yourself (it happens in 
# _processNodeDefault, which is called when no custom handler is
# present.
from cStringIO import StringIO

from gavo import utils
from gavo.utils import ElementTree
from gavo.votable import common
from gavo.votable import model
from gavo.votable import tableparser


DEFAULT_WATCHSET = []

# We treat all VOTable versions as equal.
VOTABLE_NAMESPACES = [
	"http://www.ivoa.net/xml/VOTable/v1.0",
	"http://www.ivoa.net/xml/VOTable/v1.1",
	"http://www.ivoa.net/xml/VOTable/v1.2"]


def _processNodeDefault(text, child, parent):
	"""the default node processor: Append child to parent, return child.
	"""
	parent[child]
	return child


def _processNodeWithContent(text, child, parent):
	"""the node processor for nodes with text content.
	"""
	if text and text.strip():
		child[text]  # Attention: mixed content not supported
	parent[child]
	return child


_end_DESCRIPTION = _processNodeWithContent
_end_INFO = _processNodeWithContent
# STREAMs and TABLEDATA should ordinarily be processed by the table 
# iterator, so this really is only interesting for special applications:
_end_STREAM = _processNodeWithContent  
_end_TD = _processNodeWithContent


def _end_VOTABLE(text, child, parent):
# VOTABLEs have no useful parents.
	return child


def _computeEndProcessorsImpl():
	"""returns a dictionary of tag names to end processors.

	Each processor as defined using _end_XXXX has an entry each for
	each namespace we're likely to encounter, and one non-namespaced.
	"""
	res, globs = {}, globals()
	for n, v in globs.iteritems():
		if n.startswith("_end_"):
			elName = n[5:]
			res[elName] = v
			for ns in VOTABLE_NAMESPACES:
				res["%s:%s"%(ns, elName)] = v
	return res

computeEndProcessors = utils.CachedGetter(_computeEndProcessorsImpl)


def _computeElementsImpl():
	"""returns a dictionary of tag names to xmlstan elements building them.

	All elements are present for each VOTABLE_NAMESPACE, plus once non-namespaced.
	"""
	res = {}
	for n in dir(model.VOTable):
		if not n.startswith("_"):
			val = getattr(model.VOTable, n)
			res[n] = val
			for ns in VOTABLE_NAMESPACES:
				res[ElementTree.QName(ns, n)] = val
	return res

computeElements = utils.CachedGetter(_computeElementsImpl)


def parse(inFile, watchset=DEFAULT_WATCHSET, ignoreUnknowns=False):
	"""returns an iterator yielding items of interest.

	inFile is a something that supports read(bytes)

	watchset is a sequence of items of VOTable you want yielded.  By
	default, that's just VOTable.TABLE.  You may want to see INFO
	or PARAM of certain protocols.
	"""
# This parser has gotten a bit too fat.  Maybe move the whole thing
# to a class?  All this isn't terribly critical to performance...
	watchset = set(watchset)
	idmap = {}
	processors = computeEndProcessors()
	elements = computeElements()
	elementStack = [None]  # None is VOTABLE's parent
	iterator = utils.iterparse(inFile, common.VOTableParseError)

	for type, tag, payload in iterator:
		if type=="data":
			content.append(payload)

		elif type=="start":
			# Element open: push new node on the stack...
			if tag not in elements:
				raise iterator.getParseError("Unknown tag: %s"%tag)
			if payload: 
					# Force attr keys to the byte strings for kw args and drop everything
					# that's namespace related -- it's not necessary for VOTables
					# and people mess it up anyway.
				payload = dict((str(k.replace("-", "_")), v) 
					for k, v in payload.iteritems() if (not ":" in k and k!="xmlns"))
			elementStack.append(elements[tag](**payload))

			# ...prepare for new content,...
			content = []

			# ...add the node to the id map if it has an ID...
			elId = payload.get("ID")
			if elId is not None:
				idmap[elId] = elementStack[-1]

			# ...and pass control to special iterator if DATA is coming in.
			if tag=="DATA":
				yield tableparser.Rows(elementStack[-2], iterator)

		elif type=="end":
			# Element close: process text content...
			if content:
				text = "".join(content)
				content = []
			else:
				text = None

			# ...see if we have any special procssing to do for the node type...
			nodeProc = processors.get(tag, _processNodeDefault)
			preChild = elementStack.pop()
			# ...call handler with the current node and its future parent...
			child = nodeProc(text, preChild, elementStack[-1])

			# ...and let user do something with the element if she ordered it.
			if child is not None and child.__class__ in watchset:
				child.idmap = idmap
				yield child

		else:
			assert False


def readRaw(inFile):
	"""returns a V.VOTABLE instance with filled-in data for the input from
	inFile.
	"""
	res = None
	for el in parse(inFile, [model.VOTable.TABLE, model.VOTable.VOTABLE]):
		if isinstance(el, tableparser.Rows):
			el.tableDefinition.rows = list(el)
	return el



def parseString(string, watchset=DEFAULT_WATCHSET):
	"""returns an iterator yielding pairs of (table definition, row iterator).

	string contains a VOTable literal.
	"""
	return parse(StringIO(string), watchset)
