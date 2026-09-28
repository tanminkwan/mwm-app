/**
 * Toast UI Editor : Mermaid Plugin (Custom)
 * Renders ```mermaid code blocks as Mermaid diagrams.
 * Uses codeBlock renderer override to intercept mermaid language blocks.
 * Requires mermaid.js to be loaded before this script.
 */
(function (root, factory) {
    if (typeof module === 'object' && typeof module.exports === 'object') {
        module.exports = factory();
    } else {
        root.toastui = root.toastui || {};
        root.toastui.Editor = root.toastui.Editor || {};
        root.toastui.Editor.plugin = root.toastui.Editor.plugin || {};
        root.toastui.Editor.plugin.mermaid = factory();
    }
})(typeof self !== 'undefined' ? self : this, function () {

    // Initialize mermaid once
    if (typeof mermaid !== 'undefined') {
        mermaid.initialize({
            startOnLoad: false,
            theme: 'default',
            securityLevel: 'loose'
        });
    }

    // Inject CSS to isolate mermaid SVG from page global styles
    (function () {
        var style = document.createElement('style');
        style.textContent =
            /* Reset all inherited styles inside the mermaid container */
            '.mermaid-container { line-height: normal !important; font-weight: normal !important; font-size: 16px !important; }' +
            '.mermaid-container * { line-height: normal !important; font-weight: normal !important; }' +
            /* Fix foreignObject text rendering (used by Mermaid 10.x) */
            '.mermaid-container foreignObject { overflow: visible !important; }' +
            '.mermaid-container foreignObject div { line-height: 1.2 !important; font-weight: normal !important; font-size: inherit !important; }' +
            '.mermaid-container .nodeLabel { line-height: 1.2 !important; font-weight: normal !important; }' +
            '.mermaid-container .edgeLabel { line-height: 1.2 !important; font-weight: normal !important; }' +
            '.mermaid-container .label { line-height: 1.2 !important; font-weight: normal !important; }' +
            /* Ensure SVG is visible */
            '.mermaid-container svg { overflow: visible; max-width: 100%; }';
        document.head.appendChild(style);
    })();

    var _id = 0;

    function renderMermaidEl(containerId, code) {
        setTimeout(function () {
            var el = document.getElementById(containerId);
            if (!el || typeof mermaid === 'undefined') return;

            var svgId = 'mermaid-svg-' + containerId;
            try {
                var result = mermaid.render(svgId, code);
                if (result && typeof result.then === 'function') {
                    // Mermaid 10.x (Promise-based)
                    result.then(function (res) {
                        el.innerHTML = res.svg;
                    }).catch(function (err) {
                        el.innerHTML = '<pre style="color:#e74c3c;background:#fdf2f2;padding:10px;border-radius:4px;">Mermaid Error: ' +
                            (err.message || String(err)) + '</pre>';
                    });
                } else if (typeof result === 'string') {
                    el.innerHTML = result;
                }
            } catch (err) {
                // Mermaid 8.x/9.x (callback style)
                try {
                    mermaid.render(svgId, code, function (svgCode) {
                        el.innerHTML = svgCode;
                    });
                } catch (err2) {
                    el.innerHTML = '<pre style="color:#e74c3c;background:#fdf2f2;padding:10px;border-radius:4px;">Mermaid Error: ' +
                        (err2.message || String(err2)) + '</pre>';
                }
            }
        }, 200);
    }

    /**
     * Plugin function for Toast UI Editor 3.x
     * Overrides codeBlock renderer to intercept ```mermaid blocks.
     */
    function mermaidPlugin(context, options) {
        return {
            toHTMLRenderers: {
                codeBlock: function (node, renderContext) {
                    var infoStr = node.info ? node.info.trim().toLowerCase() : '';

                    if (infoStr === 'mermaid') {
                        var code = node.literal || '';
                        var containerId = 'mermaid-' + (_id++);

                        renderMermaidEl(containerId, code);

                        return [
                            {
                                type: 'openTag',
                                tagName: 'div',
                                outerNewLine: true,
                                attributes: {
                                    id: containerId,
                                    'class': 'mermaid-container',
                                    style: 'display:flex;justify-content:center;padding:16px 0;min-height:60px;'
                                }
                            },
                            {
                                type: 'html',
                                content: '<div style="color:#888;font-size:13px;">Loading mermaid diagram...</div>'
                            },
                            {
                                type: 'closeTag',
                                tagName: 'div',
                                outerNewLine: true
                            }
                        ];
                    }

                    // Non-mermaid code blocks: use origin renderer if available
                    if (renderContext && typeof renderContext.origin === 'function') {
                        return renderContext.origin();
                    }

                    // Fallback: default code block rendering
                    var langClass = infoStr ? 'language-' + infoStr : '';
                    var attrs = langClass ? { class: langClass } : {};
                    return [
                        { type: 'openTag', tagName: 'pre', outerNewLine: true },
                        { type: 'openTag', tagName: 'code', attributes: attrs },
                        { type: 'text', content: node.literal || '' },
                        { type: 'closeTag', tagName: 'code' },
                        { type: 'closeTag', tagName: 'pre', outerNewLine: true }
                    ];
                }
            }
        };
    }

    return mermaidPlugin;
});
