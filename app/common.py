import json

def singleton(cls):
    instances = {}

    def get_instance(*args, **kwargs):
        if cls not in instances:
            instances[cls] = cls(*args, **kwargs)
        return instances[cls]
    
    return get_instance

def jsonl_to_markdown(jsonl_data):
    """
    JSONL 문자열 또는 딕셔너리 리스트를 입력받아 지정된 포맷의 Markdown 텍스트로 변환합니다.
    """
    # 입력값이 문자열인 경우 JSONL 또는 JSON List로 파싱
    if isinstance(jsonl_data, str):
        try:
            # 먼저 전체 문자열이 유효한 JSON(특히 리스트)인지 확인
            parsed = json.loads(jsonl_data)
            if isinstance(parsed, list):
                data_list = parsed
            else:
                data_list = [parsed]
        except json.JSONDecodeError:
            # 전체 파싱 실패 시, 줄 단위 JSONL로 간주
            lines = [line for line in jsonl_data.strip().split('\n') if line.strip()]
            data_list = []
            for line in lines:
                try:
                    data_list.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    elif isinstance(jsonl_data, list):
        data_list = jsonl_data
    else:
        return ""

    md_lines = []
    for i, data in enumerate(data_list, 1):
        if not isinstance(data, dict):
            continue
            
        md_lines.append(f"### Entry {i}")
        
        for key, value in data.items():
            if isinstance(value, str):
                # 문자열 내부에 이스케이프된 개행문자(\n)나 탭(\t)이 문자 그대로 있을 경우를 대비하여 치환 처리
                val_str = value.replace('\\n', '\n').replace('\\t', '\t')
                
                # Multi-line 인 경우 처리
                if '\n' in val_str:
                    md_lines.append(f"- {key} :")
                    md_lines.append("```")
                    md_lines.append(val_str)
                    md_lines.append("```")
                else:
                    md_lines.append(f"- {key} : `{val_str}`")
            else:
                md_lines.append(f"- {key} : {value}")
        
        # Entry 간 간격을 위한 빈 줄
        md_lines.append("")

    return '\n'.join(md_lines).strip()