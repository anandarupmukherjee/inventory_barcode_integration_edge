import qrcode
import json, os
import zlib
import base64
import math
from PIL import Image
Image.MAX_IMAGE_PIXELS = 933120000
import math
# Create a QR code object with a larger size and higher error correction

class QRPrint():
    def __init__(self):
        self.splitLim = 1200

    def get_concat_v(self, im1, im2):
        dst = Image.new('RGB', (im1.width, im1.height + im2.height))
        dst.paste(im1, (0, 0))
        dst.paste(im2, (0, im1.height))
        return dst

    def makeLabelAAS(self, data, fileName):
        # Define the data to be encoded in the QR code
        dataDump = json.dumps(data)
        compressed_data = zlib.compress(dataDump.encode())
        newstr = str(compressed_data)
        base64_encoded = base64.b64encode(compressed_data)
        #uncompressed = zlib.decompress(newstr).decode()
        newstr =base64_encoded
        length = len(newstr)

        if length > self.splitLim:
            num = math.ceil(length/self.splitLim)
            print(num)
            for i in range(num):
                inst = i*self.splitLim
                inen = (i+1)*self.splitLim
                if inen > length:
                    inen = length
                datTry = newstr[inst:inen]
                print(len(datTry))
                qr = qrcode.QRCode(version=3, box_size=100, border=10, error_correction=qrcode.constants.ERROR_CORRECT_H)
                qr.add_data(datTry)
                qr.make(fit=True)
                img = qr.make_image(fill_color="black", back_color="white")
                imgNew = "qr_temp" + str(i) + ".png"
                img.save("qr_temp" + str(i) + ".png")
                img = ""
                
                if i > 0:
                    im1 = Image.open(imgNew)
                    im2 = Image.open(imgOld)
                    self.get_concat_v(im1, im2).save(fileName)
                imgOld = imgNew
        else:
            qr = qrcode.QRCode(version=3, box_size=100, border=10, error_correction=qrcode.constants.ERROR_CORRECT_H)
            qr.add_data(newstr)
            qr.make(fit=True)
            img = qr.make_image(fill_color="black", back_color="white")
            img.save(fileName)


    def makeLabelQR(self, data, fileName):
        # make regular qr imiage base don id data
        try:
            qr = qrcode.QRCode(version=3, box_size=100, border=10, error_correction=qrcode.constants.ERROR_CORRECT_H)
            qr.add_data(data)
            qr.make(fit=True)
            img = qr.make_image(fill_color="black", back_color="white")
            if ".png" in fileName:
                imgFile = fileName
            else:
                imgFile = fileName + ".png"
            img.save(imgFile)
        except:
            print("Erro making QR code")