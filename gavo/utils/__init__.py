"""
Modules external to the data center.

This comprises helpers and wrappers that do not need gavo.base but for some
reason or another should be within the dc package.
"""

try:
	import cElementTree as ElementTree
except ImportError:
	from elementtree import ElementTree


from mathtricks import findMinimum
