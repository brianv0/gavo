# Author: Francesco Pierfederici <fpierfed@eso.org>.
# Licensed under the Academic Free License version 2.0 (see LICENSE.txt). 
"""
VOTable::Parser
"""
import urllib
import warnings

try:
	from xml.etree import ElementTree
except ImportError:
	try:
			import cElementTree as ElementTree
	except:
			from elementtree import ElementTree

import DataModel
import Decoders


# FIXME: save the data array of a table as a 2D numpy.array.
# FIXME: add a 1D numpy.array to each Dield (data attribute).
# FIXME: add to the table's data array the PARAMs.


def stripNamespace(qName):
    if '}' in qName:
        return qName.split('}')[-1]
    return qName


def structFormatString(fields):
    """
    Given a list of Field objects, compose the corrseponding Python struct 
    format string.
    """
    for field in fields:
        typ = field.datatype
        length = field.length



# TODO: Resolve references (e.g. ref attributes or FIELDref elements).
class Parser(object):
    def __init__(self, fileURL):
        """
        Constructor.
        
        Input
        fileURL    URL of a XML VOTable file (use file:// for local
                   files). fileURL could also be a Python file 
                   object.
        """
        # Internal/private attributes
        self._fileURL = fileURL
        self._votableTree = None
        
        # Public attributes
        self.votable = None
        
        # Parse the file
        self._parse()
        return

    def _guessNamespace(self):
        """sets a namespace attribute from the namespace of the VOTable
        root element.

        The namespace is required to make the findalls reliable.
        """
        tag = self._votableTree.tag
        if "}" in tag:
            self.namespace = tag.split("}")[0][1:]
        else:
            self.namespace = None
    
    def findall(self, element, tagName):
        """is ElementTree's findall, namespaced to the root's namespace.
        """
        if self.namespace is None:
            return element.findall(tagName)
        else:
            return element.findall(
                str(ElementTree.QName(self.namespace, tagName)))

    def find(self, element, tagName):
        """is ElementTree's findall, namespaced to the root's namespace.
        """
        if self.namespace is None:
            return element.find(tagName)
        else:
            return element.find(
                str(ElementTree.QName(self.namespace, tagName)))

    def _parse(self):
        """
        Parse the XML VOTable which self._fileURL points to. Create the 
        necessary object structure and store its root into self._decodedData.
        
        Input
        None
        
        Output
        None
        
        Raise
        Execption if the XML parsing failed or self._fileURL points to a non
        existent/non readable/non valid XML VOTable.
        """
        # Open the URL and parse the content.
        if(not hasattr(self._fileURL, 'read')):
            f = urllib.urlopen(self._fileURL)
            self._votableTree = ElementTree.parse(f).getroot()
        else:
            self._votableTree = ElementTree.parse(self._fileURL).getroot()
       
        self._guessNamespace()
        
        # Now create the table object.
        votable = DataModel.VOTable()
        try:
            votable.description = self.find(self._votableTree, 
                'DESCRIPTION').text
        except:
            # No top level description
            votable.description = ''
        
        # Deprecation Warning! VOTable <1.1 required INFO and COOSYS to be
        # enclosed into a DEFINITIONS block.
        definitions = self.find(self._votableTree, 'DEFINITIONS')
        try:
            if(definitions and len(definitions)):
                try:
                    votable.info = self._parseElement(tree=definitions,
                                                      tagName='INFO',
                                                      cls=DataModel.Info)
                except:
                    pass
                votable.coosys = self._parseElement(tree=definitions,
                                                    tagName='COOSYS',
                                                    cls=DataModel.CooSys)[0]
                # warnings.warn('The DEFINITIONS tag has been deprecated.' +
                #               'Please refer to the VOTable 1.1 specs.',
                #               DeprecationWarning)
            else:
                votable.coosys = self._parseElement(tree=self._votableTree,
                                                    tagName='COOSYS',
                                                    cls=DataModel.CooSys)[0]
            # <-- end if
        except:
            votable.coosys = None
        
        # Look for INFO elements outside of the DEFINITIONS block
        # as well. If found, they override the values found inside
        # DEFNITIONS.
        try:
            votable.info = self._parseElement(tree=self._votableTree,
                                              tagName='INFO',
                                              cls=DataModel.Info)
        except:
            pass
        
        # Attributes
        for a in self._votableTree.attrib.keys():
            setattr(votable, a.lower(), self._votableTree.get(a))
        
        # Parse RAPAM elements
        votable.params = self._parseElement(self._votableTree, 
                                            'PARAM', 
                                            DataModel.Param)
        
        # Parse the REASOURCE elements
        votable.resources = self._parseResources()
        
        # Update the votable instance variable.
        self.votable = votable
        return
    
    def _parseResources(self):
        resources = []
        
        # Loop through the RESOURCE elements.
        for rTree in self.findall(self._votableTree, 'RESOURCE'):
            r = DataModel.Resource()
            description = self.find(rTree, 'DESCRIPTION')
            if(description):
                r.description = description.text
            r.info = self._parseElement(tree=rTree,
                                        tagName='INFO',
                                        cls=DataModel.Info)
            coosys = self.find(rTree, 'COOSYS')
            if(coosys):
                r.coosys = self._parseElement(rTree, 
                                              'COOSYS', 
                                              DataModel.CooSys)
            link = self.find(rTree, 'LINK')
            if(link):
                # FIXME: Better LINK parsing.
                r.link = link.get('href')
            
            # Attributes
            for a in rTree.attrib.keys():
                setattr(r, a.lower(), rTree.get(a))
            
            # TODO: Support nested resources.
            r.tables = self._parseTables(rTree)
            r.params = self._parseElement(rTree, 
                                          'PARAM', 
                                          DataModel.Param)
            
            # Add the Resource object to the output list
            resources.append(r)
        return(resources)
   

    def _parseTables(self, resourceTree):
        tables = []
        for tTree in self.findall(resourceTree, 'TABLE'):
            t = DataModel.Table()
            
            # Attributes
            for a in tTree.attrib.keys():
                setattr(t, a.lower(), tTree.get(a))
            
            # Description and link
            description = self.find(tTree, 'DESCRIPTION')
            if(description):
                t.description = description.text
            link = self.find(tTree, 'LINK')
            if(link):
                # FIXME: Better LINK parsing.
                t.link = link.get('href')
            
            # Params and Fields.
            t.params = self._parseElement(tTree, 'PARAM', DataModel.Param)
            t.fields = self._parseElement(tTree, 'FIELD', DataModel.Field,
                self._postprocField)
            # TODO: Support GROUP
            
            # Data
            data = self.find(tTree, 'DATA')
            if(data):
                t.data = self._parseDataElement(data, t.fields)
            else:
                t.data = None
            
            # Update the output list.
            tables.append(t)
        return(tables)
   

    def _postprocField(self, fieldEl, fieldTree):
        fieldEl.values = self._parseElement(fieldTree, "VALUES",
            DataModel.Values)


    def _parseElement(self, tree, tagName, cls, postproc=None):
        """
        Generic XML to object "converter". Given an ElementTree object, a tag
        name and a class, it parses the tree looking for the given tag. Once
        found, the XML ComplexElement corresponding to the tagName is turned 
        into an object of class cls.
        
        It is important to notice that
            1. This method is NOT recursive.
            2. If the tagName complex type has attributes/sub-elements not 
               persent in the definition of cls, then those are ADDED.
            3. CONVENTION: if tagName has text content, that is added to the 
               cls object as cls.text.
        
        Return
        List of cls objects.
        """
        result = []
        for el in self.findall(tree, tagName):
            p = cls()
            
            # Attributes
            for a in el.attrib.keys():
                setattr(p, a, el.get(a))
            
            # Text content
            txt = el.text
            if(txt):
                setattr(p, 'text', txt)
            
            # Sub-elements
            for subEl in el:
                setattr(p, stripNamespace(subEl.tag).lower(), subEl.text)
            
            if postproc is not None:
                postproc(p, el)
            # Update the result list
            result.append(p)
        return(result)
    
    def _parseDataElement(self, dataTree, fields):
        """
        Try and understand how table data was serialized and use 
        the appropriate decoder.
        """

        tableDataTree = self.find(dataTree, 'TABLEDATA')
        binaryTree = self.find(dataTree, 'BINARY')
        fitsTree = self.find(dataTree, 'FITS')
        if(tableDataTree):
            return(self._decodeTableDataElement(tableDataTree, 
                                                fields))
        elif(binaryTree):
            return(self._decodeBinaryElement(binaryTree, fields))
        elif(fitsTree):
            return(self._decodeFitsElement(fitsTree, fields))
        else:
            # Unsupported DATA serialization.
            warnings.warn('Unknown data serialization scheme.)',
                          NotImplementedError)
        return(data)
    
    def _decodeTableDataElement(self, tableDataTree, fields):
        """
        Parse table data serialized in a TABLEDATA element.
        """
        # Create a BinaryDecode object
        decoder = Decoders.TableDataDecoder(fields)
        
        # Unpack the data.
        return(decoder.decode(tableDataTree))
    
    def _decodeBinaryElement(self, binaryTree, fields):
        """
        Parse table data serialized in a BINARY element.
        """
        # The actual data is inside a STREAM eolement...
        return(self._decodeStreamElement(self.find(binaryTree, 'STREAM'), fields))
    
    def _decodeFitsElement(self, binaryTree, fields):
        """
        Parse table data serialized in a FITS element.
        """
        # FIXME: Handle FITS
        warnings.warn('Unsupported data serialization scheme (FITS).',
                      Warning)
        return([])
    
    def _decodeStreamElement(self, streamTree, fields):
        # Create a BinaryDecode object
        decoder = Decoders.StreamDecoder(fields)
        
        # Unpack the data.
        return(decoder.decode(streamTree))








# vim:sta:et:sw=4:
