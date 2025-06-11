# Dockerfile - VERSI 2 (Lambda Packaging)

# Tahap 1: Build - Menginstal dependensi
# Menggunakan image resmi dari AWS yang cocok dengan lingkungan Lambda
FROM public.ecr.aws/lambda/python:3.11 as builder

# Salin file requirements.txt terlebih dahulu
COPY requirements.txt ./

# Install semua library ke dalam sebuah direktori bernama /var/task/package
RUN pip install --upgrade pip && \
    pip install -r requirements.txt -t /var/task/package

# Tahap 2: Final - Menggabungkan kode kita dengan library yang sudah diinstal
FROM public.ecr.aws/lambda/python:3.11

# Salin kode aplikasi Anda ke dalam direktori package juga
COPY gupf_brain_aws.py /var/task/package/

# Salin seluruh folder package yang berisi library DAN kode kita dari tahap 'builder'
COPY --from=builder /var/task/package /var/task/package

# Atur handler Lambda. Perhatikan, kita sekarang menggunakan sub-folder 'package'
CMD [ "package/gupf_brain_aws.handler" ]
