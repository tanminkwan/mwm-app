#!/bin/sh
# SBOM(CycloneDX)과 THIRD_PARTY_LICENSES.md 를 다시 만든다 (HOWTO_020).
#
#   sbom/generate.sh            # 이미지 mwm-app·mwm-idp 를 먼저 빌드해 둔다 (README '이미지 빌드')
#
# 운영 이미지에 실제로 설치된 패키지를 그대로 뽑는다. 도구(cyclonedx-bom·pip-licenses)는
# 컨테이너 안의 **별도 venv** 에 설치해 이미지의 패키지 목록에 섞이지 않게 한다 (인터넷 필요 — 개발 PC 에서).
# requirements*.txt 나 app/static 이 바뀌면 다시 돌려 결과를 함께 커밋한다.
set -eu
cd "$(dirname "$0")/.."

RAW=$(mktemp -d)
trap 'rm -rf "$RAW"' EXIT
chmod 777 "$RAW"

for img in mwm-app mwm-idp; do
    echo "--- $img"
    docker run --rm -u 0 -v "$RAW:/out" --entrypoint sh "$img" -euc "
        python -m venv /tmp/sbom-tools
        /tmp/sbom-tools/bin/pip install -q --disable-pip-version-check cyclonedx-bom==7.4.0 pip-licenses==5.5.5
        /tmp/sbom-tools/bin/cyclonedx-py environment /usr/local/bin/python \
            --of JSON --output-reproducible -o /out/$img.cdx.json
        /tmp/sbom-tools/bin/pip-licenses --python /usr/local/bin/python --format=json > /out/$img.licenses.json
        chmod 644 /out/$img.*"
done

VERSION=$(sed -n 's/^APP_NAME = .*VER:\([0-9.]*\).*/\1/p' config.py)
python3 sbom/build.py "$RAW" "$VERSION"
