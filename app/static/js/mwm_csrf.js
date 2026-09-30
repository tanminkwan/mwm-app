/**
 * 같은 출처로 보내는 조회 아닌 요청(POST·PUT·PATCH·DELETE)에 CSRF 토큰 헤더를 붙인다.
 * 토큰은 공통 레이아웃(mwm_base.html)의 <meta name="csrf-token"> 에 있다.
 * jQuery AJAX 는 ajaxSend(호출마다 beforeSend 를 줘도 덮이지 않는다), fetch 는 감싸서 붙인다.
 */
(function () {
    var meta = document.querySelector('meta[name="csrf-token"]');
    if (!meta) return;
    var token = meta.getAttribute('content');
    var SAFE = /^(GET|HEAD|OPTIONS|TRACE)$/i;

    function sameOrigin(url) {
        try { return new URL(url, window.location.href).origin === window.location.origin; }
        catch (e) { return false; }
    }

    if (window.jQuery) {
        window.jQuery(document).ajaxSend(function (event, xhr, settings) {
            if (!SAFE.test(settings.type || 'GET') && sameOrigin(settings.url)) {
                xhr.setRequestHeader('X-CSRFToken', token);
            }
        });
    }

    if (window.fetch) {
        var originalFetch = window.fetch;
        window.fetch = function (input, init) {
            init = init || {};
            var isRequest = typeof Request !== 'undefined' && input instanceof Request;
            var method = init.method || (isRequest ? input.method : 'GET');
            var url = isRequest ? input.url : String(input);
            if (!SAFE.test(method) && sameOrigin(url)) {
                var headers = new Headers(init.headers || (isRequest ? input.headers : undefined));
                if (!headers.has('X-CSRFToken')) headers.set('X-CSRFToken', token);
                init.headers = headers;
            }
            return originalFetch.call(this, input, init);
        };
    }
})();
