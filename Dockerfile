# Dockerfile - VERSI 3 (Hanya untuk menjalankan kode, bukan build)

FROM public.ecr.aws/lambda/python:3.11

# Menyalin folder 'package' yang akan dibuat oleh GitHub Actions
COPY ./package ${LAMBDA_TASK_ROOT}/

# Atur handler untuk menunjuk ke file di dalam 'package'
CMD [ "package/gupf_brain_aws.handler" ]
