"""
Modules dealing with generation and delivery of registry records.

Our identifiers have the form

ivo://<authority>/<rd-path>/service-id

for services (do we want specific renderers? That would be bad since right
now they appear as interfaces of the same service...) and

ivo://<authority>/static/<service-resdir-relative-path>

for static resources.

authority is given by authority in the ivoa section of config.
The path of static resources is relative to the rootdir of the services
resource descriptor.

This package deals with two ways to represent resources: 

* res tuples, as returned by servicelist.queryServicesList and used
  whenever no or little metadata is necessary.  Contrary to what their
  name suggests, they are actually dictionaries.

* res objects.  Those are the actual objects (e.g., svc.Service or
  similar).  Since they may be expensive to construct (though, of
  course, most of them ought to be cached on reasonably busy sites),
  they are only constructed when real metadata is required.
"""

from gavo.registry.common import *
from gavo.registry import oaiinter      # registration of RegistryCore
from gavo.registry import servicelist   # registration of getWebServiceList


from gavo.registry.builders import (getVOResourceElement, 
	getVORMetadataElement)
from gavo.registry.identifiers import (getResobFromIdentifier)
from gavo.registry.model import makeSchemaURL, addSchemaLocations
from gavo.registry.tableset import getTablesetForService
