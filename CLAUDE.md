# Agent Studio - 椤圭洰绾︽潫

## 浠ｇ爜瑙勮寖
- Python 3.11+锛屽叏闈娇鐢� type hints
- 绫诲瀷瀹氫箟缁熶竴鐢� Pydantic v2 BaseModel
- 鍗曟枃浠朵笉瓒呰繃 200 琛岋紝瓒呰繃蹇呴』鎷嗗垎
- 妯″潡闂村彧閫氳繃 __init__.py 鏆撮湶鐨勬帴鍙ｉ€氫俊
- 鎵€鏈夊紓姝ュ嚱鏁板繀椤� try-except锛岄敊璇敤鑷畾涔� Exception 绫�
- 鍑芥暟鍙傛暟瓒呰繃 3 涓椂鐢� dataclass 鎴� Pydantic model 灏佽

## 鏋舵瀯瑙勫垯
- backend/core/ 涓嶄緷璧� FastAPI锛岀函 Python + asyncio
- backend/core/ 涓嶇洿鎺ヨ皟鐢� LLM API锛岄€氳繃娉ㄥ叆鐨� adapter 璋冪敤
- 宸ュ叿閫氳繃 ToolRegistry 娉ㄥ唽锛岀姝㈢‖缂栫爜
- 姣忎釜 s01-s12 妯″潡鐨� __init__.py 鏄敮涓€鍏紑鍏ュ彛
- backend/api/ 鏄敮涓€鐨� HTTP 鍏ュ彛灞傦紝璐熻矗璇锋眰楠岃瘉鍜屽搷搴旀牸寮忓寲

## 渚濊禆绾︽潫
- 鑳界敤鏍囧噯搴撹В鍐崇殑涓嶅紩鍏ョ涓夋柟鍖�
- 鏂板 pip 渚濊禆鍓嶅繀椤昏鏄庣悊鐢�
- 鏍稿績渚濊禆: pydantic, fastapi, uvicorn, httpx

## 娴嬭瘯
- 姣忎釜鍏紑鎺ュ彛鑷冲皯涓€涓祴璇曠敤渚�
- 鐢� pytest + pytest-asyncio
- mock 澶栭儴 API 璋冪敤锛屼笉鍦ㄦ祴璇曚腑鍙戠湡瀹炶姹�

## 鍛藉悕绾﹀畾
- 鏂囦欢鍚�: snake_case
- 绫诲悕: PascalCase
- 鍑芥暟/鍙橀噺: snake_case
- 甯搁噺: UPPER_SNAKE_CASE
