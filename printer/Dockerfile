FROM nodered/node-red:3.0.2
RUN npm install node-red-contrib-pythonshell

USER root
RUN apk add py3-pip zlib zlib-dev jpeg-dev libpng-dev freetype-dev python3-dev gcc musl-dev
RUN pip install python-barcode==0.15.1 brother-ql==0.9.4 pillow==6.2.2 qrcode==7.4.2 
 