"""打印 CANoe 报告的结构，用于确认 verdict、testcase 等标签的位置。"""

import sys
import xml.etree.ElementTree as ET
from pathlib import Path


def local(tag):
    return tag.rsplit("}", 1)[-1] if "}" in tag else tag


def dump(elem, depth=0, max_depth=6):
    if depth > max_depth:
        return
    indent = "  " * depth
    attrs = " ".join(f'{k}="{v}"' for k, v in elem.attrib.items())
    text = (elem.text or "").strip()
    text_part = f"  text={text[:60]!r}" if text else ""
    print(f"{indent}<{local(elem.tag)} {attrs}>{text_part}")
    for child in elem:
        dump(child, depth + 1, max_depth)


def main():
    report = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("reports/Diag_Test_report.xml")
    if not report.is_file():
        print(f"报告不存在: {report}")
        print("用法: python inspect_report.py reports/Diag_Test_report.xml")
        return 1

    print(f"文件: {report}")
    print(f"大小: {report.stat().st_size} 字节")
    print("=" * 70)

    root = ET.parse(report).getroot()
    print(f"根节点: <{local(root.tag)}>")
    print(f"根属性: {root.attrib}")
    print("=" * 70)
    dump(root, max_depth=8)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())