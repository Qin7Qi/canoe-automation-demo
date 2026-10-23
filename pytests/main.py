"""顺序执行多个 XML Test Module 的最小启动脚本。

默认顺序执行 Diag_Test 和 Tester；也可用 --module 只跑其中一个。

运行前提：必须先进入工程根目录（或 pytests 目录），再执行脚本。
"""

import argparse
import os
import time

import win32com.client


# ===== 纯字符串相对路径（以当前工作目录为基准）=====
CFG_PATH = r".\Vehicle_System_CAN.cfg"

MODULES = {
    "Tester": {
        "vxt":    r".\Test_module\vxt\Tester.vxt",
        "report": r"reports\Tester_report.xml",
    },
    "Diag_Test": {
        "vxt":    r".\Diag_module\vxt\Diag_Test.vxt",
        "report": r"reports\Diag_Test_report.xml",
    },
}


def main():
    print("测试轮询git")
    parser = argparse.ArgumentParser(description="顺序启动 CANoe 并运行 XML Test Module")
    parser.add_argument(
        "--module",
        default="all",
        choices=list(MODULES.keys()) + ["all"],
        help="要执行的模块；all 表示按 MODULES 顺序全部执行",
    )
    parser.add_argument("--timeout", type=float, default=300.0, help="每个测试模块的超时（秒）")
    parser.add_argument("--no-quit", action="store_true", help="跑完后不退出 CANoe")
    args = parser.parse_args()

    module_names = list(MODULES.keys()) if args.module == "all" else [args.module]

    # ===== 启动前检查路径 =====
    if not os.path.isfile(CFG_PATH):
        raise FileNotFoundError(
            f"配置文件不存在: {os.path.abspath(CFG_PATH)}\n"
            f"请确认当前工作目录是工程根目录。当前目录: {os.getcwd()}"
        )
    for name in module_names:
        vxt_path = MODULES[name]["vxt"]
        if not os.path.isfile(vxt_path):
            raise FileNotFoundError(f"[{name}] VXT 文件不存在: {os.path.abspath(vxt_path)}")
        os.makedirs(os.path.dirname(MODULES[name]["report"]), exist_ok=True)

    print(f"当前目录   : {os.getcwd()}")
    print(f"配置文件   : {os.path.abspath(CFG_PATH)}")
    print(f"执行模块   : {', '.join(module_names)}")
    print("-" * 70)

    # ===== 1. 连接 CANoe =====
    print("[1] 连接 CANoe...")
    canoe = win32com.client.Dispatch("CANoe.Application")
    print(f"    CANoe 版本: {canoe.Version}")

    try:
        # ===== 2. 打开配置（等待加载完成）=====
        print("[2] 打开配置...")
        cfg_abs = os.path.abspath(CFG_PATH)
        print(f"    目标配置: {cfg_abs}")

        current = ""
        try:
            current = str(canoe.Configuration.FullName or "")
        except Exception:
            pass

        if current and os.path.normcase(current) == os.path.normcase(cfg_abs):
            print(f"    配置已打开，跳过加载: {current}")
        else:
            if current:
                print(f"    当前已打开其他配置: {current}")
                print(f"    切换到目标配置...")
            canoe.Open(cfg_abs)

            deadline = time.time() + 60
            while time.time() < deadline:
                try:
                    current = str(canoe.Configuration.FullName or "")
                except Exception:
                    current = ""
                if current and os.path.normcase(current) == os.path.normcase(cfg_abs):
                    print(f"    配置加载完成: {current}")
                    break
                time.sleep(0.5)
            else:
                raise RuntimeError(
                    f"配置加载超时（60 秒）。\n"
                    f"  期望: {cfg_abs}\n"
                    f"  当前: {current!r}\n"
                    f"  可能原因: 路径错误、CANoe 弹出对话框、或配置损坏。"
                )

        # ===== 3. 查找所有需要的模块（测量启动前）=====
        print("[3] 查找 XML Test Module...")
        resolved_modules = []
        for name in module_names:
            vxt_path = MODULES[name]["vxt"]
            report_path = os.path.abspath(MODULES[name]["report"])
            module = find_module(canoe, vxt_path)
            print(f"    [{name}] 找到模块: {module.Name}")
            resolved_modules.append({
                "name": name,
                "module": module,
                "vxt_path": vxt_path,
                "report_path": report_path,
            })

        # ===== 4. 设置所有模块的报告路径（测量启动前）=====
        print("[4] 设置报告路径...")
        for item in resolved_modules:
            item["module"].Report.Enabled = True
            item["module"].Report.FullName = item["report_path"]
            print(f"    [{item['name']}] 报告路径: {item['report_path']}")

        # ===== 5. 启动测量 =====
        print("[5] 启动测量...")
        measurement = canoe.Measurement
        measurement.Start()
        wait_until(lambda: measurement.Running, 60, "测量启动")
        print("    测量已启动")

        # ===== 6. 依次执行每个模块 =====
        for index, item in enumerate(resolved_modules, start=1):
            name = item["name"]
            module = item["module"]
            report_path = item["report_path"]

            print(f"\n[6.{index}] 执行模块: {name}")
            run_one_module(module, report_path, args.timeout)

        # ===== 7. 停止测量 =====
        print("\n[7] 停止测量...")
        if measurement.Running:
            measurement.Stop()
            wait_until(lambda: not measurement.Running, 30, "测量停止")
        print("    测量已停止")

        # ===== 8. 确认报告 =====
        print("\n[8] 报告检查:")
        for item in resolved_modules:
            report_path = item["report_path"]
            if not os.path.isfile(report_path) or os.path.getsize(report_path) == 0:
                raise RuntimeError(f"[{item['name']}] 报告未生成或为空: {report_path}")
            print(f"    [{item['name']}] {report_path} ({os.path.getsize(report_path)} 字节)")

    finally:
        if not args.no_quit:
            print("[9] 退出 CANoe...")
            try:
                canoe.Configuration.Modified = False
            except Exception:
                pass
            try:
                canoe.Quit()
            except Exception:
                pass


def run_one_module(module, report_path, timeout_s):
    """启动一个测试模块并等待它完成。"""
    # 删除旧报告，避免把上一次的结果误判为本次结果
    try:
        if os.path.isfile(report_path):
            os.remove(report_path)
    except OSError as exc:
        print(f"    警告: 无法删除旧报告 {report_path}: {exc}")

    print(f"    启动模块: {module.Name}")
    module.Start()

    print(f"    等待模块完成（超时 {timeout_s:.0f} 秒）...")
    wait_for_finish(module, report_path, timeout_s)
    print(f"    模块完成: {module.Name}")


def find_module(canoe, vxt_path):
    """按 VXT 所在目录查找 XML Test Module。"""
    vxt_abs  = os.path.abspath(vxt_path)
    vxt_dir  = os.path.dirname(vxt_abs)
    vxt_name = os.path.basename(vxt_abs)

    envs = canoe.Configuration.TestSetup.TestEnvironments

    for i in range(1, envs.Count + 1):
        env = envs.Item(i)
        try:
            modules = env.TestModules
        except Exception:
            from win32com.client import dynamic
            env = dynamic.Dispatch(env._oleobj_)
            modules = env.TestModules

        for j in range(1, modules.Count + 1):
            m = modules.Item(j)
            name = str(m.Name or "")
            path = str(m.Path or "")
            try:
                full = str(m.FullName or "")
            except Exception:
                full = ""

            if full and os.path.normcase(full) == os.path.normcase(vxt_abs):
                return m
            if path and os.path.normcase(os.path.normpath(path)) == \
                       os.path.normcase(os.path.normpath(vxt_dir)):
                return m
            if vxt_name in name:
                return m

    raise RuntimeError(
        f"找不到 XML Test Module: {vxt_name}\n"
        f"  期望目录: {vxt_dir}\n"
        f"  已遍历 {envs.Count} 个环境。"
    )


def wait_until(condition, timeout_s, label):
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        try:
            if condition():
                return
        except Exception:
            pass
        time.sleep(0.5)
    raise RuntimeError(f"等待超时（{timeout_s} 秒）: {label}")


def wait_for_finish(module, report_path, timeout_s):
    """等待测试模块执行结束。

    优先看 module.State；如果 State 不可用，等报告文件生成且非空。
    """
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        try:
            state = int(module.State)
            if state == 0:
                return
        except Exception:
            if os.path.isfile(report_path) and os.path.getsize(report_path) > 0:
                return
        time.sleep(1)
    raise RuntimeError(f"等待测试完成超时（{timeout_s} 秒）: {module.Name}")


if __name__ == "__main__":
    main()