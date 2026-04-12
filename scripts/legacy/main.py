"""
温度转换器命令行入口
"""
import sys
from converter import celsius_to_fahrenheit, fahrenheit_to_celsius, celsius_to_kelvin
from utils import format_result


# 支持的转换类型映射
CONVERSION_MAP = {
    "c2f": (celsius_to_fahrenheit, "°C", "°F"),
    "f2c": (fahrenheit_to_celsius, "°F", "°C"),
    "c2k": (celsius_to_kelvin, "°C", "K"),
}


def print_usage():
    """打印使用说明"""
    print("用法: python main.py <数值> <转换类型>")
    print("转换类型:")
    print("  c2f - 摄氏度转华氏度")
    print("  f2c - 华氏度转摄氏度")
    print("  c2k - 摄氏度转开尔文")
    print("示例: python main.py 25 c2f")


def main():
    """主函数"""
    # 检查参数数量
    if len(sys.argv) != 3:
        print("错误: 参数数量不足！")
        print_usage()
        sys.exit(1)

    # 解析参数
    try:
        value = float(sys.argv[1])
    except ValueError:
        print("错误: 第一个参数必须是数值！")
        print_usage()
        sys.exit(1)

    conversion_type = sys.argv[2].lower()

    # 检查转换类型是否有效
    if conversion_type not in CONVERSION_MAP:
        print(f"错误: 未知的转换类型 '{conversion_type}'！")
        print_usage()
        sys.exit(1)

    # 获取转换函数和单位信息
    conversion_func, unit_from, unit_to = CONVERSION_MAP[conversion_type]

    # 执行转换
    result = conversion_func(value)

    # 格式化并输出结果
    formatted_input = format_result(value, unit_from)
    formatted_output = format_result(result, unit_to)
    print(f"{formatted_input} = {formatted_output}")


if __name__ == "__main__":
    main()
