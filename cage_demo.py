import os
import re
import secrets
import shutil
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# ============================
# 1. 规则库：动作模式 + 公理
# ============================

# 动作模式：用正则表达式从自然语言请求中提取动作和参数
ACTION_PATTERNS = {
    "read_file": re.compile(
        r"读取文件[：:\s]*(.+?)(?:$|\s+内容\s*)", re.IGNORECASE
    ),
    "write_file": re.compile(
        r"写入文件[：:\s]*(.+?)[，,\s]*内容[：:\s]*(.+)", re.IGNORECASE
    ),
    "delete_file": re.compile(
        r"删除文件[：:\s]*(.+)", re.IGNORECASE
    ),
    "list_dir": re.compile(
        r"列出目录[：:\s]*(.+)", re.IGNORECASE
    ),
    "rename_file": re.compile(
        r"重命名文件[：:\s]*(.+?)[，,\s]*新名称[：:\s]*(.+)", re.IGNORECASE
    ),
}

# 公理：定义允许/禁止的动作及条件
# 每个公理包含动作列表、判定结果(allow/forbid)和说明
AXIOMS = [
    {
        "action_list": ["read_file", "list_dir"],
        "verdict": "allow",
        "reason": "允许读取和列出文件",
    },
    {
        "action_list": ["write_file"],
        "verdict": "allow",
        "reason": "允许写入文件，但仅限特定目录",
        # 可在后续添加参数检查，此处仅作示例
    },
    {
        "action_list": ["delete_file"],
        "verdict": "forbid",
        "reason": "禁止删除任何文件",
    },
    {
        "action_list": ["rename_file"],
        "verdict": "forbid",
        "reason": "禁止重命名文件",
    },
]

# 安全目录：所有文件操作仅限于此目录（模拟沙箱）
SAFE_ROOT = Path("./safe_workspace").resolve()
SAFE_ROOT.mkdir(exist_ok=True)


# ============================
# 2. CAGE 核心网关
# ============================
class CAGE:
    def __init__(self, action_patterns: Dict, axioms: List[Dict]):
        self.action_patterns = action_patterns
        self.axioms = axioms
        self._temp_tokens: Dict[str, Tuple[str, Dict]] = {}  # token -> (action, params)
        self._password_store: Dict[str, str] = {}  # 可存储真实密码，本演示暂不使用

    def parse_request(self, text: str) -> Optional[Tuple[str, Dict]]:
        """将自然语言请求解析为 (动作, 参数) 元组"""
        for action, pattern in self.action_patterns.items():
            match = pattern.search(text)
            if match:
                params = self._extract_params(action, match)
                return action, params
        return None

    def _extract_params(self, action: str, match) -> Dict:
        """根据动作类型从正则匹配结果中提取参数"""
        params = {}
        if action == "read_file":
            params["path"] = match.group(1).strip()
        elif action == "write_file":
            params["path"] = match.group(1).strip()
            params["content"] = match.group(2).strip()
        elif action == "delete_file":
            params["path"] = match.group(1).strip()
        elif action == "list_dir":
            params["dir"] = match.group(1).strip()
        elif action == "rename_file":
            params["old"] = match.group(1).strip()
            params["new"] = match.group(2).strip()
        return params

    def check_permission(self, action: str, params: Dict) -> Tuple[bool, str]:
        """根据公理检查动作是否允许"""
        for axiom in self.axioms:
            if action in axiom["action_list"]:
                if axiom["verdict"] == "allow":
                    # 可以添加更细粒度的参数检查（如路径是否在安全目录内）
                    if action in ["read_file", "write_file", "delete_file", "list_dir", "rename_file"]:
                        path = params.get("path") or params.get("dir") or params.get("old")
                        if path and not self._is_path_safe(path):
                            return False, f"路径 {path} 不在安全目录内"
                    return True, axiom["reason"]
                else:
                    return False, axiom["reason"]
        return False, "动作未在公理中定义"

    def _is_path_safe(self, raw_path: str) -> bool:
        """检查路径是否在安全目录内（防止目录穿越）"""
        try:
            full_path = (SAFE_ROOT / raw_path).resolve()
            return full_path.is_relative_to(SAFE_ROOT)
        except Exception:
            return False

    def generate_temp_token(self, action: str, params: Dict) -> str:
        """生成一次性临时编码，并存储动作和参数"""
        token = secrets.token_hex(8)  # 16位十六进制，足够演示
        self._temp_tokens[token] = (action, params)
        return token

    def process_request(self, request_text: str) -> str:
        """
        智能体请求入口：解析请求，检查权限，若允许则返回临时编码，
        否则返回拒绝信息。
        """
        parsed = self.parse_request(request_text)
        if not parsed:
            return "错误：无法解析请求，请使用标准格式。"

        action, params = parsed
        allowed, reason = self.check_permission(action, params)
        if not allowed:
            return f"拒绝：{reason}"

        token = self.generate_temp_token(action, params)
        return f"允许，临时编码：{token}"

    def execute(self, token: str) -> str:
        """
        智能体使用临时编码触发实际执行。执行后立即销毁该编码。
        """
        if token not in self._temp_tokens:
            return "错误：无效或已过期的临时编码。"

        action, params = self._temp_tokens.pop(token)  # 一次性使用
        return self._do_action(action, params)

    def _do_action(self, action: str, params: Dict) -> str:
        """实际执行文件操作（下层代理）"""
        try:
            if action == "read_file":
                path = SAFE_ROOT / params["path"]
                if not path.exists():
                    return f"错误：文件 {path} 不存在"
                return path.read_text(encoding='utf-8')

            elif action == "write_file":
                path = SAFE_ROOT / params["path"]
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(params["content"], encoding='utf-8')
                return f"成功写入文件 {path}"

            elif action == "delete_file":
                # 本应禁止，但若因公理允许则执行（演示用）
                path = SAFE_ROOT / params["path"]
                if path.exists():
                    path.unlink()
                    return f"成功删除文件 {path}"
                else:
                    return f"错误：文件 {path} 不存在"

            elif action == "list_dir":
                dir_path = SAFE_ROOT / params["dir"]
                if not dir_path.is_dir():
                    return f"错误：目录 {dir_path} 不存在"
                files = [f.name for f in dir_path.iterdir()]
                return f"目录内容：{', '.join(files)}"

            elif action == "rename_file":
                old = SAFE_ROOT / params["old"]
                new = SAFE_ROOT / params["new"]
                if not old.exists():
                    return f"错误：原文件 {old} 不存在"
                if new.exists():
                    return f"错误：新文件 {new} 已存在"
                old.rename(new)
                return f"成功重命名 {old} -> {new}"

            else:
                return f"错误：未实现的动作 {action}"

        except Exception as e:
            return f"执行错误：{str(e)}"


# ============================
# 3. 模拟智能体测试
# ============================
def simulate_agent(cage: CAGE, request: str):
    """模拟智能体发送请求并执行流程"""
    print(f"\n[智能体] 请求：{request}")
    response = cage.process_request(request)
    print(f"[CAGE] 响应：{response}")

    if "临时编码" in response:
        token = response.split("：")[-1].strip()
        exec_result = cage.execute(token)
        print(f"[CAGE] 执行结果：{exec_result}")
    else:
        print("[CAGE] 无临时编码，流程终止。")

def prepare_test_environment():
    """准备测试用的文件和目录"""
    (SAFE_ROOT / "test.txt").write_text("这是测试文件的内容", encoding='utf-8')
    (SAFE_ROOT / "data").mkdir(exist_ok=True)
    (SAFE_ROOT / "data" / "note.txt").write_text("data目录下的笔记", encoding='utf-8')
    print(f"测试环境已准备，安全根目录：{SAFE_ROOT}")

def main():
    print("=== CAGE demo for File Management Agent ===\n")
    prepare_test_environment()

    cage = CAGE(ACTION_PATTERNS, AXIOMS)

    # 测试用例
    test_requests = [
        "读取文件：test.txt",                         # 允许
        "列出目录：.",                                 # 允许
        "写入文件：new.txt，内容：Hello World",         # 允许
        "删除文件：test.txt",                           # 禁止
        "重命名文件：new.txt，新名称：renamed.txt",      # 禁止
        "读取文件：../outside.txt",                    # 路径穿越，应被拦截
        "列出目录：nonexist",                           # 目录不存在，但动作允许，实际执行会报错
        "这是一个乱码请求",                              # 无法解析
    ]

    for req in test_requests:
        simulate_agent(cage, req)

    # 额外展示临时编码的一次性特性
    print("\n=== 测试一次性临时编码 ===")
    request = "读取文件：test.txt"
    resp = cage.process_request(request)
    print(f"首次请求：{resp}")
    token = resp.split("：")[-1].strip()
    print(f"第一次执行：{cage.execute(token)}")
    print(f"第二次使用同一编码：{cage.execute(token)}")  # 应返回无效

if __name__ == "__main__":
    main()