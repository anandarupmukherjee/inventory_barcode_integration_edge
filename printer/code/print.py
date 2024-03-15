import barcode
from barcode import EAN13, Code128
from barcode.writer import ImageWriter
from io import BytesIO
import brother_ql
from brother_ql.raster import BrotherQLRaster
from brother_ql.backends.helpers import send
import os
import time
import datetime
from PIL import Image, ImageDraw, ImageFont
import sys
import json
import usb.core
import usb.util
import QRPrint
import math
import qrcode
import base64
import zlib


def find_brother_ql_printer():
    # Search for the Brother QL printer by its vendor and product ID
    dev = usb.core.find(idVendor=0x04f9, idProduct=0x209b)

    if dev is None:
        raise ValueError("Brother QL printer not found!")

    return dev

def sendToPrinter(path):
    ## Printer Set-up
    
    # ~ dev = find_brother_ql_printer()
    # ~ print(dev)
    
    
    PRINTER_IDENTIFIER = '/dev/usb/lp5'    
    printer = BrotherQLRaster('QL-700')


    print_data = brother_ql.brother_ql_create.convert(printer, [path], '62', dither=True)
    
    print(f'Print Data')
    print(path)
    try:
        send(print_data, PRINTER_IDENTIFIER)
    except:
        print("error printing")


def createPNG(ID, output_path):
    bc_type = 'Code128' 
    options = dict(module_height=10, quiet_zone=5,font_size=5,text_distance=1,background='white',foreground='black',center_text=False, format='PNG')    
    BC = barcode.get_barcode_class(bc_type)
    BC(str(ID), writer=ImageWriter()).save(output_path, options)

def createQRAAS(ID, output_path):
    qrclass = QRPrint.QRPrint()
    qrclass.makeLabelAAS(ID, output_path + ".png")


def createQR(ID, output_path):
    qrclass = QRPrint.QRPrint()
    qrclass.makeLabelQR(ID, output_path + ".png")



def create_formatted_label(barcode_list, text_list, QR_list, output_path):
    print("Creating label image...")
    
    try:
        # Try to Load the barcode image and find label size
        barcode_images = []
        barcode_width = 500
        labelQR_width = 500
        barcode_height = 0
        QR_height = 0
        QR_images = []
        if len(QR_list) > 0:
            for item in QR_list:
                QR_images.append(Image.open(f"{item['imgPath']}.png"))
            labelQR_width = max([image.width for image in QR_images])  
            QR_height = max([image.height for image in QR_images])   
        
        if len(barcode_list) > 0:
            for item in barcode_list:
                barcode_images.append(Image.open(f"{item['imgPath']}.png"))
            barcode_width = max([image.width for image in barcode_images])  
            barcode_height = max([image.height for image in barcode_images])   

        # Assuming the example label dimensions based on the barcode size and the provided sample
        label_width = max(barcode_width, labelQR_width)
        if labelQR_width > barcode_width and barcode_images:
            label_width = labelQR_width
            scale = int(labelQR_width/barcode_width)
            for i in range(len(barcode_images)):
                label_width = labelQR_width
                widthNew = barcode_images[i].width*scale
                hightNew = barcode_images[i].height*scale
                imageResize = barcode_images[i].resize((widthNew, hightNew))
                barcode_images[i] = imageResize
            barcode_height = max([image.height for image in barcode_images]) 


        print(f'label width: {labelQR_width} px')
        font_size =  int(label_width/10) 
        print(f'font size: {font_size} px')
        label_height = int((barcode_height * len(barcode_list)) + (QR_height * len(QR_list)) + font_size*2*len(text_list))
        print(f'label (w x h): {label_width} x {label_height} px')

        # Create a new image with white background
        label_image = Image.new('RGB', (label_width, label_height), 'white')
        
        # Paste the barcode onto the new image, centered on x and stacked on y Upper left is(0,0)
        baseline_y = label_height
        if len(barcode_images) > 0:
            for i in range(len(barcode_images)):
                barcode_x = int((label_width - barcode_images[i].width) // 2)
                barcode_y = baseline_y - barcode_images[i].height
                baseline_y = barcode_y
                label_image.paste(barcode_images[i], (barcode_x, barcode_y))
        if len(QR_images) > 0:
            for i in range(len(QR_images)):
                barcode_x = int((label_width - QR_images[i].width))
                barcode_y = baseline_y - QR_images[i].height
                baseline_y = barcode_y
                label_image.paste(QR_images[i], (barcode_x, barcode_y))

        # Set up the font for the text
        font_path = "/code/fonts/DejaVuSans-Bold.ttf"  # Adjust this path to your font file
        
        key_font = ImageFont.truetype(font_path, font_size)
        value_font = ImageFont.truetype(font_path, int(font_size * 0.5))
        
        # Initialize ImageDraw to add text to the image
        draw = ImageDraw.Draw(label_image)

        # Add text to the image
        if len(text_list) > 0:
            for i in range(len(text_list)):
                text_key_position = (10, int(font_size*i+1.5))
                text_value_position = (10, int(font_size*i*1.5 + font_size*1.2))
                draw.text(text_key_position, f"{text_list[i]['labelKey']}", fill="black", font=key_font)
                draw.text(text_value_position, f"{text_list[i]['labelValue']}", fill="black", font=value_font)


        # Save the new image
        label_image.save(output_path)
        print( "Label image created successfully.")
    except Exception as e:
        print( str(e))

# To use the function, you would call it with the barcode image path and the information you want on the label:
# create_formatted_label(barcode_path, date_packed, customer, product, pallet_no, output_path)




def main():
    if len(sys.argv) < 2:
        print("Usage: python3 myscript.py payload_data")
        sys.exit(1)
    try:
        payload_data = sys.argv[1]
        payload_dict = json.loads(payload_data)
        print("Received payload data:")
        print(f'Payload: {payload_dict}')
        labelItems = payload_dict['labelItems']
        print(labelItems)
        barcode_list = []
        text_list = []
        QR_list =[]
        for item in labelItems:
            print (item)
            if item['labelType'] == 'barcode':
                image_location = f'/code/barcodes/barcode-{item["labelKey"]}-{item["labelValue"]}'
                createPNG(item['labelValue'],image_location)
                item['imgPath'] = image_location
                barcode_list.append(item)
                print("barcode saved")
            elif item['labelType'] == 'text':
                text_list.append(item)
                print("text  item saved")
            elif item['labelType'] == 'QR':
                image_location = f'/code/QR/QR-{item["labelKey"]}'
                createQR(item['labelValue'], image_location)
                item['imgPath'] = image_location
                QR_list.append(item)
                print("AAS QR saved")
            elif item['labelType'] == 'QRAAS':
                print("ASS triggered")
                image_location = f'/code/QR/QR-{item["labelKey"]}'
                createQRAAS(item['labelValue'], image_location)
                item['imgPath'] = image_location
                QR_list.append(item)
                print("QR saved")


        create_formatted_label(barcode_list, text_list, QR_list, '/code/output/label.png')
        # Print current directory
        current_directory = os.getcwd()
        print("Current Directory:", current_directory)

        # List all files in the directory
        files = os.listdir(current_directory)
        print("Files in the Directory:")
        for file in files:
            print(file)
        sendToPrinter('/code/output/label.png')
        try:
            if payload_dict['qty']:
                for i in range(int(payload_dict['qty'])):
                    sendToPrinter('/code/output/label.png')
                    time.sleep(0.5)
            else:
                sendToPrinter('/code/output/label.png')
                print("done")
        except:
            print("Error printing but label made")


    except json.JSONDecodeError as e:
        print("Error parsing JSON:", e)
    #sendToPrinter('./printer/code/output/label.png')


if __name__ == "__main__":
    main()
