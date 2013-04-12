/* A "streaming" fits previewer.

This program takes a FITS image and produces a jpeg image striving
to give an idea what's on the image.  We only want to do one
pass over the input FITS.  Therefore, we scale into an array of floats
and then adapt something like the gamma of that.  From that array, the final
jpeg is generated.

This program should work with NAXIS>2 and will provide a preview of
the image along the fits two axes.
*/

#include <stdio.h>
#include <unistd.h> /* remove when nicing has moved to the caller */
#include <jpeglib.h>
#include <fitsio.h>
#include <math.h>
#include <assert.h>

#define DEFAULT_TARGETWIDTH 200
#define GAMMA_HIST_SIZE 10
/* maximal number of naxis before we bail out */
#define MAXDIM 20 

#define SQR(x) (x)*(x)
#define FITSCATCH(x) if (x) {fatalFitsError(status);}


typedef struct imageDesc_s {
	int pixelType;
	int naxis;
	long shape[MAXDIM];
	long fpixel[MAXDIM];
	int targetShape[2]; /* filled out by computeScale */
	fitsfile *fptr;
	double *scaledData;
} imageDesc;

char *progName;


void fatalFitsError(int status)
{
	if (status==0) { /* sometimes the functions return !=0 but still have
		status ==0 -- weird... */
		return;
	}
	fits_report_error(stderr, status);
	exit(1);
}

void fatalLibError(char *msg)
{
	perror(msg);
	exit(1);
}

void fatalError(char *msg)
{
	fprintf(stderr, "%s\n", msg);
	exit(1);
}

imageDesc *openFits(char *fName)
{
	int i;
	imageDesc *iD=malloc(sizeof(imageDesc));
	int status=0;

	if (!iD) {
		fatalLibError("Allocating image descriptor");
	}

	for (i=0; i<MAXDIM; i++) {
		iD->fpixel[i] = 1;
	}

	FITSCATCH(fits_open_file(&(iD->fptr), fName, READONLY, &status));
	FITSCATCH(fits_get_img_dim(iD->fptr, &(iD->naxis),  &status));
	if (iD->naxis>MAXDIM) {
		fatalError("NAXIS too large; if this is real, increase MAXDIM.");
	}
	FITSCATCH(fits_get_img_param(iD->fptr, 2, &(iD->pixelType), 
		&(iD->naxis), iD->shape, &status));
	return iD;
}


void computeScale(imageDesc *iD, int targetWidth)
/* fills the targetShape attribute of iD */
{
	float imageScale=targetWidth/(iD->shape[0]+0.1);
	int targetHeight = (int)(iD->shape[1]*imageScale);

	if (iD->shape[0]<=0 || iD->shape[1]<=0) {
		fatalError("Empty image cannot be scaled.\n");
	}
	if (targetHeight>targetWidth) { /* don't make images too high */
		imageScale = targetWidth/(iD->shape[1]+0.1);
		targetWidth = (int)(iD->shape[0]*imageScale);
		targetHeight = (int)(iD->shape[1]*imageScale);
	}
	if (imageScale>1) {  /* don't scale up */
		targetWidth=iD->shape[0];
		targetHeight=iD->shape[1];
		imageScale = 1;
	}
	iD->targetShape[0] = targetWidth==0?1:targetWidth;
	iD->targetShape[1] = targetHeight==0?1:targetHeight;
}

void doScale(imageDesc *iD)
/* allocates and fills the double image map by some sort of pixel
averaging 

This assumes that each source pixel only influence at most four
destination pixels, in other word that we're scaling down. */
{
	int i;
	int status=0;
	double *dp;
	float *pixBuf = malloc(iD->shape[0]*sizeof(float));
	long scaledDataSize = iD->targetShape[0]*iD->targetShape[1];
	int nSourceY=iD->shape[1], nSourceX=iD->shape[0];
	int nDestY=iD->targetShape[1], nDestX=iD->targetShape[0];

	if (!pixBuf) {
		fatalLibError("Allocating pixel buffer");
	}
	if (!(iD->scaledData = malloc(scaledDataSize*sizeof(double)))) {
		fatalLibError("Allocating image data");
	}
	for (i=0, dp=iD->scaledData; i<scaledDataSize; i++) {
		*dp++ = 0;
	}

	/* Real scaling work.  Here's my ad-hoc scaling algorithm, explained for
	1D; there's proof-of-concept code in scaletest.py.

	The main difficulty is the diffusion of the quantization error
	over the target pixels.

	Let the source line have N pixels.
	Let the target line have K pixels, and assert K<=N

	Now, the boundaries of source pixel i are i and and i+1.  The boundaries
	of its destination image are (in float arith)

	l_i = i/N*K, u_i = (i+1)/N*K, i=0..N-1

	For each source pixel, compute the overlap of its scaled image of
	with the (at most two, since N>=K) destination pixels:

	d = floor(l_i)  -- the left target pixel
	o_l = (d+1)-l_i  -- overlap of the scaled source pixel with pixel at d
	o_r = u_i-(d+1)

	The value of the source pixel is now distributed in proportion
	o_l/(o_l+o_r) the the left and in proportion o_r/(o_l+o_r)
	to the target pixel and the one right of it.

	Since, at the very right end of the line, o_r is zero, no
	overflow of the target line happens if additions of zeroes are
	suppressed.
	*/

	iD->fpixel[0] = 1;
	iD->fpixel[1] = 1;

	while (iD->fpixel[1]<=nSourceY) {  /* caution: fpixel counts like fortran */
		int dummy, x;
		/* lo = left, hi = right in the application of the recipe in y */
		double loBoundY = (double)(iD->fpixel[1]-1)/nSourceY*nDestY;
		double hiBoundY = (double)iD->fpixel[1]/nSourceY*nDestY;
		int yDestInd = (int)floor(loBoundY);
		double loPart = yDestInd+1-loBoundY;
		double hiPart =  hiBoundY-(yDestInd+1);
		double yDestWeight = 1;
		double yDest1Weight = 0;

		if (hiPart>1e-9) {
			yDestWeight = loPart/(hiPart+loPart);
			yDest1Weight = hiPart/(hiPart+loPart);
		}
		
		if (fits_read_pix(iD->fptr, TFLOAT, iD->fpixel,  iD->shape[0],
				NULL, pixBuf, &dummy, &status)) {
			fatalFitsError(status);
		}

		for (x=0; x<iD->shape[0]; x++) {
			double loBoundX = (double)x/nSourceX*nDestX;
			double upBoundX = (double)(x+1)/nSourceX*nDestX;
			int xDestInd = (int)floor(loBoundX);
			double leftPart = xDestInd+1-loBoundX;
			double rightPart = upBoundX-(xDestInd+1);
			double xDestWeight = 1;
			double xDest1Weight = 0;

			if (rightPart>1e-9) {
				xDestWeight = leftPart/(rightPart+leftPart);
				xDest1Weight = rightPart/(rightPart+leftPart);
			}

			iD->scaledData[xDestInd+yDestInd*nDestX] +=
				pixBuf[x]*xDestWeight*yDestWeight;
			/* conditions on the weights to keep from overflowing our buffer */
			if (xDest1Weight) {
				assert(xDestInd<nDestX);
				iD->scaledData[xDestInd+1+yDestInd*nDestX] +=
					pixBuf[x]*xDest1Weight*yDestWeight;
			}
			if (yDest1Weight) {
				assert(yDestInd<nDestY);
				iD->scaledData[xDestInd+(yDestInd+1)*nDestX] +=
					pixBuf[x]*xDestWeight*yDest1Weight;
			}
			if (yDest1Weight && xDest1Weight) {
				assert(xDestInd<nDestX);
				assert(yDestInd<nDestY);
				iD->scaledData[xDestInd+1+(yDestInd+1)*nDestX] +=
					pixBuf[x]*xDest1Weight*yDest1Weight;
			}
		}
		iD->fpixel[1] += 1;
	}
}


#define _MINMAX(funName, operator)\
	double funName(double *data, long dataSize)\
	/* dataSize<=0 forbidden! */\
	{\
		double min=data[0], *dp=data;\
		int i;\
\
		for (i=0; i<dataSize; i++, dp++) {\
			if (min operator *dp) {\
				min = *dp;\
			}\
		}\
		return min;\
	}

_MINMAX(getMin, >)
_MINMAX(getMax, <)


void scaleValues(double *dp, long length, double maxVal)
/* scales the values at dp in place such that they are between 0 and maxVal */
{
	double minPixel = getMin(dp, length);
	double maxPixel = getMax(dp, length);
	double pixelScale; 
	int i;

	if (maxPixel-minPixel) {
		pixelScale = maxVal/(maxPixel-minPixel);
	} else {
		pixelScale = 0;
	}

	for (i=0; i<length; i++, dp++) {
		*dp = (*dp-minPixel)*pixelScale;
	}
}


void getHistogram(double *data, long dataSize, double *histogram,
	int histogramSize)
/* leaves a histogramSize-binned histogram of the normalized (0..1)-data
in histogram.

Data outside of [0..1[ is folded into the lowest or top bin.

The histogram is normalized to sum(val)==1.*/
{
	int index;
	long i;
	double sum=0;

	for (i=0; i<histogramSize; i++) {
		histogram[i] = 0;
	}

	for (i=0; i<dataSize; i++) {
		index = (int)floor(*data++*histogramSize*1-1e-10);
		index = (index<0) ? 0 :
			((index>histogramSize-1) ? histogramSize-1 : index);
		histogram[index]++;
	}

	for (i=0, sum=0; i<histogramSize; i++) {
		sum += histogram[i];
	}

	if (sum>0) {
		for (i=0; i<histogramSize; i++) {
			histogram[i] = histogram[i]/sum;
		}
	}
}


/* TODO: do a good gamma fudging; we'll probably want to do a linear
fit on a log-log plot of the histogram and do something with this;
but the details are tricky, and thus fudgeGamma is off for now. */

void fudgeGamma(imageDesc *iD)
/* tries to improve iD's scaledData by fuzzing with the gamma curve.  
scaledData must be normalized to 1 for this to work.

This is purely heuristic.  First, we want almost all power in histogram[0],
which means a black background.  If that's not true, we don't touch
the image.

Once, that's ascertained, we collect from white until we have 2.5% of the 
pixels.  That's our cut, and we'd like it to be at 50% intensity.  To
accomplish that, we process each scaled data point by p^gamma, where
gamma is defined by cut^gamma=0.5
*/
{
	double histogram[GAMMA_HIST_SIZE];
	int i;
	double *dp, intensitySum=0, gamma;

	getHistogram(iD->scaledData, iD->targetShape[1]*iD->targetShape[0],
		histogram, GAMMA_HIST_SIZE);

	if (histogram[0]+histogram[1]<0.8) { 
		/* not a black background, we'd make a mess of this */
		return;
	}

	for (i=GAMMA_HIST_SIZE-1; i>1; i--) { /* i will be our, cut, >0 always. */
		intensitySum+=histogram[i];
		if (intensitySum>0.025) {
			break;
		}
	}

	gamma = log(0.5)/log((double)i/GAMMA_HIST_SIZE);

	for (i=0, dp=iD->scaledData; 
		i<iD->targetShape[0]*iD->targetShape[1]; 
		i++, dp++) {
		*dp = pow(*dp, gamma);
	}
}
	

void fudgeGammaBlindly(imageDesc *iD)
/* Brightens the image a bit by pushing all grey values through
a mild x^gamma.

gamma should really be determined from the image (see fudgeGamma),
but this needs more thought. */
{
	long i;
	double *dp;
	double gamma=1/1.1;

	for (i=0, dp=iD->scaledData; 
		i<iD->targetShape[0]*iD->targetShape[1]; 
		i++, dp++) {
		*dp = pow(*dp, gamma);
	}
}


void computePreview(imageDesc *iD) 
/* compresses iD's scaledData to a jpeg written to stdout.

It must already be byte-sized (i.e., values between 0 and 255, say
with scaleValues) */
{
	struct jpeg_compress_struct compressor;
	struct jpeg_error_mgr jpegErrorHandler;
	unsigned char row[iD->targetShape[0]];
	JSAMPROW rowPointer[1]={row};
	double *dp;
	int x, y;

	compressor.err = jpeg_std_error(&jpegErrorHandler);
	jpeg_create_compress(&compressor);
	jpeg_stdio_dest(&compressor, stdout);
	compressor.image_width = iD->targetShape[0];
	compressor.image_height = iD->targetShape[1];
	compressor.input_components = 1;
	compressor.in_color_space = JCS_GRAYSCALE;
	jpeg_set_defaults(&compressor);
	jpeg_set_quality(&compressor, 95, TRUE);
	jpeg_start_compress(&compressor, TRUE);

	dp = iD->scaledData;
	for (y=0; y<iD->targetShape[1]; y++) {
		for (x=0; x<iD->targetShape[0]; x++) {
			row[x] = (int)floor(*dp++*255);
		}
		jpeg_write_scanlines(&compressor, rowPointer, 1);
	}
	jpeg_finish_compress(&compressor);
}


void usage(void)
{
	fprintf(stderr, "Usage: %s <fits-name> [<target width>]\n", 
		progName);
	exit(1);
}

	
int main(int argc, char **argv)
{
	char *inputFName;
	int targetWidth=DEFAULT_TARGETWIDTH;
	imageDesc *iD;

	nice(10); /* Hack: this should really be done by the calling program */
	progName = *argv++;
	if (!*argv) {
		usage();
	}
	inputFName = *argv++;
	if (*argv) {
		if (1!=sscanf(*argv++, "%d", &targetWidth)) {
			usage();
		}
	}
	iD = openFits(inputFName);
	computeScale(iD, targetWidth);
	doScale(iD);
	scaleValues(iD->scaledData, iD->targetShape[1]*iD->targetShape[0], 1);
	/*fudgeGamma(iD);*/
	fudgeGammaBlindly(iD);
	computePreview(iD);
	return 0;
}

