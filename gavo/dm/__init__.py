"""
GAVO's VO-DML+VOTable library.
"""

#c Copyright 2008-2015, the GAVO project
#c
#c This program is free software, covered by the GNU GPL.  See the
#c COPYING file in the source distribution.


# Not checked by pyflakes: API file with gratuitous imports

from gavo.dm.annotations import (
	ColumnAnnotation, DataTypeAnnotation, GroupRefAnnotation,
	ForeignKeyRefAnnotation,
	addFKAnnotations)

from gavo.dm.common import (
	Annotation, getAnnotations,
	DMNode,
	Model, VODMLModel)

from gavo.dm.dmvot import (
	declareDMs,
	getSubtrees,
	asString)
