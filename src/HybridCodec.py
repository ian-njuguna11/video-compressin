## @class HybridCodec 
# Module designed for encoding and decoding YUV videos using the intra and inter frame methods
# That is, considering adjacent pixels in the same frame and encoding their errors in the first video frame
# And using inter frame encoding in all the remaining frames
# That is, assembling blocks from each frame and encoding the differences to the most similar block
# @author Tiago Melo 89005
# @author João Nogueira 89262

import numpy as np
import math
from Golomb import *
from Bitstream import *

class HybridCodec:

    ## Initialization function
    # @param[in] filename Path of the file to read
    # @param[in] encoded A flag used to indicate if the video in the given path was encoded by this same class
    # @param[in] limitFrames Optional parameter to limit the number of frames to considered
    # Initializing and setting up some useful parameters and flags
    def __init__(self, filename, encoded=False, limitFrames=None):

        self.vid = filename

        self.encoding='utf-8'

        # Array of arrays containing each frame's components
        self.frameY=[]
        self.frameV=[]
        self.frameU=[]

        self.encoded=False
        self.quantizationStep=None
        self.colorSpace=None

        np.seterr(over='ignore')

        #calls read video on initialization
        if not encoded:
            self.read_video()
        else:
            self.encoded=True
            self.read_encoded_video(limitFrames=limitFrames)
    
    ## read_video function
    # Reads YUV video information from file, storing all its data in our structures, calculating different components lengths and shapes
    def read_video(self):
        f=open(self.vid,"rb")
        c=1

        for line in f:

            # Processing header
            if c==1:
                line=line.decode(self.encoding)
                self.header=line.strip()
                self.handleHeader()
            
            # Rest of the video
            if c>=2:

                frameY=f.read(self.yLength)
                frameU=f.read(self.uLength)
                frameV=f.read(self.vLength)

                y=np.frombuffer(frameY, dtype=np.uint8)
                u=np.frombuffer(frameU, dtype=np.uint8)
                v=np.frombuffer(frameV, dtype=np.uint8)

                y=y.reshape(self.shape)
                u=u.reshape(self.other_shape)
                v=v.reshape(self.other_shape)

                self.frameY+=[y]
                self.frameU+=[u]
                self.frameV+=[v]

            c+=1

        self.TotalFrames=len(self.frameY)

        f.close()

    ## read_encoded_video function
    # @param[in] limitFrames Optional parameter to limit the number of frames to be decoded
    # Reads video information (encoded by this class) from file
    # Starts by decoding and interpreting the header, followed by decoding of all the pixel blocks errors and recreating the original pixel based on the vector indicating the most similar block used for calculating the differences
    def read_encoded_video(self,limitFrames=None):
        bs=BitStream(self.vid,'READ')
        headerlen=bs.read_n_bits(8)

        chars=[]
        for i in range(0,headerlen*8):
            chars.append(str(bs._readbit()))

        res=''.join(chars)
        self.header=self.decode_binary_string(res)

        #handle header
        self.handleHeader()
        
        g=Golomb(self.golombParam)
        bitsResto=int(math.log(self.golombParam,2))

        if limitFrames==None:
            l=self.TotalFrames
        else:
            l=limitFrames
        #
        self.frameY=[None]*l
        self.frameU=[None]*l
        self.frameV=[None]*l
        #
        for frame in range(0,l):
            print('decoding frame',frame)

            y=np.zeros(shape=self.shape,dtype=np.uint8)
            u=np.zeros(shape=self.other_shape,dtype=np.uint8)
            v=np.zeros(shape=self.other_shape,dtype=np.uint8)

            if frame==0:
            
                for line in range(0, self.height):
                    for column in range(0,self.width):
                        pixel=self.decodeWithBitstream(3,bs,g,bitsResto)

                        a=self.getYUVPixel(frame,line,column-1, resized=False)
                        c=self.getYUVPixel(frame,line-1,column-1, resized=False)
                        b=self.getYUVPixel(frame,line-1,column, resized=False)
                        x=self.predict(a,c,b)
                        pixel=self.sum(x,pixel)

                        pixel=tuple(pixel)

                        l,c=self.adjustCoord(line,column)

                        y[line,column]=pixel[0]                        
                        u[l,c]=pixel[1]
                        v[l,c]=pixel[2]
                        #
                        self.frameY[frame]=y
                        self.frameU[frame]=u
                        self.frameV[frame]=v

            else:
                blocks=self.getBlocks(frame-1,self.block_size)
                bl,bc=blocks.shape
                for i1 in range(0,bl):
                    for i2 in range(0,bc):
                        vetor=self.decodeWithBitstream(2,bs,g,bitsResto)
                        v1,v2=vetor
                        #print(vetor)
                        bestBlock=blocks[v1,v2]
                        for l in range(0,self.block_size):
                            for c in range(0,self.block_size):
                                pixelErro=self.decodeWithBitstream(3,bs,g,bitsResto)
                                referencePixel=bestBlock[l,c]
                                pixel=self.sum(pixelErro,referencePixel)

                                line,column=self.block_size*i1+l,self.block_size*i2+c           
                                li,co=self.adjustCoord(line,column)

                                y[line,column]=pixel[0]                        
                                u[li,co]=pixel[1]
                                v[li,co]=pixel[2]



                self.frameY[frame]=y
                self.frameU[frame]=u
                self.frameV[frame]=v
        #
        bs.close()


    ## handleHeader function
    # Interpreting the header of the file, containing width, height, frames per second and color space, assigning them to class variables
    # This header can also contain other parameters added while encoding, such as the parameter for Golomb,the quantization steps used for lossy coding, the block size and search area for inter-frame methods
    def handleHeader(self):
        print(self.header)
        fields=self.header.split(" ")

        for field in fields:
            c=field[0]
            if c=='W':
                self.width=int(field[1:])
            elif c=='H':
                self.height=int(field[1:])
            elif c=='F':
                self.fps=int(field[1:3])
            elif c=='C':
                self.colorSpace=int(field[1:])
            elif c=='G':
                self.golombParam=int(field[-1:])
                self.encoded=True
            elif c=='z':
                self.TotalFrames=int(field[1:])
            elif c=='q':
                qlist=field[1:]
                qsteps=qlist.split(':')
                self.quantizationStep=[int(qsteps[0]),int(qsteps[1]),int(qsteps[2])]
            elif c=='b':
                self.block_size=int(field[1:])
            elif c=='s':
                self.search_area=int(field[1:])
                    
        self.computeShape()
        print('width=',self.width, 'height=',self.height, self.fps, self.colorSpace, self.frameLength)
        if self.encoded:
            print('g=',self.golombParam, 'totalframes=',self.TotalFrames)
        if self.quantizationStep!=None:
            print('q=',self.quantizationStep)

    ## adjustCoord function
    # @param[in] line Line where the pixel is located
    # @param[in] column Column where the pixel is located
    # @param[out] line Adjusted line number
    # @param[out] column Adjusted column number
    # Adjusts given line and column considering the different array shapes in different color spaces
    # Useful when assigning new values to a certain pixel position
    def adjustCoord(self,line,column):
        if self.colorSpace=='4:2:2':
            c=math.floor((column/2))
            return line,c
        elif self.colorSpace=='4:2:0':
            c=math.floor((column/2))
            l=math.floor((line/2))
            return l,c
        else:
            return line,column


    ## computeShape function
    # Calculating array shapes for YUV components based on the color space
    def computeShape(self):      
        if self.colorSpace==444:
            self.colorSpace='4:4:4'
            self.frameLength=int(self.width*self.height*3)
            self.yLength=self.uLength=self.vLength=int(self.frameLength/3)
            self.shape = (int(self.height), self.width)
            self.other_shape = (int(self.height), self.width)

        elif self.colorSpace==422:
            self.colorSpace='4:2:2'
            self.frameLength=int(self.width*self.height*2)
            self.yLength=int(self.frameLength/2)
            self.vLength=self.uLength=int(self.frameLength/4)
            self.shape = (int(self.height), self.width)
            self.other_shape = (int(self.height), int(self.width/2))
        else: 
            self.colorSpace='4:2:0'
            self.frameLength=int(self.width*self.height*3/2)
            self.yLength=int(self.frameLength*(2/3))
            self.uLength=self.vLength=int(self.frameLength*(1/6))
            self.shape = (int(self.height), self.width)
            self.other_shape = (int(self.height/2), int(self.width/2))


    ## getYUVPixel function
    # @param[in] frame Number of the frame from which to read the pixel from
    # @param[in] line Line in which the pixel is located
    # @param[in] column Column in which the pixel is located
    # @param[in] resized A flag used to indicate if the arrays have been resized or not
    # @param[out] p The pixel tuple in YUV format
    # Returns 0,0,0 for non existent pixels, useful for the Codecs
    # Adjust line and column numbers based on the color space (and array shapes)
    def getYUVPixel(self, frame, line, column, resized):
        yf=self.frameY[frame]
        uf=self.frameU[frame]
        vf=self.frameV[frame]

        if resized==False:
            if self.colorSpace=='4:2:2':
                c=math.floor((column/2))
                if line<0 or column<0 or c<0:
                    return 0,0,0
                p=yf[line,column], uf[line,c], vf[line,c]
            elif self.colorSpace=='4:2:0':
                c=math.floor((column/2))
                l=math.floor((line/2))
                if line<0 or column<0 or c<0 or l<0:
                    return 0,0,0
                p=yf[line,column], uf[l,c], vf[l,c]
            else:
                if line<0 or column<0:
                    return 0,0,0
                p=yf[line,column], uf[line,column], vf[line,column]
        else:
            if line<0 or column<0:
                return 0,0,0
            p=yf[line,column], uf[line,column], vf[line,column]
        return p

    ## updateYUVPixel function
    # @param[in] compNumb Number of the pixel component to be changed (0=Y,1=U,2=V)
    # @param[in] frame Number of the frame where the pixel is located
    # @param[in] line Line in which the pixel is located
    # @param[in] column Column in which the pixel is located
    # @param[in] value New value of the pixel's component
    # Used for avoiding error propagation in lossy coding
    def updateYUVPixel(self,compNumb,frame,line,column,value):
        l,c=self.adjustCoord(line,column)
        if compNumb==0:
            rf=self.frameY[frame]
            rf.setflags(write=1)
            rf[line,column]=value
        elif compNumb==1:
            rf=self.frameU[frame]
            rf.setflags(write=1)
            rf[l,c]=value
        else:
            rf=self.frameV[frame]
            rf.setflags(write=1)
            rf[l,c]=value

        
    ## predict function
    # @param[in] a Adjacent pixel in position (line,col-1)
    # @param[in] c  Adjacent pixel in position (line-1,col-1)
    # @param[in] b  Adjacent pixel in position (line-1,col)
    # @param[out] ret Most similar pixel
    # The returned pixel is calculated using the JPEG-LS non-linear predictor formula  
    def predict(self,a,c,b):
        y=[int(a[0]),int(c[0]),int(b[0])]
        u=[int(a[1]),int(c[1]),int(b[1])]
        v=[int(a[2]),int(c[2]),int(b[2])]

        l=[y]+[u]+[v]
        ret=[]
        for component in l:
            if component[1]>=max(component[0],component[2]):
                x=min(component[0],component[2])
            elif component[1]<=min(component[0],component[2]):
                x=max(component[0],component[2])
            else:
                x=component[0]+component[2]-component[1]
            ret.append(x)
        return ret

    ## diff function
    # @param[in] p First pixel
    # @param[in] x Second pixel
    # @param[out] r Pixel result of the difference between the two pixels
    # Calculates the result pixel by calculating the difference between each yuv component  
    def diff(self,p,x):
        ey=int(p[0])-int(x[0])
        eu=int(p[1])-int(x[1])
        ev=int(p[2])-int(x[2])

        return(ey,eu,ev)

    ## sum function
    # @param[in] p First pixel
    # @param[in] x Second pixel
    # @param[out] r Pixel result of the sum between the two pixels
    # Calculates the result pixel by calculating the sum between each yuv component 
    def sum(self,p,x):
        ey=p[0]+x[0]
        eu=p[1]+x[1]
        ev=p[2]+x[2]

        return(ey,eu,ev)

    ## printPixels function
    # Function for printing pixels, useful during development
    def printPixels(self):
        l=self.TotalFrames
        l=1
        h=self.height
        #h=20
        w=self.width
        #w=20
        for frame in range(0,l):
            #print('processing frame',frame)
            for line in range(0,h):
                for column in range(0,w):
                    if line==0 and w-10<=column<w:
                        p=self.getYUVPixel(frame,line,column, resized=False)
                        print(p, end=';')
                #print('')

    ## decode_binary_string function
    # @param[in] s String
    # @param[out] r Decoded binary string
    # Additional function to decode binary strings
    def decode_binary_string(self,s):
        return ''.join(chr(int(s[i*8:i*8+8],2)) for i in range(len(s)//8))

    ## getFrames function
    # @param[out] frames The data structures with all the frames of each component
    # Useful to check data integrity
    def getFrames(self):
        return self.frameY, self.frameU,self.frameV

    ## getBlock function
    # @param[in] firstPixel Initial pixel, where the block begins
    # @param[in] length Block length (squares)
    # @param[in] frame Frame number
    # @param[out] yuv Block containing all the pixel's components
    # Constructs a pixel block based on the initial pixel, frame and block length
    def getBlock(self,firstPixel,length,frame):
        yuv=np.zeros(shape=(length,length,3), dtype=np.uint8)
        l,c=firstPixel
        fl,fc=l+length,c+length
        c1,c2=0,0
        for line in range(l,fl):
            for col in range(c,fc):
                p=self.getYUVPixel(frame,line,col,resized=False)
                #print(p)
                yuv[c1,c2]=p
                c2+=1
            c1+=1
            c2=0
        

        return yuv

    ## getBlocks function
    # @param[in] frame Frame number
    # @param[in] block_size Block length (squares)
    # @param[out] blocks Matrix of blocks of given frame
    # Constructs a matrix of pixel blocks of given frame
    def getBlocks(self,frame,block_size):
        firstPixel=[0,0]
        p1=int(self.height/block_size)
        p2=int(self.width/block_size)
        blocks=np.zeros(shape=(p1,p2), dtype=object)
        c1,c2=0,0
        while True:
            if firstPixel[0]==self.height:
                break
            yuv=self.getBlock(firstPixel,block_size,frame)
            blocks[c1,c2]=yuv
            firstPixel[1]=firstPixel[1]+block_size
            c2+=1
            if firstPixel[1]==self.width:
                firstPixel[1]=0
                c2=0
                firstPixel[0]=firstPixel[0]+block_size
                c1+=1
        return blocks

    ## encode_video function
    # @param[in] filename Path of file to write with the encoded video information
    # @param[in] golombparam Golomb's parameter M (factor)
    # @param[in] block_size Block's length
    # @param[in] search_area Search area for inter frame method
    # @param[in] q Optional parameter for specifying each components quantization steps for lossy coding
    # @param[in] limitFrames Optional parameter for limiting number of frames to encode
    # Starts by encoding the header, passing additional parameters such as the Golomb factor
    # Uses intra-coding method in the first frame, as described in the IntraCodec class
    # Uses inter-coding for all the remaining frames
    # That is by constructing a matrix of blocks for every frame, finding the most similar block of the previous frame to each one, and encoding that block of errors and the vector related to the most similar block's position
    def encode_video(self, filename, golombparam,block_size, search_area, q=None, limitFrames=None):
        if limitFrames==None:
            l=self.TotalFrames
        else:
            l=limitFrames

        g=Golomb(golombparam)

        bs=BitStream(filename,'WRITE')

        header='ENCODED '+self.header+' Golomb'+str(golombparam)+' z'+str(self.TotalFrames)+' b'+str(block_size)+' s'+str(search_area)
        if q!=None:
            header+=' q'+str(q[0])+':'+str(q[1])+':'+str(q[2])
            self.quantizationStep=q
        headerlen=len(header)
        bs.write_n_bits(headerlen,8)
        bs.writeTxt(header)

        for frame in range(0,l):
            print('encoding frame',frame)
            if frame==0:
                for line in range(0,self.height):
                    for column in range(0,self.width):
                        p=self.getYUVPixel(frame,line,column, resized=False)

                        a=self.getYUVPixel(frame,line,column-1, resized=False)
                        c=self.getYUVPixel(frame,line-1,column-1, resized=False)
                        b=self.getYUVPixel(frame,line-1,column, resized=False)
                        x=self.predict(a,c,b)
                        erro=self.diff(p,x)

                        self.encodeWithBitstream(erro,bs,g,pixel=p,frame=frame,line=line,column=column)
            else:
                blocks=self.getBlocks(frame,block_size)
                oldBlocks=self.getBlocks(frame-1,block_size)

                bl,bc=blocks.shape
                for l in range(0,bl):
                    for c in range(0,bc):
                        position=l,c
                        block=blocks[l,c]
                        bestblock,vetor=self.findBestBlock(block,oldBlocks,search_area,position)
                        #write vetor
                        self.encodeWithBitstream(vetor,bs,g)
                        #write block
                        nl,nc=bestblock.shape[0], bestblock.shape[1]
                        for a in range(0,nl):
                            for b in range(0,nc):
                                self.encodeWithBitstream(bestblock[a,b],bs,g)

            
        bs.close()

    ## blockDif function
    # @param[in] block Given block
    # @param[in] oldBlocks Blocks from previous frame
    # @param[in] search_area Search area for inter frame
    # @param[in] position Given block's position in the blocks matrix
    # @param[out] lastDif Most similar block
    # @param[out] vetor Vector with the coordinates corresponding to the most similar block's position
    # Calculates the 'best', most similar block (of the previous frame) to the given block
    def findBestBlock(self,block,oldBlocks,search_area,position):
        vetor=None
        flag=True
        lastDif=None
        ol,oc=position
        bl,bc=oldBlocks.shape
        #print(bl,bc)
        for l in range(0,bl):
            for c in range(0,bc):
                if abs(ol-l)<=search_area and abs(oc-c)<=search_area:
                    candidateBlock=oldBlocks[l,c]
                    dif=self.blockDif(block,candidateBlock)
                    if flag or self.lessError(dif,lastDif):
                        flag=False
                        lastDif=dif
                        vetor=[l,c]
        return lastDif,vetor


    ## blockDif function
    # @param[in] block First block
    # @param[in] candidateBlock Second block
    # @param[out] dif Result error block
    # Calculates differences between two blocks of pixels
    def blockDif(self,block,candidateBlock):
        length=block.shape[0]
        dif=np.zeros(shape=(length,length,3), dtype=np.int8)
        for l in range(0,length):
            for c in range(0,length):
                dif[l,c]=self.diff(block[l,c],candidateBlock[l,c])
        return dif

    ## lessError function
    # @param[in] dif First block
    # @param[in] lastDif Second block
    # @param[out] bool Returns flag indicating if the First block is better than the second one
    # Calculates which error block has the least differences, based on the sum of the absolute value of all errors
    def lessError(self,dif,lastDif):
        s1=0
        s2=0
        length=dif.shape[0]
        for l in range(0,length):
            for c in range(0,length):
                p1=dif[l,c]
                s1+=abs(int(p1[0]))+abs(int(p1[1]))+abs(int(p1[2]))
                p2=lastDif[l,c]
                s2+=abs(int(p2[0]))+abs(int(p2[1]))+abs(int(p2[2]))

        #if s1==0 or s2==0:

        if s1<s2:
            return True
        else:
            return False

    ## encodeWithBitStream function
    # @param[in] value Value to be encoded
    # @param[in] bs Bitstream class object
    # @param[in] g Golomb class object
    # @param[in] pixel Current pixel values being encoded, used for lossy coding
    # @param[in] frame Frame where the pixel being encoded is located
    # @param[in] line Line where the pixel being encoded is located
    # @param[in] column Column where the pixel being encoded is located
    # Switches the value to be encoded to positive, writing a 1 or 0 according to the original value
    # If using lossy coding functionality, divides color component by quantization step and updates pixel value
    # Proceeds to write the encoded value by Golomb with the Bitstream
    def encodeWithBitstream(self, value,bs,g, pixel=None, frame=None, line=None, column=None):
        for i in range(0,len(value)):
            if value[i]<0:
                n=value[i]*-1
                bs.writebits(1,1)
            else:
                bs.writebits(0,1)
                n=value[i]
            
            if self.quantizationStep!=None and self.quantizationStep[i]!=0:
                newValue=pixel[i]+(n)
                n=math.floor(n/self.quantizationStep[i])
                
                #TODO
                if line!=0 and column!=0:
                    self.updateYUVPixel(i,frame,line,column,newValue)
            n=g.encode(n)
            bs.writebits(int(n,2),len(n))

    ## decodeWithBitStream function
    # @param[in] len Number of values to read
    # @param[in] bs Bitstream class object
    # @param[in] g Golomb class object
    # @param[in] bitsResto Number of bits of the remainder = log(factor,2)
    # @param[out] pixel Decoded value
    # Starts by reading one bit 0 or 1, determing if number was negative
    # Reads the bits from the Bitstream and decodes them with Golomb
    # Multiplies by quantization step if using lossy coding
    def decodeWithBitstream(self, len,bs,g,bitsResto):
        pixel=[]
        for i in range(0,len):
            ay=bs.read_n_bits(1)
            seq=''
            while True:
                r=str(bs.read_n_bits(1))
                seq+=r
                if r=='0':
                    break
            seq+=str(bs.readbits(bitsResto))
            comp=g.decode(seq)
            if ay==1:
                comp=comp*-1
            if self.quantizationStep!=None and self.quantizationStep[i]!=0:
                comp=comp*self.quantizationStep[i]
            pixel.append(comp)
        return pixel

    ## verifyData function
    # @param[in] video Class containing video for comparison
    # @param[in] numberoframes Limits number of frames to check
    # Compares data between two videos
    def verifyData(self,video,numberoframes):
        m1,m2,m3=self.getFrames()
        m4,m5,m6=video.getFrames()
        for i in range(0,numberoframes):
            if (np.array_equal(m1[i],m4[i])):
                print('Y-',i,'correct')
        for i in range(0,numberoframes):
            if (np.array_equal(m2[i],m5[i])):
                print('U-',i,'correct')
        for i in range(0,numberoframes):
            if (np.array_equal(m3[i],m6[i])):
                print('V-',i,'correct')


