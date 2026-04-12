def format_result(value, unit):
    """
    将数值格式化为带单位的字符串，保留两位小数。

    Args:
        value: 数值（整数或浮点数）
        unit: 单位字符串，如 "°C", "°F", "K"

    Returns:
        格式化后的字符串，如 "25.50°C"
    """
    return f"{value:.2f}{unit}"
