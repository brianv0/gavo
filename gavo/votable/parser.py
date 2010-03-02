"""
Stream-based parsing of VOTables
"""

from cStringIO import StringIO

from gavo import utils
from gavo.utils import FastElementTree
from gavo.votable import model


DEFAULT_WATCHSET = [model.VOTable.TABLE]

# We treat all VOTable versions as equal.
VOTABLE_NAMESPACES = [
	"http://www.ivoa.net/xml/VOTable/v1.0",
	"http://www.ivoa.net/xml/VOTable/v1.1",
	"http://www.ivoa.net/xml/VOTable/v1.2"]


def _processNodeDefault(node, child, parent):
	"""the default node processor: Append child to parent, return child.
	"""
	parent[child]
	return child


def _processNodeWithContent(node, child, parent):
	"""the node processor for nodes with text content.
	"""
	if node.text and node.text.strip():
		child[node.text]  # Attention: mixed content not supported
	parent[child]
	return child

_end_DESCRIPTION = _processNodeWithContent
_end_INFO = _processNodeWithContent
# STREAMs should ordinarily be processed by the table iterator, so this
# really is only interesting for special applications.
_end_STREAM = _processNodeWithContent  
_end_TD = _processNodeWithContent


def _end_VOTABLE(node, child, parent):
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
				res[FastElementTree.QName(ns, elName)] = v
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
				res[FastElementTree.QName(ns, n)] = val
	return res

computeElements = utils.CachedGetter(_computeElementsImpl)


def parse(inFile, watchset=DEFAULT_WATCHSET):
	"""returns an iterator yielding items of interest.

	inFile is whatever is ok for ElementTree.iterparse.

	watchset is a sequence of items of VOTable you want yielded.  By
	default, that's just VOTable.TABLE.  You may want to see INFO
	or PARAM of certain protocols.
	"""
	watchset = set(watchset)
	processors = computeEndProcessors()
	elements = computeElements()
	elementStack = [None]  # None is VOTABLE's parent
	iterator = iter(FastElementTree.iterparse(inFile, ("start", "end")))

	for ev, node in iterator:
		if ev=="start":
			elementStack.append(elements[node.tag](**dict(node.items())))

		elif ev=="end":
			nodeProc = processors.get(node.tag, _processNodeDefault)
			child = nodeProc(node, elementStack.pop(), elementStack[-1])
			if child is not None and child.__class__ in watchset:
				yield child

		else:
			assert False


def parseString(string, watchset=DEFAULT_WATCHSET):
	"""returns an iterator yielding pairs of (table definition, row iterator).

	string contains a VOTable literal.
	"""
	return parse(StringIO(string), watchset)
