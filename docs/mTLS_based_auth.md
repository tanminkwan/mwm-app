# Flask x509 클라이언트 인증서 인증 설계 문서

> 작성 기준: 도메인 미가입 Windows PC 환경, TPM 없음, 내부망 고정 IP 환경

---

## 1. 개요 및 목표

Flask 기반 웹 서버의 secret 영역에 x509 클라이언트 인증서 기반 mTLS(Mutual TLS) 인증을 적용한다.
사용자는 Windows PC에 개인 인증서를 설치하고, 브라우저로 접근 시 자동 인증이 이루어진다.

---

## 2. 전체 아키텍처

```
클라이언트 PC                   서버
─────────────────               ──────────────────────────────
1. 클라이언트에서 개인키 생성
   (개인키는 PC 밖으로 안 나감)

2. CSR 생성 및 서버 전송   →   3. CA가 CSR에 서명
                                   (공개키에만 서명, 개인키 모름)

4. 서명된 인증서 수신      ←   5. 인증서 반환

6. Windows 인증서 저장소 설치
   (Exportable = FALSE)

7. 브라우저로 HTTPS 접속   →   8. Nginx: mTLS 검증
                                   - 클라이언트 인증서 요구
                                   - CA 서명 검증
                                   - 인증서 정보 헤더로 Flask 전달

                               9. Flask: 추가 검증
                                   - SAN IP ↔ 실제 접속 IP 비교
```

---

## 3. 핵심 설계 결정 — SAN에 IP 등록 후 서버 관측 IP와 비교

### 3.1 왜 IP인가 (MAC/hostname 대비)

| 식별자 | 서버 획득 방법 | 위조 가능 여부 |
|---|---|---|
| MAC 주소 | 클라이언트가 헤더로 전송 | ❌ 위조 가능 (HTTP 헤더 조작) |
| hostname | 클라이언트가 헤더로 전송 | ❌ 위조 가능 (HTTP 헤더 조작) |
| **IP 주소** | **서버가 TCP 연결에서 직접 관측** | **✅ 조작 불가** |

IP는 클라이언트가 서버에 "알려주는" 값이 아니라, 서버가 TCP 연결 자체에서 직접 읽는 값이다.
클라이언트는 개입할 수 없다.

### 3.2 검증 흐름

```
인증서 발급 시
  SAN: IP = 192.168.1.100  ← 해당 PC의 고정 IP로 발급

접속 시 서버 검증
  서버가 TCP에서 관측한 IP = 192.168.1.100
  인증서 SAN IP            = 192.168.1.100
  → 일치 → 통과

탈취 후 다른 PC에서 시도
  서버가 TCP에서 관측한 IP = 192.168.1.200  ← 속일 수 없음
  인증서 SAN IP            = 192.168.1.100
  → 불일치 → 차단
```

### 3.3 IP 스푸핑 가능성

TCP/IP 스푸핑은 이론상 가능하지만 HTTPS 환경에서는 현실적으로 매우 어렵다.

```
HTTPS = TCP 기반 = 3-way handshake 필요

  SYN       → 서버
  SYN-ACK   ← 서버가 "진짜 IP"로 응답  ← 공격자가 수신 불가
  ACK       → 서버

→ TCP 연결 자체가 성립 안 됨
→ TLS handshake 시작 불가

실제 스푸핑 성공 조건:
  내부망 + ARP 스푸핑으로 패킷 가로채기
  + 라우터/스위치 수준 접근 권한 필요
  → 이미 네트워크 인프라를 장악한 수준의 공격
```

---

## 4. 브라우저 접속 절차 (사용자 경험)

### 4.1 클라이언트 PC에 필요한 것

```
필요한 것           딱 두 가지
──────────────────────────────────────────
1. 인증서 설치      Windows 인증서 저장소에 .cer 한 번 설치
2. 브라우저         Chrome / Edge  → 별도 설정 없음
                    Firefox        → 인증서 한 번 등록 필요

필요 없는 것
──────────────────────────────────────────
x  별도 클라이언트 프로그램
x  VPN
x  플러그인 / 확장 프로그램
x  로그인 화면
x  비밀번호
```

> 브라우저 mTLS는 TLS 스펙에 포함된 기본 기능이다.  
> 서버가 "인증서 보내줘" 요청하면 브라우저가 Windows 인증서 저장소를  
> 자동으로 조회하여 제시한다. 클라이언트 PC에 별도 코드 구현이 필요 없다.

### 4.2 접속 시 단계별 흐름

```
TLS Handshake (브라우저 자동 처리)
──────────────────────────────────────────────────────
① 브라우저가 https://domain.com 접속 요청

② Nginx → 브라우저: 서버 인증서 전송
   브라우저가 "진짜 서버" 여부 확인

③ Nginx → 브라우저: 클라이언트 인증서 요청

④ 브라우저가 Windows 인증서 저장소 자동 조회
   인증서 1개 → 자동 선택
   인증서 여러 개 → 사용자에게 선택 팝업

⑤ 브라우저 → Nginx: 클라이언트 인증서 전송
   (개인키는 전송 안 함, 서명값만 전송)

⑥ Nginx: CA 서명 검증
   "우리 CA가 발급한 인증서 맞다" 확인

요청 처리
──────────────────────────────────────────────────────
⑦ Nginx → Flask: 프록시 + X-SSL 헤더 전달
   X-SSL-Client-Verify, X-SSL-Client-DN, X-Real-IP

⑧ Flask: 인증서 SAN IP ↔ 실제 접속 IP 비교
   일치 → 통과 / 불일치 → 403 반환

⑨ Flask → 브라우저: 인증 성공, 페이지 응답
```

### 4.3 사용자 경험 요약

```
최초 1회 (관리자가 인증서 배포 후)
  관리자가 보내준 .cer 파일 더블클릭 → 설치 완료

이후 매번
  브라우저 주소창에 URL 입력 → 페이지 바로 열림

로그인 화면 없음, 비밀번호 입력 없음, 완전 자동
```

---

## 5. 구현

### 4.1 CA 및 인증서 생성

```bash
# Root CA 생성
openssl genrsa -out ca.key 4096
openssl req -x509 -new -nodes -key ca.key -sha256 -days 3650 \
  -subj "/CN=MyCompany-CA/O=MyCompany" -out ca.crt

# SAN 설정 파일 (san.cnf)
cat > san.cnf << EOF
[req]
req_extensions = v3_req
[v3_req]
subjectAltName = IP:192.168.1.100
EOF

# 클라이언트 개인키 + CSR 생성 (클라이언트 PC에서 실행)
openssl genrsa -out user1.key 2048
openssl req -new -key user1.key \
  -subj "/CN=user1/O=MyCompany" \
  -config san.cnf -out user1.csr

# CA 서명
openssl x509 -req -in user1.csr -CA ca.crt -CAkey ca.key \
  -CAcreateserial -extensions v3_req -extfile san.cnf \
  -out user1.crt -days 365 -sha256
```

### 4.2 클라이언트 PC에서 CSR 생성 (PowerShell)

개인키가 PC를 벗어나지 않도록 Windows 인증서 저장소에서 직접 생성한다.

```powershell
# client_enroll.ps1
$username = $env:USERNAME
$hostname = $env:COMPUTERNAME

# 유효한 IP 목록 추출 (APIPA, 루프백 제외)
$ipList = Get-NetIPAddress -AddressFamily IPv4 |
    Where-Object { $_.IPAddress -notlike '169.*' -and
                   $_.IPAddress -ne '127.0.0.1' } |
    Select-Object InterfaceAlias, IPAddress

# IP가 하나면 자동 등록, 여러 개면 선택
if ($ipList.Count -eq 1) {
    $ip = $ipList[0].IPAddress
    Write-Host "IP 자동 등록: $ip ($($ipList[0].InterfaceAlias))" -ForegroundColor Green

} else {
    Write-Host "=== 현재 PC의 IP 목록 ===" -ForegroundColor Cyan
    $ipList | Format-Table -AutoSize

    $ip = Read-Host "인증서에 등록할 IP를 입력하세요"

    try {
        [System.Net.IPAddress]::Parse($ip) | Out-Null
    } catch {
        Write-Host "올바른 IP 형식이 아닙니다: $ip" -ForegroundColor Red
        exit 1
    }

    # 목록에 없는 IP 입력 시 경고
    if ($ip -notin $ipList.IPAddress) {
        Write-Host "경고: 목록에 없는 IP입니다." -ForegroundColor Yellow
        $confirm = Read-Host "계속하시겠습니까? (Y/N)"
        if ($confirm -ne 'Y') { exit }
    }
}

Write-Host "등록 확정 IP: $ip" -ForegroundColor Green

$reqInf = @"
[NewRequest]
Subject = "CN=$username,O=MyCompany"
KeyLength = 2048
KeyAlgorithm = RSA
Exportable = FALSE          ; 내보내기 불가 설정
KeySpec = AT_KEYEXCHANGE
RequestType = PKCS10

[Extensions]
2.5.29.17 = "{text}"
_continue_ = "ipaddress=$ip&"
"@

$reqInf | Out-File "$env:TEMP\req.inf" -Encoding ASCII
certreq -new "$env:TEMP\req.inf" "$env:TEMP\user.csr"

# CSR을 등록 서버로 전송
$body = @{
    csr      = Get-Content "$env:TEMP\user.csr" -Raw
    username = $username
    hostname = $hostname
    ip       = $ip
} | ConvertTo-Json

$resp = Invoke-RestMethod `
    -Uri "https://yourserver.com/enroll" `
    -Method POST `
    -Body $body `
    -ContentType "application/json"

# 반환된 인증서를 개인키와 결합하여 설치
$resp.certificate | Out-File "$env:TEMP\user.cer" -Encoding ASCII
certreq -accept "$env:TEMP\user.cer"

Write-Host "인증서 설치 완료" -ForegroundColor Green
```

### 4.3 Nginx 설정 (mTLS)

```nginx
server {
    listen 443 ssl;
    server_name yourserver.com;

    # 서버 인증서
    ssl_certificate     /etc/ssl/server.crt;
    ssl_certificate_key /etc/ssl/server.key;

    # 클라이언트 인증서 검증
    ssl_client_certificate /etc/ssl/ca.crt;
    ssl_verify_client      on;
    ssl_verify_depth       2;

    location / {
        proxy_pass http://127.0.0.1:5000;

        # 실제 클라이언트 IP (TCP에서 직접 읽음)
        proxy_set_header X-Real-IP        $remote_addr;

        # 인증서 정보 Flask로 전달
        proxy_set_header X-SSL-Client-Cert    $ssl_client_cert;
        proxy_set_header X-SSL-Client-Verify  $ssl_client_verify;
        proxy_set_header X-SSL-Client-DN      $ssl_client_s_dn;
    }
}
```

### 4.4 Flask 검증 로직

```python
from flask import Flask, request, abort, g
from functools import wraps
from cryptography import x509
from cryptography.hazmat.backends import default_backend
import ipaddress

app = Flask(__name__)


def get_real_ip() -> str:
    """Nginx가 TCP에서 읽은 실제 클라이언트 IP"""
    ip = request.headers.get('X-Real-IP') or request.remote_addr
    # IPv6 매핑 주소 정규화
    if ip.startswith('::ffff:'):
        ip = ip[7:]
    return ip


def get_cert_san_ips(pem_cert: str) -> list[str]:
    """인증서 SAN에서 IP 목록 추출"""
    cert = x509.load_pem_x509_certificate(
        pem_cert.encode(), default_backend()
    )
    try:
        san = cert.extensions.get_extension_for_class(
            x509.SubjectAlternativeName
        )
        return [
            str(ip)
            for ip in san.value.get_values_for_type(x509.IPAddress)
        ]
    except x509.ExtensionNotFound:
        return []


def parse_dn_field(dn: str, field: str) -> str:
    for part in dn.split(','):
        part = part.strip()
        if part.startswith(f'{field}='):
            return part[len(field) + 1:]
    return ''


def require_client_cert(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        # 1. TLS 인증서 검증 결과 확인 (Nginx가 설정)
        verify = request.headers.get('X-SSL-Client-Verify')
        if verify != 'SUCCESS':
            abort(403, "유효한 클라이언트 인증서가 없습니다.")

        # 2. 인증서 SAN IP ↔ 실제 접속 IP 비교 (핵심)
        pem     = request.headers.get('X-SSL-Client-Cert', '')
        san_ips = get_cert_san_ips(pem)
        real_ip = get_real_ip()

        if real_ip not in san_ips:
            abort(403, f"IP 불일치: 접속={real_ip}, 인증서={san_ips}")

        # 3. DN에서 사용자 정보 파싱
        dn = request.headers.get('X-SSL-Client-DN', '')
        g.user = {
            'cn':    parse_dn_field(dn, 'CN'),
            'email': parse_dn_field(dn, 'emailAddress'),
            'ip':    real_ip,
        }

        return f(*args, **kwargs)
    return decorated


@app.route('/secret')
@require_client_cert
def secret():
    return f"인증 성공 — {g.user['cn']} @ {g.user['ip']}"


@app.route('/health')
def health():
    return 'OK'
```

---

## 6. 보안 강도 평가

### 5.1 ID/PW 대비

| 공격 방법 | ID/PW | x509 + IP 검증 |
|---|---|---|
| 브루트포스 | ❌ 취약 | ✅ 해당 없음 |
| 피싱 | ❌ 입력 즉시 탈취 | ✅ 브라우저 자동 제시, 사용자 개입 없음 |
| 패스워드 재사용 | ❌ 타 사이트 유출로 뚫림 | ✅ 해당 없음 |
| 키로거 | ❌ 타이핑 탈취 | ✅ 키보드 입력 없음 |
| 인증정보 DB 유출 | ❌ 해시 크래킹 가능 | ✅ 서버에 개인키 없음 |
| 탈취 후 다른 PC 사용 | ❌ 어디서든 가능 | ✅ IP 불일치로 차단 |

### 5.2 위협별 방어 수준

| 위협 | 방어 수준 | 비고 |
|---|---|---|
| 외부 공격자 | ✅ 완벽 차단 | 인증서 없으면 접근 불가 |
| 피싱 | ✅ 완벽 차단 | 개인키는 네트워크로 안 나감 |
| 인증서 탈취 후 다른 PC 사용 | ✅ IP 불일치로 차단 | SAN IP 검증 |
| TCP/IP 스푸핑 | ⚠️ 이론상 가능 | HTTPS에서 현실적으로 매우 어려움 |
| 작정한 내부자 (ARP 스푸핑 등) | ⚠️ 어렵지만 가능 | 네트워크 인프라 장악 수준 필요 |

### 5.3 TPM 없는 환경의 한계와 보완

```
Exportable = FALSE
  → UI로 내보내기 불가
  → 일반 사용자 수준에서 추출 불가
  → mimikatz 등 공격 도구 + 관리자 권한 있으면 이론상 추출 가능

보완 방법
  1. Exportable = FALSE         (키 추출 어렵게)
  2. 유효기간 30~90일           (탈취되어도 짧게 유효)
  3. 이상 접속 감지             (동일 인증서 다중 IP 알림)
```

---

## 7. 운영 고려사항

### 고정 IP 필수
DHCP 환경이면 IP 변경 시 인증서 재발급이 필요하므로, 대상 PC에 고정 IP를 할당해야 한다.

### 인증서 폐기 (퇴직자 등)
```bash
# CRL 생성
openssl ca -gencrl -out ca.crl -config openssl.cnf

# 특정 인증서 폐기
openssl ca -revoke user1.crt -config openssl.cnf
```

Nginx에 CRL 설정:
```nginx
ssl_crl /etc/ssl/ca.crl;
```

### 인증서 유효기간
- CA 인증서: 10년
- 사용자 인증서: 30~90일 권장 (탈취 시 유효 시간 최소화)

### Windows 설치 방법 (사용자 안내)
```
배포된 .cer 파일 (또는 certreq -accept 명령)으로 설치
저장소 위치: 현재 사용자
인증서 저장소: 개인 (Personal)

Chrome / Edge: Windows 인증서 저장소 자동 사용 → 별도 설정 불필요
Firefox: about:preferences#privacy → 인증서 관리에서 별도 등록 필요
```

---

## 8. 최종 결론

> TPM 없는 도메인 미가입 Windows 환경에서  
> **소프트웨어만으로 낼 수 있는 현실적인 최선 구성**

```
✅ 클라이언트에서 개인키 직접 생성 (CA는 서명만)
✅ Exportable = FALSE (키 추출 어렵게)
✅ SAN에 고정 IP 등록
✅ 서버에서 TCP 관측 IP ↔ SAN IP 비교 (위조 불가)
✅ 유효기간 30~90일
```

ID/PW 방식과는 비교가 안 되는 수준이며,  
일반적인 위협 모델(외부 공격자, 피싱, 인증서 탈취)에 대해 충분히 견고하다.
