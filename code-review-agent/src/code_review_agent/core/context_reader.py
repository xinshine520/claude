"""Context Reader - 读取文件获取上下文."""

from ..tools import reader as reader_tools


class ContextReader:
    """读取文件获取上下文"""

    async def read_changed_files(self, diff: str) -> dict[str, dict]:
        """
        读取 diff 中涉及的所有文件

        Args:
            diff: Git diff 内容

        Returns:
            dict mapping file path to file content and metadata
        """
        files = self._extract_files_from_diff(diff)

        # 读取每个文件
        contents = {}
        for file in files:
            result = await reader_tools.read_file(file)
            contents[file] = result

        return contents

    def _extract_files_from_diff(self, diff: str) -> list[str]:
        """从 diff 中提取文件列表"""
        files = []
        for line in diff.split("\n"):
            if line.startswith("diff --git"):
                # 提取文件名 a/src/file.py b/src/file.py
                parts = line.split()
                if len(parts) >= 4:
                    # 去掉 a/ 或 b/
                    file_path = parts[2][2:] if parts[2].startswith("a/") else parts[2]
                    files.append(file_path)
        return list(set(files))

    async def read_file(self, file_path: str) -> dict:
        """
        读取单个文件

        Args:
            file_path: 文件路径

        Returns:
            dict with content, lines, error
        """
        return await reader_tools.read_file(file_path)

    def extract_file_diff(self, full_diff: str, file_path: str) -> str:
        """
        从完整 diff 中提取特定文件的 diff

        Args:
            full_diff: 完整 diff
            file_path: 文件路径

        Returns:
            该文件的 diff
        """
        lines = full_diff.split("\n")
        file_diff_lines = []
        in_target_file = False

        for line in lines:
            if line.startswith("diff --git"):
                # 检查是否是目标文件
                if f"/{file_path}" in line or line.endswith(f"{file_path}"):
                    in_target_file = True
                else:
                    in_target_file = False

            if in_target_file:
                file_diff_lines.append(line)

        return "\n".join(file_diff_lines)
