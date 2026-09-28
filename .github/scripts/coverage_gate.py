"""커버리지 게이트 (TASK 5-9, IdP 는 TASK 5-12).

    python3 .github/scripts/coverage_gate.py <coverage.json> <기준선 파일> <제목>

coverage.json 의 두 지표가 기준선 파일의 값 **아래로 떨어지면 실패**한다.
표는 job summary 에 남겨 PR 에서 바로 보이게 한다.
0.30%p 이상 오르면 기준선을 올리라고 notice 로 알린다 — 그래야 래칫이 조여진다.

본 앱(`test` job)과 IdP(`idp-test` job)가 같이 쓴다.
"""
import json
import os
import re
import sys

LABELS = {'percent_covered': '라인+분기', 'percent_branches_covered': '분기'}


def main(cov_path, baseline_path, title):
    t = json.load(open(cov_path))['totals']
    base = dict(
        (k, float(v)) for k, v in
        re.findall(r'^(\w+)\s*=\s*([\d.]+)$', open(baseline_path).read(), re.M))

    rows, failed, improved = [], [], []
    for key, label in LABELS.items():
        now, want = t[key], base[key]
        ok = now >= want
        rows.append(f"| {label} | **{now:.2f}%** | {want:.2f}% | {'통과' if ok else '**미달**'} |")
        (improved if now >= want + 0.30 else []).append(f'{key} = {now:.2f}')
        if not ok:
            failed.append(f'{label}: {now:.2f}% < 기준선 {want:.2f}%')

    summary = os.environ.get('GITHUB_STEP_SUMMARY')
    if summary:
        with open(summary, 'a') as f:
            print(f'### {title}', file=f)
            print('\n| 지표 | 현재 | 기준선 | |', file=f)
            print('| :--- | ---: | ---: | :-- |', file=f)
            for r in rows:
                print(r, file=f)
            print(f"\n라인만 {t['percent_statements_covered']:.2f}% "
                  f"(참고 — 라인은 import 만으로 부풀려진다. TASK 5-4 §4)", file=f)

    for line in rows:
        print(line)
    if improved:
        print(f'::notice::커버리지가 올랐습니다. {baseline_path} 을 갱신하십시오 -> '
              + ' / '.join(improved))
    if failed:
        print('::error::커버리지가 기준선 아래로 떨어졌습니다 -- ' + ' / '.join(failed))
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main(*sys.argv[1:4]))
