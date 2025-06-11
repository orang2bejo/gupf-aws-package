# Dockerfile - FINAL VERSION FOR GITHUB ACTIONS BUILD

# Gunakan image dasar resmi dari AWS Lambda untuk Python 3.12
# Ini menjamin kompatibilitas lingkungan (GLIBC).
FROM public.ecr.aws/lambda/python:3.12

# Atur direktori kerja di dalam container Docker.
WORKDIR ${LAMBDA_TASK_ROOT}

# Salin file daftar dependensi ke dalam container.
COPY requirements.txt .

# Instal semua dependensi dari requirements.txt ke dalam folder bernama 'package'.
# Ini adalah langkah KUNCI untuk mengumpulkan semua library.
RUN pip install -r requirements.txt --target ./package

# Salin file kode utama Anda ke dalam folder 'package' yang sama.
# GANTI NAMA FILE DI BAWAH INI JIKA PERLU!
COPY gupf_brain_aws.py ./package/

# CMD tidak dieksekusi selama build, jadi ini opsional.
CMD [ "gupf_brain_aws.handler" ]
