"""날짜/시간 입력 위젯 교체.

## 왜 필요한가

Flask-AppBuilder 의 `DateTimePickerWidget` 은 **시분초를 입력할 수 없다.**
위젯은 datetime 을 의도하지만

    data_template = ('<div class="input-group date appbuilder_datetime" '
                     'data-provide="datepicker" ...'                 # 날짜 전용
                     '<input ... data-format="yyyy-MM-dd hh:mm:ss" ...')

정작 JS 는 날짜 전용 picker 로 바인딩한다.

    // flask_appbuilder/static/appbuilder/js/ab.js
    $('.appbuilder_datetime').datepicker({ format: 'yyyy-mm-dd' });

**FAB 4.5.3 과 5.2.3 의 이 코드가 동일하다.** FAB 업그레이드로는 해결되지 않는다.

## 이전 방식과 무엇이 다른가

예전에는 `Dockerfile.app` 에서 `sed` 4번으로 FAB 내부 파일(`init.html`, `ab.js`,
`fieldwidgets.py`)을 고치고 `bootstrap-datetimepicker` + `moment.js`(97KB)를
이미지에 밀어 넣었다. 동작은 했지만

- FAB 내부 구조에 의존해 버전이 바뀌면 조용히 깨질 수 있고
- `moment.js` 는 2020년부터 유지보수 모드다 (신규 개발 비권장)

여기서는 **브라우저 기본 `<input type="datetime-local">`** 을 쓴다.
JS 라이브러리가 필요 없고 FAB 내부를 건드리지 않는다.
`step="1"` 이 초 단위 입력을 연다.
"""
from markupsafe import Markup
from wtforms.fields import DateTimeField
from wtforms.widgets import html_params

# 브라우저가 보내는 형식과 기존 데이터 형식을 모두 받는다.
#   datetime-local 은 초가 0 이면 'T%H:%M' 까지만 보낸다.
DATETIME_FORMATS = [
    '%Y-%m-%dT%H:%M:%S',   # 네이티브 입력 (초 포함)
    '%Y-%m-%dT%H:%M',      # 네이티브 입력 (초 생략)
    '%Y-%m-%d %H:%M:%S',   # 기존 방식 호환
]


class NativeDateTimeWidget:
    """`<input type="datetime-local" step="1">` 렌더러."""

    @staticmethod
    def _to_input_value(data) -> str:
        """`field.data` 를 `datetime-local` 이 받는 문자열로 바꾼다.

        `data` 가 항상 datetime 인 것은 아니다.
        - 검색 필터 위젯은 **문자열**을 넣는다
        - 검증 실패 후 재렌더링 시에도 사용자가 친 원본 문자열이 온다
        - 비어 있으면 None 또는 ''

        FAB 원본 위젯은 값을 그대로 출력해 이 경우를 자연히 견딘다.
        같은 내성을 갖추지 않으면 list view 의 검색 폼이 깨진다.
        """
        if not data:
            return ''
        if hasattr(data, 'strftime'):
            return data.strftime('%Y-%m-%dT%H:%M:%S')
        # 문자열: 공백 구분자를 'T' 로 바꿔 브라우저가 인식하게 한다.
        return str(data).strip().replace(' ', 'T', 1)

    def __call__(self, field, **kwargs):
        kwargs.setdefault('id', field.id)
        kwargs.setdefault('name', field.name)
        return Markup(
            '<div class="input-group">'
            '<input class="form-control" %s />'
            '</div>'
            % html_params(type='datetime-local', step='1',
                          value=self._to_input_value(field.data), **kwargs)
        )


class FlexibleDateTimeField(DateTimeField):
    """여러 입력 형식을 받아들이는 DateTimeField."""

    def __init__(self, *args, **kwargs):
        kwargs.setdefault('format', DATETIME_FORMATS)
        super().__init__(*args, **kwargs)


def install():
    """FAB 의 datetime 필드 변환 규칙을 교체한다.

    `FieldConverter.conversion_table` 의 `is_datetime` 항목만 바꾼다.
    날짜 전용(`is_date`)은 FAB 기본 동작이 올바르므로 건드리지 않는다.

    AppBuilder 생성 전에 호출해야 한다.
    """
    from flask_appbuilder.forms import FieldConverter

    table = list(FieldConverter.conversion_table)
    for i, entry in enumerate(table):
        if entry[0] == 'is_datetime':
            table[i] = ('is_datetime', FlexibleDateTimeField, NativeDateTimeWidget)
            break
    else:  # pragma: no cover - FAB 구조가 바뀌면 조용히 지나가지 않게 한다
        raise RuntimeError(
            "FieldConverter.conversion_table 에 'is_datetime' 항목이 없습니다. "
            'FAB 버전 변경으로 구조가 달라졌을 수 있습니다.')

    FieldConverter.conversion_table = tuple(table)
