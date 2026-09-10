import subprocess
import asyncio
import traceback

async def get_server_status():
    """执行健康检查脚本，返回状态字符串"""
    try:
        proc = await asyncio.create_subprocess_exec(
            "/usr/local/bin/health_check.sh",
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=10)
        stdout = stdout.decode().strip()
        stderr = stderr.decode().strip()
        if proc.returncode == 0 and stdout:
            return f"✅ {stdout}"
        else:
            return f"⚠️ {stderr or stdout or '未知错误'}"
    except Exception as e:
        return f"❌ 状态检查失败: {e}"
