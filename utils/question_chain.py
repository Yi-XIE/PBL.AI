import re
from typing import List


def parse_question_chain(text: str) -> List[str]:
    if not text:
        return []
    questions: List[str] = []
    for line in text.splitlines():
        cleaned = line.strip()
        if not cleaned:
            continue
        match = re.match(r"^\d+[.\)\u3001]\s*(.+)$", cleaned)
        if match:
            questions.append(match.group(1).strip())
            continue
        bullet = re.match(r"^[-*]\s+(.+)$", cleaned)
        if bullet:
            questions.append(bullet.group(1).strip())
    return questions
