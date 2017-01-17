"""
GAVO's VO-DML+VOTable library.
"""

#c Copyright 2008-2017, the GAVO project
#c
#c This program is free software, covered by the GNU GPL.  See the
#c COPYING file in the source distribution.


# Not checked by pyflakes: API file with gratuitous imports

from gavo.dm.annotations import (ColumnAnnotation, ForeignKeyAnnotation,
	ParamAnnotation)

from gavo.dm.dmrd import DataModelRoles

from gavo.dm.vodml import getModelForPrefix, resolveVODMLId, Model
