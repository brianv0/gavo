# Author: Francesco Pierfederici <fpierfed@eso.org>.
# Licensed under the Academic Free License version 2.0 (see LICENSE.txt). 
try:
    import cElementTree as ElementTree
except:
    from elementtree import ElementTree


from Encoders import *



# Constants
VERSION = '1.1'                                             # VOTable version.
XML_HEADER = '<?xml version="1.0" encoding="UTF-8"?>'



class VOObject(object):
    """
    Abstract Class
    """
    def __str__(self):
        """
        Provide the str representation for the object. The default
        implementation simply uses the ElementTree.dump() routine.
        """
        return('%s\n%s\n' % (XML_HEADER, 
                             ElementTree.tostring(self.xml())))
    
    def xml(self):
        """
        Provide the XML tree representation for the object. Returns a 
        ElementTree.Element instance.
        """
        name = self.__class__.__name__
        repr = ElementTree.Element(name.upper())
        attrDict = self.__dict__
        for attr in attrDict.keys():
            val = attrDict[attr]
            if(val != None and 
               attr != 'text' and 
               attr != 'description' and
               isinstance(val, basestring)):
                repr.set(attr, val)
        return(repr)

    def setFromDict(self, attrDict):
        """sets attributes from a dictionary.

        This method allows you to set multiple attributes at one go.  You
        are only allowed to set attributes that the object already has.
        If you try to introduce new attributes, you'll get an AttributeError.
        """
        for key, value in attrDict.iteritems():
          oVal = getattr(self, key)
          setattr(self, key, value)
        return self



class VOTable(VOObject):
    def __init__(self, **kwargs):
        self.ID = None
        self.version = VERSION                                # Default value.
        
        self.description = None
        self.info = []
        self.coosys = []
        
        self.params = []
        self.resources = []
        self.setFromDict(kwargs)
        return
    
    def xml(self):
        repr = super(VOTable, self).xml()
        
        # Create and add the sub-elements
        if(self.description):
            description = ElementTree.Element('DESCRIPTION')
            description.text = self.description or 'N/A'
            repr.append(description)
        
        for i in self.coosys:
            repr.append(i.xml())
        
        for i in self.info:
            repr.append(i.xml())
        
        for p in self.params:
            repr.append(p.xml())
        
        for r in self.resources:
            repr.append(r.xml())
        return(repr)



class Resource(VOObject):
    def __init__(self, **kwargs):
        self.description = None
        self.info = []
        self.coosys = None
        self.links = []
        self.name = None
        self.ID = None
        self.type = None
        self.utype = None
        
        self.resources = []
        self.tables = []
        self.params = []
        self.setFromDict(kwargs)
        return
    
    def xml(self):
        repr = super(Resource, self).xml()
        
        # Create and add the sub-elements
        if(self.description):
            description = ElementTree.Element('DESCRIPTION')
            description.text = self.description or 'N/A'
            repr.append(description)
        
        if(self.coosys):
            coosys = self.coosys.xml()
            repr.append(coosys)
        
        for i in self.info:
            repr.append(i.xml())
        
        for p in self.params:
            repr.append(p.xml())
        
        for t in self.tables:
            repr.append(t.xml())
        
        for r in self.resources:
            repr.append(r.xml())
        return(repr)



class Table(VOObject):
    def __init__(self, **kwargs):
        # Attributes
        self.name = None
        self.ID = None
        self.ref = None
        self.ucd = None
        self.utype = None
        self.nrows = None
        
        # Elements
        self.description = None
        self.links = []
        
        # Computed
        self.data = None
        
        # Sub-elements
        self.params = []
        self.fields = []
        self.groups = []                                    # Ignored for now.

        # internal use
        self.coder = TableDataEncoder
        self.setFromDict(kwargs)
        return
    
    def xml(self):
        repr = super(Table, self).xml()
        
        # Create and add the sub-elements
        # FIXME: Add support for GROUP
        if(self.description):
            description = ElementTree.Element('DESCRIPTION')
            description.text = self.description
            repr.append(description)
        
        for l in self.links:
            repr.append(l.xml())
        
        for p in self.params:
            repr.append(p.xml())
        
        for f in self.fields:
            repr.append(f.xml())
        
        # Encode the data part and attach it to the TABLE element.
        # TODO: Better handling of encoder choice.
        data = ElementTree.Element('DATA')
        e = self.coder()
        data.append(e.encode(self.fields, self.data))
        repr.append(data)
        return(repr)



class Link(VOObject):
    def __init__(self, **kwargs):
        self.ID = None
        self.content_role = None
        self.content_type = None
        self.title = None
        self.value = None
        self.href = None
        self.setFromDict(kwargs)

    def xml(self):
        repr = super(Link, self).xml()
        return repr



class Field(VOObject):
    def __init__(self, **kwargs):
        # Attributes
        self.name = None
        self.ID = None
        self.ucd = None
        self.datatype = None
        self.arraysize = '1'
        self.precision = None
        self.unit = None
        self.utype = None
        self.ref = None
        self.type = None                                         # Deprecated.
        self.width = None
        self.data = []
        
        # Sub-elements
        self.description = None
        self.links = []
        self.values = []
        self.setFromDict(kwargs)
        return
    
    def xml(self):
        repr = super(Field, self).xml()
        
        # Create representations for the sub-elements.
        if(self.description):
            description = ElementTree.Element('DESCRIPTION')
            description.text = self.description
            repr.append(description)
        
        for l in self.links:
          repr.append(l.xml())

        if self.values:
            repr.append(self.values.xml())
        return(repr)



class Param(Field):
    def __init__(self, **kwargs):
        super(Param, self).__init__(**kwargs)
        # Attributes
        self.value = None
    
    def xml(self):
        repr = super(Param, self).xml()
        if(self.value):
            repr.set('value', self.value)
        return(repr)



class Info(VOObject):
    def __init__(self, **kwargs):
        super(Info, self).__init__(**kwargs)
        self.name = None
        self.ID = None
        self.value = None
        self.text = None
        self.setFromDict(kwargs)
    
    def xml(self):
        repr = super(Info, self).xml()
        repr.text = self.text
        return(repr)



class CooSys(VOObject):
    def __init__(self, **kwargs):
        self.ID = None
        self.equinox = None
        self.epoch = None
        self.system = None
        self.setFromDict(kwargs)
        return



class MinMax(VOObject):
    """is either a Min or a Max element.
    """
    def __init__(self, **kwargs):
        self.value = None
        self.inclusive = None
        self.setFromDict(kwargs)



class Min(MinMax):
    pass


class Max(MinMax):
    pass


class Options(VOObject):
    def __init__(self, **kwargs):
        self.value = None
        self.name = None
        self.setFromDict(kwargs)



class Values(VOObject):
    def __init__(self, **kwargs):
        self.ID = None
        self.ref = None
        self.min = None
        self.max = None
        self.null = None
        self.type = None
        self.options = []
        self.setFromDict(kwargs)

    def xml(self):
        repr = super(Values, self).xml()
        if self.min:
            repr.append(self.min.xml())
        if self.max:
            repr.append(self.max.xml())
        for opt in self.options:
            repr.append(opt.xml())
        return repr
    
  
# vim:et:ts=4:sta:sw=4:
