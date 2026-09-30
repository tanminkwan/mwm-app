// toastui-editor-all.min.js 안의 DOMPurify 모듈만 새 DOMPurify 로 갈아 끼운다 (HOWTO_020 §5).
//
// TOAST UI Editor 는 3.2.2 가 마지막이고 DOMPurify 2.3.3 을 webpack 모듈 하나로 품고 있다.
// 에디터 코드는 그대로 두고 그 모듈 본문만 바꾼다. 여러 번 돌려도 결과가 같다.
//
//   node patch_dompurify.mjs <toastui-editor-all.min.js> <purify.min.js>
import { readFileSync, writeFileSync } from 'node:fs';
import * as acorn from 'acorn';

const [bundlePath, purifyPath] = process.argv.slice(2);
const src = readFileSync(bundlePath, 'utf8');
// 소스맵은 함께 넣지 않으므로 참조 줄을 뺀다
const purify = readFileSync(purifyPath, 'utf8').replace(/\n\/\/# sourceMappingURL=.*\s*$/, '').trim();
const newVersion = purify.match(/@license DOMPurify ([\d.]+)/)[1];

// webpack 모듈 표 `var e={368:function(e){...}, ...}` 에서 DOMPurify 를 담은 모듈을 찾는다
let target = null;
const ast = acorn.parse(src, { ecmaVersion: 'latest' });
(function walk(node) {
  if (target || !node || typeof node.type !== 'string') return;
  if (node.type === 'Property' && node.value.type === 'FunctionExpression' && node.value.params.length === 1) {
    const body = node.value.body;
    if (/@license DOMPurify /.test(src.slice(body.start, body.end)) && !/prosemirror/i.test(src.slice(body.start, body.end))) {
      target = node;
      return;
    }
  }
  for (const key of Object.keys(node)) {
    const v = node[key];
    if (Array.isArray(v)) v.forEach(walk);
    else if (v && typeof v.type === 'string') walk(v);
  }
})(ast);
if (!target) throw new Error('DOMPurify 모듈을 찾지 못했다');

const param = target.value.params[0].name;
const oldBody = src.slice(target.value.body.start, target.value.body.end);
const oldVersion = (oldBody.match(/@license DOMPurify ([\d.]+)/) || [])[1];
// UMD 가 CommonJS 경로를 타도록 module·exports 를 모듈 인자로 묶는다
const newBody = `{var module=${param},exports=${param}.exports;\n${purify}\n}`;
const out = src.slice(0, target.value.body.start) + newBody + src.slice(target.value.body.end);

acorn.parse(out, { ecmaVersion: 'latest' });  // 결과가 문법적으로 맞는지
if ((out.match(/@license DOMPurify /g) || []).length !== 1) throw new Error('DOMPurify 사본이 하나가 아니다');
writeFileSync(bundlePath, out);
console.log(`module ${target.key.value ?? target.key.name}: DOMPurify ${oldVersion} -> ${newVersion}`);
