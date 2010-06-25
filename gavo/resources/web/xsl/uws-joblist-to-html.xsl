<?xml version="1.0" encoding="UTF-8"?>

<xsl:stylesheet
    xmlns:uws="http://www.ivoa.net/xml/UWS/v1.0rc3"
    xmlns:xsl="http://www.w3.org/1999/XSL/Transform"
		xmlns="http://www.w3.org/1999/xhtml"
    version="1.0">
    
    <!-- A stylesheet to convert a UWS joblist into HTML.  -->

		<xsl:output method="xml" 
			doctype-public="-//W3C//DTD XHTML 1.0 Strict//EN"
			doctype-system="http://www.w3.org/TR/xhtml1/DTD/xhtml1-strict.dtd"/>

		<xsl:template match="uws:jobref">
			<li>
				<a>
					<xsl:attribute name="href">async/<xsl:value-of select="@id"/></xsl:attribute>
					<xsl:value-of select="@id"/></a>
				(<xsl:apply-templates/>)</li>
		</xsl:template>
	
		<xsl:template match="/">
			<html>
				<head>
					<title>UWS job list</title></head>
				<body>
					<h1>UWS jobs</h1>
					<ul>
						<xsl:apply-templates/></ul></body></html>
		</xsl:template>
</xsl:stylesheet>
