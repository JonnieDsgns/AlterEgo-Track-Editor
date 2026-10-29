"""Bounded BC1/2/3/4/5 and RGBA preview decoder; PNG output uses standard zlib.

BC7 remains explicitly unsupported when Pillow is absent. Native source bytes
are always retained; these pixels are a preview, never a replacement writer.
"""
import struct
import zlib
import numpy as np


class PreviewImage:
    def __init__(self,pixels):
        self.pixels=pixels.astype(np.uint8)
        self.size=(self.pixels.shape[1],self.pixels.shape[0])

    def __array__(self,dtype=None,copy=None):
        return self.pixels.astype(dtype,copy=bool(copy)) if dtype is not None else self.pixels.copy() if copy else self.pixels

    def convert(self,mode):
        if mode!='RGBA':raise ValueError('Preview conversion supports RGBA only')
        return self

    def thumbnail(self,size):
        w,h=self.size;scale=min(1,size[0]/w,size[1]/h)
        nw,nh=max(1,int(w*scale)),max(1,int(h*scale))
        self.pixels=self.pixels[np.arange(nh)*h//nh][:,np.arange(nw)*w//nw]
        self.size=(nw,nh)

    def save(self,output,format='PNG'):
        def chunk(kind,data):
            return struct.pack('>I',len(data))+kind+data+struct.pack('>I',zlib.crc32(kind+data)&0xffffffff)
        w,h=self.size
        rows=b''.join(b'\0'+row.tobytes() for row in self.pixels)
        output.write(b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('>2I5B',w,h,8,6,0,0,0))+chunk(b'IDAT',zlib.compress(rows))+chunk(b'IEND',b''))


def alpha(block):
    a=block[:,0].astype(np.int32);b=block[:,1].astype(np.int32)
    palette=np.empty((len(block),8),dtype=np.int32);palette[:,0]=a;palette[:,1]=b
    high=a>b
    for i in range(2,8):
        seven=((8-i)*a+(i-1)*b)//7
        five=((6-i)*a+(i-1)*b)//5 if i<6 else np.full_like(a,0 if i==6 else 255)
        palette[:,i]=np.where(high,seven,five)
    bits=np.zeros(len(block),dtype=np.uint64)
    for i in range(6):bits|=block[:,2+i].astype(np.uint64)<<(8*i)
    idx=((bits[:,None]>>(3*np.arange(16,dtype=np.uint64)))&7).astype(np.int32)
    return palette[np.arange(len(block))[:,None],idx]


def decode_image(raw,width,height,native_format,normal=False):
    if not 0<width<=4096 or not 0<height<=4096 or width*height>4*1024*1024:
        raise ValueError('Texture dimensions exceed decode budget')
    if native_format==15:
        if len(raw)<width*height*4:raise ValueError('Truncated RGBA preview')
        return PreviewImage(np.frombuffer(raw[:width*height*4],dtype=np.uint8).reshape(height,width,4))
    kind={52:1,54:1,55:3,57:3,62:2,63:4,65:5}.get(native_format)
    if not kind:raise ValueError(f'Preview decoder does not support format {native_format}; original preserved')
    bw,bh=(width+3)//4,(height+3)//4;stride=8 if kind in (1,4) else 16
    if len(raw)<bw*bh*stride:raise ValueError('Truncated BC preview')
    blocks=np.frombuffer(raw[:bw*bh*stride],dtype=np.uint8).reshape(-1,stride)
    out=np.full((len(blocks),16,4),255,dtype=np.int32)
    if kind in (1,2,3):
        colour=blocks[:,-8:]
        c0=colour[:,0].astype(np.int32)|(colour[:,1].astype(np.int32)<<8)
        c1=colour[:,2].astype(np.int32)|(colour[:,3].astype(np.int32)<<8)
        def rgb(c):
            r=(c>>11)&31;g=(c>>5)&63;b=c&31
            return np.stack(((r<<3)|(r>>2),(g<<2)|(g>>4),(b<<3)|(b>>2)),axis=1)
        a,b=rgb(c0),rgb(c1);p=np.zeros((len(blocks),4,4),dtype=np.int32);p[:,:,:]=255
        p[:,0,:3]=a;p[:,1,:3]=b
        opaque=(c0>c1)|(kind!=1)
        p[:,2,:3]=np.where(opaque[:,None],(2*a+b)//3,(a+b)//2)
        p[:,3,:3]=np.where(opaque[:,None],(a+2*b)//3,0)
        p[:,3,3]=np.where(opaque,255,0)
        bits=sum(colour[:,4+i].astype(np.uint32)<<(8*i) for i in range(4))
        idx=((bits[:,None]>>(2*np.arange(16,dtype=np.uint32)))&3).astype(np.int32)
        out=p[np.arange(len(blocks))[:,None],idx]
        if kind==2:
            vals=blocks[:,:8];out[:,:,3]=np.stack((vals&15,vals>>4),axis=2).reshape(-1,16)*17
        elif kind==3:out[:,:,3]=alpha(blocks[:,:8])
    else:
        out[:,:,0]=alpha(blocks[:,:8]);out[:,:,1]=out[:,:,0];out[:,:,2]=out[:,:,0]
        if kind==5:
            out[:,:,1]=alpha(blocks[:,8:])
            if normal:
                x=out[:,:,0]/127.5-1;y=out[:,:,1]/127.5-1
                out[:,:,2]=np.rint((np.sqrt(np.maximum(0,1-x*x-y*y))*.5+.5)*255)
    pixels=out.reshape(bh,bw,4,4,4).transpose(0,2,1,3,4).reshape(bh*4,bw*4,4)[:height,:width]
    return PreviewImage(pixels)


class ImageFacade:
    @staticmethod
    def fromarray(pixels):return PreviewImage(pixels)

    @staticmethod
    def open(stream):
        raw=stream.read()
        if raw[:8]!=b'\x89PNG\r\n\x1a\n':raise ValueError('Expected preview PNG')
        p=8;compressed=bytearray();width=height=None
        while p+12<=len(raw):
            length=struct.unpack_from('>I',raw,p)[0];kind=raw[p+4:p+8];data=raw[p+8:p+8+length]
            if p+12+length>len(raw) or zlib.crc32(kind+data)&0xffffffff!=struct.unpack_from('>I',raw,p+8+length)[0]:
                raise ValueError('Corrupt preview PNG')
            if kind==b'IHDR':
                width,height,depth,colour,compression,filtering,interlace=struct.unpack('>2I5B',data)
                if depth!=8 or colour!=6 or compression or filtering or interlace or width*height>4*1024*1024:
                    raise ValueError('Unsupported preview PNG layout')
            elif kind==b'IDAT':compressed.extend(data)
            elif kind==b'IEND':break
            p+=12+length
        if not width or not height:raise ValueError('Missing PNG dimensions')
        size=(width*4+1)*height;decoder=zlib.decompressobj();decoded=decoder.decompress(bytes(compressed),size+1)
        if len(decoded)!=size or not decoder.eof:raise ValueError('PNG decoded length mismatch')
        output=np.zeros((height,width*4),dtype=np.uint8);stride=width*4
        for y in range(height):
            method=decoded[y*(stride+1)];row=decoded[y*(stride+1)+1:(y+1)*(stride+1)]
            if method==0:output[y]=np.frombuffer(row,dtype=np.uint8);continue
            for x,value in enumerate(row):
                a=int(output[y,x-4]) if x>=4 else 0;b=int(output[y-1,x]) if y else 0
                c=int(output[y-1,x-4]) if y and x>=4 else 0
                if method==1:predictor=a
                elif method==2:predictor=b
                elif method==3:predictor=(a+b)//2
                elif method==4:
                    estimate=a+b-c;distances=[abs(estimate-a),abs(estimate-b),abs(estimate-c)]
                    predictor=(a,b,c)[distances.index(min(distances))]
                else:raise ValueError('Unsupported PNG filter')
                output[y,x]=(value+predictor)&255
        return PreviewImage(output.reshape(height,width,4))
