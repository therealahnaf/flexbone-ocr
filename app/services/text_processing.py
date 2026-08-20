class TextProcessingService:
    @staticmethod
    def clean(text: str) -> str:
        normalized = text.replace("\r\n", "\n").replace("\r", "\n")
        lines = [line.rstrip() for line in normalized.split("\n")]

        while lines and not lines[0]:
            lines.pop(0)
        while lines and not lines[-1]:
            lines.pop()

        cleaned: list[str] = []
        blank_count = 0
        for line in lines:
            if line:
                blank_count = 0
                cleaned.append(line)
                continue
            blank_count += 1
            if blank_count <= 2:
                cleaned.append("")

        return "\n".join(cleaned)
