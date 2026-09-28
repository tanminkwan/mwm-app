import boto3
from botocore.client import Config
import os
from app.common import singleton
from app import app


@singleton
class S3Client:

    def __init__(self):
        
        print(f"AWS_URL : {app.config['AWS_URL']}")
        print(f"AWS_ACCESS_KEY_ID : {app.config['AWS_ACCESS_KEY_ID']}")
        print(f"BUCKET_NAME : {app.config['BUCKET_NAME']}")
        print(f"BUCKET_PREFIX : {app.config['BUCKET_PREFIX']}")

        # S3 클라이언트 생성
        self.s3 = boto3.client('s3',
                        endpoint_url=app.config['AWS_URL'],
                        aws_access_key_id=app.config['AWS_ACCESS_KEY_ID'],
                        aws_secret_access_key=app.config['AWS_SECRET_ACCESS_KEY'],
                        config=Config(signature_version='s3v4'))
        self.bucket_name = app.config['BUCKET_NAME']
        self.prefix = app.config['BUCKET_PREFIX']

    def download_file(self, object_name: str, download_path: str) -> int:
        # 파일 다운로드
        try:
            file_path = os.path.join(self.prefix, object_name)
            print(f"File '{self.bucket_name}/{file_path}' downloading to '{download_path}'.")
            self.s3.download_file(self.bucket_name, file_path, download_path)
            print(f"File '{self.bucket_name}/{file_path}' downloaded to '{download_path}' successfully.")
            return 1
        except Exception as e:
            print(f"Error downloading file: {e}")
            return 0

    def get_file(self, object_name: str) -> str:
        file_path = os.path.join(self.prefix, object_name)
        response = self.s3.get_object(Bucket=self.bucket_name, Key=file_path)
        body = response['Body'].read()
        return body

    def upload_file(self, file_path: str, object_name: str = None) -> bool:
        # 파일 업로드
        if object_name is None:
            object_name = os.path.basename(file_path)

        try:
            file_path = os.path.join(self.prefix, object_name)
            self.s3.upload_file(file_path, self.bucket_name, file_path)
            print(f"File '{file_path}' uploaded to '{file_path}' successfully.")
            return True
        except Exception as e:
            print(f"Error uploading file: {e}")
            return False

    def list_files(self) -> list:
        # 버킷 내 파일 목록 조회
        try:
            response = self.s3.list_objects_v2(Bucket=self.bucket_name)
            files = [item['Key'] for item in response.get('Contents', [])]
            return files
        except Exception as e:
            print(f"Error listing files: {e}")
            return []

    def delete_file(self, object_name: str) -> bool:
        # 파일 삭제
        try:
            file_path = os.path.join(self.prefix, object_name)
            self.s3.delete_object(Bucket=self.bucket_name, Key=file_path)
            print(f"File '{object_name}' deleted successfully.")
            return True
        except Exception as e:
            print(f"Error deleting file: {e}")
            return False

    def generate_presigned_url(self, object_name: str, expiration: int = 3600, operation: str = 'get_object') -> str:
        # Pre-signed URL 생성
        try:
            file_path = os.path.join(self.prefix, object_name)
            url = self.s3.generate_presigned_url(
                operation,
                Params={'Bucket': self.bucket_name, 'Key': file_path},
                ExpiresIn=expiration
            )
            print(f"Generated pre-signed URL: {url}")
            return url
        except Exception as e:
            print(f"Error generating pre-signed URL: {e}")
            return ""
    """
    generate_presigned_url operation='put_object' 인 경우 js sample

    // 업로드할 파일 선택
    const uploadFile = async (file, presignedUrl) => {
        try {
            // 파일 업로드
            const response = await fetch(presignedUrl, {
                method: "PUT",
                body: file
            });

            if (response.ok) {
                console.log("File uploaded successfully.");
            } else {
                console.error(`Upload failed. Status: ${response.status}, Response: ${await response.text()}`);
            }
        } catch (error) {
            console.error("Error uploading file:", error);
        }
    };

    // HTML File Input 이벤트 리스너
    document.getElementById("fileInput").addEventListener("change", async (event) => {
        const file = event.target.files[0];
        if (!file) {
            console.log("No file selected.");
            return;
        }

        // Pre-signed URL (Python 코드로 생성된 URL을 사용)
        const presignedUrl = "https://your-minio-server/your-bucket-name/example_upload.txt?AWSAccessKeyId=...";

        console.log(`Uploading file: ${file.name}`);
        await uploadFile(file, presignedUrl);
    });
    """