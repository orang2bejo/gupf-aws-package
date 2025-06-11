# Dockerfile FINAL v2 - Dirancang untuk Stabilitas Maksimal (Python 3.10, Tanpa Rust)

# --- TAHAP 1: BUILDER ---
# Menggunakan Python 3.10 yang terbukti sangat stabil untuk C-extensions.
FROM python:3.10-slim AS builder

# HANYA butuh alat build C/C++, TIDAK PERLU Rust.
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Atur direktori kerja.
WORKDIR /app

# Salin requirements.txt.
COPY requirements.txt .

# Upgrade pip adalah best practice untuk menghindari error aneh.
RUN pip install --upgrade pip

# Instal semua library. Build akan jauh lebih cepat dan stabil.
RUN pip install --target ./package -r requirements.txt


# --- TAHAP 2: FINAL ---
# Menggunakan base image AWS Lambda yang sesuai dengan versi Python kita.
FROM public.ecr.aws/lambda/python:3.10

# Tentukan direktori kerja Lambda.
WORKDIR /var/task

# Salin HANYA hasil build (folder 'package') dari tahap BUILDER.
COPY --from=builder /app/package .

# Salin kode fungsi Anda.
COPY gupf_brain_aws.py .

# Atur perintah yang akan dijalankan oleh Lambda.
CMD [ "gupf_brain_aws.handler" ]