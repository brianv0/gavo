/* This is a small generator for preview jpegs from fits input 
 *
 * We probably don't need to be fancy, so scaling is really simple minded.
 * Maybe some more work should go in there, but I guess reliable gamma
 * estimation would have the highest payoff.
 *
 */

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <errno.h>
#include <math.h>
#include <assert.h>

#include <fitsio.h>
#include <jpeglib.h>

#define DEFAULT_WIDTH 200
#define DEFAULT_GAMMA 1
#define LIMIT_BRIGHT 80  /* dimmest pixel still considered "bright" */

char *progName=NULL;


typedef struct imageDesc_s {
	int pixelType;
	long shape[2];
	float *data;
	double dataminGiven;
} imageDesc;

typedef struct byteImageDesc_s {
	long shape[2];
	unsigned char *data;
} byteImageDesc;


void fatalFitsError(int status)
{
	if (status==0) {  /* WTF?? */
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


void read1Dvalues(imageDesc *iD, fitsfile *fptr)
{
	int x, y;
	int dummy;
	int doFold;
	int status=0;
	long fpixel[2] = {1, 1};

	if (iD->shape[0]<1000) {
		/* Don't fold, extrude */
		iD->shape[1] = iD->shape[0]/10;
		doFold = 0;
	} else {
		/* Fold 'em */
		iD->shape[1] = 1;
		doFold = 1;
	}
	if (!(iD->data = malloc(iD->shape[0]*iD->shape[1]*sizeof(float)))) {
		fatalLibError("Allocating image data");
	}
	if (fits_read_pix(fptr, TFLOAT, fpixel, iD->shape[0],
		NULL, iD->data, &dummy, &status)) {
		fatalFitsError(status);
	}
	if (doFold) {
		/* We should do a factor analysis here... */
		int i;
		int newWidth = (int)floor(sqrt(iD->shape[0]))+1;
		int newHeight = iD->shape[0]/(newWidth-1);
		if (!(iD->data = realloc(iD->data, newWidth*newHeight*sizeof(float)))) {
			fatalLibError("Re-allocating image data");
		}
		for (i=iD->shape[0]; i<newWidth*newHeight; i++) {
			iD->data[i] = 0;
		}
		iD->shape[0] = newWidth;
		iD->shape[1] = newHeight;
	} else {
		for (y=1; y<iD->shape[1]; y++) {
			float *src=iD->data, *dest=iD->data+iD->shape[0]*y;
			for (x=0; x<iD->shape[0]; x++) {
				*dest++ = *src++;
			}
		}
	}
}


imageDesc *readFits(char *fName)
{
	int status=0;
	int naxis;
	fitsfile *fptr;
	imageDesc *iD=malloc(sizeof(imageDesc));
	char dummy[80];

	if (!iD) {
		fatalLibError("Allocating image descriptor");
	}
	if (fits_open_image(&fptr, fName, READONLY, &status) ||
		fits_get_img_param(fptr, 2, &(iD->pixelType), &naxis, 
			iD->shape, &status)) {
		fatalFitsError(status);
	}
	fits_read_key(fptr, TDOUBLE, "DATAMIN", &(iD->dataminGiven), dummy,
		&status);
	if (status) {
		iD->dataminGiven = -1;
	}
	status = 0;
	if (naxis==2) {
		long fpixel[2] = {1, 1};
		int dummy;
		if (!(iD->data = malloc(iD->shape[0]*iD->shape[1]*sizeof(float)))) {
			fatalLibError("Allocating image data");
		}
		if (fits_read_pix(fptr, TFLOAT, fpixel, iD->shape[0]*iD->shape[1],
			NULL, iD->data, &dummy, &status)) {
			fatalFitsError(status);
		}
	} else if (naxis==1) {
		read1Dvalues(iD, fptr);
	} else {
		fatalError("Can only work with naxis in {1,2}");
	}
	fits_close_file(fptr, &status);
	return iD;
}


void doPixelScale(imageDesc *img, int targetWidth)
/* q'n'd -- it's only a preview */
{
	float imageScale=targetWidth/(img->shape[0]+0.1);
	int targetHeight = (int)(img->shape[1]*imageScale);
	int x, y;
	float *targetData=img->data;

	if (img->shape[0]<=0 || img->shape[1]<=0) {
		fatalError("Empty image cannot be scaled.\n");
	}
	if (targetHeight>targetWidth) { /* don't make images too high */
		imageScale = targetWidth/(img->shape[1]+0.1);
		targetWidth = (int)(img->shape[0]*imageScale);
		targetHeight = (int)(img->shape[1]*imageScale);
	}
	if (imageScale>1) {  /* don't scale up */
		targetWidth=img->shape[0];
		targetHeight=img->shape[1];
		imageScale = 1;
	}
	targetWidth = targetWidth==0?1:targetWidth;
	targetHeight = targetHeight==0?1:targetHeight;
	for (y=0; y<targetHeight; y++) {
		for (x=0; x<targetWidth; x++) {
			*targetData++ = img->data[(int)(x/imageScale)+
				(int)(y/imageScale)*img->shape[0]];
		}
	}
	img->shape[0] = targetWidth;
	img->shape[1] = targetHeight;
}


void getScaling(float *data, size_t dataLength, double minHint,
	double *zeroOut, double *rangeOut)
{
	double minVal, maxVal;
	float *curVal;

	minVal = maxVal = data[0];
	for (curVal=data; curVal<data+dataLength; curVal++) {
		minVal = (minVal>*curVal?*curVal:minVal);
		maxVal = (maxVal>*curVal?maxVal:*curVal);
	}
	if (minHint>minVal) {
		minVal = minHint;
	}
	//fprintf(stderr, "%lf %lf\n", minVal, maxVal);
	*zeroOut = minVal;
	*rangeOut = (maxVal-minVal);
}

byteImageDesc *makeByteImage(int width, int height)
{
	byteImageDesc *im=malloc(sizeof(byteImageDesc));

	if (!im || !(im->data = malloc(width*height))) {
		return NULL;
	}
	im->shape[0] = width;
	im->shape[1] = height;
	return im;
}

int *getHisto(byteImageDesc *img)
{
	int *histo=malloc(256*sizeof(int));
	unsigned char *pixel, *end;

	if (!histo) {
		fatalLibError("Allocating histogram");
	}
	memset(histo, 0, 256*sizeof(int));
	end = img->data+img->shape[0]*img->shape[1];
	for (pixel=img->data; pixel<end; pixel++) {
		histo[*pixel]++;
	}
//	for (i=0; i<256;i++) {
//		fprintf(stderr, "%d, %d\n", i, histo[i]);
//	}
	return histo;
}

unsigned char *computePixelMap(int *histo, double breakPercent)
{
	unsigned char *pixelMap;
	double total, subtotal;
	int i, breakpoint;

	for (i=0, total=0; i<256; i++) {
		total += (double)histo[i];
	}
	/* walk from back till you've got breakPercent of the pixel values */
	for (subtotal=0, breakpoint=255; breakpoint>=0; breakpoint--) {
		subtotal += histo[breakpoint];
		if (subtotal*100/breakPercent>=total) {
			break;
		}
	}
	/* do nothing if breakpoint is in the "bright" part or if img is empty. */
	//fprintf(stderr, "%d %f %f\n", breakpoint, subtotal, total);
	if (breakpoint>LIMIT_BRIGHT || breakpoint==0) {
		return NULL;
	}
	/* Also do nothing if the more than a quarter of the image 
	 * 	would become "bright" */
	if (subtotal>total/4) {
		return NULL;
	}
	if (!(pixelMap = malloc(256))) {
		fatalLibError("Allocating pixel map");
	}
	/* generate ramp to LIMIT_BRIGHT for dark pixels with a steep gamma, ramp 
	 * from LIMIT_BRIGHT to 255 for bright pixels */
	for (i=0; i<breakpoint; i++) {
		pixelMap[i] = (int)floor(pow(i/(float)breakpoint, 3)*LIMIT_BRIGHT);
	}
	for (i=breakpoint; i<255; i++) {
		pixelMap[i] = (i-breakpoint)*(255-LIMIT_BRIGHT)/(255-breakpoint)+
			LIMIT_BRIGHT;
	}
	return pixelMap;
}

/* tries to ensure that at least some of the pixels are "bright". 
 *
 * img has to be an 8-bit greyscale image.
 * */
void brighten(byteImageDesc *img)
{
	int *histo=getHisto(img);
	unsigned char *map=computePixelMap(histo, 0.05);
	unsigned char *pixel;

	free(histo);
	if (map) {
		for (pixel=img->data; pixel<img->data+img->shape[0]*img->shape[1]; 
				pixel++) {
			*pixel = map[*pixel];
		}
		free(map);
	}
}
	
byteImageDesc *computePreview(imageDesc *original, int targetWidth, 
	double gamma)
{
	double zero, range;
	byteImageDesc *preview;
	unsigned char *previewVal;
	float *origVal, *origEnd;

	doPixelScale(original, targetWidth);
	if (!(preview=makeByteImage(original->shape[0], original->shape[1]))) {
		fatalLibError("Allocating preview");
	}
	origEnd = original->data+original->shape[0]*original->shape[1];
	getScaling(original->data, origEnd-original->data, original->dataminGiven,
		&zero, &range);
	for (origVal=original->data, previewVal=preview->data; 
			origVal<origEnd; origVal++) {
		*previewVal++ = (unsigned char)(pow(((*origVal-zero)/range), gamma)*255);
	}
	brighten(preview);
	return preview;
}
	

void writeJpeg(byteImageDesc *iD, int targetWidth)
{
	struct jpeg_compress_struct compressor;
	struct jpeg_error_mgr jpegErrorHandler;
	JSAMPROW rowPointers[iD->shape[1]];
	int i;

	compressor.err = jpeg_std_error(&jpegErrorHandler);
	jpeg_create_compress(&compressor);
	jpeg_stdio_dest(&compressor, stdout);
	compressor.image_width = iD->shape[0];
	compressor.image_height = iD->shape[1];
	compressor.input_components = 1;
	compressor.in_color_space = JCS_GRAYSCALE;
	jpeg_set_defaults(&compressor);
	jpeg_start_compress(&compressor, TRUE);
	for (i=0; i<iD->shape[1]; i++) {
		rowPointers[i] = iD->data+iD->shape[0]*i;
	}
	jpeg_write_scanlines(&compressor, rowPointers, iD->shape[1]);
	jpeg_finish_compress(&compressor);
}


void usage(void)
{
	fprintf(stderr, "Usage: %s <fits-name> [<target width> [<gamma>]]\n", 
		progName);
	exit(1);
}


int main(int argc, char **argv)
{
	char *inputFName;
	int targetWidth=DEFAULT_WIDTH;
	imageDesc *original; 
	byteImageDesc *preview;
	float gamma=DEFAULT_GAMMA;

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
	if (*argv) {
		if (1!=sscanf(*argv++, "%f", &gamma)) {
			usage();
		}
	}
	original = readFits(inputFName);
	preview = computePreview(original, targetWidth, gamma);
	writeJpeg(preview, targetWidth);
	return 0;
}
		

