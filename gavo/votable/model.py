"""
xmlstan elements of VOTable.
"""

from gavo.utils.stanxml import Element

VOTableNamespace = "http://www.ivoa.net/xml/VOTable/v1.2"

class VOTable(object):
	"""The container for VOTable elements.
	"""
	class VOTElement(Element):
		namespace = VOTableNamespace
		local = True

	class _DescribedElement(VOTElement):
		a_ID = None
		a_name = None
		a_ucd = None
		a_utype = None

	class _ValuedElement(_DescribedElement):
		a_unit = None
		a_xtype = None

	class _TypedElement(_ValuedElement):
		a_arraysize = None
		a_datatype = None
		a_precision = None
		a_ref = None
		a_type = None
		a_width = None

	class _RefElement(_ValuedElement):
		a_ref = None
		a_ucd = None
		a_utype = None
		childSequence = []

	class BINARY(VOTElement):
		childSequence = ["STREAM"]
	
	# COOSYS deprecated, we don't even include it.

	class DATA(VOTElement):
		childSequence = ["INFO", "TABLEDATA", "BINARY", "FITS"]
	
	# DEFINITIONS deprecated, see COOSYS

	class FIELD(_TypedElement):
		childSequence = ["DESCRIPTION", "VALUES", "LINK"]
	
	class FIELDref(_RefElement): pass
	
	class FITS(VOTElement):
		childSequence = ["STREAM"]
	
	class GROUP(_DescribedElement):
		a_ref = None
		childSequence = ["DESCRIPTION", "PARAM", "FIELDref", "PARAMref", "GROUP"]
	
	class INFO(_ValuedElement):
		a_ref = None
		a_value = None
		childSequence = [None]
	
	class LINK(VOTElement):
		a_ID = None
		a_action = None
		a_content_role = None
		content_role_name = "content-role"
		a_content_type = None
		content_type_name = "content-type"
		a_gref = None
		a_href = None
		a_title = None
		a_value = None
		childSequence = []

	class MAX(VOTElement):
		a_inclusive = None
		a_value = None
		childSequence = []
	
	class MIN(VOTElement):
		a_inclusive = None
		a_value = None
		childSequence = []

	class OPTION(VOTElement):
		a_name = None
		a_value = None
		childSequence = ["OPTION"]
	
	class PARAM(_TypedElement):
		a_value = None
		childSequence = ["DESCRIPTION", "VALUES", "LINK"]

	class PARAMref(_RefElement): pass

	class RESOURCE(VOTElement):
		a_ID = None
		a_name = None
		a_type = None
		a_utype = None
		childSequence = ["DESCRIPTION", "INFO", "GROUP", "PARAM", "LINK",
			"TABLE", "RESOURCE"]
	
	class STREAM(VOTElement):
		a_actuate = None
		a_encoding = None
		a_expires = None
		a_href = None
		a_rights = None
		a_type = None
		childSequence = [None]
	
	class TABLE(_DescribedElement):
		a_nrows = None
		childSequence = ["DESCRIPTION", "INFO", "GROUP", "FIELD", "PARAM", "LINK",
			"DATA"]
	
	class TABLEDATA(VOTElement):
		childSequence = ["TR"]
	
	class TD(VOTElement):
		a_encoding = None
		childSequence = [None]
	
	class TR(VOTElement):
		a_ID = None
		childSequence = ["TD"]
	
	class VALUES(VOTElement):
		a_ID = None
		a_null = None
		a_ref = None
		a_type = None
	
	class VOTABLE(VOTElement):
		a_ID = None
		a_version = "1.2"
		a_xmlns = VOTableNamespace

