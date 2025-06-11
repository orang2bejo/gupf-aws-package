# Dockerfile - VERSI 2 (Lambda-Compatible)

# Gunakan image dasar resmi dari AWS Lambda untuk Python 3.12
# Image ini menjamin semua library sistem (seperti GLIBC) akan cocok.
FROM public.ecr.aws/lambda/python:3.12

# Atur direktori kerja di dalam container
WORKDIR ${LAMBDA_TASK_ROOT}

# Salin file requirements.txt ke dalam container
COPY requirements.txt .

# Instal semua dependensi ke dalam sebuah folder bernama 'package'
# Ini adalah cara standar untuk mem-package dependensi untuk Lambda
RUN pip install -r requirements.txt --target ./package

# Salin file kode utama kita ke dalam folder 'package' juga
COPY gupf_brain_aws.py ./package/

# CMD ini tidak wajib untuk proses build, tapi ini adalah praktik yang baik
CMD [ "gupf_brain_aws.handler" ]
