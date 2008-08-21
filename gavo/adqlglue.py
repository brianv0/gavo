"""
Code to bind the adql library to the data center software.
"""

from gavo import adql


def makeFieldInfo(dataField):
	"""returns an adql.tree.FieldInfo object from a dataField.
	"""
	return adql.FieldInfo(
		dataField.get_unit(), dataField.get_ucd(), dataField)
