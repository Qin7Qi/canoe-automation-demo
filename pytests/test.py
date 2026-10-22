import win32com.client
try:
    canoe = win32com.client.Dispatch("CANoe.Application")
    print("✅ SUCCESS: CANoe.Application dispatched.")
    print(f"   CANoe Version: {canoe.Version}")
    canoe.Quit()  # 清理
except Exception as e:
    print(f"❌ FAILED to dispatch CANoe: {e}")