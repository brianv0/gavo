"""
Code to bind the adql library to the data center software.
"""

from gavo import adqltree


def makeFieldInfo(dataField):
	"""returns an adqltree.FieldInfo object from a dataField.
	"""
	return adqltree.FieldInfo(
		dataField.get_unit(), dataField.get_ucd(), dataField)
