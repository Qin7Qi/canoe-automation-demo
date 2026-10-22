"""把 CANoe 原生 XML 报告转换成 JUnit XML，供 Jenkins 的 junit 插件使用。

用法:
    python pytests/convert_reports.py
    python pytests/convert_reports.py --dir reports
"""

import argparse
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path


# ==================== 工具函数 ====================

def local(tag):
    return tag.rsplit("}", 1)[-1] if "}" in tag else tag


def find_child(elem, name):
    for c in elem:
        if local(c.tag) == name:
            return c
    return None


def child_text(elem, name):
    c = find_child(elem, name)
    return (c.text or "").strip() if c is not None else ""


def as_float(value):
    try:
        return float(str(value).strip()) if value is not None else 0.0
    except (TypeError, ValueError):
        return 0.0


# ==================== 数据结构 ====================

@dataclass
class Case:
    name: str
    group: str
    ident: str
    verdict: str
    duration: float = 0.0
    messages: list = field(default_factory=list)

    @property
    def status(self):
        v = (self.verdict or "").strip().lower()
        if v == "pass":
            return "passed"
        if v == "fail":
            return "failure"
        if v == "error":
            return "error"
        return "skipped"


# ==================== 解析 ====================

def extract_case_info(elem):
    """从 <testcase> 提取 title、ident、verdict、结束时间。

    本报告的典型结构：
        <testcase timestamp="37.24">
          <comment>...</comment>
          <teststep .../>
          <verdict result="pass" endtimestamp="37.25">
            <title>DIAG-01: ...</title>
            <ident>DIAG-01</ident>
          </verdict>
        </testcase>

    同时兼容 title/ident 直接挂在 testcase 下的变体。
    """
    verdict_elem = find_child(elem, "verdict")

    verdict = ""
    end_ts = None
    if verdict_elem is not None:
        verdict = (verdict_elem.get("result") or "").strip()
        end_ts = verdict_elem.get("endtimestamp") or verdict_elem.get("timestamp")

    title = ""
    ident = ""
    # 优先从 verdict 里取（本报告的结构）
    if verdict_elem is not None:
        title = child_text(verdict_elem, "title")
        ident = child_text(verdict_elem, "ident")
    # 兜底：从 testcase 直接子元素取
    if not title:
        title = child_text(elem, "title")
    if not ident:
        ident = child_text(elem, "ident")
    # 再兜底：从属性取
    if not title:
        title = elem.get("title") or elem.get("name") or ""
    if not ident:
        ident = elem.get("ident") or ""

    return title.strip(), ident.strip(), verdict, end_ts


def extract_messages(elem):
    """只提取真正失败的 teststep 文本，忽略 result='na' 的自动步骤。"""
    messages = []
    for node in elem.iter():
        if local(node.tag) != "teststep":
            continue
        if (node.get("result") or "").lower() != "fail":
            continue
        text = " ".join("".join(node.itertext()).split())
        if text:
            messages.append(text)
    return list(dict.fromkeys(messages))


def parse_report(path: Path):
    """返回 (module_title, [Case, ...])。"""
    root = ET.parse(path).getroot()
    module_title = (
        child_text(root, "title")
        or root.get("title")
        or root.get("name")
        or path.stem
    )

    cases = []

    def visit(elem, groups):
        tag = local(elem.tag)

        if tag == "testgroup":
            title = child_text(elem, "title") or elem.get("title") or elem.get("ident")
            new_groups = groups + ([title] if title else [])
            for c in elem:
                visit(c, new_groups)
            return

        if tag == "testcase":
            title, ident, verdict, end_ts = extract_case_info(elem)
            start = as_float(elem.get("timestamp"))
            end = as_float(end_ts)
            duration = end - start if end >= start else 0.0

            messages = extract_messages(elem)
            if verdict.lower() == "fail" and not messages:
                messages = ["Test case failed (no failing teststep in report)."]

            name = title or ident or f"case-{len(cases) + 1}"
            group = " / ".join(g for g in groups if g) or module_title
            cases.append(Case(
                name=name,
                group=group,
                ident=ident,
                verdict=verdict,
                duration=duration,
                messages=messages,
            ))
            return

        # 其他节点继续往下找
        for c in elem:
            visit(c, groups)

    visit(root, [])
    return module_title, cases


# ==================== 写 JUnit ====================

def write_junit(junit_path: Path, module_title: str, cases: list):
    tests = len(cases)
    failures = sum(1 for c in cases if c.status == "failure")
    errors = sum(1 for c in cases if c.status == "error")
    skipped = sum(1 for c in cases if c.status == "skipped")
    total_time = sum(c.duration for c in cases)

    root = ET.Element("testsuites", {
        "name": module_title,
        "tests": str(tests),
        "failures": str(failures),
        "errors": str(errors),
        "skipped": str(skipped),
        "time": f"{total_time:.3f}",
    })

    groups = {}
    for c in cases:
        groups.setdefault(c.group, []).append(c)

    for group_name, group_cases in groups.items():
        g_fail = sum(1 for c in group_cases if c.status == "failure")
        g_err = sum(1 for c in group_cases if c.status == "error")
        g_skip = sum(1 for c in group_cases if c.status == "skipped")
        g_time = sum(c.duration for c in group_cases)

        suite = ET.SubElement(root, "testsuite", {
            "name": group_name,
            "tests": str(len(group_cases)),
            "failures": str(g_fail),
            "errors": str(g_err),
            "skipped": str(g_skip),
            "time": f"{g_time:.3f}",
        })

        for c in group_cases:
            # 用 ident 作为 name，避免中文标题在不同 Jenkins 版本里显示问题
            display_name = f"{c.ident}: {c.name}" if c.ident and c.ident not in c.name else c.name
            tc = ET.SubElement(suite, "testcase", {
                "classname": group_name,
                "name": display_name,
                "time": f"{c.duration:.3f}",
            })
            if c.status == "failure":
                body = "\n".join(c.messages) or "failed"
                f = ET.SubElement(tc, "failure", {
                    "message": body.splitlines()[0][:200],
                    "type": "CANoeFailure",
                })
                f.text = body
            elif c.status == "error":
                body = "\n".join(c.messages) or "error"
                e = ET.SubElement(tc, "error", {
                    "message": body.splitlines()[0][:200],
                    "type": "CANoeError",
                })
                e.text = body
            elif c.status == "skipped":
                ET.SubElement(tc, "skipped", {"message": c.verdict or "not executed"})

    ET.indent(root, space="  ")
    junit_path.parent.mkdir(parents=True, exist_ok=True)
    ET.ElementTree(root).write(str(junit_path), encoding="utf-8", xml_declaration=True)


# ==================== 主流程 ====================

def convert_one(report: Path) -> Path:
    module_title, cases = parse_report(report)
    junit_path = report.with_name(report.stem.replace("_report", "") + "_junit.xml")
    write_junit(junit_path, module_title, cases)

    passed = sum(1 for c in cases if c.status == "passed")
    failed = sum(1 for c in cases if c.status == "failure")
    print(f"[转换] {report.name} -> {junit_path.name}")
    print(f"        模块: {module_title}")
    print(f"        用例 {len(cases)} 个: 通过 {passed}, 失败 {failed}")
    for c in cases:
        print(f"          - [{c.status}] {c.ident or '-'} {c.name}  ({c.duration:.2f}s)")
    return junit_path


def main():
    parser = argparse.ArgumentParser(description="CANoe 报告转 JUnit")
    parser.add_argument("--dir", default="reports", help="报告所在目录")
    args = parser.parse_args()

    report_dir = Path(args.dir)
    if not report_dir.is_dir():
        print(f"目录不存在: {report_dir}")
        return 1

    reports = sorted(report_dir.glob("*_report.xml"))
    if not reports:
        print(f"在 {report_dir} 下没有找到 *_report.xml")
        return 1

    for report in reports:
        try:
            convert_one(report)
        except Exception as exc:
            print(f"[失败] {report.name}: {exc}")
            return 1

    print(f"\n完成，共转换 {len(reports)} 个报告")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())