#### docker run
```
docker run -dt                                  \
  -p 9000:9000 -p 9001:9001                     \
  -v $HOME/minio/data:/mnt/data          \
  -v $HOME/minio/config.env:/etc/config.env         \
  -e "MINIO_CONFIG_ENV_FILE=/etc/config.env"    \
  --name "minio_local"                          \
  minio/minio server --console-address ":9001"
```
#### Config `$HOME/minio/config.env`
```
# MINIO_ROOT_USER and MINIO_ROOT_PASSWORD sets the root account for the MinIO server.
# This user has unrestricted permissions to perform S3 and administrative API operations on any resource in the deployment.
# Omit to use the default values 'minioadmin:minioadmin'.
# MinIO recommends setting non-default values as a best practice, regardless of environment

MINIO_ROOT_USER=myminioadmin
MINIO_ROOT_PASSWORD=<MinIO root 비밀번호>

# MINIO_VOLUMES sets the storage volume or path to use for the MinIO server.

MINIO_VOLUMES="/mnt/data"

# MINIO_OPTS sets any additional commandline options to pass to the MinIO server.
# For example, `--console-address :9001` sets the MinIO Console listen port
MINIO_OPTS="--console-address :9001"
```
#### Access Web admin
- `http:127.0.0.1:9000`

#### Create Access Key
- Access Key : `<앱 액세스 키 — .env 의 AWS_ACCESS_KEY_ID>`
- Secret Key : `<앱 시크릿 키 — .env 의 AWS_SECRET_ACCESS_KEY>`

#### Create Bucket
- Bucket Name : `test`

#### Test Code
```python
import boto3
from botocore.client import Config

# MinIO 서버 설정
minio_url = 'http://localhost:9000'  # MinIO 서버 주소
access_key = 'your-access-key'
secret_key = 'your-secret-key'
bucket_name = 'your-bucket-name'
file_path = 'path/to/your/file.txt'
object_name = 'file.txt'  # MinIO에 저장될 파일 이름

# S3 클라이언트 생성
s3 = boto3.client('s3',
                  endpoint_url=minio_url,
                  aws_access_key_id=access_key,
                  aws_secret_access_key=secret_key,
                  config=Config(signature_version='s3v4'))

# 파일 업로드
try:
    s3.upload_file(file_path, bucket_name, object_name)
    print(f"File '{file_path}' uploaded to '{bucket_name}/{object_name}' successfully.")
except Exception as e:
    print(f"Error uploading file: {e}")

```