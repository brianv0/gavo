"""
Some fundamental algorithms not found in the standard library.
"""

class IndexedGraph(object):
	"""is a graph that is indexed by both incoming and outgoing edges.

	The constructor argument edges is an iterable of (from, to)-tuples,
	where both from and to must be hashable.

	The class keeps a set rootNodes of "root nodes" (i.e. those with
	no incoming edges).

	To find leaf nodes, you'd have to compute allNodes-set(outgoingIndex).

	You may access allNodes, rootNodes, incomingIndex, and outgoingIndex
	reading, but any external change to them will wreak havoc.
	"""
	def __init__(self, edges):
		self.allNodes = set()
		self.rootNodes = self.allNodes.copy()
		self.incomingIndex, self.outgoingIndex = {}, {}
		for comeFrom, goTo in edges:
			self.addEdge(comeFrom, goTo)

	def __nonzero__(self):
		return not not self.incomingIndex

	def addEdge(self, comeFrom, goTo):
		self.incomingIndex.setdefault(goTo, set()).add(comeFrom)
		self.outgoingIndex.setdefault(comeFrom, set()).add(goTo)
		self.allNodes.add(goTo)
		self.allNodes.add(comeFrom)
		if comeFrom not in self.incomingIndex:
			self.rootNodes.add(comeFrom)
		self.rootNodes.discard(goTo)

	def removeEdge(self, comeFrom, goTo):
		if (comeFrom not in self.outgoingIndex or 
				goTo not in self.outgoingIndex[comeFrom]):
			raise KeyError("No edge %s->%s"%(comeFrom, goTo))
		self.outgoingIndex[comeFrom].remove(goTo)
		self.incomingIndex[goTo].remove(comeFrom)
		if not self.outgoingIndex[comeFrom]:
			del self.outgoingIndex[comeFrom]
			if comeFrom not in self.incomingIndex:
				self.allNodes.remove(comeFrom)
				self.rootNodes.discard(comeFrom)
		if not self.incomingIndex[goTo]:
			del self.incomingIndex[goTo]
			self.rootNodes.add(goTo)
			if goTo not in self.outgoingIndex:
				self.allNodes.remove(goTo)
				self.rootNodes.discard(goTo)

	def getEdge(self):
		"""returns a random edge.

		It raises an IndexError if the graph is empty.
		"""
		comeFrom = self.incomingIndex.iterkeys().next()
		goTo = self.incomingIndex[comeFrom].pop()
		self.incomingIndex[comeFrom].add(goTo)
		return comeFrom, goTo

	def getSomeRootNode(self):
		"""returns an arbitrary element of rootNodes.

		This will raise a KeyError if no root nodes are left.
		"""
		el = self.rootNodes.pop()
		self.rootNodes.add(el)
		return el


def topoSort(edges):
	"""returns a list with the nodes in the graph edges sorted topologically.

	edges is a sequence of (from, to)-tuples, where both from and to must
	be hashable.

	A ValueError is raised if the graph is not acyclic.
	"""
	res, emptySet = [], frozenset()
	graph = IndexedGraph(edges)
	while graph.rootNodes:
		comeFrom = graph.getSomeRootNode()
		res.append(comeFrom)
		outgoingFromCur = graph.outgoingIndex.get(comeFrom, emptySet).copy()
		for goTo in outgoingFromCur:
			graph.removeEdge(comeFrom, goTo)
			if goTo not in graph.allNodes:
				res.append(goTo)
	if graph:
		raise ValueError("Graph not acyclic, cycle: %s->%s"%graph.getEdge())
	return res
