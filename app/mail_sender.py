"""
Mail Sender Module
- SMTP를 통한 HTML 이메일 발송
- Gmail / 사내 SMTP 모두 지원
- 파일 첨부 및 본문 삽입 이미지(CID) 지원
- UTF-8 한글 파일명 지원
"""
import smtplib
import logging
from os.path import basename
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.application import MIMEApplication
from email.mime.image import MIMEImage
from email.utils import COMMASPACE, formatdate, formataddr
from email.header import Header

log = logging.getLogger(__name__)


def send_mail(host, port, sender, sender_name, receivers, subject, content,
              files=None, cc=None, content_type='html',
              use_tls=False, username=None, password=None,
              inline_images=None):
    """
    SMTP를 통해 이메일을 발송합니다.

    Args:
        host (str): SMTP 서버 주소 (예: 'smtp.gmail.com')
        port (int): SMTP 포트 (Gmail: 587)
        sender (str): 발신자 이메일 주소
        sender_name (str): 발신자 표시 이름
        receivers (list): 수신자 이메일 주소 목록
        subject (str): 이메일 제목
        content (str): 이메일 본문 (HTML 또는 plain text)
        files (list, optional): 첨부파일 목록 (경로 또는 (파일명, 바이트) 튜플)
        cc (list, optional): 참조 이메일 주소 목록
        content_type (str): 본문 타입 ('html' 또는 'plain')
        use_tls (bool): TLS 사용 여부 (Gmail은 True)
        username (str, optional): SMTP 인증 사용자명
        password (str, optional): SMTP 인증 비밀번호
        inline_images (list, optional): 본문 삽입용 이미지 목록 [(cid, content), ...]

    Returns:
        tuple: (success: bool, message: str)
    """
    files = files or []
    cc = cc or []
    inline_images = inline_images or []

    try:
        msg = MIMEMultipart('mixed')
        msg['Subject'] = subject
        msg['From'] = formataddr((str(Header(sender_name, 'utf-8')), sender))
        msg['To'] = COMMASPACE.join(receivers)
        msg['Cc'] = COMMASPACE.join(cc)
        msg['Date'] = formatdate(localtime=True)
        
        # 본문과 인라인 이미지를 묶어줄 related 파트 구성
        msg_related = MIMEMultipart('related')
        msg_related.attach(MIMEText(content, content_type, 'utf-8'))

        # 본문 삽입용 이미지 처리 (CID)
        for cid, img_content in inline_images:
            try:
                img = MIMEImage(img_content)
                img.add_header('Content-ID', f'<{cid}>')
                img.add_header('Content-Disposition', 'inline', filename=cid)
                msg_related.attach(img)
            except Exception as e:
                log.warning(f"Inline image attachment failed for CID {cid}: {e}")

        # 완성된 본문+인라인이미지 그룹을 메인 메세지에 부착
        msg.attach(msg_related)

        # 파일 첨부
        for entry in files:
            try:
                if isinstance(entry, tuple):
                    fn, file_content = entry
                else:
                    fn = basename(entry)
                    with open(entry, "rb") as fil:
                        file_content = fil.read()
                
                part = MIMEApplication(file_content, Name=fn)
                part.add_header('Content-Disposition', 'attachment',
                                filename=('utf-8', '', fn))
                msg.attach(part)
            except Exception as e:
                log.warning(f"Attachment failed for {entry}: {e}")
                continue

        # SMTP 전송
        all_recipients = receivers + cc
        s = smtplib.SMTP(host, port)
        s.ehlo()

        if use_tls:
            s.starttls()
            s.ehlo()

        if username and password:
            s.login(username, password)

        s.sendmail(sender, all_recipients, msg.as_string())
        s.quit()

        log.info(f"Email sent successfully: subject='{subject}', to={receivers}")
        return True, 'OK'

    except Exception as e:
        log.error(f"Email send failed: {e}")
        return False, str(e)

def get_emails_from_tags(tag_names, manual_emails, db_session, ut_tag_model):
    """
    태그 이름 목록과 수동 입력 이메일 문자열에서 중복없는 이메일 리스트를 추출합니다.
    """
    emails = []
    if tag_names:
        for tag_name in tag_names:
            tag = db_session.query(ut_tag_model).filter_by(tag=tag_name).first()
            if tag and tag.value1:
                emails.extend(tag.value1.split(','))
    if manual_emails:
        emails.extend([e.strip() for e in manual_emails.split(',')])
    
    return list(set(filter(None, emails)))

def get_attachments_from_s3(ut_files, s3_file_manager_class):
    """
    첨부파일 목록 객체에서 S3를 통해 메일에 첨부할 실제 파일 데이터를 가져옵니다.
    """
    files = []
    if ut_files:
        s3_fm = s3_file_manager_class()
        for f in ut_files:
            try:
                file_content = s3_fm.get_file(f.file)
                files.append((f.file_name, file_content))
            except Exception as e:
                log.error(f"Failed to get file from S3: {f.file}, {e}")
    return files

def convert_md_to_html(md_content, kroki_url):
    """
    Markdown 문서를 HTML로 변환합니다. (Mermaid 다이어그램 인라인 CID 이미지 변환 포함)
    """
    import markdown
    import re
    import zlib
    import base64
    import requests

    inline_images = []
    mermaid_counter = 0

    def mermaid_replacer(match):
        nonlocal mermaid_counter
        code = match.group(1).strip()
        try:
            zlib_compressed = zlib.compress(code.encode('utf-8'), level=9)
            encoded = base64.urlsafe_b64encode(zlib_compressed).decode('utf-8')
            img_resp = requests.get(f"{kroki_url}/mermaid/png/{encoded}", timeout=10)
            if img_resp.status_code == 200:
                mermaid_counter += 1
                cid = f"mermaid_{mermaid_counter}"
                inline_images.append((cid, img_resp.content))
                return f'<img src="cid:{cid}" style="max-width:100%; border:1px solid #eee; margin:10px 0;">'
            else:
                log.error(f"Kroki fetch failed: {img_resp.status_code}")
                return f"<pre>{code}</pre>"
        except Exception as e:
            log.error(f"Mermaid conversion failed: {e}")
            return match.group(0)

    # Convert S3 images to inline CID
    s3_image_counter = [0]
    
    def s3_md_image_replacer(match):
        full_match = match.group(0)
        prefix = match.group(1) # ![alt](
        file_path = match.group(2)
        try:
            from app.file_manager.s3.filemanager import S3FileManager
            s3_fm = S3FileManager()
            file_content = s3_fm.get_file(file_path)
            s3_image_counter[0] += 1
            ext = file_path.split('.')[-1].lower() if '.' in file_path else 'png'
            cid = f"s3img_{s3_image_counter[0]}.{ext}"
            inline_images.append((cid, file_content))
            return f"{prefix}cid:{cid}"
        except Exception as e:
            log.error(f"S3 MD Image inline conversion failed: {file_path}, {e}")
            return full_match

    def s3_html_image_replacer(match):
        matched_str = match.group(0)
        file_path = match.group(1)
        try:
            from app.file_manager.s3.filemanager import S3FileManager
            s3_fm = S3FileManager()
            file_content = s3_fm.get_file(file_path)
            s3_image_counter[0] += 1
            ext = file_path.split('.')[-1].lower() if '.' in file_path else 'png'
            cid = f"s3img_{s3_image_counter[0]}.{ext}"
            inline_images.append((cid, file_content))
            return f'src="cid:{cid}"'
        except Exception as e:
            log.error(f"S3 HTML Image inline conversion failed: {file_path}, {e}")
            return matched_str

    md_content = md_content or ''
    # Replace markdown image URLs ![...](/common/download/...)
    md_content = re.sub(r'(!\[[^\]]*\]\()/common/download/([^)\s]+)', s3_md_image_replacer, md_content)
    # Replace HTML image src src="/common/download/..."
    md_content = re.sub(r'src=["\']/common/download/([^"\'\s]+)["\']', s3_html_image_replacer, md_content)

    md_content = re.sub(r'(?m)^\s*```mermaid\s*\n(.*?)\n\s*```', mermaid_replacer, md_content, flags=re.DOTALL)

    html_content = markdown.markdown(
        md_content,
        extensions=['fenced_code', 'tables', 'codehilite', 'toc', 'nl2br']
    )

    styled_html = f'''<div style="font-family: 'Malgun Gothic','맑은 고딕',sans-serif; font-size: 14px; line-height: 1.6; color: #333;">
<style>
table {{ border-collapse: collapse; margin: 10px 0; width: 100%; max-width: 100%; table-layout: fixed; }}
th, td {{ border: 1px solid #999999; padding: 8px; text-align: left; word-break: break-all; overflow-wrap: break-word; }}
th {{ background-color: #555555; color: #ffffff; }}
pre {{ background: #f6f8fa; padding: 12px; border-radius: 6px; border: 1px solid #d0d7de; overflow-x: auto; }}
code {{ background: #f0f0f0; padding: 2px 5px; border-radius: 3px; font-size: 13px; }}
pre code {{ background: none; padding: 0; }}
blockquote {{ border-left: 4px solid #dfe2e5; padding: 0 15px; color: #6a737d; margin: 10px 0; }}
h1, h2, h3 {{ border-bottom: 1px solid #eaecef; padding-bottom: 5px; }}
</style>
{html_content}</div>'''

    from premailer import transform
    return transform(styled_html), inline_images

