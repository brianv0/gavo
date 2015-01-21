<?xml version="1.0" encoding="UTF-8"?>

<xsl:stylesheet
    xmlns:v="http://www.ivoa.net/xml/VOTable/v1.1"
    xmlns:xsl="http://www.w3.org/1999/XSL/Transform"
		xmlns="http://www.w3.org/1999/xhtml"
    version="1.0">
   
   	<xsl:include href="dachs-xsl-config.xsl"/>

    <!-- A stylesheet to convert SIAP-style service metadata to HTML.  -->

		<xsl:output method="xml" 
			doctype-public="-//W3C//DTD XHTML 1.0 Strict//EN"
			doctype-system="http://www.w3.org/TR/xhtml1/DTD/xhtml1-strict.dtd"/>

		<xsl:template match="v:DESCRIPTION">
			<p class="parbody">
				<xsl:apply-templates/>
			</p>
		</xsl:template>

		<xsl:template name="format-fieldlike">
			<li><strong><xsl:value-of select="@name"/></strong>
				(<xsl:value-of select="@datatype"
					/><xsl:value-of select="@arraysize"/>)
				<xsl:if test="@unit">
					[<xsl:value-of select="@unit"/>]
				</xsl:if>
				<xsl:apply-templates/>
			</li>
		</xsl:template>

		<xsl:template match="v:PARAM">
			<xsl:call-template name="format-fieldlike"/>
		</xsl:template>

		<xsl:template match="v:FIELD">
			<xsl:call-template name="format-fieldlike"/>
		</xsl:template>

		<xsl:template match="v:INFO" priority="0"/>

		<xsl:template match="v:INFO[@name='serviceInfo']" priority="1">
			<h2>Service <xsl:value-of select="."/></h2>
			<p>Access URL: <a>
				<xsl:attribute name="href">
					<xsl:value-of select="@value"/>
				</xsl:attribute>
				<xsl:value-of select="@value"/>
			</a></p>
		</xsl:template>

		<xsl:template match="v:RESOURCE[@type='results']">
			<xsl:apply-templates select="v:INFO"/>

			<h2>Input Parameters</h2>
			<ul>
				<xsl:apply-templates select="v:PARAM[starts-with(@name, 'INPUT:')]"/>
			</ul>

			<h2>Result Table Columns</h2>

			<ul>
				<xsl:apply-templates select="v:TABLE/v:FIELD"/>
			</ul>
		</xsl:template>

		<xsl:template match="/">
			<html>
				<head>
					<title>Service Interface Documentation</title>
					<meta name="robots" content="nofollow"/>
          <xsl:call-template name="localCompleteHead"/>
					<style type="text/css">
						.parbody {
							background-color: white;
							color: #777777;
							font-size: 80%;
						}
					</style>
        </head>
				<body>
					<h1>Service Interface Documentation</h1>
						<xsl:apply-templates/>
				</body>
			</html>
		</xsl:template>
</xsl:stylesheet>
